def test_official_source_route_exists():
    from app.api import routes
    paths = {getattr(route, "path", "") for route in routes.router.routes}
    assert "/assets/{asset_id}/official-source" in paths
