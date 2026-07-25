from __future__ import annotations

import logging
from uuid import UUID

from fetch.application.integrations.context import IntegrationContext
from fetch.domain.errors import IntegrationContextError

logger = logging.getLogger(__name__)


class IntegrationContextAssembler:
    """Loads all context for an operation from PostgreSQL. No Qdrant, no embedding."""

    def __init__(
        self,
        operation_repo: object,
        server_repo: object,
        auth_scheme_repo: object,
        parameter_repo: object,
        request_body_repo: object,
        response_repo: object,
        example_repo: object,
        error_repo: object,
    ) -> None:
        self._operation_repo = operation_repo
        self._server_repo = server_repo
        self._auth_scheme_repo = auth_scheme_repo
        self._parameter_repo = parameter_repo
        self._request_body_repo = request_body_repo
        self._response_repo = response_repo
        self._example_repo = example_repo
        self._error_repo = error_repo

    async def load(
        self,
        operation_id: UUID,
        revision_id: UUID,
        workspace_id: UUID,
    ) -> IntegrationContext:
        operation = await self._operation_repo.get(operation_id)  # type: ignore[attr-defined]
        if operation is None:
            raise IntegrationContextError(
                f"Operation {operation_id} not found",
                operation_id=str(operation_id),
            )

        servers = await self._server_repo.list_by_revision(revision_id)  # type: ignore[attr-defined]
        base_url = servers[0].url if servers else ""

        all_auth = await self._auth_scheme_repo.list_by_revision(revision_id)  # type: ignore[attr-defined]
        required_scheme_names = {
            name for req in operation.security_requirements for name in req.keys()
        }
        if required_scheme_names:
            auth_schemes = [s for s in all_auth if s.name in required_scheme_names]
        else:
            auth_schemes = list(all_auth)

        parameters = await self._parameter_repo.list_by_operation(operation_id)  # type: ignore[attr-defined]

        request_body = await self._request_body_repo.get_by_operation(operation_id)  # type: ignore[attr-defined]
        request_schema_json: str | None = None
        if request_body is not None:
            request_schema_json = request_body.content_schemas.get("application/json")

        responses = await self._response_repo.list_by_operation(operation_id)  # type: ignore[attr-defined]
        response_schemas: list[tuple[str, str]] = []
        for resp in responses:
            schema = resp.content_schemas.get("application/json")
            if schema:
                response_schemas.append((resp.status_code, schema))

        examples = await self._example_repo.find_by_operation(revision_id, operation_id)  # type: ignore[attr-defined]
        error_definitions = await self._error_repo.find_by_operation(  # type: ignore[attr-defined]
            revision_id, operation_id
        )

        logger.debug(
            "integration_context_loaded",
            extra={
                "operation_id": str(operation_id),
                "parameters": len(parameters),
                "examples": len(examples),
                "errors": len(error_definitions),
            },
        )

        return IntegrationContext(
            operation=operation,
            base_url=base_url,
            auth_schemes=auth_schemes,
            parameters=parameters,
            request_body=request_body,
            request_schema_json=request_schema_json,
            response_schemas=response_schemas,
            examples=examples,
            error_definitions=error_definitions,
            api_title=None,
        )
