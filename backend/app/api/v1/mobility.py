"""Auto Mobility Causal Twin endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.mobility import (
    MobilityCopilotAskIn,
    MobilityCopilotAskOut,
    MobilityCopilotExplainIn,
    MobilityCopilotExplainOut,
    MobilityCopilotHistoryOut,
    MobilityGraphOut,
    MobilityKpiOut,
    MobilityNodeDetailOut,
)
from app.services.mobility_copilot import MobilityCopilotService
from app.services.operational_mobility import OperationalMobilityService as MobilityService

router = APIRouter()


@router.get("/graph", response_model=MobilityGraphOut, summary="Causal decision graph nodes + edges")
async def get_graph(db: Annotated[AsyncSession, Depends(get_db)]) -> MobilityGraphOut:
    return await MobilityService(db).get_graph()


@router.get("/kpis", response_model=list[MobilityKpiOut], summary="Business health KPIs")
async def list_kpis(db: Annotated[AsyncSession, Depends(get_db)]) -> list[MobilityKpiOut]:
    return await MobilityService(db).list_kpis()


@router.get(
    "/nodes/{metric}",
    response_model=MobilityNodeDetailOut,
    summary="Node detail: value, trend, stats, causal relationships, top drivers, recommended action",
)
async def get_node_detail(
    metric: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    snapshot_id: str | None = None,
) -> MobilityNodeDetailOut:
    return await MobilityService(db).get_node_detail(metric, snapshot_id)


@router.post(
    "/copilot/ask",
    response_model=MobilityCopilotAskOut,
    summary="Ask the Auto Mobility Causal Twin copilot a question (replaces the old keyword-matched /ask)",
)
async def copilot_ask(
    payload: MobilityCopilotAskIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MobilityCopilotAskOut:
    return await MobilityCopilotService(db).ask(payload)


@router.post(
    "/copilot/explain",
    response_model=MobilityCopilotExplainOut,
    summary="Explain the causal graph subset currently displayed in the browser",
)
async def copilot_explain(
    payload: MobilityCopilotExplainIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MobilityCopilotExplainOut:
    return await MobilityCopilotService(db).explain(payload)


@router.get(
    "/copilot/history",
    response_model=MobilityCopilotHistoryOut,
    summary="Full copilot conversation history for one session",
)
async def copilot_history(session_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> MobilityCopilotHistoryOut:
    return await MobilityCopilotService(db).history(session_id)


@router.delete("/copilot", summary="Clear a copilot conversation")
async def copilot_clear(session_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, str]:
    await MobilityCopilotService(db).clear(session_id)
    return {"session_id": session_id, "status": "cleared"}
