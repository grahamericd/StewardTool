from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from ..auth import current_context, require_roles
from ..db import get_db
from ..models import *
from ..services.snapshot import build_asset_snapshot
from ..services.readiness import calculate_readiness
from ..services import publication as pubsvc

router=APIRouter()
def aq(): return select(DataAsset).options(selectinload(DataAsset.resources).selectinload(AssetResource.resource).selectinload(DataResource.system),selectinload(DataAsset.metadata_items),selectinload(DataAsset.publication))
def getasset(db,id,org):
    a=db.scalar(aq().where(DataAsset.id==id,DataAsset.organization_id==org))
    if not a: raise HTTPException(404,'Data asset not found')
    return a
def serialize(a):
    s=build_asset_snapshot(a); p=a.publication
    return {**s,'readiness':calculate_readiness(a),'publication':{'status':p.status if p else 'DRAFT','submitted_at':p.submitted_at if p else None,'approved_at':p.approved_at if p else None,'published_at':p.published_at if p else None}}

@router.get('/me')
def me(ctx=Depends(current_context),db:Session=Depends(get_db)):
    o=db.get(Organization,ctx['organization_id']); return {'user':{'id':ctx['user'].id,'email':ctx['user'].email,'display_name':ctx['user'].display_name},'organization':{'id':o.id,'code':o.code,'name':o.name},'role':ctx['role']}
@router.get('/systems')
def systems(ctx=Depends(current_context),db:Session=Depends(get_db)): return db.scalars(select(CatalogSystem).where(CatalogSystem.organization_id==ctx['organization_id']).order_by(CatalogSystem.name)).all()
@router.get('/assets')
def assets(ctx=Depends(current_context),db:Session=Depends(get_db)): return [serialize(a) for a in db.scalars(aq().where(DataAsset.organization_id==ctx['organization_id']).order_by(DataAsset.name)).all()]
@router.get('/dashboard')
def dash(ctx=Depends(current_context),db:Session=Depends(get_db)):
    ss=db.scalars(select(CatalogSystem).where(CatalogSystem.organization_id==ctx['organization_id'])).all(); aa=db.scalars(aq().where(DataAsset.organization_id==ctx['organization_id'])).all(); rr=[l for a in aa for l in a.resources]; st={}
    for a in aa: st[a.publication.status if a.publication else 'DRAFT']=st.get(a.publication.status if a.publication else 'DRAFT',0)+1
    return {'systems':len(ss),'assets':len(aa),'resources':len(rr),'unstructured_resources':sum(1 for l in rr if l.resource.structure_type=='UNSTRUCTURED'),'assets_needing_attention':sum(1 for a in aa if calculate_readiness(a)['score']<80),'publication_status':st}
@router.post('/systems')
def add_system(p:dict,ctx=Depends(require_roles('STEWARD','ORG_ADMIN','ENTERPRISE_ADMIN')),db:Session=Depends(get_db)):
    s=CatalogSystem(organization_id=ctx['organization_id'],name=p['name'],business_purpose=p.get('business_purpose'),vendor=p.get('vendor'),system_owner=p.get('system_owner'),created_by=ctx['user'].id); db.add(s); db.commit(); db.refresh(s); return s
@router.post('/assets')
def add_asset(p:dict,ctx=Depends(require_roles('STEWARD','ORG_ADMIN','ENTERPRISE_ADMIN')),db:Session=Depends(get_db)):
    a=DataAsset(organization_id=ctx['organization_id'],name=p['name'],business_definition=p.get('business_definition'),business_domain=p.get('business_domain'),business_owner=p.get('business_owner'),data_steward=p.get('data_steward'),created_by=ctx['user'].id); db.add(a); db.flush(); db.add(AssetPublication(asset_id=a.id,status='DRAFT')); db.commit(); return serialize(getasset(db,a.id,ctx['organization_id']))
@router.post('/assets/{asset_id}/resources')
def add_resource(asset_id:int,p:dict,ctx=Depends(require_roles('STEWARD','ORG_ADMIN','ENTERPRISE_ADMIN')),db:Session=Depends(get_db)):
    a=getasset(db,asset_id,ctx['organization_id']); sid=p.get('system_id')
    if sid:
        s=db.get(CatalogSystem,sid)
        if not s or s.organization_id!=ctx['organization_id']: raise HTTPException(400,'System does not belong to organization')
    r=DataResource(organization_id=ctx['organization_id'],system_id=sid,name=p['name'],resource_type=p['resource_type'],structure_type=p['structure_type'],description=p.get('description'),location_reference=p.get('location_reference'),format=p.get('format'),media_type=p.get('media_type'),created_by=ctx['user'].id); db.add(r); db.flush(); db.add(AssetResource(asset_id=a.id,resource_id=r.id,relationship_type=p.get('relationship_type','REPRESENTATION'),is_authoritative=p.get('is_authoritative',False))); pubsvc.mark_changed(db,a,ctx['user'].id,'Resource changed'); db.commit(); return serialize(getasset(db,asset_id,ctx['organization_id']))
@router.put('/assets/{asset_id}/metadata')
def metadata(asset_id:int,p:dict,ctx=Depends(require_roles('STEWARD','ORG_ADMIN','ENTERPRISE_ADMIN')),db:Session=Depends(get_db)):
    a=getasset(db,asset_id,ctx['organization_id']); key=p['metadata_key']; val=p['metadata_value']; existing=db.scalars(select(AssetMetadata).where(AssetMetadata.asset_id==a.id,AssetMetadata.metadata_key==key)).all()
    for x in existing: db.delete(x)
    vals=val if key=='keyword' and isinstance(val,list) else [val]
    for v in vals: db.add(AssetMetadata(asset_id=a.id,metadata_key=key,metadata_value=v,metadata_source=p.get('metadata_source','USER'),review_status=p.get('review_status','APPROVED'),created_by=ctx['user'].id))
    pubsvc.mark_changed(db,a,ctx['user'].id,f'Metadata changed: {key}'); db.commit(); return serialize(getasset(db,asset_id,ctx['organization_id']))
@router.post('/assets/{asset_id}/submit')
def submit(asset_id:int,p:dict|None=None,ctx=Depends(require_roles('STEWARD','ORG_ADMIN')),db:Session=Depends(get_db)):
    a=getasset(db,asset_id,ctx['organization_id']); pubsvc.submit(db,a,ctx['user'].id,(p or {}).get('comments')); return serialize(getasset(db,asset_id,ctx['organization_id']))
@router.post('/assets/{asset_id}/approve')
def approve(asset_id:int,p:dict|None=None,ctx=Depends(require_roles('APPROVER','ORG_ADMIN','ENTERPRISE_ADMIN')),db:Session=Depends(get_db)):
    a=getasset(db,asset_id,ctx['organization_id']); pubsvc.approve(db,a,ctx['user'].id,(p or {}).get('comments')); return serialize(getasset(db,asset_id,ctx['organization_id']))
@router.post('/assets/{asset_id}/reject')
def reject(asset_id:int,p:dict,ctx=Depends(require_roles('APPROVER','ORG_ADMIN','ENTERPRISE_ADMIN')),db:Session=Depends(get_db)):
    a=getasset(db,asset_id,ctx['organization_id']); pubsvc.reject(db,a,ctx['user'].id,p.get('comments','Returned for changes')); return serialize(getasset(db,asset_id,ctx['organization_id']))
@router.post('/assets/{asset_id}/publish')
def publish(asset_id:int,ctx=Depends(require_roles('APPROVER','ORG_ADMIN','ENTERPRISE_ADMIN')),db:Session=Depends(get_db)):
    a=getasset(db,asset_id,ctx['organization_id']); pubsvc.publish(db,a,ctx['user'].id); return serialize(getasset(db,asset_id,ctx['organization_id']))
@router.get('/assets/{asset_id}/history')
def history(asset_id:int,ctx=Depends(current_context),db:Session=Depends(get_db)):
    a=getasset(db,asset_id,ctx['organization_id']); ev=db.scalars(select(PublicationEvent).where(PublicationEvent.asset_id==a.id).order_by(PublicationEvent.created_at.desc())).all(); rel=db.scalars(select(AssetRelease).where(AssetRelease.asset_id==a.id).order_by(AssetRelease.version_number.desc())).all(); return {'events':[{'id':e.id,'event_type':e.event_type,'from_status':e.from_status,'to_status':e.to_status,'comments':e.comments,'event_metadata':e.event_metadata,'created_at':e.created_at} for e in ev],'releases':[{'id':r.id,'version_number':r.version_number,'snapshot_hash':r.snapshot_hash,'approved_at':r.approved_at,'published_at':r.published_at,'ckan_dataset_id':r.ckan_dataset_id,'ckan_name':r.ckan_name,'publication_result':r.publication_result,'snapshot':r.snapshot} for r in rel]}
