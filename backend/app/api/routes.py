from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_context, require_roles
from ..config import settings
from ..db import get_db
from ..models import (
    AssetMetadata, AssetPublication, AssetRelease, AssetResource, CatalogSystem, DataAsset, DataResource,
    PublicationEvent, QualityDecision, QualityEngineResource, QualityIssue, QualityProfile, QualityResult, QualityRule, StewardshipTask,
)
from ..schemas import (
    AssetCreate, AssetGovernanceUpdate, MetadataUpsert, QualityProfileCreate, QualityResultCreate,
    QualityRuleCreate, RejectRequest, ResourceCreate, ReviewRequest, SubmitRequest, SystemCreate, TaskComplete,
    QualityEngineLinkCreate, QualityAssessmentRequest, QualityRunRequest, QualityRuleStatusUpdate, QualityDecisionCreate,
    HygieneFindingDecisionCreate,
)
from ..services.publication import approve, mark_needs_update_if_published, publish, reject, submit_for_review
from ..services.readiness import calculate_readiness
from ..services.snapshot import build_asset_snapshot
from ..services.task_service import sync_tasks
from ..services.quality_orchestrator import assess_resource, decide_issue, decide_hygiene_finding, enrich_hygiene_issue, ensure_link, run_tests, _source_mapping_from_link
from ..integrations.testgen.client import TestGenClient, TestGenError

router = APIRouter()


def _task_guidance(task):
    domain = (task.governance_domain or "").upper()
    source_type = (task.source_type or "").upper()

    if source_type == "QUALITY_ISSUE":
        return {
            "responsibility": "Trust the information",
            "learn_title": "What does a data steward do here?",
            "learn_text": (
                "Review the evidence, confirm what the business expects, and record "
                "whether the finding needs correction, is acceptable, needs a quality "
                "expectation, or needs expert review."
            ),
            "can_escalate": True,
        }

    if domain == "OWNERSHIP":
        return {
            "responsibility": "Know who is accountable",
            "learn_title": "Why ownership matters",
            "learn_text": (
                "Your job is to make sure the correct business owner and steward are "
                "identified. You are not expected to personally make every business "
                "decision about the information."
            ),
            "can_escalate": True,
        }

    if domain == "CLASSIFICATION":
        return {
            "responsibility": "Protect the information appropriately",
            "learn_title": "What classification means",
            "learn_text": (
                "Classification describes how sensitive the information is and helps "
                "drive handling, access, sharing, and protection decisions."
            ),
            "can_escalate": True,
        }

    if domain in {"LIFECYCLE", "RETENTION"}:
        return {
            "responsibility": "Keep information for the right amount of time",
            "learn_title": "What retention means",
            "learn_text": (
                "Retention determines how long information must be maintained and what "
                "authority governs that period. If you are unsure, involve records "
                "management rather than guessing."
            ),
            "can_escalate": True,
        }

    if domain in {"METADATA", "DESCRIPTION"}:
        return {
            "responsibility": "Make the information understandable",
            "learn_title": "Why description matters",
            "learn_text": (
                "Good stewardship means someone unfamiliar with the system can still "
                "understand what the information represents, where it comes from, and "
                "how it is used."
            ),
            "can_escalate": False,
        }

    return {
        "responsibility": "Take care of governed information",
        "learn_title": "Your stewardship responsibility",
        "learn_text": (
            "Review what is missing, confirm the business reality, and record the "
            "decision so the organization has a trusted, auditable understanding of "
            "its information."
        ),
        "can_escalate": True,
    }


def _task_bucket(task):
    status = (task.status or "").upper()
    if status in {"WAITING", "BLOCKED", "NEEDS_EXPERT_REVIEW"}:
        return "WAITING"
    return "NOW"



def asset_query():
    return select(DataAsset).options(
        selectinload(DataAsset.resources).selectinload(AssetResource.resource).selectinload(DataResource.system),
        selectinload(DataAsset.metadata_items),
        selectinload(DataAsset.publication),
        selectinload(DataAsset.quality_profiles),
        selectinload(DataAsset.quality_rules),
        selectinload(DataAsset.tasks),
    )


def get_asset_for_org(db, asset_id, org_id):
    asset = db.scalar(asset_query().where(DataAsset.id == asset_id, DataAsset.organization_id == org_id))
    if not asset:
        raise HTTPException(status_code=404, detail="Data asset not found")
    return asset


def serialize_asset(asset, db=None):
    if db:
        sync_tasks(db, asset)
        db.flush()
    snapshot = build_asset_snapshot(asset)
    readiness = calculate_readiness(asset)
    pub = asset.publication
    return {
        **snapshot,
        "readiness": readiness,
        "publication": {
            "status": pub.status if pub else "DRAFT",
            "submitted_at": pub.submitted_at if pub else None,
            "approved_at": pub.approved_at if pub else None,
            "published_at": pub.published_at if pub else None,
        },
        "task_summary": {
            "open": sum(1 for t in asset.tasks if t.status == "OPEN"),
            "high": sum(1 for t in asset.tasks if t.status == "OPEN" and t.priority == "HIGH"),
        },
    }


@router.get("/me")
def me(ctx=Depends(current_context)):
    org = ctx["membership"].organization
    return {"user": {"id": ctx["user"].id, "email": ctx["user"].email, "display_name": ctx["user"].display_name}, "organization": {"id": org.id, "code": org.code, "name": org.name}, "role": ctx["role"]}


@router.get("/dashboard")
def dashboard(ctx=Depends(current_context), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    systems = db.scalars(select(CatalogSystem).where(CatalogSystem.organization_id == org_id)).all()
    assets = db.scalars(asset_query().where(DataAsset.organization_id == org_id)).all()
    for asset in assets:
        sync_tasks(db, asset)
    db.commit()
    tasks = db.scalars(select(StewardshipTask).where(StewardshipTask.organization_id == org_id, StewardshipTask.status == "OPEN")).all()
    statuses = {}
    links = [link for asset in assets for link in asset.resources]
    for asset in assets:
        status = asset.publication.status if asset.publication else "DRAFT"
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "systems": len(systems), "assets": len(assets), "resources": len(links),
        "unstructured_resources": sum(1 for link in links if link.resource.structure_type == "UNSTRUCTURED"),
        "open_tasks": len(tasks), "high_priority_tasks": sum(1 for t in tasks if t.priority == "HIGH"),
        "publication_status": statuses,
        "average_governance_readiness": round(sum(calculate_readiness(a)["score"] for a in assets) / len(assets)) if assets else 0,
        "average_quality_score": round(sum(a.quality_profiles[0].overall_score for a in assets if a.quality_profiles) / max(1, sum(1 for a in assets if a.quality_profiles)), 1),
    }


@router.get("/systems")
def list_systems(ctx=Depends(current_context), db: Session = Depends(get_db)):
    return db.scalars(select(CatalogSystem).where(CatalogSystem.organization_id == ctx["organization_id"]).order_by(CatalogSystem.name)).all()


@router.post("/systems")
def create_system(payload: SystemCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    system = CatalogSystem(organization_id=ctx["organization_id"], name=payload.name, business_purpose=payload.business_purpose, description=payload.description, vendor=payload.vendor, system_owner=payload.system_owner, created_by=ctx["user"].id)
    db.add(system); db.commit(); db.refresh(system); return system


@router.get("/assets")
def list_assets(ctx=Depends(current_context), db: Session = Depends(get_db)):
    assets = db.scalars(asset_query().where(DataAsset.organization_id == ctx["organization_id"]).order_by(DataAsset.name)).all()
    result = [serialize_asset(a, db) for a in assets]
    db.commit(); return result


@router.post("/assets")
def create_asset(payload: AssetCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = DataAsset(organization_id=ctx["organization_id"], name=payload.name, business_definition=payload.business_definition, business_domain=payload.business_domain, business_owner=payload.business_owner, data_steward=payload.data_steward, created_by=ctx["user"].id)
    db.add(asset); db.flush(); db.add(AssetPublication(asset_id=asset.id, status="DRAFT")); db.commit()
    asset = get_asset_for_org(db, asset.id, ctx["organization_id"]); sync_tasks(db, asset); db.commit(); return serialize_asset(asset)


@router.get("/assets/{asset_id}")
def get_asset(asset_id: int, ctx=Depends(current_context), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"]); sync_tasks(db, asset); db.commit(); return serialize_asset(asset)


@router.patch("/assets/{asset_id}/governance")
def update_governance(asset_id: int, payload: AssetGovernanceUpdate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(asset, key, value)
    mark_needs_update_if_published(db, asset, ctx["user"].id, "Governance metadata changed")
    sync_tasks(db, asset, ctx["user"].id); db.commit()
    return serialize_asset(get_asset_for_org(db, asset_id, ctx["organization_id"]))


@router.post("/assets/{asset_id}/resources")
def add_resource(asset_id: int, payload: ResourceCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    if payload.system_id:
        system = db.get(CatalogSystem, payload.system_id)
        if not system or system.organization_id != ctx["organization_id"]:
            raise HTTPException(status_code=400, detail="System does not belong to current organization")
    resource = DataResource(organization_id=ctx["organization_id"], system_id=payload.system_id, name=payload.name, resource_type=payload.resource_type, structure_type=payload.structure_type, description=payload.description, location_reference=payload.location_reference, format=payload.format, media_type=payload.media_type, created_by=ctx["user"].id)
    db.add(resource); db.flush(); db.add(AssetResource(asset_id=asset.id, resource_id=resource.id, relationship_type=payload.relationship_type, is_authoritative=payload.is_authoritative))
    mark_needs_update_if_published(db, asset, ctx["user"].id, "Resource added or changed"); db.commit()
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"]); sync_tasks(db, asset); db.commit(); return serialize_asset(asset)


@router.put("/assets/{asset_id}/metadata")
def upsert_metadata(asset_id: int, payload: MetadataUpsert, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    for item in db.scalars(select(AssetMetadata).where(AssetMetadata.asset_id == asset.id, AssetMetadata.metadata_key == payload.metadata_key)).all():
        db.delete(item)
    values = payload.metadata_value if payload.metadata_key == "keyword" and isinstance(payload.metadata_value, list) else [payload.metadata_value]
    for value in values:
        db.add(AssetMetadata(asset_id=asset.id, metadata_key=payload.metadata_key, metadata_value=value, metadata_source=payload.metadata_source, review_status=payload.review_status, created_by=ctx["user"].id, reviewed_by=ctx["user"].id if payload.review_status == "APPROVED" else None, reviewed_at=datetime.now(timezone.utc) if payload.review_status == "APPROVED" else None))
    mark_needs_update_if_published(db, asset, ctx["user"].id, f"Metadata changed: {payload.metadata_key}"); db.commit()
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"]); sync_tasks(db, asset); db.commit(); return serialize_asset(asset)


@router.get("/tasks")
def list_tasks(ctx=Depends(current_context), db: Session = Depends(get_db)):
    assets = db.scalars(
        asset_query().where(
            DataAsset.organization_id == ctx["organization_id"]
        )
    ).all()
    for asset in assets:
        sync_tasks(db, asset)
    db.commit()

    tasks = db.scalars(
        select(StewardshipTask)
        .where(
            StewardshipTask.organization_id == ctx["organization_id"],
            StewardshipTask.status != "COMPLETED",
        )
        .order_by(
            StewardshipTask.priority,
            StewardshipTask.created_at,
        )
    ).all()

    names = {a.id: a.name for a in assets}
    response = []
    for task in tasks:
        guidance = _task_guidance(task)
        response.append({
            "id": task.id,
            "asset_id": task.asset_id,
            "asset_name": names.get(task.asset_id),
            "task_type": task.task_type,
            "governance_domain": task.governance_domain,
            "title": task.title,
            "why_it_matters": task.why_it_matters,
            "recommended_action": task.recommended_action,
            "priority": task.priority,
            "status": task.status,
            "source_type": task.source_type,
            "source_reference": task.source_reference,
            "bucket": _task_bucket(task),
            **guidance,
        })
    return response


@router.post("/tasks/{task_id}/complete")
def complete_task(task_id: int, payload: TaskComplete, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    task = db.get(StewardshipTask, task_id)
    if not task or task.organization_id != ctx["organization_id"]: raise HTTPException(status_code=404, detail="Task not found")
    task.status = "COMPLETED"; task.completed_at = datetime.now(timezone.utc); db.commit(); return {"success": True}


@router.post("/assets/{asset_id}/quality/profiles")
def add_quality_profile(asset_id: int, payload: QualityProfileCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    if payload.resource_id:
        linked = any(link.resource_id == payload.resource_id for link in asset.resources)
        if not linked: raise HTTPException(status_code=400, detail="Resource is not linked to this asset")
    profile = QualityProfile(asset_id=asset.id, **payload.model_dump())
    db.add(profile); db.flush(); sync_tasks(db, asset); db.commit(); db.refresh(profile); return profile


@router.get("/assets/{asset_id}/quality")
def quality(asset_id: int, ctx=Depends(current_context), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])

    if settings.testgen_mode == "real":
        for asset_resource in asset.resources:
            if asset_resource.resource.structure_type == "STRUCTURED":
                ensure_link(
                    db,
                    organization_id=ctx["organization_id"],
                    resource_id=asset_resource.resource_id,
                    payload=None,
                )
        db.commit()

    profiles = db.scalars(select(QualityProfile).where(QualityProfile.asset_id == asset.id).order_by(QualityProfile.profiled_at.desc())).all()
    rules = db.scalars(select(QualityRule).where(QualityRule.asset_id == asset.id).order_by(QualityRule.created_at.desc())).all()
    result = []
    for rule in rules:
        latest = db.scalar(select(QualityResult).where(QualityResult.rule_id == rule.id).order_by(QualityResult.evaluated_at.desc()).limit(1))
        result.append({"id": rule.id, "rule_name": rule.rule_name, "rule_type": rule.rule_type, "plain_language_rule": rule.plain_language_rule, "status": rule.status, "rule_definition": rule.rule_definition, "latest_result": None if not latest else {"result_status": latest.result_status, "evaluated_count": latest.evaluated_count, "failed_count": latest.failed_count, "score": latest.score, "details": latest.details, "evaluated_at": latest.evaluated_at}})
    links = db.scalars(select(QualityEngineResource).where(QualityEngineResource.organization_id == ctx["organization_id"], QualityEngineResource.resource_id.in_([x.resource_id for x in asset.resources] or [-1]))).all()
    issues = db.scalars(select(QualityIssue).where(QualityIssue.asset_id == asset.id).order_by(QualityIssue.created_at.desc())).all()
    changed = False
    for issue in issues:
        if issue.issue_type == "HYGIENE_FINDING":
            before = dict(issue.details or {})
            enrich_hygiene_issue(issue)
            if issue.details != before:
                changed = True
    if changed:
        db.commit()
    return {"engine_mode": settings.testgen_mode, "profiles": [{"overall_score": p.overall_score, "completeness_score": p.completeness_score, "validity_score": p.validity_score, "uniqueness_score": p.uniqueness_score, "consistency_score": p.consistency_score, "timeliness_score": p.timeliness_score, "row_count": p.row_count, "profiled_at": p.profiled_at, "source": p.source, "external_run_id": p.external_run_id} for p in profiles], "rules": result, "links": [{"id": x.id, "resource_id": x.resource_id, "provider": x.provider, "project_code": x.project_code, "connection_id": x.connection_id, "table_group_id": x.table_group_id, "test_suite_id": x.test_suite_id, "external_table_name": x.external_table_name, "source_mapping": _source_mapping_from_link(x), "sync_status": x.sync_status, "last_profiled_at": x.last_profiled_at, "last_tested_at": x.last_tested_at} for x in links], "issues": [{"id": i.id, "resource_id": i.resource_id, "rule_id": i.rule_id, "issue_type": i.issue_type, "title": i.title, "description": i.description, "severity": i.severity, "status": i.status, "failed_count": i.failed_count, "source": i.source, "external_run_id": i.external_run_id, "details": i.details, "created_at": i.created_at} for i in issues]}


@router.post("/assets/{asset_id}/quality/rules")
def add_quality_rule(asset_id: int, payload: QualityRuleCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    rule = QualityRule(asset_id=asset.id, created_by=ctx["user"].id, **payload.model_dump()); db.add(rule); db.commit(); db.refresh(rule); return rule


@router.post("/quality/rules/{rule_id}/results")
def add_quality_result(rule_id: int, payload: QualityResultCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    rule = db.get(QualityRule, rule_id)
    if not rule: raise HTTPException(status_code=404, detail="Rule not found")
    asset = get_asset_for_org(db, rule.asset_id, ctx["organization_id"])
    result = QualityResult(rule_id=rule.id, **payload.model_dump()); db.add(result)
    if payload.result_status == "FAIL" and (payload.failed_count or 0) > 0:
        existing = db.scalar(select(StewardshipTask).where(StewardshipTask.asset_id == asset.id, StewardshipTask.source_type == "QUALITY_RULE", StewardshipTask.source_reference == str(rule.id), StewardshipTask.status == "OPEN"))
        if not existing:
            db.add(StewardshipTask(organization_id=asset.organization_id, asset_id=asset.id, task_type="quality_failure", governance_domain="QUALITY", title=f"Investigate quality failure: {rule.rule_name}", why_it_matters=f"{payload.failed_count} records failed an approved quality expectation.", recommended_action="Review a sample of failures and determine whether the data, the rule, or the source process changed.", priority="HIGH", source_type="QUALITY_RULE", source_reference=str(rule.id)))
    db.commit(); db.refresh(result); return result


@router.get("/quality/engine/status")
def quality_engine_status(ctx=Depends(current_context)):
    real = settings.testgen_mode == "real"
    auth_configured = (
        bool(settings.testgen_token)
        if settings.testgen_auth_mode == "bearer"
        else all([
            settings.testgen_oauth_client_id,
            settings.testgen_oauth_client_secret,
            settings.testgen_oauth_refresh_token,
        ])
    )
    return {
        "provider": "TESTGEN",
        "mode": settings.testgen_mode,
        "auth_mode": settings.testgen_auth_mode if real else None,
        "configured": (not real) or bool(settings.testgen_base_url and auth_configured),
        "base_url": settings.testgen_base_url if real else None,
        "project_code": settings.testgen_project_code if real else None,
        "table_group_id": settings.testgen_table_group_id if real else None,
        "test_suite_id": settings.testgen_test_suite_id if real else None,
        "message": "Real TestGen REST integration is enabled." if real else "Mock TestGen is ready.",
    }


@router.post("/assets/{asset_id}/quality/test-connection")
def test_quality_engine_connection(
    asset_id: int,
    payload: QualityAssessmentRequest,
    ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")),
    db: Session = Depends(get_db),
):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    if not any(link.resource_id == payload.resource_id for link in asset.resources):
        raise HTTPException(status_code=400, detail="Resource is not linked to this asset")
    link = db.scalar(select(QualityEngineResource).where(
        QualityEngineResource.resource_id == payload.resource_id,
        QualityEngineResource.provider == "TESTGEN",
    ))
    project_code = (link.project_code if link else None) or settings.testgen_project_code
    if settings.testgen_mode != "real":
        return {"ok": True, "mode": "mock", "message": "Mock TestGen connection is available."}
    try:
        result = TestGenClient().check_connection(project_code)
        if link:
            link.sync_status = "CONNECTED"
            db.commit()
        return {**result, "mode": "real", "base_url": settings.testgen_base_url,
                "message": "Authenticated connection to TestGen succeeded."}
    except TestGenError as exc:
        if link:
            link.sync_status = "ERROR"
            db.commit()
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/assets/{asset_id}/quality/link")
def link_quality_engine(asset_id: int, payload: QualityEngineLinkCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    if not any(link.resource_id == payload.resource_id for link in asset.resources):
        raise HTTPException(status_code=400, detail="Resource is not linked to this asset")
    link = ensure_link(db, organization_id=ctx["organization_id"], resource_id=payload.resource_id, payload=payload)
    db.commit(); db.refresh(link)
    return {
        "id": link.id,
        "resource_id": link.resource_id,
        "provider": link.provider,
        "sync_status": link.sync_status,
        "project_code": link.project_code,
        "connection_id": link.connection_id,
        "table_group_id": link.table_group_id,
        "test_suite_id": link.test_suite_id,
        "external_table_name": link.external_table_name,
        "source_mapping": _source_mapping_from_link(link),
    }


@router.post("/assets/{asset_id}/quality/assess")
def assess_quality(asset_id: int, payload: QualityAssessmentRequest, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    if not any(link.resource_id == payload.resource_id for link in asset.resources):
        raise HTTPException(status_code=400, detail="Resource is not linked to this asset")
    return assess_resource(db, asset, payload.resource_id)


@router.patch("/quality/rules/{rule_id}/status")
def set_quality_rule_status(rule_id: int, payload: QualityRuleStatusUpdate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    rule = db.get(QualityRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    get_asset_for_org(db, rule.asset_id, ctx["organization_id"])
    if payload.status not in {"PROPOSED", "APPROVED", "REJECTED"}:
        raise HTTPException(status_code=400, detail="Invalid rule status")
    rule.status = payload.status; db.commit(); return {"success": True, "status": rule.status}


@router.post("/assets/{asset_id}/quality/run")
def run_quality_checks(asset_id: int, payload: QualityRunRequest, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    if not any(link.resource_id == payload.resource_id for link in asset.resources):
        raise HTTPException(status_code=400, detail="Resource is not linked to this asset")
    return run_tests(db, asset, payload.resource_id)


@router.post("/quality/issues/{issue_id}/decision")
def quality_issue_decision(issue_id: int, payload: QualityDecisionCreate, HygieneFindingDecisionCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    issue = db.get(QualityIssue, issue_id)
    if not issue or issue.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Quality issue not found")
    decide_issue(db, issue, ctx["user"].id, payload.decision_type, payload.notes)
    return {"success": True, "issue_id": issue.id, "status": issue.status, "decision": payload.decision_type}




@router.post("/quality/issues/{issue_id}/findings/{finding_fingerprint}/decision")
def hygiene_finding_decision(
    issue_id: int,
    finding_fingerprint: str,
    payload: HygieneFindingDecisionCreate,
    ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")),
    db: Session = Depends(get_db),
):
    issue = db.get(QualityIssue, issue_id)
    if not issue or issue.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Quality issue not found")
    if issue.issue_type != "HYGIENE_FINDING":
        raise HTTPException(
            status_code=400,
            detail="This endpoint is only for TestGen profiling findings.",
        )
    try:
        decide_hygiene_finding(
            db,
            issue,
            ctx["user"].id,
            finding_fingerprint,
            payload.decision_type,
            payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "success": True,
        "issue_id": issue.id,
        "status": issue.status,
        "details": issue.details,
    }


@router.post("/assets/{asset_id}/submit")
def submit(asset_id: int, payload: SubmitRequest, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"]); submit_for_review(db, asset, ctx["user"].id, payload.comments); return serialize_asset(get_asset_for_org(db, asset_id, ctx["organization_id"]))


@router.post("/assets/{asset_id}/approve")
def approve_asset(asset_id: int, payload: ReviewRequest, ctx=Depends(require_roles("APPROVER", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"]); approve(db, asset, ctx["user"].id, payload.comments); return serialize_asset(get_asset_for_org(db, asset_id, ctx["organization_id"]))


@router.post("/assets/{asset_id}/reject")
def reject_asset(asset_id: int, payload: RejectRequest, ctx=Depends(require_roles("APPROVER", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"]); reject(db, asset, ctx["user"].id, payload.comments); return serialize_asset(get_asset_for_org(db, asset_id, ctx["organization_id"]))


@router.post("/assets/{asset_id}/publish")
def publish_asset(asset_id: int, ctx=Depends(require_roles("APPROVER", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"]); publish(db, asset, ctx["user"].id); return serialize_asset(get_asset_for_org(db, asset_id, ctx["organization_id"]))


@router.get("/assets/{asset_id}/history")
def history(asset_id: int, ctx=Depends(current_context), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    events = db.scalars(select(PublicationEvent).where(PublicationEvent.asset_id == asset.id).order_by(PublicationEvent.created_at.desc())).all()
    releases = db.scalars(select(AssetRelease).where(AssetRelease.asset_id == asset.id).order_by(AssetRelease.version_number.desc())).all()
    return {
        "events": [{"id": e.id, "event_type": e.event_type, "from_status": e.from_status, "to_status": e.to_status, "comments": e.comments, "event_metadata": e.event_metadata, "created_at": e.created_at} for e in events],
        "releases": [{"id": r.id, "version_number": r.version_number, "snapshot_hash": r.snapshot_hash, "approved_at": r.approved_at, "published_at": r.published_at, "ckan_dataset_id": r.ckan_dataset_id, "ckan_name": r.ckan_name, "publication_result": r.publication_result, "snapshot": r.snapshot} for r in releases],
    }
