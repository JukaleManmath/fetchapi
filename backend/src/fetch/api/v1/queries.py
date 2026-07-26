"""Grounded Q&A streaming endpoint.

POST /v1/queries/stream  — stream an answer grounded in indexed documentation
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from fetch.api.dependencies import get_workspace_id
from fetch.application.queries.service import QueryService
from fetch.application.retrieval.bm25_retriever import (
    BM25RetrievalConfig,
    BM25Retriever,
)
from fetch.application.retrieval.dense_retriever import (
    DenseRetrievalConfig,
    DenseRetriever,
)
from fetch.application.retrieval.exact_lookup import ExactLookup
from fetch.application.retrieval.expander import ExpansionConfig, RelationshipExpander
from fetch.application.retrieval.fusion import FusionConfig, RRFFusion
from fetch.application.retrieval.normalizer import QueryNormalizer
from fetch.application.retrieval.packer import ContextPacker
from fetch.application.retrieval.reranker import RerankConfig, RetrievalReranker
from fetch.application.retrieval.service import RetrievalConfig, RetrievalService
from fetch.config import get_settings
from fetch.infrastructure.db.repositories import (
    PgChunkRelationRepository,
    PgChunkRepository,
    PgOperationRepository,
    PgQueryRunRepository,
    PgRevisionRepository,
    PgSchemaRepository,
    PgSourceRepository,
)
from fetch.infrastructure.db.session import get_session
from fetch.infrastructure.llm.nvidia_nim import NvidiaNimProvider
from fetch.infrastructure.qdrant.repository import QdrantRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/queries", tags=["queries"])


class QueryStreamRequest(BaseModel):
    source_id: UUID
    question: str


@router.post(
    "/stream",
    summary="Stream a grounded answer for a question about an indexed API",
)
async def stream_query(
    body: QueryStreamRequest,
    request: Request,
) -> StreamingResponse:
    settings = get_settings()
    workspace_id = get_workspace_id()

    question = body.question
    if len(question) > settings.llm.query_max_question_length:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "QUESTION_TOO_LONG",
                "message": f"Question exceeds maximum length of {settings.llm.query_max_question_length} characters.",
            },
        )

    # Resolve source and active revision before streaming
    async with get_session() as session:
        from sqlalchemy import text as sa_text

        source_repo = PgSourceRepository(session)
        rev_repo = PgRevisionRepository(session)

        source = await source_repo.get(body.source_id)
        if source is None or source.workspace_id != workspace_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SOURCE_NOT_FOUND", "message": "Source not found."},
            )

        revision = await rev_repo.get_active(body.source_id)
        if revision is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "NO_ACTIVE_REVISION",
                    "message": "No active revision found. Ingestion may still be in progress.",
                },
            )

        # Qdrant payloads store embedding_profile_id (UUID), not the version string.
        row = await session.execute(
            sa_text("SELECT id FROM embedding_profiles WHERE dense_model_id = :model ORDER BY created_at LIMIT 1"),
            {"model": settings.embeddings.model_id},
        )
        profile_row = row.fetchone()
        embedding_profile_version = str(profile_row[0]) if profile_row else "v1"

    source_id: UUID = body.source_id
    revision_id: UUID = revision.id

    nim: NvidiaNimProvider = request.app.state.llm_provider
    qdrant = QdrantRepository()

    retrieval_config = RetrievalConfig(
        dense=DenseRetrievalConfig(
            model_id=settings.embeddings.model_id,
            top_k=settings.retrieval.dense_candidate_limit,
            embedding_profile_version=embedding_profile_version,
        ),
        bm25=BM25RetrievalConfig(top_k=settings.retrieval.sparse_candidate_limit, embedding_profile_version=embedding_profile_version),
        fusion=FusionConfig(top_k=settings.retrieval.fused_candidate_limit),
        rerank=RerankConfig(
            model_id=settings.reranker.model_id,
            top_n=settings.retrieval.rerank_limit,
        ),
        expansion=ExpansionConfig(),
        final_evidence_limit=settings.retrieval.final_evidence_limit,
    )

    async def event_generator() -> AsyncIterator[str]:
        try:
            async with get_session() as session:
                chunk_repo = PgChunkRepository(session)
                chunk_relation_repo = PgChunkRelationRepository(session)
                operation_repo = PgOperationRepository(session)
                schema_repo = PgSchemaRepository(session)
                query_run_repo = PgQueryRunRepository(session)

                normalizer = QueryNormalizer()
                exact_lookup = ExactLookup(
                    operation_repo=operation_repo,
                    schema_repo=schema_repo,
                    chunk_repo=chunk_repo,
                )
                embedding_provider = getattr(request.app.state, "embedding_provider", nim)
                dense_retriever = DenseRetriever(embedding_provider=embedding_provider, qdrant=qdrant)
                bm25_retriever = BM25Retriever(qdrant=qdrant)
                fusion = RRFFusion()
                reranker = RetrievalReranker(rerank_provider=nim)
                expander = RelationshipExpander(
                    relation_repo=chunk_relation_repo,
                    chunk_repo=chunk_repo,
                )
                packer = ContextPacker()

                retrieval_service = RetrievalService(
                    normalizer=normalizer,
                    exact_lookup=exact_lookup,
                    dense_retriever=dense_retriever,
                    bm25_retriever=bm25_retriever,
                    fusion=fusion,
                    reranker=reranker,
                    expander=expander,
                    packer=packer,
                    query_run_repo=query_run_repo,
                )
                svc = QueryService(
                    retrieval_service=retrieval_service,
                    llm_provider=nim,  # type: ignore[arg-type]
                    query_run_repo=query_run_repo,
                    retrieval_config=retrieval_config,
                    llm_model_id=settings.llm.model_id,
                    llm_max_tokens=settings.llm.max_tokens,
                    abstention_min_chunks=settings.llm.abstention_min_chunks,
                    generation_temperature=settings.llm.generation_temperature,
                )

                async for event in svc.stream(
                    question=question,
                    source_id=source_id,
                    revision_id=revision_id,
                    workspace_id=workspace_id,
                ):
                    yield f"event: {event.event_type}\ndata: {event.to_json()}\n\n"
        except Exception as exc:
            logger.exception("Unhandled error in query stream: %s", exc)
            yield (
                f"event: error\ndata: "
                f"{json.dumps({'code': 'INTERNAL_ERROR', 'message': 'An internal error occurred.', 'retryable': False})}\n\n"
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream")
