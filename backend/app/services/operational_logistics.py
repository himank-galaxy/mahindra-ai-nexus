"""Logistics responses derived from canonical route and event history."""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select

from app.core.errors import NotFoundError
from app.database.runtime_schema import runtime_tables
from app.schemas.logistics import AutoHealOut, RouteOut, SignalOut
from app.services.base import BaseService

ROUTES = runtime_tables["routes"]
SHIPMENTS = runtime_tables["shipments"]
WAREHOUSES = runtime_tables["warehouses"]
WAREHOUSE_EVENTS = runtime_tables["warehouse_events"]
ROUTE_NAMESPACE = uuid.UUID("29f51f15-83bb-4c73-ab36-a3353c089f56")


def _route_uuid(route_id: str) -> uuid.UUID:
    return uuid.uuid5(ROUTE_NAMESPACE, route_id)


class OperationalLogisticsService(BaseService):
    async def _routes(self) -> list[RouteOut]:
        statement = (
            select(
                ROUTES.c.route_id,
                ROUTES.c.origin_city_name,
                ROUTES.c.destination_city_name,
                func.count(SHIPMENTS.c.shipment_id).label("shipments"),
                func.count(SHIPMENTS.c.shipment_id).filter(SHIPMENTS.c.sla_breach.is_(True)).label("sla_breaches"),
                func.count(SHIPMENTS.c.shipment_id)
                .filter(
                    or_(
                        SHIPMENTS.c.delay_minutes > 0,
                        SHIPMENTS.c.dispatch_delay_minutes > 0,
                    )
                )
                .label("delayed_shipments"),
                func.coalesce(
                    func.avg(SHIPMENTS.c.baseline_cost_inr),
                    ROUTES.c.baseline_cost_inr,
                ).label("avg_cost_inr"),
            )
            .select_from(
                ROUTES.outerjoin(
                    SHIPMENTS,
                    SHIPMENTS.c.route_id == ROUTES.c.route_id,
                )
            )
            .where(ROUTES.c.active.is_(True))
            .group_by(
                ROUTES.c.route_id,
                ROUTES.c.origin_city_name,
                ROUTES.c.destination_city_name,
                ROUTES.c.baseline_cost_inr,
            )
        )
        rows = (await self._session.execute(statement)).mappings().all()

        result: list[RouteOut] = []
        for row in rows:
            shipments = int(row["shipments"] or 0)
            sla_risk = round(int(row["sla_breaches"] or 0) / shipments * 100) if shipments else 0
            delay_prob = round(int(row["delayed_shipments"] or 0) / shipments * 100) if shipments else 0
            name = f"{row['origin_city_name']} → {row['destination_city_name']}"
            action = (
                "Reroute next dispatch via alternate carrier"
                if sla_risk >= 25
                else "Maintain route with ETA monitoring"
            )
            result.append(
                RouteOut(
                    id=_route_uuid(str(row["route_id"])),
                    name=name,
                    slaRisk=sla_risk,
                    delayProb=delay_prob,
                    cost=f"₹{float(row['avg_cost_inr'] or 0):,.0f} avg",
                    action=action,
                    rerouted=False,
                )
            )
        return sorted(result, key=lambda route: (-route.sla_risk, route.name))

    async def list_routes(self) -> list[RouteOut]:
        return await self._routes()

    async def list_warehouse_signals(self) -> list[SignalOut]:
        statement = (
            select(
                WAREHOUSES.c.warehouse_id,
                WAREHOUSES.c.warehouse_name,
                WAREHOUSES.c.baseline_utilization_pct,
                func.count(WAREHOUSE_EVENTS.c.warehouse_event_id).label("event_count"),
                func.count(WAREHOUSE_EVENTS.c.warehouse_event_id)
                .filter(WAREHOUSE_EVENTS.c.congestion_flag.is_(True))
                .label("congestion_events"),
                func.coalesce(
                    func.avg(WAREHOUSE_EVENTS.c.warehouse_utilization_pct),
                    WAREHOUSES.c.baseline_utilization_pct,
                ).label("avg_utilization"),
                func.coalesce(
                    func.avg(WAREHOUSE_EVENTS.c.dock_wait_minutes),
                    0,
                ).label("avg_dock_wait"),
            )
            .select_from(
                WAREHOUSES.outerjoin(
                    WAREHOUSE_EVENTS,
                    WAREHOUSE_EVENTS.c.warehouse_id == WAREHOUSES.c.warehouse_id,
                )
            )
            .where(WAREHOUSES.c.active.is_(True))
            .group_by(
                WAREHOUSES.c.warehouse_id,
                WAREHOUSES.c.warehouse_name,
                WAREHOUSES.c.baseline_utilization_pct,
            )
            .order_by(WAREHOUSES.c.warehouse_name)
        )
        rows = (await self._session.execute(statement)).mappings().all()

        result: list[SignalOut] = []
        for row in rows:
            events = int(row["event_count"] or 0)
            congestion = int(row["congestion_events"] or 0)
            utilization = float(row["avg_utilization"] or 0)
            dock_wait = float(row["avg_dock_wait"] or 0)
            congestion_rate = congestion / events if events else 0.0
            result.extend(
                [
                    SignalOut(
                        label=f"{row['warehouse_name']} utilization",
                        value=f"{utilization * 100:.1f}%",
                        tone="warning" if utilization >= 0.85 else "success",
                    ),
                    SignalOut(
                        label=f"{row['warehouse_name']} congestion",
                        value=f"{congestion_rate * 100:.1f}%",
                        tone="danger" if congestion_rate >= 0.20 else "success",
                    ),
                    SignalOut(
                        label=f"{row['warehouse_name']} dock wait",
                        value=f"{dock_wait:.1f} min",
                        tone="warning" if dock_wait >= 30 else "success",
                    ),
                ]
            )
        return result

    async def _by_id(self, route_id: uuid.UUID) -> RouteOut:
        for route in await self._routes():
            if route.id == route_id:
                return route
        raise NotFoundError(
            f"Operational route '{route_id}' not found.",
            code="route_not_found",
        )

    async def predict_delay(self, route_id: uuid.UUID) -> RouteOut:
        return await self._by_id(route_id)

    async def reroute(self, route_id: uuid.UUID) -> RouteOut:
        route = await self._by_id(route_id)
        return route.model_copy(
            update={
                "rerouted": True,
                "action": "Reroute approved; monitor the next dispatch",
            }
        )

    async def auto_heal(self, route_id: uuid.UUID) -> AutoHealOut:
        route = await self.reroute(route_id)
        steps = [
            f"Identify delayed shipments on {route.name}",
            "Notify assigned transporter",
            "Publish recalculated ETA from shipment events",
            "Flag affected delivery commitments",
            "Monitor next-dispatch SLA",
        ]
        return AutoHealOut(route=route, steps=steps)
