from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints

# Identifiers that are interpolated into TestGen URL paths. Blank is allowed so
# that clearing a field in the UI still validates; anything else must be a plain
# identifier so it cannot re-point the request at another TestGen endpoint.
TestGenId = Annotated[str, StringConstraints(pattern=r"^([A-Za-z0-9._-]{1,128})?$")]

ShortText = Annotated[str, StringConstraints(max_length=255)]
CodeText = Annotated[str, StringConstraints(max_length=80)]
LongText = Annotated[str, StringConstraints(max_length=8000)]
UrlText = Annotated[str, StringConstraints(max_length=2000)]


class SystemCreate(BaseModel):
    name: ShortText = Field(min_length=1)
    business_purpose: LongText | None = None
    description: LongText | None = None
    vendor: ShortText | None = None
    system_owner: ShortText | None = None


class AssetCreate(BaseModel):
    name: ShortText = Field(min_length=1)
    business_definition: LongText | None = None
    business_domain: ShortText | None = None
    business_owner: ShortText | None = None
    data_steward: ShortText | None = None


class AssetGovernanceUpdate(BaseModel):
    business_owner: ShortText | None = None
    data_steward: ShortText | None = None
    classification: CodeText | None = None
    retention_requirement: LongText | None = None
    retention_authority: LongText | None = None


class ResourceCreate(BaseModel):
    system_id: int | None = None
    name: ShortText = Field(min_length=1)
    resource_type: CodeText = Field(min_length=1)
    structure_type: Annotated[str, StringConstraints(max_length=40)] = Field(min_length=1)
    description: LongText | None = None
    location_reference: UrlText | None = None
    format: Annotated[str, StringConstraints(max_length=100)] | None = None
    media_type: Annotated[str, StringConstraints(max_length=150)] | None = None
    relationship_type: CodeText = "REPRESENTATION"
    is_authoritative: bool = False


class OfficialSourceDecision(BaseModel):
    resource_id: int
    decision_basis: LongText | None = None


class MetadataUpsert(BaseModel):
    metadata_key: Annotated[str, StringConstraints(max_length=120)] = Field(min_length=1)
    metadata_value: Any
    metadata_source: CodeText = "USER"
    # review_status is no longer accepted from the client: it decided whether
    # the value counted as approved governance metadata.


class TaskComplete(BaseModel):
    notes: LongText | None = None


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
    rule_name: ShortText = Field(min_length=1)
    rule_type: CodeText = Field(min_length=1)
    plain_language_rule: LongText = Field(min_length=1)
    rule_definition: dict
    status: CodeText = "PROPOSED"


class QualityResultCreate(BaseModel):
    result_status: str
    evaluated_count: int | None = None
    failed_count: int | None = None
    score: float | None = Field(default=None, ge=0, le=100)
    details: dict | None = None
    source: str = "AI_DATA_STEWARD"
    external_run_id: str | None = None


class SubmitRequest(BaseModel):
    comments: LongText | None = None


class ReviewRequest(BaseModel):
    comments: LongText | None = None


class RejectRequest(BaseModel):
    comments: LongText = Field(min_length=1)


class QualityEngineLinkCreate(BaseModel):
    resource_id: int
    provider: CodeText = "TESTGEN"
    project_code: TestGenId | None = None
    connection_id: TestGenId | None = None
    table_group_id: TestGenId | None = None
    test_suite_id: TestGenId | None = None
    external_table_name: ShortText | None = None

    # Real governed source identity. Credentials stay in TestGen.
    source_connection_name: ShortText | None = None
    source_database: ShortText | None = None
    source_schema: ShortText | None = None
    source_table: ShortText | None = None


class QualityAssessmentRequest(BaseModel):
    resource_id: int


class QualityRunRequest(BaseModel):
    resource_id: int


class QualityRuleStatusUpdate(BaseModel):
    status: CodeText


class QualityDecisionCreate(BaseModel):
    decision_type: CodeText
    notes: LongText | None = None


class HygieneFindingDecisionCreate(BaseModel):
    decision_type: CodeText
    notes: LongText | None = None



class PeriodicReviewCreate(BaseModel):
    answers: dict[Annotated[str, StringConstraints(max_length=80)], Annotated[str, StringConstraints(max_length=80)]]
    change_summary: LongText | None = None
    review_interval_days: int = Field(default=365, ge=30, le=1095)



class UnderstandingUpdate(BaseModel):
    business_definition: LongText = Field(min_length=1)
    business_area: ShortText = Field(min_length=1)
    search_terms: list[ShortText] = Field(default_factory=list, max_length=50)
    update_frequency: ShortText = Field(min_length=1)
    contact_point: ShortText = Field(min_length=1)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=512)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=12, max_length=512)



class OrganizationUserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    role: CodeText


class OrganizationUserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: CodeText | None = None
    membership_active: bool | None = None
