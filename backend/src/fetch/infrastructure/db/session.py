"""Async SQLAlchemy engine and session factory.

Call init_db() once during app startup (lifespan).
Use get_session() as an async context manager everywhere else.
Call close_db() during app shutdown.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fetch.config import get_settings

# Module-level singletons — set by init_db(), cleared by close_db()
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(url: str | None = None) -> None:
    """Create the async engine and session factory.

    Must be called before any database access. Calling twice is safe —
    the second call is a no-op if already initialized.
    """
    global _engine, _session_factory
    if _engine is not None:
        return
    settings = get_settings()
    db_url = url or settings.postgres.url
    _engine = create_async_engine(
        db_url,
        pool_size=settings.postgres.pool_size,
        max_overflow=10,
        echo=settings.app.debug,
        pool_pre_ping=True,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() in app lifespan.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() in app lifespan.")
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a database session, committing on clean exit or rolling back on error."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    """Dispose the engine connection pool. Call during app shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
