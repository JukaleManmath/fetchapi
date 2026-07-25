from __future__ import annotations

import re
from collections.abc import Set as AbstractSet

_PATTERN = re.compile(r"\[S(\d+)\]")


def extract_cited_ids(
    text: str,
    allowed_ids: AbstractSet[str],
) -> tuple[list[str], list[str]]:
    """Return (valid_cited_ids, unknown_cited_ids).

    valid_cited_ids: IDs found in text that are in allowed_ids,
                     deduplicated, in order of first appearance.
    unknown_cited_ids: IDs found in text NOT in allowed_ids.
    """
    valid: list[str] = []
    unknown: list[str] = []
    seen_valid: set[str] = set()
    seen_unknown: set[str] = set()
    for m in _PATTERN.finditer(text):
        sid = f"S{m.group(1)}"
        if sid in allowed_ids:
            if sid not in seen_valid:
                valid.append(sid)
                seen_valid.add(sid)
        else:
            if sid not in seen_unknown:
                unknown.append(sid)
                seen_unknown.add(sid)
    return valid, unknown
