"""Financial Services: product portfolio, customer twins and approvals."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts.finance_explain import EXPLANATION_BULLETS
from app.ai.prompts.rm_script import RM_SCRIPT
from app.ai.scoring.emi import simulate_offer
from app.core.errors import ConflictError, NotFoundError
from app.models import CustomerTwin
from app.models.enums import TwinApprovalStatus
from app.repositories import FinanceRepository, TwinRepository
from app.schemas.finance import (
    CustomerTwinOut,
    FinanceProductOut,
    RmScriptOut,
    SimulateOfferIn,
    SimulateOfferOut,
    TwinExplainOut,
    TwinSummaryOut,
)
from app.services.base import BaseService
from app.utils.display import TWIN_APPROVAL_DISPLAY


class FinanceService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = FinanceRepository(session)
        self._twin_repo = TwinRepository(session)

    async def list_products(self) -> list[FinanceProductOut]:
        products = await self._repo.list_all()
        return [
            FinanceProductOut(
                name=product.name,
                customers=product.customers,
                risk=product.risk,
                cross=product.cross_sell,
                opp=product.opportunity,
            )
            for product in products
        ]

    async def list_twin_summaries(self) -> list[TwinSummaryOut]:
        twins = await self._twin_repo.list_all()
        return [TwinSummaryOut(id=twin.id, name=twin.name) for twin in twins]

    async def get_twin(self, twin_id: uuid.UUID) -> CustomerTwinOut:
        twin = await self._get_twin(twin_id)
        return self._to_out(twin)

    async def submit_twin_approval(self, twin_id: uuid.UUID) -> CustomerTwinOut:
        """Submit the twin's next-best-offer for approval (Draft → Under Review)."""
        twin = await self._get_twin(twin_id)
        if twin.approval_status is not TwinApprovalStatus.DRAFT:
            raise ConflictError(
                f"Approval for twin '{twin_id}' was already submitted.",
                code="approval_already_submitted",
            )
        twin.approval_status = TwinApprovalStatus.UNDER_REVIEW
        await self._session.commit()
        return self._to_out(twin)

    async def explain_twin(self, twin_id: uuid.UUID) -> TwinExplainOut:
        """Explain why the NBA is recommended (bullets from the explain modal)."""
        await self._get_twin(twin_id)
        return TwinExplainOut(bullets=list(EXPLANATION_BULLETS))

    async def generate_rm_script(self, twin_id: uuid.UUID) -> RmScriptOut:
        """Generate the relationship-manager pitch script for the NBA."""
        await self._get_twin(twin_id)
        return RmScriptOut(script=RM_SCRIPT)

    async def simulate_offer(self, twin_id: uuid.UUID, payload: SimulateOfferIn) -> SimulateOfferOut:
        """Simulate EMI + risk for an alternative loan amount."""
        await self._get_twin(twin_id)
        emi, risk = simulate_offer(payload.amount)
        return SimulateOfferOut(amount=int(payload.amount), emi=emi, risk=risk)

    async def _get_twin(self, twin_id: uuid.UUID) -> CustomerTwin:
        twin = await self._twin_repo.get_by_id(twin_id)
        if twin is None:
            raise NotFoundError(f"Customer twin '{twin_id}' not found.", code="twin_not_found")
        return twin

    @staticmethod
    def _to_out(twin: CustomerTwin) -> CustomerTwinOut:
        return CustomerTwinOut(
            id=twin.id,
            name=twin.name,
            location=twin.location,
            income_stability=twin.income_stability,
            repayment=twin.repayment,
            products=list(twin.products),
            nba=twin.nba,
            risk_decomposition=twin.risk_decomposition,
            cross_sell=twin.cross_sell,
            approval_status=TWIN_APPROVAL_DISPLAY[twin.approval_status],
        )
