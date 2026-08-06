"""AI Factory reads: agent registry and XR experience cards."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cached_read
from app.core.errors import NotFoundError
from app.repositories import AiAgentRepository
from app.schemas.agent import AiAgentOut, WorkflowRunOut, WorkflowStageOut, XrExperienceOut
from app.services.base import BaseService
from app.utils.display import AGENT_STATUS_DISPLAY

# Agent collaboration flow (agents.tsx FLOW + STAGE_MSG), replayed client-side
# at one stage per 700 ms.
WORKFLOW_STAGES: tuple[tuple[str, str], ...] = (
    ("Data Agent", "Fetching data"),
    ("Prediction Agent", "Forecasting outcome"),
    ("Causal Agent", "Explaining drivers"),
    ("Simulation Agent", "Testing scenarios"),
    ("Compliance Agent", "Checking rules"),
    ("Human Review", "Awaiting approval"),
    ("Action Agent", "Ready to execute"),
    ("Learning Agent", "Feedback captured"),
)
WORKFLOW_INTERVAL_MS = 700


class AiAgentService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = AiAgentRepository(session)

    async def list_agents(self) -> list[AiAgentOut]:
        return await cached_read("agents:list", self._load_agents)

    async def _load_agents(self) -> list[AiAgentOut]:
        agents = await self._repo.list_all()
        return [self._to_out(agent) for agent in agents]

    async def get_agent(self, agent_id: uuid.UUID) -> AiAgentOut:
        agent = await self._repo.get_by_id(agent_id)
        if agent is None:
            raise NotFoundError(f"Agent '{agent_id}' not found.", code="agent_not_found")
        return self._to_out(agent)

    async def list_xr(self) -> list[XrExperienceOut]:
        return await cached_read("xr:list", self._load_xr)

    async def _load_xr(self) -> list[XrExperienceOut]:
        experiences = await self._repo.list_xr()
        return [
            XrExperienceOut(
                id=exp.code,
                title=exp.title,
                use=exp.use_case,
                feat=exp.feature,
                impact=exp.impact,
            )
            for exp in experiences
        ]

    @staticmethod
    def run_workflow() -> WorkflowRunOut:
        return WorkflowRunOut(
            stages=[WorkflowStageOut(stage=stage, message=message) for stage, message in WORKFLOW_STAGES],
            interval_ms=WORKFLOW_INTERVAL_MS,
        )

    @staticmethod
    def _to_out(agent) -> AiAgentOut:
        return AiAgentOut(
            id=agent.id,
            name=agent.name,
            role=agent.role,
            status=AGENT_STATUS_DISPLAY[agent.status],
            last=agent.last_activity,
            uses=list(agent.use_areas),
        )
