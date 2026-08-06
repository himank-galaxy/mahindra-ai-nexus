"""Simulation Center endpoints: option metadata, engines and causal drivers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.simulation import (
    AutoSalesSimIn,
    AutoSalesSimOut,
    CausalDriversOut,
    CollectionsSimIn,
    CollectionsSimOut,
    CreditPricingSimIn,
    CreditPricingSimOut,
    DealerAllocationSimIn,
    DealerAllocationSimOut,
    LogisticsDelaySimIn,
    LogisticsDelaySimOut,
    SimulationMetaOut,
)
from app.services import SimulationService

router = APIRouter()


@router.get("/meta", response_model=SimulationMetaOut, summary="Regions + vehicle models for selects")
async def get_meta(db: Annotated[AsyncSession, Depends(get_db)]) -> SimulationMetaOut:
    return await SimulationService(db).get_meta()


@router.get(
    "/causal-drivers",
    response_model=CausalDriversOut,
    summary="Explain-drivers modal content for a simulation domain",
)
async def get_causal_drivers(
    db: Annotated[AsyncSession, Depends(get_db)],
    domain: str = "auto-sales",
) -> CausalDriversOut:
    return await SimulationService(db).causal_drivers(domain)


@router.post("/auto-sales/run", response_model=AutoSalesSimOut, summary="Run the Auto Sales simulation")
async def run_auto_sales(payload: AutoSalesSimIn) -> AutoSalesSimOut:
    return SimulationService.run_auto_sales(payload)


@router.post(
    "/dealer-allocation/run",
    response_model=DealerAllocationSimOut,
    summary="Run the Dealer Allocation simulation",
)
async def run_dealer_allocation(payload: DealerAllocationSimIn) -> DealerAllocationSimOut:
    return SimulationService.run_dealer_allocation(payload)


@router.post(
    "/collections/run",
    response_model=CollectionsSimOut,
    summary="Run the Finance Collections simulation",
)
async def run_collections(payload: CollectionsSimIn) -> CollectionsSimOut:
    return SimulationService.run_collections(payload)


@router.post(
    "/logistics-delay/run",
    response_model=LogisticsDelaySimOut,
    summary="Run the Logistics Delay simulation",
)
async def run_logistics_delay(payload: LogisticsDelaySimIn) -> LogisticsDelaySimOut:
    return SimulationService.run_logistics_delay(payload)


@router.post(
    "/credit-pricing/run",
    response_model=CreditPricingSimOut,
    summary="Run the Circularity Credit Pricing simulation",
)
async def run_credit_pricing(payload: CreditPricingSimIn) -> CreditPricingSimOut:
    return SimulationService.run_credit_pricing(payload)
