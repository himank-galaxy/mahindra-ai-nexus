"""Repository layer — data access only, one repository per domain."""

from app.repositories.agent import AiAgentRepository
from app.repositories.catalogue import CatalogueRepository
from app.repositories.circularity import CircularityRepository
from app.repositories.collections import CollectionsRepository
from app.repositories.copilot import CopilotRepository
from app.repositories.dealer import DealerRepository
from app.repositories.finance import FinanceRepository, TwinRepository
from app.repositories.logistics import LogisticsRepository
from app.repositories.mobility import MobilityRepository
from app.repositories.overview import OverviewRepository
from app.repositories.poc import PocRepository
from app.repositories.reference import ReferenceRepository
from app.repositories.trust import TrustRepository

__all__ = [
    "AiAgentRepository",
    "CatalogueRepository",
    "CircularityRepository",
    "CollectionsRepository",
    "CopilotRepository",
    "DealerRepository",
    "FinanceRepository",
    "LogisticsRepository",
    "MobilityRepository",
    "OverviewRepository",
    "PocRepository",
    "ReferenceRepository",
    "TrustRepository",
    "TwinRepository",
]
