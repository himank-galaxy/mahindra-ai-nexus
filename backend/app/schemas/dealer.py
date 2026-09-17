"""Dealer response schemas (mirrors DEALERS / DEALER_LEADS)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class DealerOut(BaseModel):
    """Dealership headline metrics; ``id`` is the stable code (d1..d5)."""

    id: str
    name: str
    leads: int
    hot_leads: int = Field(alias="hotLeads")
    test_drives_pending: int = Field(alias="testDrivesPending")
    booking_prob: int = Field(alias="bookingProb")
    revenue_at_risk: str = Field(alias="revenueAtRisk")
    leakage: str
    bay_util: str = Field(alias="bayUtil")

    model_config = ConfigDict(populate_by_name=True)


class DealerLeadOut(BaseModel):
    """AI-scored lead; ``id`` is the row UUID used by write endpoints."""

    id: uuid.UUID
    name: str
    vehicle: str
    score: int
    prob: int
    action: str
    revenue: str
    status: str

    model_config = ConfigDict(populate_by_name=True)


class TestDriveSlotIn(BaseModel):
    """Test-drive booking slot (one of the six slots offered in the modal)."""

    slot: str = Field(min_length=1, max_length=64)


class LeadPitchOut(BaseModel):
    """Personalized pitch text generated for a lead."""

    name: str
    text: str


class CoachOut(BaseModel):
    """AI Dealer Coach panel content for one dealership."""

    top_action: str = Field(alias="topAction")
    expected: str
    best_offer: str = Field(alias="bestOffer")
    best_time: str = Field(alias="bestTime")
    risk: str

    model_config = ConfigDict(populate_by_name=True)
