from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fetch.application.integrations.context import IntegrationContext
from fetch.application.integrations.contract_validator import ContractValidator
from fetch.application.integrations.loader import IntegrationContextAssembler
from fetch.application.integrations.prompt import (
    INTEGRATION_PROMPT_VERSION,
    build_integration_system_prompt,
    build_integration_user_message,
)
from fetch.application.integrations.syntax_validator import SyntaxValidatorDispatcher
from fetch.domain.entities import IntegrationRun, ValidationReport
from fetch.domain.enums import GenerationLanguage, SupportStatus
from fetch.domain.protocols import GenerationConfig, LLMMessage, LLMProvider

logger = logging.getLogger(__name__)


class IntegrationService:
    def __init__(
        self,
        context_loader: IntegrationContextAssembler,
        llm_provider: LLMProvider,
        contract_validator: ContractValidator,
        syntax_validator: SyntaxValidatorDispatcher,
        integration_repo: object,
        llm_model_id: str,
        llm_max_tokens: int = 4096,
        generation_temperature: float = 0.1,
    ) -> None:
        self._context_loader = context_loader
        self._llm = llm_provider
        self._contract_validator = contract_validator
        self._syntax_validator = syntax_validator
        self._integration_repo = integration_repo
        self._model_id = llm_model_id
        self._max_tokens = llm_max_tokens
        self._temperature = generation_temperature

    async def generate(
        self,
        operation_id: UUID,
        source_id: UUID,
        revision_id: UUID,
        workspace_id: UUID,
        language: GenerationLanguage,
    ) -> IntegrationRun:
        run_id = uuid4()
        t0 = time.monotonic()

        # 1. Load context (raises IntegrationContextError if operation not found)
        context: IntegrationContext = await self._context_loader.load(
            operation_id, revision_id, workspace_id
        )
        context_assembly_ms = int((time.monotonic() - t0) * 1000)

        # 2. Build prompt
        system_prompt = build_integration_system_prompt(language)
        user_message = build_integration_user_message(context, language)
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_message),
        ]

        gen_config = GenerationConfig(
            model_id=self._model_id,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )

        # 3. Single LLM call — generate() not generate_stream()
        t_gen = time.monotonic()
        generated_code: str = await self._llm.generate(messages, gen_config)
        generation_ms = int((time.monotonic() - t_gen) * 1000)

        # 4. Validate
        t_val = time.monotonic()
        contract_issues = self._contract_validator.validate(
            generated_code, context, language
        )
        syntax_issues = self._syntax_validator.validate(generated_code, language)
        validation_ms = int((time.monotonic() - t_val) * 1000)

        all_issues = contract_issues + syntax_issues
        contract_valid = not any(
            i.severity == "error" and i.category == "contract" for i in all_issues
        )
        syntax_valid = not any(
            i.severity == "error" and i.category == "syntax" for i in all_issues
        )
        report = ValidationReport(
            contract_valid=contract_valid,
            syntax_valid=syntax_valid,
            issues=all_issues,
            overall_valid=contract_valid and syntax_valid,
        )

        total_ms = int((time.monotonic() - t0) * 1000)

        run = IntegrationRun(
            id=run_id,
            workspace_id=workspace_id,
            source_id=source_id,
            revision_id=revision_id,
            operation_id=operation_id,
            language=language,
            generated_code=generated_code,
            validation_report=report,
            support_status=SupportStatus.SUPPORTED,
            warnings=[],
            prompt_version=INTEGRATION_PROMPT_VERSION,
            prompt_tokens=None,
            completion_tokens=None,
            context_assembly_ms=context_assembly_ms,
            generation_ms=generation_ms,
            validation_ms=validation_ms,
            total_ms=total_ms,
            created_at=datetime.now(UTC),
        )
        await self._integration_repo.save(run)  # type: ignore[attr-defined]

        logger.info(
            "integration_run_complete",
            extra={
                "run_id": str(run_id),
                "language": language.value,
                "total_ms": total_ms,
                "overall_valid": report.overall_valid,
            },
        )

        return run
