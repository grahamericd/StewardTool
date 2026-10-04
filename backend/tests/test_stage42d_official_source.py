from fastapi.testclient import TestClient

from app.main import app


def test_official_source_route_exists():
    from app.api import routes
    paths = {getattr(route, "path", "") for route in routes.router.routes}
    assert "/assets/{asset_id}/official-source" in paths


def test_official_source_round_trip_reports_current_choice():
    client = TestClient(app)
    with client:
        created = client.post(
            "/api/assets",
            headers={"X-User-Email": "steward@demo.gov"},
            json={"name": "Permit ledger"},
        )
        assert created.status_code == 200
        asset_id = created.json()["asset"]["asset_id"]

        resource = client.post(
            f"/api/assets/{asset_id}/resources",
            headers={"X-User-Email": "steward@demo.gov"},
            json={
                "system_id": 1,
                "name": "Permit application table",
                "resource_type": "DATABASE_TABLE",
                "structure_type": "STRUCTURED",
                "description": "Primary permit record",
                "location_reference": "db:permits.application",
                "relationship_type": "REPRESENTATION",
                "is_authoritative": False,
            },
        )
        assert resource.status_code == 200
        resource_id = resource.json()["resources"][0]["resource_id"]

        chosen = client.post(
            f"/api/assets/{asset_id}/official-source",
            headers={"X-User-Email": "steward@demo.gov"},
            json={"resource_id": resource_id, "decision_basis": "This is the source where permit applications are maintained."},
        )
        assert chosen.status_code == 200

        fetched = client.get(
            f"/api/assets/{asset_id}/official-source",
            headers={"X-User-Email": "steward@demo.gov"},
        )
        assert fetched.status_code == 200
        payload = fetched.json()
        assert payload["asset_id"] == asset_id
        assert payload["official_source"]["resource_id"] == resource_id
        assert payload["official_source"]["name"] == "Permit application table"
        assert payload["official_source"]["is_authoritative"] is True
