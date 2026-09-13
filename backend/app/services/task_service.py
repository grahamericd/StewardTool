from datetime import datetime, timezone
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import StewardshipReview, StewardshipTask
from .readiness import calculate_readiness
from .quality_orchestrator import reconcile_asset_quality_issues


TASK_TEXT = {
    "business_definition": ("CATALOG", "Explain what this information means", "Without a clear explanation, other people may interpret the information differently.", "Describe the information in plain business language."),
    "business_owner": ("OWNERSHIP", "Confirm who owns the business decisions", "Governance decisions need an accountable business authority.", "Identify the business function that can make decisions about use, meaning, and quality."),
    "data_steward": ("OWNERSHIP", "Confirm who coordinates stewardship", "A steward coordinates day-to-day governance activities.", "Identify the person or role responsible for maintaining this asset's governance information."),
    "has_resource": ("CATALOG", "Identify where the information lives", "People need to know the real places where this information exists.", "Identify at least one system, file, report, database, document collection, or other place where the information exists."),
    "theme": ("METADATA", "Confirm the business area", "A business area helps people browse and discover related information.", "Identify the part of the organization’s work this information supports."),
    "keywords": ("METADATA", "Add search terms", "Search terms make the information easier for coworkers to find.", "Add words colleagues would naturally search for."),
    "update_frequency": ("METADATA", "Confirm how this information changes", "Consumers need to know how current they can expect the information to be.", "Document how often the information changes or is refreshed."),
    "contact": ("METADATA", "Confirm who can answer questions", "Consumers need someone to contact when they have questions.", "Provide a person, role, or team that can answer business questions about this information."),
    "authoritative_source": ("GOVERNANCE", "Confirm the official source", "When the same information exists in multiple places, consumers need to know which source should be trusted for official decisions.", "Review the known locations and confirm which one the organization relies on as the official source."),
    "classification": ("CLASSIFICATION", "Review how this information should be handled", "Classification drives appropriate handling and access decisions.", "Review the information contained in the asset and record the appropriate classification."),
    "retention": ("LIFECYCLE", "Confirm how long this information should be kept", "Retention obligations determine how long information should be maintained.", "Record the retention period and source authority, or flag it for records-management review."),
    "quality": ("QUALITY", "Check whether this information can be trusted", "Information should be trustworthy enough for the way the organization uses it.", "Profile a structured resource and review the quality results and expectations."),
}


def _sync_periodic_review_task(db: Session, asset, existing_tasks):
    """Create a maintenance task only when a review is actually due."""
    now = datetime.now(timezone.utc)
    latest = None
    if getattr(asset, "reviews", None):
        latest = max(asset.reviews, key=lambda r: r.reviewed_at)

    # New information gets a full year before its first scheduled review.
    due_at = latest.next_review_due if latest else (asset.created_at + timedelta(days=365))
    task = next((t for t in existing_tasks if t.task_type == "periodic_review"), None)

    if due_at <= now:
        if not task:
            db.add(StewardshipTask(
                organization_id=asset.organization_id,
                asset_id=asset.id,
                task_type="periodic_review",
                governance_domain="MAINTENANCE",
                title="Review what has changed",
                why_it_matters=(
                    "Stewardship decisions can become outdated as business processes, "
                    "owners, systems, policies, and data quality change."
                ),
                recommended_action=(
                    "Complete a short review. AI Data Steward will reopen only the "
                    "areas that actually changed."
                ),
                priority="MEDIUM",
                source_type="PERIODIC_REVIEW",
                source_reference=due_at.date().isoformat(),
            ))
        elif task.status == "COMPLETED":
            task.status = "OPEN"
            task.completed_at = None
    elif task and task.status == "OPEN":
        task.status = "COMPLETED"
        task.completed_at = now


def sync_tasks(db: Session, asset, actor_id: int | None = None):
    reconcile_asset_quality_issues(db, asset)
    readiness = calculate_readiness(asset)
    existing = db.scalars(select(StewardshipTask).where(StewardshipTask.asset_id == asset.id)).all()
    _sync_periodic_review_task(db, asset, existing)
    by_type = {t.task_type: t for t in existing}

    for check in readiness["checks"]:
        key = check["key"]
        if key not in TASK_TEXT:
            continue
        domain, title, why, action = TASK_TEXT[key]
        task = by_type.get(key)
        if not check["complete"]:
            if not task:
                priority = "HIGH" if check["required"] else ("MEDIUM" if domain in {"QUALITY", "CLASSIFICATION", "OWNERSHIP"} else "LOW")
                db.add(StewardshipTask(
                    organization_id=asset.organization_id,
                    asset_id=asset.id,
                    task_type=key,
                    governance_domain=domain,
                    title=title,
                    why_it_matters=why,
                    recommended_action=action,
                    priority=priority,
                    source_type="READINESS",
                    source_reference=key,
                ))
            elif task.status == "COMPLETED":
                task.status = "OPEN"
                task.completed_at = None
        elif task and task.status != "COMPLETED":
            task.status = "COMPLETED"
            task.completed_at = datetime.now(timezone.utc)

    db.flush()
    return readiness
