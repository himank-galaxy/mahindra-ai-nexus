"""Dealer reads: dealerships and their AI-scored leads."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app.models import Dealer, DealerLead
from app.repositories.base import BaseRepository


class DealerRepository(BaseRepository[Dealer]):
    model_type = Dealer

    async def get_by_code(self, code: str) -> Dealer | None:
        stmt = self._base_query().where(Dealer.code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_leads(self, dealer_id: uuid.UUID) -> Sequence[DealerLead]:
        stmt = (
            select(DealerLead)
            .where(DealerLead.dealer_id == dealer_id, DealerLead.deleted_at.is_(None))
            .order_by(DealerLead.sort_order)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_lead(self, lead_id: uuid.UUID) -> DealerLead | None:
        stmt = select(DealerLead).where(DealerLead.id == lead_id, DealerLead.deleted_at.is_(None))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
