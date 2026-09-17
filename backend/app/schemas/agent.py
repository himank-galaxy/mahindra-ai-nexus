"""AI Factory response schemas (agent registry + XR experience cards)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class AiAgentOut(BaseModel):
    """Registered agent; keys mirror the frontend AGENTS shape."""

    id: uuid.UUID
    name: str
    role: str
    status: str
    last: str
    uses: list[str]

    model_config = ConfigDict(populate_by_name=True)


class XrExperienceOut(BaseModel):
    """AR/VR experience card; keys mirror the frontend CARDS shape."""

    id: str
    title: str
    use: str
    feat: str
    impact: str

    model_config = ConfigDict(populate_by_name=True)


class WorkflowStageOut(BaseModel):
    """One step of the agent collaboration flow."""

    stage: str
    message: str


class WorkflowRunOut(BaseModel):
    """Staged flow messages; the frontend replays them every ``intervalMs``."""

    stages: list[WorkflowStageOut]
    interval_ms: int = Field(alias="intervalMs")

    model_config = ConfigDict(populate_by_name=True)
