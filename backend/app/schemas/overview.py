"""Executive Overview response schemas (mirrors KPI_CARDS / RECOMMENDATIONS)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class KpiOut(BaseModel):
    """One overview KPI card; ``id`` is the stable KPI code."""

    id: str
    label: str
    value: str
    trend: str
    up: bool
    confidence: int
    drivers: list[str]


class RecommendationOut(BaseModel):
    """Recommendation row; ``id`` is the stable code (r1..r5)."""

    id: str
    title: str
    impact: str
    confidence: int
    risk: str
    status: str = "Pending"

    model_config = ConfigDict(populate_by_name=True)


class RecommendationStatusUpdateIn(BaseModel):
    """Approve or route a recommendation to human review (display labels)."""

    status: Literal["Approved", "Under Review"]
