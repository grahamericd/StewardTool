from sqlalchemy import select
from .models import *

def seed(db):
    org=db.scalar(select(Organization).where(Organization.code=='DEMO'))
    if not org: org=Organization(code='DEMO',name='Department of Professional Regulation',description='Stage 1 demo organization'); db.add(org); db.flush()
    roles=[('steward@demo.gov','Demo Steward','STEWARD'),('approver@demo.gov','Demo Approver','APPROVER'),('admin@demo.gov','Organization Admin','ORG_ADMIN'),('enterprise@demo.gov','Enterprise Admin','ENTERPRISE_ADMIN')]
    users={}
    for email,name,role in roles:
        u=db.scalar(select(AppUser).where(AppUser.email==email))
        if not u: u=AppUser(email=email,display_name=name); db.add(u); db.flush()
        users[email]=u
        m=db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id==u.id,OrganizationMembership.organization_id==org.id))
        if not m: db.add(OrganizationMembership(user_id=u.id,organization_id=org.id,role=role))
    db.flush()
    sys=db.scalar(select(CatalogSystem).where(CatalogSystem.organization_id==org.id,CatalogSystem.name=='Business Licensing System'))
    if not sys: sys=CatalogSystem(organization_id=org.id,name='Business Licensing System',business_purpose='Manages professional licenses, applications, payments, disciplinary actions, and uploaded documents.',vendor='Custom',system_owner='Licensing Division',created_by=users['steward@demo.gov'].id); db.add(sys); db.flush()
    sp=db.scalar(select(CatalogSystem).where(CatalogSystem.organization_id==org.id,CatalogSystem.name=='SharePoint'))
    if not sp: sp=CatalogSystem(organization_id=org.id,name='SharePoint',business_purpose='Stores submitted applications, supporting documents, correspondence, and reports.',vendor='Microsoft',system_owner='Licensing Division',created_by=users['steward@demo.gov'].id); db.add(sp); db.flush()
    a=db.scalar(select(DataAsset).where(DataAsset.organization_id==org.id,DataAsset.name=='Application'))
    if not a:
        a=DataAsset(organization_id=org.id,name='Application',business_definition='Information submitted by an individual or organization requesting a professional license or related agency action.',business_domain='Professional Licensing',business_owner='Licensing Division',created_by=users['steward@demo.gov'].id); db.add(a); db.flush(); db.add(AssetPublication(asset_id=a.id,status='DRAFT'))
        table=DataResource(organization_id=org.id,system_id=sys.id,name='APPLICATION',resource_type='DATABASE_TABLE',structure_type='STRUCTURED',description='Primary structured application record.',location_reference='demo://business-licensing/application',format='Database table'); pdf=DataResource(organization_id=org.id,system_id=sp.id,name='Submitted License Applications',resource_type='PDF_COLLECTION',structure_type='UNSTRUCTURED',description='Uploaded PDF applications and supporting documents.',location_reference='demo://sharepoint/submitted-applications',format='PDF',media_type='application/pdf'); db.add_all([table,pdf]); db.flush(); db.add_all([AssetResource(asset_id=a.id,resource_id=table.id,is_authoritative=True),AssetResource(asset_id=a.id,resource_id=pdf.id)])
        for k,v in [('theme','Professional Licensing'),('keyword','application'),('keyword','professional license'),('update_frequency','Continuous'),('contact',{'name':'Licensing Data Steward','email':'licensing@example.gov'})]: db.add(AssetMetadata(asset_id=a.id,metadata_key=k,metadata_value=v,review_status='APPROVED',created_by=users['steward@demo.gov'].id))
    db.commit()
