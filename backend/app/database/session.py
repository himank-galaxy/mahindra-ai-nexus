"""Async engine, session factory and the FastAPI session dependency.

The engine is created lazily (and cached) so that importing the app does
not require a live database. Services own transaction boundaries: they
call ``commit`` explicitly, while the ``get_db`` dependency guarantees
rollback on error and session closure.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def get_engine() -> AsyncEngine:
    """Return the cached async engine with connection pooling configured."""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the cached session factory bound to the shared engine."""
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a database session per request.

    Rolls back automatically when the endpoint raises; commits are the
    service layer's responsibility so multi-step operations stay atomic.
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def check_database() -> bool:
    """Verify database connectivity with a cheap ``SELECT 1`` probe."""
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 — connectivity probe must never raise
        logger.warning("database_check_failed", error=str(exc))
        return False


async def dispose_engine() -> None:
    """Dispose the pooled connections on application shutdown."""
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        logger.info("database_engine_disposed")
