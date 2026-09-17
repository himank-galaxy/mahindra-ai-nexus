"""PoC roadmap endpoints (server-side replacement for localStorage)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.poc import PocItemIn, PocItemOut, RoadmapPlanOut
from app.services import PocService

router = APIRouter()


@router.get("", response_model=list[PocItemOut], summary="Shortlisted PoC roadmap items")
async def list_pocs(db: Annotated[AsyncSession, Depends(get_db)]) -> list[PocItemOut]:
    return await PocService(db).list_pocs()


@router.post(
    "",
    response_model=PocItemOut,
    status_code=status.HTTP_201_CREATED,
    summary="Shortlist a solution (deduped server-side)",
)
async def add_poc(payload: PocItemIn, db: Annotated[AsyncSession, Depends(get_db)]) -> PocItemOut:
    return await PocService(db).add_poc(payload)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a shortlisted solution")
async def remove_poc(name: str, db: Annotated[AsyncSession, Depends(get_db)]) -> None:
    await PocService(db).remove_poc(name)


@router.get("/roadmap-plan", response_model=RoadmapPlanOut, summary="Phased rollout plan + top-3 PoCs")
async def roadmap_plan() -> RoadmapPlanOut:
    return PocService.roadmap_plan()
