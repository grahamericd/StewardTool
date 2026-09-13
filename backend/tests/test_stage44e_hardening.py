from datetime import datetime, timezone

from app.api import auth_routes


def test_login_failure_tracking_can_be_cleared():
    key = "127.0.0.1|user@example.com"
    auth_routes._clear_login_failures(key)
    auth_routes._record_login_failure(key)
    assert len(auth_routes._LOGIN_FAILURES[key]) == 1
    auth_routes._clear_login_failures(key)
    assert key not in auth_routes._LOGIN_FAILURES


def test_temporary_failure_store_uses_datetimes():
    key = "127.0.0.1|another@example.com"
    auth_routes._clear_login_failures(key)
    auth_routes._record_login_failure(key)
    assert isinstance(auth_routes._LOGIN_FAILURES[key][0], datetime)
    assert auth_routes._LOGIN_FAILURES[key][0].tzinfo is not None
    auth_routes._clear_login_failures(key)
