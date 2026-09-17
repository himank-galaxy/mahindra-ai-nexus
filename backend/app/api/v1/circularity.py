"""Circular Economy endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.circularity import CreditOut, DmrvAskIn, DmrvAskOut, ElvEstimateIn, ElvEstimateOut, RvsfMetricOut
from app.services.operational_circularity import OperationalCircularityService as CircularityService

router = APIRouter()


@router.get("/credits", response_model=list[CreditOut], summary="Credit marketplace rows")
async def list_credits(db: Annotated[AsyncSession, Depends(get_db)]) -> list[CreditOut]:
    return await CircularityService(db).list_credits()


@router.get("/rvsf-metrics", response_model=list[RvsfMetricOut], summary="RVSF operations tiles")
async def list_rvsf_metrics(db: Annotated[AsyncSession, Depends(get_db)]) -> list[RvsfMetricOut]:
    return await CircularityService(db).list_rvsf_metrics()


@router.get("/dmrv/prompts", response_model=list[str], summary="dMRV copilot suggested questions")
async def list_dmrv_prompts(db: Annotated[AsyncSession, Depends(get_db)]) -> list[str]:
    return await CircularityService(db).list_dmrv_prompts()


@router.post("/dmrv/ask", response_model=DmrvAskOut, summary="Ask the dMRV copilot")
async def dmrv_ask(
    payload: DmrvAskIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DmrvAskOut:
    return await CircularityService(db).dmrv_ask(payload)


@router.post("/elv/estimate", response_model=ElvEstimateOut, summary="Estimate an ELV valuation")
async def estimate_elv(payload: ElvEstimateIn, db: Annotated[AsyncSession, Depends(get_db)]) -> ElvEstimateOut:
    return await CircularityService(db).estimate_elv(payload)


@router.post("/credits/{credit_code}/reprice", response_model=CreditOut, summary="Reprice a credit")
async def reprice_credit(
    credit_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreditOut:
    return await CircularityService(db).reprice_credit(credit_code)


@router.post("/credits/{credit_code}/match-buyer", response_model=CreditOut, summary="Match credit to a buyer")
async def match_buyer(
    credit_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreditOut:
    return await CircularityService(db).match_buyer(credit_code)
