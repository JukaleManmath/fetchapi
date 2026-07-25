from __future__ import annotations

import base64
import json
import re
import shlex
import urllib.parse

from fetch.domain.entities import ParsedRequest
from fetch.domain.errors import CurlParseError

_ANSI_C_QUOTE = re.compile(r"\$'((?:[^'\\]|\\.)*)'")


def _preprocess(curl_string: str) -> str:
    """Convert $'...' ANSI-C quoting to regular single-quoted strings."""

    def _replace(m: re.Match[str]) -> str:
        return "'" + m.group(1).replace("\\'", "'") + "'"

    return _ANSI_C_QUOTE.sub(_replace, curl_string.strip())


def parse_curl(curl_string: str) -> ParsedRequest:
    if not curl_string or not curl_string.strip():
        raise CurlParseError("Empty curl command")

    preprocessed = _preprocess(curl_string)
    try:
        tokens = shlex.split(preprocessed, posix=True)
    except ValueError as e:
        raise CurlParseError(f"Failed to parse curl command: {e}") from e

    # Strip leading "curl" token
    if tokens and tokens[0].lower() == "curl":
        tokens = tokens[1:]

    method: str | None = None
    headers: dict[str, str] = {}
    body_raw: str | None = None
    url: str | None = None
    force_get = False

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok in ("-X", "--request"):
            i += 1
            if i < len(tokens):
                method = tokens[i].upper()
        elif tok in ("-H", "--header"):
            i += 1
            if i < len(tokens):
                key, _, val = tokens[i].partition(":")
                headers[key.strip().lower()] = val.strip()
        elif tok in ("-d", "--data", "--data-raw", "--data-ascii", "--data-binary"):
            i += 1
            if i < len(tokens):
                body_raw = tokens[i]
        elif tok == "--json":
            i += 1
            if i < len(tokens):
                body_raw = tokens[i]
                if "content-type" not in headers:
                    headers["content-type"] = "application/json"
        elif tok in ("-u", "--user"):
            i += 1
            if i < len(tokens):
                encoded = base64.b64encode(tokens[i].encode()).decode()
                headers["authorization"] = f"Basic {encoded}"
        elif tok in ("-G", "--get"):
            force_get = True
        elif tok in (
            "-L",
            "--location",
            "--compressed",
            "--silent",
            "-s",
            "--no-keepalive",
            "--http1.1",
            "--http2",
        ):
            pass  # ignore
        elif tok.startswith("-"):
            # Unknown flag — skip its argument if it looks like a value flag
            if "=" in tok:
                pass  # self-contained
            elif i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                i += 1  # consume next token as argument
        elif url is None:
            url = tok

        i += 1

    if not url:
        raise CurlParseError("No URL found in curl command")

    # Ensure scheme
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed_url = urllib.parse.urlparse(url)
    query_params: dict[str, str] = {
        k: v[0] for k, v in urllib.parse.parse_qs(parsed_url.query).items()
    }

    # -G converts body to query params
    if force_get and body_raw:
        extra = dict(urllib.parse.parse_qsl(body_raw))
        query_params.update(extra)
        body_raw = None
        method = method or "GET"

    method = method or ("POST" if body_raw else "GET")
    content_type = headers.get("content-type")
    auth_header = headers.get("authorization")

    # Attempt JSON parse of body
    body_json: dict[str, object] | None = None
    is_url_encoded = False
    if body_raw:
        stripped = body_raw.strip()
        if stripped.startswith("{") or (content_type and "json" in content_type):
            try:
                body_json = json.loads(stripped)
            except json.JSONDecodeError:
                pass
        if (
            body_json is None
            and content_type
            and "x-www-form-urlencoded" in content_type
        ):
            is_url_encoded = True

    return ParsedRequest(
        method=method,
        url=url,
        headers=headers,
        body_raw=body_raw,
        body_json=body_json,
        content_type=content_type,
        auth_header=auth_header,
        query_params=query_params,
        is_url_encoded_body=is_url_encoded,
    )
