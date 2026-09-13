from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.task_service import _sync_periodic_review_task


class FakeDB:
    def __init__(self):
        self.added = []
    def add(self, item):
        self.added.append(item)


def test_periodic_review_task_not_due_for_new_asset():
    db = FakeDB()
    asset = SimpleNamespace(
        id=1,
        organization_id=1,
        created_at=datetime.now(timezone.utc),
        reviews=[],
    )
    _sync_periodic_review_task(db, asset, [])
    assert db.added == []


def test_periodic_review_task_created_when_due():
    db = FakeDB()
    asset = SimpleNamespace(
        id=1,
        organization_id=1,
        created_at=datetime.now(timezone.utc) - timedelta(days=500),
        reviews=[],
    )
    _sync_periodic_review_task(db, asset, [])
    assert len(db.added) == 1
    assert db.added[0].task_type == "periodic_review"
    assert db.added[0].source_type == "PERIODIC_REVIEW"


def test_periodic_review_routes_exist():
    from app.api import routes
    paths = {getattr(route, "path", "") for route in routes.router.routes}
    assert "/assets/{asset_id}/reviews" in paths
