"""Declarative base and shared ORM mixins.

Conventions enforced for every table:
- UUID v4 primary keys (``UUIDPrimaryKeyMixin``)
- Audit timestamps populated by the database (``TimestampMixin``)
- Soft deletes via ``deleted_at`` where required (``SoftDeleteMixin``)
- Deterministic constraint naming for clean Alembic diffs
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

# Portable column types: JSONB/ARRAY in production (PostgreSQL), plain JSON in
# the SQLite test seam. Production DDL is unaffected — migrations hardcode the
# Postgres types — this only lets the API test-suite run without Docker.
JSONType = JSON().with_variant(JSONB(astext_type=None), "postgresql")


def string_array() -> JSON:
    """TEXT[] column on PostgreSQL, JSON list on SQLite (tests only)."""
    return ARRAY(String(32)).with_variant(JSON(), "sqlite")  # type: ignore[return-value]


def uuid_pk():
    """UUID column type: native on PostgreSQL, generic ``Uuid`` on SQLite (tests)."""
    from sqlalchemy import Uuid

    return PG_UUID(as_uuid=True).with_variant(Uuid(), "sqlite")


# Explicit naming convention keeps Alembic migration names stable and readable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """Adds a UUID v4 primary key column named ``id``."""

    id: Mapped[uuid.UUID] = mapped_column(
        uuid_pk(),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Adds server-side ``created_at`` / ``updated_at`` audit columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Adds a ``deleted_at`` tombstone column; rows are never physically removed."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    @property
    def is_deleted(self) -> bool:
        """Whether this row has been soft-deleted."""
        return self.deleted_at is not None
