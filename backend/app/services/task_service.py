from datetime import datetime, timezone
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import StewardshipReview, StewardshipTask
from .readiness import calculate_readiness
from .quality_orchestrator import reconcile_asset_quality_issues


TASK_TEXT = {
    "business_definition": ("CATALOG", "Document the business definition", "Without a clear definition, other users may interpret the asset differently.", "Describe the information in plain business language."),
    "business_owner": ("OWNERSHIP", "Identify the business owner", "Governance decisions need an accountable business authority.", "Identify the business function that can make decisions about use, meaning, and quality."),
    "data_steward": ("OWNERSHIP", "Assign a data steward", "A steward coordinates day-to-day governance activities.", "Identify the person or role responsible for maintaining this asset's governance information."),
    "has_resource": ("CATALOG", "Identify where the information lives", "The catalog should connect the business asset to its real technical or document representations.", "Add at least one database, file, API, PDF collection, spreadsheet, or document library."),
    "theme": ("METADATA", "Choose a business area", "A business area helps people browse and discover related information.", "Select the business domain that best describes the asset."),
    "keywords": ("METADATA", "Add search terms", "Search terms make the asset easier to find in the enterprise catalog.", "Add words colleagues would naturally search for."),
    "update_frequency": ("METADATA", "Document update frequency", "Consumers need to know how current they can expect the information to be.", "Document how often the information changes or is refreshed."),
    "contact": ("METADATA", "Add a contact point", "Consumers need someone to contact when they have questions.", "Provide a person, role, or mailbox for questions about this asset."),
    "authoritative_source": ("GOVERNANCE", "Confirm the authoritative source", "When the same information exists in multiple places, consumers need to know which source should be trusted for official decisions.", "Review the linked resources and identify the authoritative representation."),
    "classification": ("CLASSIFICATION", "Review information classification", "Classification drives appropriate handling and access decisions.", "Review the information contained in the asset and record the appropriate classification."),
    "retention": ("LIFECYCLE", "Document retention requirements", "Retention obligations determine how long information should be maintained.", "Record the retention period and source authority, or flag it for records-management review."),
    "quality": ("QUALITY", "Assess data quality", "Cataloged data should be trustworthy enough for its intended use.", "Profile a structured resource and review the quality results and expectations."),
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
