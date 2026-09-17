"""Collections response schemas (mirrors swarm agents, tiles, case rows)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class MetricTileOut(BaseModel):
    """Headline metric tile above the case table."""

    label: str
    value: str
    tone: str = "default"


class CollectionsAgentOut(BaseModel):
    """Member of the collections agent swarm."""

    name: str
    status: str

    model_config = ConfigDict(populate_by_name=True)


class CollectionsCaseOut(BaseModel):
    """Delinquent-account row; keys mirror the frontend COLLECTIONS shape."""

    id: uuid.UUID
    customer: str
    dpd: int
    out: str
    roll: int
    channel: str
    action: str
    prob: int
    flag: str
    status: str

    model_config = ConfigDict(populate_by_name=True)


class ModifyActionIn(BaseModel):
    """Replacement collections action chosen for a case."""

    action: str = Field(min_length=1, max_length=128)
