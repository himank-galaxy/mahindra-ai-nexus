"""Alembic environment for derived Mahindra AI/ML state.

This environment is deliberately independent from the Synthetic Data Factory
runtime migration lineage.

Runtime business schema
-----------------------
Configuration:
    backend/alembic.ini

Version table:
    public.alembic_version

Current baseline:
    runtime_0001

Ownership:
    Exactly 50 validated runtime/business tables in ``public``.


Derived AI state
----------------
Configuration:
    backend/alembic_ai_state.ini

Version table:
    ai_state.alembic_version

Ownership:
    Persisted outputs produced by AI/ML processing such as causal-discovery
    runs and statistically discovered manufacturing causal relationships.

Architectural rules
-------------------
- Never import evaluator ground truth.
- Never modify the validated 50-table runtime contract.
- Never use ``Base.metadata`` from legacy application ORM models here.
- AI-state migrations use their own independent revision history.
- Runtime migrations must not depend on AI-state revisions.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings


AI_STATE_SCHEMA = "ai_state"

VERSION_TABLE = "alembic_version"


# ---------------------------------------------------------------------------
# Alembic configuration
# ---------------------------------------------------------------------------

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------

settings = get_settings()

config.set_main_option(
    "sqlalchemy.url",
    settings.database_url,
)


# ---------------------------------------------------------------------------
# Metadata
#
# AI-state migrations are currently explicit/manual migrations.
#
# Do NOT substitute app.models.Base.metadata here. That metadata contains
# legacy/application tables and is intentionally outside this migration
# environment.
# ---------------------------------------------------------------------------

target_metadata = None


# ---------------------------------------------------------------------------
# Shared Alembic configuration
# ---------------------------------------------------------------------------


def configure_context(
    *,
    connection: Connection | None = None,
    url: str | None = None,
) -> None:
    """Configure the isolated AI-state migration context."""

    kwargs = {
        "target_metadata": target_metadata,
        "compare_type": True,
        "compare_server_default": True,
        "include_schemas": True,
        "render_as_batch": False,
        "version_table": VERSION_TABLE,
        "version_table_schema": AI_STATE_SCHEMA,
    }

    if connection is not None:
        context.configure(
            connection=connection,
            **kwargs,
        )
        return

    if url is None:
        raise RuntimeError(
            "Offline AI-state Alembic configuration "
            "requires a database URL."
        )

    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named",
        },
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Offline migrations
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Generate SQL without connecting to PostgreSQL."""

    url = config.get_main_option(
        "sqlalchemy.url"
    )

    configure_context(
        url=url,
    )

    with context.begin_transaction():

        # The version table itself lives inside ai_state, so the schema must
        # exist before Alembic attempts to create ai_state.alembic_version.
        context.execute(
            f"CREATE SCHEMA IF NOT EXISTS {AI_STATE_SCHEMA}"
        )

        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migrations
# ---------------------------------------------------------------------------


def do_run_migrations(
    connection: Connection,
) -> None:
    """Run AI-state migrations on an established sync connection."""

    configure_context(
        connection=connection,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create the async engine and execute AI-state migrations."""

    connectable = async_engine_from_config(
        config.get_section(
            config.config_ini_section,
        ),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        async with connectable.connect() as connection:

            # Alembic needs the schema before it can create/use the dedicated
            # ai_state.alembic_version table.
            await connection.execute(
                sa.text(
                    f"CREATE SCHEMA IF NOT EXISTS {AI_STATE_SCHEMA}"
                )
            )

            await connection.commit()

            await connection.run_sync(
                do_run_migrations
            )

    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against configured PostgreSQL."""

    asyncio.run(
        run_async_migrations()
    )


# ---------------------------------------------------------------------------
# Alembic entry point
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
