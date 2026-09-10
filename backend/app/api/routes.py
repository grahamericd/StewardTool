from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_context, require_roles
from ..db import get_db
from ..models import (
    AssetMetadata, AssetPublication, AssetRelease, AssetResource, CatalogSystem, DataAsset, DataResource,
    PublicationEvent, QualityProfile, QualityResult, QualityRule, StewardshipTask,
)
from ..schemas import (
    AssetCreate, AssetGovernanceUpdate, MetadataUpsert, QualityProfileCreate, QualityResultCreate,
    QualityRuleCreate, RejectRequest, ResourceCreate, ReviewRequest, SubmitRequest, SystemCreate, TaskComplete,
)
from ..services.publication import approve, mark_needs_update_if_published, publish, reject, submit_for_review
from ..services.readiness import calculate_readiness
from ..services.snapshot import build_asset_snapshot
from ..services.task_service import sync_tasks

router = APIRouter()


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
    assets = db.scalars(asset_query().where(DataAsset.organization_id == ctx["organization_id"])).all()
    for asset in assets: sync_tasks(db, asset)
    db.commit()
    tasks = db.scalars(select(StewardshipTask).where(StewardshipTask.organization_id == ctx["organization_id"], StewardshipTask.status == "OPEN").order_by(StewardshipTask.priority, StewardshipTask.created_at)).all()
    names = {a.id: a.name for a in assets}
    return [{"id": t.id, "asset_id": t.asset_id, "asset_name": names.get(t.asset_id), "task_type": t.task_type, "governance_domain": t.governance_domain, "title": t.title, "why_it_matters": t.why_it_matters, "recommended_action": t.recommended_action, "priority": t.priority, "status": t.status, "source_type": t.source_type} for t in tasks]


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
    profiles = db.scalars(select(QualityProfile).where(QualityProfile.asset_id == asset.id).order_by(QualityProfile.profiled_at.desc())).all()
    rules = db.scalars(select(QualityRule).where(QualityRule.asset_id == asset.id).order_by(QualityRule.created_at.desc())).all()
    result = []
    for rule in rules:
        latest = db.scalar(select(QualityResult).where(QualityResult.rule_id == rule.id).order_by(QualityResult.evaluated_at.desc()).limit(1))
        result.append({"id": rule.id, "rule_name": rule.rule_name, "rule_type": rule.rule_type, "plain_language_rule": rule.plain_language_rule, "status": rule.status, "rule_definition": rule.rule_definition, "latest_result": None if not latest else {"result_status": latest.result_status, "evaluated_count": latest.evaluated_count, "failed_count": latest.failed_count, "score": latest.score, "details": latest.details, "evaluated_at": latest.evaluated_at}})
    return {"profiles": [{"overall_score": p.overall_score, "completeness_score": p.completeness_score, "validity_score": p.validity_score, "uniqueness_score": p.uniqueness_score, "consistency_score": p.consistency_score, "timeliness_score": p.timeliness_score, "row_count": p.row_count, "profiled_at": p.profiled_at, "source": p.source} for p in profiles], "rules": result}


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
