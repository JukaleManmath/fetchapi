"""Tests for curl_parser.parse_curl."""

from __future__ import annotations

import base64

import pytest

from fetch.application.validation.curl_parser import parse_curl
from fetch.domain.errors import CurlParseError


def test_simple_get() -> None:
    result = parse_curl("curl https://example.com/v1/items")
    assert result.method == "GET"
    assert "example.com" in result.url
    assert result.body_raw is None


def test_post_with_body_and_content_type() -> None:
    result = parse_curl(
        "curl -X POST https://api.example.com/items "
        '-H "Content-Type: application/json" '
        '-d \'{"name":"test"}\''
    )
    assert result.method == "POST"
    assert result.content_type == "application/json"
    assert result.body_json == {"name": "test"}


def test_multi_line_with_continuation() -> None:
    curl = (
        "curl https://api.example.com/v1/users \\\n"
        '  -H "Authorization: Bearer tok" \\\n'
        "  -X GET"
    )
    result = parse_curl(curl)
    assert result.method == "GET"
    assert "authorization" in result.headers


def test_basic_auth_user_flag() -> None:
    result = parse_curl("curl -u user:pass https://example.com/v1")
    assert "authorization" in result.headers
    encoded = base64.b64encode(b"user:pass").decode()
    assert result.headers["authorization"] == f"Basic {encoded}"


def test_json_flag_injects_content_type() -> None:
    result = parse_curl("curl --json '{\"a\":1}' https://example.com/v1")
    assert result.body_json == {"a": 1}
    assert result.content_type == "application/json"


def test_empty_data_body() -> None:
    result = parse_curl("curl -d '' https://example.com/v1")
    assert result.body_raw == ""
    assert result.body_json is None


def test_get_with_data_converts_to_query_params() -> None:
    result = parse_curl("curl -G -d 'foo=bar&baz=qux' https://example.com/v1")
    assert result.method == "GET"
    assert result.query_params.get("foo") == "bar"
    assert result.query_params.get("baz") == "qux"
    assert result.body_raw is None


def test_url_without_scheme_gets_https() -> None:
    result = parse_curl("curl example.com/v1/items")
    assert result.url.startswith("https://")


def test_multiple_headers_all_captured() -> None:
    result = parse_curl('curl https://example.com -H "X-Custom: foo" -H "X-Other: bar"')
    assert result.headers.get("x-custom") == "foo"
    assert result.headers.get("x-other") == "bar"


def test_data_raw_with_embedded_quotes() -> None:
    result = parse_curl(
        'curl -X POST https://example.com --data-raw \'{"key":"val with spaces"}\''
    )
    assert result.body_json == {"key": "val with spaces"}


def test_request_delete_sets_method() -> None:
    result = parse_curl("curl --request DELETE https://example.com/v1/item/1")
    assert result.method == "DELETE"


def test_missing_url_raises_curl_parse_error() -> None:
    with pytest.raises(CurlParseError):
        parse_curl("curl -X POST -H 'Content-Type: application/json'")


def test_valid_json_body_populated() -> None:
    result = parse_curl(
        "curl -X POST https://api.example.com -d '{\"id\": 1}' "
        '-H "Content-Type: application/json"'
    )
    assert result.body_json == {"id": 1}


def test_non_json_body_is_none() -> None:
    result = parse_curl(
        "curl -X POST https://api.example.com "
        '-H "Content-Type: text/plain" '
        "-d 'hello world'"
    )
    assert result.body_json is None
    assert result.body_raw == "hello world"


def test_empty_curl_raises_error() -> None:
    with pytest.raises(CurlParseError):
        parse_curl("")
