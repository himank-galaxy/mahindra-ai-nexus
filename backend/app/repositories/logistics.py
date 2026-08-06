"""Logistics reads: routes and warehouse signal tiles."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from app.models import LogisticsRoute, WarehouseSignal
from app.models.enums import SignalPanel
from app.repositories.base import BaseRepository


class LogisticsRepository(BaseRepository[LogisticsRoute]):
    model_type = LogisticsRoute

    async def list_warehouse_signals(self) -> Sequence[WarehouseSignal]:
        stmt = (
            select(WarehouseSignal)
            .where(WarehouseSignal.panel == SignalPanel.WAREHOUSE)
            .order_by(WarehouseSignal.sort_order)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
