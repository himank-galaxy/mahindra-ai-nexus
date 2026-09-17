"""Read-only dataset catalog and paginated data endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.data import DataCatalogOut, DataRowsOut, DataStatusOut
from app.services.data_reader import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, DataReader

router = APIRouter()


@router.get("/catalog", response_model=DataCatalogOut, summary="Screen/module dataset catalog")
async def get_catalog(db: Annotated[AsyncSession, Depends(get_db)]) -> DataCatalogOut:
    return await DataReader(db).catalog()


@router.get("/datasets/{dataset_id}/rows", response_model=DataRowsOut, summary="Server-paginated dataset rows")
async def get_rows(
    dataset_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    cursor: Annotated[str | None, Query(description="Cursor for the next older page.")] = None,
    before: Annotated[str | None, Query(description="Cursor for the previous newer page.")] = None,
) -> DataRowsOut:
    return await DataReader(db).rows(dataset_id, page_size=page_size, cursor=cursor, before=before)


@router.get("/datasets/{dataset_id}/status", response_model=DataStatusOut, summary="Dataset freshness and live status")
async def get_status(
    dataset_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataStatusOut:
    return await DataReader(db).status(dataset_id)
