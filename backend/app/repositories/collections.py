"""Collections reads: swarm agents, metric tiles and prioritized cases."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from app.models import CollectionsAgent, CollectionsCase, WarehouseSignal
from app.models.enums import SignalPanel
from app.repositories.base import BaseRepository


class CollectionsRepository(BaseRepository[CollectionsCase]):
    model_type = CollectionsCase

    async def list_agents(self) -> Sequence[CollectionsAgent]:
        stmt = select(CollectionsAgent).order_by(CollectionsAgent.sort_order)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_metric_tiles(self) -> Sequence[WarehouseSignal]:
        stmt = (
            select(WarehouseSignal)
            .where(WarehouseSignal.panel == SignalPanel.COLLECTIONS_METRICS)
            .order_by(WarehouseSignal.sort_order)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
