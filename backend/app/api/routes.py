from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..auth import current_context, require_roles
from ..config import settings
from ..db import get_db
from ..models import (
    AssetMetadata, AssetPublication, AssetRelease, AssetResource, BusinessConcept, BusinessFlow, BusinessFunction, BusinessFunctionUnit, BusinessUnit, CatalogSystem, DataAsset, DataResource, LandscapeRelationship, LandscapeWorkspaceDraft, SystemInventoryDetail,
    DiscoveryCandidate, DiscoveryCandidateStatus, DiscoveryProvenance, DiscoverySession, LandscapeAssertion, LandscapeEvidence, LandscapeSystem,
    PublicationEvent, QualityDecision, QualityEngineResource, QualityIssue, QualityProfile, QualityResult, QualityRule, StewardshipReview, StewardshipTask,
)
from ..schemas import (
    AssetCreate, AssetGovernanceUpdate, MetadataUpsert, QualityProfileCreate, QualityResultCreate, SystemInventoryCreate, SystemInventoryUpdate, LandscapeRelationshipCreate, LandscapeDraftCheckpoint, LandscapeDraftUpdate,
    QualityRuleCreate, RejectRequest, ResourceCreate, OfficialSourceDecision, ReviewRequest, SubmitRequest, SystemCreate, TaskComplete,
    QualityEngineLinkCreate, QualityAssessmentRequest, QualityRunRequest, QualityRuleStatusUpdate, QualityDecisionCreate,
    HygieneFindingDecisionCreate, PeriodicReviewCreate, UnderstandingUpdate,
    BusinessConceptCreate, BusinessConceptUpdate, BusinessFlowCreate, BusinessFlowUpdate, BusinessFunctionCreate, BusinessFunctionUpdate, BusinessFunctionUnitMappingCreate, BusinessFunctionUnitMappingUpdate, BusinessUnitCreate, BusinessUnitUpdate,
    DiscoveryCandidateCreate, DiscoveryCandidateUpdate, DiscoverySessionCreate, DiscoverySessionUpdate,
    LandscapeAssertionCreate, LandscapeAssertionUpdate, LandscapeEvidenceCreate, LandscapeEvidenceUpdate, LandscapeSystemCreate, LandscapeSystemUpdate,
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

    if domain == "MAINTENANCE" or source_type == "PERIODIC_REVIEW":
        return {
            "responsibility": "Keep stewardship current",
            "learn_title": "Why periodic review matters",
            "learn_text": (
                "You do not need to redo the whole stewardship process. Confirm what "
                "has changed since the last review, and AI Data Steward will reopen "
                "only the areas that need attention."
            ),
            "can_escalate": False,
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
    if domain == "PUBLICATION":
        return {
            "responsibility": "Prepare information for review",
            "learn_title": "Why approval matters",
            "learn_text": (
                "Submit the information when its required stewardship steps are complete. "
                "An authorized reviewer makes the approval decision in the review queue."
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


def _serialize_discovery_candidate(candidate):
    return {
        "id": candidate.id,
        "organization_id": candidate.organization_id,
        "name": candidate.name,
        "kind": candidate.kind,
        "summary": candidate.summary,
        "description": candidate.description,
        "status": candidate.status,
        "source": candidate.source,
        "suggested_by_ai": candidate.suggested_by_ai,
        "details": candidate.details,
        "parent_candidate_id": candidate.parent_candidate_id,
        "asset_id": candidate.asset_id,
        "system_id": candidate.system_id,
        "resource_id": candidate.resource_id,
        "created_by": candidate.created_by,
        "confirmed_by": candidate.confirmed_by,
        "rejected_by": candidate.rejected_by,
        "confirmed_at": candidate.confirmed_at.isoformat() if candidate.confirmed_at else None,
        "rejected_at": candidate.rejected_at.isoformat() if candidate.rejected_at else None,
        "created_at": candidate.created_at.isoformat(),
        "updated_at": candidate.updated_at.isoformat(),
    }


def _serialize_discovery_session(session):
    return {
        "id": session.id,
        "organization_id": session.organization_id,
        "created_by": session.created_by,
        "title": session.title,
        "status": session.status,
        "summary": session.summary,
        "context_snapshot": session.context_snapshot,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


def _serialize_landscape_evidence(item):
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "session_id": item.session_id,
        "entity_type": item.entity_type,
        "entity_id": item.entity_id,
        "evidence_type": item.evidence_type,
        "summary": item.summary,
        "details": item.details,
        "source": item.source,
        "created_by": item.created_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _serialize_landscape_assertion(item):
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "session_id": item.session_id,
        "entity_type": item.entity_type,
        "entity_id": item.entity_id,
        "assertion_type": item.assertion_type,
        "statement": item.statement,
        "confidence": item.confidence,
        "status": item.status,
        "created_by": item.created_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _serialize_provenance(entry):
    return {
        "id": entry.id,
        "organization_id": entry.organization_id,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "action": entry.action,
        "performed_by": entry.performed_by,
        "details": entry.details,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


# Ordering by the priority string alone sorted alphabetically, which put LOW
# above MEDIUM in a list the UI presents as "start at the top".
TASK_PRIORITY_ORDER = case(
    (StewardshipTask.priority == "HIGH", 0),
    (StewardshipTask.priority == "MEDIUM", 1),
    else_=2,
)


def latest_quality_profile(asset):
    """The most recent profile, rather than whatever the relationship yields first."""
    profiles = [p for p in asset.quality_profiles if p.profiled_at]
    if not profiles:
        return asset.quality_profiles[0] if asset.quality_profiles else None
    return max(profiles, key=lambda p: p.profiled_at)



# The raw engine payloads hold sample values, column statistics and TestGen's
# potential-PII list. The UI works from the derived findings, so the raw blobs
# stay in the database for enrichment and are not served to every reader.
RAW_ENGINE_DETAIL_KEYS = ("hygiene_issues", "profile_columns", "potential_pii")


def public_issue_details(details):
    if not isinstance(details, dict):
        return details
    return {k: v for k, v in details.items() if k not in RAW_ENGINE_DETAIL_KEYS}


def asset_query():
    return select(DataAsset).options(
        selectinload(DataAsset.resources).selectinload(AssetResource.resource).selectinload(DataResource.system),
        selectinload(DataAsset.metadata_items),
        selectinload(DataAsset.publication),
        selectinload(DataAsset.reviews),
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
    return {"user": {"id": ctx["user"].id, "email": ctx["user"].email, "display_name": ctx["user"].display_name}, "organization": {"id": org.id, "code": org.code, "name": org.name}, "role": ctx["role"], "must_change_password": ctx.get("must_change_password", False)}


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
        "average_quality_score": _average_quality_score(assets),
    }


def _average_quality_score(assets):
    scores = [
        profile.overall_score
        for profile in (latest_quality_profile(a) for a in assets)
        if profile is not None
    ]
    return round(sum(scores) / len(scores), 1) if scores else None


@router.get("/systems")
def list_systems(ctx=Depends(current_context), db: Session = Depends(get_db)):
    return db.scalars(select(CatalogSystem).where(CatalogSystem.organization_id == ctx["organization_id"]).order_by(CatalogSystem.name)).all()


@router.post("/systems")
def create_system(payload: SystemCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    system = CatalogSystem(organization_id=ctx["organization_id"], name=payload.name, business_purpose=payload.business_purpose, description=payload.description, vendor=payload.vendor, system_owner=payload.system_owner, created_by=ctx["user"].id)
    db.add(system); db.commit(); db.refresh(system); return system


def _serialize_system_inventory(system, detail=None):
    return {
        "id": detail.id if detail else None,
        "system_id": system.id,
        "name": system.name,
        "system_type": detail.system_type if detail else "UNKNOWN",
        "knowledge_status": detail.knowledge_status if detail else "UNASSESSED",
        "known_details": detail.known_details if detail else None,
        "business_purpose": system.business_purpose,
        "description": system.description,
        "vendor": system.vendor,
        "system_owner": system.system_owner,
        "lifecycle_status": system.lifecycle_status,
    }


@router.get("/system-inventory")
def list_system_inventory(ctx=Depends(current_context), db: Session = Depends(get_db)):
    rows = db.execute(
        select(CatalogSystem, SystemInventoryDetail)
        .outerjoin(
            SystemInventoryDetail,
            (SystemInventoryDetail.system_id == CatalogSystem.id)
            & (SystemInventoryDetail.organization_id == CatalogSystem.organization_id),
        )
        .where(CatalogSystem.organization_id == ctx["organization_id"])
        .order_by(CatalogSystem.name)
    ).all()
    return [_serialize_system_inventory(system, detail) for system, detail in rows]


@router.post("/system-inventory")
def create_system_inventory_item(payload: SystemInventoryCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    name = payload.name.strip()
    system = db.scalar(select(CatalogSystem).where(CatalogSystem.organization_id == org_id, CatalogSystem.name == name))
    if system:
        existing = db.scalar(select(SystemInventoryDetail).where(
            SystemInventoryDetail.organization_id == org_id,
            SystemInventoryDetail.system_id == system.id,
        ))
        if existing:
            raise HTTPException(status_code=409, detail="This system is already in the inventory")
        system.business_purpose = payload.business_purpose.strip() if payload.business_purpose else system.business_purpose
        system.description = payload.description.strip() if payload.description else system.description
        system.vendor = payload.vendor.strip() if payload.vendor else system.vendor
        system.system_owner = payload.system_owner.strip() if payload.system_owner else system.system_owner
    else:
        system = CatalogSystem(
            organization_id=org_id,
            name=name,
            business_purpose=payload.business_purpose.strip() if payload.business_purpose else None,
            description=payload.description.strip() if payload.description else None,
            vendor=payload.vendor.strip() if payload.vendor else None,
            system_owner=payload.system_owner.strip() if payload.system_owner else None,
            created_by=ctx["user"].id,
        )
        db.add(system)
        db.flush()
    detail = SystemInventoryDetail(
        organization_id=org_id,
        system_id=system.id,
        system_type=payload.system_type,
        knowledge_status=payload.knowledge_status,
        known_details=payload.known_details.strip() if payload.known_details else None,
        created_by=ctx["user"].id,
    )
    db.add(detail)
    db.commit()
    db.refresh(system)
    db.refresh(detail)
    return _serialize_system_inventory(system, detail)


@router.patch("/system-inventory/{system_id}")
def update_system_inventory_item(system_id: int, payload: SystemInventoryUpdate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    system = db.get(CatalogSystem, system_id)
    if not system or system.organization_id != org_id:
        raise HTTPException(status_code=404, detail="System not found")
    detail = db.scalar(select(SystemInventoryDetail).where(
        SystemInventoryDetail.organization_id == org_id,
        SystemInventoryDetail.system_id == system_id,
    ))
    if not detail:
        detail = SystemInventoryDetail(
            organization_id=org_id,
            system_id=system_id,
            system_type="UNKNOWN",
            knowledge_status="UNCERTAIN",
            created_by=ctx["user"].id,
        )
        db.add(detail)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("name") is not None:
        name = updates["name"].strip()
        duplicate = db.scalar(select(CatalogSystem).where(
            CatalogSystem.organization_id == org_id,
            CatalogSystem.name == name,
            CatalogSystem.id != system_id,
        ))
        if duplicate:
            raise HTTPException(status_code=409, detail="A system with this name already exists")
        system.name = name
    for field in ("business_purpose", "description", "vendor", "system_owner"):
        if field in updates:
            value = updates[field]
            setattr(system, field, value.strip() if isinstance(value, str) else value)
    for field in ("system_type", "knowledge_status", "known_details"):
        if field in updates:
            value = updates[field]
            setattr(detail, field, value.strip() if isinstance(value, str) and field == "known_details" else value)
    db.commit()
    db.refresh(system)
    db.refresh(detail)
    return _serialize_system_inventory(system, detail)


@router.delete("/system-inventory/{system_id}")
def delete_system_inventory_item(system_id: int, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    organization_id = ctx["organization_id"]
    system = db.get(CatalogSystem, system_id)
    if not system or system.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="System not found")
    db.query(DataResource).filter(
        DataResource.organization_id == organization_id,
        DataResource.system_id == system_id,
    ).update({DataResource.system_id: None}, synchronize_session=False)
    db.query(LandscapeRelationship).filter(
        LandscapeRelationship.organization_id == organization_id,
        ((LandscapeRelationship.source_type == "SYSTEM") & (LandscapeRelationship.source_id == system_id))
        | ((LandscapeRelationship.target_type == "SYSTEM") & (LandscapeRelationship.target_id == system_id)),
    ).delete(synchronize_session=False)
    db.query(SystemInventoryDetail).filter(
        SystemInventoryDetail.organization_id == organization_id,
        SystemInventoryDetail.system_id == system_id,
    ).delete(synchronize_session=False)
    db.delete(system)
    db.commit()
    return {"success": True}


RELATIONSHIP_ENTITY_MODELS = {
    "BUSINESS_FUNCTION": BusinessFunction,
    "BUSINESS_CONCEPT": BusinessConcept,
    "BUSINESS_PROCESS": BusinessFlow,
    "SYSTEM": CatalogSystem,
    "RESOURCE": DataResource,
    "ASSET": DataAsset,
}
RELATIONSHIP_ENTITY_PAIRS = {
    "SUPPORTS": ("BUSINESS_FUNCTION", "SYSTEM"),
    "DESCRIBES": ("BUSINESS_CONCEPT", "ASSET"),
    "REPRESENTS": ("SYSTEM", "RESOURCE"),
    "OWNER": ("ASSET", "PERSON"),
    "STEWARD": ("ASSET", "PERSON"),
}


def _relationship_entity(db, entity_type, entity_id, organization_id):
    model = RELATIONSHIP_ENTITY_MODELS.get(entity_type)
    entity = db.get(model, entity_id) if model else None
    if not entity or entity.organization_id != organization_id:
        raise HTTPException(status_code=404, detail=f"{entity_type.replace('_', ' ').title()} not found")
    return entity


def _serialize_relationship(item):
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "target_type": item.target_type,
        "target_id": item.target_id,
        "relationship_type": item.relationship_type,
        "details": item.details,
        "origin": "BUILDER",
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _relationship_identity(item):
    return (
        item["source_type"],
        item["source_id"],
        item["target_type"],
        item["target_id"],
        item["relationship_type"],
    )


@router.get("/landscape/relationships")
def list_landscape_relationships(ctx=Depends(current_context), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    items = db.scalars(
        select(LandscapeRelationship)
        .where(LandscapeRelationship.organization_id == org_id)
        .order_by(LandscapeRelationship.created_at, LandscapeRelationship.id)
    ).all()
    relationships = [_serialize_relationship(item) for item in items]
    known = {_relationship_identity(item) for item in relationships}

    def include_existing(item):
        identity = _relationship_identity(item)
        if identity in known:
            return
        known.add(identity)
        relationships.append(item)

    resources = db.scalars(select(DataResource).where(
        DataResource.organization_id == org_id,
        DataResource.system_id.is_not(None),
    )).all()
    for resource in resources:
        include_existing({
            "id": f"legacy:system-resource:{resource.system_id}:{resource.id}",
            "organization_id": org_id,
            "source_type": "SYSTEM",
            "source_id": resource.system_id,
            "target_type": "RESOURCE",
            "target_id": resource.id,
            "relationship_type": "REPRESENTS",
            "details": {"resource_name": resource.name},
            "origin": "EXISTING",
            "created_at": resource.created_at.isoformat() if resource.created_at else None,
        })

    assets = db.scalars(select(DataAsset).where(DataAsset.organization_id == org_id)).all()
    for asset in assets:
        for field, relationship_type in (("business_owner", "OWNER"), ("data_steward", "STEWARD")):
            display_name = getattr(asset, field)
            if display_name:
                include_existing({
                    "id": f"legacy:asset-{relationship_type.lower()}:{asset.id}",
                    "organization_id": org_id,
                    "source_type": "ASSET",
                    "source_id": asset.id,
                    "target_type": "PERSON",
                    "target_id": None,
                    "relationship_type": relationship_type,
                    "details": {"display_name": display_name},
                    "origin": "EXISTING",
                    "created_at": asset.updated_at.isoformat() if asset.updated_at else None,
                })

    processes = db.scalars(select(BusinessFlow).where(
        BusinessFlow.organization_id == org_id,
        BusinessFlow.source_function_id.is_not(None),
        BusinessFlow.target_function_id.is_not(None),
    )).all()
    for process in processes:
        include_existing({
            "id": f"legacy:process-flow:{process.id}",
            "organization_id": org_id,
            "source_type": "BUSINESS_FUNCTION",
            "source_id": process.source_function_id,
            "target_type": "BUSINESS_FUNCTION",
            "target_id": process.target_function_id,
            "relationship_type": "PROCESS_FLOW",
            "details": {"process_id": process.id, "process_name": process.name},
            "origin": "EXISTING",
            "created_at": process.updated_at.isoformat() if process.updated_at else None,
        })
    return relationships


@router.get("/landscape/completion")
def landscape_completion(ctx=Depends(current_context), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    functions = db.scalars(select(BusinessFunction).where(BusinessFunction.organization_id == org_id)).all()
    concepts = db.scalars(select(BusinessConcept).where(BusinessConcept.organization_id == org_id)).all()
    processes = db.scalars(select(BusinessFlow).where(BusinessFlow.organization_id == org_id)).all()
    units = db.scalars(select(BusinessUnit).where(BusinessUnit.organization_id == org_id)).all()
    systems = db.scalars(select(CatalogSystem).where(CatalogSystem.organization_id == org_id)).all()
    assets = db.scalars(select(DataAsset).where(DataAsset.organization_id == org_id)).all()
    resources = db.scalars(select(DataResource).where(DataResource.organization_id == org_id)).all()
    mappings = db.scalars(select(BusinessFunctionUnit).where(BusinessFunctionUnit.organization_id == org_id)).all()
    relationships = db.scalars(select(LandscapeRelationship).where(LandscapeRelationship.organization_id == org_id)).all()

    support_pairs = {
        (item.source_id, item.target_id)
        for item in relationships
        if item.relationship_type == "SUPPORTS" and item.source_type == "BUSINESS_FUNCTION" and item.target_type == "SYSTEM"
    }
    function_system_ids = {system_id for _, system_id in support_pairs}
    linked_system_ids = set(function_system_ids)
    linked_system_ids.update(resource.system_id for resource in resources if resource.system_id is not None)
    unconnected_systems = [
        {"id": system.id, "name": system.name}
        for system in systems
        if system.id not in linked_system_ids
    ]

    normalized_concepts = {}
    for concept in concepts:
        normalized_name = " ".join(concept.name.casefold().split())
        normalized_concepts.setdefault(normalized_name, []).append({"id": concept.id, "name": concept.name})
    duplicate_concepts = [
        {"normalized_name": normalized_name, "items": items}
        for normalized_name, items in normalized_concepts.items()
        if len(items) > 1
    ]

    incomplete_functions = [
        {"id": item.id, "name": item.name, "missing": [

            field for field, value in (("business outcome", item.purpose), ("description", item.description))
            if not (value or "").strip()
        ]}
        for item in functions
        if not (item.purpose or "").strip() or not (item.description or "").strip()
    ]
    support_count = len(support_pairs)
    sections = [
        {"key": "business_functions", "label": "Business functions", "count": len(functions)},
        {"key": "business_concepts", "label": "Business concepts", "count": len(concepts)},
        {"key": "business_processes", "label": "Business processes", "count": len(processes)},
        {"key": "departments_units", "label": "Departments and units", "count": len(units)},
        {"key": "systems", "label": "Systems", "count": len(systems)},
        {"key": "information_assets", "label": "Information assets", "count": len(assets)},
        {"key": "resources", "label": "Resources and locations", "count": len(resources)},
    ]
    empty_sections = [section["label"] for section in sections if section["count"] == 0]
    missing_business_functions = not functions
    missing_core_function_connections = bool(functions and systems and support_count == 0)
    checks = [
        bool(functions),
        bool(concepts),
        bool(processes),
        bool(units),
        bool(systems),
        bool(assets),
        bool(resources),
        support_count > 0,
        all(bool((item.purpose or "").strip()) for item in functions) if functions else False,
        not duplicate_concepts,
    ]
    completeness_score = round(100 * sum(checks) / len(checks))
    ready_to_proceed = bool(functions and systems and support_count > 0)
    if ready_to_proceed:
        state = "READY_TO_PROCEED"
    elif not functions and not systems:
        state = "NOT_STARTED"
    else:
        state = "IN_PROGRESS"

    guidance = []
    if missing_business_functions:
        guidance.append({"severity": "ACTION", "code": "MISSING_BUSINESS_FUNCTIONS", "message": "Add the core business functions this landscape needs to represent."})
    if missing_core_function_connections:
        guidance.append({"severity": "ACTION", "code": "NO_FUNCTION_SYSTEM_CONNECTIONS", "message": "You have not yet connected your core functions to any systems."})
    if unconnected_systems:
        guidance.append({"severity": "ACTION", "code": "UNCONNECTED_SYSTEMS", "message": f"{len(unconnected_systems)} system{'s are' if len(unconnected_systems) != 1 else ' is'} not connected to a business function or resource."})
    if duplicate_concepts:
        guidance.append({"severity": "REVIEW", "code": "DUPLICATE_CONCEPTS", "message": f"Review {len(duplicate_concepts)} possible duplicate business concept{'s' if len(duplicate_concepts) != 1 else ''}."})
    if empty_sections:
        guidance.append({"severity": "REVIEW", "code": "EMPTY_SECTIONS", "message": "This area looks incomplete: " + ", ".join(empty_sections) + "."})
    if incomplete_functions:
        guidance.append({"severity": "REVIEW", "code": "INCOMPLETE_FUNCTIONS", "message": f"Add a business outcome or description for {len(incomplete_functions)} function{'s' if len(incomplete_functions) != 1 else ''}."})
    if not guidance:
        guidance.append({"severity": "SUCCESS", "code": "READY", "message": "Core functions are connected to systems. You can proceed and keep refining the landscape as you learn more."})

    return {
        "state": state,
        "completeness_score": completeness_score,
        "ready_to_proceed": ready_to_proceed,
        "checks_complete": sum(checks),
        "checks_total": len(checks),
        "counts": {
            "business_functions": len(functions),
            "business_concepts": len(concepts),
            "business_processes": len(processes),
            "departments_units": len(units),
            "systems": len(systems),
            "information_assets": len(assets),
            "resources": len(resources),
            "function_system_connections": support_count,
            "function_unit_mappings": len(mappings),
        },
        "missing_business_functions": missing_business_functions,
        "incomplete_functions": incomplete_functions,
        "unconnected_systems": unconnected_systems,
        "duplicate_concepts": duplicate_concepts,
        "empty_sections": empty_sections,
        "guidance": guidance,
    }


LANDSCAPE_HANDOFF_TASKS = {
    "understanding": {
        "task_type": "landscape_understanding",
        "governance_domain": "DESCRIPTION",
        "title": "Complete the business understanding",
        "why_it_matters": "The landscape identifies the information, but people still need a clear explanation of what it means and how the business uses it.",
        "recommended_action": "Record the business definition, business area, search terms, update frequency, and contact point.",
        "priority": "HIGH",
        "page": "Information Details",
        "tab": "Help Others Understand It",
    },
    "official_source": {
        "task_type": "landscape_official_source",
        "governance_domain": "CATALOG",
        "title": "Confirm where the information officially lives",
        "why_it_matters": "The organization needs to know which recorded location should be relied on for official decisions.",
        "recommended_action": "Record the known locations and confirm the authoritative source.",
        "priority": "HIGH",
        "page": "Information Details",
        "tab": "Where It Lives",
    },
    "quality": {
        "task_type": "landscape_quality",
        "governance_domain": "QUALITY",
        "title": "Assess whether the information can be trusted",
        "why_it_matters": "A quality assessment makes the evidence behind the information's fitness for use visible to stewards.",
        "recommended_action": "Profile a structured source and review the resulting quality evidence and expectations.",
        "priority": "MEDIUM",
        "page": "Information Details",
        "tab": "Can This Information Be Trusted?",
    },
    "approval": {
        "task_type": "landscape_submit_for_review",
        "governance_domain": "PUBLICATION",
        "title": "Submit the stewardship record for approval",
        "why_it_matters": "Approval records the human governance decision before the information is published for wider use.",
        "recommended_action": "Review the completed stewardship record and submit it to an authorized approver.",
        "priority": "MEDIUM",
        "page": "Information Details",
        "tab": "Share & Publish",
    },
}


def _handoff_stage_complete(asset, stage_key, readiness):
    completed = {item["key"] for item in readiness["checks"] if item["complete"]}
    if stage_key == "understanding":
        return "business_definition" in completed and "theme" in completed
    if stage_key == "official_source":
        return "has_resource" in completed and "authoritative_source" in completed
    if stage_key == "quality":
        return "quality" in completed
    publication_status = asset.publication.status if asset.publication else "DRAFT"
    return publication_status in {"IN_REVIEW", "APPROVED", "PUBLISHED"}


@router.post("/landscape/handoff")
def landscape_handoff(ctx=Depends(require_roles("STEWARD", "APPROVER", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    """Turn a ready landscape into explicit, idempotent asset-level work."""
    org_id = ctx["organization_id"]
    assets = db.scalars(
        asset_query().where(DataAsset.organization_id == org_id).order_by(DataAsset.created_at, DataAsset.id)
    ).all()
    created_task_ids = []
    stage_rows = {key: [] for key in LANDSCAPE_HANDOFF_TASKS}
    can_manage_work = ctx["role"] in {"STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN"}

    for asset in assets:
        readiness = sync_tasks(db, asset, ctx["user"].id) if can_manage_work else calculate_readiness(asset)
        if can_manage_work:
            db.flush()
        existing = {
            task.task_type: task
            for task in db.scalars(
                select(StewardshipTask).where(
                    StewardshipTask.organization_id == org_id,
                    StewardshipTask.asset_id == asset.id,
                    StewardshipTask.task_type.in_([item["task_type"] for item in LANDSCAPE_HANDOFF_TASKS.values()]),
                )
            ).all()
        }
        earlier_complete = True
        for stage_key, definition in LANDSCAPE_HANDOFF_TASKS.items():
            complete = _handoff_stage_complete(asset, stage_key, readiness)
            actionable = earlier_complete and not complete
            task = existing.get(definition["task_type"])
            if can_manage_work and actionable and task is None:
                task = StewardshipTask(
                    organization_id=org_id,
                    asset_id=asset.id,
                    task_type=definition["task_type"],
                    governance_domain=definition["governance_domain"],
                    title=definition["title"],
                    why_it_matters=definition["why_it_matters"],
                    recommended_action=definition["recommended_action"],
                    priority=definition["priority"],
                    source_type="LANDSCAPE_HANDOFF",
                    source_reference=stage_key,
                    assigned_to=ctx["user"].id if ctx["role"] in {"STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN"} else None,
                )
                db.add(task)
                db.flush()
                created_task_ids.append(task.id)
            elif can_manage_work and task and complete and task.status != "COMPLETED":
                task.status = "COMPLETED"
                task.completed_at = datetime.now(timezone.utc)
            elif can_manage_work and task and actionable and task.status == "COMPLETED":
                task.status = "OPEN"
                task.completed_at = None

            publication_status = asset.publication.status if asset.publication else "DRAFT"
            if complete:
                status = "COMPLETE"
            elif stage_key == "approval" and publication_status == "IN_REVIEW":
                status = "IN_REVIEW"
            elif actionable:
                status = "REVIEW_REQUIRED" if stage_key == "approval" else "ACTION_REQUIRED"
            else:
                status = "BLOCKED"
            stage_rows[stage_key].append({
                "asset_id": asset.id,
                "asset_name": asset.name,
                "status": status,
                "task_id": task.id if task and task.status != "COMPLETED" else None,
            })
            earlier_complete = earlier_complete and complete

    db.commit()

    stages = []
    for stage_key, definition in LANDSCAPE_HANDOFF_TASKS.items():
        rows = stage_rows[stage_key]
        actionable = next((row for row in rows if row["status"] in {"ACTION_REQUIRED", "REVIEW_REQUIRED", "IN_REVIEW"}), None)
        if not assets:
            status = "WAITING_FOR_INFORMATION"
        elif actionable:
            status = actionable["status"]
        elif all(row["status"] == "COMPLETE" for row in rows):
            status = "COMPLETE"
        else:
            status = "BLOCKED"
        stages.append({
            "key": stage_key,
            "label": definition["title"],
            "page": "Review Queue" if stage_key == "approval" and ctx["role"] == "APPROVER" else definition["page"],
            "tab": definition["tab"],
            "status": status,
            "task_count": sum(1 for row in rows if row["task_id"] is not None),
            "asset_id": actionable["asset_id"] if actionable else None,
            "asset_name": actionable["asset_name"] if actionable else None,
            "task_id": actionable["task_id"] if actionable else None,
        })

    next_stage = next((stage for stage in stages if stage["status"] in {"ACTION_REQUIRED", "REVIEW_REQUIRED", "IN_REVIEW"}), None)
    if next_stage is None and not assets:
        next_stage = {
            "key": "understanding",
            "label": "Identify information to steward",
            "page": "Discover Information",
            "tab": None,
            "status": "WAITING_FOR_INFORMATION",
            "task_count": 0,
            "asset_id": None,
            "asset_name": None,
            "task_id": None,
        }
    return {"success": True, "created_task_ids": created_task_ids, "stages": stages, "next_stage": next_stage}

def _landscape_snapshot(db, organization_id):
    def rows(model, fields):
        items = db.scalars(select(model).where(model.organization_id == organization_id)).all()
        return [{field: getattr(item, field) for field in fields} for item in items]

    return {
        "business_functions": rows(BusinessFunction, ("id", "name", "description", "purpose", "owner", "parent_function_id", "status", "created_by")),
        "business_concepts": rows(BusinessConcept, ("id", "name", "description", "category", "definition", "status", "owner", "created_by")),
        "business_processes": rows(BusinessFlow, ("id", "name", "description", "trigger", "frequency", "source_function_id", "target_function_id", "status", "created_by")),
        "business_units": rows(BusinessUnit, ("id", "name", "unit_type", "description", "status", "created_by")),
        "function_unit_mappings": rows(BusinessFunctionUnit, ("id", "function_id", "unit_id", "created_by")),
        "systems": rows(CatalogSystem, ("id", "name", "description", "business_purpose", "vendor", "system_owner", "lifecycle_status", "created_by")),
        "system_inventory": rows(SystemInventoryDetail, ("id", "system_id", "system_type", "knowledge_status", "known_details", "created_by")),
        "relationships": rows(LandscapeRelationship, ("id", "source_type", "source_id", "target_type", "target_id", "relationship_type", "details", "created_by")),
        "asset_responsibilities": rows(DataAsset, ("id", "business_owner", "data_steward")),
        "resource_systems": rows(DataResource, ("id", "system_id")),
    }


def _draft_revision_summary(revision):
    return {"id": revision["id"], "label": revision["label"], "created_at": revision["created_at"]}


@router.get("/landscape/draft")
def get_landscape_draft(ctx=Depends(current_context), db: Session = Depends(get_db)):
    item = db.scalar(select(LandscapeWorkspaceDraft).where(LandscapeWorkspaceDraft.organization_id == ctx["organization_id"]))
    if not item:
        return {"draft_data": {}, "revisions": [], "updated_at": None}
    return {
        "draft_data": item.draft_data or {},
        "revisions": [_draft_revision_summary(revision) for revision in reversed(item.revisions or [])],
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.patch("/landscape/draft")
def save_landscape_draft(payload: LandscapeDraftUpdate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    organization_id = ctx["organization_id"]
    item = db.scalar(select(LandscapeWorkspaceDraft).where(LandscapeWorkspaceDraft.organization_id == organization_id))
    if not item:
        item = LandscapeWorkspaceDraft(
            organization_id=organization_id,
            created_by=ctx["user"].id,
            draft_data=payload.draft_data,
            revisions=[],
        )
        db.add(item)
    else:
        item.draft_data = payload.draft_data
        item.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        # Blur and debounced autosave requests can arrive concurrently. The
        # organization-level unique constraint decides which insert wins; the
        # losing request then updates that row instead of returning a 500.
        db.rollback()
        item = db.scalar(select(LandscapeWorkspaceDraft).where(LandscapeWorkspaceDraft.organization_id == organization_id))
        if not item:
            raise
        item.draft_data = payload.draft_data
        item.updated_at = datetime.now(timezone.utc)
        db.commit()
    db.refresh(item)
    return {"draft_data": item.draft_data, "updated_at": item.updated_at.isoformat() if item.updated_at else None}


@router.post("/landscape/draft/checkpoint")
def checkpoint_landscape(ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), payload: LandscapeDraftCheckpoint | None = None, db: Session = Depends(get_db)):
    item = db.scalar(select(LandscapeWorkspaceDraft).where(LandscapeWorkspaceDraft.organization_id == ctx["organization_id"]))
    if not item:
        item = LandscapeWorkspaceDraft(organization_id=ctx["organization_id"], created_by=ctx["user"].id, draft_data={}, revisions=[])
        db.add(item)
        db.flush()
    revisions = list(item.revisions or [])
    revision = {
        "id": str(uuid4()),
        "label": (payload.label.strip() if payload and payload.label else "Before landscape changes"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshot": _landscape_snapshot(db, ctx["organization_id"]),
    }
    revisions.append(revision)
    item.revisions = revisions[-20:]
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"revision": _draft_revision_summary(revision), "revision_count": len(item.revisions)}


def _replace_org_rows(db, model, organization_id, saved_rows):
    saved_ids = {row["id"] for row in saved_rows}
    db.query(model).filter(model.organization_id == organization_id, model.id.not_in(saved_ids)).delete(synchronize_session=False)
    for values in saved_rows:
        item = db.get(model, values["id"])
        if item is not None and item.organization_id != organization_id:
            raise HTTPException(status_code=409, detail="A saved landscape item now belongs to another organization")
        if item is None:
            item = model(id=values["id"], organization_id=organization_id)
            db.add(item)
        for field, value in values.items():
            if field != "id":
                setattr(item, field, value)


@router.post("/landscape/draft/restore/{revision_id}")
def restore_landscape_revision(revision_id: str, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    organization_id = ctx["organization_id"]
    item = db.scalar(select(LandscapeWorkspaceDraft).where(LandscapeWorkspaceDraft.organization_id == organization_id))
    revision = next((entry for entry in (item.revisions if item else []) if entry.get("id") == revision_id), None)
    if not revision:
        raise HTTPException(status_code=404, detail="Landscape revision not found")

    revisions = list(item.revisions or [])
    before_restore = {
        "id": str(uuid4()),
        "label": "Before restoring a landscape revision",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshot": _landscape_snapshot(db, organization_id),
    }
    revisions.append(before_restore)
    snapshot = revision["snapshot"]

    db.query(LandscapeRelationship).filter(LandscapeRelationship.organization_id == organization_id).delete(synchronize_session=False)
    db.query(BusinessFunctionUnit).filter(BusinessFunctionUnit.organization_id == organization_id).delete(synchronize_session=False)
    db.query(BusinessFlow).filter(BusinessFlow.organization_id == organization_id).delete(synchronize_session=False)
    db.query(BusinessFunction).filter(BusinessFunction.organization_id == organization_id).update({BusinessFunction.parent_function_id: None}, synchronize_session=False)
    _replace_org_rows(db, BusinessFunction, organization_id, snapshot["business_functions"])
    _replace_org_rows(db, BusinessConcept, organization_id, snapshot["business_concepts"])
    _replace_org_rows(db, BusinessUnit, organization_id, snapshot["business_units"])
    _replace_org_rows(db, BusinessFlow, organization_id, snapshot["business_processes"])
    _replace_org_rows(db, BusinessFunctionUnit, organization_id, snapshot["function_unit_mappings"])

    db.query(DataResource).filter(DataResource.organization_id == organization_id).update({DataResource.system_id: None}, synchronize_session=False)
    _replace_org_rows(db, CatalogSystem, organization_id, snapshot["systems"])
    _replace_org_rows(db, SystemInventoryDetail, organization_id, snapshot["system_inventory"])
    _replace_org_rows(db, LandscapeRelationship, organization_id, snapshot["relationships"])

    for saved in snapshot["asset_responsibilities"]:
        asset = db.get(DataAsset, saved["id"])
        if asset and asset.organization_id == organization_id:
            asset.business_owner = saved["business_owner"]
            asset.data_steward = saved["data_steward"]
    for saved in snapshot["resource_systems"]:
        resource = db.get(DataResource, saved["id"])
        if resource and resource.organization_id == organization_id:
            resource.system_id = saved["system_id"]

    item.revisions = revisions[-20:]
    item.draft_data = {}
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"success": True, "restored_revision": _draft_revision_summary(revision), "revision_count": len(item.revisions)}



def _validate_dependency_acyclic(db, organization_id, entity_type, source_id, target_id):
    if source_id == target_id:
        raise HTTPException(status_code=422, detail="An item cannot depend on itself")
    pending = [target_id]
    visited = set()
    while pending:
        current_id = pending.pop()
        if current_id == source_id:
            raise HTTPException(status_code=409, detail="This dependency would create a cycle")
        if current_id in visited:
            continue
        visited.add(current_id)
        pending.extend(db.scalars(select(LandscapeRelationship.target_id).where(
            LandscapeRelationship.organization_id == organization_id,
            LandscapeRelationship.source_type == entity_type,
            LandscapeRelationship.source_id == current_id,
            LandscapeRelationship.target_type == entity_type,
            LandscapeRelationship.relationship_type == "DEPENDS_ON",
            LandscapeRelationship.target_id.is_not(None),
        )).all())


def _legacy_relationship_id(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Relationship not found")
    if parsed < 1:
        raise HTTPException(status_code=404, detail="Relationship not found")
    return parsed


@router.post("/landscape/relationships")
def create_landscape_relationship(payload: LandscapeRelationshipCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    relationship_type = payload.relationship_type
    details = dict(payload.details or {})

    if relationship_type in RELATIONSHIP_ENTITY_PAIRS:
        expected_source, expected_target = RELATIONSHIP_ENTITY_PAIRS[relationship_type]
        if (payload.source_type, payload.target_type) != (expected_source, expected_target):
            raise HTTPException(status_code=422, detail="These entity types do not support that relationship")
    elif relationship_type == "DEPENDS_ON":
        valid_types = {"BUSINESS_FUNCTION", "SYSTEM", "ASSET"}
        if payload.source_type != payload.target_type or payload.source_type not in valid_types:
            raise HTTPException(status_code=422, detail="Dependencies must connect two functions, two systems, or two assets")
    elif relationship_type == "PROCESS_FLOW":
        if (payload.source_type, payload.target_type) != ("BUSINESS_FUNCTION", "BUSINESS_FUNCTION") or not payload.process_id:
            raise HTTPException(status_code=422, detail="A process flow needs a process and two business functions")

    source = _relationship_entity(db, payload.source_type, payload.source_id, org_id)
    target = None
    if payload.target_type == "PERSON":
        if payload.target_id is not None:
            raise HTTPException(status_code=422, detail="People are identified by name, not by a system record")
        display_name = details.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip() or len(display_name.strip()) > 255:
            raise HTTPException(status_code=422, detail="Enter the owner or steward name")
        details["display_name"] = display_name.strip()
    else:
        if payload.target_id is None:
            raise HTTPException(status_code=422, detail="A target item is required")
        target = _relationship_entity(db, payload.target_type, payload.target_id, org_id)

    if relationship_type == "DEPENDS_ON":
        _validate_dependency_acyclic(db, org_id, payload.source_type, payload.source_id, payload.target_id)

    if relationship_type == "PROCESS_FLOW":
        process = db.get(BusinessFlow, payload.process_id)
        if not process or process.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Business process not found")
        process.source_function_id = payload.source_id
        process.target_function_id = payload.target_id
        process.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(process)
        return {
            "id": f"legacy:process-flow:{process.id}",
            "organization_id": org_id,
            "source_type": "BUSINESS_FUNCTION",
            "source_id": process.source_function_id,
            "target_type": "BUSINESS_FUNCTION",
            "target_id": process.target_function_id,
            "relationship_type": "PROCESS_FLOW",
            "details": {"process_id": process.id, "process_name": process.name},
            "origin": "EXISTING",
            "created_at": process.updated_at.isoformat() if process.updated_at else None,
        }

    if relationship_type in {"OWNER", "STEWARD"}:
        field = "business_owner" if relationship_type == "OWNER" else "data_steward"
        db.query(LandscapeRelationship).filter(
            LandscapeRelationship.organization_id == org_id,
            LandscapeRelationship.source_type == "ASSET",
            LandscapeRelationship.source_id == source.id,
            LandscapeRelationship.relationship_type == relationship_type,
        ).delete(synchronize_session=False)
        setattr(source, field, details["display_name"])
    elif relationship_type == "REPRESENTS":
        if target.system_id not in (None, source.id):
            raise HTTPException(status_code=409, detail="This resource is already linked to another system")
        target.system_id = source.id

    duplicate = db.scalar(select(LandscapeRelationship).where(
        LandscapeRelationship.organization_id == org_id,
        LandscapeRelationship.source_type == payload.source_type,
        LandscapeRelationship.source_id == payload.source_id,
        LandscapeRelationship.target_type == payload.target_type,
        LandscapeRelationship.target_id == payload.target_id,
        LandscapeRelationship.relationship_type == relationship_type,
    ))
    if duplicate:
        raise HTTPException(status_code=409, detail="This relationship already exists")

    item = LandscapeRelationship(
        organization_id=org_id,
        source_type=payload.source_type,
        source_id=payload.source_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        relationship_type=relationship_type,
        details=details or None,
        created_by=ctx["user"].id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_relationship(item)


@router.delete("/landscape/relationships/{relationship_id}")
def delete_landscape_relationship(relationship_id: str, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    try:
        item_id = int(relationship_id)
    except ValueError:
        item_id = None
    if item_id is not None:
        item = db.get(LandscapeRelationship, item_id)
        if not item or item.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Relationship not found")
        if item.relationship_type == "REPRESENTS" and item.source_type == "SYSTEM":
            resource = db.get(DataResource, item.target_id)
            if resource and resource.organization_id == org_id and resource.system_id == item.source_id:
                resource.system_id = None
        elif item.relationship_type in {"OWNER", "STEWARD"}:
            asset = db.get(DataAsset, item.source_id)
            field = "business_owner" if item.relationship_type == "OWNER" else "data_steward"
            if asset and asset.organization_id == org_id and getattr(asset, field) == (item.details or {}).get("display_name"):
                setattr(asset, field, None)
        db.delete(item)
        db.commit()
        return {"success": True}

    parts = relationship_id.split(":")
    if len(parts) >= 3 and parts[0] == "legacy":
        if parts[1] == "system-resource" and len(parts) == 4:
            system = _relationship_entity(db, "SYSTEM", _legacy_relationship_id(parts[2]), org_id)
            resource = _relationship_entity(db, "RESOURCE", _legacy_relationship_id(parts[3]), org_id)
            if resource.system_id == system.id:
                resource.system_id = None
        elif parts[1] in {"asset-owner", "asset-steward"} and len(parts) == 3:
            asset = _relationship_entity(db, "ASSET", _legacy_relationship_id(parts[2]), org_id)
            field = "business_owner" if parts[1] == "asset-owner" else "data_steward"
            setattr(asset, field, None)
        elif parts[1] == "process-flow" and len(parts) == 3:
            process = _relationship_entity(db, "BUSINESS_PROCESS", _legacy_relationship_id(parts[2]), org_id)
            process.source_function_id = None
            process.target_function_id = None
        else:
            raise HTTPException(status_code=404, detail="Relationship not found")
        db.commit()
        return {"success": True}
    raise HTTPException(status_code=404, detail="Relationship not found")


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


@router.get("/assets/{asset_id}/official-source")
def get_official_source(asset_id: int, ctx=Depends(current_context), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    current = next((link for link in asset.resources if link.is_authoritative), None)

    def serialize_location(link):
        resource = link.resource
        return {
            "resource_id": resource.id,
            "name": resource.name,
            "resource_type": resource.resource_type,
            "structure_type": resource.structure_type,
            "location_reference": resource.location_reference,
            "description": resource.description,
            "relationship_type": link.relationship_type,
            "is_authoritative": bool(link.is_authoritative),
            "system": resource.system.name if resource.system else None,
        }

    return {
        "asset_id": asset.id,
        "asset_name": asset.name,
        "authoritative_status": asset.authoritative_status,
        "official_source": serialize_location(current) if current else None,
        "locations": [serialize_location(link) for link in asset.resources],
    }


@router.post("/assets/{asset_id}/official-source")
def choose_official_source(asset_id: int, payload: OfficialSourceDecision, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    links = db.scalars(select(AssetResource).where(AssetResource.asset_id == asset.id)).all()

    selected = None
    for link in links:
        if link.resource_id == payload.resource_id:
            selected = link
            break

    if not selected:
        raise HTTPException(status_code=400, detail="Selected location is not linked to this information asset")

    # Exactly one linked representation is the official source at a time.
    for link in links:
        link.is_authoritative = (link.resource_id == payload.resource_id)

    asset.authoritative_status = "CONFIRMED"

    # Preserve the steward's business reasoning as approved metadata so the
    # decision remains understandable without exposing technical catalog fields.
    if payload.decision_basis:
        for item in db.scalars(
            select(AssetMetadata).where(
                AssetMetadata.asset_id == asset.id,
                AssetMetadata.metadata_key == "official_source_basis",
            )
        ).all():
            db.delete(item)
        db.add(AssetMetadata(
            asset_id=asset.id,
            metadata_key="official_source_basis",
            metadata_value=payload.decision_basis,
            metadata_source="STEWARD",
            review_status="APPROVED",
            created_by=ctx["user"].id,
            reviewed_by=ctx["user"].id,
            reviewed_at=datetime.now(timezone.utc),
        ))

    mark_needs_update_if_published(db, asset, ctx["user"].id, "Official source decision changed")
    db.commit()

    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    sync_tasks(db, asset, ctx["user"].id)
    db.commit()
    return serialize_asset(asset)


@router.get("/assets/{asset_id}/understanding")
def get_understanding(asset_id: int, ctx=Depends(current_context), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    metadata = build_asset_snapshot(asset)["metadata"]

    def first_value(value):
        if isinstance(value, list):
            return value[0] if value else None
        return value

    business_area = asset.business_domain or first_value(metadata.get("theme")) or ""
    search_terms = metadata.get("keyword")
    if isinstance(search_terms, str):
        search_terms = [search_terms]
    elif search_terms is None:
        search_terms = []

    update_frequency = first_value(metadata.get("update_frequency")) or ""
    contact = first_value(metadata.get("contact")) or {}
    if isinstance(contact, str):
        contact = {"name": contact, "email": None}
    if not isinstance(contact, dict):
        contact = {"name": "", "email": None}

    return {
        "asset_id": asset.id,
        "business_definition": asset.business_definition,
        "business_area": business_area,
        "search_terms": search_terms,
        "update_frequency": update_frequency,
        "contact_point": {
            "name": contact.get("name") or "",
            "email": contact.get("email") or None,
        },
    }


@router.patch("/assets/{asset_id}/understanding")
def update_understanding(asset_id: int, payload: UnderstandingUpdate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])

    asset.business_definition = payload.business_definition.strip()
    asset.business_domain = payload.business_area.strip()
    
    if isinstance(payload.contact_point, str):
        contact_value = {
            "name": payload.contact_point.strip(),
        }
    else:
        contact_value = {
            "name": payload.contact_point.name.strip(),
        }
        if payload.contact_point.email and payload.contact_point.email.strip():
            contact_value["email"] = payload.contact_point.email.strip()
            
    metadata_values = {
        "theme": [payload.business_area.strip()],
        "keyword": [value.strip() for value in payload.search_terms if value and value.strip()],
        "update_frequency": [payload.update_frequency.strip()],
        "contact": [contact_value],
    }

    for key, values in metadata_values.items():
        for item in db.scalars(
            select(AssetMetadata).where(
                AssetMetadata.asset_id == asset.id,
                AssetMetadata.metadata_key == key,
            )
        ).all():
            db.delete(item)

        for value in values:
            db.add(AssetMetadata(
                asset_id=asset.id,
                metadata_key=key,
                metadata_value=value,
                metadata_source="STEWARD",
                review_status="APPROVED",
                created_by=ctx["user"].id,
                reviewed_by=ctx["user"].id,
                reviewed_at=datetime.now(timezone.utc),
            ))

    mark_needs_update_if_published(db, asset, ctx["user"].id, "Business description or discovery information changed")
    db.commit()

    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    sync_tasks(db, asset, ctx["user"].id)
    db.commit()
    return serialize_asset(asset)


@router.put("/assets/{asset_id}/metadata")
def upsert_metadata(asset_id: int, payload: MetadataUpsert, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    for item in db.scalars(select(AssetMetadata).where(AssetMetadata.asset_id == asset.id, AssetMetadata.metadata_key == payload.metadata_key)).all():
        db.delete(item)
    values = payload.metadata_value if payload.metadata_key == "keyword" and isinstance(payload.metadata_value, list) else [payload.metadata_value]
    now = datetime.now(timezone.utc)
    for value in values:
        db.add(AssetMetadata(asset_id=asset.id, metadata_key=payload.metadata_key, metadata_value=value, metadata_source=payload.metadata_source, review_status="APPROVED", created_by=ctx["user"].id, reviewed_by=ctx["user"].id, reviewed_at=now))
    mark_needs_update_if_published(db, asset, ctx["user"].id, f"Metadata changed: {payload.metadata_key}"); db.commit()
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"]); sync_tasks(db, asset); db.commit(); return serialize_asset(asset)


@router.get("/assets/{asset_id}/reviews")
def list_periodic_reviews(asset_id: int, ctx=Depends(current_context), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    reviews = db.scalars(
        select(StewardshipReview)
        .where(
            StewardshipReview.asset_id == asset.id,
            StewardshipReview.organization_id == ctx["organization_id"],
        )
        .order_by(StewardshipReview.reviewed_at.desc())
    ).all()

    latest = reviews[0] if reviews else None
    next_due = latest.next_review_due if latest else (asset.created_at + timedelta(days=365))
    return {
        "latest": _serialize_review(latest) if latest else None,
        "next_review_due": next_due.isoformat(),
        "is_due": next_due <= datetime.now(timezone.utc),
        "history": [_serialize_review(r) for r in reviews],
    }


def _serialize_review(review):
    if not review:
        return None
    return {
        "id": review.id,
        "review_type": review.review_type,
        "answers": review.answers or {},
        "change_summary": review.change_summary,
        "reviewed_by": review.reviewed_by,
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        "next_review_due": review.next_review_due.isoformat() if review.next_review_due else None,
    }


def _ensure_review_followup_task(db, asset, review, key, domain, title, why, action, priority="MEDIUM"):
    task_type = f"review_change_{key}"
    existing = db.scalar(
        select(StewardshipTask).where(
            StewardshipTask.asset_id == asset.id,
            StewardshipTask.task_type == task_type,
            StewardshipTask.status != "COMPLETED",
        )
    )
    if existing:
        existing.source_reference = str(review.id)
        existing.source_type = "PERIODIC_REVIEW_CHANGE"
        return existing, False

    task = StewardshipTask(
        organization_id=asset.organization_id,
        asset_id=asset.id,
        task_type=task_type,
        governance_domain=domain,
        title=title,
        why_it_matters=why,
        recommended_action=action,
        priority=priority,
        source_type="PERIODIC_REVIEW_CHANGE",
        source_reference=str(review.id),
    )
    db.add(task)
    return task, True


@router.post("/assets/{asset_id}/reviews")
def complete_periodic_review(asset_id: int, payload: PeriodicReviewCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    now = datetime.now(timezone.utc)
    interval_days = min(max(payload.review_interval_days, 30), 1095)

    review = StewardshipReview(
        organization_id=ctx["organization_id"],
        asset_id=asset.id,
        review_type="PERIODIC",
        answers=payload.answers,
        change_summary=payload.change_summary,
        snapshot_before=build_asset_snapshot(asset),
        reviewed_by=ctx["user"].id,
        reviewed_at=now,
        next_review_due=now + timedelta(days=interval_days),
    )
    db.add(review)
    db.flush()

    followups = {
        "purpose": (
            "DESCRIPTION", "Review the information purpose",
            "The steward indicated that the business purpose may have changed.",
            "Update the plain-language description so it reflects how the information is used now."
        ),
        "ownership": (
            "OWNERSHIP", "Review ownership responsibilities",
            "The steward indicated that the owner or stewardship responsibility may have changed.",
            "Confirm the current business owner and data steward."
        ),
        "locations": (
            "CATALOG", "Review where the information lives",
            "The steward indicated that systems, files, reports, or other locations may have changed.",
            "Update the known locations and representations for this information."
        ),
        "official_source": (
            "GOVERNANCE", "Reconfirm the official source",
            "The steward indicated that the location relied on as the official record may have changed.",
            "Use the guided Official Source workflow to reconfirm the correct location."
        ),
        "classification": (
            "CLASSIFICATION", "Recheck how this information should be handled",
            "The steward indicated that sensitivity, access, or sharing conditions may have changed.",
            "Repeat the guided classification review using the current business context."
        ),
        "retention": (
            "LIFECYCLE", "Recheck retention requirements",
            "The steward indicated that the retention requirement or governing authority may have changed.",
            "Confirm the current approved retention requirement and authority."
        ),
        "quality": (
            "QUALITY", "Reassess whether this information can be trusted",
            "The steward indicated that there may be new or meaningful quality concerns.",
            "Review the current quality evidence and rerun assessment when appropriate."
        ),
        "active_use": (
            "MAINTENANCE", "Confirm whether this information is still actively used",
            "The steward indicated that the information may no longer be actively used.",
            "Confirm whether it should remain active, be archived, or follow another lifecycle action."
        ),
    }

    created_followups = []
    for key, answer in (payload.answers or {}).items():
        if answer not in {"changed", "unsure", "no"}:
            continue
        # For active use, "no" means no longer actively used; for other fields
        # "changed"/"unsure" means follow-up is needed.
        needs_followup = (
            (key == "active_use" and answer in {"no", "unsure"})
            or (key != "active_use" and answer in {"changed", "unsure"})
        )
        if needs_followup and key in followups:
            domain, title, why, action = followups[key]
            _task, created = _ensure_review_followup_task(
                db, asset, review, key, domain, title, why, action
            )
            if created:
                created_followups.append(title)

    # Close the scheduled review task itself.
    periodic_task = db.scalar(
        select(StewardshipTask).where(
            StewardshipTask.asset_id == asset.id,
            StewardshipTask.task_type == "periodic_review",
            StewardshipTask.status != "COMPLETED",
        )
    )
    if periodic_task:
        periodic_task.status = "COMPLETED"
        periodic_task.completed_at = now

    db.commit()

    # Existing readiness tasks are still reconciled normally.
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    sync_tasks(db, asset, ctx["user"].id)
    db.commit()

    return {
        "success": True,
        "review": _serialize_review(review),
        "follow_up_tasks": created_followups,
        "message": (
            "Review complete. Follow-up work was created only for areas that changed."
            if created_followups
            else "Review complete. No stewardship changes need follow-up."
        ),
    }


@router.get("/discovery/summary")
def discovery_summary(ctx=Depends(current_context), db: Session = Depends(get_db)):
    organization_id = ctx["organization_id"]
    candidates = db.scalars(select(DiscoveryCandidate).where(DiscoveryCandidate.organization_id == organization_id)).all()
    assets = db.scalars(select(DataAsset).where(DataAsset.organization_id == organization_id)).all()
    systems = db.scalars(select(CatalogSystem).where(CatalogSystem.organization_id == organization_id)).all()
    resources = db.scalars(select(DataResource).where(DataResource.organization_id == organization_id)).all()
    confirmed_candidates = [c for c in candidates if c.status == DiscoveryCandidateStatus.CONFIRMED.value]
    confirmed_assets = [a for a in assets if a.asset_status in {"ACTIVE", "DRAFT"}]
    confirmed_systems = [s for s in systems if s.lifecycle_status in {"ACTIVE", "DRAFT"}]
    confirmed_locations = [r for r in resources if r.resource_type in {"TABLE", "FILE", "DATABASE", "API", "DOCUMENT", "REPORT", "SYSTEM"}]

    # Ground Zero is a server-side state, not a browser-local one: a new or
    # uninitialized organization has no meaningful confirmed landscape yet.
    ground_zero = (
        len(confirmed_assets) == 0
        and len(confirmed_systems) == 0
        and len(confirmed_locations) == 0
        and len(confirmed_candidates) == 0
    )

    return {
        "ground_zero": ground_zero,
        "meaningful_landscape": not ground_zero,
        "known_assets": len(confirmed_assets),
        "known_systems": len(confirmed_systems),
        "known_locations": len(confirmed_locations),
        "candidate_count": len(candidates),
        "confirmed_count": len(confirmed_candidates),
        "suggested_count": sum(1 for c in candidates if c.status == DiscoveryCandidateStatus.SUGGESTED.value),
        "needs_confirmation_count": sum(1 for c in candidates if c.status == DiscoveryCandidateStatus.NEEDS_CONFIRMATION.value),
        "rejected_count": sum(1 for c in candidates if c.status == DiscoveryCandidateStatus.REJECTED.value),
        "unknown_count": sum(1 for c in candidates if c.status == DiscoveryCandidateStatus.UNKNOWN.value),
    }


@router.get("/discovery/provenance")
def list_discovery_provenance(ctx=Depends(current_context), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    entries = db.scalars(
        select(DiscoveryProvenance)
        .where(DiscoveryProvenance.organization_id == org_id)
        .order_by(DiscoveryProvenance.created_at.desc())
    ).all()
    return [_serialize_provenance(entry) for entry in entries]


@router.get("/landscape/functions")
def list_business_functions(ctx=Depends(current_context), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    items = db.scalars(select(BusinessFunction).where(BusinessFunction.organization_id == org_id).order_by(BusinessFunction.name)).all()
    return [{
        "id": item.id,
        "organization_id": item.organization_id,
        "name": item.name,
        "description": item.description,
        "purpose": item.purpose,
        "owner": item.owner,
        "parent_function_id": item.parent_function_id,
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    } for item in items]


@router.get("/landscape/units")
def list_business_units(ctx=Depends(current_context), db: Session = Depends(get_db)):
    items = db.scalars(
        select(BusinessUnit)
        .where(BusinessUnit.organization_id == ctx["organization_id"])
        .order_by(BusinessUnit.name)
    ).all()
    return [_serialize_business_unit(item) for item in items]


def _serialize_business_unit(item):
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "name": item.name,
        "unit_type": item.unit_type,
        "description": item.description,
        "status": item.status,
    }


@router.post("/landscape/units")
def create_business_unit(payload: BusinessUnitCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    item = BusinessUnit(
        organization_id=ctx["organization_id"],
        name=payload.name.strip(),
        unit_type=payload.unit_type,
        description=payload.description.strip() if payload.description else None,
        status=payload.status,
        created_by=ctx["user"].id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_business_unit(item)


@router.patch("/landscape/units/{unit_id}")
def update_business_unit(unit_id: int, payload: BusinessUnitUpdate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    item = db.get(BusinessUnit, unit_id)
    if not item or item.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Business unit not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(item, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(item)
    return _serialize_business_unit(item)


@router.delete("/landscape/units/{unit_id}")
def delete_business_unit(unit_id: int, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    item = db.get(BusinessUnit, unit_id)
    if not item or item.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Business unit not found")
    db.query(BusinessFunctionUnit).filter(
        BusinessFunctionUnit.organization_id == ctx["organization_id"],
        BusinessFunctionUnit.unit_id == unit_id,
    ).delete(synchronize_session=False)
    db.delete(item)
    db.commit()
    return {"success": True}


@router.get("/landscape/function-unit-mappings")
def list_business_function_unit_mappings(ctx=Depends(current_context), db: Session = Depends(get_db)):
    items = db.scalars(
        select(BusinessFunctionUnit)
        .where(BusinessFunctionUnit.organization_id == ctx["organization_id"])
        .order_by(BusinessFunctionUnit.id)
    ).all()
    return [_serialize_business_function_unit_mapping(item) for item in items]


def _serialize_business_function_unit_mapping(item):
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "function_id": item.function_id,
        "unit_id": item.unit_id,
    }


def _get_org_business_function(db, function_id, organization_id):
    item = db.get(BusinessFunction, function_id)
    if not item or item.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Business function not found")
    return item


def _get_org_business_unit(db, unit_id, organization_id):
    item = db.get(BusinessUnit, unit_id)
    if not item or item.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Business unit not found")
    return item


@router.post("/landscape/function-unit-mappings")
def create_business_function_unit_mapping(payload: BusinessFunctionUnitMappingCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    _get_org_business_function(db, payload.function_id, org_id)
    _get_org_business_unit(db, payload.unit_id, org_id)
    existing = db.scalar(select(BusinessFunctionUnit).where(
        BusinessFunctionUnit.organization_id == org_id,
        BusinessFunctionUnit.function_id == payload.function_id,
        BusinessFunctionUnit.unit_id == payload.unit_id,
    ))
    if existing:
        raise HTTPException(status_code=409, detail="This business function is already mapped to that unit")
    item = BusinessFunctionUnit(
        organization_id=org_id,
        function_id=payload.function_id,
        unit_id=payload.unit_id,
        created_by=ctx["user"].id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_business_function_unit_mapping(item)


@router.patch("/landscape/function-unit-mappings/{mapping_id}")
def update_business_function_unit_mapping(mapping_id: int, payload: BusinessFunctionUnitMappingUpdate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    item = db.get(BusinessFunctionUnit, mapping_id)
    if not item or item.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Business function unit mapping not found")
    updates = payload.model_dump(exclude_unset=True)
    function_id = updates.get("function_id", item.function_id)
    unit_id = updates.get("unit_id", item.unit_id)
    _get_org_business_function(db, function_id, org_id)
    _get_org_business_unit(db, unit_id, org_id)
    duplicate = db.scalar(select(BusinessFunctionUnit).where(
        BusinessFunctionUnit.organization_id == org_id,
        BusinessFunctionUnit.function_id == function_id,
        BusinessFunctionUnit.unit_id == unit_id,
        BusinessFunctionUnit.id != mapping_id,
    ))
    if duplicate:
        raise HTTPException(status_code=409, detail="This business function is already mapped to that unit")
    item.function_id = function_id
    item.unit_id = unit_id
    db.commit()
    db.refresh(item)
    return _serialize_business_function_unit_mapping(item)


@router.delete("/landscape/function-unit-mappings/{mapping_id}")
def delete_business_function_unit_mapping(mapping_id: int, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    item = db.get(BusinessFunctionUnit, mapping_id)
    if not item or item.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Business function unit mapping not found")
    db.delete(item)
    db.commit()
    return {"success": True}


@router.post("/landscape/functions")
def create_business_function(payload: BusinessFunctionCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    item = BusinessFunction(
        organization_id=ctx["organization_id"],
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        purpose=payload.purpose.strip() if payload.purpose else None,
        owner=payload.owner.strip() if payload.owner else None,
        parent_function_id=payload.parent_function_id,
        status=payload.status or "ACTIVE",
        created_by=ctx["user"].id,
    )
    db.add(item)
    db.commit(); db.refresh(item)
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "name": item.name,
        "description": item.description,
        "purpose": item.purpose,
        "owner": item.owner,
        "parent_function_id": item.parent_function_id,
        "status": item.status,
    }


@router.patch("/landscape/functions/{function_id}")
def update_business_function(function_id: int, payload: BusinessFunctionUpdate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    item = db.get(BusinessFunction, function_id)
    if not item or item.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Business function not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        setattr(item, field, value)
    db.commit(); db.refresh(item)
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "name": item.name,
        "description": item.description,
        "purpose": item.purpose,
        "owner": item.owner,
        "parent_function_id": item.parent_function_id,
        "status": item.status,
    }


@router.delete("/landscape/functions/{function_id}")
def delete_business_function(function_id: int, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    item = db.get(BusinessFunction, function_id)
    if not item or item.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Business function not found")
    db.query(BusinessFunctionUnit).filter(BusinessFunctionUnit.function_id == function_id).delete(synchronize_session=False)
    db.query(BusinessFlow).filter(BusinessFlow.source_function_id == function_id).update({BusinessFlow.source_function_id: None}, synchronize_session=False)
    db.query(BusinessFlow).filter(BusinessFlow.target_function_id == function_id).update({BusinessFlow.target_function_id: None}, synchronize_session=False)
    db.delete(item)
    db.commit()
    return {"success": True}


@router.get("/landscape/concepts")
def list_business_concepts(ctx=Depends(current_context), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    items = db.scalars(select(BusinessConcept).where(BusinessConcept.organization_id == org_id).order_by(BusinessConcept.name)).all()
    return [{
        "id": item.id,
        "organization_id": item.organization_id,
        "name": item.name,
        "description": item.description,
        "category": item.category,
        "definition": item.definition,
        "status": item.status,
        "owner": item.owner,
    } for item in items]


@router.post("/landscape/concepts")
def create_business_concept(payload: BusinessConceptCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    item = BusinessConcept(
        organization_id=ctx["organization_id"],
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        category=payload.category,
        definition=payload.definition.strip() if payload.definition else None,
        status=payload.status or "PROPOSED",
        owner=payload.owner.strip() if payload.owner else None,
        created_by=ctx["user"].id,
    )
    db.add(item)
    db.commit(); db.refresh(item)
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "name": item.name,
        "description": item.description,
        "category": item.category,
        "definition": item.definition,
        "status": item.status,
        "owner": item.owner,
    }


@router.patch("/landscape/concepts/{concept_id}")
def update_business_concept(concept_id: int, payload: BusinessConceptUpdate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    item = db.get(BusinessConcept, concept_id)
    if not item or item.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Business concept not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        setattr(item, field, value)
    db.commit(); db.refresh(item)
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "name": item.name,
        "description": item.description,
        "category": item.category,
        "definition": item.definition,
        "status": item.status,
        "owner": item.owner,
    }


@router.delete("/landscape/concepts/{concept_id}")
def delete_business_concept(concept_id: int, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    item = db.get(BusinessConcept, concept_id)
    if not item or item.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Business concept not found")
    db.delete(item)
    db.commit()
    return {"success": True}


@router.get("/landscape/processes")
@router.get("/landscape/flows")
def list_business_flows(ctx=Depends(current_context), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    items = db.scalars(select(BusinessFlow).where(BusinessFlow.organization_id == org_id).order_by(BusinessFlow.name)).all()
    return [{
        "id": item.id,
        "organization_id": item.organization_id,
        "name": item.name,
        "description": item.description,
        "trigger": item.trigger,
        "frequency": item.frequency,
        "source_function_id": item.source_function_id,
        "target_function_id": item.target_function_id,
        "status": item.status,
    } for item in items]


@router.post("/landscape/processes")
@router.post("/landscape/flows")
def create_business_flow(payload: BusinessFlowCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    item = BusinessFlow(
        organization_id=ctx["organization_id"],
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        trigger=payload.trigger.strip() if payload.trigger else None,
        frequency=payload.frequency.strip() if payload.frequency else None,
        source_function_id=payload.source_function_id,
        target_function_id=payload.target_function_id,
        status=payload.status or "ACTIVE",
        created_by=ctx["user"].id,
    )
    db.add(item)
    db.commit(); db.refresh(item)
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "name": item.name,
        "description": item.description,
        "trigger": item.trigger,
        "frequency": item.frequency,
        "source_function_id": item.source_function_id,
        "target_function_id": item.target_function_id,
        "status": item.status,
    }


@router.patch("/landscape/processes/{flow_id}")
@router.patch("/landscape/flows/{flow_id}")
def update_business_flow(flow_id: int, payload: BusinessFlowUpdate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    item = db.get(BusinessFlow, flow_id)
    if not item or item.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Business flow not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        setattr(item, field, value)
    db.commit(); db.refresh(item)
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "name": item.name,
        "description": item.description,
        "trigger": item.trigger,
        "frequency": item.frequency,
        "source_function_id": item.source_function_id,
        "target_function_id": item.target_function_id,
        "status": item.status,
    }


@router.delete("/landscape/processes/{flow_id}")
@router.delete("/landscape/flows/{flow_id}")
def delete_business_flow(flow_id: int, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    item = db.get(BusinessFlow, flow_id)
    if not item or item.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Business process not found")
    db.delete(item)
    db.commit()
    return {"success": True}


@router.get("/landscape/systems")
def list_landscape_systems(ctx=Depends(current_context), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    items = db.scalars(select(LandscapeSystem).where(LandscapeSystem.organization_id == org_id).order_by(LandscapeSystem.name)).all()
    return [{
        "id": item.id,
        "organization_id": item.organization_id,
        "name": item.name,
        "description": item.description,
        "business_purpose": item.business_purpose,
        "vendor": item.vendor,
        "system_owner": item.system_owner,
        "lifecycle_status": item.lifecycle_status,
    } for item in items]


@router.post("/landscape/systems")
def create_landscape_system(payload: LandscapeSystemCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    item = LandscapeSystem(
        organization_id=ctx["organization_id"],
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        business_purpose=payload.business_purpose.strip() if payload.business_purpose else None,
        vendor=payload.vendor.strip() if payload.vendor else None,
        system_owner=payload.system_owner.strip() if payload.system_owner else None,
        lifecycle_status=payload.lifecycle_status or "ACTIVE",
        created_by=ctx["user"].id,
    )
    db.add(item)
    db.commit(); db.refresh(item)
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "name": item.name,
        "description": item.description,
        "business_purpose": item.business_purpose,
        "vendor": item.vendor,
        "system_owner": item.system_owner,
        "lifecycle_status": item.lifecycle_status,
    }


@router.patch("/landscape/systems/{system_id}")
def update_landscape_system(system_id: int, payload: LandscapeSystemUpdate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    item = db.get(LandscapeSystem, system_id)
    if not item or item.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Landscape system not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        setattr(item, field, value)
    db.commit(); db.refresh(item)
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "name": item.name,
        "description": item.description,
        "business_purpose": item.business_purpose,
        "vendor": item.vendor,
        "system_owner": item.system_owner,
        "lifecycle_status": item.lifecycle_status,
    }


@router.get("/discovery/sessions")
def list_discovery_sessions(ctx=Depends(current_context), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    sessions = db.scalars(
        select(DiscoverySession)
        .where(DiscoverySession.organization_id == org_id)
        .order_by(DiscoverySession.updated_at.desc())
    ).all()
    return [_serialize_discovery_session(session) for session in sessions]


@router.get("/discovery/sessions/{session_id}")
def get_discovery_session(session_id: int, ctx=Depends(current_context), db: Session = Depends(get_db)):
    session = db.get(DiscoverySession, session_id)
    if not session or session.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Discovery session not found")
    return _serialize_discovery_session(session)


@router.post("/discovery/sessions")
def create_discovery_session(payload: DiscoverySessionCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    session = DiscoverySession(
        organization_id=ctx["organization_id"],
        created_by=ctx["user"].id,
        title=payload.title.strip(),
        status=payload.status or "ACTIVE",
        summary=payload.summary.strip() if payload.summary else None,
        context_snapshot=payload.context_snapshot,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    db.add(DiscoveryProvenance(
        organization_id=ctx["organization_id"],
        entity_type="DiscoverySession",
        entity_id=session.id,
        action="CREATED",
        performed_by=ctx["user"].id,
        details={"title": session.title, "status": session.status},
    ))
    db.commit()
    db.refresh(session)
    return _serialize_discovery_session(session)


@router.patch("/discovery/sessions/{session_id}")
def update_discovery_session(session_id: int, payload: DiscoverySessionUpdate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    session = db.get(DiscoverySession, session_id)
    if not session or session.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Discovery session not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        setattr(session, field, value)

    if payload.status == "COMPLETED":
        session.completed_at = datetime.now(timezone.utc)
    elif payload.status and payload.status != "COMPLETED":
        session.completed_at = session.completed_at if session.completed_at else None

    session.updated_at = datetime.now(timezone.utc)
    db.add(DiscoveryProvenance(
        organization_id=ctx["organization_id"],
        entity_type="DiscoverySession",
        entity_id=session.id,
        action="UPDATED",
        performed_by=ctx["user"].id,
        details={"status": session.status, "summary": session.summary},
    ))
    db.commit()
    db.refresh(session)
    return _serialize_discovery_session(session)


@router.get("/discovery/sessions/{session_id}/evidence")
def list_session_evidence(session_id: int, ctx=Depends(current_context), db: Session = Depends(get_db)):
    session = db.get(DiscoverySession, session_id)
    if not session or session.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Discovery session not found")
    evidence = db.scalars(
        select(LandscapeEvidence)
        .where(LandscapeEvidence.organization_id == ctx["organization_id"], LandscapeEvidence.session_id == session_id)
        .order_by(LandscapeEvidence.created_at.desc())
    ).all()
    return [_serialize_landscape_evidence(item) for item in evidence]


@router.post("/discovery/sessions/{session_id}/evidence")
def create_session_evidence(session_id: int, payload: LandscapeEvidenceCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    session = db.get(DiscoverySession, session_id)
    if not session or session.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Discovery session not found")
    item = LandscapeEvidence(
        organization_id=ctx["organization_id"],
        session_id=session_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        evidence_type=payload.evidence_type,
        summary=payload.summary.strip() if payload.summary else None,
        details=payload.details,
        source=payload.source,
        created_by=ctx["user"].id,
    )
    db.add(item)
    db.flush()
    db.add(DiscoveryProvenance(
        organization_id=ctx["organization_id"],
        entity_type="LandscapeEvidence",
        entity_id=item.id,
        action="EVIDENCE_ADDED",
        performed_by=ctx["user"].id,
        details={"session_id": session_id, "entity_type": payload.entity_type, "evidence_type": payload.evidence_type},
    ))
    db.commit()
    db.refresh(item)
    return _serialize_landscape_evidence(item)


@router.get("/discovery/sessions/{session_id}/assertions")
def list_session_assertions(session_id: int, ctx=Depends(current_context), db: Session = Depends(get_db)):
    session = db.get(DiscoverySession, session_id)
    if not session or session.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Discovery session not found")
    assertions = db.scalars(
        select(LandscapeAssertion)
        .where(LandscapeAssertion.organization_id == ctx["organization_id"], LandscapeAssertion.session_id == session_id)
        .order_by(LandscapeAssertion.created_at.desc())
    ).all()
    return [_serialize_landscape_assertion(item) for item in assertions]


@router.post("/discovery/sessions/{session_id}/assertions")
def create_session_assertion(session_id: int, payload: LandscapeAssertionCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    session = db.get(DiscoverySession, session_id)
    if not session or session.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Discovery session not found")
    item = LandscapeAssertion(
        organization_id=ctx["organization_id"],
        session_id=session_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        assertion_type=payload.assertion_type,
        statement=payload.statement.strip(),
        confidence=payload.confidence,
        status=payload.status,
        created_by=ctx["user"].id,
    )
    db.add(item)
    db.flush()
    db.add(DiscoveryProvenance(
        organization_id=ctx["organization_id"],
        entity_type="LandscapeAssertion",
        entity_id=item.id,
        action="ASSERTION_ADDED",
        performed_by=ctx["user"].id,
        details={"session_id": session_id, "entity_type": payload.entity_type, "assertion_type": payload.assertion_type},
    ))
    db.commit()
    db.refresh(item)
    return _serialize_landscape_assertion(item)


@router.get("/discovery/sessions/{session_id}/summary")
def get_discovery_session_summary(session_id: int, ctx=Depends(current_context), db: Session = Depends(get_db)):
    session = db.get(DiscoverySession, session_id)
    if not session or session.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Discovery session not found")
    evidence = db.scalars(
        select(LandscapeEvidence)
        .where(LandscapeEvidence.organization_id == ctx["organization_id"], LandscapeEvidence.session_id == session_id)
        .order_by(LandscapeEvidence.created_at.desc())
    ).all()
    assertions = db.scalars(
        select(LandscapeAssertion)
        .where(LandscapeAssertion.organization_id == ctx["organization_id"], LandscapeAssertion.session_id == session_id)
        .order_by(LandscapeAssertion.created_at.desc())
    ).all()
    return {
        "id": session.id,
        "title": session.title,
        "status": session.status,
        "summary": session.summary,
        "evidence_count": len(evidence),
        "assertion_count": len(assertions),
        "evidence": [_serialize_landscape_evidence(item) for item in evidence],
        "assertions": [_serialize_landscape_assertion(item) for item in assertions],
    }


@router.get("/discovery/candidates")
def list_discovery_candidates(ctx=Depends(current_context), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    candidates = db.scalars(
        select(DiscoveryCandidate)
        .where(DiscoveryCandidate.organization_id == org_id)
        .order_by(DiscoveryCandidate.created_at.desc())
    ).all()
    return [_serialize_discovery_candidate(candidate) for candidate in candidates]


@router.post("/discovery/candidates")
def create_discovery_candidate(payload: DiscoveryCandidateCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    org_id = ctx["organization_id"]
    if payload.status in {DiscoveryCandidateStatus.CONFIRMED.value, DiscoveryCandidateStatus.REJECTED.value}:
        raise HTTPException(status_code=400, detail="Candidates must be created as suggested and confirmed or rejected explicitly by a human.")
    if payload.parent_candidate_id:
        parent = db.get(DiscoveryCandidate, payload.parent_candidate_id)
        if not parent or parent.organization_id != org_id:
            raise HTTPException(status_code=400, detail="Parent candidate does not belong to this organization")
    if payload.asset_id:
        asset = db.get(DataAsset, payload.asset_id)
        if not asset or asset.organization_id != org_id:
            raise HTTPException(status_code=400, detail="Asset does not belong to this organization")
    if payload.system_id:
        system = db.get(CatalogSystem, payload.system_id)
        if not system or system.organization_id != org_id:
            raise HTTPException(status_code=400, detail="System does not belong to this organization")
    if payload.resource_id:
        resource = db.get(DataResource, payload.resource_id)
        if not resource or resource.organization_id != org_id:
            raise HTTPException(status_code=400, detail="Resource does not belong to this organization")

    candidate = DiscoveryCandidate(
        organization_id=org_id,
        created_by=ctx["user"].id,
        name=payload.name.strip(),
        kind=payload.kind,
        summary=payload.summary.strip() if payload.summary else None,
        description=payload.description.strip() if payload.description else None,
        status=payload.status or DiscoveryCandidateStatus.SUGGESTED.value,
        source=payload.source,
        suggested_by_ai=bool(payload.suggested_by_ai),
        parent_candidate_id=payload.parent_candidate_id,
        asset_id=payload.asset_id,
        system_id=payload.system_id,
        resource_id=payload.resource_id,
        details=payload.details,
    )
    db.add(candidate)
    db.flush()
    db.add(DiscoveryProvenance(
        organization_id=org_id,
        entity_type="DiscoveryCandidate",
        entity_id=candidate.id,
        action="SUGGESTED",
        performed_by=ctx["user"].id,
        details={"name": candidate.name, "kind": candidate.kind, "source": candidate.source, "status": candidate.status},
    ))
    db.commit()
    db.refresh(candidate)
    return _serialize_discovery_candidate(candidate)


@router.patch("/discovery/candidates/{candidate_id}")
def update_discovery_candidate(candidate_id: int, payload: DiscoveryCandidateUpdate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    candidate = db.get(DiscoveryCandidate, candidate_id)
    if not candidate or candidate.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Discovery candidate not found")
    if payload.status in {DiscoveryCandidateStatus.CONFIRMED.value, DiscoveryCandidateStatus.REJECTED.value}:
        raise HTTPException(status_code=400, detail="Use the explicit confirm or reject action to change a candidate to confirmed or rejected.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        setattr(candidate, field, value)

    candidate.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(candidate)
    return _serialize_discovery_candidate(candidate)


@router.post("/discovery/candidates/{candidate_id}/confirm")
def confirm_discovery_candidate(candidate_id: int, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    candidate = db.get(DiscoveryCandidate, candidate_id)
    if not candidate or candidate.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Discovery candidate not found")
    if candidate.status == DiscoveryCandidateStatus.CONFIRMED.value:
        return _serialize_discovery_candidate(candidate)

    candidate.status = DiscoveryCandidateStatus.CONFIRMED.value
    candidate.confirmed_by = ctx["user"].id
    candidate.confirmed_at = datetime.now(timezone.utc)
    candidate.updated_at = candidate.confirmed_at
    db.add(DiscoveryProvenance(
        organization_id=ctx["organization_id"],
        entity_type="DiscoveryCandidate",
        entity_id=candidate.id,
        action="CONFIRMED",
        performed_by=ctx["user"].id,
        details={"name": candidate.name, "kind": candidate.kind, "source": candidate.source},
    ))
    db.commit()
    db.refresh(candidate)
    return _serialize_discovery_candidate(candidate)


@router.post("/discovery/candidates/{candidate_id}/reject")
def reject_discovery_candidate(candidate_id: int, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    candidate = db.get(DiscoveryCandidate, candidate_id)
    if not candidate or candidate.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Discovery candidate not found")
    if candidate.status == DiscoveryCandidateStatus.REJECTED.value:
        return _serialize_discovery_candidate(candidate)

    candidate.status = DiscoveryCandidateStatus.REJECTED.value
    candidate.rejected_by = ctx["user"].id
    candidate.rejected_at = datetime.now(timezone.utc)
    candidate.updated_at = candidate.rejected_at
    db.add(DiscoveryProvenance(
        organization_id=ctx["organization_id"],
        entity_type="DiscoveryCandidate",
        entity_id=candidate.id,
        action="REJECTED",
        performed_by=ctx["user"].id,
        details={"name": candidate.name, "kind": candidate.kind, "source": candidate.source},
    ))
    db.commit()
    db.refresh(candidate)
    return _serialize_discovery_candidate(candidate)


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
            TASK_PRIORITY_ORDER,
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
    if not task or task.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Task not found")

    # Readiness tasks are reconciled from the asset itself, so marking one
    # complete while the information is still missing was silently undone on the
    # next request. Say so instead of pretending it worked.
    if (task.source_type or "").upper() == "READINESS":
        asset = get_asset_for_org(db, task.asset_id, ctx["organization_id"])
        outstanding = {c["key"] for c in calculate_readiness(asset)["checks"] if not c["complete"]}
        if task.task_type in outstanding:
            raise HTTPException(
                status_code=400,
                detail=(
                    "This step completes itself once the information it asks for is "
                    "recorded. Add the missing information and it will clear automatically."
                ),
            )

    task.status = "COMPLETED"
    task.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"success": True}


@router.post("/tasks/{task_id}/expert-review")
def request_task_expert_review(task_id: int, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    task = db.get(StewardshipTask, task_id)
    if not task or task.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "NEEDS_EXPERT_REVIEW"
    task.completed_at = None
    db.commit()
    return {"success": True, "status": task.status}


@router.post("/tasks/{task_id}/resume")
def resume_task(task_id: int, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
    task = db.get(StewardshipTask, task_id)
    if not task or task.organization_id != ctx["organization_id"]:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "OPEN"
    task.completed_at = None
    db.commit()
    return {"success": True, "status": task.status}


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
    return {"engine_mode": settings.testgen_mode, "profiles": [{"overall_score": p.overall_score, "completeness_score": p.completeness_score, "validity_score": p.validity_score, "uniqueness_score": p.uniqueness_score, "consistency_score": p.consistency_score, "timeliness_score": p.timeliness_score, "row_count": p.row_count, "profiled_at": p.profiled_at, "source": p.source, "external_run_id": p.external_run_id} for p in profiles], "rules": result, "links": [{"id": x.id, "resource_id": x.resource_id, "provider": x.provider, "project_code": x.project_code, "connection_id": x.connection_id, "table_group_id": x.table_group_id, "test_suite_id": x.test_suite_id, "external_table_name": x.external_table_name, "source_mapping": _source_mapping_from_link(x), "sync_status": x.sync_status, "last_profiled_at": x.last_profiled_at, "last_tested_at": x.last_tested_at} for x in links], "issues": [{"id": i.id, "resource_id": i.resource_id, "rule_id": i.rule_id, "issue_type": i.issue_type, "title": i.title, "description": i.description, "severity": i.severity, "status": i.status, "failed_count": i.failed_count, "source": i.source, "external_run_id": i.external_run_id, "details": public_issue_details(i.details), "created_at": i.created_at} for i in issues]}


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
    # Connection details are operational information. Read-only roles get the
    # mode and nothing that describes where the engine lives.
    detailed = ctx["role"] in {"STEWARD", "APPROVER", "ORG_ADMIN", "ENTERPRISE_ADMIN"}
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
        "auth_mode": settings.testgen_auth_mode if (real and detailed) else None,
        "configured": (not real) or bool(settings.testgen_base_url and auth_configured),
        "base_url": settings.testgen_base_url if (real and detailed) else None,
        "project_code": settings.testgen_project_code if (real and detailed) else None,
        "table_group_id": settings.testgen_table_group_id if (real and detailed) else None,
        "test_suite_id": settings.testgen_test_suite_id if (real and detailed) else None,
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
def quality_issue_decision(issue_id: int, payload: QualityDecisionCreate, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN", "ENTERPRISE_ADMIN")), db: Session = Depends(get_db)):
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
        "details": public_issue_details(issue.details),
    }


@router.post("/assets/{asset_id}/submit")
def submit(asset_id: int, payload: SubmitRequest, ctx=Depends(require_roles("STEWARD", "ORG_ADMIN")), db: Session = Depends(get_db)):
    asset = get_asset_for_org(db, asset_id, ctx["organization_id"])
    submit_for_review(db, asset, ctx["user"].id, payload.comments)
    handoff_task = db.scalar(select(StewardshipTask).where(
        StewardshipTask.organization_id == ctx["organization_id"],
        StewardshipTask.asset_id == asset_id,
        StewardshipTask.task_type == "landscape_submit_for_review",
        StewardshipTask.status != "COMPLETED",
    ))
    if handoff_task:
        handoff_task.status = "COMPLETED"
        handoff_task.completed_at = datetime.now(timezone.utc)
    db.commit()
    return serialize_asset(get_asset_for_org(db, asset_id, ctx["organization_id"]))


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
