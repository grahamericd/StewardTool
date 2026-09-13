import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


class MembershipRole(str, enum.Enum):
    STEWARD = "STEWARD"
    ORG_ADMIN = "ORG_ADMIN"
    APPROVER = "APPROVER"
    VIEWER = "VIEWER"
    ENTERPRISE_ADMIN = "ENTERPRISE_ADMIN"


class PublicationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    NEEDS_UPDATE = "NEEDS_UPDATE"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AppUser(Base):
    __tablename__ = "app_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_user_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", name="uq_user_org"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user = relationship("AppUser")
    organization = relationship("Organization")


class CatalogSystem(Base):
    __tablename__ = "catalog_systems"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_system_org_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    business_purpose: Mapped[str | None] = mapped_column(Text)
    vendor: Mapped[str | None] = mapped_column(String(255))
    system_owner: Mapped[str | None] = mapped_column(String(255))
    lifecycle_status: Mapped[str] = mapped_column(String(40), default="ACTIVE", nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DataAsset(Base):
    __tablename__ = "data_assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    asset_identifier: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_definition: Mapped[str | None] = mapped_column(Text)
    business_domain: Mapped[str | None] = mapped_column(String(255))
    business_owner: Mapped[str | None] = mapped_column(String(255))
    data_steward: Mapped[str | None] = mapped_column(String(255))
    authoritative_status: Mapped[str] = mapped_column(String(40), default="UNKNOWN", nullable=False)
    classification: Mapped[str | None] = mapped_column(String(80))
    retention_requirement: Mapped[str | None] = mapped_column(Text)
    retention_authority: Mapped[str | None] = mapped_column(Text)
    asset_status: Mapped[str] = mapped_column(String(40), default="ACTIVE", nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    resources = relationship("AssetResource", cascade="all, delete-orphan")
    metadata_items = relationship("AssetMetadata", cascade="all, delete-orphan")
    publication = relationship("AssetPublication", uselist=False, cascade="all, delete-orphan")
    quality_profiles = relationship("QualityProfile", cascade="all, delete-orphan")
    quality_rules = relationship("QualityRule", cascade="all, delete-orphan")
    tasks = relationship("StewardshipTask", cascade="all, delete-orphan")
    reviews = relationship("StewardshipReview", cascade="all, delete-orphan")


class DataResource(Base):
    __tablename__ = "data_resources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    system_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_systems.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    structure_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location_reference: Mapped[str | None] = mapped_column(Text)
    format: Mapped[str | None] = mapped_column(String(100))
    media_type: Mapped[str | None] = mapped_column(String(150))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    system = relationship("CatalogSystem")


class AssetResource(Base):
    __tablename__ = "asset_resources"
    __table_args__ = (UniqueConstraint("asset_id", "resource_id", name="uq_asset_resource"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    resource_id: Mapped[int] = mapped_column(ForeignKey("data_resources.id", ondelete="CASCADE"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(80), default="REPRESENTATION", nullable=False)
    is_authoritative: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resource = relationship("DataResource")


class AssetMetadata(Base):
    __tablename__ = "asset_metadata"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    metadata_key: Mapped[str] = mapped_column(String(120), nullable=False)
    metadata_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    metadata_source: Mapped[str] = mapped_column(String(40), default="USER", nullable=False)
    review_status: Mapped[str] = mapped_column(String(40), default="PROPOSED", nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GovernanceRequirement(Base):
    __tablename__ = "governance_requirements"
    __table_args__ = (UniqueConstraint("organization_id", "requirement_key", name="uq_org_requirement"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    requirement_key: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    guidance: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(80), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    required_for_submission: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class StewardshipReview(Base):
    __tablename__ = "stewardship_reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    asset_id: Mapped[int] = mapped_column(ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    review_type: Mapped[str] = mapped_column(String(40), default="PERIODIC", nullable=False)
    answers: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text)
    snapshot_before: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    next_review_due: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class StewardshipTask(Base):
    __tablename__ = "stewardship_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    asset_id: Mapped[int] = mapped_column(ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    governance_domain: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    why_it_matters: Mapped[str | None] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="MEDIUM", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="OPEN", nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), default="GOVERNANCE", nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(255))
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QualityProfile(Base):
    __tablename__ = "quality_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("data_resources.id", ondelete="SET NULL"))
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    completeness_score: Mapped[float | None] = mapped_column(Float)
    validity_score: Mapped[float | None] = mapped_column(Float)
    uniqueness_score: Mapped[float | None] = mapped_column(Float)
    consistency_score: Mapped[float | None] = mapped_column(Float)
    timeliness_score: Mapped[float | None] = mapped_column(Float)
    row_count: Mapped[int | None] = mapped_column(Integer)
    profiled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(80), default="AI_DATA_STEWARD", nullable=False)
    external_run_id: Mapped[str | None] = mapped_column(String(255))


class QualityRule(Base):
    __tablename__ = "quality_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("data_resources.id", ondelete="SET NULL"))
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False)
    plain_language_rule: Mapped[str] = mapped_column(Text, nullable=False)
    rule_definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PROPOSED", nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QualityResult(Base):
    __tablename__ = "quality_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("quality_rules.id", ondelete="CASCADE"), nullable=False)
    result_status: Mapped[str] = mapped_column(String(20), nullable=False)
    evaluated_count: Mapped[int | None] = mapped_column(Integer)
    failed_count: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict | None] = mapped_column(JSON)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(80), default="AI_DATA_STEWARD", nullable=False)
    external_run_id: Mapped[str | None] = mapped_column(String(255))


class QualityEngineResource(Base):
    __tablename__ = "quality_engine_resources"
    __table_args__ = (UniqueConstraint("resource_id", "provider", name="uq_resource_quality_provider"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    resource_id: Mapped[int] = mapped_column(ForeignKey("data_resources.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="TESTGEN", nullable=False)
    project_code: Mapped[str | None] = mapped_column(String(255))
    connection_id: Mapped[str | None] = mapped_column(String(255))
    table_group_id: Mapped[str | None] = mapped_column(String(255))
    test_suite_id: Mapped[str | None] = mapped_column(String(255))
    external_table_name: Mapped[str | None] = mapped_column(String(255))
    sync_status: Mapped[str] = mapped_column(String(40), default="CONFIGURED", nullable=False)
    last_profiled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_external_run_id: Mapped[str | None] = mapped_column(String(255))
    configuration: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class QualityIssue(Base):
    __tablename__ = "quality_issues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    asset_id: Mapped[int] = mapped_column(ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("data_resources.id", ondelete="SET NULL"))
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("quality_rules.id", ondelete="SET NULL"))
    issue_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="MEDIUM", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="OPEN", nullable=False)
    failed_count: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(80), default="TESTGEN", nullable=False)
    external_run_id: Mapped[str | None] = mapped_column(String(255))
    external_issue_id: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QualityDecision(Base):
    __tablename__ = "quality_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("quality_issues.id", ondelete="CASCADE"), nullable=False)
    decision_type: Mapped[str] = mapped_column(String(60), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssetPublication(Base):
    __tablename__ = "asset_publications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("data_assets.id", ondelete="CASCADE"), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default=PublicationStatus.DRAFT.value, nullable=False)
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_validation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation_errors: Mapped[list | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AssetRelease(Base):
    __tablename__ = "asset_releases"
    __table_args__ = (UniqueConstraint("asset_id", "version_number", name="uq_asset_release"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("data_assets.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_hash: Mapped[str | None] = mapped_column(String(128))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ckan_dataset_id: Mapped[str | None] = mapped_column(String(255))
    ckan_name: Mapped[str | None] = mapped_column(String(255))
    publication_result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PublicationEvent(Base):
    __tablename__ = "publication_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("data_assets.id"), nullable=False)
    publication_id: Mapped[int | None] = mapped_column(ForeignKey("asset_publications.id"))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str | None] = mapped_column(String(40))
    performed_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    comments: Mapped[str | None] = mapped_column(Text)
    event_metadata: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
