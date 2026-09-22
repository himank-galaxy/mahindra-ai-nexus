"""Trust ledger response schemas (mirrors TRUST_LEDGER + sidebar rules)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TrustDecisionOut(BaseModel):
    """Ledger row; ``id`` is the stable code (AUTO-1042...)."""

    id: str
    use: str
    rec: str
    data: str
    conf: int
    approval: str
    risk: str
    audit: str
    # Whether every mandatory condition for acting on this recommendation
    # is satisfied right now (see app/services/trust.py) — never implied
    # by approval alone, since a mandatory compliance failure still
    # blocks it even after a human has approved.
    execution_eligible: bool = False
    # The real reason behind that boolean — same explanatory treatment
    # every compliance rule card already gets, so "Execution eligible"
    # is never just a bare Yes/Blocked pill.
    execution_eligible_reason: str = ""

    model_config = ConfigDict(populate_by_name=True)


class ComplianceRuleOut(BaseModel):
    """Compliance rule check shown in the trust sidebar."""

    label: str
    status: str


class ComplianceCheckOut(BaseModel):
    """One rule's real evaluation against a single decision — never a
    global aggregate across every decision (see app/services/trust.py)."""

    rule_code: str
    rule_name: str
    result: Literal["PASS", "REVIEW_REQUIRED", "FAIL", "NOT_APPLICABLE"]
    reason: str


class LineageStepOut(BaseModel):
    """One step of the six-step decision lineage."""

    step: int
    title: str
    detail: Any


class ExplanationDriverOut(BaseModel):
    """A real per-feature contribution — only present where one was
    actually fit (the simulation track's trained models/calibrated
    layers). Never fabricated for decisions with no such weight."""

    name: str
    direction: Literal["positive", "negative"]
    contribution: float
    source: Literal["trained_model", "calibrated_heuristic"]
    detail: str


class EvidenceItemOut(BaseModel):
    """A real supporting fact — a business input/output value the
    recommendation was actually generated from, not a weighted driver."""

    label: str
    value: str


class ExplanationOut(BaseModel):
    """Why this recommendation was made — grounded in the decision's own
    persisted evidence, never a generic template (see
    docs/simulation_centre_implementation.md-style WHY answer, §7 of the
    Trust Ledger audit)."""

    recommendation: str
    confidence: int
    confidence_basis: Literal["trained_model", "calibrated_heuristic", "generated"]
    confidence_reason: str
    drivers: list[ExplanationDriverOut]
    supporting_evidence: list[EvidenceItemOut]


class AuditEventOut(BaseModel):
    """One immutable step in a decision's lifecycle — real timestamps
    only, never a synthesized intermediate step that was never actually
    recorded (see app/services/trust.py)."""

    event_type: str
    event_at: datetime
    actor: str
    summary: str


class OutcomeOut(BaseModel):
    """Real observed/expected outcome for one decision — never a
    fabricated value. ``outcome_status`` is ``PENDING`` whenever no real
    ``action_outcomes`` row exists yet for this decision, regardless of
    whether an ``expected_impact`` figure exists on its recommendation
    (see app/services/trust.py). No variance/expected-vs-observed
    comparison is computed here — that field doesn't exist in the
    runtime schema yet."""

    outcome_status: Literal["OBSERVED", "PENDING"]
    expected_impact: dict[str, Any] | None = None
    observed_outcome_type: str | None = None
    observed_outcome_value: str | None = None
    observed_at: datetime | None = None
    business_outcome_observed: bool | None = None
    business_outcome_note: str | None = None


class RejectDecisionIn(BaseModel):
    """Rejection payload; the reason may be empty (UI shows "no reason")."""

    reason: str = Field(default="", max_length=512)


class EscalateDecisionIn(BaseModel):
    """Escalation payload — routes a still-open decision to a human reviewer."""

    reviewer_role: Literal["Business Owner", "Domain Expert", "Risk Reviewer", "Compliance Reviewer", "Quality Reviewer"]
    reason: str = Field(default="", max_length=512)
