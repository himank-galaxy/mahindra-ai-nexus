"""Trust ledger response schemas (mirrors TRUST_LEDGER + sidebar rules)."""

from __future__ import annotations

from typing import Any

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

    model_config = ConfigDict(populate_by_name=True)


class ComplianceRuleOut(BaseModel):
    """Compliance rule check shown in the trust sidebar."""

    label: str
    status: str


class LineageStepOut(BaseModel):
    """One step of the six-step decision lineage."""

    step: int
    title: str
    detail: Any


class RejectDecisionIn(BaseModel):
    """Rejection payload; the reason may be empty (UI shows "no reason")."""

    reason: str = Field(default="", max_length=512)
