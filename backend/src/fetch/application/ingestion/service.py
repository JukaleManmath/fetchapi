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

import asyncio
import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx

from fetch.config import get_settings
from fetch.domain.entities import IngestionJob, SourceRevision
from fetch.domain.enums import IngestionStage, RevisionStatus
from fetch.domain.errors import IngestionError
from fetch.infrastructure.db.repositories import (
    PgAuthSchemeRepository,
    PgErrorRepository,
    PgExampleRepository,
    PgJobRepository,
    PgOperationRepository,
    PgRevisionRepository,
    PgSchemaRepository,
    PgServerRepository,
)
from fetch.infrastructure.db.session import get_session
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

    resolved_doc, openapi_version = await load_and_resolve(
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

    # ── ACTIVE: atomic revision activation ───────────────────────────────────
    # (CHUNKING, EMBEDDING, INDEXING, VERIFYING are Phase 2 — skip for now)
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
        },
    )
