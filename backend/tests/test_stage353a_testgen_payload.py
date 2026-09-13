from app.services.quality_orchestrator import (
    _hygiene_count,
    _hygiene_kind,
    _parse_testgen_detail,
    _raw_evidence,
)


def test_testgen_issue_name_preferred_over_numeric_code():
    raw = {
        "issue_type": "1002",
        "issue_type_name": "Non-Standard Blank Values",
    }
    assert _hygiene_kind(raw) == "Non-Standard Blank Values"


def test_blank_detail_parses_counts():
    raw = {
        "issue_type": "1002",
        "issue_type_name": "Non-Standard Blank Values",
        "detail": "Dummy Values: 0, Empty String: 5034, Null: 0, Records: 5195",
    }
    assert _hygiene_count(raw) == 5034
    evidence = _raw_evidence(raw)
    assert evidence["records_profiled"] == 5195
    assert evidence["affected_count"] == 5034
    assert evidence["affected_percent"] == 96.9


def test_zip_patterns_parse_and_estimate_noncanonical_formats():
    raw = {
        "issue_type": "1003",
        "issue_type_name": "Invalid USA Zip Code Format",
        "detail": "Patterns: NNNNN (5064), NNNNN--NNN (88), NNNNN-NNNN (18), NNNN (7), NNNNN-N (5), Dummy Values: 0",
    }
    parsed = _parse_testgen_detail(raw["detail"])
    assert len(parsed["patterns"]) == 5
    assert _hygiene_count(raw) == 100


def test_non_alpha_count_parses():
    raw = {
        "issue_type_name": "Non-Alpha Name or Address",
        "detail": "Non-Alpha Values: 37, Semantic Type: City, Records: 5195",
    }
    assert _hygiene_count(raw) == 37
