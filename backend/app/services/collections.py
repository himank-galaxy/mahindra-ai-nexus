"""Collections & Recovery: agents, metric tiles, cases and case actions."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import CollectionsCase
from app.models.enums import CollectionsCaseStatus
from app.repositories import CollectionsRepository
from app.schemas.collections import CollectionsAgentOut, CollectionsCaseOut, MetricTileOut
from app.services.base import BaseService
from app.utils.display import (
    AGENT_STATUS_DISPLAY,
    COLLECTIONS_CASE_STATUS_DISPLAY,
    COLLECTIONS_FLAG_DISPLAY,
)

# Static trust-trail steps shown by the per-case ledger modal (collections.tsx).
CASE_LEDGER_STEPS = [
    "Data sources: DPD, income stability, past behavior",
    "Model output: restructuring recommended",
    "Key drivers: 3-month income variability + prior 30-DPD",
    "Compliance check: passed",
    "Human decision: approved",
    "Feedback: awaiting outcome",
]


class CollectionsService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = CollectionsRepository(session)

    async def list_metrics(self) -> list[MetricTileOut]:
        tiles = await self._repo.list_metric_tiles()
        return [MetricTileOut(label=tile.label, value=tile.value, tone=tile.tone) for tile in tiles]

    async def list_agents(self) -> list[CollectionsAgentOut]:
        agents = await self._repo.list_agents()
        return [CollectionsAgentOut(name=agent.name, status=AGENT_STATUS_DISPLAY[agent.status]) for agent in agents]

    async def list_cases(self) -> list[CollectionsCaseOut]:
        cases = await self._repo.list_all()
        return [self._to_out(case) for case in cases]

    async def approve_case(self, case_id: uuid.UUID) -> CollectionsCaseOut:
        """Approve the swarm's recommended action for a case."""
        case = await self._get_case(case_id)
        case.status = CollectionsCaseStatus.APPROVED
        await self._session.commit()
        return self._to_out(case)

    async def modify_case(self, case_id: uuid.UUID, action: str) -> CollectionsCaseOut:
        """Replace the recommended action with a hand-picked one."""
        case = await self._get_case(case_id)
        case.status = CollectionsCaseStatus.MODIFIED
        case.modified_action = action
        await self._session.commit()
        return self._to_out(case)

    async def review_case(self, case_id: uuid.UUID) -> CollectionsCaseOut:
        """Route the case to human review."""
        case = await self._get_case(case_id)
        case.status = CollectionsCaseStatus.HUMAN_REVIEW
        await self._session.commit()
        return self._to_out(case)

    async def get_case_ledger(self, case_id: uuid.UUID) -> list[str]:
        """Trust-trail steps for one case (identical trail per the prototype)."""
        await self._get_case(case_id)
        return list(CASE_LEDGER_STEPS)

    async def _get_case(self, case_id: uuid.UUID) -> CollectionsCase:
        case = await self._repo.get_by_id(case_id)
        if case is None:
            raise NotFoundError(f"Collections case '{case_id}' not found.", code="case_not_found")
        return case

    @staticmethod
    def _to_out(case: CollectionsCase) -> CollectionsCaseOut:
        return CollectionsCaseOut(
            id=case.id,
            customer=case.customer,
            dpd=case.dpd,
            out=case.outstanding,
            roll=case.roll_forward_risk,
            channel=case.channel,
            action=case.action,
            prob=case.prob,
            flag=COLLECTIONS_FLAG_DISPLAY[case.compliance_flag],
            status=COLLECTIONS_CASE_STATUS_DISPLAY[case.status],
        )
