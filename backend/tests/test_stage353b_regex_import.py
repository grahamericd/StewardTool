from app.services.quality_orchestrator import _parse_testgen_detail


def test_testgen_detail_parser_executes_regex_path():
    parsed = _parse_testgen_detail(
        "Dummy Values: 0, Empty String: 5034, Null: 0, Records: 5195"
    )
    assert parsed["empty_string_count"] == 5034
    assert parsed["records"] == 5195
