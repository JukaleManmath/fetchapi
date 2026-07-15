"""Domain-layer protocols.

Pure Python interfaces — no external imports.
Infrastructure adapters implement these. Application services depend on them.
Domain code never imports openai, boto3, SQLAlchemy, or any provider SDK.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from fetch.domain.entities import (
    ApiOperation,
    ApiSchema,
    ApiSource,
    AuthScheme,
    IngestionJob,
    SourceRevision,
)

# ── Value objects passed across the LLM boundary ──────────────────────────────


@dataclass(frozen=True)
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class GenerationConfig:
    model_id: str
    max_tokens: int = 4096
    temperature: float = 0.1
    # Request usage metadata on the final streamed chunk
    stream_include_usage: bool = True


@dataclass(frozen=True)
class StreamChunk:
    text: str
    # Present only on the final chunk when stream_include_usage=True
    usage: LLMUsage | None = None


# ── Value objects passed across the embedding boundary ────────────────────────


@dataclass(frozen=True)
class EmbeddingResult:
    index: int
    vector: list[float]


# ── Value objects passed across the reranker boundary ─────────────────────────


@dataclass(frozen=True)
class RerankCandidate:
    index: int
    text: str


@dataclass(frozen=True)
class RerankResult:
    index: int
    score: float


# ── Value objects passed across the storage boundary ──────────────────────────


@dataclass(frozen=True)
class UploadResult:
    key: str
    url: str
    size_bytes: int


# ── Provider protocols ─────────────────────────────────────────────────────────


@runtime_checkable
class LLMProvider(Protocol):
    """Streaming and non-streaming text generation."""

    def generate_stream(
        self,
        messages: list[LLMMessage],
        config: GenerationConfig,
    ) -> AsyncIterator[StreamChunk]:
        """Stream text chunks. The final chunk may include usage metadata."""
        ...

    async def generate(
        self,
        messages: list[LLMMessage],
        config: GenerationConfig,
    ) -> str:
        """Non-streaming generation. Returns the complete response text."""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Dense vector embeddings."""

    async def embed(
        self,
        texts: list[str],
        model_id: str,
    ) -> list[EmbeddingResult]:
        """Embed a batch of texts. Returns one result per input, in order."""
        ...


@runtime_checkable
class RerankProvider(Protocol):
    """Cross-encoder reranking of retrieval candidates."""

    async def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        model_id: str,
        top_n: int,
    ) -> list[RerankResult]:
        """Rerank candidates by relevance to the query.

        Returns up to top_n results sorted by descending score.
        """
        ...


@runtime_checkable
class StorageProvider(Protocol):
    """Immutable object storage for source snapshots."""

    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str,
    ) -> UploadResult:
        """Upload bytes to the given key. Overwrites if key exists."""
        ...

    async def download(self, key: str) -> bytes:
        """Download the object at key. Raises KeyError if not found."""
        ...

    async def delete(self, key: str) -> None:
        """Delete the object at key. No-op if key does not exist."""
        ...

    async def exists(self, key: str) -> bool:
        """Return True if the key exists in storage."""
        ...


# ── Repository protocols ───────────────────────────────────────────────────────


@runtime_checkable
class SourceRepository(Protocol):
    """Persistence for ApiSource entities."""

    async def get(self, source_id: UUID) -> ApiSource | None:
        """Return the source or None if not found."""
        ...

    async def list_by_workspace(self, workspace_id: UUID) -> list[ApiSource]:
        """Return all sources in a workspace."""
        ...

    async def save(self, source: ApiSource) -> None:
        """Insert or update a source record."""
        ...


@runtime_checkable
class RevisionRepository(Protocol):
    """Persistence for SourceRevision entities."""

    async def get(self, revision_id: UUID) -> SourceRevision | None:
        """Return the revision or None if not found."""
        ...

    async def get_active(self, source_id: UUID) -> SourceRevision | None:
        """Return the currently active revision for a source, or None."""
        ...

    async def get_by_content_hash(
        self, source_id: UUID, content_hash: str
    ) -> SourceRevision | None:
        """Return an existing revision with the same content hash, or None."""
        ...

    async def save(self, revision: SourceRevision) -> None:
        """Insert or update a revision record."""
        ...

    async def activate(self, revision_id: UUID) -> None:
        """Mark revision ACTIVE and supersede all previous active revisions.

        This must be atomic — either both writes succeed or neither does.
        """
        ...


@runtime_checkable
class JobRepository(Protocol):
    """Persistence for IngestionJob entities."""

    async def get(self, job_id: UUID) -> IngestionJob | None:
        """Return the job or None if not found."""
        ...

    async def get_by_revision(self, revision_id: UUID) -> IngestionJob | None:
        """Return the most recent job for a revision, or None."""
        ...

    async def save(self, job: IngestionJob) -> None:
        """Insert or update a job record."""
        ...


@runtime_checkable
class OperationRepository(Protocol):
    """Persistence for ApiOperation entities."""

    async def get(self, operation_id: UUID) -> ApiOperation | None:
        """Return the operation or None if not found."""
        ...

    async def list_by_revision(self, revision_id: UUID) -> list[ApiOperation]:
        """Return all operations for a revision."""
        ...

    async def find_by_method_path(
        self, revision_id: UUID, method: str, path_normalized: str
    ) -> ApiOperation | None:
        """Exact lookup by method and normalized path."""
        ...

    async def save_many(self, operations: list[ApiOperation]) -> None:
        """Bulk insert operations. On conflict on logical_key, skip (idempotent)."""
        ...


@runtime_checkable
class SchemaRepository(Protocol):
    """Persistence for ApiSchema entities."""

    async def get(self, schema_id: UUID) -> ApiSchema | None:
        """Return the schema or None if not found."""
        ...

    async def list_by_revision(self, revision_id: UUID) -> list[ApiSchema]:
        """Return all schemas for a revision."""
        ...

    async def save_many(self, schemas: list[ApiSchema]) -> None:
        """Bulk insert schemas. On conflict on logical_key, skip (idempotent)."""
        ...


@runtime_checkable
class AuthSchemeRepository(Protocol):
    """Persistence for AuthScheme entities."""

    async def list_by_revision(self, revision_id: UUID) -> list[AuthScheme]:
        """Return all auth schemes for a revision."""
        ...

    async def save_many(self, schemes: list[AuthScheme]) -> None:
        """Bulk insert auth schemes. On conflict on name+revision, skip (idempotent)."""
        ...
