"""Catalogue reads: buckets with nested solutions."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import SolutionBucket
from app.repositories.base import BaseRepository


class CatalogueRepository(BaseRepository[SolutionBucket]):
    model_type = SolutionBucket

    async def list_buckets(self, tag: str | None = None) -> Sequence[SolutionBucket]:
        stmt = (
            select(SolutionBucket).options(selectinload(SolutionBucket.solutions)).order_by(SolutionBucket.sort_order)
        )
        if tag:
            stmt = stmt.where(SolutionBucket.tag == tag)
        result = await self._session.execute(stmt)
        return result.scalars().all()
