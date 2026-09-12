from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AppUser, AssetMetadata, AssetPublication, AssetResource, CatalogSystem, DataAsset, DataResource,
    GovernanceRequirement, Organization, OrganizationMembership, QualityEngineResource, QualityIssue,
    QualityProfile, QualityResult, QualityRule, StewardshipTask,
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

    # Stage 3.5.1: give the validated Florida Corporate Data source its own
    # business catalog context rather than borrowing the demo Application asset.
    corporate_system = db.scalar(
        select(CatalogSystem).where(
            CatalogSystem.organization_id == org.id,
            CatalogSystem.name == "Sunbiz Corporate Registry",
        )
    )
    if not corporate_system:
        corporate_system = CatalogSystem(
            organization_id=org.id,
            name="Sunbiz Corporate Registry",
            business_purpose=(
                "Maintains Florida corporate registration and filing information "
                "published by the Division of Corporations."
            ),
            vendor="Florida Department of State",
            system_owner="Division of Corporations",
            created_by=users["steward@demo.gov"].id,
        )
        db.add(corporate_system)
        db.flush()

    corporate_asset = db.scalar(
        select(DataAsset).where(
            DataAsset.organization_id == org.id,
            DataAsset.name == "Corporate Filings",
        )
    )
    if not corporate_asset:
        corporate_asset = DataAsset(
            organization_id=org.id,
            name="Corporate Filings",
            business_definition=(
                "Information describing corporations and related filing records "
                "registered with the Florida Division of Corporations."
            ),
            business_domain="Business Registration",
            business_owner="Division of Corporations",
            data_steward="Division of Corporations Data Steward",
            classification=None,
            created_by=users["steward@demo.gov"].id,
        )
        db.add(corporate_asset)
        db.flush()
        db.add(AssetPublication(asset_id=corporate_asset.id, status="DRAFT"))

        for key, value in [
            ("theme", "Business Registration"),
            ("keyword", "corporate filings"),
            ("keyword", "corporations"),
            ("keyword", "Sunbiz"),
            ("update_frequency", "Quarterly data extract"),
            (
                "contact",
                {
                    "name": "Division of Corporations Data Steward",
                    "email": "data.steward@example.gov",
                },
            ),
        ]:
            db.add(
                AssetMetadata(
                    asset_id=corporate_asset.id,
                    metadata_key=key,
                    metadata_value=value,
                    metadata_source="USER",
                    review_status="APPROVED",
                    created_by=users["steward@demo.gov"].id,
                    reviewed_by=users["steward@demo.gov"].id,
                )
            )

    corporate_resource = db.scalar(
        select(DataResource).where(
            DataResource.organization_id == org.id,
            DataResource.system_id == corporate_system.id,
            DataResource.name == "Corporate Registry Data",
        )
    )
    if not corporate_resource:
        corporate_resource = DataResource(
            organization_id=org.id,
            system_id=corporate_system.id,
            name="Corporate Registry Data",
            resource_type="DATABASE_TABLE",
            structure_type="STRUCTURED",
            description=(
                "Structured corporate registration records loaded into the "
                "Florida Data Lab from the Division of Corporations data extract."
            ),
            location_reference="florida_data_lab.raw.corporate_data",
            format="PostgreSQL table",
            media_type="application/sql",
            created_by=users["steward@demo.gov"].id,
        )
        db.add(corporate_resource)
        db.flush()

    if not db.scalar(
        select(AssetResource).where(
            AssetResource.asset_id == corporate_asset.id,
            AssetResource.resource_id == corporate_resource.id,
        )
    ):
        db.add(
            AssetResource(
                asset_id=corporate_asset.id,
                resource_id=corporate_resource.id,
                is_authoritative=True,
            )
        )
        db.flush()

    corporate_table_group_id = "8e516582-c3af-4f5e-81ad-35bdbcd55f83"
    corporate_test_suite_id = "b025efd2-da4c-4384-9578-9a28f0f8cf2f"

    existing_corporate_engine = db.scalar(
        select(QualityEngineResource).where(
            QualityEngineResource.resource_id == corporate_resource.id,
            QualityEngineResource.provider == "TESTGEN",
        )
    )

    misplaced_engine = db.scalar(
        select(QualityEngineResource).where(
            QualityEngineResource.provider == "TESTGEN",
            QualityEngineResource.table_group_id == corporate_table_group_id,
            QualityEngineResource.resource_id != corporate_resource.id,
        )
    )

    if misplaced_engine and not existing_corporate_engine:
        old_resource_id = misplaced_engine.resource_id

        moved_issues = db.scalars(
            select(QualityIssue).where(
                QualityIssue.resource_id == old_resource_id,
                QualityIssue.source == "TESTGEN",
            )
        ).all()
        moved_issue_ids = []
        for issue in moved_issues:
            issue.asset_id = corporate_asset.id
            issue.resource_id = corporate_resource.id
            moved_issue_ids.append(str(issue.id))

        for profile in db.scalars(
            select(QualityProfile).where(
                QualityProfile.resource_id == old_resource_id,
                QualityProfile.source == "TESTGEN",
            )
        ).all():
            profile.asset_id = corporate_asset.id
            profile.resource_id = corporate_resource.id

        if moved_issue_ids:
            for task in db.scalars(
                select(StewardshipTask).where(
                    StewardshipTask.source_type == "QUALITY_ISSUE",
                    StewardshipTask.source_reference.in_(moved_issue_ids),
                )
            ).all():
                task.asset_id = corporate_asset.id

        misplaced_engine.resource_id = corporate_resource.id
        misplaced_engine.external_table_name = "raw.corporate_data"
        cfg = dict(misplaced_engine.configuration or {})
        cfg.update(
            {
                "source_connection_name": "Florida Data Lab",
                "source_database": "florida_data_lab",
                "source_schema": "raw",
                "source_table": "corporate_data",
                "source_qualified_name": "raw.corporate_data",
            }
        )
        misplaced_engine.configuration = cfg
        misplaced_engine.project_code = misplaced_engine.project_code or "DEFAULT"
        misplaced_engine.table_group_id = corporate_table_group_id
        misplaced_engine.test_suite_id = corporate_test_suite_id
        misplaced_engine.sync_status = "CONFIGURED"
        existing_corporate_engine = misplaced_engine

    if not existing_corporate_engine:
        existing_corporate_engine = QualityEngineResource(
            organization_id=org.id,
            resource_id=corporate_resource.id,
            provider="TESTGEN",
            project_code="DEFAULT",
            table_group_id=corporate_table_group_id,
            test_suite_id=corporate_test_suite_id,
            external_table_name="raw.corporate_data",
            sync_status="CONFIGURED",
            configuration={
                "source_connection_name": "Florida Data Lab",
                "source_database": "florida_data_lab",
                "source_schema": "raw",
                "source_table": "corporate_data",
                "source_qualified_name": "raw.corporate_data",
            },
        )
        db.add(existing_corporate_engine)
    else:
        existing_corporate_engine.project_code = existing_corporate_engine.project_code or "DEFAULT"
        existing_corporate_engine.table_group_id = existing_corporate_engine.table_group_id or corporate_table_group_id
        existing_corporate_engine.test_suite_id = existing_corporate_engine.test_suite_id or corporate_test_suite_id
        existing_corporate_engine.external_table_name = existing_corporate_engine.external_table_name or "raw.corporate_data"
        cfg = dict(existing_corporate_engine.configuration or {})
        cfg.setdefault("source_connection_name", "Florida Data Lab")
        cfg.setdefault("source_database", "florida_data_lab")
        cfg.setdefault("source_schema", "raw")
        cfg.setdefault("source_table", "corporate_data")
        cfg.setdefault("source_qualified_name", "raw.corporate_data")
        existing_corporate_engine.configuration = cfg

    db.flush()
    sync_tasks(db, application, users["steward@demo.gov"].id)
    sync_tasks(db, corporate_asset, users["steward@demo.gov"].id)
    db.commit()
