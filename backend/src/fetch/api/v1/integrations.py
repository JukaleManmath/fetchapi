"""Integration code generation endpoint.

POST /v1/integrations/generate — generate integration code for an API operation
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, model_validator

from fetch.api.dependencies import get_llm_provider, get_workspace_id
from fetch.application.integrations.contract_validator import ContractValidator
from fetch.application.integrations.loader import IntegrationContextAssembler
from fetch.application.integrations.service import IntegrationService
from fetch.application.integrations.syntax_validator import SyntaxValidatorDispatcher
from fetch.config import get_settings
from fetch.domain.enums import GenerationLanguage
from fetch.domain.errors import IntegrationContextError
from fetch.domain.protocols import LLMProvider
from fetch.infrastructure.db.repositories import (
    PgAuthSchemeRepository,
    PgErrorRepository,
    PgExampleRepository,
    PgIntegrationRunRepository,
    PgOperationRepository,
    PgParameterRepository,
    PgRequestBodyRepository,
    PgResponseRepository,
    PgRevisionRepository,
    PgServerRepository,
    PgSourceRepository,
)
from fetch.infrastructure.db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])


class GenerateIntegrationRequest(BaseModel):
    source_id: UUID
    operation_id: UUID | None = None
    method: str | None = None
    path: str | None = None
    language: GenerationLanguage = GenerationLanguage.PYTHON

    @model_validator(mode="after")
    def check_operation_selector(self) -> GenerateIntegrationRequest:
        if self.operation_id is None and (self.method is None or self.path is None):
            raise ValueError("Provide either operation_id or both method and path")
        return self


class ValidationIssueOut(BaseModel):
    severity: str
    category: str
    message: str
    field: str | None


class ValidationReportOut(BaseModel):
    contract_valid: bool
    syntax_valid: bool
    overall_valid: bool
    issues: list[ValidationIssueOut]


class GenerateIntegrationResponse(BaseModel):
    integration_run_id: UUID
    operation_id: UUID
    method: str
    path: str
    language: str
    generated_code: str | None
    validation_report: ValidationReportOut
    support_status: str
    warnings: list[str]
    prompt_version: str | None
    usage: dict[str, int] | None
    latency_ms: dict[str, int]


@router.post("/generate", response_model=GenerateIntegrationResponse)
async def generate_integration(
    body: GenerateIntegrationRequest,
    request: Request,
    workspace_id: UUID = Depends(get_workspace_id),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> GenerateIntegrationResponse:
    settings = get_settings()

    async with get_session() as session:
        source_repo = PgSourceRepository(session)
        rev_repo = PgRevisionRepository(session)
        operation_repo = PgOperationRepository(session)
        server_repo = PgServerRepository(session)
        auth_scheme_repo = PgAuthSchemeRepository(session)
        parameter_repo = PgParameterRepository(session)
        request_body_repo = PgRequestBodyRepository(session)
        response_repo = PgResponseRepository(session)
        example_repo = PgExampleRepository(session)
        error_repo = PgErrorRepository(session)
        integration_run_repo = PgIntegrationRunRepository(session)

        # 1. Resolve source and active revision
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
                    "message": "No active revision found. Ingestion may still be in progress.",
                },
            )

        revision_id = revision.id

        # 2. Resolve operation_id
        if body.operation_id is not None:
            operation = await operation_repo.get(body.operation_id)
            if operation is None or operation.revision_id != revision_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "code": "OPERATION_NOT_FOUND",
                        "message": "Operation not found in the active revision.",
                    },
                )
            operation_id = body.operation_id
        else:
            # Normalize path: lowercase, strip trailing slash
            path_normalized = (body.path or "").rstrip("/").lower()
            operation = await operation_repo.find_by_method_path(
                revision_id, (body.method or "").upper(), path_normalized
            )
            if operation is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "code": "OPERATION_NOT_FOUND",
                        "message": f"No operation found for {body.method} {body.path}.",
                    },
                )
            operation_id = operation.id

        # 3. Build service and generate
        context_loader = IntegrationContextAssembler(
            operation_repo=operation_repo,
            server_repo=server_repo,
            auth_scheme_repo=auth_scheme_repo,
            parameter_repo=parameter_repo,
            request_body_repo=request_body_repo,
            response_repo=response_repo,
            example_repo=example_repo,
            error_repo=error_repo,
        )

        service = IntegrationService(
            context_loader=context_loader,
            llm_provider=llm_provider,
            contract_validator=ContractValidator(),
            syntax_validator=SyntaxValidatorDispatcher(),
            integration_repo=integration_run_repo,
            llm_model_id=settings.llm.model_id,
            llm_max_tokens=settings.llm.max_tokens,
            generation_temperature=settings.llm.generation_temperature,
        )

        try:
            run = await service.generate(
                operation_id=operation_id,
                source_id=body.source_id,
                revision_id=revision_id,
                workspace_id=workspace_id,
                language=body.language,
            )
        except IntegrationContextError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "OPERATION_NOT_FOUND", "message": str(exc)},
            ) from exc

    # 4. Map IntegrationRun → response
    report = run.validation_report
    if report is None:
        report_out = ValidationReportOut(
            contract_valid=False,
            syntax_valid=False,
            overall_valid=False,
            issues=[],
        )
    else:
        report_out = ValidationReportOut(
            contract_valid=report.contract_valid,
            syntax_valid=report.syntax_valid,
            overall_valid=report.overall_valid,
            issues=[
                ValidationIssueOut(
                    severity=i.severity,
                    category=i.category,
                    message=i.message,
                    field=i.field,
                )
                for i in report.issues
            ],
        )

    usage: dict[str, int] | None = None
    if run.prompt_tokens is not None or run.completion_tokens is not None:
        usage = {
            "prompt_tokens": run.prompt_tokens or 0,
            "completion_tokens": run.completion_tokens or 0,
        }

    return GenerateIntegrationResponse(
        integration_run_id=run.id,
        operation_id=run.operation_id,
        method=operation.method.value,
        path=operation.path,
        language=run.language.value,
        generated_code=run.generated_code,
        validation_report=report_out,
        support_status=run.support_status.value,
        warnings=run.warnings,
        prompt_version=run.prompt_version,
        usage=usage,
        latency_ms={
            "context_assembly_ms": run.context_assembly_ms or 0,
            "generation_ms": run.generation_ms or 0,
            "validation_ms": run.validation_ms or 0,
            "total_ms": run.total_ms or 0,
        },
    )
