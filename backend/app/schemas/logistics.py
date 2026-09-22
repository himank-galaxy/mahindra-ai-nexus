"""Logistics response schemas (mirrors ROUTES + warehouse signal tiles)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.trust import ComplianceCheckOut, ExplanationDriverOut, OutcomeOut

# Backend-derived, explainable route priority (see
# app/services/logistics_priority.py) — never randomly assigned.
PRIORITY_VALUES = Literal["Critical", "High", "Medium", "Low"]

# Real recorded action the optimizer chose between — matches the exact
# real categories used by Logistics Delay Simulation, never invented.
ACTION_VALUES = Literal["MAINTAIN", "REROUTE"]


class RouteOut(BaseModel):
    """Freight corridor card; keys mirror the frontend ROUTES shape."""

    id: uuid.UUID
    route_id: str
    name: str
    sla_risk: int = Field(alias="slaRisk")
    delay_prob: int = Field(alias="delayProb")
    cost: str
    action: str
    rerouted: bool = False
    active_shipments: int
    at_risk_shipments: int
    status: str
    priority: PRIORITY_VALUES
    priority_reason: str
    scored_at: datetime
    model_version: str

    model_config = ConfigDict(populate_by_name=True)


class AutoHealOut(BaseModel):
    """Auto-heal result: the updated route plus the executed workflow steps."""

    route: RouteOut
    steps: list[str]
    approved_shipments: int
    already_decided_shipments: int

    model_config = ConfigDict(populate_by_name=True)


class SignalOut(BaseModel):
    """Signal tile (warehouse panel)."""

    label: str
    value: str
    tone: str
    threshold: str
    affected_routes: list[str] = Field(default_factory=list)


class ShipmentOut(BaseModel):
    """One real shipment on a route — the drill-down beneath a route card."""

    shipment_id: str
    status: str
    priority: str
    dispatch_time: datetime
    expected_arrival: datetime
    actual_arrival: datetime | None
    sla_deadline: datetime
    delay_minutes: float
    sla_breach: bool
    vehicle_id: str
    current_warehouse: str | None
    delay_probability: int
    breach_probability: int
    recommended_action: str
    recommended_route_label: str | None
    governance_track: Literal["canonical", "live"]
    decision_status: str
    decision_code: str | None


class ModifyShipmentActionIn(BaseModel):
    """Human override of the optimizer's recommended action for a
    shipment — a real recorded route, never a free-text destination. The
    original AI recommendation is preserved separately; this never
    replaces it."""

    action: ACTION_VALUES
    route_id: str | None = Field(default=None, description="Required when action='REROUTE'.")
    reason: str = Field(default="", max_length=512)


class ShipmentTrustLedgerOut(BaseModel):
    """Real governance state for one shipment — reuses the exact Trust
    Ledger compliance/outcome shapes."""

    track: Literal["canonical", "live", "none"]
    decision_code: str | None
    approval: str
    audit_status: str
    compliance: list[ComplianceCheckOut]
    priority: PRIORITY_VALUES
    priority_reason: str
    scored_at: datetime
    model_version: str
    recommended_action: str | None = None
    recommended_route_id: str | None = None
    modified_action: str | None = None
    modified_route_id: str | None = None
    modification_reason: str | None = None
    outcome: OutcomeOut


class SlaReportOut(BaseModel):
    """Real per-route SLA report — every figure aggregated from real
    shipments, never a placeholder shape."""

    route_id: str
    route_name: str
    active_shipments: int
    on_time_shipments: int
    at_risk_shipments: int
    expected_breaches: float
    average_delay_minutes: float
    cost_exposure_inr: float
    recommended_action: str
    drivers: list[ExplanationDriverOut]
