from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
STEWARD = {"X-User-Email": "steward@demo.gov"}
APPROVER = {"X-User-Email": "approver@demo.gov"}


def _ready_asset():
    assets = client.get("/api/assets", headers=STEWARD).json()
    match = next(
        (
            asset
            for asset in assets
            if asset["publication"]["status"] in {"DRAFT", "REJECTED", "NEEDS_UPDATE"}
            and asset["readiness"]["ready_to_submit"]
        ),
        None,
    )
    if match is not None:
        return match

    # Keep this workflow test independent of whichever demo records happen to
    # be present or were changed by an earlier test.
    created = client.post(
        "/api/assets",
        headers=STEWARD,
        json={
            "name": "Milestone 31 submission fixture",
            "business_definition": "A self-contained record used to validate submission and approval.",
            "business_owner": "Milestone Test Owner",
        },
    )
    assert created.status_code == 200, created.text
    asset_id = created.json()["asset"]["asset_id"]
    location = client.post(
        f"/api/assets/{asset_id}/resources",
        headers=STEWARD,
        json={
            "name": "Milestone 31 authoritative fixture",
            "resource_type": "TABLE",
            "structure_type": "STRUCTURED",
            "is_authoritative": True,
        },
    )
    assert location.status_code == 200, location.text
    theme = client.put(
        f"/api/assets/{asset_id}/metadata",
        headers=STEWARD,
        json={"metadata_key": "theme", "metadata_value": ["Integration testing"]},
    )
    assert theme.status_code == 200, theme.text
    ready = client.get(f"/api/assets/{asset_id}", headers=STEWARD)
    assert ready.status_code == 200, ready.text
    assert ready.json()["readiness"]["ready_to_submit"] is True
    return ready.json()


def test_milestone_31_submission_and_approval_flow():
    with client:
        asset = _ready_asset()
        asset_id = asset["asset"]["asset_id"]

        submitted = client.post(
            f"/api/assets/{asset_id}/submit",
            headers=STEWARD,
            json={"comments": "Ready for review."},
        )
        assert submitted.status_code == 200, submitted.text
        submitted_payload = submitted.json()
        assert submitted_payload["publication"]["status"] == "IN_REVIEW"

        approved = client.post(
            f"/api/assets/{asset_id}/approve",
            headers=APPROVER,
            json={"comments": "Approved after review."},
        )
        assert approved.status_code == 200, approved.text
        approved_payload = approved.json()
        assert approved_payload["publication"]["status"] == "APPROVED"
