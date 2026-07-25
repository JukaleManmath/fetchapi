"""MCP service factory functions.

Plain async functions that construct application services with their
repositories injected. MCP tools call these directly (not via FastAPI Depends).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from fetch.application.comparisons.service import VersionDiffService
from fetch.application.integrations.contract_validator import ContractValidator
from fetch.application.integrations.loader import IntegrationContextAssembler
from fetch.application.integrations.service import IntegrationService
from fetch.application.integrations.syntax_validator import SyntaxValidatorDispatcher
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
from fetch.application.validation.error_lookup import ErrorStatusLookup
from fetch.application.validation.service import ValidationService
from fetch.application.validation.validators import (
    BodyValidator,
    HeaderValidator,
    ParameterValidator,
)
from fetch.config import get_settings
from fetch.infrastructure.db.repositories import (
    PgAuthSchemeRepository,
    PgChunkRelationRepository,
    PgChunkRepository,
    PgDiagnosticRunRepository,
    PgErrorRepository,
    PgExampleRepository,
    PgIntegrationRunRepository,
    PgOperationRepository,
    PgParameterRepository,
    PgQueryRunRepository,
    PgRequestBodyRepository,
    PgResponseRepository,
    PgRevisionRepository,
    PgSchemaRepository,
    PgServerRepository,
    PgSourceRepository,
    PgVersionDiffRepository,
)
from fetch.infrastructure.llm.nvidia_nim import NvidiaNimProvider
from fetch.infrastructure.qdrant.repository import QdrantRepository


def _get_llm_provider() -> NvidiaNimProvider:
    settings = get_settings()
    return NvidiaNimProvider(
        api_key=settings.llm.api_key.get_secret_value(),
        base_url=settings.llm.base_url,
        timeout_seconds=settings.llm.timeout_seconds,
    )


def get_source_repo(session: AsyncSession) -> PgSourceRepository:
    return PgSourceRepository(session)


def get_revision_repo(session: AsyncSession) -> PgRevisionRepository:
    return PgRevisionRepository(session)


def get_operation_repo(session: AsyncSession) -> PgOperationRepository:
    return PgOperationRepository(session)


def get_schema_repo(session: AsyncSession) -> PgSchemaRepository:
    return PgSchemaRepository(session)


def get_auth_scheme_repo(session: AsyncSession) -> PgAuthSchemeRepository:
    return PgAuthSchemeRepository(session)


def get_query_service(session: AsyncSession) -> "QueryServiceBundle":
    """Return a bundle with QueryService and its dependencies."""
    settings = get_settings()
    llm_provider = _get_llm_provider()
    qdrant = QdrantRepository()

    chunk_repo = PgChunkRepository(session)
    chunk_relation_repo = PgChunkRelationRepository(session)
    operation_repo = PgOperationRepository(session)
    schema_repo = PgSchemaRepository(session)
    query_run_repo = PgQueryRunRepository(session)

    retrieval_config = RetrievalConfig(
        dense=DenseRetrievalConfig(
            model_id=settings.embeddings.model_id,
            top_k=settings.retrieval.dense_candidate_limit,
        ),
        bm25=BM25RetrievalConfig(top_k=settings.retrieval.sparse_candidate_limit),
        fusion=FusionConfig(top_k=settings.retrieval.fused_candidate_limit),
        rerank=RerankConfig(
            model_id=settings.reranker.model_id,
            top_n=settings.retrieval.rerank_limit,
        ),
        expansion=ExpansionConfig(),
    )

    normalizer = QueryNormalizer()
    exact_lookup = ExactLookup(
        operation_repo=operation_repo,
        schema_repo=schema_repo,
        chunk_repo=chunk_repo,
    )
    dense_retriever = DenseRetriever(embedding_provider=llm_provider, qdrant=qdrant)
    bm25_retriever = BM25Retriever(qdrant=qdrant)
    fusion = RRFFusion()
    reranker = RetrievalReranker(rerank_provider=llm_provider)
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
        llm_provider=llm_provider,  # type: ignore[arg-type]
        query_run_repo=query_run_repo,
        retrieval_config=retrieval_config,
        llm_model_id=settings.llm.model_id,
        llm_max_tokens=settings.llm.max_tokens,
        abstention_min_chunks=settings.llm.abstention_min_chunks,
        generation_temperature=settings.llm.generation_temperature,
    )
    return QueryServiceBundle(service=svc, llm_provider=llm_provider)


class QueryServiceBundle:
    def __init__(self, service: QueryService, llm_provider: NvidiaNimProvider) -> None:
        self.service = service
        self.llm_provider = llm_provider


def get_integration_service(session: AsyncSession) -> IntegrationService:
    settings = get_settings()
    llm_provider = _get_llm_provider()

    operation_repo = PgOperationRepository(session)
    server_repo = PgServerRepository(session)
    auth_scheme_repo = PgAuthSchemeRepository(session)
    parameter_repo = PgParameterRepository(session)
    request_body_repo = PgRequestBodyRepository(session)
    response_repo = PgResponseRepository(session)
    example_repo = PgExampleRepository(session)
    error_repo = PgErrorRepository(session)
    integration_run_repo = PgIntegrationRunRepository(session)

    context_loader = IntegrationContextAssembler(
        operation_repo=operation_repo,
        server_repo=server_repo,
        auth_scheme_repo=auth_scheme_repo,
        parameter_repo=parameter_repo,
        request_body_repo=request_body_repo,
        response_repo=response_repo,
        example_repo=example_repo,
        error_repo=error_repo,
    )

    return IntegrationService(
        context_loader=context_loader,
        llm_provider=llm_provider,  # type: ignore[arg-type]
        contract_validator=ContractValidator(),
        syntax_validator=SyntaxValidatorDispatcher(),
        integration_repo=integration_run_repo,
        llm_model_id=settings.llm.model_id,
        llm_max_tokens=settings.llm.max_tokens,
        generation_temperature=settings.llm.generation_temperature,
    )


def get_validation_service(session: AsyncSession) -> ValidationService:
    settings = get_settings()
    llm_provider = _get_llm_provider()
    diagnostic_repo = PgDiagnosticRunRepository(session)

    return ValidationService(
        llm_provider=llm_provider,  # type: ignore[arg-type]
        diagnostic_repo=diagnostic_repo,
        header_validator=HeaderValidator(),
        parameter_validator=ParameterValidator(),
        body_validator=BodyValidator(),
        error_lookup=ErrorStatusLookup(),
        llm_model_id=settings.llm.model_id,
        llm_max_tokens=settings.llm.max_tokens,
        generation_temperature=settings.llm.generation_temperature,
    )


def get_version_diff_service(session: AsyncSession) -> VersionDiffService:
    repo = PgVersionDiffRepository(session)
    return VersionDiffService(repo=repo)
