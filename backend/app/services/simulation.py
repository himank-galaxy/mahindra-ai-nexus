"""Simulation Center: reference options plus the five deterministic engines."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.causal.drivers import CAUSAL_DRIVERS, SIMULATION_DOMAINS
from app.ai.simulation import (
    auto_sales,
    collections_sim,
    credit_pricing,
    dealer_allocation,
    logistics_delay,
)
from app.core.cache import cached_read
from app.core.errors import NotFoundError
from app.repositories import ReferenceRepository
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
from app.services.base import BaseService


class SimulationService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._ref_repo = ReferenceRepository(session)

    async def get_meta(self) -> SimulationMetaOut:
        return await cached_read("simulations:meta", self._load_meta)

    async def _load_meta(self) -> SimulationMetaOut:
        regions = await self._ref_repo.list_regions()
        models = await self._ref_repo.list_vehicle_models()
        return SimulationMetaOut(regions=list(regions), models=list(models))

    async def causal_drivers(self, domain: str) -> CausalDriversOut:
        if domain not in SIMULATION_DOMAINS:
            raise NotFoundError(
                f"Simulation domain '{domain}' is not known.",
                code="unknown_simulation_domain",
            )
        return CausalDriversOut(domain=domain, drivers=list(CAUSAL_DRIVERS))

    @staticmethod
    def run_auto_sales(payload: AutoSalesSimIn) -> AutoSalesSimOut:
        return auto_sales.run(payload)

    @staticmethod
    def run_dealer_allocation(payload: DealerAllocationSimIn) -> DealerAllocationSimOut:
        return dealer_allocation.run(payload)

    @staticmethod
    def run_collections(payload: CollectionsSimIn) -> CollectionsSimOut:
        return collections_sim.run(payload)

    @staticmethod
    def run_logistics_delay(payload: LogisticsDelaySimIn) -> LogisticsDelaySimOut:
        return logistics_delay.run(payload)

    @staticmethod
    def run_credit_pricing(payload: CreditPricingSimIn) -> CreditPricingSimOut:
        return credit_pricing.run(payload)
