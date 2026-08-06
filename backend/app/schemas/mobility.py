"""Mobility causal twin response schemas (graph, KPIs)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CausalNodeOut(BaseModel):
    """Node in the causal decision graph (SVG coordinates included)."""

    label: str
    x: float
    y: float
    metric: str
    trend: str
    drivers: list[str]
    action: str


class MobilityGraphOut(BaseModel):
    """Full graph payload; edges are (source, target) label pairs."""

    nodes: list[CausalNodeOut]
    edges: list[tuple[str, str]]


class MobilityKpiOut(BaseModel):
    """Business health KPI beside the graph."""

    label: str
    value: str
    trend: str


class MobilityAskIn(BaseModel):
    """Ask Causal Twin request."""

    question: str = Field(min_length=1, max_length=512)


class MobilityAskOut(BaseModel):
    """Causal answer rendered in the Ask Causal Twin panel."""

    question: str
    answer: str
