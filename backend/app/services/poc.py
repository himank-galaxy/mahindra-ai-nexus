"""PoC roadmap with explicit handling for absent runtime persistence."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainValidationError
from app.schemas.poc import (
    PocItemIn,
    PocItemOut,
    RoadmapPhaseOut,
    RoadmapPlanOut,
)
from app.services.base import BaseService

ROADMAP_PHASES = [
    {"p": "Phase 0", "t": "Discovery", "w": "1-2 weeks", "d": "Align sponsors, data readiness, success metrics."},
    {"p": "Phase 1", "t": "Prototype", "w": "3-4 weeks", "d": "Working prototype on real data slice, human-approved."},
    {"p": "Phase 2", "t": "PoC", "w": "6-8 weeks", "d": "End-to-end closed loop with trust ledger + HITL."},
    {"p": "Phase 3", "t": "Production Pilot", "w": "8-12 weeks", "d": "Scale to one BU / region, measure impact."},
]

TOP_POCS = [
    "AI Simulation Center",
    "Dealer Revenue Optimizer",
    "Financial Services AI Command Center",
]
OPTIONAL_POC = "Optional: Circular Economy Intelligence Platform"


class PocService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_pocs(self) -> list[PocItemOut]:
        return []

    async def add_poc(self, payload: PocItemIn) -> PocItemOut:
        raise DomainValidationError(
            "runtime_0001 has no PoC shortlist persistence entity.",
            code="poc_persistence_unavailable",
        )

    async def remove_poc(self, name: str) -> None:
        raise DomainValidationError(
            "runtime_0001 has no PoC shortlist persistence entity.",
            code="poc_persistence_unavailable",
        )

    @staticmethod
    def roadmap_plan() -> RoadmapPlanOut:
        return RoadmapPlanOut(
            phases=[RoadmapPhaseOut(**phase) for phase in ROADMAP_PHASES],
            top_pocs=list(TOP_POCS),
            optional=OPTIONAL_POC,
        )
