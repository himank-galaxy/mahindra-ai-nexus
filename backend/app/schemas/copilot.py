"""Analytics Copilot chat schemas (mirror the ``CopilotResult`` TS type)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class CopilotChatIn(BaseModel):
    """Chat request body; ``sessionId`` keeps a conversation thread."""

    message: str = Field(min_length=1, max_length=2000)
    session_id: uuid.UUID | None = Field(default=None, alias="sessionId")

    model_config = ConfigDict(populate_by_name=True)


class CopilotChartPoint(BaseModel):
    label: str
    value: int


class CopilotTableOut(BaseModel):
    headers: list[str]
    rows: list[list[str]]


class CopilotResultOut(BaseModel):
    """Full copilot answer; optional chart/table omitted when absent."""

    answer: str
    explanation: str
    sql: str
    python: str
    chart: list[CopilotChartPoint] | None = None
    table: CopilotTableOut | None = None
    action: str
    confidence: int


class ExecutiveSummaryIn(BaseModel):
    use_case: str = Field(min_length=1, max_length=128, alias="useCase")

    model_config = ConfigDict(populate_by_name=True)


class ExecutiveSummaryOut(BaseModel):
    """The 9 fields rendered by ``executive-summary.tsx``."""

    problem: str
    solution: str
    diff: str
    impact: str
    data: str
    scope: str
    timeline: str
    risks: str
    next: str
