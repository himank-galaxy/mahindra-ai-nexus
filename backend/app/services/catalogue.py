"""Catalogue reads: solution buckets (optionally tag-filtered) and tag chips."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cached_read
from app.database.seed_data import SOLUTION_TAGS
from app.repositories import CatalogueRepository
from app.schemas.catalogue import BucketOut, SolutionOut
from app.services.base import BaseService


class CatalogueService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = CatalogueRepository(session)

    async def list_buckets(self, tag: str | None = None) -> list[BucketOut]:
        return await cached_read(f"catalogue:buckets:{tag or 'all'}", lambda: self._load_buckets(tag))

    async def _load_buckets(self, tag: str | None) -> list[BucketOut]:
        buckets = await self._repo.list_buckets(tag=tag)
        return [
            BucketOut(
                name=bucket.name,
                tag=bucket.tag,
                items=[
                    SolutionOut(
                        name=sol.name,
                        problem=sol.problem,
                        solution=sol.solution,
                        diff=sol.differentiator,
                        impact=sol.impact,
                    )
                    for sol in bucket.solutions
                ],
            )
            for bucket in buckets
        ]

    async def list_tags(self) -> list[str]:
        """Frontend filter chips: static superset of bucket tags."""
        return list(SOLUTION_TAGS)
