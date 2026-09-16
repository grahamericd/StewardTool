from datetime import datetime

from app.api import auth_routes


def _keys(email="person@example.com"):
    return [f"ip:203.0.113.10|{email}", f"account:{email}"]


def test_login_failure_tracking_can_be_cleared():
    keys = _keys()
    auth_routes._clear_login_failures(keys)
    auth_routes._record_login_failure(keys)
    assert all(len(auth_routes._LOGIN_FAILURES[key]) == 1 for key in keys)
    auth_routes._clear_login_failures(keys)
    assert all(key not in auth_routes._LOGIN_FAILURES for key in keys)


def test_temporary_failure_store_uses_datetimes():
    keys = _keys("another@example.com")
    auth_routes._clear_login_failures(keys)
    auth_routes._record_login_failure(keys)
    assert all(
        isinstance(auth_routes._LOGIN_FAILURES[key][0], datetime) for key in keys
    )
    auth_routes._clear_login_failures(keys)
