"""AI Factory reads: registered agents and XR experiences."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from app.models import AiAgent, XrExperience
from app.repositories.base import BaseRepository


class AiAgentRepository(BaseRepository[AiAgent]):
    model_type = AiAgent

    async def get_by_name(self, name: str) -> AiAgent | None:
        stmt = select(AiAgent).where(AiAgent.name == name)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_xr(self) -> Sequence[XrExperience]:
        stmt = select(XrExperience).order_by(XrExperience.sort_order)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_xr_by_code(self, code: str) -> XrExperience | None:
        stmt = select(XrExperience).where(XrExperience.code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
