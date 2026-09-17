"""Circularity Credit Pricing Simulation engine — Phase 6: real regressions + calibrated closure sweep.

Ask-price and buyer-interest come from two OLS regressions trained on
real historical listing/assessment data (see
app/ai/simulation/models/credit_pricing_model.py) — never a formula.
Credit type is the exact real recorded category
(``MIXED_CIRCULARITY``/``RECYCLING_AVOIDANCE``/``REUSE_AVOIDANCE``),
replacing the retired invented "Carbon/EPR/SDG/CD" abstraction.

``credit_listings.listing_status`` is ``OPEN`` for every real listing
(see the repository docstring) — there is no recorded closed/not-closed
outcome anywhere in the runtime schema, so trade-closure probability
stays a documented calibrated function of (ask price vs. market
reference) x (demand/supply pressure) x (traceability + dMRV evidence
completeness), never presented as a trained classifier.
``confidence_basis`` for the whole run is therefore ``calibrated_heuristic``
— the same treatment Dealer Allocation gives its CSAT/waiting-period
layer on top of a real optimizer.

The recommended price is a genuine small search: sweep candidate prices
across the price regression's own residual-spread band and recommend
whichever maximizes ``price x closure_probability(price)`` (expected
marketplace value) — never simply the highest price the band allows.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.ai.simulation.confidence import calibrated_heuristic_confidence
from app.ai.simulation.models.credit_pricing_model import FRIENDLY_NAMES, get_or_train_models
from app.ai.utils import js_round
from app.repositories.credit_pricing_simulation import CREDIT_TYPE_DISPLAY_NAMES, CreditPricingSimulationRepository
from app.schemas.simulation import CreditPricingSimIn

MODEL_NAME = "credit_pricing.ols_price_buyer_interest_v1"
MODEL_VERSION = "phase6.0"

PRICE_SWEEP_POINTS = 25


def _closure_probability(
    candidate_price: float,
    market_reference_price: float,
    demand_pct: float,
    supply_pct: float,
    quality_factor: float,
) -> float:
    """Documented monotonic calibration — not fit on data (see module
    docstring): asking further above market reference lowers closure
    chance, stronger buyer demand relative to supply raises it, and
    higher traceability/dMRV completeness raises it. Bounded to a
    plausible 3-92% range, never 0% or 100%."""
    price_ratio = candidate_price / market_reference_price if market_reference_price else 1.0
    price_factor = max(0.15, min(1.2, 1.35 - 0.7 * price_ratio))
    demand_supply_ratio = demand_pct / max(supply_pct, 0.15)
    demand_factor = max(0.3, min(1.5, demand_supply_ratio))
    return max(0.03, min(0.92, 0.55 * price_factor * demand_factor * (0.5 + 0.5 * quality_factor)))


async def run(payload: CreditPricingSimIn, repo: CreditPricingSimulationRepository) -> dict[str, Any]:
    models = await get_or_train_models(repo)
    cohort_features, cohort_size = models.cohort_features(payload.credit_type)
    cohort_stats = await repo.get_cohort_stats(payload.credit_type)

    demand_low, demand_high = models.feature_bounds("buyer_demand_index")
    trace_low, trace_high = models.feature_bounds("traceability_score")
    dmrv_low, dmrv_high = models.feature_bounds("dmrv_completeness_ratio")
    demand_value = min(demand_high, max(demand_low, payload.demand / 100))
    trace_value = min(trace_high, max(trace_low, payload.trace / 100))
    dmrv_value = min(dmrv_high, max(dmrv_low, payload.verif / 100))
    in_training_range = (
        demand_low <= payload.demand / 100 <= demand_high
        and trace_low <= payload.trace / 100 <= trace_high
        and dmrv_low <= payload.verif / 100 <= dmrv_high
    )

    features = {
        **cohort_features,
        "buyer_demand_index": demand_value,
        "traceability_score": trace_value,
        "dmrv_completeness_ratio": dmrv_value,
    }
    categorical = {"credit_type": payload.credit_type}

    predicted_price = models.price.predict(features, categorical)
    band_half_width = models.price.holdout_rmse or predicted_price * 0.05
    price_band_low = max(1.0, predicted_price - band_half_width)
    price_band_high = predicted_price + band_half_width

    predicted_inquiries = max(0.0, models.buyer_interest.predict(features, categorical))
    match_pct = min(100.0, predicted_inquiries / models.max_observed_inquiries() * 100)

    market_reference_price = cohort_features["market_reference_price_per_tco2e_inr"]
    quality_factor = (trace_value + dmrv_value) / 2

    # Pricing optimizer: sweep the regression's own residual-spread band
    # and recommend whichever price maximizes expected marketplace value
    # (price x closure probability), never simply the top of the band.
    candidates = np.linspace(price_band_low, price_band_high, PRICE_SWEEP_POINTS)
    closures = [
        _closure_probability(price, market_reference_price, payload.demand, payload.supply, quality_factor)
        for price in candidates
    ]
    expected_values = [price * closure for price, closure in zip(candidates, closures, strict=True)]
    best_index = int(np.argmax(expected_values))
    recommended_price = float(candidates[best_index])
    closure_probability = closures[best_index]

    if cohort_stats["avg_dmrv_missing_records"] > 1.0 or dmrv_value < 0.6:
        compliance_risk = "High"
    elif cohort_stats["avg_dmrv_missing_records"] > 0.4 or dmrv_value < 0.85:
        compliance_risk = "Medium"
    else:
        compliance_risk = "Low"

    confidence_base = 40 + min(15, cohort_size // 5) + (10 if in_training_range else -10)
    confidence, confidence_band = calibrated_heuristic_confidence(base=confidence_base)

    credit_type_label = CREDIT_TYPE_DISPLAY_NAMES[payload.credit_type]
    direction = "above" if recommended_price > market_reference_price else "below"
    recommended_action = (
        f"List at ₹{js_round(recommended_price)}/tCO2e ({direction} the ₹{js_round(market_reference_price)} "
        f"market reference) — projected {js_round(closure_probability * 100)}% closure probability, expected "
        f"value ₹{js_round(recommended_price * closure_probability)}/tCO2e ({cohort_size} {credit_type_label} "
        f"listings observed)."
    )

    predictive_drivers: list[dict[str, Any]] = [
        {
            "name": FRIENDLY_NAMES.get(feature, feature),
            "direction": direction_,
            "contribution": round(coefficient, 3),
            "source": "trained_model",
            "detail": f"Standardized effect on predicted ask price (price model holdout R² {models.price.holdout_r2:.2f}).",
        }
        for feature, coefficient, direction_ in models.price.numeric_drivers()[:2]
    ]
    credit_type_coef = models.price.categorical_coefficient("credit_type", payload.credit_type)
    predictive_drivers.append(
        {
            "name": f"Credit type: {credit_type_label}",
            "direction": "positive" if (credit_type_coef or 0) >= 0 else "negative",
            "contribution": round(credit_type_coef, 3) if credit_type_coef is not None else 0.0,
            "source": "trained_model",
            "detail": (
                "This credit type's own historical ask-price effect vs. the reference type."
                if credit_type_coef is not None
                else "Reference credit type for this effect — no separate contrast estimated against itself."
            ),
        }
    )
    predictive_drivers.append(
        {
            "name": "Trade-closure probability",
            "direction": "positive",
            "contribution": round(closure_probability, 3),
            "source": "calibrated_heuristic",
            "detail": (
                "Documented monotonic function of price-vs-market-reference, demand/supply pressure, and "
                "traceability+dMRV completeness — not fit on a real closed/not-closed outcome (listing_status "
                "is OPEN for every real listing)."
            ),
        }
    )

    return {
        "priceBandLow": js_round(price_band_low),
        "priceBandHigh": js_round(price_band_high),
        "closure": js_round(closure_probability * 100),
        "match": js_round(match_pct),
        "complianceRisk": compliance_risk,
        "conf": confidence,
        "confidence_band": confidence_band,
        "confidence_basis": "calibrated_heuristic",
        "recommendedAction": recommended_action,
        "_baseline_reference": {
            "cohort_listing_count": cohort_size,
            "avg_market_reference_price_inr": round(cohort_stats["avg_market_reference_price_inr"], 2),
            "avg_seller_ask_price_inr": round(cohort_stats["avg_seller_ask_price_inr"], 2),
            "avg_dmrv_missing_records": round(cohort_stats["avg_dmrv_missing_records"], 2),
        },
        "_recommendation": {
            "credit_type": payload.credit_type,
            "recommended_price_inr": round(recommended_price, 2),
            "closure_probability": round(closure_probability, 4),
        },
        "_predictive_drivers": predictive_drivers,
    }
