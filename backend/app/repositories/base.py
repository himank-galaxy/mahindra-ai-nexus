"""Base repository with shared async query helpers.

Repositories are the only layer allowed to touch SQLAlchemy. They never
commit (services own transactions) and never apply business rules.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import ClassVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base


class BaseRepository[ModelT: Base]:
    """Common read helpers; subclasses set ``model_type``."""

    model_type: ClassVar[type[Base]]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _base_query(self):
        """SELECT with soft-delete filter and sort ordering when present."""
        stmt = select(self.model_type)
        if hasattr(self.model_type, "deleted_at"):
            stmt = stmt.where(self.model_type.deleted_at.is_(None))
        if hasattr(self.model_type, "sort_order"):
            stmt = stmt.order_by(self.model_type.sort_order)
        return stmt

    async def list_all(self) -> Sequence[ModelT]:
        result = await self._session.execute(self._base_query())
        return result.scalars().all()

    async def get_by_id(self, entity_id: uuid.UUID) -> ModelT | None:
        stmt = self._base_query().where(self.model_type.id == entity_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
