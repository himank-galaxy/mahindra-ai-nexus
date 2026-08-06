"""Logistics response schemas (mirrors ROUTES + warehouse signal tiles)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class RouteOut(BaseModel):
    """Freight corridor card; keys mirror the frontend ROUTES shape."""

    id: uuid.UUID
    name: str
    sla_risk: int = Field(alias="slaRisk")
    delay_prob: int = Field(alias="delayProb")
    cost: str
    action: str
    rerouted: bool = False

    model_config = ConfigDict(populate_by_name=True)


class AutoHealOut(BaseModel):
    """Auto-heal result: the updated route plus the executed workflow steps."""

    route: RouteOut
    steps: list[str]

    model_config = ConfigDict(populate_by_name=True)


class SignalOut(BaseModel):
    """Signal tile (warehouse panel)."""

    label: str
    value: str
    tone: str
