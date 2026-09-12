from app.services.quality_orchestrator import (
    _quality_score_from_results,
    _test_result_key,
)


def test_quality_score_prefers_record_evidence():
    items = [
        {"status": "FAILED", "evaluated_count": 100, "failed_count": 10},
        {"status": "PASSED", "evaluated_count": 100, "failed_count": 0},
    ]
    assert _quality_score_from_results(items) == 95.0


def test_quality_score_falls_back_to_test_pass_rate():
    items = [
        {"status": "PASSED"},
        {"status": "FAILED"},
        {"status": "PASSED"},
        {"status": "PASSED"},
    ]
    assert _quality_score_from_results(items) == 75.0


def test_test_result_key_prefers_external_id():
    assert _test_result_key({"test_definition_id": "abc"}, 1) == "external:abc"
