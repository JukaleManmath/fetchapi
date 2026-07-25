"""Request validation / curl debugger endpoint.

POST /v1/validate/curl   — validate a curl command
POST /v1/validate/request — validate a structured HTTP request
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from fetch.api.dependencies import get_llm_provider, get_workspace_id
from fetch.application.validation.error_lookup import ErrorStatusLookup
from fetch.application.validation.service import ValidationService
from fetch.application.validation.validators import (
    BodyValidator,
    HeaderValidator,
    ParameterValidator,
)
from fetch.config import get_settings
from fetch.domain.entities import ParsedRequest
from fetch.domain.errors import CurlParseError
from fetch.domain.protocols import LLMProvider
from fetch.infrastructure.db.repositories import (
    PgAuthSchemeRepository,
    PgDiagnosticRunRepository,
    PgErrorRepository,
    PgOperationRepository,
    PgRevisionRepository,
    PgServerRepository,
    PgSourceRepository,
)
from fetch.infrastructure.db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/validate", tags=["validation"])


# ── Request models ─────────────────────────────────────────────────────────────


class ValidateCurlRequest(BaseModel):
    source_id: UUID
    curl_command: str = Field(..., min_length=1, max_length=10_000)
    received_status_code: str | None = Field(None, pattern=r"^\d{3}$")


class ValidateRequestBody(BaseModel):
    source_id: UUID
    method: str = Field(..., min_length=1, max_length=10)
    url: str = Field(..., min_length=1, max_length=2_000)
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, object] | None = None
    received_status_code: str | None = Field(None, pattern=r"^\d{3}$")


# ── Response models ────────────────────────────────────────────────────────────


class FindingOut(BaseModel):
    severity: str
    category: str
    message: str
    field: str | None
    canonical_value: str | None


class EndpointMatchOut(BaseModel):
    match_confidence: str
    path: str | None
    method: str | None
    path_params: dict[str, str]


class ErrorStatusOut(BaseModel):
    status_code: str
    is_documented: bool
    matched_count: int


class DiagnosticResponse(BaseModel):
    diagnostic_run_id: UUID
    is_valid: bool
    support_status: str
    endpoint_match: EndpointMatchOut | None
    findings: list[FindingOut]
    error_status: ErrorStatusOut | None
    corrected_curl: str | None
    explanation: str | None
    prompt_version: str | None
    latency_ms: dict[str, int]


# ── Helpers ────────────────────────────────────────────────────────────────────


def _build_service(
    session: object,
    llm_provider: LLMProvider,
) -> ValidationService:
    settings = get_settings()
    diagnostic_repo = PgDiagnosticRunRepository(session)  # type: ignore[arg-type]
    return ValidationService(
        llm_provider=llm_provider,
        diagnostic_repo=diagnostic_repo,
        header_validator=HeaderValidator(),
        parameter_validator=ParameterValidator(),
        body_validator=BodyValidator(),
        error_lookup=ErrorStatusLookup(),
        llm_model_id=settings.llm.model_id,
        llm_max_tokens=settings.llm.max_tokens,
        generation_temperature=settings.llm.generation_temperature,
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/curl", response_model=DiagnosticResponse)
async def validate_curl(
    body: ValidateCurlRequest,
    request: Request,
    workspace_id: UUID = Depends(get_workspace_id),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> DiagnosticResponse:
    async with get_session() as session:
        source_repo = PgSourceRepository(session)
        rev_repo = PgRevisionRepository(session)
        operation_repo = PgOperationRepository(session)
        server_repo = PgServerRepository(session)
        auth_scheme_repo = PgAuthSchemeRepository(session)
        error_repo = PgErrorRepository(session)

        source = await source_repo.get(body.source_id)
        if source is None or source.workspace_id != workspace_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SOURCE_NOT_FOUND", "message": "Source not found."},
            )

        revision = await rev_repo.get_active(body.source_id)
        if revision is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "NO_ACTIVE_REVISION",
                    "message": "No active revision found.",
                },
            )

        revision_id = revision.id
        operations = await operation_repo.list_by_revision(revision_id)
        servers = await server_repo.list_by_revision(revision_id)
        auth_schemes = await auth_scheme_repo.list_by_revision(revision_id)
        auth_schemes_by_name = {s.name: s for s in auth_schemes}

        # Load all error definitions for the revision
        error_definitions = []
        if body.received_status_code:
            error_definitions = await error_repo.find_by_status_code(
                revision_id, body.received_status_code
            )

        service = _build_service(session, llm_provider)

        try:
            run = await service.validate_curl(
                curl_string=body.curl_command,
                source_id=body.source_id,
                revision_id=revision_id,
                workspace_id=workspace_id,
                operations=operations,
                servers=servers,
                auth_schemes_by_name=auth_schemes_by_name,
                error_definitions=error_definitions,
                received_status_code=body.received_status_code,
            )
        except CurlParseError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "CURL_PARSE_ERROR", "message": str(exc)},
            ) from exc

    return _map_run_to_response(run)


@router.post("/request", response_model=DiagnosticResponse)
async def validate_request(
    body: ValidateRequestBody,
    request: Request,
    workspace_id: UUID = Depends(get_workspace_id),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> DiagnosticResponse:
    async with get_session() as session:
        source_repo = PgSourceRepository(session)
        rev_repo = PgRevisionRepository(session)
        operation_repo = PgOperationRepository(session)
        server_repo = PgServerRepository(session)
        auth_scheme_repo = PgAuthSchemeRepository(session)
        error_repo = PgErrorRepository(session)

        source = await source_repo.get(body.source_id)
        if source is None or source.workspace_id != workspace_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SOURCE_NOT_FOUND", "message": "Source not found."},
            )

        revision = await rev_repo.get_active(body.source_id)
        if revision is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "NO_ACTIVE_REVISION",
                    "message": "No active revision found.",
                },
            )

        revision_id = revision.id
        operations = await operation_repo.list_by_revision(revision_id)
        servers = await server_repo.list_by_revision(revision_id)
        auth_schemes = await auth_scheme_repo.list_by_revision(revision_id)
        auth_schemes_by_name = {s.name: s for s in auth_schemes}

        error_definitions = []
        if body.received_status_code:
            error_definitions = await error_repo.find_by_status_code(
                revision_id, body.received_status_code
            )

        # Construct ParsedRequest directly from body fields
        headers_lower = {k.lower(): v for k, v in body.headers.items()}
        auth_header = headers_lower.get("authorization")
        content_type = headers_lower.get("content-type")
        parsed = ParsedRequest(
            method=body.method.upper(),
            url=body.url,
            headers=headers_lower,
            body_raw=None,
            body_json=body.body,
            content_type=content_type,
            auth_header=auth_header,
            query_params={},
            is_url_encoded_body=False,
        )

        service = _build_service(session, llm_provider)
        run = await service.validate_request(
            parsed=parsed,
            source_id=body.source_id,
            revision_id=revision_id,
            workspace_id=workspace_id,
            operations=operations,
            servers=servers,
            auth_schemes_by_name=auth_schemes_by_name,
            error_definitions=error_definitions,
            received_status_code=body.received_status_code,
        )

    return _map_run_to_response(run)


def _map_run_to_response(run: object) -> DiagnosticResponse:
    from fetch.domain.entities import RequestDiagnosticRun

    assert isinstance(run, RequestDiagnosticRun)

    endpoint_out: EndpointMatchOut | None = None
    if run.diagnostic and run.diagnostic.endpoint_match:
        em = run.diagnostic.endpoint_match
        op = em.operation
        endpoint_out = EndpointMatchOut(
            match_confidence=str(em.match_confidence),
            path=op.path if op else None,
            method=op.method.value if op else None,
            path_params=dict(em.path_params),
        )

    findings_out: list[FindingOut] = []
    if run.diagnostic:
        findings_out = [
            FindingOut(
                severity=f.severity,
                category=str(f.category),
                message=f.message,
                field=f.field,
                canonical_value=f.canonical_value,
            )
            for f in run.diagnostic.findings
        ]

    error_status_out: ErrorStatusOut | None = None
    if run.diagnostic and run.diagnostic.error_status_match:
        esm = run.diagnostic.error_status_match
        error_status_out = ErrorStatusOut(
            status_code=esm.status_code,
            is_documented=esm.is_documented,
            matched_count=len(esm.matched_definitions),
        )

    return DiagnosticResponse(
        diagnostic_run_id=run.id,
        is_valid=run.is_valid,
        support_status=run.support_status.value,
        endpoint_match=endpoint_out,
        findings=findings_out,
        error_status=error_status_out,
        corrected_curl=run.corrected_curl,
        explanation=run.explanation,
        prompt_version=run.prompt_version,
        latency_ms={
            "parse_ms": run.parse_ms or 0,
            "match_ms": run.match_ms or 0,
            "validate_ms": run.validate_ms or 0,
            "explanation_ms": run.explanation_ms or 0,
            "total_ms": run.total_ms or 0,
        },
    )
