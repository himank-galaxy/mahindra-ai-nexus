"""Auto Sales Simulation: repository over the real leads -> bookings funnel.

Reads only the canonical runtime schema (never a parallel dataset), and
never selects the generator's own probability columns
(``latent_purchase_intent``, ``booking_probability``,
``cancellation_probability``, ``completion_probability``,
``request_probability``) — see docs/simulation_centre_implementation.md §3.1.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.runtime_schema import runtime_tables

LEADS = runtime_tables["leads"]
TEST_DRIVES = runtime_tables["test_drives"]
FOLLOWUPS = runtime_tables["followups"]
BOOKINGS = runtime_tables["bookings"]
CANCELLATIONS = runtime_tables["cancellations"]


class AutoSalesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_lead_conversion_frame(self) -> pd.DataFrame:
        """One row per lead: pre-decision funnel features + the ``booked`` label."""
        leads = (
            (
                await self._session.execute(
                    select(
                        LEADS.c.lead_id,
                        LEADS.c.region_name,
                        LEADS.c.vehicle_model_name,
                        LEADS.c.budget_fit,
                        LEADS.c.engagement_score,
                        LEADS.c.urgency_score,
                        LEADS.c.model_interest_score,
                        LEADS.c.source_quality,
                        LEADS.c.lead_created_at,
                    )
                )
            )
            .mappings()
            .all()
        )
        frame = pd.DataFrame(leads)
        if frame.empty:
            return frame

        test_drives = (
            (
                await self._session.execute(
                    select(TEST_DRIVES.c.lead_id, TEST_DRIVES.c.completed, TEST_DRIVES.c.any_within_sla_followup)
                )
            )
            .mappings()
            .all()
        )
        td_frame = pd.DataFrame(test_drives)
        if not td_frame.empty:
            td_agg = (
                td_frame.groupby("lead_id")
                .agg(
                    completed_test_drive=("completed", "max"),
                    within_sla_followup=("any_within_sla_followup", "max"),
                )
                .reset_index()
            )
        else:
            td_agg = pd.DataFrame(columns=["lead_id", "completed_test_drive", "within_sla_followup"])

        followups = (
            (await self._session.execute(select(FOLLOWUPS.c.lead_id, FOLLOWUPS.c.completed, FOLLOWUPS.c.customer_responded)))
            .mappings()
            .all()
        )
        fu_frame = pd.DataFrame(followups)
        if not fu_frame.empty:
            fu_agg = (
                fu_frame.groupby("lead_id")
                .agg(
                    followup_completion_rate=("completed", "mean"),
                    followup_response_rate=("customer_responded", "mean"),
                )
                .reset_index()
            )
        else:
            fu_agg = pd.DataFrame(columns=["lead_id", "followup_completion_rate", "followup_response_rate"])

        booked_ids = set((await self._session.execute(select(BOOKINGS.c.lead_id))).scalars().all())

        frame = frame.merge(td_agg, on="lead_id", how="left").merge(fu_agg, on="lead_id", how="left")
        frame["completed_test_drive"] = frame["completed_test_drive"].astype("boolean").fillna(False).astype(bool)
        frame["within_sla_followup"] = frame["within_sla_followup"].astype("boolean").fillna(False).astype(bool)
        frame["followup_completion_rate"] = frame["followup_completion_rate"].fillna(0.0)
        frame["followup_response_rate"] = frame["followup_response_rate"].fillna(0.0)
        frame["booked"] = frame["lead_id"].isin(booked_ids)
        frame["lead_created_at"] = pd.to_datetime(frame["lead_created_at"], utc=True)
        return frame.sort_values("lead_created_at").reset_index(drop=True)

    async def load_booking_cancellation_frame(self) -> pd.DataFrame:
        """One row per booking: at-booking-time features + the ``cancelled`` label."""
        bookings = (
            (
                await self._session.execute(
                    select(
                        BOOKINGS.c.booking_id,
                        BOOKINGS.c.region_name,
                        BOOKINGS.c.vehicle_model_name,
                        BOOKINGS.c.booking_amount_inr,
                        BOOKINGS.c.booking_timestamp,
                        BOOKINGS.c.completed_test_drive,
                        BOOKINGS.c.good_followup,
                        BOOKINGS.c.finance_assisted,
                        BOOKINGS.c.finance_preapproval_signal,
                        BOOKINGS.c.exchange_assisted,
                        BOOKINGS.c.long_test_drive_wait,
                    )
                )
            )
            .mappings()
            .all()
        )
        frame = pd.DataFrame(bookings)
        if frame.empty:
            return frame
        cancelled_ids = set((await self._session.execute(select(CANCELLATIONS.c.booking_id))).scalars().all())
        frame["cancelled"] = frame["booking_id"].isin(cancelled_ids)
        frame["booking_timestamp"] = pd.to_datetime(frame["booking_timestamp"], utc=True)
        return frame.sort_values("booking_timestamp").reset_index(drop=True)

    async def get_cohort_baseline(self, region: str, model: str) -> dict[str, Any]:
        """Real recent baseline for a region/model: lead volume and average deal value.

        ``vehicle_base_price_inr`` is the actual transaction value (real
        XUV700 avg: ~₹24L); ``booking_amount_inr`` is only the refundable
        booking deposit (real avg: ~₹49K across all models) and must never
        be used as the deal size for revenue/margin arithmetic.
        """
        lead_count = (
            await self._session.execute(
                select(func.count()).select_from(LEADS).where(LEADS.c.region_name == region, LEADS.c.vehicle_model_name == model)
            )
        ).scalar_one()
        booking_values = (
            (
                await self._session.execute(
                    select(BOOKINGS.c.vehicle_base_price_inr).where(
                        BOOKINGS.c.region_name == region, BOOKINGS.c.vehicle_model_name == model
                    )
                )
            )
            .scalars()
            .all()
        )
        booking_count = len(booking_values)
        avg_booking_value_inr = float(sum(booking_values) / booking_count) if booking_count else 0.0
        return {
            "lead_count": int(lead_count),
            "booking_count": booking_count,
            "avg_booking_value_inr": avg_booking_value_inr,
        }

    async def load_daily_business_panel(self) -> pd.DataFrame:
        """Whole-business daily aggregates for the Explain Drivers causal-evidence panel."""
        day_lead = func.date(LEADS.c.lead_created_at).label("day")
        leads_daily = (
            (
                await self._session.execute(
                    select(
                        day_lead,
                        func.count().label("lead_count"),
                        func.avg(LEADS.c.engagement_score).label("avg_engagement_score"),
                    ).group_by(day_lead)
                )
            )
            .mappings()
            .all()
        )

        day_fu = func.date(FOLLOWUPS.c.scheduled_at).label("day")
        followups_daily = (
            (
                await self._session.execute(
                    select(
                        day_fu,
                        func.avg(case((FOLLOWUPS.c.completed, 1.0), else_=0.0)).label("followup_completion_rate"),
                    ).group_by(day_fu)
                )
            )
            .mappings()
            .all()
        )

        day_td = func.date(TEST_DRIVES.c.requested_at).label("day")
        test_drives_daily = (
            (
                await self._session.execute(
                    select(
                        day_td,
                        func.avg(case((TEST_DRIVES.c.completed, 1.0), else_=0.0)).label("test_drive_completion_rate"),
                    ).group_by(day_td)
                )
            )
            .mappings()
            .all()
        )

        day_booking = func.date(BOOKINGS.c.booking_timestamp).label("day")
        bookings_daily = (
            (
                await self._session.execute(
                    select(
                        day_booking,
                        func.count().label("booking_count"),
                        func.avg(BOOKINGS.c.vehicle_base_price_inr).label("avg_booking_value_inr"),
                    ).group_by(day_booking)
                )
            )
            .mappings()
            .all()
        )

        day_cancel = func.date(CANCELLATIONS.c.cancelled_at).label("day")
        cancellations_daily = (
            (await self._session.execute(select(day_cancel, func.count().label("cancellation_count")).group_by(day_cancel)))
            .mappings()
            .all()
        )

        frames = [pd.DataFrame(rows) for rows in (leads_daily, followups_daily, test_drives_daily, bookings_daily, cancellations_daily)]
        panel = frames[0]
        for frame in frames[1:]:
            panel = panel.merge(frame, on="day", how="outer")
        panel["day"] = pd.to_datetime(panel["day"], utc=True)
        panel = panel.sort_values("day").reset_index(drop=True)
        panel[["lead_count", "booking_count", "cancellation_count"]] = panel[
            ["lead_count", "booking_count", "cancellation_count"]
        ].fillna(0)
        panel = panel.ffill().bfill()
        return panel
