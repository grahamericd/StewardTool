def test_understanding_route_exists():
    from app.api import routes
    paths = {getattr(route, "path", "") for route in routes.router.routes}
    assert "/assets/{asset_id}/understanding" in paths
