"""Unit tests for domain enums, entities, and errors.

No external services required. Pure Python only.
"""

from datetime import UTC, datetime
from uuid import uuid4

from fetch.domain.entities import (
    ApiOperation,
    ApiSource,
    Chunk,
    ChunkRelation,
    IngestionJob,
    QueryRun,
    SourceRevision,
)
from fetch.domain.enums import (
    ChunkRelationType,
    ChunkType,
    HttpMethod,
    IngestionStage,
    QueryWorkflow,
    RevisionStatus,
    SourceType,
    SupportStatus,
)
from fetch.domain.errors import (
    FetchError,
    FileTooLargeError,
    IngestionAlreadyRunningError,
    IngestionError,
    InvalidOpenAPIError,
    NoActiveRevisionError,
    OperationNotFoundError,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RequestValidationError,
    SourceNotFoundError,
)

# ── Enum tests ────────────────────────────────────────────────────────────────


def test_source_type_values() -> None:
    assert SourceType.OPENAPI_FILE == "openapi_file"
    assert SourceType.OPENAPI_URL == "openapi_url"
    assert SourceType.WEBSITE == "website"


def test_revision_status_values() -> None:
    assert RevisionStatus.BUILDING == "building"
    assert RevisionStatus.ACTIVE == "active"
    assert RevisionStatus.FAILED == "failed"
    assert RevisionStatus.SUPERSEDED == "superseded"


def test_ingestion_stage_has_all_states() -> None:
    stages = {s.value for s in IngestionStage}
    expected = {
        "queued", "fetching", "snapshotting", "parsing", "validating",
        "normalizing", "chunking", "embedding", "indexing", "verifying",
        "active", "failed", "cancelled",
    }
    assert stages == expected


def test_support_status_values() -> None:
    assert SupportStatus.SUPPORTED == "supported"
    assert SupportStatus.INSUFFICIENT_EVIDENCE == "insufficient_evidence"


def test_http_method_values() -> None:
    assert HttpMethod.GET == "GET"
    assert HttpMethod.POST == "POST"
    assert HttpMethod.DELETE == "DELETE"


def test_enums_are_str_subclasses() -> None:
    # str-based enums serialize directly to JSON without extra conversion
    assert isinstance(SourceType.OPENAPI_FILE, str)
    assert isinstance(RevisionStatus.ACTIVE, str)
    assert isinstance(IngestionStage.QUEUED, str)
    assert isinstance(SupportStatus.SUPPORTED, str)


# ── Entity construction tests ─────────────────────────────────────────────────


def test_api_source_construction() -> None:
    source = ApiSource(
        id=uuid4(),
        workspace_id=uuid4(),
        name="Stripe API",
        source_type=SourceType.OPENAPI_FILE,
        config_url=None,
        config_object_key="uploads/stripe.yaml",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert source.name == "Stripe API"
    assert source.source_type == SourceType.OPENAPI_FILE


def test_source_revision_defaults() -> None:
    revision = SourceRevision(
        id=uuid4(),
        source_id=uuid4(),
        workspace_id=uuid4(),
        status=RevisionStatus.BUILDING,
        content_hash=None,
        snapshot_object_key=None,
        api_version=None,
        api_title=None,
        expected_chunk_count=None,
        actual_chunk_count=None,
        created_at=datetime.now(UTC),
        activated_at=None,
        failed_at=None,
        failure_reason=None,
    )
    assert revision.status == RevisionStatus.BUILDING
    assert revision.activated_at is None


def test_api_operation_defaults_empty_lists() -> None:
    op = ApiOperation(
        id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        method=HttpMethod.POST,
        path="/v1/customers/",
        path_normalized="/v1/customers",
        operation_id="createCustomer",
        summary="Create a customer",
        description=None,
        tags=["Customers"],
        deprecated=False,
        logical_key="source123:2025-01-01:POST:/v1/customers",
        source_pointer="#/paths/~1v1~1customers/post",
    )
    assert op.parameters == []
    assert op.request_body is None
    assert op.responses == []
    assert op.security_requirements == []


def test_ingestion_job_construction() -> None:
    job = IngestionJob(
        id=uuid4(),
        source_id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        stage=IngestionStage.QUEUED,
        attempt=1,
        max_attempts=3,
        error_message=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        started_at=None,
        completed_at=None,
    )
    assert job.stage == IngestionStage.QUEUED
    assert job.attempt == 1


def test_query_run_defaults() -> None:
    run = QueryRun(
        id=uuid4(),
        workspace_id=uuid4(),
        source_id=uuid4(),
        revision_id=uuid4(),
        workflow=QueryWorkflow.DOC_QA,
        question="How does pagination work?",
        answer=None,
    )
    assert run.citations == []
    assert run.warnings == []
    assert run.support_status == SupportStatus.INSUFFICIENT_EVIDENCE
    assert run.validation is None


def test_chunk_tags_default_empty() -> None:
    chunk = Chunk(
        id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        source_id=uuid4(),
        chunk_type=ChunkType.OPERATION_SUMMARY,
        entity_type="operation",
        entity_id=uuid4(),
        title="Create a customer",
        text="POST /v1/customers — Creates a new customer...",
        content_hash="sha256:abc123",
        embedding_profile_version="v1",
        qdrant_point_id=uuid4(),
        method="POST",
        path="/v1/customers",
        operation_id="createCustomer",
    )
    assert chunk.tags == []
    assert chunk.status_codes == []
    assert chunk.language is None


def test_chunk_relation_construction() -> None:
    relation = ChunkRelation(
        id=uuid4(),
        from_chunk_id=uuid4(),
        to_chunk_id=uuid4(),
        relation_type=ChunkRelationType.OPERATION_USES_SCHEMA,
        revision_id=uuid4(),
    )
    assert relation.relation_type == ChunkRelationType.OPERATION_USES_SCHEMA


# ── Error hierarchy tests ─────────────────────────────────────────────────────


def test_all_errors_inherit_from_fetch_error() -> None:
    assert issubclass(ProviderError, FetchError)
    assert issubclass(ProviderTimeoutError, FetchError)
    assert issubclass(SourceNotFoundError, FetchError)
    assert issubclass(IngestionError, FetchError)
    assert issubclass(InvalidOpenAPIError, FetchError)
    assert issubclass(OperationNotFoundError, FetchError)
    assert issubclass(RequestValidationError, FetchError)


def test_provider_timeout_is_retryable() -> None:
    err = ProviderTimeoutError("timed out")
    assert err.retryable is True
    assert isinstance(err, ProviderError)
    assert isinstance(err, FetchError)


def test_provider_auth_is_not_retryable() -> None:
    err = ProviderAuthError("invalid key")
    assert err.retryable is False


def test_provider_rate_limit_is_retryable() -> None:
    err = ProviderRateLimitError("too many requests")
    assert err.retryable is True


def test_provider_unavailable_is_retryable() -> None:
    err = ProviderUnavailableError("service down")
    assert err.retryable is True


def test_provider_error_stores_message() -> None:
    err = ProviderTimeoutError("request timed out after 60s")
    assert str(err) == "request timed out after 60s"


def test_invalid_openapi_error_stores_pointer() -> None:
    err = InvalidOpenAPIError("missing required field", source_pointer="#/info/title")
    assert err.source_pointer == "#/info/title"
    assert isinstance(err, IngestionError)


def test_ingestion_error_hierarchy() -> None:
    assert issubclass(IngestionAlreadyRunningError, IngestionError)
    assert issubclass(InvalidOpenAPIError, IngestionError)
    assert issubclass(FileTooLargeError, IngestionError)


def test_no_active_revision_error() -> None:
    err = NoActiveRevisionError("no active revision for source abc")
    assert isinstance(err, FetchError)
    assert "abc" in str(err)
