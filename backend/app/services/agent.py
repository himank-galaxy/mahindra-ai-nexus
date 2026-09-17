"""AI Factory views over canonical agent and XR runtime events."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select

from app.core.errors import NotFoundError
from app.database.runtime_schema import runtime_tables
from app.schemas.agent import (
    AiAgentOut,
    WorkflowRunOut,
    WorkflowStageOut,
    XrExperienceOut,
)
from app.services.base import BaseService

AGENT_EVENTS = runtime_tables["agent_events"]
XR_EXPERIENCES = runtime_tables["xr_experiences"]
AGENT_NAMESPACE = uuid.UUID("fd15c1cf-7a55-47de-828a-0c195867f46b")
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


def _agent_uuid(agent_id: str) -> uuid.UUID:
    return uuid.uuid5(AGENT_NAMESPACE, agent_id)


class AiAgentService(BaseService):
    async def list_agents(self) -> list[AiAgentOut]:
        rows = (
            (await self._session.execute(select(AGENT_EVENTS).order_by(AGENT_EVENTS.c.completed_at))).mappings().all()
        )
        grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in rows:
            grouped[str(row["agent_id"])].append(dict(row))

        result: list[AiAgentOut] = []
        for agent_id, events in grouped.items():
            latest = events[-1]
            domains = sorted({str(event["domain"]) for event in events})
            role = agent_id.removeprefix("AGENT_").replace("_", " ").title()
            result.append(
                AiAgentOut(
                    id=_agent_uuid(agent_id),
                    name=str(latest["agent_name"]),
                    role=role,
                    status=str(latest["status"]).replace("_", " ").title(),
                    last=latest["completed_at"].isoformat(),
                    uses=domains,
                )
            )
        return sorted(result, key=lambda agent: agent.name)

    async def get_agent(self, agent_id: uuid.UUID) -> AiAgentOut:
        for agent in await self.list_agents():
            if agent.id == agent_id:
                return agent
        raise NotFoundError(
            f"Agent '{agent_id}' not found.",
            code="agent_not_found",
        )

    async def list_xr(self) -> list[XrExperienceOut]:
        rows = (
            (
                await self._session.execute(
                    select(XR_EXPERIENCES)
                    .where(XR_EXPERIENCES.c.active.is_(True))
                    .order_by(XR_EXPERIENCES.c.experience_id)
                )
            )
            .mappings()
            .all()
        )
        output: list[XrExperienceOut] = []
        for row in rows:
            features = [
                label
                for field, label in (
                    ("supports_ai_assistant", "AI assistant"),
                    ("supports_configuration", "Configuration"),
                    ("supports_training_score", "Training score"),
                    ("supports_repair_steps", "Repair steps"),
                )
                if row[field]
            ]
            output.append(
                XrExperienceOut(
                    id=str(row["experience_id"]),
                    title=str(row["experience_type"]),
                    use=str(row["experience_category"]).replace("_", " ").title(),
                    feat=", ".join(features) if features else "No optional features",
                    impact="No measured impact is available in runtime_0001",
                )
            )
        return output

    @staticmethod
    def run_workflow() -> WorkflowRunOut:
        return WorkflowRunOut(
            stages=[WorkflowStageOut(stage=stage, message=message) for stage, message in WORKFLOW_STAGES],
            interval_ms=WORKFLOW_INTERVAL_MS,
        )
