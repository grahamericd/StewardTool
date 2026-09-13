from types import SimpleNamespace
from app.api.routes import _task_guidance, _task_bucket


def make_task(domain="", source_type="", status="OPEN"):
    return SimpleNamespace(
        governance_domain=domain,
        source_type=source_type,
        status=status,
    )


def test_quality_task_teaches_trust():
    result = _task_guidance(make_task(source_type="QUALITY_ISSUE"))
    assert result["responsibility"] == "Trust the information"
    assert "evidence" in result["learn_text"].lower()


def test_classification_task_teaches_protection():
    result = _task_guidance(make_task(domain="CLASSIFICATION"))
    assert "Protect" in result["responsibility"]


def test_waiting_bucket():
    assert _task_bucket(make_task(status="NEEDS_EXPERT_REVIEW")) == "WAITING"
    assert _task_bucket(make_task(status="OPEN")) == "NOW"
