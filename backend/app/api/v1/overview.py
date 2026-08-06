"""Executive Overview endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.overview import KpiOut, RecommendationOut, RecommendationStatusUpdateIn
from app.services import OverviewService

router = APIRouter()

# Mounted at the /api/v1 root (the plan catalogs it as PATCH /recommendations/{id}).
recommendations_router = APIRouter()


@router.get("/kpis", response_model=list[KpiOut], summary="KPI cards with drivers")
async def list_kpis(db: Annotated[AsyncSession, Depends(get_db)]) -> list[KpiOut]:
    return await OverviewService(db).list_kpis()


@router.get("/recommendations", response_model=list[RecommendationOut], summary="AI recommendations")
async def list_recommendations(db: Annotated[AsyncSession, Depends(get_db)]) -> list[RecommendationOut]:
    return await OverviewService(db).list_recommendations()


@recommendations_router.patch(
    "/recommendations/{rec_code}",
    response_model=RecommendationOut,
    summary="Approve or route a recommendation to human review",
)
async def update_recommendation(
    rec_code: str,
    payload: RecommendationStatusUpdateIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecommendationOut:
    return await OverviewService(db).update_recommendation_status(rec_code, payload.status)
