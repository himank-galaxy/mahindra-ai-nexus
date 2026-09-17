"""Logistics Delay Simulation: repository over real shipments/routes/warehouse_events.

Named distinctly from ``app/repositories/logistics.py`` (an existing,
unrelated dashboard-panel repository over ``LogisticsRoute``/
``WarehouseSignal`` ORM models) to avoid colliding with an already-wired
screen.

``dispatch_delay_minutes``, ``port_delay``, and ``customs_delay`` are
never read here: every shipment in the runtime schema is domestic ROAD
transport (no SEA/AIR mode, no port/customs leg), so these three columns
are always constant/zero across all 7,500 shipments — a generator
artifact, not a real signal (see
docs/simulation_centre_implementation.md §4.4).
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.runtime_schema import runtime_tables

ROUTES = runtime_tables["routes"]
SHIPMENTS = runtime_tables["shipments"]
WAREHOUSE_EVENTS = runtime_tables["warehouse_events"]

# Real recorded categories on `shipments.priority` — the wire value sent
# to/from the API is always the exact real category (left column), never
# the label, matching the Collections channel/offer precedent.
PRIORITY_DISPLAY_NAMES: dict[str, str] = {
    "LOW": "Low",
    "NORMAL": "Normal",
    "HIGH": "High",
    "CRITICAL": "Critical",
}

_ROUTE_COLUMNS = (
    ROUTES.c.route_id,
    ROUTES.c.origin_city_name,
    ROUTES.c.destination_city_name,
    ROUTES.c.origin_region_id,
    ROUTES.c.destination_region_id,
    ROUTES.c.typical_transit_hours,
    ROUTES.c.sla_hours,
    ROUTES.c.baseline_cost_inr,
    ROUTES.c.distance_km,
)


class LogisticsDelaySimulationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_routes(self) -> list[dict]:
        """Real active routes for the UI's Route select — ``id`` is the
        wire value (route_id), ``label`` a human-readable
        "Origin → Destination" string built from real city names."""
        rows = (
            (
                await self._session.execute(
                    select(ROUTES.c.route_id, ROUTES.c.origin_city_name, ROUTES.c.destination_city_name)
                    .where(ROUTES.c.active.is_(True))
                    .order_by(ROUTES.c.origin_city_name, ROUTES.c.destination_city_name)
                )
            )
            .mappings()
            .all()
        )
        return [
            {"id": row["route_id"], "label": f"{row['origin_city_name']} → {row['destination_city_name']}"}
            for row in rows
        ]

    async def get_route(self, route_id: str) -> dict | None:
        row = (
            await self._session.execute(select(*_ROUTE_COLUMNS).where(ROUTES.c.route_id == route_id))
        ).mappings().first()
        return dict(row) if row else None

    async def get_route_alternatives(self, route_id: str) -> list[dict]:
        """Other active routes on the same origin-region → destination-region
        pair — the real candidate set for the reroute optimizer."""
        current = await self.get_route(route_id)
        if current is None:
            return []
        rows = (
            (
                await self._session.execute(
                    select(*_ROUTE_COLUMNS).where(
                        ROUTES.c.origin_region_id == current["origin_region_id"],
                        ROUTES.c.destination_region_id == current["destination_region_id"],
                        ROUTES.c.route_id != route_id,
                        ROUTES.c.active.is_(True),
                    )
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    async def load_shipment_frame(self) -> pd.DataFrame:
        """One row per shipment: real route/weather/vehicle/priority
        features plus the real ``delay_minutes``/``sla_breach`` outcomes.

        Warehouse congestion is averaged from the shipment's own linked
        ``warehouse_events`` (dispatch + arrival touchpoints), never a
        static per-warehouse baseline — a genuine per-shipment signal.
        """
        shipments = (
            (
                await self._session.execute(
                    select(
                        SHIPMENTS.c.shipment_id,
                        SHIPMENTS.c.route_id,
                        SHIPMENTS.c.distance_km,
                        SHIPMENTS.c.priority,
                        SHIPMENTS.c.weather_disruption,
                        SHIPMENTS.c.vehicle_breakdown,
                        SHIPMENTS.c.delay_minutes,
                        SHIPMENTS.c.sla_breach,
                        SHIPMENTS.c.dispatch_time,
                    )
                )
            )
            .mappings()
            .all()
        )
        frame = pd.DataFrame(shipments)
        if frame.empty:
            return frame

        congestion = (
            (
                await self._session.execute(
                    select(
                        WAREHOUSE_EVENTS.c.shipment_id,
                        func.avg(WAREHOUSE_EVENTS.c.warehouse_utilization_pct).label("warehouse_utilization_pct"),
                        func.avg(WAREHOUSE_EVENTS.c.dock_wait_minutes).label("dock_wait_minutes"),
                    ).group_by(WAREHOUSE_EVENTS.c.shipment_id)
                )
            )
            .mappings()
            .all()
        )
        congestion_frame = pd.DataFrame(congestion)
        frame = frame.merge(congestion_frame, on="shipment_id", how="left")

        # Defensive: asyncpg can promote SUM/AVG aggregates to Decimal
        # against real Postgres depending on the underlying column type.
        for column in ("distance_km", "delay_minutes", "warehouse_utilization_pct", "dock_wait_minutes"):
            frame[column] = frame[column].astype(float)
        frame["warehouse_utilization_pct"] = frame["warehouse_utilization_pct"].fillna(
            frame["warehouse_utilization_pct"].mean()
        )
        frame["dock_wait_minutes"] = frame["dock_wait_minutes"].fillna(frame["dock_wait_minutes"].mean())
        frame["weather_disruption"] = frame["weather_disruption"].astype(float)
        frame["vehicle_breakdown"] = frame["vehicle_breakdown"].astype(float)
        frame["sla_breach"] = frame["sla_breach"].astype(float)
        frame["any_delay"] = (frame["delay_minutes"] > 0).astype(float)
        frame["dispatch_time"] = pd.to_datetime(frame["dispatch_time"], utc=True)
        return frame.sort_values("dispatch_time").reset_index(drop=True)
