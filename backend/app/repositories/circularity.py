"""Circularity reads: credit marketplace and RVSF tiles."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from app.models import CarbonCredit, WarehouseSignal
from app.models.enums import SignalPanel
from app.repositories.base import BaseRepository


class CircularityRepository(BaseRepository[CarbonCredit]):
    model_type = CarbonCredit

    async def get_by_code(self, code: str) -> CarbonCredit | None:
        stmt = select(CarbonCredit).where(CarbonCredit.code == code, CarbonCredit.deleted_at.is_(None))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_rvsf_metrics(self) -> Sequence[WarehouseSignal]:
        stmt = (
            select(WarehouseSignal)
            .where(WarehouseSignal.panel == SignalPanel.RVSF)
            .order_by(WarehouseSignal.sort_order)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
