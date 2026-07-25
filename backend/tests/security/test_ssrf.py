"""SSRF protection tests.

Verifies that external $ref fetching blocks loopback, private network,
and cloud metadata IP ranges via the SSRF guard in the OpenAPI validator.
"""

from __future__ import annotations

import pytest

from fetch.domain.errors import IngestionError
from fetch.infrastructure.openapi.validator import _is_ssrf_blocked, fetch_external_ref


def test_ssrf_loopback_blocked() -> None:
    """$ref to 127.0.0.1 must be detected as blocked."""
    assert _is_ssrf_blocked("http://127.0.0.1/openapi.json") is True


def test_ssrf_private_network_blocked() -> None:
    """$ref to 10.0.0.1 must be detected as blocked."""
    assert _is_ssrf_blocked("http://10.0.0.1/openapi.json") is True


def test_ssrf_metadata_endpoint_blocked() -> None:
    """$ref to 169.254.169.254 (cloud metadata) must be detected as blocked."""
    assert _is_ssrf_blocked("http://169.254.169.254/latest/meta-data/") is True


def test_ssrf_private_172_blocked() -> None:
    """$ref to 172.16.x.x private range must be detected as blocked."""
    assert _is_ssrf_blocked("http://172.16.0.1/openapi.json") is True


def test_ssrf_private_192_blocked() -> None:
    """$ref to 192.168.x.x private range must be detected as blocked."""
    assert _is_ssrf_blocked("http://192.168.1.1/openapi.json") is True


def test_ssrf_ipv6_loopback_blocked() -> None:
    """$ref to ::1 IPv6 loopback must be detected as blocked."""
    assert _is_ssrf_blocked("http://[::1]/openapi.json") is True


def test_ssrf_non_http_scheme_blocked() -> None:
    """$ref with file:// scheme must be detected as blocked."""
    assert _is_ssrf_blocked("file:///etc/passwd") is True


@pytest.mark.asyncio
async def test_fetch_external_ref_raises_on_loopback() -> None:
    """fetch_external_ref must raise IngestionError for loopback addresses."""
    with pytest.raises(IngestionError, match="blocked by SSRF policy"):
        await fetch_external_ref(
            "http://127.0.0.1/openapi.json",
            max_bytes=1_048_576,
            timeout=10.0,
        )


@pytest.mark.asyncio
async def test_fetch_external_ref_raises_on_private_network() -> None:
    """fetch_external_ref must raise IngestionError for private network addresses."""
    with pytest.raises(IngestionError, match="blocked by SSRF policy"):
        await fetch_external_ref(
            "http://10.0.0.1/openapi.json",
            max_bytes=1_048_576,
            timeout=10.0,
        )


@pytest.mark.asyncio
async def test_fetch_external_ref_raises_on_metadata_endpoint() -> None:
    """fetch_external_ref must raise IngestionError for cloud metadata endpoints."""
    with pytest.raises(IngestionError, match="blocked by SSRF policy"):
        await fetch_external_ref(
            "http://169.254.169.254/latest/meta-data/",
            max_bytes=1_048_576,
            timeout=10.0,
        )
