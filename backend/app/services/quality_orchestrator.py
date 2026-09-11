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
    link.sync_status = 'CONNECTED' if settings.testgen_mode == 'real' else 'MOCK_READY'
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


def assess_resource(db: Session, asset: DataAsset, resource_id: int):
    link = get_link(db, resource_id)
    if not link:
        link = QualityEngineResource(organization_id=asset.organization_id, resource_id=resource_id, provider='TESTGEN', sync_status='MOCK_READY' if settings.testgen_mode != 'real' else 'NEEDS_CONFIGURATION')
        db.add(link); db.flush()

    try:
        if settings.testgen_mode == 'real':
            if not link.table_group_id:
                raise HTTPException(status_code=400, detail='Link this resource to a TestGen table group first.')
            client = TestGenClient()
            submission = client.submit_profile(link.table_group_id)
            run_id = submission.get('id')
            client.wait_for_job(run_id)
            result = client.get_profile_run(run_id)
            suggestions = []
        else:
            result = MockTestGenClient().profile(link.external_table_name)
            run_id = result['id']
            suggestions = result.get('suggested_expectations', [])
    except TestGenError as exc:
        link.sync_status = 'ERROR'; db.commit()
        raise HTTPException(status_code=502, detail=str(exc))

    summary = result.get('result') or {}
    score = round(float(summary.get('score') or 0) * 100, 1)
    profile = QualityProfile(
        asset_id=asset.id, resource_id=resource_id, overall_score=score,
        completeness_score=min(100.0, score + 5.0), validity_score=max(0.0, score - 1.5),
        uniqueness_score=min(100.0, score + 7.0), consistency_score=max(0.0, score - 3.0),
        timeliness_score=max(0.0, score - 8.0), row_count=summary.get('record_ct'),
        source='TESTGEN', external_run_id=run_id,
    )
    db.add(profile)

    for spec in suggestions:
        exists = db.scalar(select(QualityRule).where(QualityRule.asset_id == asset.id, QualityRule.resource_id == resource_id, QualityRule.rule_name == spec['name']))
        if not exists:
            db.add(QualityRule(
                asset_id=asset.id, resource_id=resource_id, rule_name=spec['name'], rule_type=spec['rule_type'],
                plain_language_rule=spec['plain_language_rule'], rule_definition=spec['definition'], status='PROPOSED',
            ))

    issue_counts = summary.get('issue_counts', {}).get('hygiene_issues', {})
    active_hygiene = sum(int(issue_counts.get(k, 0) or 0) for k in ('definite','likely','possible'))
    if active_hygiene:
        issue = QualityIssue(
            organization_id=asset.organization_id, asset_id=asset.id, resource_id=resource_id,
            issue_type='HYGIENE_FINDING', title=f'Review {active_hygiene} profiling findings',
            description='Profiling found data characteristics that may require a stewardship decision. Review them before treating them as defects.',
            severity='MEDIUM', source='TESTGEN', external_run_id=run_id,
            details={'issue_counts': summary.get('issue_counts', {})},
        )
        db.add(issue); db.flush(); _open_task_for_issue(db, issue)

    link.last_profiled_at = now(); link.last_external_run_id = run_id; link.sync_status = 'SYNCED'
    db.commit()
    return {'profile_run_id': run_id, 'overall_score': score, 'suggested_expectations': len(suggestions), 'hygiene_findings': active_hygiene}


def run_tests(db: Session, asset: DataAsset, resource_id: int):
    link = get_link(db, resource_id)
    if not link:
        raise HTTPException(status_code=400, detail='Assess this resource first so it is linked to the quality engine.')

    approved_rules = db.scalars(select(QualityRule).where(QualityRule.asset_id == asset.id, QualityRule.resource_id == resource_id, QualityRule.status == 'APPROVED')).all()
    if settings.testgen_mode != 'real' and not approved_rules:
        raise HTTPException(status_code=400, detail='Approve at least one suggested quality expectation first.')

    try:
        if settings.testgen_mode == 'real':
            if not link.test_suite_id:
                raise HTTPException(status_code=400, detail='Add the TestGen test suite ID before running checks.')
            client = TestGenClient()
            submission = client.submit_test_run(link.test_suite_id)
            run_id = submission.get('id')
            client.wait_for_job(run_id)
            result = client.get_test_run(run_id)
            failures = []
        else:
            result = MockTestGenClient().run_tests(); run_id = result['id']; failures = result.get('failures', [])
    except TestGenError as exc:
        link.sync_status = 'ERROR'; db.commit(); raise HTTPException(status_code=502, detail=str(exc))

    summary = result.get('result') or {}
    failed_total = int((summary.get('result_counts') or {}).get('failed', 0) or 0)

    if settings.testgen_mode == 'real' and failed_total:
        issue = QualityIssue(
            organization_id=asset.organization_id, asset_id=asset.id, resource_id=resource_id,
            issue_type='TEST_RUN_FAILURE', title=f'Investigate {failed_total} failed TestGen checks',
            description='The latest TestGen run contains failed quality checks. Review the detailed run in TestGen or sync detailed results when configured.',
            severity='HIGH', failed_count=failed_total, source='TESTGEN', external_run_id=run_id,
            details={'result_counts': summary.get('result_counts', {}), 'score': summary.get('score')},
        )
        db.add(issue); db.flush(); _open_task_for_issue(db, issue)
    else:
        by_name = {r.rule_name: r for r in approved_rules}
        for failure in failures:
            rule = by_name.get(failure['rule_name'])
            if not rule:
                continue
            db.add(QualityResult(
                rule_id=rule.id, result_status='FAIL', evaluated_count=failure['evaluated_count'], failed_count=failure['failed_count'],
                score=failure['score'], details={'message': failure['description'], 'sample_values': failure.get('sample_values', [])},
                source='TESTGEN', external_run_id=run_id,
            ))
            issue = QualityIssue(
                organization_id=asset.organization_id, asset_id=asset.id, resource_id=resource_id, rule_id=rule.id,
                issue_type='RULE_FAILURE', title=f'Investigate quality failure: {rule.rule_name}', description=failure['description'],
                severity='HIGH', failed_count=failure['failed_count'], source='TESTGEN', external_run_id=run_id,
                details={'sample_values': failure.get('sample_values', []), 'score': failure['score']},
            )
            db.add(issue); db.flush(); _open_task_for_issue(db, issue)

    score = round(float(summary.get('score') or 0) * 100, 1)
    if score:
        db.add(QualityProfile(asset_id=asset.id, resource_id=resource_id, overall_score=score, source='TESTGEN', external_run_id=run_id))
    link.last_tested_at = now(); link.last_external_run_id = run_id; link.sync_status = 'SYNCED'
    db.commit()
    return {'test_run_id': run_id, 'score': score, 'failed_checks': failed_total or len(failures)}


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
