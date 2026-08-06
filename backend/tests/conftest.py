"""Shared pytest fixtures.

``client`` boots the real FastAPI app in-process via ASGI transport, so
API tests exercise middleware, exception handlers and routing exactly as
in production. The ``get_db`` dependency is overridden with a seeded
SQLite (aiosqlite) engine — the portable column variants in
``app.database.base`` make every table creatable without PostgreSQL.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

# Tests fire hundreds of requests in seconds; disable the limiter so suites
# never hit 429. Must be set before ``app.main`` builds the app.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

import app.models  # noqa: F401,E402 — register every model on Base.metadata
import pytest_asyncio  # noqa: E402
from app.core.cache import clear_read_cache  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.seed import seed_database  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402


@pytest_asyncio.fixture
async def test_engine() -> AsyncIterator[AsyncEngine]:
    """In-memory SQLite engine shared across all connections via StaticPool."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Session over a freshly seeded test database."""
    clear_read_cache()  # never serve a previous test's cached reads
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await seed_database(session)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Async HTTP client wired to the app with the test session injected."""

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)
