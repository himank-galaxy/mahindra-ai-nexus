"""Logistics AI Control Tower endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.logistics import (
    AutoHealOut,
    ModifyShipmentActionIn,
    RouteOut,
    ShipmentOut,
    ShipmentTrustLedgerOut,
    SignalOut,
    SlaReportOut,
)
from app.schemas.trust import EscalateDecisionIn
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


@router.post("/routes/{route_id}/reroute", response_model=RouteOut, summary="Preview recommended reroute")
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


@router.get(
    "/routes/{route_id}/sla-report",
    response_model=SlaReportOut,
    summary="Real SLA report for a route",
)
async def get_sla_report(
    route_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SlaReportOut:
    return await LogisticsService(db).get_sla_report(route_id)


@router.get(
    "/routes/{route_id}/shipments",
    response_model=list[ShipmentOut],
    summary="Real shipments on a route (drill-down)",
)
async def list_shipments(
    route_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ShipmentOut]:
    return await LogisticsService(db).list_shipments(route_id)


@router.post(
    "/shipments/{shipment_id}/approve",
    response_model=ShipmentOut,
    summary="Approve the AI recommendation for a shipment",
)
async def approve_shipment(
    shipment_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ShipmentOut:
    return await LogisticsService(db).approve_shipment(shipment_id)


@router.post(
    "/shipments/{shipment_id}/modify",
    response_model=ShipmentOut,
    summary="Approve with a human-modified action/route",
)
async def modify_shipment(
    shipment_id: str,
    payload: ModifyShipmentActionIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ShipmentOut:
    return await LogisticsService(db).modify_shipment(shipment_id, payload.action, payload.route_id, payload.reason)


@router.post(
    "/shipments/{shipment_id}/review",
    response_model=ShipmentOut,
    summary="Send shipment to human review",
)
async def review_shipment(
    shipment_id: str,
    payload: EscalateDecisionIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ShipmentOut:
    return await LogisticsService(db).review_shipment(shipment_id, payload.reviewer_role, payload.reason)


@router.get(
    "/shipments/{shipment_id}/ledger",
    response_model=ShipmentTrustLedgerOut,
    summary="Real compliance/approval/outcome state for a shipment",
)
async def get_shipment_ledger(
    shipment_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ShipmentTrustLedgerOut:
    return await LogisticsService(db).get_shipment_ledger(shipment_id)
