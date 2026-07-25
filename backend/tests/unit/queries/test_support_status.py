"""Unit tests for support_status."""

from __future__ import annotations

from fetch.application.queries.support_status import compute_support_status
from fetch.domain.enums import SupportStatus


def test_empty_available_ids_returns_insufficient() -> None:
    result = compute_support_status(
        valid_cited_ids=["S1"],
        available_ids=[],
        unknown_ids=[],
    )
    assert result == SupportStatus.INSUFFICIENT_EVIDENCE


def test_empty_valid_cited_returns_insufficient() -> None:
    result = compute_support_status(
        valid_cited_ids=[],
        available_ids=["S1", "S2"],
        unknown_ids=[],
    )
    assert result == SupportStatus.INSUFFICIENT_EVIDENCE


def test_valid_only_returns_supported() -> None:
    result = compute_support_status(
        valid_cited_ids=["S1", "S2"],
        available_ids=["S1", "S2"],
        unknown_ids=[],
    )
    assert result == SupportStatus.SUPPORTED


def test_valid_with_unknown_returns_partially_supported() -> None:
    result = compute_support_status(
        valid_cited_ids=["S1"],
        available_ids=["S1", "S2"],
        unknown_ids=["S99"],
    )
    assert result == SupportStatus.PARTIALLY_SUPPORTED
