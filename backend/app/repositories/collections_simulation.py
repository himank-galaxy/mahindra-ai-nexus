"""Collections Simulation: repository over real cases/interactions/loans.

Named distinctly from ``app/repositories/collections.py`` (the existing
"Collections AI Swarm" screen's repository, over orphaned
``CollectionsAgent``/``CollectionsCase`` ORM models) to avoid colliding
with an already-wired, unrelated screen.

Unlike Auto Sales' incentive layer or Dealer Allocation's shortage
scenario, Collections has no missing-history gap: every real
``collection_interactions`` row already carries a genuine recorded
outcome (``payment_after_contact``) for a real channel/offer/DPD
combination. Both the channel and offer inputs use the exact real
recorded categories — SMS/WHATSAPP/EMAIL/CALL/FIELD_VISIT and
NONE/PAYMENT_REMINDER/PARTIAL_PAYMENT_PLAN/REPAYMENT_PLAN_DISCUSSION — so
there is no UI-to-real translation layer and every combination trains on
genuine historical outcomes (the previous "Digital" channel grouping and
invented "Waiver" offer are retired for exactly this reason).
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.runtime_schema import runtime_tables

COLLECTION_CASES = runtime_tables["collection_cases"]
COLLECTION_INTERACTIONS = runtime_tables["collection_interactions"]
LOAN_ACCOUNTS = runtime_tables["loan_accounts"]

# Human-readable labels for the real categories — used by the UI and by
# driver/summary text. The wire value sent to/from the API is always the
# exact real category (left column), never the label.
CHANNEL_DISPLAY_NAMES: dict[str, str] = {
    "SMS": "SMS",
    "WHATSAPP": "WhatsApp",
    "EMAIL": "Email",
    "CALL": "Call",
    "FIELD_VISIT": "Field Visit",
}

OFFER_DISPLAY_NAMES: dict[str, str] = {
    "NONE": "None",
    "PAYMENT_REMINDER": "Payment Reminder",
    "PARTIAL_PAYMENT_PLAN": "Partial Payment Plan",
    "REPAYMENT_PLAN_DISCUSSION": "Repayment Plan Discussion",
}

# Real-world DPD bucketing (not a data percentile split): the runtime
# schema's ``dpd_at_case_creation`` is a fixed generator trigger (always
# 15) with no variation, so risk segment is derived from each
# interaction's own ``dpd_at_interaction`` instead, using conventional
# NBFC delinquency bands.
RISK_TO_DPD_RANGE: dict[str, tuple[int, int]] = {
    "Low": (1, 30),
    "Medium": (31, 90),
    "High": (91, 10_000),
}


class CollectionsSimulationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_interaction_frame(self) -> pd.DataFrame:
        """One row per interaction: pre-decision features + the real ``payment_after_contact`` outcome."""
        rows = (
            (
                await self._session.execute(
                    select(
                        COLLECTION_INTERACTIONS.c.dpd_at_interaction,
                        COLLECTION_INTERACTIONS.c.arrears_at_interaction_inr,
                        COLLECTION_INTERACTIONS.c.outstanding_principal_at_interaction_inr,
                        COLLECTION_INTERACTIONS.c.channel,
                        COLLECTION_INTERACTIONS.c.offer_type,
                        COLLECTION_INTERACTIONS.c.field_visit_flag,
                        COLLECTION_INTERACTIONS.c.payment_after_contact,
                        COLLECTION_INTERACTIONS.c.interaction_at,
                    )
                )
            )
            .mappings()
            .all()
        )
        frame = pd.DataFrame(rows)
        if frame.empty:
            return frame
        frame["interaction_at"] = pd.to_datetime(frame["interaction_at"], utc=True)
        return frame.sort_values("interaction_at").reset_index(drop=True)

    async def load_case_resolution_frame(self) -> pd.DataFrame:
        """One row per case: loan-origination features + whether it resolved (inverse: roll-forward risk)."""
        rows = (
            (
                await self._session.execute(
                    select(
                        COLLECTION_CASES.c.collection_case_id,
                        COLLECTION_CASES.c.loan_account_id,
                        COLLECTION_CASES.c.case_status,
                        COLLECTION_CASES.c.current_dpd,
                        COLLECTION_CASES.c.case_created_at,
                    )
                )
            )
            .mappings()
            .all()
        )
        cases = pd.DataFrame(rows)
        if cases.empty:
            return cases

        loans = (
            (
                await self._session.execute(
                    select(
                        LOAN_ACCOUNTS.c.loan_account_id,
                        LOAN_ACCOUNTS.c.principal_inr,
                        LOAN_ACCOUNTS.c.interest_rate_pct,
                        LOAN_ACCOUNTS.c.debt_service_ratio_at_origination,
                        LOAN_ACCOUNTS.c.secured,
                    )
                )
            )
            .mappings()
            .all()
        )
        loan_frame = pd.DataFrame(loans)

        frame = cases.merge(loan_frame, on="loan_account_id", how="inner")
        frame["resolved"] = frame["case_status"] == "RESOLVED"
        frame["case_created_at"] = pd.to_datetime(frame["case_created_at"], utc=True)
        return frame.sort_values("case_created_at").reset_index(drop=True)

    async def get_cohort_stats(self, risk: str) -> dict[str, float | int]:
        """Real average arrears/outstanding/case count for a risk segment's DPD band."""
        low, high = RISK_TO_DPD_RANGE[risk]
        rows = (
            (
                await self._session.execute(
                    select(
                        COLLECTION_INTERACTIONS.c.arrears_at_interaction_inr,
                        COLLECTION_INTERACTIONS.c.outstanding_principal_at_interaction_inr,
                    ).where(
                        COLLECTION_INTERACTIONS.c.dpd_at_interaction >= low,
                        COLLECTION_INTERACTIONS.c.dpd_at_interaction <= high,
                    )
                )
            )
            .mappings()
            .all()
        )
        frame = pd.DataFrame(rows)
        count = len(frame)
        return {
            "interaction_count": count,
            "avg_arrears_inr": float(frame["arrears_at_interaction_inr"].mean()) if count else 0.0,
            "avg_outstanding_inr": float(frame["outstanding_principal_at_interaction_inr"].mean()) if count else 0.0,
        }
