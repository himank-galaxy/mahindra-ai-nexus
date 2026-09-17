"""Circularity response schemas (mirrors CREDITS + RVSF tiles)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CreditOut(BaseModel):
    """Credit marketplace row; ``id`` is the stable code (CR-2214...)."""

    id: str
    type: str
    price: str
    match: int
    closure: int
    trace: int

    model_config = ConfigDict(populate_by_name=True)


class RvsfMetricOut(BaseModel):
    """RVSF operations tile."""

    label: str
    value: str
    tone: str


class ElvEstimateIn(BaseModel):
    """ELV Assessment inputs mirroring the sliders and their defaults."""

    vehicle_type: str = Field(default="SUV", max_length=64, alias="vehicleType")
    age: int = Field(default=12, ge=1, le=25)
    condition: int = Field(default=60, ge=0, le=100)
    docs: int = Field(default=80, ge=0, le=100)

    model_config = ConfigDict(populate_by_name=True)


class ElvEstimateOut(BaseModel):
    price: int
    recoverable: int
    risks: list[str]


class DmrvAskIn(BaseModel):
    """dMRV copilot question."""

    question: str = Field(min_length=1, max_length=512)


class DmrvAskOut(BaseModel):
    question: str
    answer: str
