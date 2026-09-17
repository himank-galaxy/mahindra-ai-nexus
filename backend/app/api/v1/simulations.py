"""Simulation Center endpoints: option metadata, engines, and the run lifecycle."""

from __future__ import annotations

import uuid
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
    SimulationApprovalOut,
    SimulationDecisionIn,
    SimulationDriversOut,
    SimulationMetaOut,
    SimulationRunDetailOut,
    SimulationSummaryOut,
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
async def run_auto_sales(
    payload: AutoSalesSimIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AutoSalesSimOut:
    return await SimulationService(db).run_auto_sales(payload)


@router.post(
    "/dealer-allocation/run",
    response_model=DealerAllocationSimOut,
    summary="Run the Dealer Allocation simulation",
)
async def run_dealer_allocation(
    payload: DealerAllocationSimIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DealerAllocationSimOut:
    return await SimulationService(db).run_dealer_allocation(payload)


@router.post(
    "/collections/run",
    response_model=CollectionsSimOut,
    summary="Run the Finance Collections simulation",
)
async def run_collections(
    payload: CollectionsSimIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CollectionsSimOut:
    return await SimulationService(db).run_collections(payload)


@router.post(
    "/logistics-delay/run",
    response_model=LogisticsDelaySimOut,
    summary="Run the Logistics Delay simulation",
)
async def run_logistics_delay(
    payload: LogisticsDelaySimIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LogisticsDelaySimOut:
    return await SimulationService(db).run_logistics_delay(payload)


@router.post(
    "/credit-pricing/run",
    response_model=CreditPricingSimOut,
    summary="Run the Circularity Credit Pricing simulation",
)
async def run_credit_pricing(
    payload: CreditPricingSimIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreditPricingSimOut:
    return await SimulationService(db).run_credit_pricing(payload)


# ---------------------------------------------------------------------------
# Run lifecycle — declared after every fixed-path route above so a literal
# segment (``meta``, ``causal-drivers``, ``auto-sales``, ...) never risks
# being swallowed by the ``{run_id}`` path parameter.
# ---------------------------------------------------------------------------


@router.get(
    "/{run_id}",
    response_model=SimulationRunDetailOut,
    summary="Fetch a persisted simulation run",
)
async def get_run(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimulationRunDetailOut:
    return await SimulationService(db).get_run(run_id)


@router.get(
    "/{run_id}/drivers",
    response_model=SimulationDriversOut,
    summary="Explain Drivers: predictive contribution vs causal evidence for a run",
)
async def get_run_drivers(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimulationDriversOut:
    return await SimulationService(db).get_drivers(run_id)


@router.post(
    "/{run_id}/summary",
    response_model=SimulationSummaryOut,
    summary="Generate an executive summary grounded in a run's own persisted evidence",
)
async def generate_run_summary(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimulationSummaryOut:
    return await SimulationService(db).generate_summary(run_id)


@router.post(
    "/{run_id}/approve",
    response_model=SimulationApprovalOut,
    summary="Approve a simulation run's recommendation",
)
async def approve_run(
    run_id: uuid.UUID,
    payload: SimulationDecisionIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimulationApprovalOut:
    return await SimulationService(db).approve_run(run_id, payload.reason)


@router.post(
    "/{run_id}/reject",
    response_model=SimulationApprovalOut,
    summary="Reject a simulation run's recommendation",
)
async def reject_run(
    run_id: uuid.UUID,
    payload: SimulationDecisionIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimulationApprovalOut:
    return await SimulationService(db).reject_run(run_id, payload.reason)
