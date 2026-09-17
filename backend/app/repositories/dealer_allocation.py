"""Dealer Allocation Simulation: repository over real dealers/allocations/deliveries.

Never reads the generator's own priority/demand-index columns
(``regional_demand_index``, ``allocation_priority_score``,
``allocation_priority``) — see
docs/simulation_centre_implementation.md §3.1/§4.2. Note: in the real
history, ``requested_units`` always equals ``allocated_units`` (demand was
never actually constrained) — there is no historical shortage example to
learn a "how we behaved under scarcity" pattern from, which is exactly why
this domain is an optimization problem over real demand/quality signals,
not a trained predictive model.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.runtime_schema import runtime_tables

DEALERS = runtime_tables["dealers"]
ALLOCATIONS = runtime_tables["allocations"]
DELIVERIES = runtime_tables["deliveries"]
BOOKINGS = runtime_tables["bookings"]


class DealerAllocationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_dealer_stats(self) -> pd.DataFrame:
        """One row per active dealer: real capacity, historical demand share, delivery reliability."""
        dealers = (
            (
                await self._session.execute(
                    select(
                        DEALERS.c.dealer_id,
                        DEALERS.c.dealer_name,
                        DEALERS.c.region_name,
                        DEALERS.c.dealer_tier,
                        DEALERS.c.monthly_booking_capacity,
                    ).where(DEALERS.c.active.is_(True))
                )
            )
            .mappings()
            .all()
        )
        frame = pd.DataFrame(dealers)
        if frame.empty:
            return frame

        demand = (
            (
                await self._session.execute(
                    select(
                        ALLOCATIONS.c.dealer_id,
                        func.sum(ALLOCATIONS.c.requested_units).label("total_requested"),
                    ).group_by(ALLOCATIONS.c.dealer_id)
                )
            )
            .mappings()
            .all()
        )
        demand_frame = pd.DataFrame(demand)

        delivery = (
            (
                await self._session.execute(
                    select(
                        DELIVERIES.c.dealer_id,
                        func.avg(case((DELIVERIES.c.delayed, 1.0), else_=0.0)).label("delayed_rate"),
                        func.avg(DELIVERIES.c.total_transit_days).label("avg_transit_days"),
                    ).group_by(DELIVERIES.c.dealer_id)
                )
            )
            .mappings()
            .all()
        )
        delivery_frame = pd.DataFrame(delivery)

        frame = frame.merge(demand_frame, on="dealer_id", how="left").merge(delivery_frame, on="dealer_id", how="left")
        # asyncpg returns Decimal for SUM/AVG over numeric/bigint columns
        # (Postgres promotes them to `numeric`); SQLite returns plain floats,
        # which is why this only surfaces against the real database. Cast
        # explicitly so downstream numpy/pandas arithmetic never sees Decimal.
        for column in ("monthly_booking_capacity", "total_requested", "delayed_rate", "avg_transit_days"):
            frame[column] = frame[column].astype(float)
        frame["total_requested"] = frame["total_requested"].fillna(0.0)
        frame["delayed_rate"] = frame["delayed_rate"].fillna(frame["delayed_rate"].mean())
        frame["avg_transit_days"] = frame["avg_transit_days"].fillna(frame["avg_transit_days"].mean())
        if frame["total_requested"].sum() == 0:
            frame["total_requested"] = 1.0  # avoid an all-zero demand share when history is empty
        return frame

    async def get_avg_booking_value_inr(self) -> float:
        value = (await self._session.execute(select(func.avg(BOOKINGS.c.vehicle_base_price_inr)))).scalar_one()
        return float(value) if value is not None else 0.0
