"""Regression tests for the defects found in the independent code review.

Each test names the finding it covers so that a future change that reintroduces
the behaviour fails here rather than in production.
"""

import pytest
from fastapi.testclient import TestClient

from app.api import auth_routes
from app.config import Settings
from app.db import UTCDateTime
from app.integrations.testgen.client import TestGenError as TestGenFailure
from app.integrations.testgen.client import _segment
from app.services import quality_orchestrator as qo

from conftest import STEWARD


# --- BUG-01: the decision route required a stray query parameter -------------


def test_quality_issue_decision_accepts_a_json_body_only(client):
    """The endpoint used to answer 422 because of a leftover parameter name."""
    response = client.post(
        "/api/quality/issues/999999/decision",
        headers=STEWARD,
        json={"decision_type": "BAD_DATA", "notes": "checked with the owner"},
    )
    # 404 because the issue id is invented; the point is that the body validated.
    assert response.status_code == 404, response.text


def test_quality_issue_decision_resolves_and_records_who_decided(client, first_asset_id):
    resource_id = _structured_resource_id(client, first_asset_id)
    client.post(
        f"/api/assets/{first_asset_id}/quality/assess",
        headers=STEWARD,
        json={"resource_id": resource_id},
    )
    issues = client.get(f"/api/assets/{first_asset_id}/quality", headers=STEWARD).json()["issues"]
    open_issues = [i for i in issues if i["status"] == "OPEN"]
    assert open_issues, "assessment should raise at least one issue in mock mode"

    response = client.post(
        f"/api/quality/issues/{open_issues[0]['id']}/decision",
        headers=STEWARD,
        json={"decision_type": "VALID_EXCEPTION", "notes": "expected for this source"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "RESOLVED"


# --- ORCH-01: decide_hygiene_finding used a column name that does not exist --


def test_quality_decision_model_accepts_decided_by():
    """QualityDecision has decided_by, not actor_id; the wrong name raised TypeError."""
    from app.models import QualityDecision

    decision = QualityDecision(issue_id=1, decided_by=2, decision_type="HYGIENE_BAD_DATA")
    assert decision.decided_by == 2
    with pytest.raises(TypeError):
        QualityDecision(issue_id=1, actor_id=2, decision_type="x")


# --- ORCH-02: readable TestGen names lost to numeric codes -------------------


def test_hygiene_kind_prefers_the_readable_name_whatever_the_payload_order():
    payload = {"issue_type": "1002", "issue_type_name": "Non-Standard Blank Values"}
    assert qo._hygiene_kind(payload) == "Non-Standard Blank Values"
    assert qo._hygiene_kind(dict(reversed(list(payload.items())))) == "Non-Standard Blank Values"


def test_first_recursive_value_honours_key_priority():
    payload = {"second": "b", "first": "a"}
    assert qo._first_recursive_value(payload, ("first", "second")) == "a"
    assert qo._first_recursive_value(payload, ("second", "first")) == "b"
    assert qo._first_recursive_value(payload, ("missing",), "fallback") == "fallback"


# --- ORCH-07: an escalated issue belongs in the waiting bucket ---------------


def test_task_status_follows_the_issue_status():
    from app.models import QualityIssue

    assert qo._task_status_for_issue(QualityIssue(status="OPEN")) == "OPEN"
    assert (
        qo._task_status_for_issue(QualityIssue(status="NEEDS_EXPERT_REVIEW"))
        == "NEEDS_EXPERT_REVIEW"
    )


# --- BUG-02: SQLite returned naive datetimes --------------------------------


def test_utc_datetime_always_returns_aware_values():
    from datetime import datetime, timezone

    column = UTCDateTime()
    naive = datetime(2026, 1, 1, 12, 0, 0)
    assert column.process_result_value(naive, None).tzinfo is timezone.utc
    assert column.process_bind_param(naive, None).tzinfo is timezone.utc
    assert column.process_result_value(None, None) is None


def test_periodic_review_endpoint_works_on_sqlite(client, first_asset_id):
    """This comparison raised "can't compare offset-naive and offset-aware"."""
    response = client.get(f"/api/assets/{first_asset_id}/reviews", headers=STEWARD)
    assert response.status_code == 200, response.text
    assert "next_review_due" in response.json()


# --- BUG-03: the health check failed once TRUSTED_HOSTS was the real domain --


def test_loopback_is_always_a_trusted_host():
    settings = Settings(app_env="test", trusted_hosts="steward.example.com")
    assert "127.0.0.1" in settings.trusted_host_list
    assert "localhost" in settings.trusted_host_list
    assert "steward.example.com" in settings.trusted_host_list


def test_health_check_host_header_is_accepted():
    from app.main import app

    with TestClient(app, base_url="http://127.0.0.1:8000") as local:
        assert local.get("/health").status_code == 200


# --- BUG-06: tasks were ordered alphabetically by priority ------------------


def test_tasks_are_returned_highest_priority_first(client):
    priorities = [t["priority"] for t in client.get("/api/tasks", headers=STEWARD).json()]
    rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    assert priorities == sorted(priorities, key=lambda p: rank.get(p, 3))


# --- SEC-01: the login throttle trusted a client-supplied header -------------


def test_client_address_ignores_forwarded_header_without_trusted_proxies(monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "auth_trusted_proxy_hops", 0)
    request = _FakeRequest({"x-forwarded-for": "1.2.3.4"}, "10.0.0.1")
    assert auth_routes._client_address(request) == "10.0.0.1"


def test_client_address_uses_the_hop_the_trusted_proxy_recorded(monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "auth_trusted_proxy_hops", 2)
    # spoofed, real client (added by Caddy), Caddy (added by nginx)
    request = _FakeRequest({"x-forwarded-for": "9.9.9.9, 203.0.113.7, 172.18.0.4"}, "172.18.0.5")
    assert auth_routes._client_address(request) == "203.0.113.7"


def test_account_throttle_survives_a_rotating_forwarded_header(monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "auth_login_max_failures", 3)
    email = "throttle-target@example.com"
    auth_routes._clear_login_failures([f"account:{email}"])
    for index in range(3):
        auth_routes._record_login_failure([f"ip:10.0.0.{index}|{email}", f"account:{email}"])
    with pytest.raises(Exception) as excinfo:
        auth_routes._check_login_throttle([f"ip:10.0.0.99|{email}", f"account:{email}"])
    assert getattr(excinfo.value, "status_code", None) == 429
    auth_routes._clear_login_failures([f"account:{email}"])


# --- SEC-10: TestGen identifiers could redirect the request ------------------


@pytest.mark.parametrize(
    "value",
    ["x?limit=1#frag", "x/../../projects/other/jobs", "../../oauth/token", "", "a b"],
)
def test_testgen_path_segments_reject_anything_but_an_identifier(value):
    with pytest.raises(TestGenFailure):
        _segment(value, "TestGen table group id")


def test_testgen_path_segments_accept_a_uuid():
    value = "8e516582-c3af-4f5e-81ad-35bdbcd55f83"
    assert _segment(value, "TestGen table group id") == value


# --- SEC-11: raw engine payloads are no longer served ------------------------


def test_raw_engine_payloads_are_not_returned(client, first_asset_id):
    from app.api.routes import public_issue_details

    details = public_issue_details(
        {"steward_findings": [], "hygiene_issues": [{"a": 1}], "potential_pii": ["x"], "profile_columns": []}
    )
    assert "steward_findings" in details
    assert "hygiene_issues" not in details
    assert "potential_pii" not in details
    assert "profile_columns" not in details

    payload = client.get(f"/api/assets/{first_asset_id}/quality", headers=STEWARD).json()
    for issue in payload["issues"]:
        assert "potential_pii" not in (issue["details"] or {})


# --- SEC-04: production must configure OIDC fully ---------------------------


def test_production_requires_an_oidc_audience():
    with pytest.raises(ValueError, match="OIDC_AUDIENCE"):
        Settings(
            app_env="production",
            auth_mode="oidc",
            oidc_issuer="https://issuer.example.gov",
            seed_demo_data=False,
            enable_api_docs=False,
        )


# --- BUG-08: completing a readiness task silently did nothing ----------------


def test_completing_an_unmet_readiness_task_explains_itself(client):
    tasks = client.get("/api/tasks", headers=STEWARD).json()
    readiness = [t for t in tasks if t["source_type"] == "READINESS"]
    if not readiness:
        pytest.skip("no outstanding readiness task in the seeded data")
    response = client.post(
        f"/api/tasks/{readiness[0]['id']}/complete", headers=STEWARD, json={}
    )
    assert response.status_code == 400
    assert "completes itself" in response.json()["detail"]


# --- CQ: the dashboard used an arbitrary profile ----------------------------


def test_dashboard_reports_no_score_rather_than_zero_when_nothing_is_profiled():
    from app.api.routes import _average_quality_score

    class _Asset:
        quality_profiles: list = []

    assert _average_quality_score([_Asset()]) is None


# --- helpers ----------------------------------------------------------------


class _FakeRequest:
    def __init__(self, headers, peer):
        self.headers = headers
        self.client = type("Client", (), {"host": peer})()


def _structured_resource_id(client, asset_id):
    asset = client.get(f"/api/assets/{asset_id}", headers=STEWARD).json()
    for resource in asset["resources"]:
        if resource["structure_type"] == "STRUCTURED":
            return resource["resource_id"]
    pytest.skip("no structured resource in the seeded data")


def test_hygiene_finding_decision_is_recorded_end_to_end(client):
    """ORCH-01: this path raised TypeError before decided_by was used.

    Mock mode does not yet produce per-finding data, so a TestGen-shaped
    profiling item is supplied directly to exercise the decision path.
    """
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import DataAsset, QualityDecision, QualityIssue
    from app.services.quality_orchestrator import decide_hygiene_finding, enrich_hygiene_issue

    with SessionLocal() as db:
        asset = db.scalar(select(DataAsset))
        issue = QualityIssue(
            organization_id=asset.organization_id,
            asset_id=asset.id,
            issue_type="HYGIENE_FINDING",
            title="Review 1 TestGen profiling finding",
            severity="MEDIUM",
            source="TESTGEN",
            details={
                "hygiene_issues": [
                    {
                        "id": "finding-1",
                        "column_name": "mail_zip",
                        "issue_type": "1002",
                        "issue_type_name": "Non-Standard Blank Values",
                        "detail": "Missing values: 248",
                    }
                ],
                "profile_columns": [],
            },
        )
        db.add(issue)
        db.commit()
        issue_id = issue.id

        enrich_hygiene_issue(issue)
        findings = issue.details["steward_findings"]
        assert len(findings) == 1
        # ORCH-02: the numeric TestGen code must not reach the steward.
        assert "1002" not in findings[0]["title"]
        fingerprint = findings[0]["fingerprint"]

        decide_hygiene_finding(db, issue, 1, fingerprint, "VALID_EXCEPTION", "known format")

        assert issue.status == "RESOLVED"
        assert issue.details["steward_findings"][0]["review_status"] == "RESOLVED"
        decision = db.scalar(select(QualityDecision).where(QualityDecision.issue_id == issue_id))
        assert decision is not None
        assert decision.decided_by == 1
        assert decision.decision_type == "HYGIENE_VALID_EXCEPTION"
