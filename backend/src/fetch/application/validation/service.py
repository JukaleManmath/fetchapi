from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fetch.application.validation.corrected_example import build_corrected_curl
from fetch.application.validation.curl_parser import parse_curl
from fetch.application.validation.endpoint_matcher import EndpointMatcher
from fetch.application.validation.error_lookup import ErrorStatusLookup
from fetch.application.validation.prompt import (
    VALIDATION_PROMPT_VERSION,
    build_validation_system_prompt,
    build_validation_user_message,
)
from fetch.application.validation.validators import (
    BodyValidator,
    HeaderValidator,
    ParameterValidator,
)
from fetch.domain.entities import (
    ApiOperation,
    ApiServer,
    AuthScheme,
    DiagnosticFinding,
    ErrorDefinition,
    ParsedRequest,
    RequestDiagnostic,
    RequestDiagnosticRun,
)
from fetch.domain.enums import DiagnosticCategory, DiagnosticInputType, SupportStatus
from fetch.domain.protocols import (
    DiagnosticRunRepository,
    GenerationConfig,
    LLMMessage,
    LLMProvider,
)

logger = logging.getLogger(__name__)


class ValidationService:
    def __init__(
        self,
        llm_provider: LLMProvider,
        diagnostic_repo: DiagnosticRunRepository,
        header_validator: HeaderValidator,
        parameter_validator: ParameterValidator,
        body_validator: BodyValidator,
        error_lookup: ErrorStatusLookup,
        llm_model_id: str,
        llm_max_tokens: int = 4096,
        generation_temperature: float = 0.1,
    ) -> None:
        self._llm = llm_provider
        self._repo = diagnostic_repo
        self._header_validator = header_validator
        self._parameter_validator = parameter_validator
        self._body_validator = body_validator
        self._error_lookup = error_lookup
        self._model_id = llm_model_id
        self._max_tokens = llm_max_tokens
        self._temperature = generation_temperature

    async def validate_curl(
        self,
        curl_string: str,
        source_id: UUID,
        revision_id: UUID,
        workspace_id: UUID,
        operations: list[ApiOperation],
        servers: list[ApiServer],
        auth_schemes_by_name: dict[str, AuthScheme],
        error_definitions: list[ErrorDefinition],
        received_status_code: str | None = None,
    ) -> RequestDiagnosticRun:
        t0 = time.monotonic()
        parsed = parse_curl(curl_string)
        parse_ms = int((time.monotonic() - t0) * 1000)

        # Redact auth from raw_input for storage
        raw_input_safe = self._redact_auth(curl_string)

        return await self._run_pipeline(
            parsed=parsed,
            source_id=source_id,
            revision_id=revision_id,
            workspace_id=workspace_id,
            input_type=DiagnosticInputType.CURL,
            raw_input=raw_input_safe,
            operations=operations,
            servers=servers,
            auth_schemes_by_name=auth_schemes_by_name,
            error_definitions=error_definitions,
            received_status_code=received_status_code,
            parse_ms=parse_ms,
        )

    async def validate_request(
        self,
        parsed: ParsedRequest,
        source_id: UUID,
        revision_id: UUID,
        workspace_id: UUID,
        operations: list[ApiOperation],
        servers: list[ApiServer],
        auth_schemes_by_name: dict[str, AuthScheme],
        error_definitions: list[ErrorDefinition],
        received_status_code: str | None = None,
    ) -> RequestDiagnosticRun:
        raw_input_safe = f"{parsed.method} {parsed.url}"
        return await self._run_pipeline(
            parsed=parsed,
            source_id=source_id,
            revision_id=revision_id,
            workspace_id=workspace_id,
            input_type=DiagnosticInputType.REQUEST,
            raw_input=raw_input_safe,
            operations=operations,
            servers=servers,
            auth_schemes_by_name=auth_schemes_by_name,
            error_definitions=error_definitions,
            received_status_code=received_status_code,
            parse_ms=0,
        )

    async def _run_pipeline(
        self,
        parsed: ParsedRequest,
        source_id: UUID,
        revision_id: UUID,
        workspace_id: UUID,
        input_type: DiagnosticInputType,
        raw_input: str,
        operations: list[ApiOperation],
        servers: list[ApiServer],
        auth_schemes_by_name: dict[str, AuthScheme],
        error_definitions: list[ErrorDefinition],
        received_status_code: str | None,
        parse_ms: int,
    ) -> RequestDiagnosticRun:
        t0 = time.monotonic()
        run_id = uuid4()

        # Match endpoint
        t_match = time.monotonic()
        matcher = EndpointMatcher(operations=operations, servers=servers)
        endpoint_match = matcher.match(parsed.method, parsed.url)
        match_ms = int((time.monotonic() - t_match) * 1000)

        operation = endpoint_match.operation
        matched_auth_schemes = []
        if operation is not None:
            sec_reqs = getattr(operation, "security_requirements", []) or []
            for req in sec_reqs:
                for name in req if isinstance(req, list) else [req]:
                    if isinstance(name, dict):
                        for k in name:
                            if k in auth_schemes_by_name:
                                matched_auth_schemes.append(auth_schemes_by_name[k])
                    elif name in auth_schemes_by_name:
                        matched_auth_schemes.append(auth_schemes_by_name[name])

        # Validate
        t_val = time.monotonic()
        findings: list[DiagnosticFinding] = []
        if operation is not None:
            findings += self._header_validator.validate(
                parsed, operation, matched_auth_schemes
            )
            findings += self._parameter_validator.validate(
                parsed, operation, endpoint_match.path_params
            )
            findings += self._body_validator.validate(parsed, operation)
        else:
            findings.append(
                DiagnosticFinding(
                    severity="error",
                    category=DiagnosticCategory.ENDPOINT,
                    message=f"No operation matching {parsed.method} {parsed.url} found in the active revision.",
                    field=None,
                )
            )
        validate_ms = int((time.monotonic() - t_val) * 1000)

        is_valid = not any(f.severity == "error" for f in findings)

        # Error status lookup
        error_status_match = self._error_lookup.lookup(
            received_status_code, error_definitions
        )

        # Corrected curl
        corrected_curl: str | None = None
        if operation is not None and servers:
            base_url = servers[0].url if servers else ""
            corrected_curl = build_corrected_curl(
                operation=operation,
                base_url=base_url,
                auth_schemes=matched_auth_schemes,
                parsed=parsed,
            )

        # Build diagnostic — strip auth_header before storing
        parsed_safe = ParsedRequest(
            method=parsed.method,
            url=parsed.url,
            headers={k: v for k, v in parsed.headers.items() if k != "authorization"},
            body_raw=parsed.body_raw,
            body_json=parsed.body_json,
            content_type=parsed.content_type,
            auth_header=None,  # never stored
            query_params=parsed.query_params,
            is_url_encoded_body=parsed.is_url_encoded_body,
        )
        diagnostic = RequestDiagnostic(
            parsed_request=parsed_safe,
            endpoint_match=endpoint_match,
            findings=findings,
            error_status_match=error_status_match,
            corrected_curl=corrected_curl,
            is_valid=is_valid,
        )

        # LLM explanation — one call only
        t_exp = time.monotonic()
        explanation: str | None = None
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        support_status = (
            SupportStatus.SUPPORTED if is_valid else SupportStatus.VALIDATION_FAILED
        )
        try:
            messages = [
                LLMMessage(role="system", content=build_validation_system_prompt()),
                LLMMessage(
                    role="user",
                    content=build_validation_user_message(diagnostic, corrected_curl),
                ),
            ]
            gen_config = GenerationConfig(
                model_id=self._model_id,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
            explanation = await self._llm.generate(messages, gen_config)
        except Exception as exc:
            logger.warning(
                "LLM explanation failed for diagnostic run %s: %s", run_id, exc
            )
            support_status = SupportStatus.INSUFFICIENT_EVIDENCE
        explanation_ms = int((time.monotonic() - t_exp) * 1000)

        total_ms = int((time.monotonic() - t0) * 1000)

        run = RequestDiagnosticRun(
            id=run_id,
            workspace_id=workspace_id,
            source_id=source_id,
            revision_id=revision_id,
            operation_id=operation.id if operation else None,
            input_type=input_type,
            raw_input=raw_input,
            parsed_method=parsed.method,
            parsed_url=parsed.url,
            received_status_code=received_status_code,
            diagnostic=diagnostic,
            explanation=explanation,
            corrected_curl=corrected_curl,
            is_valid=is_valid,
            support_status=support_status,
            prompt_version=VALIDATION_PROMPT_VERSION,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            parse_ms=parse_ms,
            match_ms=match_ms,
            validate_ms=validate_ms,
            explanation_ms=explanation_ms,
            total_ms=total_ms,
            created_at=datetime.now(UTC),
        )
        await self._repo.save(run)
        return run

    @staticmethod
    def _redact_auth(curl_string: str) -> str:
        import re

        redacted = re.sub(
            r'(-H\s+["\']?Authorization:\s*(?:Bearer|Basic)\s+)[^\s"\'\\]+',
            r"\1<REDACTED>",
            curl_string,
            flags=re.IGNORECASE,
        )
        return redacted
