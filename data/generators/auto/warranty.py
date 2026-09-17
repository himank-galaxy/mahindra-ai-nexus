"""
Synthetic Warranty Claim generator for Mahindra AI Nexus.

Dependency chain:

Production Batch
      ↓
Allocation
      ↓
Delivery
      ↓
Service Event
      ↓
Warranty Claim

IMPORTANT:

Warranty claims are NOT generated independently.

They are created from service evidence, primarily:

    service_type == "UNSCHEDULED_REPAIR"

and:

    warranty_candidate == True

This preserves the traceability:

Warranty Claim
    ↓
Service Event
    ↓
Vehicle
    ↓
Production Batch
    ↓
Plant / Production Line / Machine
    ↓
Supplier Lot
    ↓
Supplier

This allows the Warranty & Quality Early-Warning Graph to later
identify patterns such as:

    Supplier Lot
        ↓
    Production Batch
        ↓
    Repeated Service Issues
        ↓
    Warranty Claims

This module DOES NOT save CSV files.

Later generate_all.py will save:

    data/synthetic/auto/warranty.csv

All probabilities, claim amounts and decision thresholds are
synthetic PoC assumptions. They are not real Mahindra warranty
rules, costs or operational statistics.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.helpers import (
    load_generation_config,
)

from data.generators.common.ids import (
    make_entity_id,
)

from data.generators.common.seed import (
    derive_seed,
    make_rng,
)


# ============================================================
# WARRANTY CLAIM CREATION PROBABILITIES
#
# A warranty candidate does not automatically become a claim.
# The customer/service center must actually raise the claim.
# ============================================================

LOW_SEVERITY_CLAIM_PROBABILITY = 0.55

MEDIUM_SEVERITY_CLAIM_PROBABILITY = 0.78

HIGH_SEVERITY_CLAIM_PROBABILITY = 0.92


# ============================================================
# CLAIM SUBMISSION DELAY
# ============================================================

MIN_CLAIM_SUBMISSION_HOURS = 2.0
MAX_CLAIM_SUBMISSION_HOURS = 36.0


# ============================================================
# CLAIM DECISION DELAY
# ============================================================

MIN_DECISION_HOURS = 4.0
MAX_DECISION_HOURS = 96.0


# ============================================================
# SYNTHETIC CLAIM AMOUNT RANGES
# ============================================================

LOW_CLAIM_MIN_INR = 3000
LOW_CLAIM_MAX_INR = 12000

MEDIUM_CLAIM_MIN_INR = 12000
MEDIUM_CLAIM_MAX_INR = 45000

HIGH_CLAIM_MIN_INR = 35000
HIGH_CLAIM_MAX_INR = 120000


# ============================================================
# QUALITY REFERENCES
# ============================================================

PRODUCTION_QUALITY_REFERENCE = 0.95

SUPPLIER_QUALITY_REFERENCE = 0.90


# ============================================================
# VALID VALUES
# ============================================================

VALID_CLAIM_STATUSES = {
    "APPROVED",
    "MANUAL_REVIEW",
    "REJECTED",
}


VALID_ROOT_CAUSE_DOMAINS = {
    "SUPPLIER_QUALITY",
    "MANUFACTURING_QUALITY",
    "COMPONENT_FAILURE",
    "SERVICE_DIAGNOSIS",
    "MULTIPLE_FACTORS",
}


VALID_SEVERITIES = {
    "LOW",
    "MEDIUM",
    "HIGH",
}


# ============================================================
# GENERATION END
# ============================================================


def _get_generation_end(
    generation: Mapping[str, Any],
) -> pd.Timestamp:
    """
    Read configured synthetic generation end timestamp.
    """

    time_config = generation.get(
        "time"
    )

    if not isinstance(
        time_config,
        Mapping,
    ):
        time_config = generation.get(
            "time_window"
        )

    if not isinstance(
        time_config,
        Mapping,
    ):
        raise KeyError(
            "Missing generation time configuration"
        )

    iot_config = generation.get("iot", {})
    end_value = iot_config.get(
        "end_date",
        time_config.get(
            "end",
            time_config.get(
                "end_date"
            ),
        ),
    )

    if end_value is None:
        raise KeyError(
            "Missing generation end/end_date"
        )

    timezone = str(
        time_config.get(
            "timezone",
            "Asia/Kolkata",
        )
    )

    timestamp = pd.Timestamp(
        end_value
    )

    if timestamp.tzinfo is None:

        timestamp = timestamp.tz_localize(
            timezone
        )

    else:

        timestamp = timestamp.tz_convert(
            timezone
        )

    return timestamp


# ============================================================
# INPUT VALIDATION
# ============================================================


def _validate_inputs(
    service_events: pd.DataFrame,
) -> None:
    """
    Validate service-event input.
    """

    required = {
        "service_event_id",

        "delivery_id",
        "allocation_id",
        "booking_id",
        "customer_id",

        "vehicle_id",
        "vehicle_model_id",
        "vehicle_model_name",
        "variant",

        "service_dealer_id",
        "service_dealer_name",

        "region_id",
        "region_name",

        "city_id",
        "city_name",

        "production_batch_id",

        "plant_id",
        "plant_name",

        "production_line_id",
        "production_line_name",

        "representative_machine_id",
        "representative_machine_name",

        "primary_supplier_id",
        "primary_supplier_name",
        "primary_supplier_lot_id",

        "supplier_component_category",

        "supplier_lot_quality_score",
        "production_quality_score",

        "service_type",

        "service_started_at",
        "service_completed_at",

        "days_since_delivery",
        "odometer_km",

        "issue_category",
        "severity",

        "diagnosis",
        "repair_required",

        "service_duration_hours",

        "warranty_candidate",

        "service_status",
    }

    missing = (
        required
        .difference(
            service_events.columns
        )
    )

    if missing:

        raise ValueError(
            "Service-events DataFrame is missing "
            "columns required by warranty.py: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if service_events.empty:

        raise ValueError(
            "Service-events DataFrame cannot be empty"
        )

    if service_events[
        "service_event_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate service_event_id values found"
        )


# ============================================================
# CLAIM PROBABILITY
# ============================================================


def _calculate_claim_probability(
    severity: str,

    production_quality: float,

    supplier_quality: float,

    service_duration_hours: float,
) -> float:
    """
    Calculate probability that a warranty candidate turns
    into an actual warranty claim.

    Evidence:

        severity
        production quality
        supplier-lot quality
        service repair duration

    Higher severity and poorer quality increase probability.
    """

    severity = (
        str(
            severity
        )
        .strip()
        .upper()
    )

    if severity == "HIGH":

        probability = (
            HIGH_SEVERITY_CLAIM_PROBABILITY
        )

    elif severity == "MEDIUM":

        probability = (
            MEDIUM_SEVERITY_CLAIM_PROBABILITY
        )

    else:

        probability = (
            LOW_SEVERITY_CLAIM_PROBABILITY
        )

    production_quality = float(
        np.clip(
            production_quality,
            0.0,
            1.0,
        )
    )

    supplier_quality = float(
        np.clip(
            supplier_quality,
            0.0,
            1.0,
        )
    )

    # --------------------------------------------------------
    # POOR PRODUCTION QUALITY
    # --------------------------------------------------------

    production_gap = max(
        PRODUCTION_QUALITY_REFERENCE
        -
        production_quality,
        0.0,
    )

    probability += (
        production_gap
        * 1.20
    )

    # --------------------------------------------------------
    # POOR SUPPLIER QUALITY
    # --------------------------------------------------------

    supplier_gap = max(
        SUPPLIER_QUALITY_REFERENCE
        -
        supplier_quality,
        0.0,
    )

    probability += (
        supplier_gap
        * 0.80
    )

    # --------------------------------------------------------
    # LONG REPAIR
    # --------------------------------------------------------

    if service_duration_hours > 24:

        probability += 0.05

    if service_duration_hours > 48:

        probability += 0.04

    return float(
        np.clip(
            probability,
            0.05,
            0.98,
        )
    )


# ============================================================
# CLAIM AMOUNT
# ============================================================


def _generate_claim_amount(
    rng: np.random.Generator,

    severity: str,

    service_duration_hours: float,

    production_quality: float,
) -> float:
    """
    Generate synthetic claimed warranty cost.
    """

    severity = (
        str(
            severity
        )
        .strip()
        .upper()
    )

    if severity == "HIGH":

        low = HIGH_CLAIM_MIN_INR
        high = HIGH_CLAIM_MAX_INR

    elif severity == "MEDIUM":

        low = MEDIUM_CLAIM_MIN_INR
        high = MEDIUM_CLAIM_MAX_INR

    else:

        low = LOW_CLAIM_MIN_INR
        high = LOW_CLAIM_MAX_INR

    amount = float(
        rng.uniform(
            low,
            high,
        )
    )

    # --------------------------------------------------------
    # LONGER SERVICE → slightly higher claim cost
    # --------------------------------------------------------

    if service_duration_hours > 24:

        amount *= 1.10

    if service_duration_hours > 48:

        amount *= 1.12

    # --------------------------------------------------------
    # Lower production quality can increase repair extent
    # --------------------------------------------------------

    quality_gap = max(
        PRODUCTION_QUALITY_REFERENCE
        -
        float(
            production_quality
        ),
        0.0,
    )

    amount *= (
        1.0
        +
        quality_gap
        * 1.5
    )

    return round(
        amount,
        2,
    )


# ============================================================
# ROOT CAUSE DOMAIN
# ============================================================


def _derive_root_cause_domain(
    supplier_quality: float,

    production_quality: float,

    issue_category: str,
) -> str:
    """
    Derive a broad synthetic root-cause domain.

    IMPORTANT:

    This is generator truth/evaluation metadata.

    It should later be handled carefully when generating
    runtime-facing CSV/DB tables so it is not used as an
    unfair shortcut by causal discovery.
    """

    supplier_problem = bool(
        supplier_quality
        <
        SUPPLIER_QUALITY_REFERENCE
    )

    production_problem = bool(
        production_quality
        <
        PRODUCTION_QUALITY_REFERENCE
    )

    issue = (
        str(
            issue_category
        )
        .upper()
    )

    component_keywords = (
        "BATTERY",
        "BRAKE",
        "ECU",
        "ELECTRIC",
        "HVAC",
        "STEERING",
        "SUSPENSION",
        "TYRE",
        "DRIVETRAIN",
        "EXHAUST",
        "LIGHT",
        "FLUID",
    )

    component_problem = any(
        keyword in issue
        for keyword
        in component_keywords
    )

    evidence_count = sum(
        [
            supplier_problem,
            production_problem,
            component_problem,
        ]
    )

    if evidence_count >= 2:

        return "MULTIPLE_FACTORS"

    if supplier_problem:

        return "SUPPLIER_QUALITY"

    if production_problem:

        return "MANUFACTURING_QUALITY"

    if component_problem:

        return "COMPONENT_FAILURE"

    return "SERVICE_DIAGNOSIS"


# ============================================================
# CLAIM DECISION
# ============================================================


def _derive_claim_decision(
    rng: np.random.Generator,

    severity: str,

    supplier_quality: float,

    production_quality: float,

    claim_amount: float,
) -> str:
    """
    Determine synthetic claim-decision status.

    Better supporting evidence:
        APPROVED more likely.

    Expensive ambiguous claims:
        MANUAL_REVIEW more likely.

    Some claims:
        REJECTED.
    """

    severity = (
        str(
            severity
        )
        .strip()
        .upper()
    )

    evidence_strength = 0.0

    if severity == "HIGH":

        evidence_strength += 0.35

    elif severity == "MEDIUM":

        evidence_strength += 0.22

    else:

        evidence_strength += 0.10

    if supplier_quality < 0.90:

        evidence_strength += 0.22

    if production_quality < 0.95:

        evidence_strength += 0.20

    if claim_amount > 50000:

        evidence_strength -= 0.05

    if claim_amount > 90000:

        evidence_strength -= 0.06

    evidence_strength = float(
        np.clip(
            evidence_strength,
            0.0,
            1.0,
        )
    )

    approval_probability = (
        0.62
        +
        0.28
        * evidence_strength
    )

    manual_probability = (
        0.22
        -
        0.05
        * evidence_strength
    )

    approval_probability = float(
        np.clip(
            approval_probability,
            0.55,
            0.92,
        )
    )

    manual_probability = float(
        np.clip(
            manual_probability,
            0.08,
            0.25,
        )
    )

    rejection_probability = max(
        0.0,
        1.0
        -
        approval_probability
        -
        manual_probability,
    )

    probabilities = np.array(
        [
            approval_probability,
            manual_probability,
            rejection_probability,
        ],
        dtype=float,
    )

    probabilities = (
        probabilities
        /
        probabilities.sum()
    )

    return str(
        rng.choice(
            [
                "APPROVED",
                "MANUAL_REVIEW",
                "REJECTED",
            ],
            p=probabilities,
        )
    )


# ============================================================
# APPROVED AMOUNT
# ============================================================


def _derive_approved_amount(
    rng: np.random.Generator,

    claim_amount: float,

    claim_status: str,
) -> float:
    """
    Calculate approved reimbursement amount.
    """

    if claim_status == "REJECTED":

        return 0.0

    if claim_status == "MANUAL_REVIEW":

        # Not yet finalized.
        return 0.0

    approval_ratio = float(
        rng.uniform(
            0.86,
            1.00,
        )
    )

    return round(
        claim_amount
        *
        approval_ratio,
        2,
    )


# ============================================================
# FAILURE CODE
# ============================================================


def _derive_failure_code(
    issue_category: str,
) -> str:
    """
    Convert service issue category into a stable synthetic
    warranty failure code.
    """

    cleaned = (
        str(
            issue_category
        )
        .strip()
        .upper()
        .replace(
            " ",
            "_",
        )
    )

    return (
        "WFAIL_"
        +
        cleaned
    )


# ============================================================
# GENERATOR
# ============================================================


def generate_warranty_claims(
    service_events: pd.DataFrame,

    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate warranty claims from service evidence.

    Only:

        UNSCHEDULED_REPAIR
        +
        warranty_candidate=True

    are considered.

    Even then, not every candidate necessarily becomes
    an actual claim.
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    # ========================================================
    # VALIDATE
    # ========================================================

    _validate_inputs(
        service_events
    )

    # ========================================================
    # GENERATION END
    # ========================================================

    generation_end = (
        _get_generation_end(
            generation
        )
    )

    # ========================================================
    # RNG
    # ========================================================

    try:

        base_seed = int(
            generation[
                "seed"
            ]
        )

    except KeyError as exc:

        raise KeyError(
            "Missing generation.seed"
        ) from exc

    rng = make_rng(
        derive_seed(
            base_seed,
            "auto.warranty",
        )
    )

    # ========================================================
    # PROVENANCE
    # ========================================================

    provenance = generation.get(
        "provenance",
        {},
    )

    data_origin = str(
        provenance.get(
            "data_origin",
            "SYNTHETIC",
        )
    )

    generator_version = str(
        generation.get(
            "generator_version",
            "1.0.0",
        )
    )

    # ========================================================
    # WARRANTY CANDIDATES
    # ========================================================

    candidates = (
        service_events[
            (
                service_events[
                    "service_type"
                ]
                ==
                "UNSCHEDULED_REPAIR"
            )
            &
            (
                service_events[
                    "warranty_candidate"
                ]
                .astype(bool)
            )
            &
            (
                service_events[
                    "service_status"
                ]
                ==
                "COMPLETED"
            )
        ]
        .copy()
    )

    if candidates.empty:

        return pd.DataFrame(
            columns=_warranty_columns()
        )

    # ========================================================
    # GENERATE
    # ========================================================

    rows: list[
        dict[str, Any]
    ] = []

    claim_counter = 1

    for service in candidates.itertuples(
        index=False
    ):

        severity = (
            str(
                service.severity
            )
            .strip()
            .upper()
        )

        if severity not in VALID_SEVERITIES:

            raise ValueError(
                f"{service.service_event_id}: "
                f"invalid severity {severity}"
            )

        production_quality = float(
            service.
            production_quality_score
        )

        supplier_quality = float(
            service.
            supplier_lot_quality_score
        )

        service_duration_hours = float(
            service.
            service_duration_hours
        )

        # ====================================================
        # SHOULD CLAIM BE RAISED?
        # ====================================================

        claim_probability = (
            _calculate_claim_probability(
                severity=
                    severity,

                production_quality=
                    production_quality,

                supplier_quality=
                    supplier_quality,

                service_duration_hours=
                    service_duration_hours,
            )
        )

        claim_created = bool(
            float(
                rng.random()
            )
            <
            claim_probability
        )

        if not claim_created:

            continue

        # ====================================================
        # CLAIM SUBMISSION
        # ====================================================

        service_completed_at = pd.Timestamp(
            service.
            service_completed_at
        )

        available_hours = (
            (
                generation_end
                -
                service_completed_at
            ).total_seconds()
            /
            3600.0
        )

        if available_hours <= 0:

            continue

        max_submission_delay = min(
            MAX_CLAIM_SUBMISSION_HOURS,
            available_hours,
        )

        min_submission_delay = min(
            MIN_CLAIM_SUBMISSION_HOURS,
            max_submission_delay,
        )

        submission_delay_hours = float(
            rng.uniform(
                min_submission_delay,
                max_submission_delay,
            )
        )

        claim_submitted_at = (
            service_completed_at
            +
            timedelta(
                hours=
                    submission_delay_hours
            )
        )

        if claim_submitted_at > generation_end:

            continue

        # ====================================================
        # CLAIM AMOUNT
        # ====================================================

        claim_amount = (
            _generate_claim_amount(
                rng=rng,

                severity=
                    severity,

                service_duration_hours=
                    service_duration_hours,

                production_quality=
                    production_quality,
            )
        )

        # ====================================================
        # CLAIM DECISION
        # ====================================================

        claim_status = (
            _derive_claim_decision(
                rng=rng,

                severity=
                    severity,

                supplier_quality=
                    supplier_quality,

                production_quality=
                    production_quality,

                claim_amount=
                    claim_amount,
            )
        )

        # ====================================================
        # DECISION TIME
        # ====================================================

        remaining_hours = (
            (
                generation_end
                -
                claim_submitted_at
            ).total_seconds()
            /
            3600.0
        )

        if remaining_hours <= 0:

            # Claim exists but decision cannot occur before
            # generation cutoff.
            claim_status = (
                "MANUAL_REVIEW"
            )

            decision_at = None

        else:

            max_decision_delay = min(
                MAX_DECISION_HOURS,
                remaining_hours,
            )

            min_decision_delay = min(
                MIN_DECISION_HOURS,
                max_decision_delay,
            )

            decision_delay_hours = float(
                rng.uniform(
                    min_decision_delay,
                    max_decision_delay,
                )
            )

            decision_at = (
                claim_submitted_at
                +
                timedelta(
                    hours=
                        decision_delay_hours
                )
            )

        # ====================================================
        # APPROVED AMOUNT
        # ====================================================

        approved_amount = (
            _derive_approved_amount(
                rng=rng,

                claim_amount=
                    claim_amount,

                claim_status=
                    claim_status,
            )
        )

        # ====================================================
        # ROOT CAUSE DOMAIN
        # ====================================================

        root_cause_domain = (
            _derive_root_cause_domain(
                supplier_quality=
                    supplier_quality,

                production_quality=
                    production_quality,

                issue_category=
                    str(
                        service.
                        issue_category
                    ),
            )
        )

        # ====================================================
        # FAILURE CODE
        # ====================================================

        failure_code = (
            _derive_failure_code(
                str(
                    service.
                    issue_category
                )
            )
        )

        # ====================================================
        # CLAIM AGE / VEHICLE AGE
        # ====================================================

        vehicle_age_days = float(
            service.
            days_since_delivery
        )

        odometer_km = int(
            service.
            odometer_km
        )

        # ====================================================
        # RECORD
        # ====================================================

        rows.append(
            {
                # --------------------------------------------
                # CLAIM
                # --------------------------------------------

                "warranty_claim_id":
                    make_entity_id(
                        "warranty_claim",
                        claim_counter,
                        width=6,
                    ),

                # --------------------------------------------
                # SERVICE
                # --------------------------------------------

                "service_event_id":
                    service.service_event_id,

                "delivery_id":
                    service.delivery_id,

                "allocation_id":
                    service.allocation_id,

                "booking_id":
                    service.booking_id,

                "customer_id":
                    service.customer_id,

                # --------------------------------------------
                # VEHICLE
                # --------------------------------------------

                "vehicle_id":
                    service.vehicle_id,

                "vehicle_model_id":
                    service.vehicle_model_id,

                "vehicle_model_name":
                    service.vehicle_model_name,

                "variant":
                    service.variant,

                "vehicle_age_days":
                    round(
                        vehicle_age_days,
                        3,
                    ),

                "odometer_km":
                    odometer_km,

                # --------------------------------------------
                # DEALER / LOCATION
                # --------------------------------------------

                "service_dealer_id":
                    service.service_dealer_id,

                "service_dealer_name":
                    service.service_dealer_name,

                "region_id":
                    service.region_id,

                "region_name":
                    service.region_name,

                "city_id":
                    service.city_id,

                "city_name":
                    service.city_name,

                # --------------------------------------------
                # PRODUCTION
                # --------------------------------------------

                "production_batch_id":
                    service.production_batch_id,

                "plant_id":
                    service.plant_id,

                "plant_name":
                    service.plant_name,

                "production_line_id":
                    service.production_line_id,

                "production_line_name":
                    service.production_line_name,

                "representative_machine_id":
                    service.
                    representative_machine_id,

                "representative_machine_name":
                    service.
                    representative_machine_name,

                # --------------------------------------------
                # SUPPLIER
                # --------------------------------------------

                "primary_supplier_id":
                    service.primary_supplier_id,

                "primary_supplier_name":
                    service.primary_supplier_name,

                "primary_supplier_lot_id":
                    service.primary_supplier_lot_id,

                "supplier_component_category":
                    service.
                    supplier_component_category,

                "supplier_lot_quality_score":
                    round(
                        supplier_quality,
                        6,
                    ),

                "production_quality_score":
                    round(
                        production_quality,
                        6,
                    ),

                # --------------------------------------------
                # FAILURE / SERVICE EVIDENCE
                # --------------------------------------------

                "issue_category":
                    service.issue_category,

                "failure_code":
                    failure_code,

                "severity":
                    severity,

                "diagnosis":
                    service.diagnosis,

                "service_duration_hours":
                    round(
                        service_duration_hours,
                        3,
                    ),

                # --------------------------------------------
                # WARRANTY GENERATION EVIDENCE
                #
                # This probability is generator truth and
                # should later be excluded from runtime-facing
                # inference tables.
                # --------------------------------------------

                "claim_probability":
                    round(
                        claim_probability,
                        6,
                    ),

                # --------------------------------------------
                # CLAIM PROCESS
                # --------------------------------------------

                "claim_submitted_at":
                    claim_submitted_at,

                "decision_at":
                    decision_at,

                "claim_amount_inr":
                    claim_amount,

                "approved_amount_inr":
                    approved_amount,

                "claim_status":
                    claim_status,

                # --------------------------------------------
                # SYNTHETIC EVALUATION LABEL
                #
                # Keep separate from causal discovery later.
                # --------------------------------------------

                "root_cause_domain":
                    root_cause_domain,

                # --------------------------------------------
                # PROVENANCE
                # --------------------------------------------

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

        claim_counter += 1

    # ========================================================
    # DATAFRAME
    # ========================================================

    warranty_claims = pd.DataFrame(
        rows,
        columns=_warranty_columns(),
    )

    validate_warranty_claims(
        warranty_claims=
            warranty_claims,

        service_events=
            service_events,

        generation_end=
            generation_end,
    )

    return warranty_claims


# ============================================================
# COLUMN ORDER
# ============================================================


def _warranty_columns() -> list[str]:
    """
    Canonical warranty output schema.
    """

    return [
        "warranty_claim_id",

        "service_event_id",
        "delivery_id",
        "allocation_id",
        "booking_id",
        "customer_id",

        "vehicle_id",
        "vehicle_model_id",
        "vehicle_model_name",
        "variant",

        "vehicle_age_days",
        "odometer_km",

        "service_dealer_id",
        "service_dealer_name",

        "region_id",
        "region_name",

        "city_id",
        "city_name",

        "production_batch_id",

        "plant_id",
        "plant_name",

        "production_line_id",
        "production_line_name",

        "representative_machine_id",
        "representative_machine_name",

        "primary_supplier_id",
        "primary_supplier_name",
        "primary_supplier_lot_id",

        "supplier_component_category",

        "supplier_lot_quality_score",
        "production_quality_score",

        "issue_category",
        "failure_code",

        "severity",
        "diagnosis",

        "service_duration_hours",

        "claim_probability",

        "claim_submitted_at",
        "decision_at",

        "claim_amount_inr",
        "approved_amount_inr",

        "claim_status",

        "root_cause_domain",

        "data_origin",
        "generator_version",
    ]


# ============================================================
# VALIDATION
# ============================================================


def validate_warranty_claims(
    warranty_claims: pd.DataFrame,

    service_events: pd.DataFrame,

    generation_end: pd.Timestamp,
) -> None:
    """
    Validate generated warranty claims.
    """

    required = set(
        _warranty_columns()
    )

    missing = (
        required
        .difference(
            warranty_claims.columns
        )
    )

    if missing:

        raise ValueError(
            "Warranty claims are missing columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    # Zero warranty claims is technically possible.
    if warranty_claims.empty:

        return

    # ========================================================
    # UNIQUE CLAIM ID
    # ========================================================

    if warranty_claims[
        "warranty_claim_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate warranty_claim_id values found"
        )

    # One claim per service event in this PoC.
    if warranty_claims[
        "service_event_id"
    ].duplicated().any():

        raise ValueError(
            "A service event generated multiple "
            "warranty claims"
        )

    # ========================================================
    # ONLY VALID WARRANTY CANDIDATES
    # ========================================================

    candidates = (
        service_events[
            (
                service_events[
                    "service_type"
                ]
                ==
                "UNSCHEDULED_REPAIR"
            )
            &
            (
                service_events[
                    "warranty_candidate"
                ]
                .astype(bool)
            )
        ]
    )

    valid_service_ids = set(
        candidates[
            "service_event_id"
        ]
    )

    invalid_service_ids = (
        set(
            warranty_claims[
                "service_event_id"
            ]
        )
        -
        valid_service_ids
    )

    if invalid_service_ids:

        raise ValueError(
            "Warranty claims were generated from "
            "non-warranty-candidate service events"
        )

    # ========================================================
    # STATUS
    # ========================================================

    invalid_statuses = (
        set(
            warranty_claims[
                "claim_status"
            ]
        )
        -
        VALID_CLAIM_STATUSES
    )

    if invalid_statuses:

        raise ValueError(
            "Invalid warranty claim statuses found"
        )

    # ========================================================
    # ROOT CAUSE DOMAIN
    # ========================================================

    invalid_root_causes = (
        set(
            warranty_claims[
                "root_cause_domain"
            ]
        )
        -
        VALID_ROOT_CAUSE_DOMAINS
    )

    if invalid_root_causes:

        raise ValueError(
            "Invalid warranty root-cause domains found"
        )

    # ========================================================
    # AMOUNTS
    # ========================================================

    claim_amounts = pd.to_numeric(
        warranty_claims[
            "claim_amount_inr"
        ],
        errors="raise",
    )

    approved_amounts = pd.to_numeric(
        warranty_claims[
            "approved_amount_inr"
        ],
        errors="raise",
    )

    if (
        claim_amounts
        <=
        0
    ).any():

        raise ValueError(
            "claim_amount_inr must be > 0"
        )

    if (
        approved_amounts
        <
        0
    ).any():

        raise ValueError(
            "approved_amount_inr cannot be negative"
        )

    if (
        approved_amounts
        >
        claim_amounts
    ).any():

        raise ValueError(
            "approved_amount_inr cannot exceed "
            "claim_amount_inr"
        )

    # ========================================================
    # APPROVED CLAIMS
    # ========================================================

    approved = (
        warranty_claims[
            "claim_status"
        ]
        ==
        "APPROVED"
    )

    if (
        warranty_claims.loc[
            approved,
            "approved_amount_inr",
        ]
        <=
        0
    ).any():

        raise ValueError(
            "APPROVED warranty claims must "
            "have approved_amount_inr > 0"
        )

    # ========================================================
    # NON-APPROVED CLAIMS
    # ========================================================

    non_approved = (
        warranty_claims[
            "claim_status"
        ]
        !=
        "APPROVED"
    )

    if not (
        warranty_claims.loc[
            non_approved,
            "approved_amount_inr",
        ]
        ==
        0
    ).all():

        raise ValueError(
            "Non-approved warranty claims must "
            "have approved_amount_inr=0"
        )

    # ========================================================
    # CLAIM PROBABILITY
    # ========================================================

    probabilities = pd.to_numeric(
        warranty_claims[
            "claim_probability"
        ],
        errors="raise",
    )

    if (
        (
            probabilities < 0
        )
        |
        (
            probabilities > 1
        )
    ).any():

        raise ValueError(
            "claim_probability must be "
            "between 0 and 1"
        )

    # ========================================================
    # LOOKUP
    # ========================================================

    service_lookup = {
        str(
            row.service_event_id
        ):
            row

        for row
        in service_events.itertuples(
            index=False
        )
    }

    # ========================================================
    # ROW CONSISTENCY
    # ========================================================

    for claim in warranty_claims.itertuples(
        index=False
    ):

        service = (
            service_lookup[
                str(
                    claim.service_event_id
                )
            ]
        )

        # ----------------------------------------------------
        # Vehicle
        # ----------------------------------------------------

        if (
            str(
                claim.vehicle_id
            )
            !=
            str(
                service.vehicle_id
            )
        ):

            raise ValueError(
                f"{claim.warranty_claim_id}: "
                "vehicle mismatch"
            )

        # ----------------------------------------------------
        # Production batch
        # ----------------------------------------------------

        if (
            str(
                claim.production_batch_id
            )
            !=
            str(
                service.production_batch_id
            )
        ):

            raise ValueError(
                f"{claim.warranty_claim_id}: "
                "production batch mismatch"
            )

        # ----------------------------------------------------
        # Supplier lot
        # ----------------------------------------------------

        if (
            str(
                claim.primary_supplier_lot_id
            )
            !=
            str(
                service.primary_supplier_lot_id
            )
        ):

            raise ValueError(
                f"{claim.warranty_claim_id}: "
                "supplier lot mismatch"
            )

        # ----------------------------------------------------
        # Time
        # ----------------------------------------------------

        service_completed = pd.Timestamp(
            service.service_completed_at
        )

        claim_submitted = pd.Timestamp(
            claim.claim_submitted_at
        )

        if (
            claim_submitted
            <
            service_completed
        ):

            raise ValueError(
                f"{claim.warranty_claim_id}: "
                "claim submitted before "
                "service completion"
            )

        if (
            claim_submitted
            >
            generation_end
        ):

            raise ValueError(
                f"{claim.warranty_claim_id}: "
                "claim submitted after "
                "generation end"
            )

        # ----------------------------------------------------
        # Decision
        # ----------------------------------------------------

        if (
            claim.decision_at
            is not None
            and
            not pd.isna(
                claim.decision_at
            )
        ):

            decision_at = pd.Timestamp(
                claim.decision_at
            )

            if (
                decision_at
                <
                claim_submitted
            ):

                raise ValueError(
                    f"{claim.warranty_claim_id}: "
                    "decision before claim submission"
                )

            if (
                decision_at
                >
                generation_end
            ):

                raise ValueError(
                    f"{claim.warranty_claim_id}: "
                    "decision exceeds generation end"
                )


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_warranty_master(
    service_events: pd.DataFrame,

    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Public entry point later used by generate_all.py.
    """

    return generate_warranty_claims(
        service_events=
            service_events,

        generation=
            generation,
    )


# ============================================================
# LOCAL TEST
#
# Uses the already implemented generator chain.
# ============================================================


if __name__ == "__main__":

    from data.generators.master.geography import (
        generate_geography,
    )

    from data.generators.master.vehicle_models import (
        generate_vehicle_models,
    )

    from data.generators.master.dealers import (
        generate_dealer_master,
    )

    from data.generators.master.plants import (
        generate_plant_master,
    )

    from data.generators.master.machines import (
        generate_machine_master,
    )

    from data.generators.auto.customers import (
        generate_customer_master,
    )

    from data.generators.auto.leads import (
        generate_lead_master,
    )

    from data.generators.auto.followups import (
        generate_followup_master,
    )

    from data.generators.auto.test_drives import (
        generate_test_drive_master,
    )

    from data.generators.auto.bookings import (
        generate_booking_master,
    )

    from data.generators.auto.finance_applications import (
        generate_finance_application_master,
    )

    from data.generators.auto.cancellations import (
        generate_cancellation_master,
    )

    from data.generators.auto.suppliers import (
        generate_supplier_master,
    )

    from data.generators.auto.production import (
        generate_production_batch_master,
    )

    from data.generators.auto.allocations import (
        generate_allocation_master,
    )

    from data.generators.auto.deliveries import (
        generate_delivery_master,
    )

    from data.generators.auto.service import (
        generate_service_master,
    )

    # ========================================================
    # MASTER
    # ========================================================

    (
        regions_df,
        cities_df,
    ) = generate_geography()

    vehicle_models_df = (
        generate_vehicle_models()
    )

    dealers_df = (
        generate_dealer_master(
            regions=regions_df,
            cities=cities_df,
        )
    )

    (
        plants_df,
        production_lines_df,
    ) = generate_plant_master(
        cities_df
    )

    machines_df = (
        generate_machine_master(
            production_lines_df
        )
    )

    # ========================================================
    # AUTO COMMERCIAL
    # ========================================================

    customers_df = (
        generate_customer_master(
            regions=regions_df,
            cities=cities_df,
            vehicle_models=vehicle_models_df,
        )
    )

    leads_df = (
        generate_lead_master(
            customers=customers_df,
            dealers=dealers_df,
            vehicle_models=vehicle_models_df,
        )
    )

    followups_df = (
        generate_followup_master(
            leads=leads_df,
            dealers=dealers_df,
        )
    )

    test_drives_df = (
        generate_test_drive_master(
            leads=leads_df,
            followups=followups_df,
        )
    )

    bookings_df = (
        generate_booking_master(
            customers=customers_df,
            leads=leads_df,
            followups=followups_df,
            test_drives=test_drives_df,
            vehicle_models=vehicle_models_df,
        )
    )

    finance_df = (
        generate_finance_application_master(
            bookings=bookings_df,
            customers=customers_df,
        )
    )

    cancellations_df = (
        generate_cancellation_master(
            bookings=bookings_df,
            finance_applications=finance_df,
        )
    )

    # ========================================================
    # MANUFACTURING
    # ========================================================

    (
        suppliers_df,
        supplier_lots_df,
    ) = generate_supplier_master(
        cities=cities_df
    )

    production_df = (
        generate_production_batch_master(
            plants=plants_df,
            production_lines=production_lines_df,
            machines=machines_df,
            vehicle_models=vehicle_models_df,
            suppliers=suppliers_df,
            supplier_lots=supplier_lots_df,
        )
    )

    # ========================================================
    # ALLOCATION
    # ========================================================

    allocations_df = (
        generate_allocation_master(
            bookings=bookings_df,
            cancellations=cancellations_df,
            production_batches=production_df,
            dealers=dealers_df,
            finance_applications=finance_df,
        )
    )

    # ========================================================
    # DELIVERY
    # ========================================================

    deliveries_df = (
        generate_delivery_master(
            bookings=bookings_df,
            allocations=allocations_df,
        )
    )

    # ========================================================
    # SERVICE
    # ========================================================

    service_df = (
        generate_service_master(
            deliveries=deliveries_df
        )
    )

    # ========================================================
    # WARRANTY
    # ========================================================

    warranty_df = (
        generate_warranty_master(
            service_events=service_df
        )
    )

    # ========================================================
    # SAMPLE
    # ========================================================

    print(
        "\n=== WARRANTY CLAIM SAMPLE ===\n"
    )

    if warranty_df.empty:

        print(
            "No warranty claims generated."
        )

    else:

        display_columns = [
            "warranty_claim_id",

            "service_event_id",

            "vehicle_id",

            "vehicle_model_name",

            "issue_category",

            "severity",

            "primary_supplier_name",

            "primary_supplier_lot_id",

            "production_batch_id",

            "claim_amount_inr",

            "approved_amount_inr",

            "claim_status",

            "root_cause_domain",
        ]

        print(
            warranty_df[
                display_columns
            ]
            .head(
                30
            )
            .to_string(
                index=False
            )
        )

    # ========================================================
    # KPI CHECK
    # ========================================================

    warranty_candidates = int(
        service_df[
            "warranty_candidate"
        ].sum()
    )

    claims_created = len(
        warranty_df
    )

    approved_count = int(
        (
            warranty_df[
                "claim_status"
            ]
            ==
            "APPROVED"
        )
        .sum()
    )

    manual_review_count = int(
        (
            warranty_df[
                "claim_status"
            ]
            ==
            "MANUAL_REVIEW"
        )
        .sum()
    )

    rejected_count = int(
        (
            warranty_df[
                "claim_status"
            ]
            ==
            "REJECTED"
        )
        .sum()
    )

    print(
        "\n=== WARRANTY KPI CHECK ===\n"
    )

    print(
        "Service events:",
        len(
            service_df
        ),
    )

    print(
        "Unscheduled repairs:",
        int(
            (
                service_df[
                    "service_type"
                ]
                ==
                "UNSCHEDULED_REPAIR"
            )
            .sum()
        ),
    )

    print(
        "Warranty candidates:",
        warranty_candidates,
    )

    print(
        "Warranty claims:",
        claims_created,
    )

    print(
        "Approved:",
        approved_count,
    )

    print(
        "Manual review:",
        manual_review_count,
    )

    print(
        "Rejected:",
        rejected_count,
    )

    if not warranty_df.empty:

        print(
            "Average claim amount:",
            round(
                warranty_df[
                    "claim_amount_inr"
                ].mean(),
                2,
            ),
        )

        print(
            "Total claimed amount:",
            round(
                warranty_df[
                    "claim_amount_inr"
                ].sum(),
                2,
            ),
        )

        print(
            "Total approved amount:",
            round(
                warranty_df[
                    "approved_amount_inr"
                ].sum(),
                2,
            ),
        )

        print(
            "\n=== ROOT CAUSE DOMAINS ===\n"
        )

        print(
            warranty_df
            .groupby(
                "root_cause_domain"
            )
            .size()
            .reset_index(
                name="claim_count"
            )
            .sort_values(
                "claim_count",
                ascending=False,
            )
            .to_string(
                index=False
            )
        )

    print(
        "\nGenerated "
        f"{len(warranty_df)} "
        "synthetic warranty claims from "
        f"{warranty_candidates} warranty candidates "
        "successfully."
    )