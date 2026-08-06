"""Mobility causal twin reads: graph nodes/edges, KPIs and Q&A."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from app.models import CausalEdge, CausalNode, CausalQa, MobilityKpi
from app.models.enums import QaCategory
from app.repositories.base import BaseRepository


class MobilityRepository(BaseRepository[CausalNode]):
    model_type = CausalNode

    async def list_edges(self) -> Sequence[CausalEdge]:
        stmt = select(CausalEdge).order_by(CausalEdge.sort_order)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_node_labels(self) -> dict:
        """Map node UUID -> label for resolving edge endpoints."""
        stmt = select(CausalNode.id, CausalNode.label)
        result = await self._session.execute(stmt)
        return dict(result.all())

    async def list_kpis(self) -> Sequence[MobilityKpi]:
        stmt = select(MobilityKpi).order_by(MobilityKpi.sort_order)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_qa(self, category: QaCategory | None = None) -> Sequence[CausalQa]:
        stmt = select(CausalQa).order_by(CausalQa.sort_order)
        if category is not None:
            stmt = stmt.where(CausalQa.category == category)
        result = await self._session.execute(stmt)
        return result.scalars().all()
