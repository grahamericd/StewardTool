from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
STEWARD = {"X-User-Email": "steward@demo.gov"}


def test_discovery_candidates_require_explicit_human_confirmation():
    with client:
        created = client.post(
            "/api/discovery/candidates",
            headers=STEWARD,
            json={
                "name": "Discovery Candidate Example",
                "kind": "INFORMATION",
                "summary": "Suggested during discovery",
                "status": "SUGGESTED",
                "source": "USER",
            },
        )
        assert created.status_code == 200
        candidate_id = created.json()["id"]

        patched = client.patch(
            f"/api/discovery/candidates/{candidate_id}",
            headers=STEWARD,
            json={"status": "CONFIRMED"},
        )
        assert patched.status_code == 400

        confirmed = client.post(f"/api/discovery/candidates/{candidate_id}/confirm", headers=STEWARD)
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "CONFIRMED"

        fetched = client.get("/api/discovery/candidates", headers=STEWARD)
        assert fetched.status_code == 200
        payload = fetched.json()
        assert any(item["id"] == candidate_id and item["status"] == "CONFIRMED" for item in payload)


def test_discovery_summary_reports_ground_zero_state():
    with client:
        summary = client.get("/api/discovery/summary", headers=STEWARD)
        assert summary.status_code == 200
        payload = summary.json()
        assert "ground_zero" in payload
        assert "known_assets" in payload
        assert "known_systems" in payload
        assert "known_locations" in payload
        assert isinstance(payload["ground_zero"], bool)
        assert payload["meaningful_landscape"] is (not payload["ground_zero"])


def test_discovery_sessions_are_resumable_and_reviewable():
    with client:
        created = client.post(
            "/api/discovery/sessions",
            headers=STEWARD,
            json={
                "title": "Licensing landscape refresh",
                "summary": "Review the applicant flow and the licensing records it creates.",
            },
        )
        assert created.status_code == 200
        session_id = created.json()["id"]

        paused = client.patch(
            f"/api/discovery/sessions/{session_id}",
            headers=STEWARD,
            json={"status": "PAUSED", "summary": "Awaiting confirmatory interview follow-up."},
        )
        assert paused.status_code == 200
        assert paused.json()["status"] == "PAUSED"

        evidence = client.post(
            f"/api/discovery/sessions/{session_id}/evidence",
            headers=STEWARD,
            json={
                "entity_type": "BusinessFunction",
                "entity_id": 1,
                "evidence_type": "screening",
                "summary": "The licensing team reviewed the application intake screen.",
                "details": {"source": "user_interview"},
            },
        )
        assert evidence.status_code == 200

        assertion = client.post(
            f"/api/discovery/sessions/{session_id}/assertions",
            headers=STEWARD,
            json={
                "entity_type": "BusinessFunction",
                "entity_id": 1,
                "assertion_type": "business_context",
                "statement": "The licensing process is reviewed weekly.",
                "confidence": 0.85,
            },
        )
        assert assertion.status_code == 200

        fetched = client.get(f"/api/discovery/sessions/{session_id}", headers=STEWARD)
        assert fetched.status_code == 200
        assert fetched.json()["status"] == "PAUSED"

        evidence_list = client.get(f"/api/discovery/sessions/{session_id}/evidence", headers=STEWARD)
        assert evidence_list.status_code == 200
        assert any(item["summary"] == "The licensing team reviewed the application intake screen." for item in evidence_list.json())

        assertion_list = client.get(f"/api/discovery/sessions/{session_id}/assertions", headers=STEWARD)
        assert assertion_list.status_code == 200
        assert any(item["statement"] == "The licensing process is reviewed weekly." for item in assertion_list.json())


def test_discovery_candidate_creation_records_reviewable_provenance():
    with client:
        created = client.post(
            "/api/discovery/candidates",
            headers=STEWARD,
            json={
                "name": "Licensing application intake",
                "kind": "INFORMATION",
                "summary": "New candidate suggested during landscape review",
                "status": "SUGGESTED",
                "source": "USER",
            },
        )
        assert created.status_code == 200

        provenance = client.get("/api/discovery/provenance", headers=STEWARD)
        assert provenance.status_code == 200
        payload = provenance.json()
        assert any(item["action"] == "SUGGESTED" and item["entity_type"] == "DiscoveryCandidate" for item in payload)
