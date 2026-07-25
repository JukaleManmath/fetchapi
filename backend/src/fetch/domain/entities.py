"""Domain entities.

Pure Python dataclasses — no SQLAlchemy, no Pydantic, no external imports.
These are the core data structures the entire system operates on.

Entities (mutable state, have identity):  ApiSource, SourceRevision, IngestionJob, QueryRun
Value objects (immutable, no identity):   ApiParameter, ApiResponse, AuthScheme, etc.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from fetch.domain.enums import (
    AuthSchemeType,
    ChunkRelationType,
    ChunkType,
    DiagnosticCategory,
    DiagnosticInputType,
    GenerationLanguage,
    HttpMethod,
    IngestionStage,
    MatchConfidence,
    ParameterLocation,
    QueryWorkflow,
    RevisionStatus,
    SourceType,
    SupportStatus,
)

# ── Workspace ─────────────────────────────────────────────────────────────────


@dataclass
class Workspace:
    """Isolation boundary. Single default workspace in local MVP."""

    id: UUID
    name: str
    created_at: datetime


# ── Source and revision ───────────────────────────────────────────────────────


@dataclass
class ApiSource:
    """A user-configured documentation source.

    One source may have many revisions over time. Exactly one revision
    is ACTIVE at any point; all others are BUILDING, FAILED, or SUPERSEDED.
    """

    id: UUID
    workspace_id: UUID
    name: str
    source_type: SourceType
    # For OPENAPI_FILE: the object storage key of the uploaded file.
    # For OPENAPI_URL: the remote URL to fetch.
    config_url: str | None
    config_object_key: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class ApiServer:
    """A base URL and optional server variables declared in the OpenAPI spec."""

    id: UUID
    revision_id: UUID
    url: str
    description: str | None
    # e.g. {"environment": {"default": "production", "enum": ["production", "sandbox"]}}
    variables: dict[str, object]


@dataclass
class SourceRevision:
    """An immutable ingestion snapshot of one ApiSource.

    Created at the start of ingestion, activated only after full verification.
    Never mutated after activation — a re-ingest creates a new revision.
    """

    id: UUID
    source_id: UUID
    workspace_id: UUID
    status: RevisionStatus
    # SHA-256 hash of the raw source content — used for idempotency checks.
    content_hash: str | None
    # Object storage key for the immutable raw snapshot.
    snapshot_object_key: str | None
    # The API version string extracted from the spec (e.g. "1.0.0", "2025-01-27").
    api_version: str | None
    api_title: str | None
    # How many chunks were expected vs actually indexed — verified before activation.
    expected_chunk_count: int | None
    actual_chunk_count: int | None
    created_at: datetime
    activated_at: datetime | None
    failed_at: datetime | None
    failure_reason: str | None


# ── Canonical API entities ────────────────────────────────────────────────────


@dataclass
class ApiParameter:
    """A single named parameter (path/query/header/cookie)."""

    id: UUID
    revision_id: UUID
    operation_id: UUID | None  # None if this is a shared/reusable parameter
    name: str
    location: ParameterLocation
    required: bool
    deprecated: bool
    description: str | None
    schema_json: str | None  # raw JSON Schema for this parameter
    example_json: str | None
    source_pointer: str | None  # JSON Pointer to location in the original spec


@dataclass
class ApiRequestBody:
    """The request body for an operation."""

    id: UUID
    operation_id: UUID
    required: bool
    description: str | None
    # Maps content-type → JSON Schema string, e.g. {"application/json": "{...}"}
    content_schemas: dict[str, str]


@dataclass
class ApiResponse:
    """A documented response for a specific HTTP status code."""

    id: UUID
    operation_id: UUID
    status_code: str  # "200", "404", "default"
    description: str | None
    # Maps content-type → JSON Schema string
    content_schemas: dict[str, str]
    # Maps header name → description
    headers: dict[str, str]


@dataclass
class ApiOperation:
    """An HTTP operation extracted from an OpenAPI spec.

    This is the central entity — most retrieval and generation workflows
    start by finding the right operation.
    """

    id: UUID
    revision_id: UUID
    workspace_id: UUID
    method: HttpMethod
    path: str  # raw path as written in the spec, e.g. /v1/Customers/
    path_normalized: (
        str  # normalized: strip trailing slash, lowercase, e.g. /v1/customers
    )
    operation_id: str | None
    summary: str | None
    description: str | None
    tags: list[str]
    deprecated: bool
    # Logical key for deduplication: {source_id}:{api_version}:{METHOD}:{path_normalized}
    logical_key: str
    source_pointer: str | None  # JSON Pointer to this operation in the original spec
    parameters: list[ApiParameter] = field(default_factory=list)
    request_body: ApiRequestBody | None = None
    responses: list[ApiResponse] = field(default_factory=list)
    # Security requirement names referencing AuthScheme.name
    security_requirements: list[dict[str, list[str]]] = field(default_factory=list)


@dataclass
class ApiSchema:
    """A named or anonymous schema extracted from the OpenAPI spec.

    Large or reused schemas are stored as separate entities rather than
    being inlined into every operation that references them.
    """

    id: UUID
    revision_id: UUID
    workspace_id: UUID
    # Name from #/components/schemas/{name}, or a generated name for inline schemas.
    name: str
    description: str | None
    # The canonical JSON Schema as a string — may be large.
    schema_json: str
    # JSON Pointer to the schema definition in the original spec.
    source_pointer: str | None
    # Logical key: {source_id}:{api_version}:{source_pointer_or_name}
    logical_key: str
    nullable: bool
    deprecated: bool


@dataclass
class AuthScheme:
    """An API authentication/security scheme."""

    id: UUID
    revision_id: UUID
    workspace_id: UUID
    name: str  # the key in #/components/securitySchemes
    scheme_type: AuthSchemeType
    description: str | None
    # Scheme-specific details stored as JSON — varies by AuthSchemeType.
    # e.g. for apiKey: {"in": "header", "name": "X-API-Key"}
    # e.g. for oauth2: {"flows": {...}}
    details_json: str


@dataclass
class ApiExample:
    """A request, response, curl, or SDK code example."""

    id: UUID
    revision_id: UUID
    workspace_id: UUID
    operation_id: UUID | None
    title: str | None
    description: str | None
    language: str | None  # "python", "typescript", "curl", etc.
    content: str
    source_pointer: str | None


@dataclass
class ErrorDefinition:
    """A documented API error — status code or provider-specific error code."""

    id: UUID
    revision_id: UUID
    workspace_id: UUID
    operation_id: UUID | None  # None if this is a global error definition
    status_code: str | None  # "404", "429", etc.
    # Provider-specific codes, e.g. "card_declined", "insufficient_funds"
    error_code: str | None
    title: str | None
    description: str | None
    source_pointer: str | None


@dataclass
class GuideSection:
    """A section of conceptual documentation (pagination, rate limits, etc.)."""

    id: UUID
    revision_id: UUID
    workspace_id: UUID
    title: str
    # Breadcrumb of parent heading titles, e.g. ["Authentication", "OAuth 2.0"]
    heading_path: list[str]
    content: str
    source_url: str | None
    # Anchor ID within the page, e.g. "#pagination"
    anchor: str | None


# ── Retrieval layer ───────────────────────────────────────────────────────────


@dataclass
class Chunk:
    """A retrieval-optimized projection of one or more canonical entities.

    The text field is what gets embedded and stored in Qdrant.
    PostgreSQL owns the metadata; Qdrant owns the vector.
    """

    id: UUID
    revision_id: UUID
    workspace_id: UUID
    source_id: UUID
    chunk_type: ChunkType
    # The entity this chunk was projected from.
    entity_type: str  # "operation", "schema", "auth_scheme", etc.
    entity_id: UUID
    title: str
    # The text that was embedded. Store separately from canonical entities.
    text: str
    # SHA-256 of text + embedding_profile_version — used for idempotency.
    content_hash: str
    # Version of the embedding profile used to produce the vector.
    embedding_profile_version: str
    # Qdrant point ID — deterministic UUID derived from chunk_id.
    qdrant_point_id: UUID
    # Denormalized payload fields stored in Qdrant for filtering.
    method: str | None  # "GET", "POST", etc.
    path: str | None
    operation_id: str | None
    tags: list[str] = field(default_factory=list)
    status_codes: list[str] = field(default_factory=list)
    api_version: str | None = None
    source_url: str | None = None
    source_pointer: str | None = None
    language: str | None = None


@dataclass
class ChunkRelation:
    """A typed relationship between two chunks.

    Used during relationship expansion after reranking to deterministically
    add context without running another semantic retrieval query.
    """

    id: UUID
    from_chunk_id: UUID
    to_chunk_id: UUID
    relation_type: ChunkRelationType
    revision_id: UUID


# ── Job and query tracking ────────────────────────────────────────────────────


@dataclass
class IngestionJob:
    """Durable state machine record for one ingestion run.

    Created before any work begins. Updated as the worker progresses.
    A failed job never activates its revision.
    """

    id: UUID
    source_id: UUID
    revision_id: UUID
    workspace_id: UUID
    stage: IngestionStage
    attempt: int  # starts at 1, increments on each retry
    # Retry always restarts from QUEUED — no mid-stage resume in v1.
    max_attempts: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


@dataclass
class Citation:
    """A server-owned citation linking an answer claim to a source chunk."""

    source_id: str  # query-local ID: "S1", "S2", etc.
    chunk_id: UUID
    entity_type: str
    entity_id: UUID | None
    title: str
    content: str
    source_url: str | None
    source_pointer: str | None
    api_version: str | None
    method: str | None
    path: str | None


@dataclass
class ValidationSummary:
    """Result of deterministic request or code validation."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]
    corrected_example: str | None


@dataclass
class ValidationIssue:
    severity: str  # "error" | "warning"
    category: str  # "contract" | "syntax" | "security"
    message: str
    field: str | None = None


@dataclass
class ValidationReport:
    contract_valid: bool
    syntax_valid: bool
    issues: list[ValidationIssue]
    overall_valid: bool  # contract_valid AND syntax_valid


@dataclass
class IntegrationRun:
    """A traceable record of one complete integration code generation run."""

    id: UUID
    workspace_id: UUID
    source_id: UUID
    revision_id: UUID
    operation_id: UUID
    language: GenerationLanguage
    generated_code: str | None
    validation_report: ValidationReport | None
    support_status: SupportStatus
    warnings: list[str]
    prompt_version: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    context_assembly_ms: int | None
    generation_ms: int | None
    validation_ms: int | None
    total_ms: int | None
    created_at: datetime


@dataclass
class QueryRun:
    """A traceable record of one complete query execution."""

    id: UUID
    workspace_id: UUID
    source_id: UUID
    revision_id: UUID
    workflow: QueryWorkflow
    question: str
    answer: str | None
    citations: list[Citation] = field(default_factory=list)
    support_status: SupportStatus = SupportStatus.INSUFFICIENT_EVIDENCE
    warnings: list[str] = field(default_factory=list)
    validation: ValidationSummary | None = None
    # Latency breakdown in milliseconds.
    retrieval_ms: int | None = None
    generation_ms: int | None = None
    total_ms: int | None = None
    # Token usage from the LLM call.
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Retrieval trace fields — populated after retrieval, before generation.
    dense_candidate_count: int | None = None
    bm25_candidate_count: int | None = None
    fused_candidate_count: int | None = None
    reranked_candidate_count: int | None = None
    expanded_candidate_count: int | None = None
    exact_match_found: bool = False
    prompt_version: str | None = None
    intent_classification: str | None = None


# ── Request validation ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ParsedRequest:
    method: str
    url: str
    headers: dict[str, str]  # keys lowercased
    body_raw: str | None
    body_json: dict[str, object] | None
    content_type: str | None
    auth_header: str | None  # NEVER log or persist this value
    query_params: dict[str, str]
    is_url_encoded_body: bool


@dataclass(frozen=True)
class EndpointMatch:
    operation: "ApiOperation | None"
    path_params: dict[str, str]
    match_confidence: MatchConfidence


@dataclass(frozen=True)
class DiagnosticFinding:
    severity: str  # "error" | "warning"
    category: DiagnosticCategory
    message: str
    field: str | None = None
    canonical_value: str | None = None


@dataclass(frozen=True)
class ErrorStatusMatch:
    status_code: str
    matched_definitions: list["ErrorDefinition"]
    is_documented: bool


@dataclass(frozen=True)
class RequestDiagnostic:
    parsed_request: ParsedRequest
    endpoint_match: "EndpointMatch | None"
    findings: list[DiagnosticFinding]
    error_status_match: "ErrorStatusMatch | None"
    corrected_curl: str | None
    is_valid: bool


# ── Version diff entities ─────────────────────────────────────────────────────


@dataclass
class OperationDiff:
    operation_id: UUID
    method: str
    path: str
    change_type: str  # "added" | "removed" | "changed"
    changed_fields: list[str]  # e.g. ["description", "parameters"]


@dataclass
class SchemaDiff:
    schema_id: UUID
    name: str
    change_type: str  # "added" | "removed" | "changed"
    changed_fields: list[str]


@dataclass
class AuthDiff:
    name: str
    change_type: str  # "added" | "removed" | "changed"


@dataclass
class VersionDiff:
    source_id: UUID
    revision_a_id: UUID
    revision_b_id: UUID
    revision_a_version: str
    revision_b_version: str
    operations_added: list[OperationDiff]
    operations_removed: list[OperationDiff]
    operations_changed: list[OperationDiff]
    schemas_added: list[SchemaDiff]
    schemas_removed: list[SchemaDiff]
    schemas_changed: list[SchemaDiff]
    auth_added: list[AuthDiff]
    auth_removed: list[AuthDiff]
    summary: str  # e.g. "3 operations added, 1 removed, 2 schemas changed"


@dataclass
class RequestDiagnosticRun:
    id: UUID
    workspace_id: UUID
    source_id: UUID
    revision_id: UUID
    operation_id: UUID | None
    input_type: DiagnosticInputType
    raw_input: str  # auth header values must be redacted before storing
    parsed_method: str | None
    parsed_url: str | None
    received_status_code: str | None
    diagnostic: "RequestDiagnostic | None"
    explanation: str | None
    corrected_curl: str | None
    is_valid: bool
    support_status: SupportStatus
    prompt_version: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    parse_ms: int | None
    match_ms: int | None
    validate_ms: int | None
    explanation_ms: int | None
    total_ms: int | None
    created_at: datetime
