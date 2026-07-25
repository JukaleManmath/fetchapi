"""Unit tests for prompt builder."""

from __future__ import annotations

from fetch.application.queries.prompt import (
    PROMPT_VERSION,
    build_system_prompt,
    build_user_message,
)


def test_prompt_version_is_v1() -> None:
    assert PROMPT_VERSION == "v1"


def test_injection_safety_text_present() -> None:
    prompt = build_system_prompt("some context", ["S1"])
    assert "INJECTION SAFETY" in prompt


def test_allowed_ids_in_system_prompt() -> None:
    prompt = build_system_prompt("context here", ["S1", "S2", "S3"])
    assert "S1" in prompt
    assert "S2" in prompt
    assert "S3" in prompt


def test_context_text_in_system_prompt() -> None:
    context = "This API supports OAuth2 authentication [S1]."
    prompt = build_system_prompt(context, ["S1"])
    assert context in prompt


def test_user_message_equals_question() -> None:
    question = "How do I authenticate with Bearer tokens?"
    assert build_user_message(question) == question


def test_empty_source_ids_shows_none() -> None:
    prompt = build_system_prompt("context", [])
    assert "(none)" in prompt
