from app.api.admin_routes import ALLOWED_ROLES, MANAGEMENT_ROLES, _temporary_password


def test_expected_roles_are_available():
    assert {"STEWARD", "APPROVER", "ORG_ADMIN", "VIEWER", "ENTERPRISE_ADMIN"} == ALLOWED_ROLES
    assert "ORG_ADMIN" in MANAGEMENT_ROLES


def test_temporary_password_is_long_and_unique():
    first = _temporary_password()
    second = _temporary_password()
    assert len(first) >= 20
    assert len(second) >= 20
    assert first != second
