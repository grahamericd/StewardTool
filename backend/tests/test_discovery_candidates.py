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
