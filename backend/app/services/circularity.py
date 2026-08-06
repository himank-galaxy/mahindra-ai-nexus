"""Circular Economy: credit marketplace, RVSF tiles, dMRV prompts and actions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.causal.qa import match_answer
from app.ai.prompts.dmrv import DMRV_FALLBACK
from app.ai.scoring.elv_valuation import estimate_elv
from app.core.errors import NotFoundError
from app.models import CarbonCredit
from app.models.enums import QaCategory
from app.repositories import CircularityRepository, MobilityRepository
from app.schemas.circularity import (
    CreditOut,
    DmrvAskIn,
    DmrvAskOut,
    ElvEstimateIn,
    ElvEstimateOut,
    RvsfMetricOut,
)
from app.services.base import BaseService


class CircularityService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = CircularityRepository(session)
        self._qa_repo = MobilityRepository(session)

    async def list_credits(self) -> list[CreditOut]:
        credits = await self._repo.list_all()
        return [self._to_out(credit) for credit in credits]

    async def list_rvsf_metrics(self) -> list[RvsfMetricOut]:
        tiles = await self._repo.list_rvsf_metrics()
        return [RvsfMetricOut(label=tile.label, value=tile.value, tone=tile.tone) for tile in tiles]

    async def list_dmrv_prompts(self) -> list[str]:
        qa = await self._qa_repo.list_qa(category=QaCategory.DMRV)
        return [item.question for item in qa]

    async def dmrv_ask(self, payload: DmrvAskIn) -> DmrvAskOut:
        qa = await self._qa_repo.list_qa(category=QaCategory.DMRV)
        answer = match_answer(
            payload.question,
            [(item.question, item.answer) for item in qa],
            DMRV_FALLBACK,
        )
        return DmrvAskOut(question=payload.question, answer=answer)

    @staticmethod
    def estimate_elv(payload: ElvEstimateIn) -> ElvEstimateOut:
        price, recoverable, risks = estimate_elv(payload.age, payload.condition, payload.docs)
        return ElvEstimateOut(price=price, recoverable=recoverable, risks=risks)

    async def reprice_credit(self, code: str) -> CreditOut:
        """Trigger a reprice of the credit (timestamped for audit)."""
        credit = await self._get_credit(code)
        credit.repriced_at = datetime.now(UTC)
        await self._session.commit()
        return self._to_out(credit)

    async def match_buyer(self, code: str) -> CreditOut:
        """Match the credit to a buyer (full match score)."""
        credit = await self._get_credit(code)
        credit.buyer_match = 100
        credit.buyer_matched_at = datetime.now(UTC)
        await self._session.commit()
        return self._to_out(credit)

    async def _get_credit(self, code: str) -> CarbonCredit:
        credit = await self._repo.get_by_code(code)
        if credit is None:
            raise NotFoundError(f"Credit '{code}' not found.", code="credit_not_found")
        return credit

    @staticmethod
    def _to_out(credit: CarbonCredit) -> CreditOut:
        return CreditOut(
            id=credit.code,
            type=credit.type,
            price=credit.price,
            match=credit.buyer_match,
            closure=credit.closure_prob,
            trace=credit.traceability,
        )
