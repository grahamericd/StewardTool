from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
STEWARD = {"X-User-Email": "steward@demo.gov"}


def _asset_and_resource():
    assets = client.get("/api/assets", headers=STEWARD).json()
    asset = assets[0]
    structured = next(resource for resource in asset["resources"] if resource["structure_type"] == "STRUCTURED")
    return asset["asset"]["asset_id"], structured["resource_id"]


def test_milestone_33_quality_assessment_and_resolution_flow():
    with client:
        asset_id, resource_id = _asset_and_resource()

        assessment = client.post(
            f"/api/assets/{asset_id}/quality/assess",
            headers=STEWARD,
            json={"resource_id": resource_id},
        )
        assert assessment.status_code == 200, assessment.text
        quality_summary = assessment.json()
        assert quality_summary["overall_score"] >= 0
        assert "profile_run_id" in quality_summary

        full_quality = client.get(f"/api/assets/{asset_id}/quality", headers=STEWARD).json()
        assert "profiles" in full_quality
        assert "rules" in full_quality
        assert "issues" in full_quality

        proposed_rule = next(rule for rule in full_quality["rules"] if rule["status"] == "PROPOSED")
        approved = client.patch(
            f"/api/quality/rules/{proposed_rule['id']}/status",
            headers=STEWARD,
            json={"status": "APPROVED"},
        )
        assert approved.status_code == 200, approved.text

        run = client.post(
            f"/api/assets/{asset_id}/quality/run",
            headers=STEWARD,
            json={"resource_id": resource_id},
        )
        assert run.status_code == 200, run.text

        refreshed = client.get(f"/api/assets/{asset_id}/quality", headers=STEWARD).json()
        issues = refreshed["issues"]
        assert issues
        issue = next(
            issue
            for issue in issues
            if issue["status"] == "OPEN" and issue["issue_type"] == "RULE_FAILURE"
        )
        decision = client.post(
            f"/api/quality/issues/{issue['id']}/decision",
            headers=STEWARD,
            json={"decision_type": "BAD_DATA", "notes": "Confirmed with the source owner."},
        )
        assert decision.status_code == 200, decision.text
        assert decision.json()["status"] == "RESOLVED"
