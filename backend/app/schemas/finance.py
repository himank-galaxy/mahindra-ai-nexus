"""Finance response schemas (mirrors FIN_PRODUCTS + the customer twin)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FinanceProductOut(BaseModel):
    """Financial product portfolio card."""

    name: str
    customers: str
    risk: str
    cross: str
    opp: str

    model_config = ConfigDict(populate_by_name=True)


class TwinSummaryOut(BaseModel):
    """Minimal twin reference used for client-side lookup."""

    id: uuid.UUID
    name: str


class CustomerTwinOut(BaseModel):
    """Unified customer financial twin profile."""

    id: uuid.UUID
    name: str
    location: str
    income_stability: str
    repayment: str
    products: list[str]
    nba: dict[str, Any]
    risk_decomposition: dict[str, str]
    cross_sell: dict[str, str]
    approval_status: str

    model_config = ConfigDict(populate_by_name=True)


class TwinExplainOut(BaseModel):
    """Explain Recommendation modal bullets."""

    bullets: list[str]


class RmScriptOut(BaseModel):
    """RM Script modal content."""

    script: str


class SimulateOfferIn(BaseModel):
    """Simulate Offer request; amount mirrors the slider (₹1L–₹10L)."""

    amount: float = Field(ge=100000, le=1000000)


class SimulateOfferOut(BaseModel):
    """Simulated EMI + risk for the offered amount."""

    amount: int
    emi: int
    risk: str
