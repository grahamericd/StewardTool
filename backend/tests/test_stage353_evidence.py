from app.services.quality_orchestrator import (
    _evidence_sufficiency,
    _profile_context_for_column,
)


def test_profile_context_extracts_common_stats():
    columns = [{
        "column_name": "fei_number",
        "data_type": "text",
        "semantic_type": "ID",
        "row_count": 1044,
        "distinct_count": 1000,
        "null_count": 4,
        "min_length": 4,
        "max_length": 13,
    }]
    context = _profile_context_for_column("fei_number", columns)
    assert context["data_type"] == "text"
    assert context["row_count"] == 1044
    assert context["distinct_count"] == 1000
    assert context["min_length"] == 4


def test_low_evidence_requires_caution():
    result = _evidence_sufficiency({}, {})
    assert result["level"] == "LOW"
    assert "not enough evidence" in result["guidance"].lower()


def test_higher_evidence_is_actionable():
    result = _evidence_sufficiency(
        {"observed_values": ["1002"], "affected_count": 1},
        {"row_count": 1044, "distinct_count": 1000, "typical_values": [{"value": "P0900"}]},
    )
    assert result["level"] == "HIGH"
