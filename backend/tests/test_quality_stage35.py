from app.services.quality_orchestrator import _apply_testgen_defaults


class Link:
    project_code = None
    table_group_id = None
    test_suite_id = None


def test_env_defaults_fill_blank_mapping(monkeypatch):
    monkeypatch.setattr(
        "app.services.quality_orchestrator.settings.testgen_project_code",
        "DEFAULT",
    )
    monkeypatch.setattr(
        "app.services.quality_orchestrator.settings.testgen_table_group_id",
        "table-group-id",
    )
    monkeypatch.setattr(
        "app.services.quality_orchestrator.settings.testgen_test_suite_id",
        "test-suite-id",
    )
    link = Link()
    _apply_testgen_defaults(link)
    assert link.project_code == "DEFAULT"
    assert link.table_group_id == "table-group-id"
    assert link.test_suite_id == "test-suite-id"


def test_resource_mapping_wins_over_env(monkeypatch):
    monkeypatch.setattr(
        "app.services.quality_orchestrator.settings.testgen_project_code",
        "ENV",
    )
    monkeypatch.setattr(
        "app.services.quality_orchestrator.settings.testgen_table_group_id",
        "env-group",
    )
    monkeypatch.setattr(
        "app.services.quality_orchestrator.settings.testgen_test_suite_id",
        "env-suite",
    )
    link = Link()
    link.project_code = "RESOURCE"
    link.table_group_id = "resource-group"
    link.test_suite_id = "resource-suite"
    _apply_testgen_defaults(link)
    assert link.project_code == "RESOURCE"
    assert link.table_group_id == "resource-group"
    assert link.test_suite_id == "resource-suite"
