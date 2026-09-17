"""Finance reads: product portfolio and customer twins."""

from __future__ import annotations

from collections.abc import Sequence

from app.models import CustomerTwin, FinanceProduct
from app.repositories.base import BaseRepository


class FinanceRepository(BaseRepository[FinanceProduct]):
    model_type = FinanceProduct

    async def list_twins(self) -> Sequence[CustomerTwin]:
        repo = TwinRepository(self._session)
        return await repo.list_all()


class TwinRepository(BaseRepository[CustomerTwin]):
    model_type = CustomerTwin
