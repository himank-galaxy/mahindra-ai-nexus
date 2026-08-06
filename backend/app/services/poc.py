"""PoC roadmap: CRUD with server-side dedupe plus the static rollout plan."""

from __future__ import annotations

from datetime import UTC

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models import PocItem
from app.repositories import PocRepository
from app.schemas.poc import PocItemIn, PocItemOut, RoadmapPhaseOut, RoadmapPlanOut
from app.services.base import BaseService

# Phased rollout plan rendered by the Generate PoC Roadmap dialog (poc-roadmap.tsx).
ROADMAP_PHASES = [
    {"p": "Phase 0", "t": "Discovery", "w": "1-2 weeks", "d": "Align sponsors, data readiness, success metrics."},
    {"p": "Phase 1", "t": "Prototype", "w": "3-4 weeks", "d": "Working prototype on real data slice, human-approved."},
    {"p": "Phase 2", "t": "PoC", "w": "6-8 weeks", "d": "End-to-end closed loop with trust ledger + HITL."},
    {"p": "Phase 3", "t": "Production Pilot", "w": "8-12 weeks", "d": "Scale to one BU / region, measure impact."},
]

TOP_POCS = ["AI Simulation Center", "Dealer Revenue Optimizer", "Financial Services AI Command Center"]

OPTIONAL_POC = "Optional: Circular Economy Intelligence Platform"


class PocService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = PocRepository(session)

    async def list_pocs(self) -> list[PocItemOut]:
        items = await self._repo.list_all()
        return [self._to_out(item) for item in items]

    async def add_poc(self, payload: PocItemIn) -> PocItemOut:
        """Shortlist a solution; duplicate names are rejected (409)."""
        existing = await self._repo.get_by_name(payload.name)
        if existing is not None:
            raise ConflictError(
                f"'{payload.name}' is already on the PoC roadmap.",
                code="duplicate_poc_item",
            )
        items = await self._repo.list_all()
        item = PocItem(name=payload.name, bucket=payload.bucket, sort_order=len(items))
        self._session.add(item)
        await self._session.commit()
        await self._session.refresh(item)
        return self._to_out(item)

    async def remove_poc(self, name: str) -> None:
        """Remove a shortlisted solution by name."""
        item = await self._repo.get_by_name(name)
        if item is None:
            raise NotFoundError(f"PoC item '{name}' not found.", code="poc_item_not_found")
        await self._session.delete(item)
        await self._session.commit()

    @staticmethod
    def roadmap_plan() -> RoadmapPlanOut:
        """Static phased rollout plan plus the top-3 recommended PoCs."""
        return RoadmapPlanOut(
            phases=[RoadmapPhaseOut(**phase) for phase in ROADMAP_PHASES],
            top_pocs=list(TOP_POCS),
            optional=OPTIONAL_POC,
        )

    @staticmethod
    def _to_out(item: PocItem) -> PocItemOut:
        added = item.created_at
        if added.tzinfo is None:  # SQLite's now() returns naive datetimes
            added = added.replace(tzinfo=UTC)
        return PocItemOut(
            id=item.id,
            name=item.name,
            bucket=item.bucket,
            added_at=int(added.timestamp() * 1000),
        )
