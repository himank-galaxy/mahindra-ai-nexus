"""Executive Overview: KPI cards, recommendations and approval actions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainValidationError, NotFoundError
from app.models import Recommendation
from app.models.enums import RecommendationStatus
from app.repositories import OverviewRepository
from app.schemas.overview import KpiOut, RecommendationOut
from app.services.base import BaseService
from app.services.merger import merge_kpis, merge_recommendations
from app.utils.display import RECOMMENDATION_RISK_DISPLAY, RECOMMENDATION_STATUS_DISPLAY

_STATUS_BY_LABEL = {label: member for member, label in RECOMMENDATION_STATUS_DISPLAY.items()}


class OverviewService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = OverviewRepository(session)

    async def list_kpis(self) -> list[KpiOut]:
        kpis = await self._repo.list_kpis_with_drivers()
        return merge_kpis(kpis)

    async def list_recommendations(self) -> list[RecommendationOut]:
        recs = await self._repo.list_recommendations()
        return merge_recommendations(recs)


    async def update_recommendation_status(self, code: str, status_label: str) -> RecommendationOut:
        """Approve or route a recommendation to human review (Trust-logged)."""
        rec = await self._repo.get_recommendation_by_code(code)
        if rec is None:
            raise NotFoundError(f"Recommendation '{code}' not found.", code="recommendation_not_found")
        rec.status = self._parse_status(status_label)
        rec.decided_at = datetime.now(UTC)
        await self._session.commit()
        return self._to_out(rec)

    @staticmethod
    def _parse_status(status_label: str) -> RecommendationStatus:
        new_status = _STATUS_BY_LABEL.get(status_label)
        if new_status is None or new_status is RecommendationStatus.PENDING:
            raise DomainValidationError(
                "Status must be 'Approved' or 'Under Review'.",
                code="invalid_recommendation_status",
            )
        return new_status

    @staticmethod
    def _to_out(rec: Recommendation) -> RecommendationOut:
        return RecommendationOut(
            id=rec.code,
            title=rec.title,
            impact=rec.impact,
            confidence=rec.confidence,
            risk=RECOMMENDATION_RISK_DISPLAY[rec.risk],
            status=RECOMMENDATION_STATUS_DISPLAY[rec.status],
        )
