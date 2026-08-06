"""Dealer Revenue Optimizer endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.dealer import CoachOut, DealerLeadOut, DealerOut, LeadPitchOut, TestDriveSlotIn
from app.services import DealerService

router = APIRouter()

# Mounted under /api/v1/dealer-leads for direct lead actions.
leads_router = APIRouter()


@router.get("", response_model=list[DealerOut], summary="Dealers with headline metrics")
async def list_dealers(db: Annotated[AsyncSession, Depends(get_db)]) -> list[DealerOut]:
    return await DealerService(db).list_dealers()


@router.get("/{dealer_code}/leads", response_model=list[DealerLeadOut], summary="AI-scored leads")
async def list_dealer_leads(
    dealer_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DealerLeadOut]:
    return await DealerService(db).list_leads(dealer_code)


@router.get("/{dealer_code}/coach", response_model=CoachOut, summary="AI Dealer Coach panel")
async def get_coach(
    dealer_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CoachOut:
    return await DealerService(db).get_coach(dealer_code)


@router.post(
    "/{dealer_code}/leads/{lead_id}/pitch",
    response_model=LeadPitchOut,
    summary="Generated personalized pitch",
)
async def generate_pitch(
    dealer_code: str,
    lead_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LeadPitchOut:
    return await DealerService(db).generate_pitch(dealer_code, lead_id)


@leads_router.post("/{lead_id}/message", response_model=DealerLeadOut, summary="Mark WhatsApp sent")
async def message_lead(
    lead_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DealerLeadOut:
    return await DealerService(db).message_lead(lead_id)


@leads_router.post("/{lead_id}/test-drive", response_model=DealerLeadOut, summary="Book a test-drive slot")
async def schedule_test_drive(
    lead_id: uuid.UUID,
    payload: TestDriveSlotIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DealerLeadOut:
    return await DealerService(db).schedule_test_drive(lead_id, payload.slot)


@leads_router.post("/{lead_id}/convert", response_model=DealerLeadOut, summary="Mark lead converted")
async def convert_lead(
    lead_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DealerLeadOut:
    return await DealerService(db).convert_lead(lead_id)
