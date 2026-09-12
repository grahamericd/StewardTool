from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..integrations.testgen.client import MockTestGenClient, TestGenClient, TestGenError
from ..models import (
    DataAsset, QualityDecision, QualityEngineResource, QualityIssue,
    QualityProfile, QualityResult, QualityRule, StewardshipTask,
)


def now():
    return datetime.now(timezone.utc)


def get_link(db: Session, resource_id: int):
    return db.scalar(select(QualityEngineResource).where(QualityEngineResource.resource_id == resource_id, QualityEngineResource.provider == 'TESTGEN'))


def ensure_link(db: Session, *, organization_id: int, resource_id: int, payload):
    link = get_link(db, resource_id)
    if not link:
        link = QualityEngineResource(organization_id=organization_id, resource_id=resource_id, provider='TESTGEN')
        db.add(link)
    for field in ('project_code','connection_id','table_group_id','test_suite_id','external_table_name'):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(link, field, value)
    if settings.testgen_mode == 'real':
        link.sync_status = 'CONFIGURED'
        if not link.project_code and settings.testgen_project_code:
            link.project_code = settings.testgen_project_code
    else:
        link.sync_status = 'MOCK_READY'
    db.flush()
    return link


def _open_task_for_issue(db: Session, issue: QualityIssue):
    existing = db.scalar(select(StewardshipTask).where(
        StewardshipTask.asset_id == issue.asset_id,
        StewardshipTask.source_type == 'QUALITY_ISSUE',
        StewardshipTask.source_reference == str(issue.id),
        StewardshipTask.status == 'OPEN',
    ))
    if existing:
        return existing
    task = StewardshipTask(
        organization_id=issue.organization_id,
        asset_id=issue.asset_id,
        task_type='quality_issue',
        governance_domain='QUALITY',
        title=issue.title,
        why_it_matters=issue.description or 'A quality finding needs a human stewardship decision.',
        recommended_action='Review the evidence and decide whether this is bad data, a valid exception, an expectation that needs to change, or something that needs expert review.',
        priority='HIGH' if issue.severity == 'HIGH' else 'MEDIUM',
        source_type='QUALITY_ISSUE',
        source_reference=str(issue.id),
    )
    db.add(task); db.flush(); return task


def _items(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("items", "results", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _recursive_number(payload, keys):
    """Find the first numeric value for any candidate key in nested JSON."""
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
        for value in payload.values():
            found = _recursive_number(value, keys)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _recursive_number(value, keys)
            if found is not None:
                return found
    return None


def _normalize_percent(value):
    if value is None:
        return None
    value = float(value)
    if 0 <= value <= 1:
        value *= 100
    return round(max(0.0, min(100.0, value)), 1)


def _result_status(item):
    raw = (
        item.get("status")
        or item.get("result_status")
        or item.get("test_status")
        or item.get("outcome")
        or item.get("result")
    )
    if isinstance(raw, dict):
        raw = raw.get("value") or raw.get("name") or raw.get("status")
    return str(raw or "").upper()


def _is_failure(item):
    status = _result_status(item)
    return status in {
        "FAIL", "FAILED", "FAILURE", "ERROR",
        "WARNING", "WARN"
    }


def _test_name(item, index):
    for key in (
        "test_name", "test_definition_name", "name",
        "test_suite_name", "description"
    ):
        value = item.get(key)
        if value:
            return str(value)
    return f"TestGen quality check {index}"


def _failed_count(item):
    value = _recursive_number(
        item,
        (
            "failed_count", "failure_count", "failed_rows",
            "failed_row_count", "records_failed",
            "failing_rows", "fail_count",
        ),
    )
    return int(value) if value is not None else None


def _evaluated_count(item):
    value = _recursive_number(
        item,
        (
            "evaluated_count", "record_count", "records_tested",
            "tested_count", "row_count", "total_count",
        ),
    )
    return int(value) if value is not None else None


def assess_resource(db: Session, asset: DataAsset, resource_id: int):
    link = get_link(db, resource_id)
    if not link:
        link = QualityEngineResource(
            organization_id=asset.organization_id,
            resource_id=resource_id,
            provider="TESTGEN",
            project_code=(
                settings.testgen_project_code
                if settings.testgen_mode == "real"
                else None
            ),
            sync_status=(
                "MOCK_READY"
                if settings.testgen_mode != "real"
                else "NEEDS_CONFIGURATION"
            ),
        )
        db.add(link)
        db.flush()

    try:
        if settings.testgen_mode == "real":
            if not link.table_group_id:
                raise HTTPException(
                    status_code=400,
                    detail="Link this resource to a TestGen table group first.",
                )

            client = TestGenClient()
            submission = client.submit_profile(link.table_group_id)
            run_id = submission.get("id")
            if not run_id:
                raise TestGenError(
                    "TestGen profiling submission did not return a job id."
                )

            result = client.wait_for_profile(run_id)

            # Pull real 5.92 profiling detail endpoints after completion.
            columns = client.get_profile_columns(run_id)
            hygiene = client.get_hygiene_issues(run_id)
            try:
                pii = client.get_potential_pii(run_id)
            except TestGenError:
                # PII detail should not make an otherwise successful profile fail.
                pii = {"items": []}

            suggestions = []

            summary = result.get("result") or {}
            score = _normalize_percent(
                _recursive_number(
                    summary,
                    ("dq_score", "quality_score", "score"),
                )
            )

            # TestGen may not include a DQ score in the profiling response.
            # Preserve a prior score if available; otherwise display 0.0 until
            # a real test run supplies quality evidence.
            if score is None:
                previous = db.scalar(
                    select(QualityProfile)
                    .where(
                        QualityProfile.asset_id == asset.id,
                        QualityProfile.resource_id == resource_id,
                    )
                    .order_by(QualityProfile.profiled_at.desc())
                    .limit(1)
                )
                score = previous.overall_score if previous else 0.0

            row_count_value = _recursive_number(
                summary,
                ("record_ct", "row_count", "record_count", "rows"),
            )
            row_count = (
                int(row_count_value)
                if row_count_value is not None
                else None
            )

            profile = QualityProfile(
                asset_id=asset.id,
                resource_id=resource_id,
                overall_score=score,
                row_count=row_count,
                source="TESTGEN",
                external_run_id=run_id,
            )
            db.add(profile)

            hygiene_items = _items(hygiene)
            pii_items = _items(pii)

            if hygiene_items:
                existing = db.scalar(
                    select(QualityIssue).where(
                        QualityIssue.asset_id == asset.id,
                        QualityIssue.resource_id == resource_id,
                        QualityIssue.issue_type == "HYGIENE_FINDING",
                        QualityIssue.external_run_id == run_id,
                    )
                )
                if not existing:
                    issue = QualityIssue(
                        organization_id=asset.organization_id,
                        asset_id=asset.id,
                        resource_id=resource_id,
                        issue_type="HYGIENE_FINDING",
                        title=f"Review {len(hygiene_items)} TestGen profiling findings",
                        description=(
                            "TestGen profiling identified data characteristics "
                            "that may need stewardship review."
                        ),
                        severity="MEDIUM",
                        source="TESTGEN",
                        external_run_id=run_id,
                        details={
                            "hygiene_issues": hygiene_items,
                            "potential_pii_count": len(pii_items),
                            "profile_column_count": len(_items(columns)),
                        },
                    )
                    db.add(issue)
                    db.flush()
                    _open_task_for_issue(db, issue)

            hygiene_count = len(hygiene_items)

        else:
            result = MockTestGenClient().profile(link.external_table_name)
            run_id = result["id"]
            suggestions = result.get("suggested_expectations", [])
            summary = result.get("result") or {}
            score = round(float(summary.get("score") or 0) * 100, 1)

            profile = QualityProfile(
                asset_id=asset.id,
                resource_id=resource_id,
                overall_score=score,
                completeness_score=min(100.0, score + 5.0),
                validity_score=max(0.0, score - 1.5),
                uniqueness_score=min(100.0, score + 7.0),
                consistency_score=max(0.0, score - 3.0),
                timeliness_score=max(0.0, score - 8.0),
                row_count=summary.get("record_ct"),
                source="TESTGEN",
                external_run_id=run_id,
            )
            db.add(profile)

            hygiene_counts = (
                summary.get("issue_counts", {})
                .get("hygiene_issues", {})
            )
            hygiene_count = sum(
                int(hygiene_counts.get(k, 0) or 0)
                for k in ("definite", "likely", "possible")
            )

            if hygiene_count:
                issue = QualityIssue(
                    organization_id=asset.organization_id,
                    asset_id=asset.id,
                    resource_id=resource_id,
                    issue_type="HYGIENE_FINDING",
                    title=f"Review {hygiene_count} profiling findings",
                    description=(
                        "Profiling found data characteristics that may "
                        "require a stewardship decision."
                    ),
                    severity="MEDIUM",
                    source="TESTGEN",
                    external_run_id=run_id,
                    details={
                        "issue_counts": summary.get("issue_counts", {})
                    },
                )
                db.add(issue)
                db.flush()
                _open_task_for_issue(db, issue)

        for spec in suggestions:
            exists = db.scalar(
                select(QualityRule).where(
                    QualityRule.asset_id == asset.id,
                    QualityRule.resource_id == resource_id,
                    QualityRule.rule_name == spec["name"],
                )
            )
            if not exists:
                db.add(
                    QualityRule(
                        asset_id=asset.id,
                        resource_id=resource_id,
                        rule_name=spec["name"],
                        rule_type=spec["rule_type"],
                        plain_language_rule=spec["plain_language_rule"],
                        rule_definition=spec["definition"],
                        status="PROPOSED",
                    )
                )

    except TestGenError as exc:
        link.sync_status = "ERROR"
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc))

    link.last_profiled_at = now()
    link.last_external_run_id = run_id
    link.sync_status = "SYNCED"
    db.commit()

    return {
        "profile_run_id": run_id,
        "overall_score": score,
        "suggested_expectations": len(suggestions),
        "hygiene_findings": hygiene_count,
    }


def run_tests(db: Session, asset: DataAsset, resource_id: int):
    link = get_link(db, resource_id)
    if not link:
        raise HTTPException(
            status_code=400,
            detail=(
                "Assess this resource first so it is linked "
                "to the quality engine."
            ),
        )

    approved_rules = db.scalars(
        select(QualityRule).where(
            QualityRule.asset_id == asset.id,
            QualityRule.resource_id == resource_id,
            QualityRule.status == "APPROVED",
        )
    ).all()

    if settings.testgen_mode != "real" and not approved_rules:
        raise HTTPException(
            status_code=400,
            detail="Approve at least one suggested quality expectation first.",
        )

    try:
        if settings.testgen_mode == "real":
            if not link.test_suite_id:
                raise HTTPException(
                    status_code=400,
                    detail="Add the TestGen test suite ID before running checks.",
                )

            client = TestGenClient()
            submission = client.submit_test_run(link.test_suite_id)
            run_id = submission.get("id")
            if not run_id:
                raise TestGenError(
                    "TestGen test-run submission did not return a job id."
                )

            result = client.wait_for_test_run(run_id)
            result_page = client.get_test_results(run_id)
            test_items = _items(result_page)
            failures = [
                item for item in test_items if _is_failure(item)
            ]

            passed_count = max(0, len(test_items) - len(failures))
            score = (
                round((passed_count / len(test_items)) * 100, 1)
                if test_items
                else 0.0
            )

            # Create one actionable AI Data Steward issue per failed TestGen check.
            for index, item in enumerate(failures, start=1):
                name = _test_name(item, index)
                failed_count = _failed_count(item)
                evaluated_count = _evaluated_count(item)

                description = (
                    f"TestGen reported a failed quality check: {name}."
                )
                if failed_count is not None:
                    description += f" {failed_count} records failed."

                issue = QualityIssue(
                    organization_id=asset.organization_id,
                    asset_id=asset.id,
                    resource_id=resource_id,
                    issue_type="TESTGEN_TEST_FAILURE",
                    title=f"Investigate quality failure: {name}",
                    description=description,
                    severity="HIGH",
                    failed_count=failed_count,
                    source="TESTGEN",
                    external_run_id=run_id,
                    external_issue_id=str(
                        item.get("id")
                        or item.get("test_definition_id")
                        or ""
                    ) or None,
                    details={
                        "testgen_result": item,
                        "evaluated_count": evaluated_count,
                    },
                )
                db.add(issue)
                db.flush()
                _open_task_for_issue(db, issue)

            db.add(
                QualityProfile(
                    asset_id=asset.id,
                    resource_id=resource_id,
                    overall_score=score,
                    source="TESTGEN",
                    external_run_id=run_id,
                )
            )

            failed_total = len(failures)

        else:
            result = MockTestGenClient().run_tests()
            run_id = result["id"]
            failures = result.get("failures", [])
            summary = result.get("result") or {}
            failed_total = int(
                (summary.get("result_counts") or {}).get("failed", 0) or 0
            )

            by_name = {r.rule_name: r for r in approved_rules}
            for failure in failures:
                rule = by_name.get(failure["rule_name"])
                if not rule:
                    continue

                db.add(
                    QualityResult(
                        rule_id=rule.id,
                        result_status="FAIL",
                        evaluated_count=failure["evaluated_count"],
                        failed_count=failure["failed_count"],
                        score=failure["score"],
                        details={
                            "message": failure["description"],
                            "sample_values":
                                failure.get("sample_values", []),
                        },
                        source="TESTGEN",
                        external_run_id=run_id,
                    )
                )

                issue = QualityIssue(
                    organization_id=asset.organization_id,
                    asset_id=asset.id,
                    resource_id=resource_id,
                    rule_id=rule.id,
                    issue_type="RULE_FAILURE",
                    title=(
                        f"Investigate quality failure: {rule.rule_name}"
                    ),
                    description=failure["description"],
                    severity="HIGH",
                    failed_count=failure["failed_count"],
                    source="TESTGEN",
                    external_run_id=run_id,
                    details={
                        "sample_values":
                            failure.get("sample_values", []),
                        "score": failure["score"],
                    },
                )
                db.add(issue)
                db.flush()
                _open_task_for_issue(db, issue)

            score = round(
                float(summary.get("score") or 0) * 100,
                1,
            )
            if score:
                db.add(
                    QualityProfile(
                        asset_id=asset.id,
                        resource_id=resource_id,
                        overall_score=score,
                        source="TESTGEN",
                        external_run_id=run_id,
                    )
                )

    except TestGenError as exc:
        link.sync_status = "ERROR"
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc))

    link.last_tested_at = now()
    link.last_external_run_id = run_id
    link.sync_status = "SYNCED"
    db.commit()

    return {
        "test_run_id": run_id,
        "score": score,
        "failed_checks": failed_total,
    }

def decide_issue(db: Session, issue: QualityIssue, actor_id: int, decision_type: str, notes: str | None):
    allowed = {'BAD_DATA','VALID_EXCEPTION','EXPECTATION_NEEDS_CHANGE','EXPERT_REVIEW'}
    if decision_type not in allowed:
        raise HTTPException(status_code=400, detail=f'Decision must be one of: {", ".join(sorted(allowed))}')
    db.add(QualityDecision(issue_id=issue.id, decision_type=decision_type, notes=notes, decided_by=actor_id))
    if decision_type != 'EXPERT_REVIEW':
        issue.status = 'RESOLVED'; issue.resolved_at = now()
        task = db.scalar(select(StewardshipTask).where(StewardshipTask.source_type == 'QUALITY_ISSUE', StewardshipTask.source_reference == str(issue.id), StewardshipTask.status == 'OPEN'))
        if task:
            task.status = 'COMPLETED'; task.completed_at = now()
    else:
        issue.status = 'NEEDS_EXPERT_REVIEW'
    db.commit()
