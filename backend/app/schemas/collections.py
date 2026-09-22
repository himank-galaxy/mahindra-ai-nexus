"""Collections response schemas (mirrors swarm agents, tiles, case rows)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.trust import ComplianceCheckOut, OutcomeOut

# Real recorded categories (see app/repositories/collections_simulation.py)
# — the exact same enums Collections Simulation uses, never a UI-invented
# grouping, so a human override always maps to a real historical category
# the recovery model was actually trained on.
CHANNEL_VALUES = Literal["SMS", "WHATSAPP", "EMAIL", "CALL", "FIELD_VISIT"]
OFFER_VALUES = Literal["NONE", "PAYMENT_REMINDER", "PARTIAL_PAYMENT_PLAN", "REPAYMENT_PLAN_DISCUSSION"]

# Backend-derived, explainable case priority (see
# app/services/collections_priority.py) — never randomly assigned.
PRIORITY_VALUES = Literal["Critical", "High", "Medium", "Low"]

# One of four mutually-exclusive buckets the frontend filters by (see
# CollectionsService._categorize) — computed purely from real governance/
# lifecycle/compliance fields, never a fifth invented state.
CATEGORY_VALUES = Literal["actionable", "review_required", "approved", "resolved"]


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
    case_id: str
    customer: str
    dpd: int
    out: str
    roll: int
    channel: str
    action: str
    # Channel + action combined into one label (e.g. "Field Visit +
    # Repayment Plan Discussion") — the same real recommendation, just
    # presented as a single "Best Action" column.
    best_action: str
    prob: int
    flag: str
    status: str
    # Which governance mechanism owns this case's decision: an immutable
    # canonical (Synthetic Data Factory) trust_decisions row, or a live
    # decision made from this screen (see app/services/collections.py).
    # Action buttons are disabled on the frontend for "canonical" rows —
    # those are immutable audit history, the same rule the Trust Ledger
    # applies to its own canonical decisions.
    governance_track: Literal["canonical", "live"]
    decision_code: str | None = None
    # Filter-tab bucket — see CollectionsService._categorize.
    category: CATEGORY_VALUES
    # Backend-derived priority ranking — see
    # app/services/collections_priority.py. Click-to-explain on the
    # frontend surfaces `priority_reason`.
    priority: PRIORITY_VALUES
    priority_reason: str
    scored_at: datetime
    model_version: str

    model_config = ConfigDict(populate_by_name=True)


class ModifyActionIn(BaseModel):
    """Human override of the AI-recommended channel/offer for a case —
    both real recorded categories, never a free-text action string (see
    app/repositories/collections_simulation.py). The original AI
    recommendation is preserved separately; this never replaces it."""

    channel: CHANNEL_VALUES
    offer: OFFER_VALUES
    reason: str = Field(default="", max_length=512)


class CaseTrustLedgerOut(BaseModel):
    """Real governance state for one case — reuses the exact Trust Ledger
    compliance/outcome shapes (never a separate, possibly-inconsistent
    representation). ``track`` is ``"none"`` only when the case has never
    been decided by either mechanism, in which case ``compliance`` is a
    live (unpersisted) preview of what evaluating it right now would show."""

    track: Literal["canonical", "live", "none"]
    decision_code: str | None
    approval: str
    audit_status: str
    compliance: list[ComplianceCheckOut]
    priority: PRIORITY_VALUES
    priority_reason: str
    scored_at: datetime
    model_version: str
    recommended_channel: str | None = None
    recommended_offer: str | None = None
    modified_channel: str | None = None
    modified_offer: str | None = None
    modification_reason: str | None = None
    outcome: OutcomeOut
