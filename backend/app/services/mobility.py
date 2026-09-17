"""Mobility causal twin: graph, business KPIs and Ask Causal Twin Q&A."""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.causal.qa import MOBILITY_FALLBACK, match_answer
from app.models.enums import QaCategory
from app.repositories import MobilityRepository
from app.schemas.mobility import (
    MobilityAskIn,
    MobilityAskOut,
    MobilityGraphOut,
    MobilityKpiOut,
)
from app.services.base import BaseService
from app.services.merger import merge_causal_nodes, merge_mobility_kpis


class MobilityService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = MobilityRepository(session)

    async def get_graph(self) -> MobilityGraphOut:
        nodes = await self._repo.list_all()
        edges = await self._repo.list_edges()
        label_by_id = {node.id: node.label for node in nodes}

        merged_nodes = merge_causal_nodes(nodes)

        # Build normalized edge pairs
        edge_set: set[tuple[str, str]] = set()
        edge_pairs: list[tuple[str, str]] = []
        for edge in edges:
            src = label_by_id.get(edge.source_node_id, "")
            tgt = label_by_id.get(edge.target_node_id, "")
            if src and tgt:
                clean_src = re.sub(r"\s*\(Synthetic\)", "", src, flags=re.IGNORECASE)
                clean_tgt = re.sub(r"\s*\(Synthetic\)", "", tgt, flags=re.IGNORECASE)
                pair = (clean_src, clean_tgt)
                if pair not in edge_set:
                    edge_set.add(pair)
                    edge_pairs.append(pair)

        return MobilityGraphOut(
            nodes=merged_nodes,
            edges=edge_pairs,
        )

    async def list_kpis(self) -> list[MobilityKpiOut]:
        kpis = await self._repo.list_kpis()
        return merge_mobility_kpis(kpis)


    async def ask(self, payload: MobilityAskIn) -> MobilityAskOut:
        qa = await self._repo.list_qa(category=QaCategory.MOBILITY)
        answer = match_answer(
            payload.question,
            [(item.question, item.answer) for item in qa],
            MOBILITY_FALLBACK,
        )
        return MobilityAskOut(question=payload.question, answer=answer)
