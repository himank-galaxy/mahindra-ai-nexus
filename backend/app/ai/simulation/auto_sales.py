"""Auto Sales Simulation engine — Phase 2: real data, real models.

Two layers, kept deliberately distinct (see
docs/simulation_centre_implementation.md §4.1):

1. Booking-conversion and cancellation-risk baselines come from calibrated
   logistic regressions trained on the real leads -> bookings ->
   cancellations funnel (``app/ai/simulation/models/auto_sales_model.py``).
   This is genuine ``trained_model`` evidence.
2. The incentive-response layer (how discount/bonus/campaign spend shift
   that baseline) is a documented, reviewable calibrated function, NOT a
   fit on observed variation — the runtime schema has no historical
   discount/bonus/campaign column to fit one against. Every coefficient
   below is a business assumption, not a discovered pattern, and the
   engine's overall ``confidence_basis`` stays ``calibrated_heuristic``
   because the headline number (uplift) flows through this layer.

Revenue/margin arithmetic uses the cohort's real historical lead volume
and average booking value — never an invented multiplier.
"""

from __future__ import annotations

import math
from typing import Any

from app.ai.simulation.confidence import calibrated_heuristic_confidence
from app.ai.simulation.models.auto_sales_model import FRIENDLY_NAMES, get_or_train_models
from app.ai.utils import format_inr, js_round
from app.repositories.auto_sales import AutoSalesRepository
from app.schemas.simulation import AutoSalesSimIn

MODEL_NAME = "auto_sales.logit_conversion_cancellation_v1"
MODEL_VERSION = "phase2.0"

# --- Calibrated incentive-response assumptions --------------------------
# No historical discount/bonus/campaign variation exists in the runtime
# schema to fit these against (see module docstring). Each constant is a
# documented, reviewable business assumption.
DISCOUNT_ELASTICITY = 0.05  # +5% relative conversion lift per discount point
BONUS_ELASTICITY_REF_INR = 50_000  # bonus scale at which the lift saturates
BONUS_ELASTICITY_CAP = 0.35  # max relative conversion lift attributable to bonus alone
CAMPAIGN_ELASTICITY = 0.06  # +6% relative conversion lift per ₹1 Cr of campaign spend
INTENSITY_MULTIPLIER = {"Low": 0.85, "Medium": 1.0, "High": 1.15}
CANCELLATION_BONUS_RELIEF_REF_INR = 40_000
CANCELLATION_BONUS_RELIEF_CAP = 0.15
CANCELLATION_INTENSITY_RELIEF = {"Low": 0.0, "Medium": 0.10, "High": 0.20}
CANCELLATION_RELIEF_CAP = 0.6  # incentives can't erase cancellation risk entirely


def _incentive_terms(payload: AutoSalesSimIn) -> tuple[float, float, float]:
    discount_term = DISCOUNT_ELASTICITY * payload.discount
    bonus_term = BONUS_ELASTICITY_CAP * math.tanh(payload.bonus / BONUS_ELASTICITY_REF_INR)
    campaign_term = CAMPAIGN_ELASTICITY * payload.campaign
    return discount_term, bonus_term, campaign_term


def _cancellation_relief(payload: AutoSalesSimIn) -> float:
    bonus_relief = CANCELLATION_BONUS_RELIEF_CAP * math.tanh(payload.bonus / CANCELLATION_BONUS_RELIEF_REF_INR)
    intensity_relief = CANCELLATION_INTENSITY_RELIEF.get(payload.intensity, 0.0)
    return min(CANCELLATION_RELIEF_CAP, bonus_relief + intensity_relief)


async def run(payload: AutoSalesSimIn, repo: AutoSalesRepository) -> dict[str, Any]:
    models = await get_or_train_models(repo)
    baseline_stats = await repo.get_cohort_baseline(payload.region, payload.model)

    conversion_features, conversion_cohort_size = models.cohort_conversion_features(payload.region, payload.model)
    cancellation_features, cancellation_cohort_size = models.cohort_cancellation_features(payload.region, payload.model)

    baseline_conversion_prob = models.conversion.predict_proba(
        conversion_features,
        {"region_name": payload.region, "vehicle_model_name": payload.model},
    )
    baseline_cancellation_prob = models.cancellation.predict_proba(cancellation_features)

    discount_term, bonus_term, campaign_term = _incentive_terms(payload)
    intensity_multiplier = INTENSITY_MULTIPLIER.get(payload.intensity, 1.0)
    relative_uplift = (discount_term + bonus_term + campaign_term) * intensity_multiplier
    scenario_conversion_prob = min(0.95, baseline_conversion_prob * (1 + relative_uplift))

    cancellation_relief = _cancellation_relief(payload)
    scenario_cancellation_prob = baseline_cancellation_prob * (1 - cancellation_relief)

    cohort_lead_count = baseline_stats["lead_count"]
    avg_booking_value_inr = baseline_stats["avg_booking_value_inr"] or 0.0

    expected_baseline_bookings = cohort_lead_count * baseline_conversion_prob
    expected_scenario_bookings = cohort_lead_count * scenario_conversion_prob
    incremental_bookings = expected_scenario_bookings - expected_baseline_bookings

    gross_incremental_revenue_inr = incremental_bookings * avg_booking_value_inr
    discount_cost_inr = expected_scenario_bookings * avg_booking_value_inr * (payload.discount / 100)
    bonus_cost_inr = expected_scenario_bookings * payload.bonus
    campaign_cost_inr = payload.campaign * 1e7  # ₹ Cr -> INR
    net_revenue_impact_inr = gross_incremental_revenue_inr - discount_cost_inr - bonus_cost_inr - campaign_cost_inr

    # Percentage-point delta in predicted booking probability for THIS cohort
    # (not the bare relative-uplift formula, which only reads the incentive
    # sliders and would otherwise show the same number for every
    # region/model) — consistent with `incremental_bookings` below, which
    # already scales this same delta by the cohort's real lead volume.
    uplift_pct = js_round((scenario_conversion_prob - baseline_conversion_prob) * 100)
    margin_cost_pct = payload.discount + (
        js_round(payload.bonus / avg_booking_value_inr * 100) if avg_booking_value_inr else 0
    )
    cancel_pct = js_round(scenario_cancellation_prob * 100)
    rev_cr = js_round(net_revenue_impact_inr / 1e7)

    cohort_size = min(conversion_cohort_size, cancellation_cohort_size)
    confidence_base = 40 + js_round(20 * max(0.0, (models.conversion.holdout_auc - 0.5) * 2) + 10 * min(1.0, cohort_size / 200))
    confidence, confidence_band = calibrated_heuristic_confidence(base=confidence_base)

    deploy = net_revenue_impact_inr > 0 and scenario_cancellation_prob <= baseline_cancellation_prob * 1.1
    action = "Deploy" if deploy else "Deploy with monitoring" if net_revenue_impact_inr > 0 else "Hold — projected net revenue impact is negative"
    recommended_action = (
        f"{action}: exchange bonus {format_inr(payload.bonus)} in {payload.region} for {payload.model} "
        f"with {payload.intensity.lower()} follow-up — projected net revenue impact ₹{rev_cr} Cr on "
        f"~{max(0, round(incremental_bookings))} incremental bookings (cohort: {cohort_lead_count} leads observed)."
    )

    conversion_auc = models.conversion.holdout_auc
    predictive_drivers = [
        {
            "name": FRIENDLY_NAMES.get(feature, feature),
            "direction": direction,
            "contribution": round(coefficient, 3),
            "source": "trained_model",
            "detail": (
                f"Standardized effect on predicted booking probability "
                f"(conversion model holdout AUC {conversion_auc:.2f})."
            ),
        }
        for feature, coefficient, direction in models.conversion.numeric_drivers()[:3]
    ]
    # Only the SELECTED region/model's own effect — never another region's
    # or model's coefficient, which would misattribute the effect to a
    # cohort this run didn't choose (see FittedLogit.categorical_coefficient).
    for feature_name, value, label in (
        ("region_name", payload.region, f"Region: {payload.region}"),
        ("vehicle_model_name", payload.model, f"Vehicle model: {payload.model}"),
    ):
        coefficient = models.conversion.categorical_coefficient(feature_name, value)
        if coefficient is None:
            predictive_drivers.append(
                {
                    "name": label,
                    "direction": "positive",
                    "contribution": 0.0,
                    "source": "trained_model",
                    "detail": "Reference cohort for this effect — no separate contrast estimated against itself.",
                }
            )
        else:
            predictive_drivers.append(
                {
                    "name": label,
                    "direction": "positive" if coefficient >= 0 else "negative",
                    "contribution": round(coefficient, 3),
                    "source": "trained_model",
                    "detail": (
                        f"This cohort's own historical conversion rate vs. the reference cohort "
                        f"(conversion model holdout AUC {conversion_auc:.2f})."
                    ),
                }
            )
    predictive_drivers.extend(
        [
            {
                "name": "Discount %",
                "direction": "positive" if discount_term >= 0 else "negative",
                "contribution": round(discount_term, 3),
                "source": "calibrated_heuristic",
                "detail": f"Assumed +{DISCOUNT_ELASTICITY:.0%} relative conversion lift per discount point.",
            },
            {
                "name": "Exchange bonus",
                "direction": "positive" if bonus_term >= 0 else "negative",
                "contribution": round(bonus_term, 3),
                "source": "calibrated_heuristic",
                "detail": f"Assumed diminishing-returns lift saturating near {format_inr(BONUS_ELASTICITY_REF_INR)}.",
            },
            {
                "name": "Campaign spend",
                "direction": "positive" if campaign_term >= 0 else "negative",
                "contribution": round(campaign_term, 3),
                "source": "calibrated_heuristic",
                "detail": f"Assumed +{CAMPAIGN_ELASTICITY:.0%} relative conversion lift per ₹1 Cr spent.",
            },
        ]
    )

    return {
        "uplift": uplift_pct,
        "margin": -margin_cost_pct,
        "cancel": max(0, cancel_pct),
        "rev": rev_cr,
        "conf": confidence,
        "confidence_band": confidence_band,
        "confidence_basis": "calibrated_heuristic",
        "recommendedAction": recommended_action,
        "_baseline_reference": {
            "baseline_conversion_probability": round(baseline_conversion_prob, 4),
            "baseline_cancellation_probability": round(baseline_cancellation_prob, 4),
            "cohort_lead_count": cohort_lead_count,
            "cohort_booking_count": baseline_stats["booking_count"],
            "avg_booking_value_inr": round(avg_booking_value_inr, 2),
        },
        "_recommendation": {
            "action": action,
            "net_revenue_impact_inr": round(net_revenue_impact_inr, 2),
            "incremental_bookings": round(incremental_bookings, 2),
        },
        "_predictive_drivers": predictive_drivers,
    }
