"""Tests for EndpointMatcher."""

from __future__ import annotations

from uuid import uuid4

from fetch.application.validation.endpoint_matcher import EndpointMatcher
from fetch.domain.entities import ApiOperation, ApiServer
from fetch.domain.enums import HttpMethod, MatchConfidence


def _make_op(
    method: str,
    path: str,
    path_normalized: str | None = None,
) -> ApiOperation:
    return ApiOperation(
        id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        method=HttpMethod(method.upper()),
        path=path,
        path_normalized=path_normalized or path.lower().rstrip("/"),
        operation_id=None,
        summary=None,
        description=None,
        tags=[],
        deprecated=False,
        logical_key=f"test:{method.upper()}:{path}",
        source_pointer=None,
    )


def _make_server(url: str) -> ApiServer:
    return ApiServer(
        id=uuid4(), revision_id=uuid4(), url=url, description=None, variables={}
    )


def test_exact_match_post() -> None:
    op = _make_op("POST", "/v1/customers")
    matcher = EndpointMatcher(operations=[op], servers=[])
    result = matcher.match("POST", "https://api.example.com/v1/customers")
    assert result.operation == op
    assert result.match_confidence == MatchConfidence.EXACT


def test_path_template_match() -> None:
    op = _make_op("GET", "/v1/customers/{id}")
    matcher = EndpointMatcher(operations=[op], servers=[])
    result = matcher.match("GET", "https://api.example.com/v1/customers/cus_123")
    assert result.operation == op
    assert result.path_params == {"id": "cus_123"}
    assert result.match_confidence == MatchConfidence.PATH_TEMPLATE


def test_server_base_url_stripped() -> None:
    op = _make_op("GET", "/v1/customers")
    server = _make_server("https://api.example.com")
    matcher = EndpointMatcher(operations=[op], servers=[server])
    result = matcher.match("GET", "https://api.example.com/v1/customers")
    assert result.operation == op
    assert result.match_confidence == MatchConfidence.EXACT


def test_wrong_method_returns_no_match() -> None:
    op = _make_op("POST", "/v1/customers")
    matcher = EndpointMatcher(operations=[op], servers=[])
    result = matcher.match("GET", "https://api.example.com/v1/customers")
    assert result.operation is None
    assert result.match_confidence == MatchConfidence.NO_MATCH


def test_two_path_params() -> None:
    op = _make_op("GET", "/v1/subscriptions/{sub_id}/items/{item_id}")
    matcher = EndpointMatcher(operations=[op], servers=[])
    result = matcher.match(
        "GET", "https://api.example.com/v1/subscriptions/sub_1/items/item_2"
    )
    assert result.operation == op
    assert result.path_params == {"sub_id": "sub_1", "item_id": "item_2"}


def test_no_operations_returns_no_match() -> None:
    matcher = EndpointMatcher(operations=[], servers=[])
    result = matcher.match("GET", "https://api.example.com/v1/anything")
    assert result.operation is None
    assert result.match_confidence == MatchConfidence.NO_MATCH


def test_most_specific_match_wins() -> None:
    generic = _make_op("GET", "/v1/items/{id}")
    specific = _make_op("GET", "/v1/items/featured")
    matcher = EndpointMatcher(operations=[generic, specific], servers=[])
    result = matcher.match("GET", "https://api.example.com/v1/items/featured")
    # exact match on the specific one
    assert result.operation == specific
    assert result.match_confidence == MatchConfidence.EXACT
