"""Financial Services endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.finance import (
    CustomerTwinOut,
    FinanceProductOut,
    RmScriptOut,
    SimulateOfferIn,
    SimulateOfferOut,
    TwinExplainOut,
    TwinSummaryOut,
)
from app.services import FinanceService

router = APIRouter()


@router.get("/products", response_model=list[FinanceProductOut], summary="Product portfolio cards")
async def list_products(db: Annotated[AsyncSession, Depends(get_db)]) -> list[FinanceProductOut]:
    return await FinanceService(db).list_products()


@router.get("/twins", response_model=list[TwinSummaryOut], summary="Customer twin id/name index")
async def list_twins(db: Annotated[AsyncSession, Depends(get_db)]) -> list[TwinSummaryOut]:
    return await FinanceService(db).list_twin_summaries()


@router.get(
    "/customers/{twin_id}/twin",
    response_model=CustomerTwinOut,
    summary="Unified customer financial twin",
)
async def get_twin(
    twin_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CustomerTwinOut:
    return await FinanceService(db).get_twin(twin_id)


@router.post(
    "/twins/{twin_id}/submit-approval",
    response_model=CustomerTwinOut,
    summary="Submit NBA offer for approval (Draft → Under Review)",
)
async def submit_approval(
    twin_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CustomerTwinOut:
    return await FinanceService(db).submit_twin_approval(twin_id)


@router.post(
    "/twins/{twin_id}/explain",
    response_model=TwinExplainOut,
    summary="Explain why the NBA is recommended",
)
async def explain_twin(
    twin_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TwinExplainOut:
    return await FinanceService(db).explain_twin(twin_id)


@router.post(
    "/twins/{twin_id}/rm-script",
    response_model=RmScriptOut,
    summary="Generate the RM pitch script for the NBA",
)
async def generate_rm_script(
    twin_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RmScriptOut:
    return await FinanceService(db).generate_rm_script(twin_id)


@router.post(
    "/twins/{twin_id}/simulate-offer",
    response_model=SimulateOfferOut,
    summary="Simulate EMI + risk for an alternative loan amount",
)
async def simulate_offer(
    twin_id: uuid.UUID,
    payload: SimulateOfferIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimulateOfferOut:
    return await FinanceService(db).simulate_offer(twin_id, payload)
