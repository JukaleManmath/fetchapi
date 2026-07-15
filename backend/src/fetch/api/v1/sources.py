"""Source management endpoints.

POST /v1/sources/openapi/upload  — upload an OpenAPI file
POST /v1/sources/openapi/url     — ingest from a remote URL
GET  /v1/sources                 — list all sources in the workspace
GET  /v1/sources/{source_id}     — get one source with its active revision status
GET  /v1/jobs/{job_id}           — poll an ingestion job's current stage
"""

from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, HttpUrl

from fetch.api.dependencies import get_settings_dep, get_workspace_id
from fetch.application.sources.service import CreateSourceService
from fetch.config import get_settings
from fetch.domain.enums import IngestionStage, RevisionStatus
from fetch.infrastructure.db.repositories import (
    PgJobRepository,
    PgRevisionRepository,
    PgSourceRepository,
)
from fetch.infrastructure.db.session import get_session

router = APIRouter(prefix="/v1", tags=["sources"])


# ── Request / response models ─────────────────────────────────────────────────


class SourceResponse(BaseModel):
    source_id: UUID
    name: str
    source_type: str
    active_revision_id: UUID | None
    active_api_title: str | None
    active_api_version: str | None
    created_at: str


class IngestResponse(BaseModel):
    source_id: UUID
    revision_id: UUID
    job_id: UUID | None
    is_duplicate: bool
    message: str


class JobResponse(BaseModel):
    job_id: UUID
    source_id: UUID
    revision_id: UUID
    stage: str
    attempt: int
    error_message: str | None
    created_at: str
    updated_at: str
    completed_at: str | None


class UrlIngestRequest(BaseModel):
    name: str
    url: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/sources/openapi/upload",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload an OpenAPI file for ingestion",
)
async def upload_openapi(
    name: str = Form(...),
    file: UploadFile = File(...),
) -> IngestResponse:
    """Upload an OpenAPI 3.0 or 3.1 file (YAML or JSON).

    Returns 202 immediately. Poll GET /v1/jobs/{job_id} for progress.
    """
    settings = get_settings()
    content = await file.read()

    if len(content) > settings.upload.max_file_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "FILE_TOO_LARGE",
                "message": f"File exceeds maximum size of {settings.upload.max_file_bytes} bytes.",
            },
        )

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "EMPTY_FILE", "message": "Uploaded file is empty."},
        )

    workspace_id = get_workspace_id()
    svc = CreateSourceService(workspace_id)
    result = await svc.from_upload(
        name=name,
        file_content=content,
        original_filename=file.filename or "openapi.yaml",
    )

    return IngestResponse(
        source_id=result.source_id,
        revision_id=result.revision_id,
        job_id=result.job_id,
        is_duplicate=result.is_duplicate,
        message="Duplicate — existing active revision returned."
        if result.is_duplicate
        else "Ingestion started.",
    )


@router.post(
    "/sources/openapi/url",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest an OpenAPI spec from a remote URL",
)
async def ingest_openapi_url(body: UrlIngestRequest) -> IngestResponse:
    """Provide a public URL to an OpenAPI 3.0 or 3.1 spec.

    The spec is fetched, validated, and indexed in the background.
    Returns 202 immediately. Poll GET /v1/jobs/{job_id} for progress.
    """
    workspace_id = get_workspace_id()
    svc = CreateSourceService(workspace_id)
    result = await svc.from_url(name=body.name, url=body.url)

    return IngestResponse(
        source_id=result.source_id,
        revision_id=result.revision_id,
        job_id=result.job_id,
        is_duplicate=result.is_duplicate,
        message="Ingestion started.",
    )


@router.get(
    "/sources",
    response_model=list[SourceResponse],
    summary="List all sources in the workspace",
)
async def list_sources() -> list[SourceResponse]:
    workspace_id = get_workspace_id()
    async with get_session() as session:
        source_repo = PgSourceRepository(session)
        rev_repo = PgRevisionRepository(session)
        sources = await source_repo.list_by_workspace(workspace_id)

        results = []
        for source in sources:
            active_rev = await rev_repo.get_active(source.id)
            results.append(
                SourceResponse(
                    source_id=source.id,
                    name=source.name,
                    source_type=source.source_type.value,
                    active_revision_id=active_rev.id if active_rev else None,
                    active_api_title=active_rev.api_title if active_rev else None,
                    active_api_version=active_rev.api_version if active_rev else None,
                    created_at=source.created_at.isoformat(),
                )
            )
    return results


@router.get(
    "/sources/{source_id}",
    response_model=SourceResponse,
    summary="Get a single source",
)
async def get_source(source_id: UUID) -> SourceResponse:
    workspace_id = get_workspace_id()
    async with get_session() as session:
        source_repo = PgSourceRepository(session)
        rev_repo = PgRevisionRepository(session)

        source = await source_repo.get(source_id)
        if source is None or source.workspace_id != workspace_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SOURCE_NOT_FOUND", "message": "Source not found."},
            )

        active_rev = await rev_repo.get_active(source_id)

    return SourceResponse(
        source_id=source.id,
        name=source.name,
        source_type=source.source_type.value,
        active_revision_id=active_rev.id if active_rev else None,
        active_api_title=active_rev.api_title if active_rev else None,
        active_api_version=active_rev.api_version if active_rev else None,
        created_at=source.created_at.isoformat(),
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Poll an ingestion job",
)
async def get_job(job_id: UUID) -> JobResponse:
    workspace_id = get_workspace_id()
    async with get_session() as session:
        repo = PgJobRepository(session)
        job = await repo.get(job_id)

    if job is None or job.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOB_NOT_FOUND", "message": "Job not found."},
        )

    return JobResponse(
        job_id=job.id,
        source_id=job.source_id,
        revision_id=job.revision_id,
        stage=job.stage.value,
        attempt=job.attempt,
        error_message=job.error_message,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )
