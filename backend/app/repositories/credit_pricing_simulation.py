"""Circularity Credit Pricing Simulation: repository over real credit_listings/elv_assessments.

Named distinctly from ``app/repositories/circularity.py`` (an existing,
unrelated dashboard-panel repository over static seed data —
``CarbonCredit``/``WarehouseSignal`` ORM models) to avoid colliding with
an already-wired screen.

``credit_listings.listing_status`` is ``OPEN`` for all 750 real rows —
there is no recorded closed/not-closed outcome anywhere in the runtime
schema, so a trained closure-probability classifier is not honestly
possible from this data (see
docs/simulation_centre_implementation.md §4.5). ``credit_listings`` and
``elv_assessments`` are 1:1 on ``elv_assessment_id``; the dMRV
completeness counts (``dmrv_available_records``/``dmrv_expected_records``/
``dmrv_missing_records``) are already denormalized onto ``credit_listings``
itself, so no separate join to ``dmrv_records`` is needed for this
domain.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.runtime_schema import runtime_tables

CREDIT_LISTINGS = runtime_tables["credit_listings"]
ELV_ASSESSMENTS = runtime_tables["elv_assessments"]

# Real recorded categories on `credit_listings.credit_type` — the wire
# value sent to/from the API is always the exact real category (left
# column), never the label, matching the Collections channel/offer and
# Logistics Delay priority precedents. Replaces the retired invented
# "Carbon/EPR/SDG/CD" abstraction, which had no real database counterpart.
CREDIT_TYPE_DISPLAY_NAMES: dict[str, str] = {
    "MIXED_CIRCULARITY": "Mixed Circularity",
    "RECYCLING_AVOIDANCE": "Recycling Avoidance",
    "REUSE_AVOIDANCE": "Reuse Avoidance",
}


class CreditPricingSimulationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_listing_frame(self) -> pd.DataFrame:
        """One row per listing: real market/price/buyer-interest/dMRV
        completeness features plus the credit type category."""
        rows = (
            (
                await self._session.execute(
                    select(
                        CREDIT_LISTINGS.c.carbon_credit_listing_id,
                        CREDIT_LISTINGS.c.credit_type,
                        CREDIT_LISTINGS.c.listing_at,
                        CREDIT_LISTINGS.c.market_reference_price_per_tco2e_inr,
                        CREDIT_LISTINGS.c.seller_ask_price_per_tco2e_inr,
                        CREDIT_LISTINGS.c.buyer_inquiry_count,
                        CREDIT_LISTINGS.c.buyer_bid_count,
                        CREDIT_LISTINGS.c.dmrv_available_records,
                        CREDIT_LISTINGS.c.dmrv_expected_records,
                        CREDIT_LISTINGS.c.dmrv_missing_records,
                        ELV_ASSESSMENTS.c.traceability_score,
                        ELV_ASSESSMENTS.c.document_completeness,
                        ELV_ASSESSMENTS.c.buyer_demand_index,
                    ).select_from(
                        CREDIT_LISTINGS.join(
                            ELV_ASSESSMENTS,
                            CREDIT_LISTINGS.c.elv_assessment_id == ELV_ASSESSMENTS.c.elv_assessment_id,
                        )
                    )
                )
            )
            .mappings()
            .all()
        )
        frame = pd.DataFrame(rows)
        if frame.empty:
            return frame

        for column in (
            "market_reference_price_per_tco2e_inr",
            "seller_ask_price_per_tco2e_inr",
            "buyer_inquiry_count",
            "buyer_bid_count",
            "dmrv_available_records",
            "dmrv_expected_records",
            "dmrv_missing_records",
            "traceability_score",
            "document_completeness",
            "buyer_demand_index",
        ):
            frame[column] = frame[column].astype(float)
        frame["dmrv_completeness_ratio"] = frame["dmrv_available_records"] / frame["dmrv_expected_records"].replace(
            0, 1.0
        )
        frame["listing_at"] = pd.to_datetime(frame["listing_at"], utc=True)
        return frame.sort_values("listing_at").reset_index(drop=True)

    async def get_cohort_stats(self, credit_type: str) -> dict[str, float | int]:
        """Real average price/dMRV stats for one credit-type cohort."""
        rows = (
            (
                await self._session.execute(
                    select(
                        CREDIT_LISTINGS.c.market_reference_price_per_tco2e_inr,
                        CREDIT_LISTINGS.c.seller_ask_price_per_tco2e_inr,
                        CREDIT_LISTINGS.c.dmrv_missing_records,
                    ).where(CREDIT_LISTINGS.c.credit_type == credit_type)
                )
            )
            .mappings()
            .all()
        )
        frame = pd.DataFrame(rows)
        count = len(frame)
        return {
            "listing_count": count,
            "avg_market_reference_price_inr": float(frame["market_reference_price_per_tco2e_inr"].mean()) if count else 0.0,
            "avg_seller_ask_price_inr": float(frame["seller_ask_price_per_tco2e_inr"].mean()) if count else 0.0,
            "avg_dmrv_missing_records": float(frame["dmrv_missing_records"].mean()) if count else 0.0,
        }
