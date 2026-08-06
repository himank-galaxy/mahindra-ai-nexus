"""Mobility causal twin: graph, business KPIs and Ask Causal Twin Q&A."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.causal.qa import MOBILITY_FALLBACK, match_answer
from app.core.cache import cached_read
from app.models.enums import QaCategory
from app.repositories import MobilityRepository
from app.schemas.mobility import (
    CausalNodeOut,
    MobilityAskIn,
    MobilityAskOut,
    MobilityGraphOut,
    MobilityKpiOut,
)
from app.services.base import BaseService


class MobilityService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = MobilityRepository(session)

    async def get_graph(self) -> MobilityGraphOut:
        return await cached_read("mobility:graph", self._load_graph)

    async def _load_graph(self) -> MobilityGraphOut:
        nodes = await self._repo.list_all()
        edges = await self._repo.list_edges()
        label_by_id = {node.id: node.label for node in nodes}
        return MobilityGraphOut(
            nodes=[
                CausalNodeOut(
                    label=node.label,
                    x=node.x,
                    y=node.y,
                    metric=node.metric,
                    trend=node.trend,
                    drivers=list(node.drivers),
                    action=node.action,
                )
                for node in nodes
            ],
            edges=[(label_by_id[edge.source_node_id], label_by_id[edge.target_node_id]) for edge in edges],
        )

    async def list_kpis(self) -> list[MobilityKpiOut]:
        return await cached_read("mobility:kpis", self._load_kpis)

    async def _load_kpis(self) -> list[MobilityKpiOut]:
        kpis = await self._repo.list_kpis()
        return [MobilityKpiOut(label=kpi.label, value=kpi.value, trend=kpi.trend) for kpi in kpis]

    async def ask(self, payload: MobilityAskIn) -> MobilityAskOut:
        qa = await self._repo.list_qa(category=QaCategory.MOBILITY)
        answer = match_answer(
            payload.question,
            [(item.question, item.answer) for item in qa],
            MOBILITY_FALLBACK,
        )
        return MobilityAskOut(question=payload.question, answer=answer)
