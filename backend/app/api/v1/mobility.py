"""Auto Mobility Causal Twin endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.mobility import MobilityAskIn, MobilityAskOut, MobilityGraphOut, MobilityKpiOut
from app.services import MobilityService

router = APIRouter()


@router.get("/graph", response_model=MobilityGraphOut, summary="Causal decision graph nodes + edges")
async def get_graph(db: Annotated[AsyncSession, Depends(get_db)]) -> MobilityGraphOut:
    return await MobilityService(db).get_graph()


@router.get("/kpis", response_model=list[MobilityKpiOut], summary="Business health KPIs")
async def list_kpis(db: Annotated[AsyncSession, Depends(get_db)]) -> list[MobilityKpiOut]:
    return await MobilityService(db).list_kpis()


@router.post("/ask", response_model=MobilityAskOut, summary="Ask the causal twin a question")
async def ask(
    payload: MobilityAskIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MobilityAskOut:
    return await MobilityService(db).ask(payload)
