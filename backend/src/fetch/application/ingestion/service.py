"""Ingestion pipeline service.

Runs as an asyncio background task started by CreateSourceService.
Owns the full ingestion state machine:

    QUEUED → FETCHING → SNAPSHOTTING → PARSING → VALIDATING
           → NORMALIZING → ACTIVE
    Any stage → FAILED on unhandled error.

On failure the revision stays BUILDING/FAILED — it is never activated.
The caller (CreateSourceService) can retry by calling start_ingestion again,
which creates a new job record and starts a new task.
"""

import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx

from fetch.config import get_settings
from fetch.domain.entities import Chunk
from fetch.domain.enums import IngestionStage, RevisionStatus
from fetch.domain.errors import IngestionError
from fetch.infrastructure.db.repositories import (
    PgAuthSchemeRepository,
    PgChunkRepository,
    PgErrorRepository,
    PgExampleRepository,
    PgJobRepository,
    PgOperationRepository,
    PgRevisionRepository,
    PgSchemaRepository,
    PgServerRepository,
)
from fetch.infrastructure.db.session import get_session
from fetch.infrastructure.embeddings.chunker import (
    build_auth_chunk,
    build_chunk_relations,
    build_error_chunk,
    build_operation_chunk,
    build_schema_chunk,
)
from fetch.infrastructure.embeddings.profile import (
    EmbeddingProfile,
    get_or_create_profile,
)
from fetch.infrastructure.llm.nvidia_nim import NvidiaNimProvider
from fetch.infrastructure.openapi.extractor import (
    extract_api_title,
    extract_api_version,
    extract_auth_schemes,
    extract_error_definitions,
    extract_examples,
    extract_operations,
    extract_schemas,
    extract_servers,
)
from fetch.infrastructure.openapi.validator import load_and_resolve
from fetch.infrastructure.qdrant.repository import QdrantRepository
from fetch.infrastructure.storage.minio import MinioStorageProvider

logger = logging.getLogger(__name__)


async def _update_job_stage(
    job_id: UUID,
    stage: IngestionStage,
    error_message: str | None = None,
) -> None:
    """Persist a job stage transition. Opens its own short session."""
    async with get_session() as session:
        repo = PgJobRepository(session)
        job = await repo.get(job_id)
        if job is None:
            logger.error("ingestion_job_not_found", extra={"job_id": str(job_id)})
            return
        job.stage = stage
        job.updated_at = datetime.now(UTC)
        job.error_message = error_message
        if stage == IngestionStage.ACTIVE:
            job.completed_at = datetime.now(UTC)
        if stage == IngestionStage.FAILED:
            job.completed_at = datetime.now(UTC)
        await repo.save(job)


async def run_ingestion(
    job_id: UUID,
    revision_id: UUID,
    source_id: UUID,
    workspace_id: UUID,
) -> None:
    """Full ingestion pipeline. Designed to run as asyncio.create_task().

    Catches all exceptions to ensure the job is always marked FAILED
    rather than silently disappearing.
    """
    logger.info(
        "ingestion_started",
        extra={
            "job_id": str(job_id),
            "revision_id": str(revision_id),
            "source_id": str(source_id),
        },
    )

    try:
        await _run_pipeline(job_id, revision_id, source_id, workspace_id)
    except IngestionError as exc:
        logger.warning(
            "ingestion_failed",
            extra={
                "job_id": str(job_id),
                "revision_id": str(revision_id),
                "error": str(exc),
            },
        )
        await _mark_failed(job_id, revision_id, str(exc))
    except Exception as exc:
        logger.exception(
            "ingestion_unexpected_error",
            extra={"job_id": str(job_id), "revision_id": str(revision_id)},
        )
        await _mark_failed(job_id, revision_id, f"Unexpected error: {exc}")


async def _mark_failed(job_id: UUID, revision_id: UUID, reason: str) -> None:
    now = datetime.now(UTC)
    async with get_session() as session:
        rev_repo = PgRevisionRepository(session)
        revision = await rev_repo.get(revision_id)
        if revision:
            revision.status = RevisionStatus.FAILED
            revision.failed_at = now
            revision.failure_reason = reason
            await rev_repo.save(revision)
    await _update_job_stage(job_id, IngestionStage.FAILED, error_message=reason)


async def _run_pipeline(
    job_id: UUID,
    revision_id: UUID,
    source_id: UUID,
    workspace_id: UUID,
) -> None:
    settings = get_settings()

    # ── FETCHING: load source config and get raw bytes ────────────────────────
    await _update_job_stage(job_id, IngestionStage.FETCHING)

    async with get_session() as session:
        from fetch.infrastructure.db.repositories import PgSourceRepository
        source_repo = PgSourceRepository(session)
        source = await source_repo.get(source_id)
        if source is None:
            raise IngestionError(f"Source {source_id} not found.")

    raw_content: bytes
    source_url: str | None = None

    if source.config_object_key:
        # File upload path — fetch from object storage
        storage = MinioStorageProvider()
        raw_content = await storage.download(source.config_object_key)
    elif source.config_url:
        # URL path — fetch from remote with SSRF protection (reused in validator)
        source_url = source.config_url
        timeout = settings.external_ref.timeout_seconds
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
                response = await client.get(source_url)
                response.raise_for_status()
                raw_content = response.content
        except httpx.HTTPError as exc:
            raise IngestionError(f"Failed to fetch OpenAPI URL: {exc}") from exc
    else:
        raise IngestionError("Source has neither config_object_key nor config_url.")

    # ── SNAPSHOTTING: compute content hash, store snapshot ────────────────────
    await _update_job_stage(job_id, IngestionStage.SNAPSHOTTING)

    content_hash = hashlib.sha256(raw_content).hexdigest()

    # Store snapshot for file-upload sources if not already stored
    snapshot_key: str | None = source.config_object_key
    if not snapshot_key:
        snapshot_key = f"snapshots/{source_id}/{revision_id}.raw"
        storage = MinioStorageProvider()
        content_type = "application/yaml" if raw_content.lstrip()[:1] != b"{" else "application/json"
        await storage.upload(snapshot_key, raw_content, content_type)

    async with get_session() as session:
        rev_repo = PgRevisionRepository(session)
        revision = await rev_repo.get(revision_id)
        if revision is None:
            raise IngestionError(f"Revision {revision_id} not found.")
        revision.content_hash = content_hash
        revision.snapshot_object_key = snapshot_key
        await rev_repo.save(revision)

    # ── PARSING: load YAML/JSON safely ───────────────────────────────────────
    await _update_job_stage(job_id, IngestionStage.PARSING)

    resolved_doc, _openapi_version = await load_and_resolve(
        raw_content,
        source_url=source_url,
        max_aliases=settings.worker.ingestion_max_aliases,
    )

    # ── VALIDATING: already done inside load_and_resolve ─────────────────────
    await _update_job_stage(job_id, IngestionStage.VALIDATING)

    api_version = extract_api_version(resolved_doc)
    api_title = extract_api_title(resolved_doc)

    # ── NORMALIZING: extract canonical entities ───────────────────────────────
    await _update_job_stage(job_id, IngestionStage.NORMALIZING)

    servers = extract_servers(resolved_doc, revision_id)
    auth_schemes = extract_auth_schemes(resolved_doc, revision_id, workspace_id)
    schemas = extract_schemas(
        resolved_doc, revision_id, workspace_id, source_id, api_version
    )
    operations = extract_operations(
        resolved_doc, revision_id, workspace_id, source_id, api_version
    )
    examples = extract_examples(resolved_doc, revision_id, workspace_id)
    error_definitions = extract_error_definitions(operations, revision_id, workspace_id)

    logger.info(
        "ingestion_entities_extracted",
        extra={
            "revision_id": str(revision_id),
            "operations": len(operations),
            "schemas": len(schemas),
            "auth_schemes": len(auth_schemes),
            "servers": len(servers),
            "examples": len(examples),
            "error_definitions": len(error_definitions),
        },
    )

    # ── Persist all canonical entities in one session ─────────────────────────
    async with get_session() as session:
        await PgServerRepository(session).save_many(servers)
        await PgAuthSchemeRepository(session).save_many(auth_schemes)
        await PgSchemaRepository(session).save_many(schemas)
        await PgOperationRepository(session).save_many(operations)
        await PgExampleRepository(session).save_many(examples)
        await PgErrorRepository(session).save_many(error_definitions)

        # Update revision with extracted metadata
        rev_repo = PgRevisionRepository(session)
        revision = await rev_repo.get(revision_id)
        if revision is None:
            raise IngestionError(f"Revision {revision_id} not found after extraction.")
        revision.api_version = api_version
        revision.api_title = api_title
        await rev_repo.save(revision)

    # ── CHUNKING: build text projections from canonical entities ─────────────
    await _update_job_stage(job_id, IngestionStage.CHUNKING)

    async with get_session() as session:
        profile = await get_or_create_profile(session)

    # Build auth and schema chunks first — needed for relation building.
    auth_chunks = [
        build_auth_chunk(a, api_version, source_id, workspace_id, profile)
        for a in auth_schemes
    ]
    schema_chunks = [
        build_schema_chunk(s, api_version, source_id, workspace_id, profile)
        for s in schemas
    ]
    error_chunks = [
        build_error_chunk(e, api_version, source_id, workspace_id, profile)
        for e in error_definitions
    ]

    # Index by entity_id / name for O(1) relation lookup.
    schema_chunks_by_id = {c.entity_id: c for c in schema_chunks}
    auth_chunks_by_name = {
        a.name: c for a, c in zip(auth_schemes, auth_chunks, strict=True)
    }
    # Map error definition -> its chunk for per-operation filtering below.
    error_def_to_chunk = {
        e.id: c for e, c in zip(error_definitions, error_chunks, strict=True)
    }

    op_chunks = []
    all_relations = []
    for op in operations:
        auth_names = [
            name for req in op.security_requirements for name in req
        ]
        op_chunk = build_operation_chunk(
            op, auth_names, api_version, source_id, workspace_id, profile
        )
        op_chunks.append(op_chunk)

        # Only include error chunks that belong to this operation.
        op_error_chunks = {
            e.id: error_def_to_chunk[e.id]
            for e in error_definitions
            if e.operation_id == op.id and e.id in error_def_to_chunk
        }

        relations = build_chunk_relations(
            op_chunk=op_chunk,
            operation=op,
            schema_chunks_by_entity_id=schema_chunks_by_id,
            auth_chunks_by_name=auth_chunks_by_name,
            error_chunks_by_entity_id=op_error_chunks,
        )
        all_relations.extend(relations)

    all_chunks: list[Chunk] = op_chunks + schema_chunks + auth_chunks + error_chunks

    async with get_session() as session:
        chunk_repo = PgChunkRepository(session)
        await chunk_repo.save_many(all_chunks)
        await chunk_repo.save_many_relations(all_relations)

        rev_repo = PgRevisionRepository(session)
        revision = await rev_repo.get(revision_id)
        if revision is None:
            raise IngestionError(f"Revision {revision_id} not found after chunking.")
        revision.expected_chunk_count = len(all_chunks)
        await rev_repo.save(revision)

    logger.info(
        "ingestion_chunking_complete",
        extra={
            "revision_id": str(revision_id),
            "op_chunks": len(op_chunks),
            "schema_chunks": len(schema_chunks),
            "auth_chunks": len(auth_chunks),
            "error_chunks": len(error_chunks),
            "relations": len(all_relations),
        },
    )

    # ── EMBEDDING: generate dense vectors via provider ────────────────────────
    await _update_job_stage(job_id, IngestionStage.EMBEDDING)

    texts = [c.text for c in all_chunks]
    vectors = await _embed_in_batches(texts, profile, settings)

    # ── INDEXING: upsert into Qdrant ──────────────────────────────────────────
    await _update_job_stage(job_id, IngestionStage.INDEXING)

    qdrant = QdrantRepository()
    await qdrant.upsert_chunks(
        all_chunks, vectors, batch_size=settings.embeddings.batch_size
    )

    logger.info(
        "ingestion_indexing_complete",
        extra={"revision_id": str(revision_id), "points_upserted": len(all_chunks)},
    )

    # ── VERIFYING: confirm point count matches expected ───────────────────────
    await _update_job_stage(job_id, IngestionStage.VERIFYING)

    actual_count = await qdrant.count_points(revision_id, workspace_id)

    async with get_session() as session:
        rev_repo = PgRevisionRepository(session)
        revision = await rev_repo.get(revision_id)
        if revision is None:
            raise IngestionError(f"Revision {revision_id} not found after indexing.")
        revision.actual_chunk_count = actual_count
        await rev_repo.save(revision)

    expected_count = len(all_chunks)
    if actual_count != expected_count:
        raise IngestionError(
            f"Qdrant point count mismatch: expected {expected_count}, got {actual_count}. "
            "Revision not activated."
        )

    logger.info(
        "ingestion_verification_passed",
        extra={
            "revision_id": str(revision_id),
            "expected": expected_count,
            "actual": actual_count,
        },
    )

    # ── ACTIVE: atomic revision activation ───────────────────────────────────
    async with get_session() as session:
        rev_repo = PgRevisionRepository(session)
        await rev_repo.activate(revision_id)

    await _update_job_stage(job_id, IngestionStage.ACTIVE)

    logger.info(
        "ingestion_complete",
        extra={
            "job_id": str(job_id),
            "revision_id": str(revision_id),
            "source_id": str(source_id),
            "api_title": api_title,
            "api_version": api_version,
            "operations": len(operations),
            "chunks": len(all_chunks),
        },
    )


async def _embed_in_batches(
    texts: list[str],
    profile: EmbeddingProfile,
    settings: object,
) -> list[list[float]]:
    """Embed all texts in bounded batches using the configured provider.

    Returns a flat list of dense vectors in the same order as texts.
    CPU-bound reranking is excluded here — this is I/O-bound embedding only.
    """
    provider = NvidiaNimProvider(
        api_key=settings.embeddings.api_key.get_secret_value(),
        base_url=settings.embeddings.base_url,
    )
    batch_size: int = settings.embeddings.batch_size
    all_vectors: list[list[float]] = []

    for batch_start in range(0, len(texts), batch_size):
        batch = texts[batch_start : batch_start + batch_size]
        results = await provider.embed(batch, model_id=profile.dense_model_id)
        # Results are returned in index order.
        sorted_results = sorted(results, key=lambda r: r.index)
        all_vectors.extend(r.vector for r in sorted_results)

        logger.debug(
            "embedding_batch_complete",
            extra={
                "batch_start": batch_start,
                "batch_size": len(batch),
                "model_id": profile.dense_model_id,
            },
        )

    return all_vectors
