"""PoC roadmap reads/writes: shortlisted solutions."""

from __future__ import annotations

from sqlalchemy import select

from app.models import PocItem
from app.repositories.base import BaseRepository


class PocRepository(BaseRepository[PocItem]):
    model_type = PocItem

    async def get_by_name(self, name: str) -> PocItem | None:
        stmt = select(PocItem).where(PocItem.name == name, PocItem.deleted_at.is_(None))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
