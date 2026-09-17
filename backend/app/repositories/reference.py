"""Reference reads: regions and vehicle models."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.runtime_schema import runtime_tables

REGIONS = runtime_tables["regions"]
VEHICLE_MODELS = runtime_tables["vehicle_models"]


class ReferenceRepository:
    """Reference options read from the canonical runtime schema."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_regions(self) -> Sequence[str]:
        result = await self._session.execute(select(REGIONS.c.region_name).order_by(REGIONS.c.region_name))
        return result.scalars().all()

    async def list_vehicle_models(self) -> Sequence[str]:
        result = await self._session.execute(select(VEHICLE_MODELS.c.model_name).order_by(VEHICLE_MODELS.c.model_name))
        return result.scalars().all()
