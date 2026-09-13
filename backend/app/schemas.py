from typing import Any
from pydantic import BaseModel, Field


class SystemCreate(BaseModel):
    name: str
    business_purpose: str | None = None
    description: str | None = None
    vendor: str | None = None
    system_owner: str | None = None


class AssetCreate(BaseModel):
    name: str
    business_definition: str | None = None
    business_domain: str | None = None
    business_owner: str | None = None
    data_steward: str | None = None


class AssetGovernanceUpdate(BaseModel):
    business_owner: str | None = None
    data_steward: str | None = None
    classification: str | None = None
    retention_requirement: str | None = None
    retention_authority: str | None = None


class ResourceCreate(BaseModel):
    system_id: int | None = None
    name: str
    resource_type: str
    structure_type: str
    description: str | None = None
    location_reference: str | None = None
    format: str | None = None
    media_type: str | None = None
    relationship_type: str = "REPRESENTATION"
    is_authoritative: bool = False


class MetadataUpsert(BaseModel):
    metadata_key: str
    metadata_value: Any
    metadata_source: str = "USER"
    review_status: str = "APPROVED"


class TaskComplete(BaseModel):
    notes: str | None = None


class QualityProfileCreate(BaseModel):
    resource_id: int | None = None
    overall_score: float = Field(ge=0, le=100)
    completeness_score: float | None = Field(default=None, ge=0, le=100)
    validity_score: float | None = Field(default=None, ge=0, le=100)
    uniqueness_score: float | None = Field(default=None, ge=0, le=100)
    consistency_score: float | None = Field(default=None, ge=0, le=100)
    timeliness_score: float | None = Field(default=None, ge=0, le=100)
    row_count: int | None = None
    source: str = "AI_DATA_STEWARD"
    external_run_id: str | None = None


class QualityRuleCreate(BaseModel):
    resource_id: int | None = None
    rule_name: str
    rule_type: str
    plain_language_rule: str
    rule_definition: dict
    status: str = "PROPOSED"


class QualityResultCreate(BaseModel):
    result_status: str
    evaluated_count: int | None = None
    failed_count: int | None = None
    score: float | None = Field(default=None, ge=0, le=100)
    details: dict | None = None
    source: str = "AI_DATA_STEWARD"
    external_run_id: str | None = None


class SubmitRequest(BaseModel):
    comments: str | None = None


class ReviewRequest(BaseModel):
    comments: str | None = None


class RejectRequest(BaseModel):
    comments: str = Field(min_length=1)


class QualityEngineLinkCreate(BaseModel):
    resource_id: int
    provider: str = "TESTGEN"
    project_code: str | None = None
    connection_id: str | None = None
    table_group_id: str | None = None
    test_suite_id: str | None = None
    external_table_name: str | None = None

    # Real governed source identity. Credentials stay in TestGen.
    source_connection_name: str | None = None
    source_database: str | None = None
    source_schema: str | None = None
    source_table: str | None = None


class QualityAssessmentRequest(BaseModel):
    resource_id: int


class QualityRunRequest(BaseModel):
    resource_id: int


class QualityRuleStatusUpdate(BaseModel):
    status: str


class QualityDecisionCreate(BaseModel):
    decision_type: str
    notes: str | None = None


class HygieneFindingDecisionCreate(BaseModel):
    decision_type: str
    notes: str | None = None
