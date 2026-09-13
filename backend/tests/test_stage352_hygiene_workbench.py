from app.services.quality_orchestrator import (
    _hygiene_plain_language,
    _normalize_hygiene_findings,
    _hygiene_summary,
)


def test_missing_values_translate_to_plain_language():
    title, why, action, category = _hygiene_plain_language(
        "mail_zip",
        "missing values",
    )
    assert title == "mail_zip has missing values"
    assert category == "COMPLETENESS"
    assert "required" in action.lower()


def test_normalizer_preserves_prior_decision():
    raw = [{"column_name": "zip", "issue_type": "format inconsistency"}]
    initial = _normalize_hygiene_findings(raw)
    initial[0]["review_status"] = "RESOLVED"
    initial[0]["decision"] = "VALID_EXCEPTION"
    rerun = _normalize_hygiene_findings(raw, initial)
    assert rerun[0]["review_status"] == "RESOLVED"
    assert rerun[0]["decision"] == "VALID_EXCEPTION"


def test_summary_counts_actionable_states():
    findings = [
        {"category": "VALIDITY", "review_status": "PENDING"},
        {"category": "VALIDITY", "review_status": "RESOLVED"},
        {"category": "PROFILE", "review_status": "ESCALATED"},
    ]
    summary = _hygiene_summary(findings)
    assert summary["total"] == 3
    assert summary["pending"] == 1
    assert summary["resolved"] == 1
    assert summary["escalated"] == 1
    assert summary["categories"]["VALIDITY"] == 2
