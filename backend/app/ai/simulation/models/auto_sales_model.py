"""Auto Sales trained models: booking-conversion and cancellation-risk.

Fit once per process on the real leads -> bookings -> cancellations funnel
(a static 7-month synthetic history, not a live stream). Cached in-process;
a scheduled retrain job is future work since nothing in the underlying data
moves between requests today (see
docs/simulation_centre_implementation.md §4.1/§14).

Both models are plain logistic regression (statsmodels — already a
dependency; no new one added) on standardized features, chronologically
split 80/20 so the holdout never precedes training data. Feature lists
are restricted to signals genuinely observable before the outcome; see
``app/repositories/auto_sales.py`` for the leakage exclusions.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pandas as pd

from app.ai.simulation.models.logit import FittedLogit, fit_logit
from app.core.errors import DomainValidationError
from app.repositories.auto_sales import AutoSalesRepository

MIN_TRAINING_ROWS = 50

CONVERSION_FEATURES: list[str] = [
    "budget_fit",
    "engagement_score",
    "urgency_score",
    "model_interest_score",
    "source_quality",
    "completed_test_drive",
    "within_sla_followup",
    "followup_completion_rate",
    "followup_response_rate",
]

# Real conversion rate varies meaningfully by region/model in the data
# (observed range ~13.5%-19.7%) but lead-quality features above don't
# capture that on their own — these go in as dummy variables so the model
# actually reflects each cohort's own historical conversion rate, not just
# the population-wide lead-quality effect.
CONVERSION_CATEGORICAL_FEATURES: list[str] = ["region_name", "vehicle_model_name"]

CANCELLATION_FEATURES: list[str] = [
    "completed_test_drive",
    "good_followup",
    "finance_assisted",
    "finance_preapproval_signal",
    "exchange_assisted",
    "long_test_drive_wait",
]

FRIENDLY_NAMES: dict[str, str] = {
    "budget_fit": "Budget fit",
    "engagement_score": "Lead engagement score",
    "urgency_score": "Purchase urgency score",
    "model_interest_score": "Model interest score",
    "source_quality": "Lead source quality",
    "completed_test_drive": "Completed test drive",
    "within_sla_followup": "Dealer followed up within SLA",
    "followup_completion_rate": "Follow-up completion rate",
    "followup_response_rate": "Customer follow-up response rate",
    "good_followup": "Good dealer follow-up at booking",
    "finance_assisted": "Finance-assisted purchase",
    "finance_preapproval_signal": "Finance pre-approval signal",
    "exchange_assisted": "Exchange-assisted purchase",
    "long_test_drive_wait": "Long test-drive wait",
}

MIN_COHORT_SIZE = 20


@dataclass(frozen=True)
class AutoSalesModels:
    conversion: FittedLogit
    cancellation: FittedLogit
    lead_frame: pd.DataFrame
    booking_frame: pd.DataFrame

    def cohort_conversion_features(self, region: str, model: str) -> tuple[dict[str, float], int]:
        cohort = self.lead_frame[
            (self.lead_frame["region_name"] == region) & (self.lead_frame["vehicle_model_name"] == model)
        ]
        source = cohort if len(cohort) >= MIN_COHORT_SIZE else self.lead_frame
        return {feature: float(source[feature].mean()) for feature in CONVERSION_FEATURES}, len(cohort)

    def cohort_cancellation_features(self, region: str, model: str) -> tuple[dict[str, float], int]:
        cohort = self.booking_frame[
            (self.booking_frame["region_name"] == region) & (self.booking_frame["vehicle_model_name"] == model)
        ]
        source = cohort if len(cohort) >= MIN_COHORT_SIZE else self.booking_frame
        return {feature: float(source[feature].mean()) for feature in CANCELLATION_FEATURES}, len(cohort)


_cache: AutoSalesModels | None = None
_lock = asyncio.Lock()


def reset_cache_for_tests() -> None:
    """Clear the in-process model cache — test isolation only, never called at runtime."""
    global _cache
    _cache = None


async def get_or_train_models(repo: AutoSalesRepository) -> AutoSalesModels:
    global _cache
    if _cache is not None:
        return _cache
    async with _lock:
        if _cache is not None:
            return _cache
        lead_frame = await repo.load_lead_conversion_frame()
        booking_frame = await repo.load_booking_cancellation_frame()
        if len(lead_frame) < MIN_TRAINING_ROWS or "booked" not in lead_frame.columns or lead_frame["booked"].nunique() < 2:
            raise DomainValidationError(
                "Insufficient historical lead data to train the Auto Sales booking-conversion model.",
                code="insufficient_training_data",
            )
        if (
            len(booking_frame) < MIN_TRAINING_ROWS
            or "cancelled" not in booking_frame.columns
            or booking_frame["cancelled"].nunique() < 2
        ):
            raise DomainValidationError(
                "Insufficient historical booking data to train the Auto Sales cancellation-risk model.",
                code="insufficient_training_data",
            )
        conversion = fit_logit(
            lead_frame,
            CONVERSION_FEATURES,
            "booked",
            categorical_features=CONVERSION_CATEGORICAL_FEATURES,
        )
        cancellation = fit_logit(booking_frame, CANCELLATION_FEATURES, "cancelled")
        _cache = AutoSalesModels(
            conversion=conversion,
            cancellation=cancellation,
            lead_frame=lead_frame,
            booking_frame=booking_frame,
        )
        return _cache
