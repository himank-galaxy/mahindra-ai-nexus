"""Finance Collections Simulation engine — Phase 4: real trained models.

Recovery probability, channel response, and offer response come from one
real logistic regression trained on the actual recorded outcome
(``payment_after_contact``) — see
app/ai/simulation/models/collections_model.py. Both channel and offer are
the exact real recorded categories (no UI-to-real translation layer — see
app/repositories/collections_simulation.py), so every combination trains
on genuine historical outcomes; this domain has no missing-history gap
like Auto Sales' incentive layer or Dealer Allocation's shortage
scenario, and its ``confidence_basis`` is always ``trained_model``.

Recovery cost and friction have no real per-contact cost field in the
runtime schema, so both stay documented, reviewable assumptions — the one
part of this engine that isn't fit on data.
"""

from __future__ import annotations

from typing import Any

from app.ai.simulation.confidence import trained_model_confidence
from app.ai.simulation.models.collections_model import FRIENDLY_NAMES, get_or_train_models
from app.ai.utils import js_round
from app.repositories.collections_simulation import CHANNEL_DISPLAY_NAMES, OFFER_DISPLAY_NAMES, CollectionsSimulationRepository
from app.schemas.simulation import CollectionsSimIn

MODEL_NAME = "collections.logit_recovery_channel_offer_v1"
MODEL_VERSION = "phase4.1"

CHANNELS = ("SMS", "WHATSAPP", "EMAIL", "CALL", "FIELD_VISIT")
OFFERS = ("NONE", "PAYMENT_REMINDER", "PARTIAL_PAYMENT_PLAN", "REPAYMENT_PLAN_DISCUSSION")

# Calibrated per-contact cost/friction — no real cost-per-contact field
# exists in the runtime schema, so these are documented business
# assumptions, not fitted effects. Digital channels are cheapest/lowest
# friction, field visits are the most expensive and intrusive.
COST_BY_CHANNEL_INR: dict[str, int] = {
    "SMS": 40,
    "WHATSAPP": 60,
    "EMAIL": 90,
    "CALL": 320,
    "FIELD_VISIT": 1200,
}
FIELD_VISIT_COST_PER_INTENSITY_INR = 8
FRICTION_BY_CHANNEL: dict[str, int] = {
    "SMS": 8,
    "WHATSAPP": 10,
    "EMAIL": 12,
    "CALL": 34,
    "FIELD_VISIT": 62,
}
FRICTION_FIELD_INTENSITY_WEIGHT = 10

MIN_COHORT_SIZE = 20


def _cost_inr(channel: str, field_intensity_pct: int) -> int:
    cost = COST_BY_CHANNEL_INR[channel]
    if channel == "FIELD_VISIT":
        cost += field_intensity_pct * FIELD_VISIT_COST_PER_INTENSITY_INR
    return cost


def _friction(channel: str, field_intensity_pct: int) -> int:
    return min(100, FRICTION_BY_CHANNEL[channel] + js_round(field_intensity_pct / 100 * FRICTION_FIELD_INTENSITY_WEIGHT))


async def run(payload: CollectionsSimIn, repo: CollectionsSimulationRepository) -> dict[str, Any]:
    models = await get_or_train_models(repo)
    recovery_features, recovery_cohort_size = models.cohort_recovery_features(payload.risk)
    roll_forward_features, roll_forward_cohort_size = models.cohort_roll_forward_features(payload.risk)
    cohort_stats = await repo.get_cohort_stats(payload.risk)
    avg_outstanding_inr = cohort_stats["avg_outstanding_inr"] or 0.0

    recovery_prob = models.recovery.predict_proba(
        recovery_features, {"channel": payload.channel, "offer_type": payload.offer}
    )
    roll_forward_risk_prob = 1 - models.roll_forward.predict_proba(roll_forward_features)
    cost = _cost_inr(payload.channel, payload.field)
    friction = _friction(payload.channel, payload.field)
    net_recovery_inr = recovery_prob * avg_outstanding_inr - cost
    net_k = js_round(net_recovery_inr / 1000)

    cohort_size = min(recovery_cohort_size, roll_forward_cohort_size)
    confidence, confidence_band = trained_model_confidence(
        predicted_probability=recovery_prob,
        in_training_range=True,
        cohort_sample_size=cohort_size,
    )

    # Strategy optimizer: sweep the real action space (5 channels x 4
    # offers) for THIS risk segment and field intensity, and recommend
    # whichever maximizes expected net recovery — never simply the
    # highest recovery probability alone.
    best_channel, best_offer, best_net = payload.channel, payload.offer, net_recovery_inr
    for candidate_channel in CHANNELS:
        for candidate_offer in OFFERS:
            candidate_prob = models.recovery.predict_proba(
                recovery_features, {"channel": candidate_channel, "offer_type": candidate_offer}
            )
            candidate_cost = _cost_inr(candidate_channel, payload.field)
            candidate_net = candidate_prob * avg_outstanding_inr - candidate_cost
            if candidate_net > best_net:
                best_channel, best_offer, best_net = candidate_channel, candidate_offer, candidate_net

    matches_selection = best_channel == payload.channel and best_offer == payload.offer
    channel_label = CHANNEL_DISPLAY_NAMES[payload.channel]
    offer_label = OFFER_DISPLAY_NAMES[payload.offer]
    if matches_selection:
        action = f"Deploy: {channel_label} contact with {offer_label} offer is already the best expected net recovery for this risk segment"
    else:
        best_channel_label, best_offer_label = CHANNEL_DISPLAY_NAMES[best_channel], OFFER_DISPLAY_NAMES[best_offer]
        action = (
            f"Consider {best_channel_label} contact with {best_offer_label} offer instead — projected "
            f"₹{js_round((best_net - net_recovery_inr) / 1000)}K higher net recovery"
        )
    recommended_action = (
        f"{action} (cohort: {cohort_size} interactions observed, avg outstanding "
        f"₹{js_round(avg_outstanding_inr)})."
    )

    predictive_drivers: list[dict[str, Any]] = [
        {
            "name": FRIENDLY_NAMES.get(feature, feature),
            "direction": direction,
            "contribution": round(coefficient, 3),
            "source": "trained_model",
            "detail": (
                f"Standardized effect on predicted recovery probability "
                f"(recovery model holdout AUC {models.recovery.holdout_auc:.2f})."
            ),
        }
        for feature, coefficient, direction in models.recovery.numeric_drivers()[:2]
    ]
    channel_coef = models.recovery.categorical_coefficient("channel", payload.channel)
    predictive_drivers.append(
        {
            "name": f"Channel: {channel_label}",
            "direction": "positive" if (channel_coef or 0) >= 0 else "negative",
            "contribution": round(channel_coef, 3) if channel_coef is not None else 0.0,
            "source": "trained_model",
            "detail": "This channel's own historical recovery effect vs. the reference channel."
            if channel_coef is not None
            else "Reference channel for this effect — no separate contrast estimated against itself.",
        }
    )
    offer_coef = models.recovery.categorical_coefficient("offer_type", payload.offer)
    predictive_drivers.append(
        {
            "name": f"Offer: {offer_label}",
            "direction": "positive" if (offer_coef or 0) >= 0 else "negative",
            "contribution": round(offer_coef, 3) if offer_coef is not None else 0.0,
            "source": "trained_model",
            "detail": "This offer's own historical recovery effect vs. the reference offer."
            if offer_coef is not None
            else "Reference offer for this effect — no separate contrast estimated against itself.",
        }
    )

    return {
        "prob": js_round(recovery_prob * 100),
        "cost": cost,
        "friction": friction,
        "net": net_k,
        "conf": confidence,
        "confidence_band": confidence_band,
        "confidence_basis": "trained_model",
        "recommendedAction": recommended_action,
        "_baseline_reference": {
            "cohort_interaction_count": cohort_stats["interaction_count"],
            "avg_arrears_inr": round(cohort_stats["avg_arrears_inr"], 2),
            "avg_outstanding_inr": round(avg_outstanding_inr, 2),
            "roll_forward_risk_probability": round(roll_forward_risk_prob, 4),
        },
        "_recommendation": {
            "best_channel": best_channel,
            "best_offer": best_offer,
            "matches_selection": matches_selection,
            "net_recovery_inr": round(net_recovery_inr, 2),
        },
        "_predictive_drivers": predictive_drivers,
    }
