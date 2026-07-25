from __future__ import annotations

from fetch.domain.entities import ErrorDefinition, ErrorStatusMatch


class ErrorStatusLookup:
    def lookup(
        self,
        received_status_code: str | None,
        error_definitions: list[ErrorDefinition],
    ) -> ErrorStatusMatch | None:
        if received_status_code is None:
            return None
        matched = [
            e
            for e in error_definitions
            if getattr(e, "status_code", None) == received_status_code
        ]
        return ErrorStatusMatch(
            status_code=received_status_code,
            matched_definitions=matched,
            is_documented=len(matched) > 0,
        )
