"""PoC roadmap schemas (server-side replacement for localStorage)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class PocItemIn(BaseModel):
    """Payload for shortlisting a catalogue solution to the PoC roadmap."""

    name: str = Field(min_length=1, max_length=128)
    bucket: str = Field(min_length=1, max_length=128)


class PocItemOut(BaseModel):
    """PoC roadmap row; ``addedAt`` mirrors the client's ``Date.now()`` epoch-ms."""

    id: uuid.UUID
    name: str
    bucket: str
    added_at: int = Field(alias="addedAt")

    model_config = ConfigDict(populate_by_name=True)


class RoadmapPhaseOut(BaseModel):
    """One rollout phase; aliases mirror the keys rendered by poc-roadmap.tsx."""

    phase: str = Field(alias="p")
    title: str = Field(alias="t")
    weeks: str = Field(alias="w")
    description: str = Field(alias="d")

    model_config = ConfigDict(populate_by_name=True)


class RoadmapPlanOut(BaseModel):
    """Phased rollout plan plus the top-3 recommended PoCs."""

    phases: list[RoadmapPhaseOut]
    top_pocs: list[str] = Field(alias="topPocs")
    optional: str

    model_config = ConfigDict(populate_by_name=True)
