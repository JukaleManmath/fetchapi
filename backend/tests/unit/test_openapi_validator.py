"""Unit tests for the OpenAPI validator and $ref resolver.

No database, no network (external ref tests use a mock).
"""

import pytest

from fetch.domain.errors import IngestionError
from fetch.infrastructure.openapi.validator import (
    detect_openapi_version,
    load_yaml_safe,
)


# ── load_yaml_safe ────────────────────────────────────────────────────────────


def test_load_yaml_safe_valid_yaml() -> None:
    content = b"openapi: '3.0.0'\ninfo:\n  title: Test\n  version: '1.0'"
    doc = load_yaml_safe(content)
    assert doc["openapi"] == "3.0.0"


def test_load_yaml_safe_valid_json() -> None:
    content = b'{"openapi": "3.0.0", "info": {"title": "T", "version": "1"}}'
    doc = load_yaml_safe(content)
    assert doc["openapi"] == "3.0.0"


def test_load_yaml_safe_invalid_yaml() -> None:
    with pytest.raises(IngestionError, match="YAML parse error"):
        load_yaml_safe(b"key: [unclosed")


def test_load_yaml_safe_non_dict_root() -> None:
    with pytest.raises(IngestionError, match="root must be a mapping"):
        load_yaml_safe(b"- item1\n- item2")


def test_load_yaml_safe_alias_limit() -> None:
    # Create a YAML doc with 5 alias expansions — exceeds limit of 3
    anchor = "a: &anchor value\n"
    aliases = "\n".join(f"key{i}: *anchor" for i in range(5))
    content = (anchor + aliases).encode()
    with pytest.raises(IngestionError, match="alias count"):
        load_yaml_safe(content, max_aliases=3)


def test_load_yaml_safe_within_alias_limit() -> None:
    anchor = "a: &anchor value\n"
    aliases = "\n".join(f"key{i}: *anchor" for i in range(2))
    content = (anchor + aliases).encode()
    doc = load_yaml_safe(content, max_aliases=10)
    assert "a" in doc


# ── detect_openapi_version ────────────────────────────────────────────────────


def test_detect_version_30() -> None:
    assert detect_openapi_version({"openapi": "3.0.3"}) == "3.0"


def test_detect_version_31() -> None:
    assert detect_openapi_version({"openapi": "3.1.0"}) == "3.1"


def test_detect_version_unsupported() -> None:
    with pytest.raises(IngestionError, match="Unsupported"):
        detect_openapi_version({"openapi": "2.0"})


def test_detect_version_missing() -> None:
    with pytest.raises(IngestionError, match="Missing or non-string"):
        detect_openapi_version({})


# ── load_and_resolve with real fixture ───────────────────────────────────────


@pytest.mark.asyncio
async def test_load_and_resolve_petstore() -> None:
    """Smoke test: load the Petstore fixture end-to-end."""
    import pathlib
    from fetch.infrastructure.openapi.validator import load_and_resolve

    fixture = (
        pathlib.Path(__file__).parent.parent
        / "fixtures"
        / "openapi"
        / "valid_minimal.yaml"
    )
    content = fixture.read_bytes()
    doc, version = await load_and_resolve(content)
    assert version in ("3.0", "3.1")
    assert "paths" in doc or "info" in doc


@pytest.mark.asyncio
async def test_load_and_resolve_invalid_spec() -> None:
    """An invalid spec (missing info) should raise IngestionError."""
    import pathlib
    from fetch.infrastructure.openapi.validator import load_and_resolve

    fixture = (
        pathlib.Path(__file__).parent.parent
        / "fixtures"
        / "openapi"
        / "invalid_missing_info.yaml"
    )
    content = fixture.read_bytes()
    with pytest.raises(IngestionError):
        await load_and_resolve(content)
