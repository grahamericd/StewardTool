from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

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


SystemInventoryType = Literal["APPLICATION", "REPOSITORY", "REPORTING_TOOL", "INTEGRATION", "EXTERNAL_SYSTEM", "OTHER", "UNKNOWN"]
SystemKnowledgeStatus = Literal["CONFIRMED", "PARTIAL", "UNCERTAIN"]
RelationshipEntityType = Literal["BUSINESS_FUNCTION", "BUSINESS_CONCEPT", "BUSINESS_PROCESS", "SYSTEM", "RESOURCE", "ASSET", "PERSON"]
RelationshipType = Literal["SUPPORTS", "DESCRIBES", "REPRESENTS", "OWNER", "STEWARD", "DEPENDS_ON", "PROCESS_FLOW"]


class SystemInventoryCreate(BaseModel):
    name: ShortText = Field(min_length=1)
    system_type: SystemInventoryType = "UNKNOWN"
    knowledge_status: SystemKnowledgeStatus = "UNCERTAIN"
    known_details: LongText | None = None
    business_purpose: LongText | None = None
    description: LongText | None = None
    vendor: ShortText | None = None
    system_owner: ShortText | None = None


class SystemInventoryUpdate(BaseModel):
    name: ShortText | None = None
    system_type: SystemInventoryType | None = None
    knowledge_status: SystemKnowledgeStatus | None = None
    known_details: LongText | None = None
    business_purpose: LongText | None = None
    description: LongText | None = None
    vendor: ShortText | None = None
    system_owner: ShortText | None = None


class LandscapeRelationshipCreate(BaseModel):
    source_type: RelationshipEntityType
    source_id: int = Field(gt=0)
    target_type: RelationshipEntityType
    target_id: int | None = Field(default=None, gt=0)
    relationship_type: RelationshipType
    details: dict | None = None
    process_id: int | None = Field(default=None, gt=0)


class LandscapeDraftUpdate(BaseModel):
    draft_data: dict


class LandscapeDraftCheckpoint(BaseModel):
    label: ShortText | None = None


class BusinessFunctionCreate(BaseModel):
    name: ShortText = Field(min_length=1)
    description: LongText | None = None
    purpose: LongText | None = None
    owner: ShortText | None = None
    parent_function_id: int | None = None
    status: CodeText = "ACTIVE"


class BusinessFunctionUpdate(BaseModel):
    name: ShortText | None = None
    description: LongText | None = None
    purpose: LongText | None = None
    owner: ShortText | None = None
    parent_function_id: int | None = None
    status: CodeText | None = None


class BusinessUnitCreate(BaseModel):
    name: ShortText = Field(min_length=1)
    unit_type: CodeText = "DEPARTMENT"
    description: LongText | None = None
    status: CodeText = "ACTIVE"


class BusinessUnitUpdate(BaseModel):
    name: ShortText | None = None
    unit_type: CodeText | None = None
    description: LongText | None = None
    status: CodeText | None = None


class BusinessFunctionUnitMappingCreate(BaseModel):
    function_id: int = Field(gt=0)
    unit_id: int = Field(gt=0)


class BusinessFunctionUnitMappingUpdate(BaseModel):
    function_id: int | None = Field(default=None, gt=0)
    unit_id: int | None = Field(default=None, gt=0)


class BusinessConceptCreate(BaseModel):
    name: ShortText = Field(min_length=1)
    description: LongText | None = None
    category: CodeText | None = None
    definition: LongText | None = None
    status: CodeText = "PROPOSED"
    owner: ShortText | None = None


class BusinessConceptUpdate(BaseModel):
    name: ShortText | None = None
    description: LongText | None = None
    category: CodeText | None = None
    definition: LongText | None = None
    status: CodeText | None = None
    owner: ShortText | None = None


class BusinessFlowCreate(BaseModel):
    name: ShortText = Field(min_length=1)
    description: LongText | None = None
    trigger: LongText | None = None
    frequency: ShortText | None = None
    source_function_id: int | None = None
    target_function_id: int | None = None
    status: CodeText = "ACTIVE"


class BusinessFlowUpdate(BaseModel):
    name: ShortText | None = None
    description: LongText | None = None
    trigger: LongText | None = None
    frequency: ShortText | None = None
    source_function_id: int | None = None
    target_function_id: int | None = None
    status: CodeText | None = None


class LandscapeSystemCreate(BaseModel):
    name: ShortText = Field(min_length=1)
    description: LongText | None = None
    business_purpose: LongText | None = None
    vendor: ShortText | None = None
    system_owner: ShortText | None = None
    lifecycle_status: CodeText = "ACTIVE"


class LandscapeSystemUpdate(BaseModel):
    name: ShortText | None = None
    description: LongText | None = None
    business_purpose: LongText | None = None
    vendor: ShortText | None = None
    system_owner: ShortText | None = None
    lifecycle_status: CodeText | None = None


class DiscoverySessionCreate(BaseModel):
    title: ShortText = Field(min_length=1)
    status: CodeText = "ACTIVE"
    summary: LongText | None = None
    context_snapshot: dict | None = None


class DiscoverySessionUpdate(BaseModel):
    title: ShortText | None = None
    status: CodeText | None = None
    summary: LongText | None = None
    context_snapshot: dict | None = None


class LandscapeEvidenceCreate(BaseModel):
    entity_type: CodeText = Field(min_length=1)
    entity_id: int | None = None
    evidence_type: CodeText = Field(min_length=1)
    summary: LongText | None = None
    details: dict | None = None
    source: CodeText = "USER"
    session_id: int | None = None


class LandscapeEvidenceUpdate(BaseModel):
    entity_type: CodeText | None = None
    entity_id: int | None = None
    evidence_type: CodeText | None = None
    summary: LongText | None = None
    details: dict | None = None
    source: CodeText | None = None
    session_id: int | None = None


class LandscapeAssertionCreate(BaseModel):
    entity_type: CodeText = Field(min_length=1)
    entity_id: int | None = None
    assertion_type: CodeText = Field(min_length=1)
    statement: LongText = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: CodeText = "PROPOSED"
    session_id: int | None = None


class LandscapeAssertionUpdate(BaseModel):
    entity_type: CodeText | None = None
    entity_id: int | None = None
    assertion_type: CodeText | None = None
    statement: LongText | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: CodeText | None = None
    session_id: int | None = None


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


class DiscoveryCandidateCreate(BaseModel):
    name: ShortText = Field(min_length=1)
    kind: CodeText = "INFORMATION"
    summary: LongText | None = None
    description: LongText | None = None
    status: CodeText = "SUGGESTED"
    source: CodeText = "USER"
    parent_candidate_id: int | None = None
    asset_id: int | None = None
    system_id: int | None = None
    resource_id: int | None = None
    suggested_by_ai: bool = False
    details: dict | None = None


class DiscoveryCandidateUpdate(BaseModel):
    name: ShortText | None = None
    kind: CodeText | None = None
    summary: LongText | None = None
    description: LongText | None = None
    status: CodeText | None = None
    source: CodeText | None = None
    parent_candidate_id: int | None = None
    asset_id: int | None = None
    system_id: int | None = None
    resource_id: int | None = None
    suggested_by_ai: bool | None = None
    details: dict | None = None


class DiscoveryObservationCreate(BaseModel):
    candidate_id: int = Field(gt=0)
    observation_type: CodeText = Field(min_length=1)
    details: dict = Field(default_factory=dict)
    source: CodeText = "USER"


class DiscoveryRelationshipCreate(BaseModel):
    left_candidate_id: int = Field(gt=0)
    right_candidate_id: int = Field(gt=0)
    relationship_type: CodeText = Field(min_length=1)
    status: CodeText = "SUGGESTED"
    details: dict | None = None


class DiscoveryProvenanceCreate(BaseModel):
    entity_type: CodeText = Field(min_length=1)
    entity_id: int = Field(gt=0)
    action: CodeText = Field(min_length=1)
    details: dict | None = None


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

    @field_validator("comments")
    @classmethod
    def comments_must_contain_real_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("A review note is required when returning information for changes.")
        return value


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



class ContactPointInput(BaseModel):
    name: ShortText = Field(min_length=1)
    email: ShortText | None = None


class UnderstandingUpdate(BaseModel):
    business_definition: LongText = Field(min_length=1)
    business_area: ShortText = Field(min_length=1)
    search_terms: list[ShortText] = Field(default_factory=list, max_length=50)
    update_frequency: ShortText = Field(min_length=1)

    # Accept the structured representation used by the catalog while
    # remaining compatible with older clients that submitted a string.
    contact_point: ContactPointInput | ShortText


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
