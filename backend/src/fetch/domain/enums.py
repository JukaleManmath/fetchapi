"""Domain enums.

All persisted states and workflow types are defined here as enums.
str-based enums serialize cleanly to/from JSON and PostgreSQL varchar columns.
"""

from enum import StrEnum


class SourceType(StrEnum):
    """The kind of documentation source being ingested."""

    OPENAPI_FILE = "openapi_file"
    OPENAPI_URL = "openapi_url"
    WEBSITE = "website"  # deferred — do not implement ingestion until Phase 4


class RevisionStatus(StrEnum):
    """Lifecycle state of a source revision."""

    BUILDING = "building"       # ingestion is in progress
    ACTIVE = "active"           # this revision is the current queryable version
    FAILED = "failed"           # ingestion failed — never activated
    SUPERSEDED = "superseded"   # a newer revision replaced this one


class IngestionStage(StrEnum):
    """Fine-grained stage within the ingestion state machine."""

    QUEUED = "queued"
    FETCHING = "fetching"
    SNAPSHOTTING = "snapshotting"
    PARSING = "parsing"
    VALIDATING = "validating"
    NORMALIZING = "normalizing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    VERIFYING = "verifying"
    ACTIVE = "active"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QueryWorkflow(StrEnum):
    """The primary intent workflow for a query run."""

    DOC_QA = "doc_qa"
    ENDPOINT_LOOKUP = "endpoint_lookup"
    AUTH_GUIDANCE = "auth_guidance"
    INTEGRATION_GENERATION = "integration_generation"
    REQUEST_VALIDATION = "request_validation"
    ERROR_DIAGNOSIS = "error_diagnosis"
    VERSION_COMPARE = "version_compare"
    SCHEMA_LOOKUP = "schema_lookup"
    SOURCE_MANAGEMENT = "source_management"
    UNSUPPORTED = "unsupported"


class SupportStatus(StrEnum):
    """Evidence support level for a query answer.

    Never expose uncalibrated confidence floats. Use this enum instead.
    """

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    VALIDATION_FAILED = "validation_failed"


class ChunkType(StrEnum):
    """The kind of retrieval projection a chunk represents."""

    OPERATION_SUMMARY = "operation_summary"
    SCHEMA_DETAIL = "schema_detail"
    AUTH_SCHEME = "auth_scheme"
    ERROR_DEFINITION = "error_definition"
    GUIDE_SECTION = "guide_section"
    CODE_EXAMPLE = "code_example"


class ChunkRelationType(StrEnum):
    """Typed relationship between two chunks.

    Used during relationship expansion after reranking.
    """

    OPERATION_USES_SCHEMA = "operation_uses_schema"
    OPERATION_REQUIRES_AUTH = "operation_requires_auth"
    OPERATION_RETURNS_SCHEMA = "operation_returns_schema"
    OPERATION_HAS_ERROR = "operation_has_error"
    EXAMPLE_FOR_OPERATION = "example_for_operation"
    SCHEMA_REFERENCES_SCHEMA = "schema_references_schema"
    GUIDE_COVERS_OPERATION = "guide_covers_operation"


class ParameterLocation(StrEnum):
    """Where an API parameter appears in the HTTP request."""

    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"


class AuthSchemeType(StrEnum):
    """OpenAPI security scheme types."""

    API_KEY = "apiKey"
    HTTP = "http"
    OAUTH2 = "oauth2"
    OPENID_CONNECT = "openIdConnect"


class HttpMethod(StrEnum):
    """HTTP methods used in API operations."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    TRACE = "TRACE"
