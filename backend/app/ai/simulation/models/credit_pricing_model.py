"""Credit Pricing trained models: ask-price regression + buyer-interest regression.

``credit_listings.listing_status`` is constant ``OPEN`` for every real
listing (see app/repositories/credit_pricing_simulation.py) — there is no
recorded closed/not-closed outcome anywhere in the runtime schema, so a
trained closure-probability classifier is not honestly possible. Two
OTHER continuous outcomes DO have real historical variation and support
genuine OLS regressions (reusing the mixed numeric+categorical fitting in
app/ai/simulation/models/regression.py): ``seller_ask_price_per_tco2e_inr``
(price prediction) and ``buyer_inquiry_count`` (buyer interest/"match"),
both against real listing/assessment attributes. Trade-closure
probability itself stays a documented calibrated function — see
app/ai/simulation/credit_pricing.py.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pandas as pd

from app.ai.simulation.models.regression import FittedOLS, fit_ols
from app.core.errors import DomainValidationError
from app.repositories.credit_pricing_simulation import CreditPricingSimulationRepository

MIN_TRAINING_ROWS = 50
MIN_COHORT_SIZE = 20

PRICE_NUMERIC_FEATURES: list[str] = [
    "market_reference_price_per_tco2e_inr",
    "buyer_bid_count",
    "dmrv_completeness_ratio",
    "traceability_score",
]
INTEREST_NUMERIC_FEATURES: list[str] = [
    "market_reference_price_per_tco2e_inr",
    "traceability_score",
    "buyer_demand_index",
    "document_completeness",
]
CATEGORICAL_FEATURES: list[str] = ["credit_type"]

FRIENDLY_NAMES: dict[str, str] = {
    "market_reference_price_per_tco2e_inr": "Market reference price",
    "buyer_bid_count": "Buyer bid count",
    "dmrv_completeness_ratio": "dMRV evidence completeness",
    "traceability_score": "Traceability score",
    "buyer_demand_index": "Buyer demand index",
    "document_completeness": "Document completeness",
}

_COHORT_FEATURES = sorted(set(PRICE_NUMERIC_FEATURES) | set(INTEREST_NUMERIC_FEATURES) | {"dmrv_missing_records"})


@dataclass(frozen=True)
class CreditPricingModels:
    price: FittedOLS
    buyer_interest: FittedOLS
    frame: pd.DataFrame

    def cohort_features(self, credit_type: str) -> tuple[dict[str, float], int]:
        cohort = self.frame[self.frame["credit_type"] == credit_type]
        source = cohort if len(cohort) >= MIN_COHORT_SIZE else self.frame
        return {feature: float(source[feature].mean()) for feature in _COHORT_FEATURES}, len(cohort)

    def feature_bounds(self, feature: str) -> tuple[float, float]:
        return float(self.frame[feature].min()), float(self.frame[feature].max())

    def max_observed_inquiries(self) -> float:
        return float(self.frame["buyer_inquiry_count"].max()) or 1.0


_cache: CreditPricingModels | None = None
_lock = asyncio.Lock()


def reset_cache_for_tests() -> None:
    """Clear the in-process model cache — test isolation only, never called at runtime."""
    global _cache
    _cache = None


async def get_or_train_models(repo: CreditPricingSimulationRepository) -> CreditPricingModels:
    global _cache
    if _cache is not None:
        return _cache
    async with _lock:
        if _cache is not None:
            return _cache
        frame = await repo.load_listing_frame()
        if len(frame) < MIN_TRAINING_ROWS:
            raise DomainValidationError(
                "Insufficient historical listing data to train the Credit Pricing models.",
                code="insufficient_training_data",
            )
        price = fit_ols(
            frame,
            PRICE_NUMERIC_FEATURES,
            "seller_ask_price_per_tco2e_inr",
            categorical_features=CATEGORICAL_FEATURES,
        )
        buyer_interest = fit_ols(
            frame,
            INTEREST_NUMERIC_FEATURES,
            "buyer_inquiry_count",
            categorical_features=CATEGORICAL_FEATURES,
        )
        _cache = CreditPricingModels(price=price, buyer_interest=buyer_interest, frame=frame)
        return _cache
