"""Mobility causal twin response schemas (graph, KPIs, node detail)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CausalNodeOut(BaseModel):
    """Node in the causal decision graph (SVG coordinates included).

    `metric_key` is the raw identifier (e.g. "lead_volume") used to fetch
    this node's detail via GET /mobility-twin/nodes/{metric_key} — `metric`
    itself holds the formatted DISPLAY VALUE (e.g. "26.1"), not the key.
    """

    label: str
    x: float
    y: float
    metric_key: str
    metric: str
    trend: str
    drivers: list[str]
    action: str
    trend_pct: float | None = None
    trend_tone: Literal["success", "danger", "default"] = "default"
    unit: str = "number"
    aggregation: str = ""
    connection_count: int = 0
    recent_values: list[float] = Field(default_factory=list)


class MobilityGraphOut(BaseModel):
    """Full graph payload; edges are (source, target) label pairs."""

    nodes: list[CausalNodeOut]
    edges: list[tuple[str, str]]
    edge_details: list[MobilityEdgeOut] = Field(default_factory=list)
    kpis: list[MobilityKpiOut] = Field(default_factory=list)
    metadata: MobilitySnapshotOut | None = None
    width: float = 1200
    height: float = 600
    node_width: float = 240
    node_height: float = 72


class MobilityEdgeOut(BaseModel):
    source: str
    target: str
    score: float
    p_value: float
    q_value: float
    lag_minutes: int


class MobilitySnapshotOut(BaseModel):
    snapshot_id: str
    computed_at: datetime
    data_start: datetime
    data_end: datetime
    source_latest_at: datetime | None
    checked_at: datetime | None
    next_check_at: datetime | None
    observation_count: int
    effective_observation_count: int
    segment_count: int
    sample_stride_hours: int
    refresh_check_minutes: int
    max_lag_hours: int
    significance_threshold: float
    status: Literal["ready", "stale"]
    refreshing: bool
    last_error: str | None
    warnings: list[str]
    excluded_metrics: dict[str, str]
    data_origins: list[str]
    connected_measure_count: int = 0
    hidden_isolated_measure_count: int = 0


class MobilityKpiOut(BaseModel):
    """Business health KPI beside the graph."""

    label: str
    value: str
    trend: str
    metric_key: str = ""
    trend_tone: Literal["success", "danger", "default"] = "default"


class MobilityNodeStatsOut(BaseModel):
    """Real avg/min/max/std over the node's trailing history window —
    measured directly from mobility_timeseries, never hardcoded."""

    mean: float
    min: float
    max: float
    std: float


class MobilityNodeHistoryPointOut(BaseModel):
    """One point on the node's recent-trend sparkline."""

    timestamp: datetime
    value: float


class MobilityNodeRelationshipOut(BaseModel):
    """One causal edge touching the selected node, in either direction."""

    metric: str
    label: str
    direction: Literal["into", "out_of"]
    score: float
    lag_minutes: int
    p_value: float
    q_value: float = 1.0


class MobilityNodeDetailOut(BaseModel):
    """Full detail view for one node, shown when it's clicked in the graph."""

    metric: str
    label: str
    current_value: float
    display_value: str
    trend_pct: float | None
    trend_label: str
    stats: MobilityNodeStatsOut
    history: list[MobilityNodeHistoryPointOut]
    relationships: list[MobilityNodeRelationshipOut]
    top_drivers: list[MobilityNodeRelationshipOut]
    recommended_action: str
    snapshot_id: str = ""
    trend_tone: Literal["success", "danger", "default"] = "default"
    aggregation: str = ""
    unit: str = "number"


class MobilityAskIn(BaseModel):
    """Ask Causal Twin request."""

    question: str = Field(min_length=1, max_length=512)


class MobilityAskOut(BaseModel):
    """Causal answer rendered in the Ask Causal Twin panel."""

    question: str
    answer: str


class MobilityViewContext(BaseModel):
    domain: str = Field(default="All Measures", max_length=64)
    focus: bool = False
    visible_metrics: list[str] = Field(default_factory=list, max_length=500)


class MobilityCopilotAskIn(BaseModel):
    """One conversational turn to the Auto Mobility Causal Twin copilot."""

    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)
    snapshot_id: str | None = None
    view_context: MobilityViewContext | None = None
    selected_metric: str | None = Field(
        default=None,
        description="Selected measure's key, used to ground the copilot in the displayed node's evidence.",
    )


class MobilityCopilotAskOut(BaseModel):
    """The copilot's reply to one turn."""

    reply: str


class MobilityCopilotExplainIn(BaseModel):
    """Request an explanation of the graph subset currently shown in the browser."""

    snapshot_id: str | None = None
    view_context: MobilityViewContext | None = None
    selected_metric: str | None = Field(
        default=None,
        description="Selected visible measure used as the explanation's target metric.",
    )


class MobilityCopilotExplainOut(BaseModel):
    """A structured, business-readable explanation of the current graph view."""

    reply: str


class MobilityCopilotTurnOut(BaseModel):
    """One persisted turn in a copilot conversation."""

    role: str
    content: str
    created_at: datetime


class MobilityCopilotHistoryOut(BaseModel):
    """Full conversation history for one session."""

    session_id: str
    turns: list[MobilityCopilotTurnOut]
