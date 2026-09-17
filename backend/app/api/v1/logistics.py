"""Logistics Control Tower endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.logistics import AutoHealOut, RouteOut, SignalOut
from app.services.operational_logistics import OperationalLogisticsService as LogisticsService

router = APIRouter()


@router.get("/routes", response_model=list[RouteOut], summary="Freight corridor cards")
async def list_routes(db: Annotated[AsyncSession, Depends(get_db)]) -> list[RouteOut]:
    return await LogisticsService(db).list_routes()


@router.get("/warehouse-signals", response_model=list[SignalOut], summary="Warehouse signal tiles")
async def list_warehouse_signals(db: Annotated[AsyncSession, Depends(get_db)]) -> list[SignalOut]:
    return await LogisticsService(db).list_warehouse_signals()


@router.post("/routes/{route_id}/predict-delay", response_model=RouteOut, summary="Re-score delay probability")
async def predict_delay(
    route_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RouteOut:
    return await LogisticsService(db).predict_delay(route_id)


@router.post("/routes/{route_id}/reroute", response_model=RouteOut, summary="Apply recommended reroute")
async def reroute(
    route_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RouteOut:
    return await LogisticsService(db).reroute(route_id)


@router.post(
    "/routes/{route_id}/auto-heal",
    response_model=AutoHealOut,
    summary="Approve & execute the auto-heal workflow",
)
async def auto_heal(
    route_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AutoHealOut:
    return await LogisticsService(db).auto_heal(route_id)
