"""Data access for live Collections AI Swarm governance state.

Mirrors ``app/repositories/simulation_run.py``'s approval/review/
compliance methods, but keyed by a real ``collection_case_id`` string
instead of a generated run UUID — see app/models/collections_case.py for
why these are separate ai_state tables rather than reusing the
simulation ones.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collections_case import CollectionCaseDecision, CollectionCaseHumanReview


class CollectionsCaseDecisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_decision(self, collection_case_id: str) -> CollectionCaseDecision | None:
        result = await self._session.execute(
            select(CollectionCaseDecision).where(CollectionCaseDecision.collection_case_id == collection_case_id)
        )
        return result.scalar_one_or_none()

    async def get_decisions(self, collection_case_ids: list[str]) -> dict[str, CollectionCaseDecision]:
        if not collection_case_ids:
            return {}
        result = await self._session.execute(
            select(CollectionCaseDecision).where(CollectionCaseDecision.collection_case_id.in_(collection_case_ids))
        )
        return {row.collection_case_id: row for row in result.scalars().all()}

    async def upsert_decision(
        self,
        *,
        collection_case_id: str,
        status: str,
        recommended_channel: str,
        recommended_offer: str,
        modified_channel: str | None = None,
        modified_offer: str | None = None,
        modification_reason: str | None = None,
        reviewer_role: str | None = None,
        reason: str | None = None,
        actor: str = "demo_user",
    ) -> CollectionCaseDecision:
        """At most one decision row per case — re-deciding (e.g. escalate,
        then later approve) updates this same row rather than creating a
        second one, the same rule the Trust Ledger's simulation track
        follows for its own approvals."""
        existing = await self.get_decision(collection_case_id)
        now = datetime.now(UTC)
        if existing is not None:
            existing.status = status
            existing.recommended_channel = recommended_channel
            existing.recommended_offer = recommended_offer
            existing.modified_channel = modified_channel
            existing.modified_offer = modified_offer
            existing.modification_reason = modification_reason
            existing.reviewer_role = reviewer_role
            existing.reason = reason
            existing.actor = actor
            existing.decided_at = now
            await self._session.commit()
            await self._session.refresh(existing)
            return existing
        decision = CollectionCaseDecision(
            collection_case_id=collection_case_id,
            status=status,
            recommended_channel=recommended_channel,
            recommended_offer=recommended_offer,
            modified_channel=modified_channel,
            modified_offer=modified_offer,
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
        collection_case_id: str,
        reviewer_role: str,
        reason: str | None = None,
        requested_by: str = "demo_user",
    ) -> CollectionCaseHumanReview:
        review = CollectionCaseHumanReview(
            collection_case_id=collection_case_id,
            reviewer_role=reviewer_role,
            reason=reason,
            requested_by=requested_by,
            requested_at=datetime.now(UTC),
        )
        self._session.add(review)
        await self._session.commit()
        await self._session.refresh(review)
        return review

    async def get_human_reviews(self, collection_case_id: str) -> list[CollectionCaseHumanReview]:
        result = await self._session.execute(
            select(CollectionCaseHumanReview)
            .where(CollectionCaseHumanReview.collection_case_id == collection_case_id)
            .order_by(CollectionCaseHumanReview.requested_at)
        )
        return list(result.scalars().all())
