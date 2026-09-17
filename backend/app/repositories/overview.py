"""Overview reads: KPIs (with drivers) and recommendations."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Kpi, Recommendation
from app.repositories.base import BaseRepository


class OverviewRepository(BaseRepository[Kpi]):
    model_type = Kpi

    async def list_kpis_with_drivers(self) -> Sequence[Kpi]:
        stmt = select(Kpi).options(selectinload(Kpi.drivers)).order_by(Kpi.sort_order)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_recommendations(self) -> Sequence[Recommendation]:
        stmt = select(Recommendation).where(Recommendation.deleted_at.is_(None)).order_by(Recommendation.sort_order)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_recommendation_by_code(self, code: str) -> Recommendation | None:
        stmt = select(Recommendation).where(Recommendation.code == code, Recommendation.deleted_at.is_(None))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
