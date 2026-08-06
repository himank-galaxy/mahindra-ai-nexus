"""Simulation Center schemas: option metadata plus engine inputs/outputs.

Output field names mirror exactly what ``simulation.tsx`` computes so the
frontend can swap its inline formulas for these API calls untouched.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SimulationMetaOut(BaseModel):
    """Reference options feeding the simulator selects."""

    regions: list[str]
    models: list[str]


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
    delay: int
    rev: int
    csat: int
    suggested_split: str = Field(alias="suggestedSplit")

    model_config = ConfigDict(populate_by_name=True)


# ---------------------------------------------------------------------------
# Finance Collections Simulation
# ---------------------------------------------------------------------------


class CollectionsSimIn(BaseModel):
    risk: Literal["Low", "Medium", "High"] = "Medium"
    channel: Literal["Digital", "Voice", "Field"] = "Digital"
    offer: Literal["Restructure", "Waiver", "Settlement", "None"] = "Restructure"
    field: int = Field(default=40, ge=0, le=100)


class CollectionsSimOut(BaseModel):
    prob: int
    cost: int
    friction: int
    net: int


# ---------------------------------------------------------------------------
# Logistics Delay Simulation
# ---------------------------------------------------------------------------


class LogisticsDelaySimIn(BaseModel):
    route: str = Field(default="Mumbai → Pune", max_length=128)
    warehouse: int = Field(default=60, ge=0, le=100)
    vehicle: int = Field(default=70, ge=20, le=100)
    weather: int = Field(default=20, ge=0, le=100)
    sla: Literal["Low", "Medium", "High"] = "High"


class LogisticsDelaySimOut(BaseModel):
    delay: int
    breach: int
    reroute: str
    cost: int


# ---------------------------------------------------------------------------
# Circularity Credit Pricing Simulation
# ---------------------------------------------------------------------------


class CreditPricingSimIn(BaseModel):
    credit_type: str = Field(default="Carbon", max_length=64, alias="type")
    supply: int = Field(default=50, ge=10, le=100)
    demand: int = Field(default=60, ge=10, le=100)
    trace: int = Field(default=70, ge=10, le=100)
    verif: int = Field(default=65, ge=10, le=100)

    model_config = ConfigDict(populate_by_name=True)


class CreditPricingSimOut(BaseModel):
    price_band_low: int = Field(alias="priceBandLow")
    price_band_high: int = Field(alias="priceBandHigh")
    closure: int
    match: int
    compliance_risk: str = Field(alias="complianceRisk")

    model_config = ConfigDict(populate_by_name=True)


# ---------------------------------------------------------------------------
# Causal drivers (Explain Drivers modal)
# ---------------------------------------------------------------------------


class CausalDriversOut(BaseModel):
    domain: str
    drivers: list[str]
