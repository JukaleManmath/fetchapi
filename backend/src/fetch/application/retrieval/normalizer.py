"""Query normalizer for structured identifier extraction.

Extracts HTTP methods, path patterns, operation IDs, schema names, status codes,
and significant keywords from a raw natural-language question — no LLM involved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Words that appear PascalCase but are common English and should not be treated
# as schema names.
_COMMON_PASCAL_WORDS: frozenset[str] = frozenset(
    {
        "I",
        "The",
        "A",
        "An",
        "In",
        "Is",
        "It",
        "My",
        "We",
        "He",
        "She",
        "They",
        "You",
        "Do",
        "How",
        "What",
        "When",
        "Where",
        "Why",
        "Which",
        "Who",
        "Can",
        "Will",
        "Should",
        "Does",
        "Are",
        "Was",
        "Were",
        "Has",
        "Have",
        "Had",
        "Get",
        "Post",
        "Put",
        "Delete",
        "Patch",
        "Head",
        "If",
        "Or",
        "And",
        "But",
        "So",
        "To",
        "Of",
        "On",
        "At",
        "By",
        "For",
        "Not",
        "This",
        "That",
        "With",
        "From",
        "Up",
        "Out",
        "As",
        "Be",
        "No",
        "All",
        "Any",
        "Its",
        "New",
        "True",
        "False",
        "None",
        "Api",
        "Url",
        "Id",
        "Ok",
        "Json",
        "Http",
        "Https",
    }
)

# Stop words filtered out of the keywords list.
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "it",
        "in",
        "on",
        "at",
        "to",
        "of",
        "for",
        "by",
        "or",
        "and",
        "but",
        "so",
        "do",
        "does",
        "did",
        "are",
        "was",
        "were",
        "has",
        "have",
        "had",
        "be",
        "been",
        "being",
        "with",
        "from",
        "as",
        "up",
        "out",
        "if",
        "not",
        "no",
        "this",
        "that",
        "my",
        "its",
        "i",
        "we",
        "he",
        "she",
        "they",
        "you",
        "get",
        "post",
        "put",
        "delete",
        "patch",
        "how",
        "what",
        "when",
        "where",
        "why",
        "which",
        "who",
        "can",
        "will",
        "should",
        "would",
        "could",
        "may",
        "might",
        "return",
        "returns",
        "work",
        "works",
        "use",
        "using",
        "used",
        "make",
        "call",
        "calls",
        "send",
        "receive",
        "new",
        "all",
        "any",
        "api",
        "url",
        "http",
        "https",
        "tell",
        "me",
        "about",
        "show",
        "give",
        "need",
        "want",
        "than",
        "then",
        "just",
        "like",
        "also",
        "more",
    }
)

# Matches HTTP method as a standalone token (whole word, case-insensitive).
_HTTP_METHOD_RE = re.compile(
    r"\b(GET|POST|PUT|DELETE|PATCH)\b", re.IGNORECASE
)

# Matches URL path segments starting with /, including {param} placeholders.
# Stops at whitespace, comma, or closing punctuation.
_PATH_PATTERN_RE = re.compile(
    r"(/(?:[a-zA-Z0-9_\-\.~%]|\{[a-zA-Z0-9_]+\})+(?:/(?:[a-zA-Z0-9_\-\.~%]|\{[a-zA-Z0-9_]+\})*)*)"
)

# camelCase: lowercase letter followed by uppercase (e.g. createCustomer).
# Must have at least one internal uppercase to qualify as two "words".
_CAMEL_CASE_RE = re.compile(r"\b([a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*)\b")

# snake_case with a verb-like prefix: verb_noun with at least one underscore
# and at least 2 segments (e.g. create_customer, list_payments).
_SNAKE_CASE_RE = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z][a-z0-9]+)+)\b")

# PascalCase: starts uppercase, has at least one more uppercase letter mid-word
# (i.e., not a plain capitalised word like "The").  Minimum 4 chars so single
# three-letter acronyms (URL, API) are excluded unless they compound.
_PASCAL_CASE_RE = re.compile(r"\b([A-Z][a-z]+(?:[A-Z][a-z0-9]+)+)\b")

# 3-digit HTTP status codes in range 100-599.
_STATUS_CODE_RE = re.compile(r"\b([1-5][0-9]{2})\b")


@dataclass(frozen=True)
class NormalizedQuery:
    """Value object produced by QueryNormalizer.normalize().

    All fields are derived deterministically from the raw question text using
    regex only — no LLM is involved.  Downstream retrieval stages use the
    extracted identifiers to build targeted filters before falling back to
    semantic search.
    """

    raw_text: str
    method: str | None = None
    path_pattern: str | None = None
    operation_id: str | None = None
    schema_names: list[str] = field(default_factory=list)
    status_codes: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


class QueryNormalizer:
    """Extracts structured identifiers from a natural-language API question.

    All extraction is regex-based and executes in O(n) time relative to the
    length of the question.  The class is stateless; a single instance may be
    shared across concurrent calls.
    """

    def normalize(self, question: str) -> NormalizedQuery:
        """Parse *question* and return a :class:`NormalizedQuery`.

        Extraction order matters: methods and paths are removed from the token
        pool before keyword extraction so they do not appear redundantly in the
        keywords list.
        """
        method = self._extract_method(question)
        path_pattern = self._extract_path(question)
        operation_id = self._extract_operation_id(question)
        schema_names = self._extract_schema_names(question)
        status_codes = self._extract_status_codes(question)
        keywords = self._extract_keywords(
            question,
            method=method,
            path_pattern=path_pattern,
            operation_id=operation_id,
            schema_names=schema_names,
            status_codes=status_codes,
        )
        return NormalizedQuery(
            raw_text=question,
            method=method,
            path_pattern=path_pattern,
            operation_id=operation_id,
            schema_names=schema_names,
            status_codes=status_codes,
            keywords=keywords,
        )

    # ------------------------------------------------------------------
    # Private extraction helpers
    # ------------------------------------------------------------------

    def _extract_method(self, text: str) -> str | None:
        """Return the first HTTP method found, uppercased, or None."""
        match = _HTTP_METHOD_RE.search(text)
        return match.group(1).upper() if match else None

    def _extract_path(self, text: str) -> str | None:
        """Return the first URL path pattern found, or None."""
        match = _PATH_PATTERN_RE.search(text)
        return match.group(1) if match else None

    def _extract_operation_id(self, text: str) -> str | None:
        """Return the first camelCase or qualifying snake_case identifier, or None.

        camelCase is preferred over snake_case when both appear.
        """
        camel_match = _CAMEL_CASE_RE.search(text)
        snake_match = _SNAKE_CASE_RE.search(text)

        camel_pos = camel_match.start() if camel_match else len(text)
        snake_pos = snake_match.start() if snake_match else len(text)

        if camel_pos <= snake_pos and camel_match:
            return camel_match.group(1)
        if snake_match:
            return snake_match.group(1)
        return None

    def _extract_schema_names(self, text: str) -> list[str]:
        """Return PascalCase words that are likely schema/model names."""
        candidates = _PASCAL_CASE_RE.findall(text)
        return [c for c in candidates if c not in _COMMON_PASCAL_WORDS]

    def _extract_status_codes(self, text: str) -> list[str]:
        """Return all 3-digit HTTP status codes found in *text*."""
        return _STATUS_CODE_RE.findall(text)

    def _extract_keywords(
        self,
        text: str,
        *,
        method: str | None,
        path_pattern: str | None,
        operation_id: str | None,
        schema_names: list[str],
        status_codes: list[str],
    ) -> list[str]:
        """Return significant tokens after stripping already-extracted identifiers.

        Steps:
        1. Remove path patterns (they contain slashes that confuse tokenisation).
        2. Tokenise on non-alphanumeric characters.
        3. Drop stop words, short tokens (<3 chars), status codes, and tokens
           that are already captured as method/operation_id/schema_names.
        """
        residual = text
        if path_pattern:
            residual = residual.replace(path_pattern, " ")

        already_extracted: set[str] = set()
        if method:
            already_extracted.add(method.lower())
        if operation_id:
            already_extracted.add(operation_id.lower())
        for name in schema_names:
            already_extracted.add(name.lower())
        already_extracted.update(sc.lower() for sc in status_codes)

        tokens = re.split(r"[^a-zA-Z0-9_]+", residual)
        seen: set[str] = set()
        keywords: list[str] = []
        for token in tokens:
            lower = token.lower()
            if (
                len(token) < 3
                or lower in _STOP_WORDS
                or lower in already_extracted
                or lower in seen
            ):
                continue
            seen.add(lower)
            keywords.append(token)
        return keywords
