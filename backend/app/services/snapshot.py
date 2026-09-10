from collections import defaultdict

def build_asset_snapshot(asset):
    md=defaultdict(list)
    for i in asset.metadata_items:
        if i.review_status=='APPROVED': md[i.metadata_key].append(i.metadata_value)
    normalized={k:(v if len(v)>1 else v[0]) for k,v in md.items()}
    resources=[]
    for link in asset.resources:
        r=link.resource
        resources.append({"resource_id":r.id,"name":r.name,"resource_type":r.resource_type,"structure_type":r.structure_type,"description":r.description,"location_reference":r.location_reference,"format":r.format,"media_type":r.media_type,"relationship_type":link.relationship_type,"is_authoritative":link.is_authoritative,"system":r.system.name if r.system else None})
    return {"asset":{"asset_id":asset.id,"asset_identifier":asset.asset_identifier,"organization_id":asset.organization_id,"name":asset.name,"business_definition":asset.business_definition,"business_domain":asset.business_domain,"business_owner":asset.business_owner,"data_steward":asset.data_steward,"authoritative_status":asset.authoritative_status,"asset_status":asset.asset_status},"metadata":normalized,"resources":resources}
