from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
STEWARD = {"X-User-Email": "steward@demo.gov"}


def _asset_id():
    assets = client.get("/api/assets", headers=STEWARD).json()
    assert assets, "No asset records were found for the organization."
    return assets[0]["asset"]["asset_id"]


def test_milestone_32_understanding_and_metadata_round_trip():
    with client:
        asset_id = _asset_id()
        payload = {
            "business_definition": "This collection captures licensing applications received from applicants.",
            "business_area": "Licensing",
            "search_terms": ["license application", "professional licensing"],
            "update_frequency": "Weekly",
            "contact_point": {"name": "Licensing operations", "email": "licensing@example.gov"},
        }

        patched = client.patch(
            f"/api/assets/{asset_id}/understanding",
            headers=STEWARD,
            json=payload,
        )
        assert patched.status_code == 200, patched.text

        readback = client.get(f"/api/assets/{asset_id}/understanding", headers=STEWARD)
        assert readback.status_code == 200, readback.text
        readback_body = readback.json()
        assert readback_body["business_definition"] == payload["business_definition"]
        assert readback_body["business_area"] == payload["business_area"]
        assert "license application" in readback_body["search_terms"]
        assert readback_body["contact_point"]["email"] == "licensing@example.gov"

        metadata = client.put(
            f"/api/assets/{asset_id}/metadata",
            headers=STEWARD,
            json={
                "metadata_key": "theme",
                "metadata_value": ["Licensing", "Applications"],
                "metadata_source": "USER",
            },
        )
        assert metadata.status_code == 200, metadata.text

        metadata_snapshot = client.get(f"/api/assets/{asset_id}", headers=STEWARD).json()
        assert metadata_snapshot["metadata"]["theme"] == ["Licensing", "Applications"]
