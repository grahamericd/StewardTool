from fastapi.testclient import TestClient

from app.main import app


def test_understanding_route_exists():
    from app.api import routes
    paths = {getattr(route, "path", "") for route in routes.router.routes}
    assert "/assets/{asset_id}/understanding" in paths


def test_understanding_round_trip_persists_business_context():
    client = TestClient(app)
    with client:
        created = client.post(
            "/api/assets",
            headers={"X-User-Email": "steward@demo.gov"},
            json={"name": "License application register"},
        )
        assert created.status_code == 200
        asset_id = created.json()["asset"]["asset_id"]

        patched = client.patch(
            f"/api/assets/{asset_id}/understanding",
            headers={"X-User-Email": "steward@demo.gov"},
            json={
                "business_definition": "A record of licensing applications submitted by residents.",
                "business_area": "Professional licensing",
                "search_terms": ["licenses", "permits", "application status"],
                "update_frequency": "WEEKLY",
                "contact_point": {"name": "Licensing Data Steward", "email": "licensing@example.gov"},
            },
        )
        assert patched.status_code == 200

        fetched = client.get(
            f"/api/assets/{asset_id}/understanding",
            headers={"X-User-Email": "steward@demo.gov"},
        )
        assert fetched.status_code == 200
        payload = fetched.json()
        assert payload["business_definition"].startswith("A record of licensing applications")
        assert payload["business_area"] == "Professional licensing"
        assert payload["search_terms"] == ["licenses", "permits", "application status"]
        assert payload["update_frequency"] == "WEEKLY"
        assert payload["contact_point"]["name"] == "Licensing Data Steward"
        assert payload["contact_point"]["email"] == "licensing@example.gov"
