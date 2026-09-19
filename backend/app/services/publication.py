import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import AssetPublication, AssetRelease, DataAsset, Organization, PublicationEvent, PublicationStatus
from .dcat_mapper import map_snapshot_to_dcat
from .publisher import get_publisher
from .readiness import calculate_readiness
from .snapshot import build_asset_snapshot


def now():
    return datetime.now(timezone.utc)


def get_or_create_publication(db: Session, asset: DataAsset) -> AssetPublication:
    publication = asset.publication
    if not publication:
        publication = AssetPublication(asset_id=asset.id, status=PublicationStatus.DRAFT.value)
        db.add(publication)
        db.flush()
        asset.publication = publication
    return publication


def record_event(db, publication, asset_id, event_type, actor_id, from_status=None, to_status=None, comments=None, event_metadata=None):
    db.add(PublicationEvent(
        asset_id=asset_id,
        publication_id=publication.id if publication else None,
        event_type=event_type,
        performed_by=actor_id,
        from_status=from_status,
        to_status=to_status,
        comments=comments,
        event_metadata=event_metadata,
    ))


def submit_for_review(db: Session, asset: DataAsset, actor_id: int, comments: str | None):
    publication = get_or_create_publication(db, asset)
    readiness = calculate_readiness(asset)
    publication.last_validation_at = now()
    publication.validation_errors = readiness["blocking"]
    if not readiness["ready_to_submit"]:
        # Keep the record of what was missing; raising first discarded it.
        db.commit()
        raise HTTPException(status_code=400, detail={"message": "Asset is not ready to submit.", "readiness": readiness})

    old = publication.status
    if old not in {"DRAFT", "NEEDS_UPDATE", "REJECTED"}:
        raise HTTPException(status_code=400, detail=f"Cannot submit from status {old}")
    publication.status = "IN_REVIEW"
    publication.submitted_by = actor_id
    publication.submitted_at = now()
    record_event(db, publication, asset.id, "SUBMITTED", actor_id, old, publication.status, comments)
    db.commit()
    return publication


def approve(db: Session, asset: DataAsset, actor_id: int, comments: str | None):
    publication = get_or_create_publication(db, asset)
    if publication.status != "IN_REVIEW":
        raise HTTPException(status_code=400, detail="Asset is not currently in review.")
    if publication.submitted_by == actor_id:
        raise HTTPException(status_code=400, detail="Submitter cannot approve their own asset.")

    old = publication.status
    publication.status = "APPROVED"
    publication.approved_by = actor_id
    publication.approved_at = now()

    version_number = db.scalar(select(func.coalesce(func.max(AssetRelease.version_number), 0)).where(AssetRelease.asset_id == asset.id)) + 1
    snapshot = build_asset_snapshot(asset)
    serialized = json.dumps(snapshot, sort_keys=True, default=str).encode("utf-8")
    snapshot_hash = hashlib.sha256(serialized).hexdigest()
    release = AssetRelease(
        asset_id=asset.id,
        version_number=version_number,
        snapshot=snapshot,
        snapshot_hash=snapshot_hash,
        approved_by=actor_id,
        approved_at=publication.approved_at,
    )
    db.add(release)
    record_event(db, publication, asset.id, "APPROVED", actor_id, old, publication.status, comments, {"version_number": version_number, "snapshot_hash": snapshot_hash})
    try:
        db.commit()
    except IntegrityError:
        # Two approvals raced for the same version number. Nothing is written.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Another approval completed first. Reload the asset and try again.",
        )
    return publication


def reject(db: Session, asset: DataAsset, actor_id: int, comments: str):
    publication = get_or_create_publication(db, asset)
    if publication.status != "IN_REVIEW":
        raise HTTPException(status_code=400, detail="Asset is not currently in review.")
    old = publication.status
    publication.status = "REJECTED"
    record_event(db, publication, asset.id, "RETURNED_FOR_CHANGES", actor_id, old, publication.status, comments)
    db.commit()
    return publication


def publish(db: Session, asset: DataAsset, actor_id: int):
    publication = get_or_create_publication(db, asset)
    if publication.status != "APPROVED":
        raise HTTPException(status_code=400, detail="Asset must be approved before publication.")

    release = db.scalar(select(AssetRelease).where(AssetRelease.asset_id == asset.id).order_by(AssetRelease.version_number.desc()).limit(1))
    if not release:
        raise HTTPException(status_code=500, detail="Approved release snapshot not found.")
    prior = db.scalar(select(AssetRelease).where(AssetRelease.asset_id == asset.id, AssetRelease.ckan_name.is_not(None)).order_by(AssetRelease.version_number.desc()).limit(1))
    org = db.get(Organization, asset.organization_id)
    dcat_payload = map_snapshot_to_dcat(release.snapshot, org.name)
    result = get_publisher().publish(
        release_id=release.id,
        snapshot=release.snapshot,
        dcat_payload=dcat_payload,
        existing_ckan_name=prior.ckan_name if prior and prior.id != release.id else None,
    )

    old = publication.status
    publication.status = "PUBLISHED"
    publication.published_at = now()
    release.published_at = publication.published_at
    release.ckan_dataset_id = result["ckan_dataset_id"]
    release.ckan_name = result["ckan_name"]
    release.publication_result = {**result, "dcat_payload": dcat_payload}
    record_event(db, publication, asset.id, "PUBLISHED", actor_id, old, publication.status, event_metadata={"release_id": release.id, "ckan_name": release.ckan_name})
    db.commit()
    return publication


def mark_needs_update_if_published(db: Session, asset: DataAsset, actor_id: int, reason: str):
    publication = get_or_create_publication(db, asset)
    if publication.status == "PUBLISHED":
        old = publication.status
        publication.status = "NEEDS_UPDATE"
        record_event(db, publication, asset.id, "UPDATED_AFTER_PUBLICATION", actor_id, old, publication.status, event_metadata={"reason": reason})
