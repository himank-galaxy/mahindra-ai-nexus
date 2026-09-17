"""Alembic migration environment for the Mahindra AI Nexus runtime schema.

Alembic is intentionally isolated from the legacy application ORM models.

Migration metadata source:
    app.database.runtime_schema.runtime_metadata

Architectural rules:
- Alembic manages only the validated Synthetic Data Factory runtime schema.
- Exactly 50 runtime business tables are represented in target metadata.
- Evaluator ground-truth datasets are never part of runtime PostgreSQL.
- Legacy ``app.models`` metadata is not imported here.
- Generated CSV files and ``dataset_manifest.json`` are not required by
  migrations.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.database.runtime_schema import (
    runtime_metadata,
    validate_runtime_metadata,
)


# ---------------------------------------------------------------------
# Alembic configuration
# ---------------------------------------------------------------------

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ---------------------------------------------------------------------
# Validate the static runtime contract before Alembic does anything.
# ---------------------------------------------------------------------

validate_runtime_metadata()


# ---------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------

settings = get_settings()

config.set_main_option(
    "sqlalchemy.url",
    settings.database_url,
)


# ---------------------------------------------------------------------
# Alembic target metadata
#
# IMPORTANT:
# Do not replace this with Base.metadata and do not import app.models.
# ---------------------------------------------------------------------

target_metadata = runtime_metadata


# ---------------------------------------------------------------------
# Shared Alembic configuration
# ---------------------------------------------------------------------

def configure_context(
    *,
    connection: Connection | None = None,
    url: str | None = None,
) -> None:
    """Configure Alembic consistently for online/offline migrations."""

    kwargs = {
        "target_metadata": target_metadata,
        "compare_type": True,
        "compare_server_default": True,
        "include_schemas": False,
        "render_as_batch": False,
    }

    if connection is not None:
        context.configure(
            connection=connection,
            **kwargs,
        )
        return

    if url is None:
        raise RuntimeError(
            "Offline Alembic configuration requires a database URL."
        )

    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named",
        },
        **kwargs,
    )


# ---------------------------------------------------------------------
# Offline migrations
# ---------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations without establishing a database connection."""

    url = config.get_main_option(
        "sqlalchemy.url"
    )

    configure_context(
        url=url,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------
# Online migrations
# ---------------------------------------------------------------------

def do_run_migrations(
    connection: Connection,
) -> None:
    """Run Alembic migrations using an established sync connection."""

    configure_context(
        connection=connection,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create the async engine and execute Alembic migrations."""

    connectable = async_engine_from_config(
        config.get_section(
            config.config_ini_section,
        ),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(
                do_run_migrations
            )
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against the configured PostgreSQL database."""

    asyncio.run(
        run_async_migrations()
    )


# ---------------------------------------------------------------------
# Alembic entry point
# ---------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
