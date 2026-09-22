"""Data access for live Logistics AI Control Tower governance state.

Mirrors ``app/repositories/collections_case_decision.py`` exactly, keyed
by a real ``shipment_id`` string instead of a ``collection_case_id`` —
see app/models/logistics_route.py for why these are separate ai_state
tables.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.logistics_route import RouteShipmentDecision, RouteShipmentHumanReview


class LogisticsRouteDecisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_decision(self, shipment_id: str) -> RouteShipmentDecision | None:
        result = await self._session.execute(
            select(RouteShipmentDecision).where(RouteShipmentDecision.shipment_id == shipment_id)
        )
        return result.scalar_one_or_none()

    async def get_decisions(self, shipment_ids: list[str]) -> dict[str, RouteShipmentDecision]:
        if not shipment_ids:
            return {}
        result = await self._session.execute(
            select(RouteShipmentDecision).where(RouteShipmentDecision.shipment_id.in_(shipment_ids))
        )
        return {row.shipment_id: row for row in result.scalars().all()}

    async def upsert_decision(
        self,
        *,
        shipment_id: str,
        status: str,
        recommended_action: str,
        recommended_route_id: str | None = None,
        modified_action: str | None = None,
        modified_route_id: str | None = None,
        modification_reason: str | None = None,
        reviewer_role: str | None = None,
        reason: str | None = None,
        actor: str = "demo_user",
    ) -> RouteShipmentDecision:
        """At most one decision row per shipment — re-deciding (e.g.
        escalate, then later approve) updates this same row rather than
        creating a second one, the same rule the Trust Ledger's
        simulation track follows for its own approvals."""
        existing = await self.get_decision(shipment_id)
        now = datetime.now(UTC)
        if existing is not None:
            existing.status = status
            existing.recommended_action = recommended_action
            existing.recommended_route_id = recommended_route_id
            existing.modified_action = modified_action
            existing.modified_route_id = modified_route_id
            existing.modification_reason = modification_reason
            existing.reviewer_role = reviewer_role
            existing.reason = reason
            existing.actor = actor
            existing.decided_at = now
            await self._session.commit()
            await self._session.refresh(existing)
            return existing
        decision = RouteShipmentDecision(
            shipment_id=shipment_id,
            status=status,
            recommended_action=recommended_action,
            recommended_route_id=recommended_route_id,
            modified_action=modified_action,
            modified_route_id=modified_route_id,
            modification_reason=modification_reason,
            reviewer_role=reviewer_role,
            reason=reason,
            actor=actor,
            decided_at=now,
        )
        self._session.add(decision)
        await self._session.commit()
        await self._session.refresh(decision)
        return decision

    async def create_human_review(
        self,
        *,
        shipment_id: str,
        reviewer_role: str,
        reason: str | None = None,
        requested_by: str = "demo_user",
    ) -> RouteShipmentHumanReview:
        review = RouteShipmentHumanReview(
            shipment_id=shipment_id,
            reviewer_role=reviewer_role,
            reason=reason,
            requested_by=requested_by,
            requested_at=datetime.now(UTC),
        )
        self._session.add(review)
        await self._session.commit()
        await self._session.refresh(review)
        return review

    async def get_human_reviews(self, shipment_id: str) -> list[RouteShipmentHumanReview]:
        result = await self._session.execute(
            select(RouteShipmentHumanReview)
            .where(RouteShipmentHumanReview.shipment_id == shipment_id)
            .order_by(RouteShipmentHumanReview.requested_at)
        )
        return list(result.scalars().all())
