"""Domain errors.

All application and infrastructure code must convert their internal exceptions
into one of these stable errors before crossing a layer boundary.
"""


class FetchError(Exception):
    """Base error for all FetchAPI domain errors."""


# ── Provider errors ────────────────────────────────────────────────────────────


class ProviderError(FetchError):
    """An external provider (LLM, embeddings, reranker) returned an error."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ProviderTimeoutError(ProviderError):
    """Provider did not respond within the configured timeout."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class ProviderRateLimitError(ProviderError):
    """Provider rate limit exceeded."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


class ProviderAuthError(ProviderError):
    """Provider rejected the API key or credentials."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class ProviderUnavailableError(ProviderError):
    """Provider is unreachable or returned a 5xx error."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=True)


# ── Source and revision errors ─────────────────────────────────────────────────


class SourceNotFoundError(FetchError):
    """The requested ApiSource does not exist."""


class RevisionNotFoundError(FetchError):
    """The requested SourceRevision does not exist."""


class NoActiveRevisionError(FetchError):
    """The source has no active revision — ingestion may still be in progress."""


class SourceAlreadyExistsError(FetchError):
    """A source with the same config already exists in this workspace."""


class RevisionAlreadyActiveError(FetchError):
    """A revision is already active for this source — cannot activate another."""


# ── Ingestion errors ───────────────────────────────────────────────────────────


class IngestionError(FetchError):
    """Base class for errors that occur during ingestion."""


class IngestionAlreadyRunningError(IngestionError):
    """An ingestion job is already running for this source."""


class InvalidOpenAPIError(IngestionError):
    """The uploaded or fetched document is not a valid OpenAPI spec."""

    def __init__(self, message: str, *, source_pointer: str | None = None) -> None:
        super().__init__(message)
        self.source_pointer = source_pointer


class ExternalRefError(IngestionError):
    """An external $ref could not be resolved or violated safety limits."""


class FileTooLargeError(IngestionError):
    """The uploaded file exceeds the configured size limit."""


class TooManyOperationsError(IngestionError):
    """The spec exceeds the configured maximum operation count."""


# ── Retrieval errors ───────────────────────────────────────────────────────────


class RetrievalError(FetchError):
    """Base class for retrieval pipeline errors."""


class OperationNotFoundError(RetrievalError):
    """The requested operation does not exist in the active revision."""


class SchemaNotFoundError(RetrievalError):
    """The requested schema does not exist in the active revision."""


class InsufficientEvidenceError(RetrievalError):
    """Not enough evidence was retrieved to answer the query."""


# ── Storage errors ─────────────────────────────────────────────────────────────


class ObjectNotFoundError(FetchError):
    """The requested object does not exist in object storage."""


# ── Validation errors ──────────────────────────────────────────────────────────


class RequestValidationError(FetchError):
    """The user-supplied request or curl command failed validation."""


class GeneratedCodeValidationError(FetchError):
    """The generated integration code failed schema or syntax validation."""
