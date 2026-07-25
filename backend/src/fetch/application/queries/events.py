from __future__ import annotations

import json
from dataclasses import dataclass, field
from uuid import UUID

from fetch.domain.entities import Citation
from fetch.domain.enums import SupportStatus


@dataclass
class StreamEvent:
    event_type: str = field(init=False)

    def to_json(self) -> str:
        raise NotImplementedError


@dataclass
class StartEvent(StreamEvent):
    query_id: UUID
    workflow: str
    event_type: str = field(init=False, default="start")

    def to_json(self) -> str:
        return json.dumps({"query_id": str(self.query_id), "workflow": self.workflow})


@dataclass
class TokenEvent(StreamEvent):
    text: str
    event_type: str = field(init=False, default="token")

    def to_json(self) -> str:
        return json.dumps({"text": self.text})


@dataclass
class EvidenceEvent(StreamEvent):
    citations: list[Citation]
    event_type: str = field(init=False, default="evidence")

    def to_json(self) -> str:
        items = [
            {
                "source_id": c.source_id,
                "chunk_id": str(c.chunk_id),
                "entity_type": c.entity_type,
                "title": c.title,
                "source_url": c.source_url,
                "source_pointer": c.source_pointer,
                "method": c.method,
                "path": c.path,
            }
            for c in self.citations
        ]
        return json.dumps({"citations": items})


@dataclass
class ResultEvent(StreamEvent):
    query_id: UUID
    cited_source_ids: list[str]
    support_status: SupportStatus
    warnings: list[str]
    usage: dict[str, object] | None
    latency_ms: dict[str, object]
    event_type: str = field(init=False, default="result")

    def to_json(self) -> str:
        return json.dumps(
            {
                "query_id": str(self.query_id),
                "cited_source_ids": self.cited_source_ids,
                "support_status": self.support_status.value,
                "warnings": self.warnings,
                "usage": self.usage,
                "latency_ms": self.latency_ms,
            }
        )


@dataclass
class DoneEvent(StreamEvent):
    event_type: str = field(init=False, default="done")

    def to_json(self) -> str:
        return json.dumps({})


@dataclass
class ErrorEvent(StreamEvent):
    code: str
    message: str
    retryable: bool
    event_type: str = field(init=False, default="error")

    def to_json(self) -> str:
        return json.dumps(
            {"code": self.code, "message": self.message, "retryable": self.retryable}
        )
