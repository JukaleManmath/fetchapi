"""Context packer: assigns stable [S1], [S2], ... source IDs to evidence chunks.

Application layer — no FastAPI, SQLAlchemy, Qdrant, or LLM SDK imports.
Pure sync: context formatting is CPU-only string work with no I/O.
"""

from dataclasses import dataclass
from uuid import UUID

from fetch.domain.entities import Citation
from fetch.infrastructure.qdrant.models import ChunkHit


@dataclass(frozen=True)
class PackedContext:
    """Result of packing a ranked list of evidence chunks for LLM injection."""

    citations: list[Citation]
    context_text: str
    source_id_map: dict[str, UUID]  # "S1" -> chunk_id UUID


def _format_entry(source_label: str, payload: dict) -> str:
    """Format a single evidence entry for the context text block."""
    entity_type = payload.get("entity_type", "")
    title = payload.get("title", "")
    method = payload.get("method")
    path = payload.get("path")
    content = payload.get("text", "")

    lines: list[str] = [f"[{source_label}] {entity_type} — {title}"]

    if method and path:
        lines.append(f"Method: {method} {path}")

    lines.append(content)
    return "\n".join(lines)


class ContextPacker:
    """Assigns stable citation IDs to evidence hits and formats context text."""

    def pack(self, hits: list[ChunkHit]) -> PackedContext:
        """Assign [S1], [S2], ... IDs to hits and build a PackedContext.

        Order is preserved from the input list. Missing payload fields are
        handled with .get() defaults — no KeyError will propagate.
        """
        if not hits:
            return PackedContext(citations=[], context_text="", source_id_map={})

        citations: list[Citation] = []
        source_id_map: dict[str, UUID] = {}
        entry_texts: list[str] = []

        for index, hit in enumerate(hits, start=1):
            source_label = f"S{index}"
            payload = hit.payload

            raw_entity_id = payload.get("entity_id")
            entity_id: UUID | None
            if raw_entity_id is not None:
                try:
                    entity_id = UUID(str(raw_entity_id))
                except (ValueError, AttributeError):
                    entity_id = None
            else:
                entity_id = None

            citation = Citation(
                source_id=source_label,
                chunk_id=hit.chunk_id,
                entity_type=payload.get("entity_type", ""),
                entity_id=entity_id,
                title=payload.get("title", ""),
                content=payload.get("text", ""),
                source_url=payload.get("source_url"),
                source_pointer=payload.get("source_pointer"),
                api_version=payload.get("api_version"),
                method=payload.get("method"),
                path=payload.get("path"),
            )

            citations.append(citation)
            source_id_map[source_label] = hit.chunk_id
            entry_texts.append(_format_entry(source_label, payload))

        context_text = "\n\n".join(entry_texts)
        return PackedContext(
            citations=citations,
            context_text=context_text,
            source_id_map=source_id_map,
        )
