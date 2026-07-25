"""Integration tests for the Phase 3 retrieval pipeline.

Requires real PostgreSQL, Qdrant, and MinIO — run with:
    make test-integration

Tests verify each stage of the retrieval pipeline in isolation, then the
full service wired end-to-end.

Tests 1-4 and 8 are pure DB tests and do NOT call NIM.
Tests 5, 6, 7, and 9 require a live NIM API key (EMBEDDINGS_API_KEY /
RERANKER_API_KEY).

The module is skipped entirely when the NIM embedding API key is absent so
CI environments without credentials do not fail on import.
"""

import asyncio
import pathlib
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from fetch.application.retrieval.bm25_retriever import (
    BM25RetrievalConfig,
    BM25Retriever,
)
from fetch.application.retrieval.dense_retriever import (
    DenseRetrievalConfig,
    DenseRetriever,
)
from fetch.application.retrieval.exact_lookup import ExactLookup
from fetch.application.retrieval.expander import ExpansionConfig, RelationshipExpander
from fetch.application.retrieval.fusion import FusionConfig, RRFFusion
from fetch.application.retrieval.normalizer import QueryNormalizer
from fetch.application.retrieval.packer import ContextPacker
from fetch.application.retrieval.reranker import RerankConfig, RetrievalReranker
from fetch.application.retrieval.service import RetrievalConfig, RetrievalService
from fetch.application.sources.service import CreateSourceService
from fetch.config import get_settings
from fetch.domain.entities import IngestionJob, QueryRun
from fetch.domain.enums import IngestionStage, QueryWorkflow, SupportStatus
from fetch.infrastructure.db.repositories import (
    PgChunkRelationRepository,
    PgChunkRepository,
    PgEmbeddingProfileRepository,
    PgJobRepository,
    PgOperationRepository,
    PgQueryRunRepository,
    PgSchemaRepository,
)
from fetch.infrastructure.db.session import close_db, get_session, init_db
from fetch.infrastructure.llm.nvidia_nim import NvidiaNimProvider
from fetch.infrastructure.qdrant.repository import QdrantRepository

# ── Module-level skip when NIM key is absent ──────────────────────────────────

pytestmark = [pytest.mark.integration]

_settings = get_settings()
_nim_key = _settings.embeddings.api_key.get_secret_value()
if not _nim_key:
    pytest.skip(
        "NIM API key not set (EMBEDDINGS_API_KEY) — skipping retrieval integration tests",
        allow_module_level=True,
    )

_reranker_key = _settings.reranker.api_key.get_secret_value()
_RERANKER_AVAILABLE = bool(_reranker_key) and _reranker_key != "your-nvidia-nim-api-key"

# ── Constants ─────────────────────────────────────────────────────────────────

WORKSPACE_ID: UUID = _settings.app.workspace_id

PETSTORE_PATH = (
    pathlib.Path(__file__).parent.parent.parent.parent.parent
    / "examples"
    / "petstore"
    / "openapi.yaml"
)

_EMBEDDING_PROFILE_VERSION = "v1"  # human-readable version key


async def _get_profile_uuid() -> str:
    """Return the UUID (as str) of the 'v1' embedding profile from DB.

    The UUID is what gets stored in Qdrant's payload as embedding_profile_version.
    """
    async with get_session() as session:
        repo = PgEmbeddingProfileRepository(session)
        record = await repo.get_by_version(_EMBEDDING_PROFILE_VERSION)
    if record is None:
        raise RuntimeError("Embedding profile 'v1' not found in DB — run ingestion first")
    return str(record.id)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def db_lifecycle():  # type: ignore[return]
    """Initialize the DB connection pool before each test and close after."""
    init_db()
    yield
    await close_db()


# ── Prerequisite helper ───────────────────────────────────────────────────────


async def _wait_for_job(
    job_id: UUID,
    timeout: float = 120.0,
    poll: float = 1.0,
) -> IngestionJob:
    """Poll until the ingestion job reaches a terminal stage or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        async with get_session() as session:
            job = await PgJobRepository(session).get(job_id)
        if job and job.stage in (IngestionStage.ACTIVE, IngestionStage.FAILED):
            return job
        await asyncio.sleep(poll)
    raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")


async def _ingest_petstore() -> tuple[UUID, UUID]:
    """Ingest the petstore fixture and return (source_id, revision_id).

    Raises AssertionError when the job does not reach ACTIVE.
    """
    content = PETSTORE_PATH.read_bytes()
    svc = CreateSourceService(WORKSPACE_ID)
    result = await svc.from_upload(
        name="Petstore Retrieval Integration Test",
        file_content=content,
        original_filename="openapi.yaml",
    )
    job = await _wait_for_job(result.job_id)
    assert job.stage == IngestionStage.ACTIVE, (
        f"Petstore ingestion did not reach ACTIVE: {job.stage} — {job.error_message}"
    )
    return result.source_id, result.revision_id


def _make_nim_provider() -> NvidiaNimProvider:
    """Construct a NvidiaNimProvider using settings values."""
    return NvidiaNimProvider(
        api_key=_nim_key,
        base_url=_settings.embeddings.base_url,
        timeout_seconds=60.0,
    )


# ── Test 1 — QueryNormalizer ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_normalizer_extracts_method_and_path() -> None:
    """QueryNormalizer must extract HTTP method and path without LLM involvement.

    This is a pure in-process test — no DB or Qdrant required.  It lives
    here to confirm the normalizer behaves correctly under the same pytest
    setup as the integration tests, catching any import-time breakage.
    """
    normalizer = QueryNormalizer()
    result = normalizer.normalize("How do I GET /pets?")

    assert result.method == "GET"
    assert result.path_pattern == "/pets"


# ── Test 2 — ExactLookup finds operation ─────────────────────────────────────


@pytest.mark.asyncio
async def test_exact_lookup_finds_operation_by_method_path() -> None:
    """ExactLookup must resolve a GET /pet/findByStatus query to an operation entity.

    After ingestion the canonical operation table contains petstore paths.
    The lookup must find the operation without any vector search.
    """
    _source_id, revision_id = await _ingest_petstore()

    normalizer = QueryNormalizer()
    normalized = normalizer.normalize("How do I GET /pet/findByStatus?")

    async with get_session() as session:
        op_repo = PgOperationRepository(session)
        schema_repo = PgSchemaRepository(session)
        chunk_repo = PgChunkRepository(session)

        lookup = ExactLookup(op_repo, schema_repo, chunk_repo)
        result = await lookup.lookup(normalized, revision_id, WORKSPACE_ID)

    assert result.matched_entity_type == "operation", (
        f"Expected 'operation', got {result.matched_entity_type!r}"
    )
    assert result.matched_entity_id is not None
    assert isinstance(result.matched_entity_id, UUID)


# ── Test 3 — ExactLookup finds schema ────────────────────────────────────────


@pytest.mark.asyncio
async def test_exact_lookup_finds_schema_by_name() -> None:
    """ExactLookup must fall through to schema matching when no operation matches.

    The petstore spec defines an 'ApiResponse' schema in its components.  A query
    containing the word 'ApiResponse' (PascalCase compound) must resolve to it.
    """
    _source_id, revision_id = await _ingest_petstore()

    normalizer = QueryNormalizer()
    # No method or path — forces the lookup to fall through to schema matching.
    normalized = normalizer.normalize("What fields does the ApiResponse schema have?")

    async with get_session() as session:
        op_repo = PgOperationRepository(session)
        schema_repo = PgSchemaRepository(session)
        chunk_repo = PgChunkRepository(session)

        lookup = ExactLookup(op_repo, schema_repo, chunk_repo)
        result = await lookup.lookup(normalized, revision_id, WORKSPACE_ID)

    assert result.matched_entity_type == "schema", (
        f"Expected 'schema', got {result.matched_entity_type!r}"
    )
    assert result.matched_entity_id is not None


# ── Test 4 — PgChunkRepository.find_chunk_ids_by_entity ──────────────────────


@pytest.mark.asyncio
async def test_pg_chunk_repository_find_by_entity() -> None:
    """Chunks for a known operation must be present after ingestion.

    Verifies that the chunking stage persisted at least one chunk whose
    entity_type is 'operation' and whose entity_id matches a real operation.
    """
    _source_id, revision_id = await _ingest_petstore()

    async with get_session() as session:
        op_repo = PgOperationRepository(session)
        ops = await op_repo.list_by_revision(revision_id)
        assert ops, "No operations found after ingestion"

        operation = ops[0]
        chunk_repo = PgChunkRepository(session)
        chunk_ids = await chunk_repo.find_chunk_ids_by_entity(
            revision_id, "operation", operation.id
        )

    assert chunk_ids, (
        f"No chunks found for operation {operation.id} in revision {revision_id}"
    )
    assert all(isinstance(cid, UUID) for cid in chunk_ids)


# ── Test 5 — Dense retrieval returns hits ────────────────────────────────────


@pytest.mark.asyncio
async def test_qdrant_search_dense_returns_hits() -> None:
    """Dense search must return scored ChunkHit objects after indexing.

    The ingestion pipeline embeds all chunks and upserts them into Qdrant.
    After a successful ingest, a query vector for 'list all pets' should
    find at least one hit within the revision's tenant partition.
    """
    _source_id, revision_id = await _ingest_petstore()
    profile_uuid = await _get_profile_uuid()

    provider = _make_nim_provider()
    try:
        embedding_results = await provider.embed(
            ["list all pets"],
            model_id=_settings.embeddings.model_id,
            input_type="query",
        )
    finally:
        await provider.aclose()

    assert embedding_results, "NIM embed returned no results"
    query_vector = embedding_results[0].vector

    qdrant = QdrantRepository()
    hits = await qdrant.search_dense(
        query_vector=query_vector,
        revision_id=revision_id,
        workspace_id=WORKSPACE_ID,
        embedding_profile_version=profile_uuid,
        top_k=5,
    )

    assert hits, "Dense search returned no hits"
    assert all(h.score > 0 for h in hits), "Expected all hit scores to be positive"
    assert all(
        h.payload.get("workspace_id") == str(WORKSPACE_ID) for h in hits
    ), "All hits must belong to the queried workspace"
    assert all(
        h.payload.get("revision_id") == str(revision_id) for h in hits
    ), "All hits must belong to the queried revision"


# ── Test 6 — BM25 retrieval returns hits ─────────────────────────────────────


@pytest.mark.asyncio
async def test_qdrant_search_bm25_returns_hits() -> None:
    """BM25 full-text search must find chunks containing the token 'pet'.

    All indexed chunk texts contain at least some API terminology.  The word
    'pet' should match multiple chunks in the petstore index.
    """
    _source_id, revision_id = await _ingest_petstore()
    profile_uuid = await _get_profile_uuid()

    qdrant = QdrantRepository()
    hits = await qdrant.search_bm25(
        query_text="pet",
        revision_id=revision_id,
        workspace_id=WORKSPACE_ID,
        embedding_profile_version=profile_uuid,
        top_k=5,
    )

    assert hits, "BM25 search returned no hits for token 'pet'"
    assert all(h.score == 1.0 for h in hits), (
        "BM25 hits must carry score=1.0 (Qdrant text index does not score)"
    )


# ── Test 7 — RRF fusion combines both retrieval lists ────────────────────────


@pytest.mark.asyncio
async def test_rrf_fusion_combines_dense_and_bm25() -> None:
    """RRF fusion must produce a non-empty merged ranking from both retrievers.

    Dense and BM25 results are retrieved independently and then fused.  The
    fused list must be non-empty and its length must not exceed top_k.
    """
    _source_id, revision_id = await _ingest_petstore()
    profile_uuid = await _get_profile_uuid()

    provider = _make_nim_provider()
    try:
        embedding_results = await provider.embed(
            ["list pets"],
            model_id=_settings.embeddings.model_id,
            input_type="query",
        )
    finally:
        await provider.aclose()

    assert embedding_results
    query_vector = embedding_results[0].vector

    qdrant = QdrantRepository()
    top_k = 10

    dense_hits = await qdrant.search_dense(
        query_vector=query_vector,
        revision_id=revision_id,
        workspace_id=WORKSPACE_ID,
        embedding_profile_version=profile_uuid,
        top_k=top_k,
    )
    bm25_hits = await qdrant.search_bm25(
        query_text="pet",
        revision_id=revision_id,
        workspace_id=WORKSPACE_ID,
        embedding_profile_version=profile_uuid,
        top_k=top_k,
    )

    config = FusionConfig(top_k=top_k)
    fused = RRFFusion().fuse([dense_hits, bm25_hits], config)

    assert fused, "RRF fusion returned no results"
    assert len(fused) <= top_k, (
        f"Fused list length {len(fused)} exceeds top_k {top_k}"
    )


# ── Test 8 — PgQueryRunRepository save and get ────────────────────────────────


@pytest.mark.asyncio
async def test_pg_query_run_repository_save_and_get() -> None:
    """A persisted QueryRun must be retrievable by its ID with matching fields.

    This test does NOT ingest petstore — it builds a minimal QueryRun with
    placeholder UUIDs and verifies the round-trip through the DB repository.
    """
    run_id = uuid4()
    source_id = uuid4()
    revision_id = uuid4()

    run = QueryRun(
        id=run_id,
        workspace_id=WORKSPACE_ID,
        source_id=source_id,
        revision_id=revision_id,
        workflow=QueryWorkflow.DOC_QA,
        question="How do I list all pets?",
        answer=None,
        citations=[],
        support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
        retrieval_ms=42,
        dense_candidate_count=5,
        bm25_candidate_count=3,
        fused_candidate_count=7,
        reranked_candidate_count=4,
        expanded_candidate_count=4,
        exact_match_found=False,
        created_at=datetime.now(UTC),
    )

    async with get_session() as session:
        repo = PgQueryRunRepository(session)
        await repo.save(run)
        retrieved = await repo.get(run_id)

    assert retrieved is not None, "QueryRun not found after save"
    assert retrieved.question == run.question
    assert retrieved.citations == run.citations
    assert retrieved.workflow == QueryWorkflow.DOC_QA
    assert retrieved.retrieval_ms == 42
    assert retrieved.dense_candidate_count == 5


# ── Test 9 — Full RetrievalService pipeline ───────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _RERANKER_AVAILABLE,
    reason="Reranker API key not configured (RERANKER_API_KEY is placeholder)",
)
async def test_full_retrieval_service_pipeline() -> None:
    """End-to-end retrieval pipeline must produce a populated PackedContext.

    All real dependencies are wired from settings.  The test asserts that:
    - citations list is non-empty (evidence was found and packed)
    - context_text includes at least one source label ([S1])
    - query_run.retrieval_ms > 0 (pipeline actually ran and timed itself)
    - query_run.dense_candidate_count > 0 (dense retriever found something)
    - the saved QueryRun is retrievable from the DB
    """
    source_id, revision_id = await _ingest_petstore()
    profile_uuid = await _get_profile_uuid()

    provider = _make_nim_provider()

    try:
        async with get_session() as session:
            op_repo = PgOperationRepository(session)
            schema_repo = PgSchemaRepository(session)
            chunk_repo = PgChunkRepository(session)
            relation_repo = PgChunkRelationRepository(session)
            query_run_repo = PgQueryRunRepository(session)

            service = RetrievalService(
                normalizer=QueryNormalizer(),
                exact_lookup=ExactLookup(op_repo, schema_repo, chunk_repo),
                dense_retriever=DenseRetriever(provider, QdrantRepository()),
                bm25_retriever=BM25Retriever(QdrantRepository()),
                fusion=RRFFusion(),
                reranker=RetrievalReranker(provider),
                expander=RelationshipExpander(relation_repo, chunk_repo),
                packer=ContextPacker(),
                query_run_repo=query_run_repo,
            )

            config = RetrievalConfig(
                dense=DenseRetrievalConfig(
                    model_id=_settings.embeddings.model_id,
                    top_k=_settings.retrieval.dense_candidate_limit,
                    embedding_profile_version=profile_uuid,
                ),
                bm25=BM25RetrievalConfig(
                    top_k=_settings.retrieval.sparse_candidate_limit,
                    embedding_profile_version=profile_uuid,
                ),
                fusion=FusionConfig(
                    top_k=_settings.retrieval.fused_candidate_limit,
                ),
                rerank=RerankConfig(
                    model_id=_settings.reranker.model_id,
                    top_n=_settings.retrieval.rerank_limit,
                ),
                expansion=ExpansionConfig(
                    max_expanded_chunks=5,
                ),
            )

            packed_context, query_run = await service.retrieve(
                question="How do I list all pets?",
                source_id=source_id,
                revision_id=revision_id,
                workspace_id=WORKSPACE_ID,
                workflow=QueryWorkflow.DOC_QA,
                config=config,
            )

            # Assert packed context
            assert packed_context.citations, "Expected non-empty citations"
            assert "[S1]" in packed_context.context_text, (
                "Expected [S1] source label in context_text"
            )

            # Assert query run trace fields
            assert query_run.retrieval_ms is not None, "retrieval_ms must not be None"
            assert query_run.retrieval_ms > 0, "retrieval_ms must be positive"
            assert query_run.dense_candidate_count is not None, (
                "dense_candidate_count must not be None"
            )
            assert query_run.dense_candidate_count > 0, (
                "Expected dense retriever to find at least one candidate"
            )

            # Assert the saved QueryRun is retrievable
            saved = await query_run_repo.get(query_run.id)
            assert saved is not None, "Saved QueryRun was not found in the DB"
            assert saved.question == query_run.question
            assert saved.dense_candidate_count == query_run.dense_candidate_count

    finally:
        await provider.aclose()
