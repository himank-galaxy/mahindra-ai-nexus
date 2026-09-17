"""Logistics Delay Simulation engine — Phase 5: real trained models + reroute sweep.

Any-delay and SLA-breach probability come from two logistic regressions
trained on the real ``shipments`` history (see
app/ai/simulation/models/logistics_delay_model.py) — never a formula.
Route and priority are the exact real recorded categories (``route_id``,
``LOW``/``NORMAL``/``HIGH``/``CRITICAL``), so this domain has no
UI-to-real translation layer and ``confidence_basis`` is always
``trained_model``.

There is no real per-minute delay-cost or per-breach-penalty field in the
runtime schema, so translating predicted delay/breach probability into a
rupee cost impact stays a documented calibrated assumption — the one part
of this engine that isn't fit on data (same shape as Collections'
per-channel cost table).

The reroute recommendation is a genuine strategy sweep: the SAME trained
models are re-evaluated with ``route_id`` swapped for every real
alternative route on the same origin-region → destination-region pair
(holding the scenario's weather/vehicle/warehouse inputs fixed), and
whichever route minimizes expected cost (real route cost + calibrated
delay/breach penalty) is recommended — never simply the lowest
``baseline_risk_score``.

``weather_disruption``/``vehicle_breakdown`` are rare real boolean flags
(~6%/~3% of shipments) with large fitted effects. Feeding a slider's
fractional value directly into the standardized coefficient would
linearly extrapolate a rare-event effect far outside anything the model
was fit on and saturates at implausible near-0%/near-100% predictions for
ordinary slider positions. Instead, each slider is treated as "the
probability this disruption occurs on the trip," and the expected outcome
is the law-of-total-probability mixture of the model's own four genuine
0/1 predictions — bounded by what the model actually learned, never an
extrapolation past it.
"""

from __future__ import annotations

from typing import Any

from app.ai.simulation.confidence import trained_model_confidence
from app.ai.simulation.models.logit import FittedLogit
from app.ai.simulation.models.logistics_delay_model import FRIENDLY_NAMES, LogisticsDelayModels, get_or_train_models
from app.ai.utils import js_round
from app.core.errors import DomainValidationError
from app.repositories.logistics_delay_simulation import PRIORITY_DISPLAY_NAMES, LogisticsDelaySimulationRepository
from app.schemas.simulation import LogisticsDelaySimIn

MODEL_NAME = "logistics_delay.logit_any_delay_breach_v1"
MODEL_VERSION = "phase5.0"

# Calibrated — no real per-minute delay-cost or per-breach-penalty field
# exists in the runtime schema. The delay cost approximates detention/
# holding cost; the breach penalty approximates the customer-SLA/
# reputational cost of an actual breach (same documented-assumption shape
# as Collections' COST_BY_CHANNEL_INR / Dealer Allocation's CSAT
# calibration).
COST_PER_DELAY_HOUR_INR = 1_400
SLA_BREACH_PENALTY_INR = 30_000


def _mixture_probability(
    model: FittedLogit,
    features: dict[str, float],
    route_id: str,
    priority: str,
    weather_p: float,
    vehicle_p: float,
) -> float:
    """Expected probability under the law of total probability over
    whether a weather disruption / vehicle breakdown actually occurs —
    see the module docstring for why this replaces a raw continuous
    extrapolation of the rare-event coefficients."""
    categorical = {"route_id": route_id, "priority": priority}
    p00 = model.predict_proba({**features, "weather_disruption": 0.0, "vehicle_breakdown": 0.0}, categorical)
    p10 = model.predict_proba({**features, "weather_disruption": 1.0, "vehicle_breakdown": 0.0}, categorical)
    p01 = model.predict_proba({**features, "weather_disruption": 0.0, "vehicle_breakdown": 1.0}, categorical)
    p11 = model.predict_proba({**features, "weather_disruption": 1.0, "vehicle_breakdown": 1.0}, categorical)
    return (
        p00 * (1 - weather_p) * (1 - vehicle_p)
        + p10 * weather_p * (1 - vehicle_p)
        + p01 * (1 - weather_p) * vehicle_p
        + p11 * weather_p * vehicle_p
    )


def _route_outcome(
    models: LogisticsDelayModels,
    route: dict,
    features: dict[str, float],
    priority: str,
    weather_p: float,
    vehicle_p: float,
) -> tuple[float, float, float]:
    """``(expected_cost_inr, delay_probability, breach_probability)`` for one candidate route."""
    delay_prob = _mixture_probability(models.any_delay, features, route["route_id"], priority, weather_p, vehicle_p)
    breach_prob = _mixture_probability(models.breach, features, route["route_id"], priority, weather_p, vehicle_p)
    expected_delay_minutes = delay_prob * models.mean_delay_minutes_when_delayed(route["route_id"])
    cost = (
        route["baseline_cost_inr"]
        + (expected_delay_minutes / 60) * COST_PER_DELAY_HOUR_INR
        + breach_prob * SLA_BREACH_PENALTY_INR
    )
    return cost, delay_prob, breach_prob


async def run(payload: LogisticsDelaySimIn, repo: LogisticsDelaySimulationRepository) -> dict[str, Any]:
    models = await get_or_train_models(repo)
    route = await repo.get_route(payload.route)
    if route is None:
        raise DomainValidationError(f"Unknown route '{payload.route}'.", code="unknown_route")

    base_features, route_cohort_size = models.route_cohort_features(payload.route)
    low, high = models.warehouse_utilization_bounds()
    requested_utilization = payload.warehouse / 100
    in_training_range = low <= requested_utilization <= high
    features = {**base_features, "warehouse_utilization_pct": min(high, max(low, requested_utilization))}
    weather_p = payload.weather / 100
    vehicle_p = (100 - payload.vehicle) / 100

    cost, delay_prob, breach_prob = _route_outcome(models, route, features, payload.sla, weather_p, vehicle_p)

    confidence, confidence_band = trained_model_confidence(
        predicted_probability=breach_prob,
        in_training_range=in_training_range,
        cohort_sample_size=route_cohort_size,
    )

    # Reroute optimizer: sweep every real alternative route on the same
    # region-pair corridor, holding the scenario's inputs fixed, and pick
    # whichever minimizes expected cost — never simply the highest
    # breach/delay probability alone.
    alternatives = await repo.get_route_alternatives(payload.route)
    best_route, best_cost = route, cost
    for candidate in alternatives:
        candidate_base, _ = models.route_cohort_features(candidate["route_id"])
        candidate_features = {**candidate_base, "warehouse_utilization_pct": features["warehouse_utilization_pct"]}
        candidate_cost, _, _ = _route_outcome(models, candidate, candidate_features, payload.sla, weather_p, vehicle_p)
        if candidate_cost < best_cost:
            best_route, best_cost = candidate, candidate_cost

    route_label = f"{route['origin_city_name']} → {route['destination_city_name']}"
    if best_route["route_id"] == route["route_id"]:
        reroute_text = f"Keep current route ({route_label})"
        recommended_action = (
            f"Deploy: {route_label} is already the lowest-expected-cost route on this corridor "
            f"({route_cohort_size} shipments observed)."
        )
    else:
        best_label = f"{best_route['origin_city_name']} → {best_route['destination_city_name']}"
        savings = js_round((cost - best_cost) / 1000)
        reroute_text = f"Reroute via {best_label}"
        recommended_action = (
            f"Consider rerouting via {best_label} instead — projected ₹{savings}K lower expected cost "
            f"({route_cohort_size} shipments observed on {route_label})."
        )

    priority_label = PRIORITY_DISPLAY_NAMES[payload.sla]

    predictive_drivers: list[dict[str, Any]] = [
        {
            "name": FRIENDLY_NAMES.get(feature, feature),
            "direction": direction,
            "contribution": round(coefficient, 3),
            "source": "trained_model",
            "detail": (
                f"Standardized effect on predicted SLA-breach probability "
                f"(breach model holdout AUC {models.breach.holdout_auc:.2f})."
            ),
        }
        for feature, coefficient, direction in models.breach.numeric_drivers()[:2]
    ]
    route_coef = models.breach.categorical_coefficient("route_id", payload.route)
    predictive_drivers.append(
        {
            "name": f"Route: {route_label}",
            "direction": "positive" if (route_coef or 0) >= 0 else "negative",
            "contribution": round(route_coef, 3) if route_coef is not None else 0.0,
            "source": "trained_model",
            "detail": (
                "This route's own historical breach effect vs. the reference route."
                if route_coef is not None
                else "Reference route for this effect — no separate contrast estimated against itself."
            ),
        }
    )
    priority_coef = models.breach.categorical_coefficient("priority", payload.sla)
    predictive_drivers.append(
        {
            "name": f"Priority: {priority_label}",
            "direction": "positive" if (priority_coef or 0) >= 0 else "negative",
            "contribution": round(priority_coef, 3) if priority_coef is not None else 0.0,
            "source": "trained_model",
            "detail": (
                "This priority tier's own historical breach effect vs. the reference tier."
                if priority_coef is not None
                else "Reference priority tier for this effect — no separate contrast estimated against itself."
            ),
        }
    )

    return {
        "delay": js_round(delay_prob * 100),
        "breach": js_round(breach_prob * 100),
        "reroute": reroute_text,
        "cost": js_round(cost),
        "conf": confidence,
        "confidence_band": confidence_band,
        "confidence_basis": "trained_model",
        "recommendedAction": recommended_action,
        "_baseline_reference": {
            "route_shipment_count": route_cohort_size,
            "route_label": route_label,
            "typical_transit_hours": round(route["typical_transit_hours"], 2),
            "route_sla_hours": route["sla_hours"],
            "route_baseline_cost_inr": round(route["baseline_cost_inr"], 2),
        },
        "_recommendation": {
            "current_route_id": route["route_id"],
            "recommended_route_id": best_route["route_id"],
            "rerouted": best_route["route_id"] != route["route_id"],
            "expected_cost_inr": round(best_cost, 2),
        },
        "_predictive_drivers": predictive_drivers,
    }
