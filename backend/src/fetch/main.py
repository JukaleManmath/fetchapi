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
from fetch.api.v1.sources import router as sources_router
from fetch.infrastructure.db.session import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield
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


@app.get("/health/live", tags=["health"], include_in_schema=False)
async def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"], include_in_schema=False)
async def health_ready() -> dict[str, str]:
    return {"status": "ok"}
