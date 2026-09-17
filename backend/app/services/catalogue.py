"""Catalogue reads with explicit handling for absent runtime entities."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.catalogue import BucketOut
from app.services.base import BaseService


class CatalogueService(BaseService):
    """The canonical runtime schema has no solution-catalogue entity."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_buckets(
        self,
        tag: str | None = None,
    ) -> list[BucketOut]:
        return []

    async def list_tags(self) -> list[str]:
        return []
