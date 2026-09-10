import hashlib, json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import func, select
from .snapshot import build_asset_snapshot
from .readiness import calculate_readiness
from .dcat_mapper import map_snapshot_to_dcat
from .publisher import MockCKANPublisher
from ..models import AssetPublication, AssetRelease, Organization, PublicationEvent

def now(): return datetime.now(timezone.utc)
def event(db,asset_id,event_type,actor,from_status=None,to_status=None,comments=None,meta=None): db.add(PublicationEvent(asset_id=asset_id,event_type=event_type,performed_by=actor,from_status=from_status,to_status=to_status,comments=comments,event_metadata=meta))
def getpub(db,asset):
    if asset.publication: return asset.publication
    p=AssetPublication(asset_id=asset.id,status='DRAFT'); db.add(p); db.flush(); return p

def submit(db,asset,actor,comments=None):
    p=getpub(db,asset); r=calculate_readiness(asset); p.validation_errors=r['missing']
    if not r['ready_to_submit']: raise HTTPException(400,{"message":"Asset is not ready to submit","readiness":r})
    if p.status not in {'DRAFT','NEEDS_UPDATE','REJECTED'}: raise HTTPException(400,f'Cannot submit from {p.status}')
    old=p.status; p.status='IN_REVIEW'; p.submitted_by=actor; p.submitted_at=now(); event(db,asset.id,'SUBMITTED',actor,old,p.status,comments); db.commit()

def approve(db,asset,actor,comments=None):
    p=getpub(db,asset)
    if p.status!='IN_REVIEW': raise HTTPException(400,'Asset is not in review')
    if p.submitted_by==actor: raise HTTPException(400,'Submitter cannot approve own asset')
    old=p.status; p.status='APPROVED'; p.approved_by=actor; p.approved_at=now()
    v=db.scalar(select(func.coalesce(func.max(AssetRelease.version_number),0)).where(AssetRelease.asset_id==asset.id))+1
    snap=build_asset_snapshot(asset); h=hashlib.sha256(json.dumps(snap,sort_keys=True,default=str).encode()).hexdigest()
    db.add(AssetRelease(asset_id=asset.id,version_number=v,snapshot=snap,snapshot_hash=h,approved_by=actor,approved_at=p.approved_at))
    event(db,asset.id,'APPROVED',actor,old,p.status,comments,{"version":v,"snapshot_hash":h}); db.commit()

def reject(db,asset,actor,comments):
    p=getpub(db,asset)
    if p.status!='IN_REVIEW': raise HTTPException(400,'Asset is not in review')
    old=p.status; p.status='REJECTED'; event(db,asset.id,'RETURNED_FOR_CHANGES',actor,old,p.status,comments); db.commit()

def publish(db,asset,actor):
    p=getpub(db,asset)
    if p.status!='APPROVED': raise HTTPException(400,'Asset must be approved first')
    rel=db.scalar(select(AssetRelease).where(AssetRelease.asset_id==asset.id).order_by(AssetRelease.version_number.desc()).limit(1))
    org=db.get(Organization,asset.organization_id); dcat=map_snapshot_to_dcat(rel.snapshot,org.name); result=MockCKANPublisher().publish(rel.id,dcat)
    old=p.status; p.status='PUBLISHED'; p.published_at=now(); rel.published_at=p.published_at; rel.ckan_dataset_id=result['ckan_dataset_id']; rel.ckan_name=result['ckan_name']; rel.publication_result={**result,'dcat_payload':dcat}; event(db,asset.id,'PUBLISHED',actor,old,p.status,meta={"release":rel.id}); db.commit()

def mark_changed(db,asset,actor,reason):
    p=getpub(db,asset)
    if p.status=='PUBLISHED':
        old=p.status; p.status='NEEDS_UPDATE'; event(db,asset.id,'UPDATED_AFTER_PUBLICATION',actor,old,p.status,meta={"reason":reason})
