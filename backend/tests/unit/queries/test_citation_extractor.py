"""Unit tests for citation_extractor."""

from __future__ import annotations

from fetch.application.queries.citation_extractor import extract_cited_ids


def test_valid_id_found() -> None:
    valid, unknown = extract_cited_ids("See [S1] for details.", {"S1", "S2"})
    assert valid == ["S1"]
    assert unknown == []


def test_unknown_id() -> None:
    valid, unknown = extract_cited_ids("According to [S5].", {"S1", "S2"})
    assert valid == []
    assert unknown == ["S5"]


def test_mixed_valid_and_unknown() -> None:
    valid, unknown = extract_cited_ids("[S1] and [S99] support this.", {"S1", "S2"})
    assert valid == ["S1"]
    assert unknown == ["S99"]


def test_empty_text() -> None:
    valid, unknown = extract_cited_ids("", {"S1"})
    assert valid == []
    assert unknown == []


def test_duplicate_deduplication() -> None:
    valid, unknown = extract_cited_ids("[S1] again [S1] and [S2].", {"S1", "S2"})
    assert valid == ["S1", "S2"]
    assert unknown == []


def test_s0_is_unknown() -> None:
    valid, unknown = extract_cited_ids("[S0] is not in the allowed set.", {"S1", "S2"})
    assert valid == []
    assert unknown == ["S0"]


def test_s1_without_brackets_not_matched() -> None:
    valid, unknown = extract_cited_ids("S1 without brackets.", {"S1"})
    assert valid == []
    assert unknown == []


def test_s100_handled() -> None:
    valid, unknown = extract_cited_ids("[S100] is valid.", {"S100"})
    assert valid == ["S100"]
    assert unknown == []


def test_unknown_deduplication() -> None:
    valid, unknown = extract_cited_ids("[S99] and [S99] again.", {"S1"})
    assert valid == []
    assert unknown == ["S99"]
