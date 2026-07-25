from __future__ import annotations

import json
import re

from fetch.application.integrations.context import IntegrationContext
from fetch.domain.entities import ValidationIssue
from fetch.domain.enums import AuthSchemeType, GenerationLanguage

_REAL_TOKEN_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9+/._-]{30,}")


class ContractValidator:
    """Pure string analysis of generated code against the OpenAPI contract. No I/O."""

    def validate(
        self,
        generated_code: str,
        context: IntegrationContext,
        language: GenerationLanguage,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        code_lower = generated_code.lower()

        # Check HTTP method present
        if context.operation.method.value.upper() not in generated_code.upper():
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="contract",
                    message=f"HTTP method {context.operation.method.value.upper()} not found in generated code",
                    field="method",
                )
            )

        # Check path present
        if context.operation.path not in generated_code:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="contract",
                    message=f"Path {context.operation.path} not found in generated code",
                    field="path",
                )
            )

        # Check auth: bearer
        for scheme in context.auth_schemes:
            if scheme.scheme_type == AuthSchemeType.HTTP:
                try:
                    details = json.loads(scheme.details_json)
                    if details.get("scheme", "").lower() == "bearer":
                        if (
                            "authorization" not in code_lower
                            or "bearer" not in code_lower
                        ):
                            issues.append(
                                ValidationIssue(
                                    severity="error",
                                    category="contract",
                                    message="Bearer Authorization header not found in generated code",
                                    field="Authorization header",
                                )
                            )
                except Exception:
                    pass

        # Check required body fields present as string literals
        if context.request_schema_json:
            try:
                schema = json.loads(context.request_schema_json)
                required_fields = schema.get("required", [])
                for field_name in required_fields:
                    if (
                        f'"{field_name}"' not in generated_code
                        and f"'{field_name}'" not in generated_code
                    ):
                        issues.append(
                            ValidationIssue(
                                severity="error",
                                category="contract",
                                message=f"Required field '{field_name}' not found as string literal in generated code",
                                field=f"body.{field_name}",
                            )
                        )
            except Exception:
                pass

        # Security: no real bearer tokens
        if _REAL_TOKEN_PATTERN.search(generated_code):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="security",
                    message="Generated code may contain a real bearer token. Use environment variables.",
                    field=None,
                )
            )

        return issues
