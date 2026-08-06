"""AI Solution Catalogue endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.catalogue import BucketOut
from app.services import CatalogueService

router = APIRouter()


@router.get("/buckets", response_model=list[BucketOut], summary="Solution buckets (tag-filtered)")
async def list_buckets(
    db: Annotated[AsyncSession, Depends(get_db)],
    tag: Annotated[str | None, Query(description="Filter by solution tag chip")] = None,
) -> list[BucketOut]:
    return await CatalogueService(db).list_buckets(tag=tag)


@router.get("/tags", response_model=list[str], summary="Catalogue filter tag chips")
async def list_tags(db: Annotated[AsyncSession, Depends(get_db)]) -> list[str]:
    return await CatalogueService(db).list_tags()
