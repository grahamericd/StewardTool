def map_snapshot_to_dcat(snapshot, organization_name):
    a=snapshot['asset']; md=snapshot.get('metadata',{}); resources=snapshot.get('resources',[])
    uri=f"urn:ai-data-steward:dataset:{a['asset_identifier']}"
    ds={'@id':uri,'@type':'dcat:Dataset','dct:title':a['name'],'dct:description':a.get('business_definition') or '','dct:publisher':{'@type':'foaf:Agent','foaf:name':organization_name}}
    if md.get('theme'): ds['dcat:theme']=md['theme']
    if md.get('keyword'): ds['dcat:keyword']=md['keyword']
    if md.get('update_frequency'): ds['dct:accrualPeriodicity']=md['update_frequency']
    if md.get('contact'): ds['dcat:contactPoint']=md['contact']
    dists=[]; services=[]
    for r in resources:
        base={'@id':f"urn:ai-data-steward:resource:{r['resource_id']}",'dct:title':r['name']}
        if r.get('location_reference'): base['dcat:accessURL']=r['location_reference']
        if r.get('format'): base['dct:format']=r['format']
        if r.get('media_type'): base['dcat:mediaType']=r['media_type']
        if r['resource_type']=='API': services.append({**base,'@type':'dcat:DataService','dcat:servesDataset':{'@id':uri}})
        else: dists.append({**base,'@type':'dcat:Distribution'})
    if dists: ds['dcat:distribution']=dists
    return {'@context':{'dcat':'http://www.w3.org/ns/dcat#','dct':'http://purl.org/dc/terms/','foaf':'http://xmlns.com/foaf/0.1/'},'@graph':[ds]+services}
