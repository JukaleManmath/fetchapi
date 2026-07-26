"""Job management endpoints.

POST /v1/jobs/{job_id}/cancel  — cancel an active ingestion job
GET  /v1/jobs/{job_id}/logs    — list structured ingestion stage logs for a job
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from fetch.application.ingestion.service import (
    _update_job_stage,
    cancel_task,
)
from fetch.domain.enums import IngestionStage
from fetch.infrastructure.db.repositories import PgJobLogRepository, PgJobRepository
from fetch.infrastructure.db.session import get_session

router = APIRouter(prefix="/v1", tags=["jobs"])


class JobLogResponse(BaseModel):
    id: UUID
    job_id: UUID
    created_at: str
    stage: str | None
    level: str
    message: str


@router.post("/jobs/{job_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_job(job_id: UUID) -> dict[str, bool]:
    """Cancel a running ingestion task.

    Returns 404 if no active ingestion is found for the given job.
    """
    cancelled = cancel_task(job_id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active ingestion for this job",
        )
    await _update_job_stage(job_id, IngestionStage.CANCELLED)
    return {"cancelled": True}


@router.get(
    "/jobs/{job_id}/logs",
    response_model=list[JobLogResponse],
    summary="List structured ingestion stage logs for a job",
)
async def get_job_logs(job_id: UUID) -> list[JobLogResponse]:
    """Return all log entries for the given job, sorted by created_at ASC."""
    async with get_session() as session:
        job_repo = PgJobRepository(session)
        job = await job_repo.get(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "JOB_NOT_FOUND", "message": "Job not found."},
            )
        log_repo = PgJobLogRepository(session)
        logs = await log_repo.list_by_job(job_id)

    return [
        JobLogResponse(
            id=log.id,
            job_id=log.job_id,
            created_at=log.created_at.isoformat(),
            stage=log.stage,
            level=log.level,
            message=log.message,
        )
        for log in logs
    ]
