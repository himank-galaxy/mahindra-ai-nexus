"""Reference reads: regions and vehicle models."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Region, VehicleModel


class ReferenceRepository:
    """Lookup tables with natural string keys (no UUID id)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_regions(self) -> Sequence[str]:
        result = await self._session.execute(select(Region.code))
        return result.scalars().all()

    async def list_vehicle_models(self) -> Sequence[str]:
        result = await self._session.execute(select(VehicleModel.name))
        return result.scalars().all()
