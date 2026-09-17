"""Repository layer — data access only, one repository per domain."""

from app.repositories.agent import AiAgentRepository
from app.repositories.auto_sales import AutoSalesRepository
from app.repositories.dealer_allocation import DealerAllocationRepository
from app.repositories.catalogue import CatalogueRepository
from app.repositories.circularity import CircularityRepository
from app.repositories.collections import CollectionsRepository
from app.repositories.collections_simulation import CollectionsSimulationRepository
from app.repositories.copilot import CopilotRepository
from app.repositories.credit_pricing_simulation import CreditPricingSimulationRepository
from app.repositories.dealer import DealerRepository
from app.repositories.finance import FinanceRepository, TwinRepository
from app.repositories.logistics import LogisticsRepository
from app.repositories.logistics_delay_simulation import LogisticsDelaySimulationRepository
from app.repositories.mobility import MobilityRepository
from app.repositories.overview import OverviewRepository
from app.repositories.poc import PocRepository
from app.repositories.reference import ReferenceRepository
from app.repositories.simulation_run import SimulationRunRepository
from app.repositories.trust import TrustRepository

__all__ = [
    "AiAgentRepository",
    "AutoSalesRepository",
    "DealerAllocationRepository",
    "CatalogueRepository",
    "CircularityRepository",
    "CollectionsRepository",
    "CollectionsSimulationRepository",
    "CopilotRepository",
    "CreditPricingSimulationRepository",
    "DealerRepository",
    "FinanceRepository",
    "LogisticsDelaySimulationRepository",
    "LogisticsRepository",
    "MobilityRepository",
    "OverviewRepository",
    "PocRepository",
    "ReferenceRepository",
    "SimulationRunRepository",
    "TrustRepository",
    "TwinRepository",
]
