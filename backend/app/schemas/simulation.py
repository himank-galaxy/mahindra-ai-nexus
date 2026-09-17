"""Simulation Center schemas: option metadata plus engine inputs/outputs.

Output field names mirror exactly what ``simulation.tsx`` computes so the
frontend can swap its inline formulas for these API calls untouched.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RouteOption(BaseModel):
    """A real active route — ``id`` is the wire value, ``label`` a
    human-readable "Origin → Destination" string built from real city
    names (see app/repositories/logistics_delay_simulation.py)."""

    id: str
    label: str


class SimulationMetaOut(BaseModel):
    """Reference options feeding the simulator selects."""

    regions: list[str]
    models: list[str]
    routes: list[RouteOption] = []


# ---------------------------------------------------------------------------
# Common run envelope — every ``*/run`` response and the generic run-detail
# fetch share these fields. See docs/simulation_centre_implementation.md §8.
# ---------------------------------------------------------------------------


class SimulationRunEnvelope(BaseModel):
    """Fields every persisted simulation run carries, regardless of domain."""

    run_id: UUID
    status: str
    confidence: int
    confidence_band: str
    confidence_basis: Literal["trained_model", "calibrated_heuristic"]


class SimulationRunDetailOut(SimulationRunEnvelope):
    """Generic ``GET /{run_id}`` response — domain-typed output stays a dict."""

    domain: str
    scenario_name: str
    inputs: dict[str, Any]
    baseline_reference: dict[str, Any] | None
    outputs: dict[str, Any]
    driver_json: dict[str, Any] | None
    recommendation_json: dict[str, Any] | None
    model_name: str
    model_version: str
    created_at: datetime


class SimulationDecisionIn(BaseModel):
    """Body for both ``/approve`` and ``/reject`` — the route implies the decision."""

    reason: str | None = Field(default=None, max_length=512)


class SimulationApprovalOut(BaseModel):
    run_id: UUID
    status: str
    decision: str
    decided_at: datetime
    actor: str


# ---------------------------------------------------------------------------
# Auto Sales Simulation
# ---------------------------------------------------------------------------


class AutoSalesSimIn(BaseModel):
    """Inputs mirroring the AutoSales sliders/selects and their defaults."""

    region: str = Field(default="West", max_length=64)
    model: str = Field(default="XUV700", max_length=64)
    discount: float = Field(default=3, ge=0, le=10)
    bonus: float = Field(default=25000, ge=0, le=75000)
    campaign: float = Field(default=1.5, ge=0, le=5)
    intensity: Literal["Low", "Medium", "High"] = "Medium"


class AutoSalesSimOut(BaseModel):
    run_id: UUID
    status: str
    confidence_band: str
    confidence_basis: Literal["trained_model", "calibrated_heuristic"]
    uplift: int
    margin: int
    cancel: int
    rev: int
    conf: int
    recommended_action: str = Field(alias="recommendedAction")

    model_config = ConfigDict(populate_by_name=True)


# ---------------------------------------------------------------------------
# Dealer Allocation Simulation
# ---------------------------------------------------------------------------


class DealerAllocationSimIn(BaseModel):
    units: int = Field(default=120, ge=20, le=400)
    demand: int = Field(default=70, ge=20, le=100)
    capacity: int = Field(default=80, ge=30, le=100)
    wait: int = Field(default=14, ge=5, le=45)


class DealerAllocationSimOut(BaseModel):
    run_id: UUID
    status: str
    confidence_band: str
    confidence_basis: Literal["trained_model", "calibrated_heuristic"]
    delay: int
    rev: int
    csat: int
    suggested_split: str = Field(alias="suggestedSplit")
    conf: int
    recommended_action: str = Field(alias="recommendedAction")

    model_config = ConfigDict(populate_by_name=True)


# ---------------------------------------------------------------------------
# Finance Collections Simulation
# ---------------------------------------------------------------------------


class CollectionsSimIn(BaseModel):
    risk: Literal["Low", "Medium", "High"] = "Medium"
    # Real recorded channel/offer categories (see
    # app/repositories/collections_simulation.py) — no UI-to-real
    # translation needed, so every choice trains on genuine historical
    # outcomes (unlike the retired "Digital" grouping and "Waiver" option,
    # which had no real precedent and required a calibrated-heuristic
    # special case).
    channel: Literal["SMS", "WHATSAPP", "EMAIL", "CALL", "FIELD_VISIT"] = "WHATSAPP"
    offer: Literal["NONE", "PAYMENT_REMINDER", "PARTIAL_PAYMENT_PLAN", "REPAYMENT_PLAN_DISCUSSION"] = (
        "REPAYMENT_PLAN_DISCUSSION"
    )
    field: int = Field(default=40, ge=0, le=100)


class CollectionsSimOut(BaseModel):
    run_id: UUID
    status: str
    confidence_band: str
    confidence_basis: Literal["trained_model", "calibrated_heuristic"]
    prob: int
    cost: int
    friction: int
    net: int
    conf: int
    recommended_action: str = Field(alias="recommendedAction")

    model_config = ConfigDict(populate_by_name=True)


# ---------------------------------------------------------------------------
# Logistics Delay Simulation
# ---------------------------------------------------------------------------


class LogisticsDelaySimIn(BaseModel):
    # Real recorded route id (see app/repositories/logistics_delay_simulation.py
    # — GET /simulations/meta lists every active route as {id, label}) — no
    # UI-to-real translation, unlike the retired free-text city-pair strings
    # that didn't exist in the schema.
    route: str = Field(default="ROUTE_SYN_001", max_length=64)
    warehouse: int = Field(default=60, ge=0, le=100)
    vehicle: int = Field(default=70, ge=20, le=100)
    weather: int = Field(default=20, ge=0, le=100)
    # Real recorded priority categories on `shipments.priority` — replaces
    # the retired invented "Low/Medium/High" SLA-priority scale.
    sla: Literal["LOW", "NORMAL", "HIGH", "CRITICAL"] = "HIGH"


class LogisticsDelaySimOut(BaseModel):
    run_id: UUID
    status: str
    confidence_band: str
    confidence_basis: Literal["trained_model", "calibrated_heuristic"]
    delay: int
    breach: int
    reroute: str
    cost: int
    conf: int
    recommended_action: str = Field(alias="recommendedAction")

    model_config = ConfigDict(populate_by_name=True)


# ---------------------------------------------------------------------------
# Circularity Credit Pricing Simulation
# ---------------------------------------------------------------------------


class CreditPricingSimIn(BaseModel):
    # Real recorded categories on `credit_listings.credit_type` (see
    # app/repositories/credit_pricing_simulation.py) — no UI-to-real
    # translation, unlike the retired invented "Carbon/EPR/SDG/CD" scale.
    credit_type: Literal["MIXED_CIRCULARITY", "RECYCLING_AVOIDANCE", "REUSE_AVOIDANCE"] = Field(
        default="REUSE_AVOIDANCE", alias="type"
    )
    supply: int = Field(default=50, ge=10, le=100)
    demand: int = Field(default=60, ge=10, le=100)
    trace: int = Field(default=70, ge=10, le=100)
    verif: int = Field(default=65, ge=10, le=100)

    model_config = ConfigDict(populate_by_name=True)


class CreditPricingSimOut(BaseModel):
    run_id: UUID
    status: str
    confidence_band: str
    confidence_basis: Literal["trained_model", "calibrated_heuristic"]
    price_band_low: int = Field(alias="priceBandLow")
    price_band_high: int = Field(alias="priceBandHigh")
    closure: int
    match: int
    compliance_risk: str = Field(alias="complianceRisk")
    conf: int
    recommended_action: str = Field(alias="recommendedAction")

    model_config = ConfigDict(populate_by_name=True)


# ---------------------------------------------------------------------------
# Causal drivers (Explain Drivers modal)
# ---------------------------------------------------------------------------


class CausalDriversOut(BaseModel):
    domain: str
    drivers: list[str]


# ---------------------------------------------------------------------------
# Real per-run Explain Drivers (Phase 2) — predictive contribution and
# causal evidence are kept as separate, clearly labelled lists so the UI
# never captions one as the other. See
# docs/simulation_centre_implementation.md §4.1/§11.
# ---------------------------------------------------------------------------


class SimulationDriverItem(BaseModel):
    name: str
    direction: Literal["positive", "negative"]
    contribution: float
    source: Literal["trained_model", "calibrated_heuristic"]
    detail: str


class SimulationCausalEdgeItem(BaseModel):
    source: str
    target: str
    lag_days: int
    score: float
    p_value: float


class SimulationDriversOut(BaseModel):
    run_id: UUID
    domain: str
    predictive_drivers: list[SimulationDriverItem]
    causal_evidence: list[SimulationCausalEdgeItem]
    causal_evidence_note: str


# ---------------------------------------------------------------------------
# Run-scoped executive summary (Phase 2) — built only from a persisted
# run's own evidence, never a generic template. Distinct from the
# catalogue's 9-field pitch template (``ExecutiveSummaryOut`` in
# app/schemas/copilot.py), which describes a use case, not a specific
# simulation outcome.
# ---------------------------------------------------------------------------


class SimulationSummaryOut(BaseModel):
    run_id: UUID
    scenario: str
    inputs_summary: str
    baseline: str
    predicted_outcome: str
    major_drivers: list[str]
    trade_off: str
    recommendation: str
    confidence: str
    risk: str
