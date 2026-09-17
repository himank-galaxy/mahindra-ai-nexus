"""Dedicated SQLAlchemy declarative base for derived AI/ML state.

Why this exists
---------------
The Mahindra AI Nexus backend intentionally keeps two persistence domains
separate:

1. ``Base.metadata``
   Legacy/application ORM tables used by the existing application and its
   SQLite test seam.

2. ``AiStateBase.metadata``
   Derived AI/ML persistence stored in PostgreSQL's ``ai_state`` schema.

The separation is deliberate.

AI-state models must not be registered on ``Base.metadata`` because:
- the existing application metadata contract is independently tested,
- the SQLite test seam creates ``Base.metadata`` in-memory,
- PostgreSQL schema-qualified AI state should not leak into that seam,
- the Synthetic Data Factory runtime schema remains independently managed.

AI-state migrations are managed by:

    backend/alembic_ai_state.ini
    backend/alembic_ai_state/

and use:

    ai_state.alembic_version

They are independent from:

    public.alembic_version
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from app.database.base import NAMING_CONVENTION


AI_STATE_SCHEMA = "ai_state"


class AiStateBase(DeclarativeBase):
    """Declarative base for derived AI/ML persistence only."""

    metadata = MetaData(
        naming_convention=NAMING_CONVENTION,
    )
