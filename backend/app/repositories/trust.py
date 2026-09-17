"""Trust ledger reads: audited AI decisions and compliance rules."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from app.models import ComplianceRule, TrustDecision
from app.repositories.base import BaseRepository


class TrustRepository(BaseRepository[TrustDecision]):
    model_type = TrustDecision

    async def get_by_code(self, code: str) -> TrustDecision | None:
        stmt = select(TrustDecision).where(TrustDecision.code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_rules(self) -> Sequence[ComplianceRule]:
        stmt = select(ComplianceRule).order_by(ComplianceRule.sort_order)
        result = await self._session.execute(stmt)
        return result.scalars().all()
