def test_stage41_routes_present():
    from app.api import routes
    names = {route.name for route in routes.router.routes}
    assert "request_task_expert_review" in names
    assert "resume_task" in names
