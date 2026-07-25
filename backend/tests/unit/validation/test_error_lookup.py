"""Tests for ErrorStatusLookup."""

from __future__ import annotations

from uuid import uuid4

from fetch.application.validation.error_lookup import ErrorStatusLookup
from fetch.domain.entities import ErrorDefinition


def _make_error(status_code: str | None) -> ErrorDefinition:
    return ErrorDefinition(
        id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        operation_id=None,
        status_code=status_code,
        error_code=None,
        title=f"Error {status_code}",
        description=f"Description for {status_code}",
        source_pointer=None,
    )


class TestErrorStatusLookup:
    def setup_method(self) -> None:
        self.lookup = ErrorStatusLookup()

    def test_matching_status_code_is_documented(self) -> None:
        errors = [_make_error("401"), _make_error("404")]
        result = self.lookup.lookup("401", errors)
        assert result is not None
        assert result.is_documented is True
        assert result.status_code == "401"
        assert len(result.matched_definitions) == 1

    def test_non_matching_status_code_not_documented(self) -> None:
        errors = [_make_error("404")]
        result = self.lookup.lookup("500", errors)
        assert result is not None
        assert result.is_documented is False
        assert len(result.matched_definitions) == 0

    def test_none_input_returns_none(self) -> None:
        result = self.lookup.lookup(None, [_make_error("404")])
        assert result is None

    def test_multiple_matching_definitions(self) -> None:
        errors = [_make_error("400"), _make_error("400"), _make_error("404")]
        result = self.lookup.lookup("400", errors)
        assert result is not None
        assert len(result.matched_definitions) == 2
        assert result.is_documented is True
