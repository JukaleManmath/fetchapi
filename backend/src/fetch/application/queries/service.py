from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from uuid import UUID

from fetch.application.queries.citation_extractor import extract_cited_ids
from fetch.application.queries.events import (
    DoneEvent,
    ErrorEvent,
    EvidenceEvent,
    ResultEvent,
    StartEvent,
    TokenEvent,
)
from fetch.application.queries.prompt import (
    PROMPT_VERSION,
    build_system_prompt,
    build_user_message,
)
from fetch.application.queries.support_status import compute_support_status
from fetch.application.retrieval.service import RetrievalConfig, RetrievalService
from fetch.domain.enums import QueryWorkflow, SupportStatus
from fetch.domain.protocols import (
    GenerationConfig,
    LLMMessage,
    LLMProvider,
    QueryRunRepository,
)

logger = logging.getLogger(__name__)

# Union type for all event kinds yielded by stream()
StreamEventType = (
    StartEvent | TokenEvent | EvidenceEvent | ResultEvent | DoneEvent | ErrorEvent
)


class QueryService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        llm_provider: LLMProvider,
        query_run_repo: QueryRunRepository,
        retrieval_config: RetrievalConfig,
        llm_model_id: str,
        llm_max_tokens: int = 4096,
        abstention_min_chunks: int = 1,
        generation_temperature: float = 0.1,
    ) -> None:
        self._retrieval = retrieval_service
        self._llm = llm_provider
        self._repo = query_run_repo
        self._retrieval_config = retrieval_config
        self._llm_model_id = llm_model_id
        self._llm_max_tokens = llm_max_tokens
        self._abstention_min_chunks = abstention_min_chunks
        self._temperature = generation_temperature

    async def stream(
        self,
        question: str,
        source_id: UUID,
        revision_id: UUID,
        workspace_id: UUID,
    ) -> AsyncIterator[StreamEventType]:
        # Retrieve context
        packed, run = await self._retrieval.retrieve(
            question=question,
            source_id=source_id,
            revision_id=revision_id,
            workspace_id=workspace_id,
            workflow=QueryWorkflow.DOC_QA,
            config=self._retrieval_config,
        )

        yield StartEvent(query_id=run.id, workflow="doc_qa")

        # Abstention: no evidence, skip LLM entirely
        if len(packed.citations) < self._abstention_min_chunks:
            run.support_status = SupportStatus.INSUFFICIENT_EVIDENCE
            run.prompt_version = None
            run.intent_classification = "doc_qa"
            run.warnings = [
                "No supporting evidence found in the indexed documentation."
            ]
            await self._repo.save(run)
            retrieval_ms = run.retrieval_ms or 0
            yield ResultEvent(
                query_id=run.id,
                cited_source_ids=[],
                support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
                warnings=run.warnings,
                usage=None,
                latency_ms={
                    "retrieval_ms": retrieval_ms,
                    "generation_ms": 0,
                    "total_ms": retrieval_ms,
                },
            )
            yield DoneEvent()
            return

        yield EvidenceEvent(citations=packed.citations)

        allowed_ids = list(packed.source_id_map.keys())
        system_prompt = build_system_prompt(packed.context_text, allowed_ids)
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=build_user_message(question)),
        ]

        gen_config = GenerationConfig(
            model_id=self._llm_model_id,
            max_tokens=self._llm_max_tokens,
            temperature=self._temperature,
        )

        full_text = ""
        usage = None
        t_start = time.monotonic()
        generation_ms = 0

        try:
            stream_iter = await self._llm.generate_stream(messages, gen_config)  # type: ignore[misc]
            async for chunk in stream_iter:
                if chunk.text:
                    full_text += chunk.text
                    yield TokenEvent(text=chunk.text)
                if chunk.usage:
                    usage = chunk.usage
            generation_ms = int((time.monotonic() - t_start) * 1000)
        except Exception as exc:
            generation_ms = int((time.monotonic() - t_start) * 1000)
            run.support_status = SupportStatus.INSUFFICIENT_EVIDENCE
            run.prompt_version = PROMPT_VERSION
            run.intent_classification = "doc_qa"
            run.warnings = [f"Generation failed: {exc}"]
            run.generation_ms = generation_ms
            await self._repo.save(run)
            logger.warning("LLM generation failed for query %s: %s", run.id, exc)
            yield ErrorEvent(code="PROVIDER_ERROR", message=str(exc), retryable=True)
            return

        valid_ids, unknown_ids = extract_cited_ids(full_text, set(allowed_ids))
        status = compute_support_status(valid_ids, allowed_ids, unknown_ids)

        warnings: list[str] = []
        if unknown_ids:
            warnings.append(
                f"Model cited unknown source IDs that were removed: {', '.join(unknown_ids)}"
            )
            logger.warning("Query %s: unknown citation IDs %s", run.id, unknown_ids)

        cited_citations = [c for c in packed.citations if c.source_id in set(valid_ids)]
        retrieval_ms = run.retrieval_ms or 0
        total_ms = retrieval_ms + generation_ms

        run.answer = full_text
        run.citations = cited_citations
        run.support_status = status
        run.warnings = warnings
        run.prompt_version = PROMPT_VERSION
        run.intent_classification = "doc_qa"
        run.generation_ms = generation_ms
        run.total_ms = total_ms
        if usage:
            run.prompt_tokens = usage.prompt_tokens
            run.completion_tokens = usage.completion_tokens
        await self._repo.save(run)

        usage_dict: dict[str, object] | None = None
        if usage:
            usage_dict = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": (usage.prompt_tokens or 0)
                + (usage.completion_tokens or 0),
            }

        yield ResultEvent(
            query_id=run.id,
            cited_source_ids=valid_ids,
            support_status=status,
            warnings=warnings,
            usage=usage_dict,
            latency_ms={
                "retrieval_ms": retrieval_ms,
                "generation_ms": generation_ms,
                "total_ms": total_ms,
            },
        )
        yield DoneEvent()
