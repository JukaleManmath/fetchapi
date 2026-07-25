"""FastAPI application entry point.

Lifespan:
- Initializes the async database engine (init_db)
- Shuts down the engine pool cleanly (close_db)

All routes are mounted under /v1 except health endpoints.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fetch.api.errors import register_error_handlers
from fetch.api.v1.operations import router as operations_router
from fetch.api.v1.queries import router as queries_router
from fetch.api.v1.sources import router as sources_router
from fetch.config import get_settings
from fetch.infrastructure.db.session import close_db, init_db
from fetch.infrastructure.llm.nvidia_nim import NvidiaNimProvider
from fetch.infrastructure.qdrant.repository import QdrantRepository


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    settings = get_settings()
    qdrant = QdrantRepository()
    await qdrant.ensure_collection(dense_dimension=settings.embeddings.dimension)
    llm_provider = NvidiaNimProvider(
        api_key=settings.llm.api_key.get_secret_value(),
        base_url=settings.llm.base_url,
        timeout_seconds=settings.llm.timeout_seconds,
    )
    app.state.llm_provider = llm_provider
    yield
    if hasattr(app.state, "llm_provider"):
        await app.state.llm_provider.aclose()
    await close_db()


app = FastAPI(
    title="FetchAPI",
    description=(
        "Self-hosted MCP server that turns OpenAPI specs into structured, "
        "citation-backed API knowledge for your AI coding assistant."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

register_error_handlers(app)

app.include_router(sources_router)
app.include_router(operations_router)
app.include_router(queries_router)


@app.get("/health/live", tags=["health"], include_in_schema=False)
async def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"], include_in_schema=False)
async def health_ready() -> dict[str, str]:
    return {"status": "ok"}
