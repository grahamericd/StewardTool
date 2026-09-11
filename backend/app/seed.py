from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AppUser, AssetMetadata, AssetPublication, AssetResource, CatalogSystem, DataAsset, DataResource,
    GovernanceRequirement, Organization, OrganizationMembership, QualityProfile, QualityResult, QualityRule,
)
from .services.task_service import sync_tasks


DEMO_USERS = [
    ("steward@demo.gov", "Demo Steward", "STEWARD"),
    ("approver@demo.gov", "Demo Approver", "APPROVER"),
    ("admin@demo.gov", "Organization Admin", "ORG_ADMIN"),
    ("enterprise@demo.gov", "Enterprise Admin", "ENTERPRISE_ADMIN"),
]


def seed(db: Session):
    org = db.scalar(select(Organization).where(Organization.code == "DEMO"))
    if not org:
        org = Organization(code="DEMO", name="Department of Professional Regulation", description="Stage 3 demonstration organization")
        db.add(org); db.flush()

    users = {}
    for email, name, role in DEMO_USERS:
        user = db.scalar(select(AppUser).where(AppUser.email == email))
        if not user:
            user = AppUser(email=email, display_name=name)
            db.add(user); db.flush()
        users[email] = user
        membership = db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == user.id, OrganizationMembership.organization_id == org.id))
        if not membership:
            db.add(OrganizationMembership(user_id=user.id, organization_id=org.id, role=role))
    db.flush()

    for key, title, domain, required in [
        ("business_definition", "Business definition", "CATALOG", True),
        ("business_owner", "Business owner", "OWNERSHIP", True),
        ("has_resource", "At least one resource", "CATALOG", True),
        ("theme", "Business area", "METADATA", True),
        ("authoritative_source", "Authoritative source", "GOVERNANCE", True),
        ("classification", "Classification", "CLASSIFICATION", False),
        ("quality", "Quality assessment", "QUALITY", False),
    ]:
        if not db.scalar(select(GovernanceRequirement).where(GovernanceRequirement.organization_id == org.id, GovernanceRequirement.requirement_key == key)):
            db.add(GovernanceRequirement(organization_id=org.id, requirement_key=key, title=title, description=title, domain=domain, required_for_submission=required))

    def ensure_system(name, purpose, vendor):
        system = db.scalar(select(CatalogSystem).where(CatalogSystem.organization_id == org.id, CatalogSystem.name == name))
        if not system:
            system = CatalogSystem(organization_id=org.id, name=name, business_purpose=purpose, vendor=vendor, system_owner="Licensing Division", created_by=users["steward@demo.gov"].id)
            db.add(system); db.flush()
        return system

    system = ensure_system("Business Licensing System", "Manages professional licenses, applications, payments, disciplinary actions, and uploaded documents.", "Custom")
    sharepoint = ensure_system("SharePoint", "Stores submitted applications, supporting documents, correspondence, and reports.", "Microsoft")

    application = db.scalar(select(DataAsset).where(DataAsset.organization_id == org.id, DataAsset.name == "Application"))
    if not application:
        application = DataAsset(
            organization_id=org.id,
            name="Application",
            business_definition="Information submitted by an individual or organization requesting a professional license or related agency action.",
            business_domain="Professional Licensing",
            business_owner="Licensing Division",
            data_steward=None,
            classification=None,
            created_by=users["steward@demo.gov"].id,
        )
        db.add(application); db.flush()
        db.add(AssetPublication(asset_id=application.id, status="DRAFT"))

        table = DataResource(organization_id=org.id, system_id=system.id, name="APPLICATION", resource_type="DATABASE_TABLE", structure_type="STRUCTURED", description="Primary structured application record.", location_reference="https://example.gov/data/application", format="Database table", created_by=users["steward@demo.gov"].id)
        pdfs = DataResource(organization_id=org.id, system_id=sharepoint.id, name="Submitted License Applications", resource_type="PDF_COLLECTION", structure_type="UNSTRUCTURED", description="Uploaded PDF applications and supporting documents.", location_reference="https://example.gov/sharepoint/submitted-applications", format="PDF", media_type="application/pdf", created_by=users["steward@demo.gov"].id)
        db.add_all([table, pdfs]); db.flush()
        db.add_all([
            AssetResource(asset_id=application.id, resource_id=table.id, is_authoritative=True),
            AssetResource(asset_id=application.id, resource_id=pdfs.id, is_authoritative=False),
        ])
        for key, value in [
            ("theme", "Professional Licensing"),
            ("keyword", "application"),
            ("keyword", "professional license"),
            ("update_frequency", "Continuous"),
            ("contact", {"name": "Licensing Data Steward", "email": "licensing@example.gov"}),
        ]:
            db.add(AssetMetadata(asset_id=application.id, metadata_key=key, metadata_value=value, metadata_source="USER", review_status="APPROVED", created_by=users["steward@demo.gov"].id, reviewed_by=users["steward@demo.gov"].id))
        db.flush()

        profile = QualityProfile(
            asset_id=application.id, resource_id=table.id, overall_score=91.4,
            completeness_score=98.2, validity_score=93.1, uniqueness_score=99.8,
            consistency_score=88.4, timeliness_score=77.5, row_count=125440,
            source="TESTGEN_BASELINE",
        )
        db.add(profile)
        rule = QualityRule(
            asset_id=application.id, resource_id=table.id, rule_name="Application ID is required",
            rule_type="not_null", plain_language_rule="Every application should have an Application ID.",
            rule_definition={"type": "not_null", "column": "application_id"}, status="APPROVED",
            created_by=users["steward@demo.gov"].id,
        )
        db.add(rule); db.flush()
        db.add(QualityResult(rule_id=rule.id, result_status="FAIL", evaluated_count=125440, failed_count=248, score=99.8, details={"message": "248 records are missing Application ID."}, source="TESTGEN_BASELINE"))

    db.flush()
    sync_tasks(db, application, users["steward@demo.gov"].id)
    db.commit()
