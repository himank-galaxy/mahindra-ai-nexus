"""SQLAlchemy ORM models.

Importing this package registers every table on ``Base.metadata`` so that
Alembic autogenerate and the seeding script see the complete schema
(28 tables — see implementation_plan.md §7).
"""

from app.models.agents import AiAgent, XrExperience
from app.models.catalogue import Solution, SolutionBucket
from app.models.circularity import CarbonCredit
from app.models.collections import CollectionsAgent, CollectionsCase
from app.models.copilot import CopilotMessage, CopilotSession, SuggestedPrompt
from app.models.dealer import Dealer, DealerLead
from app.models.finance import CustomerTwin, FinanceProduct
from app.models.logistics import LogisticsRoute, WarehouseSignal
from app.models.mobility import CausalEdge, CausalNode, CausalQa, MobilityKpi
from app.models.overview import Kpi, KpiDriver, Recommendation
from app.models.poc import PocItem
from app.models.reference import Region, VehicleModel
from app.models.simulation import SimulationRun
from app.models.trust import ComplianceRule, TrustDecision
from app.models.user import User

__all__ = [
    "AiAgent",
    "CarbonCredit",
    "CausalEdge",
    "CausalNode",
    "CausalQa",
    "CollectionsAgent",
    "CollectionsCase",
    "ComplianceRule",
    "CopilotMessage",
    "CopilotSession",
    "CustomerTwin",
    "Dealer",
    "DealerLead",
    "FinanceProduct",
    "Kpi",
    "KpiDriver",
    "LogisticsRoute",
    "MobilityKpi",
    "PocItem",
    "Recommendation",
    "Region",
    "SimulationRun",
    "Solution",
    "SolutionBucket",
    "SuggestedPrompt",
    "TrustDecision",
    "User",
    "VehicleModel",
    "WarehouseSignal",
    "XrExperience",
]
