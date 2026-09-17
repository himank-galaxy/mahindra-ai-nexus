"""
Synthetic Insurance Claim generator for Mahindra AI Nexus.

Dependency chain:

Production Batch
      |
Allocation
      |
Delivery
      |
Service Event (is_accident_caused=True)
      |
Insurance Claim

Mirrors warranty.py's architecture deliberately: insurance claims are
NOT generated independently, they are created from accident-caused
service evidence (service.py's generate_accident_service_events), the
same way warranty claims are created from ordinary defect-caused
service evidence. This is what actually backs the Warranty-Insurance
Boundary Guidelines document's INSURANCE routing branch with real data -
previously nothing in this project's data ever produced an insurance
claim at all.

This module DOES NOT save CSV files. Persistence is owned by the
caller (data/scripts/generate_all.py), which will write:

    data/synthetic/auto/insurance_claims.csv

All probabilities, claim amounts, and decision thresholds are synthetic
PoC assumptions. They are not real insurer pricing, underwriting rules,
or actual claims statistics.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.helpers import load_generation_config
from data.generators.common.ids import make_entity_id
from data.generators.common.seed import derive_seed, make_rng

# ============================================================
# CLAIM FILING PROBABILITY
#
# Unlike a warranty candidate (where the customer decides whether to
# bother filing), an accident is filed as an insurance claim in the
# large majority of real cases - the customer has already paid for the
# repair to happen and wants it reimbursed.
# ============================================================

BASE_CLAIM_FILING_PROBABILITY = 0.90

# ============================================================
# CLAIM SUBMISSION / DECISION DELAY
# ============================================================

MIN_CLAIM_SUBMISSION_HOURS = 4.0
MAX_CLAIM_SUBMISSION_HOURS = 72.0
MIN_DECISION_HOURS = 24.0
MAX_DECISION_HOURS = 240.0

# ============================================================
# SYNTHETIC CLAIM AMOUNT RANGES (INR)
#
# Collision/accident repair (body panels, glass, lighting, suspension,
# braking) is generally costlier than a typical warranty defect repair -
# these ranges are deliberately higher than warranty.py's equivalents,
# not a copy-paste of them.
# ============================================================

LOW_CLAIM_MIN_INR = 8_000
LOW_CLAIM_MAX_INR = 30_000
MEDIUM_CLAIM_MIN_INR = 30_000
MEDIUM_CLAIM_MAX_INR = 90_000
HIGH_CLAIM_MIN_INR = 90_000
HIGH_CLAIM_MAX_INR = 300_000

# ============================================================
# VALID VALUES
# ============================================================

VALID_CLAIM_STATUSES = {"APPROVED", "MANUAL_REVIEW", "REJECTED"}
VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH"}

INSURANCE_COLUMNS = [
    "insurance_claim_id", "policy_number", "service_event_id", "delivery_id",
    "vehicle_id", "vehicle_model_id", "vehicle_model_name", "variant",
    "vehicle_age_days", "odometer_km", "service_dealer_id", "service_dealer_name",
    "region_id", "region_name", "city_id", "city_name",
    "supplier_component_category", "severity", "accident_impact_g_force",
    "claim_submitted_at", "decision_at", "claim_amount_inr", "approved_amount_inr",
    "claim_status", "data_origin", "generator_version",
]


def _get_generation_end(generation: Mapping[str, Any]) -> pd.Timestamp:
    time_config = generation.get("time", generation.get("time_window", {}))
    iot_config = generation.get("iot", {})
    end_value = iot_config.get(
        "end_date",
        time_config.get("end", time_config.get("end_date")),
    )
    if end_value is None:
        raise KeyError("Missing generation end/end_date")
    timezone = str(time_config.get("timezone", "Asia/Kolkata"))
    timestamp = pd.Timestamp(end_value)
    return (
        timestamp.tz_localize(timezone)
        if timestamp.tzinfo is None
        else timestamp.tz_convert(timezone)
    )


def _validate_inputs(service_events: pd.DataFrame) -> None:
    required = {
        "service_event_id", "delivery_id", "vehicle_id", "vehicle_model_id",
        "vehicle_model_name", "variant", "service_dealer_id", "service_dealer_name",
        "region_id", "region_name", "city_id", "city_name",
        "supplier_component_category", "severity", "is_accident_caused",
        "accident_impact_g_force", "days_since_delivery", "odometer_km",
        "service_completed_at", "service_status",
    }
    missing = required.difference(service_events.columns)
    if missing:
        raise ValueError(
            "Service-events DataFrame is missing columns required by insurance.py: "
            + ", ".join(sorted(missing))
        )
    if service_events["service_event_id"].duplicated().any():
        raise ValueError("Duplicate service_event_id values found")


def _generate_claim_amount(rng: np.random.Generator, severity: str, impact_g_force: float) -> float:
    if severity == "HIGH":
        low, high = HIGH_CLAIM_MIN_INR, HIGH_CLAIM_MAX_INR
    elif severity == "MEDIUM":
        low, high = MEDIUM_CLAIM_MIN_INR, MEDIUM_CLAIM_MAX_INR
    else:
        low, high = LOW_CLAIM_MIN_INR, LOW_CLAIM_MAX_INR
    amount = float(rng.uniform(low, high))
    # Within a severity band, a harder impact still costs a bit more.
    _, band_high = ACCIDENT_IMPACT_RANGE_LOOKUP[severity]
    impact_ratio = float(np.clip(impact_g_force / band_high, 0.0, 1.0))
    amount *= 0.85 + 0.30 * impact_ratio
    return round(amount, 2)


ACCIDENT_IMPACT_RANGE_LOOKUP = {
    "LOW": (1.5, 3.0),
    "MEDIUM": (3.0, 6.0),
    "HIGH": (6.0, 12.0),
}


def _derive_claim_decision(rng: np.random.Generator, severity: str, claim_amount: float) -> str:
    """
    Insurance adjudication evidence is different in kind from warranty
    adjudication (no production/supplier quality score applies here) -
    it is driven by claim size and, loosely, by how severe/plausible the
    reported damage is. Very large claims get more scrutiny (more likely
    MANUAL_REVIEW), consistent with real claims-handling practice, but
    this is a synthetic PoC approximation, not real underwriting logic.
    """
    approval_probability = 0.88
    if severity == "HIGH":
        approval_probability -= 0.05
    if claim_amount > 150_000:
        approval_probability -= 0.10
    if claim_amount > 250_000:
        approval_probability -= 0.08
    approval_probability = float(np.clip(approval_probability, 0.55, 0.92))
    manual_probability = float(np.clip(0.30 - (approval_probability - 0.55), 0.06, 0.30))
    rejection_probability = max(0.0, 1.0 - approval_probability - manual_probability)
    probabilities = np.array([approval_probability, manual_probability, rejection_probability])
    probabilities = probabilities / probabilities.sum()
    return str(rng.choice(["APPROVED", "MANUAL_REVIEW", "REJECTED"], p=probabilities))


def _derive_approved_amount(rng: np.random.Generator, claim_amount: float, claim_status: str) -> float:
    if claim_status != "APPROVED":
        return 0.0
    # A deductible/excess is standard in motor insurance - approved amount
    # is usually a bit less than the raw claim amount, not a 1:1 payout.
    approval_ratio = float(rng.uniform(0.80, 0.97))
    return round(claim_amount * approval_ratio, 2)


def generate_insurance_claims(
    service_events: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Generate insurance claims from accident-caused service evidence only."""
    if generation is None:
        generation = load_generation_config()
    _validate_inputs(service_events)
    generation_end = _get_generation_end(generation)
    base_seed = int(generation["seed"])
    rng = make_rng(derive_seed(base_seed, "auto.insurance"))
    provenance = generation.get("provenance", {})
    data_origin = str(provenance.get("data_origin", "SYNTHETIC"))
    generator_version = str(generation.get("generator_version", "1.0.0"))

    candidates = service_events[
        service_events["is_accident_caused"].astype(bool)
        & (service_events["service_status"] == "COMPLETED")
    ].copy()

    if candidates.empty:
        return pd.DataFrame(columns=INSURANCE_COLUMNS)

    rows: list[dict[str, Any]] = []
    claim_counter = 1
    for service in candidates.itertuples(index=False):
        if float(rng.random()) >= BASE_CLAIM_FILING_PROBABILITY:
            continue

        service_completed_at = pd.Timestamp(service.service_completed_at)
        available_hours = (generation_end - service_completed_at).total_seconds() / 3600.0
        if available_hours <= 0:
            continue
        max_submission_delay = min(MAX_CLAIM_SUBMISSION_HOURS, available_hours)
        min_submission_delay = min(MIN_CLAIM_SUBMISSION_HOURS, max_submission_delay)
        submission_delay_hours = float(rng.uniform(min_submission_delay, max_submission_delay))
        claim_submitted_at = service_completed_at + timedelta(hours=submission_delay_hours)
        if claim_submitted_at > generation_end:
            continue

        severity = str(service.severity).strip().upper()
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"{service.service_event_id}: invalid severity {severity}")

        impact_g_force = float(service.accident_impact_g_force)
        claim_amount = _generate_claim_amount(rng, severity, impact_g_force)
        claim_status = _derive_claim_decision(rng, severity, claim_amount)

        remaining_hours = (generation_end - claim_submitted_at).total_seconds() / 3600.0
        if remaining_hours <= 0:
            claim_status = "MANUAL_REVIEW"
            decision_at = None
        else:
            max_decision_delay = min(MAX_DECISION_HOURS, remaining_hours)
            min_decision_delay = min(MIN_DECISION_HOURS, max_decision_delay)
            decision_delay_hours = float(rng.uniform(min_decision_delay, max_decision_delay))
            decision_at = claim_submitted_at + timedelta(hours=decision_delay_hours)

        approved_amount = _derive_approved_amount(rng, claim_amount, claim_status)

        rows.append({
            "insurance_claim_id": make_entity_id("insurance_claim", claim_counter, width=6),
            "policy_number": f"POLICY_SYN_{str(service.vehicle_id).split('_')[-1]}",
            "service_event_id": service.service_event_id,
            "delivery_id": service.delivery_id,
            "vehicle_id": service.vehicle_id,
            "vehicle_model_id": service.vehicle_model_id,
            "vehicle_model_name": service.vehicle_model_name,
            "variant": service.variant,
            "vehicle_age_days": round(float(service.days_since_delivery), 3),
            "odometer_km": int(service.odometer_km),
            "service_dealer_id": service.service_dealer_id,
            "service_dealer_name": service.service_dealer_name,
            "region_id": service.region_id,
            "region_name": service.region_name,
            "city_id": service.city_id,
            "city_name": service.city_name,
            "supplier_component_category": service.supplier_component_category,
            "severity": severity,
            "accident_impact_g_force": round(impact_g_force, 3),
            "claim_submitted_at": claim_submitted_at,
            "decision_at": decision_at,
            "claim_amount_inr": claim_amount,
            "approved_amount_inr": approved_amount,
            "claim_status": claim_status,
            "data_origin": data_origin,
            "generator_version": generator_version,
        })
        claim_counter += 1

    insurance_claims = pd.DataFrame(rows, columns=INSURANCE_COLUMNS)
    validate_insurance_claims(insurance_claims, service_events, generation_end)
    return insurance_claims


def validate_insurance_claims(
    insurance_claims: pd.DataFrame,
    service_events: pd.DataFrame,
    generation_end: pd.Timestamp,
) -> None:
    missing = set(INSURANCE_COLUMNS).difference(insurance_claims.columns)
    if missing:
        raise ValueError("Insurance claims are missing columns: " + ", ".join(sorted(missing)))
    if insurance_claims.empty:
        return
    if insurance_claims["insurance_claim_id"].duplicated().any():
        raise ValueError("Duplicate insurance_claim_id values found")
    if insurance_claims["service_event_id"].duplicated().any():
        raise ValueError("A service event generated multiple insurance claims")

    accident_service_ids = set(
        service_events.loc[service_events["is_accident_caused"].astype(bool), "service_event_id"]
    )
    invalid_service_ids = set(insurance_claims["service_event_id"]) - accident_service_ids
    if invalid_service_ids:
        raise ValueError("Insurance claims were generated from non-accident-caused service events")

    if not insurance_claims["claim_status"].isin(VALID_CLAIM_STATUSES).all():
        raise ValueError("Invalid insurance claim statuses found")

    claim_amounts = pd.to_numeric(insurance_claims["claim_amount_inr"])
    approved_amounts = pd.to_numeric(insurance_claims["approved_amount_inr"])
    if (claim_amounts <= 0).any():
        raise ValueError("claim_amount_inr must be > 0")
    if (approved_amounts < 0).any():
        raise ValueError("approved_amount_inr cannot be negative")
    if (approved_amounts > claim_amounts).any():
        raise ValueError("approved_amount_inr cannot exceed claim_amount_inr")

    approved = insurance_claims["claim_status"] == "APPROVED"
    if (insurance_claims.loc[approved, "approved_amount_inr"] <= 0).any():
        raise ValueError("APPROVED insurance claims must have approved_amount_inr > 0")
    non_approved = insurance_claims["claim_status"] != "APPROVED"
    if not (insurance_claims.loc[non_approved, "approved_amount_inr"] == 0).all():
        raise ValueError("Non-approved insurance claims must have approved_amount_inr=0")

    submitted = pd.to_datetime(insurance_claims["claim_submitted_at"])
    if (submitted > generation_end).any():
        raise ValueError("Insurance claim submitted after generation end")


if __name__ == "__main__":
    from data.generators.auto.service import generate_accident_service_events, generate_service_events

    deliveries = pd.read_csv("data/synthetic/auto/deliveries.csv")
    service_events = generate_service_events(deliveries=deliveries)
    enriched = generate_accident_service_events(deliveries=deliveries, service_events=service_events)
    insurance_claims = generate_insurance_claims(service_events=enriched)

    print(f"\nAccident-caused service events: {int(enriched['is_accident_caused'].sum())}")
    print(f"Insurance claims generated: {len(insurance_claims)}\n")
    if not insurance_claims.empty:
        display_columns = [
            "insurance_claim_id", "vehicle_id", "severity", "accident_impact_g_force",
            "supplier_component_category", "claim_amount_inr", "approved_amount_inr", "claim_status",
        ]
        print(insurance_claims[display_columns].to_string(index=False))
        print(f"\nTotal claimed: {insurance_claims['claim_amount_inr'].sum():,.2f}")
        print(f"Total approved: {insurance_claims['approved_amount_inr'].sum():,.2f}")
