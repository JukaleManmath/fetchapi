from __future__ import annotations

from fetch.domain.enums import SupportStatus


def compute_support_status(
    valid_cited_ids: list[str],
    available_ids: list[str],
    unknown_ids: list[str],
) -> SupportStatus:
    if not available_ids:
        return SupportStatus.INSUFFICIENT_EVIDENCE
    if not valid_cited_ids:
        return SupportStatus.INSUFFICIENT_EVIDENCE
    if unknown_ids:
        return SupportStatus.PARTIALLY_SUPPORTED
    return SupportStatus.SUPPORTED
