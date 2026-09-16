from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)
STEWARD = {"X-User-Email": "steward@demo.gov"}
APPROVER = {"X-User-Email": "approver@demo.gov"}


def test_dashboard_and_tasks():
    with client:
        dash = client.get("/api/dashboard", headers=STEWARD)
        assert dash.status_code == 200
        assert dash.json()["assets"] >= 1
        tasks = client.get("/api/tasks", headers=STEWARD)
        assert tasks.status_code == 200
        assert isinstance(tasks.json(), list)


def test_quality_is_attached_to_asset():
    with client:
        assets = client.get("/api/assets", headers=STEWARD).json()
        asset_id = assets[0]["asset"]["asset_id"]
        quality = client.get(f"/api/assets/{asset_id}/quality", headers=STEWARD)
        assert quality.status_code == 200
        assert "profiles" in quality.json()
        assert "rules" in quality.json()


def test_submitter_cannot_self_approve():
    with client:
        assets = client.get("/api/assets", headers=STEWARD).json()
        asset = assets[0]
        aid = asset["asset"]["asset_id"]
        if asset["publication"]["status"] in {"DRAFT", "REJECTED", "NEEDS_UPDATE"} and asset["readiness"]["ready_to_submit"]:
            submitted = client.post(f"/api/assets/{aid}/submit", headers=STEWARD, json={"comments":"test"})
            assert submitted.status_code == 200
            self_approve = client.post(f"/api/assets/{aid}/approve", headers=STEWARD, json={"comments":"test"})
            assert self_approve.status_code in {400, 403}
