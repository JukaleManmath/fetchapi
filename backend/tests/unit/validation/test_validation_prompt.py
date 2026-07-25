"""Tests for validation prompt builder."""

from __future__ import annotations

from fetch.application.validation.prompt import (
    VALIDATION_PROMPT_VERSION,
    build_validation_system_prompt,
    build_validation_user_message,
)
from fetch.domain.entities import (
    DiagnosticFinding,
    EndpointMatch,
    ParsedRequest,
    RequestDiagnostic,
)
from fetch.domain.enums import DiagnosticCategory, MatchConfidence


def _make_diagnostic(
    findings: list[DiagnosticFinding] | None = None,
    auth_header: str | None = None,
) -> RequestDiagnostic:
    parsed = ParsedRequest(
        method="POST",
        url="https://api.example.com/v1/items",
        headers={"content-type": "application/json"},
        body_raw='{"name":"test"}',
        body_json={"name": "test"},
        content_type="application/json",
        auth_header=auth_header,
        query_params={},
        is_url_encoded_body=False,
    )
    return RequestDiagnostic(
        parsed_request=parsed,
        endpoint_match=EndpointMatch(
            operation=None,
            path_params={},
            match_confidence=MatchConfidence.NO_MATCH,
        ),
        findings=findings or [],
        error_status_match=None,
        corrected_curl=None,
        is_valid=not any(f.severity == "error" for f in (findings or [])),
    )


def test_system_prompt_contains_injection_safety_text() -> None:
    prompt = build_validation_system_prompt()
    assert "INJECTION SAFETY" in prompt


def test_user_message_contains_method_and_url() -> None:
    diag = _make_diagnostic()
    msg = build_validation_user_message(diag, None)
    assert "POST" in msg
    assert "https://api.example.com/v1/items" in msg


def test_user_message_contains_finding_messages() -> None:
    finding = DiagnosticFinding(
        severity="error",
        category=DiagnosticCategory.AUTH,
        message="Authorization header is missing.",
        field="Authorization",
    )
    diag = _make_diagnostic(findings=[finding])
    msg = build_validation_user_message(diag, None)
    assert "Authorization header is missing." in msg


def test_user_message_does_not_contain_auth_header_value() -> None:
    secret_token = "Bearer supersecrettoken123456789"
    diag = _make_diagnostic(auth_header=secret_token)
    msg = build_validation_user_message(diag, None)
    assert "supersecrettoken123456789" not in msg
    assert secret_token not in msg


def test_validation_prompt_version_is_v1() -> None:
    assert VALIDATION_PROMPT_VERSION == "v1"
