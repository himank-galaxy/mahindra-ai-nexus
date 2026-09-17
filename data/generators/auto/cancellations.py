"""
Synthetic Booking Cancellation generator for Mahindra AI Nexus.

Dependency chain:

Customers
    ↓
Leads
    ↓
Follow-ups
    ↓
Test Drives
    ↓
Bookings
    ↓
Finance Applications
    ↓
Cancellations

Cancellation probability starts from the configured base probability,
then is adjusted using evidence already generated in the customer journey.

Cancellation reasons are also constrained by evidence.

Examples:
- FINANCE_REJECTED is allowed only if finance status is REJECTED.
- FINANCE_TAT requires a finance application with delay/pending/review.
- DEALER_FOLLOWUP requires poor follow-up evidence.
- DELIVERY_WAIT requires a relatively long promised delivery window.

This module DOES NOT modify the bookings DataFrame.
It returns a separate cancellation-event DataFrame.

Later downstream code can derive:

    active bookings
        =
    bookings - cancelled bookings

This module DOES NOT write CSV files.

Later generate_all.py will save:

    data/synthetic/auto/cancellations.csv

All records are synthetic.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.helpers import (
    load_distribution_config,
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
# SYNTHETIC PROCESS ASSUMPTIONS
#
# These are PoC engineering assumptions.
# They are NOT real Mahindra operating thresholds.
# ============================================================

FINANCE_TAT_WARNING_HOURS = 24.0
FINANCE_TAT_SEVERE_HOURS = 48.0

DELIVERY_WAIT_WARNING_DAYS = 35
DELIVERY_WAIT_SEVERE_DAYS = 50

MAX_CANCELLATION_DELAY_DAYS = 14


# ============================================================
# BASIC HELPERS
# ============================================================


def _validate_probability(
    value: Any,
    name: str,
) -> float:
    """
    Validate probability in [0, 1].
    """

    try:
        result = float(value)

    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"{name} must be numeric"
        ) from exc

    if not 0.0 <= result <= 1.0:
        raise ValueError(
            f"{name} must be between 0 and 1"
        )

    return result


def _normalize_weights(
    weights: Mapping[str, Any],
    name: str,
) -> dict[str, float]:
    """
    Validate and normalize categorical weights.
    """

    if (
        not isinstance(
            weights,
            Mapping,
        )
        or not weights
    ):
        raise ValueError(
            f"{name} must be a non-empty mapping"
        )

    parsed: dict[str, float] = {}

    for label, raw_value in weights.items():

        try:
            value = float(
                raw_value
            )

        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"{name}.{label} must be numeric"
            ) from exc

        if value < 0:
            raise ValueError(
                f"{name}.{label} cannot be negative"
            )

        parsed[
            str(label)
        ] = value

    total = sum(
        parsed.values()
    )

    if total <= 0:
        raise ValueError(
            f"{name} must sum to > 0"
        )

    return {
        key: value / total
        for key, value
        in parsed.items()
    }


def _has_timestamp(
    value: Any,
) -> bool:
    """
    Safe test for optional pandas timestamps.
    """

    return (
        value is not None
        and not pd.isna(
            value
        )
    )


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

    end_value = time_config.get(
        "end",
        time_config.get(
            "end_date"
        ),
    )

    if end_value is None:
        raise KeyError(
            "Missing end/end_date "
            "in generation time configuration"
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

        timestamp = (
            timestamp.tz_localize(
                timezone
            )
        )

    else:

        timestamp = (
            timestamp.tz_convert(
                timezone
            )
        )

    return timestamp


# ============================================================
# INPUT VALIDATION
# ============================================================


def _validate_inputs(
    bookings: pd.DataFrame,
    finance_applications: pd.DataFrame,
) -> None:
    """
    Validate booking and finance datasets.
    """

    booking_required = {
        "booking_id",

        "lead_id",
        "customer_id",

        "dealer_id",
        "dealer_name",

        "region_id",
        "region_name",

        "city_id",
        "city_name",

        "vehicle_model_id",
        "vehicle_model_name",

        "booking_amount_inr",

        "booking_timestamp",
        "promised_delivery_date",

        "good_followup",
        "finance_assisted",
        "long_test_drive_wait",

        "booking_status",
    }

    finance_required = {
        "finance_application_id",

        "booking_id",
        "customer_id",

        "submitted_at",
        "decision_at",

        "status",
        "risk_band",

        "approval_tat_hours",
    }

    missing_booking = (
        booking_required
        .difference(
            bookings.columns
        )
    )

    if missing_booking:

        raise ValueError(
            "Bookings DataFrame is missing "
            "columns required by cancellations.py: "
            + ", ".join(
                sorted(
                    missing_booking
                )
            )
        )

    if bookings.empty:

        raise ValueError(
            "Bookings DataFrame cannot be empty"
        )

    if bookings[
        "booking_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate booking_id values found"
        )

    # --------------------------------------------------------
    # Finance DataFrame may theoretically be empty,
    # so only validate schema/duplicates when it has records.
    # --------------------------------------------------------

    if not finance_applications.empty:

        missing_finance = (
            finance_required
            .difference(
                finance_applications.columns
            )
        )

        if missing_finance:

            raise ValueError(
                "Finance applications DataFrame "
                "is missing columns required "
                "by cancellations.py: "
                + ", ".join(
                    sorted(
                        missing_finance
                    )
                )
            )

        if finance_applications[
            "finance_application_id"
        ].duplicated().any():

            raise ValueError(
                "Duplicate finance_application_id "
                "values found"
            )

        if finance_applications[
            "booking_id"
        ].duplicated().any():

            raise ValueError(
                "More than one finance application "
                "exists for a booking"
            )

        invalid_booking_ids = (
            set(
                finance_applications[
                    "booking_id"
                ]
            )
            -
            set(
                bookings[
                    "booking_id"
                ]
            )
        )

        if invalid_booking_ids:

            raise ValueError(
                "Finance applications reference "
                "invalid booking IDs"
            )


# ============================================================
# FINANCE LOOKUP
# ============================================================


def _build_finance_lookup(
    finance_applications: pd.DataFrame,
) -> dict[str, Any]:
    """
    One finance application per finance-assisted booking.
    """

    if finance_applications.empty:
        return {}

    return {
        row.booking_id: row

        for row
        in finance_applications.itertuples(
            index=False
        )
    }


# ============================================================
# DELIVERY WAIT
# ============================================================


def _calculate_promised_wait_days(
    booking_timestamp: Any,
    promised_delivery_date: Any,
) -> float:
    """
    Calculate promised booking-to-delivery duration.
    """

    booking_time = pd.Timestamp(
        booking_timestamp
    )

    promised_time = pd.Timestamp(
        promised_delivery_date
    )

    wait_days = (
        promised_time
        - booking_time
    ).total_seconds() / 86400.0

    return max(
        0.0,
        wait_days,
    )


# ============================================================
# CANCELLATION PROBABILITY
# ============================================================


def _calculate_cancellation_probability(
    base_probability: float,
    finance_status: str | None,
    approval_tat_hours: float | None,
    good_followup: bool,
    long_test_drive_wait: bool,
    promised_wait_days: float,
) -> float:
    """
    Start from configured base cancellation probability,
    then adjust using previously generated evidence.

    We deliberately do NOT generate an unrelated random
    cancellation risk score.
    """

    probability = float(
        base_probability
    )

    # ========================================================
    # FINANCE EFFECTS
    # ========================================================

    if finance_status == "REJECTED":

        # Rejected financing creates a strong cancellation risk.
        probability = max(
            probability,
            0.65,
        )

    elif finance_status == "MANUAL_REVIEW":

        probability += 0.07

    elif finance_status == "PENDING":

        probability += 0.08

    elif finance_status == "APPROVED":

        # Successful finance approval slightly reduces risk.
        probability -= 0.015

    # --------------------------------------------------------
    # Finance turnaround pressure
    # --------------------------------------------------------

    if approval_tat_hours is not None:

        if (
            approval_tat_hours
            >= FINANCE_TAT_SEVERE_HOURS
        ):

            probability += 0.12

        elif (
            approval_tat_hours
            >= FINANCE_TAT_WARNING_HOURS
        ):

            probability += 0.06

    # ========================================================
    # DEALER FOLLOW-UP
    # ========================================================

    if not good_followup:

        probability += 0.04

    # ========================================================
    # TEST-DRIVE WAIT
    # ========================================================

    if long_test_drive_wait:

        probability += 0.025

    # ========================================================
    # PROMISED DELIVERY WAIT
    # ========================================================

    if (
        promised_wait_days
        >= DELIVERY_WAIT_SEVERE_DAYS
    ):

        probability += 0.10

    elif (
        promised_wait_days
        >= DELIVERY_WAIT_WARNING_DAYS
    ):

        probability += 0.05

    return float(
        np.clip(
            probability,
            0.01,
            0.90,
        )
    )


# ============================================================
# REASON WEIGHTS
# ============================================================


def _build_reason_probabilities(
    configured_weights: Mapping[str, float],
    finance_status: str | None,
    approval_tat_hours: float | None,
    good_followup: bool,
    promised_wait_days: float,
) -> dict[str, float]:
    """
    Filter cancellation reasons according to available evidence.

    Configured reason weights remain the starting point.
    """

    candidate_weights: dict[
        str,
        float,
    ] = {}

    # ========================================================
    # FINANCE REJECTED
    #
    # Impossible unless finance really was rejected.
    # ========================================================

    if (
        finance_status
        == "REJECTED"
    ):

        candidate_weights[
            "FINANCE_REJECTED"
        ] = (
            configured_weights[
                "FINANCE_REJECTED"
            ]
            * 5.0
        )

    # ========================================================
    # FINANCE TAT
    # ========================================================

    finance_tat_problem = False

    if finance_status in {
        "PENDING",
        "MANUAL_REVIEW",
    }:

        finance_tat_problem = True

    if (
        approval_tat_hours is not None
        and
        approval_tat_hours
        >= FINANCE_TAT_WARNING_HOURS
    ):

        finance_tat_problem = True

    if finance_tat_problem:

        multiplier = 2.0

        if (
            approval_tat_hours is not None
            and
            approval_tat_hours
            >= FINANCE_TAT_SEVERE_HOURS
        ):

            multiplier = 3.0

        candidate_weights[
            "FINANCE_TAT"
        ] = (
            configured_weights[
                "FINANCE_TAT"
            ]
            * multiplier
        )

    # ========================================================
    # DELIVERY WAIT
    # ========================================================

    if (
        promised_wait_days
        >= DELIVERY_WAIT_WARNING_DAYS
    ):

        multiplier = 1.5

        if (
            promised_wait_days
            >= DELIVERY_WAIT_SEVERE_DAYS
        ):

            multiplier = 2.5

        candidate_weights[
            "DELIVERY_WAIT"
        ] = (
            configured_weights[
                "DELIVERY_WAIT"
            ]
            * multiplier
        )

    # ========================================================
    # DEALER FOLLOW-UP
    # ========================================================

    if not good_followup:

        candidate_weights[
            "DEALER_FOLLOWUP"
        ] = (
            configured_weights[
                "DEALER_FOLLOWUP"
            ]
            * 2.0
        )

    # ========================================================
    # LATENT / EXTERNAL CUSTOMER REASONS
    #
    # These do not require a contradictory system event,
    # so they remain available as baseline reasons.
    # ========================================================

    for reason in (
        "COMPETITOR_OFFER",
        "PRICE",
        "MODEL_CHANGE",
        "CUSTOMER_CHANGE",
        "OTHER",
    ):

        candidate_weights[
            reason
        ] = (
            configured_weights[
                reason
            ]
        )

    if not candidate_weights:

        candidate_weights[
            "OTHER"
        ] = 1.0

    total = sum(
        candidate_weights.values()
    )

    if total <= 0:

        raise ValueError(
            "Eligible cancellation reason "
            "weights sum to zero"
        )

    return {
        reason:
            weight / total

        for reason, weight
        in candidate_weights.items()
    }


# ============================================================
# CANCELLATION ANCHOR
# ============================================================


def _get_cancellation_anchor(
    booking: Any,
    finance_application: Any | None,
    cancellation_reason: str,
) -> pd.Timestamp:
    """
    Choose the latest logically relevant event.

    Example:

    FINANCE_REJECTED
        ↓
    cancellation cannot occur before finance rejection.
    """

    booking_time = pd.Timestamp(
        booking.booking_timestamp
    )

    anchor = booking_time

    if finance_application is None:

        return anchor

    if cancellation_reason in {
        "FINANCE_REJECTED",
        "FINANCE_TAT",
    }:

        if _has_timestamp(
            finance_application.decision_at
        ):

            anchor = max(
                anchor,
                pd.Timestamp(
                    finance_application.
                    decision_at
                ),
            )

        elif _has_timestamp(
            finance_application.submitted_at
        ):

            anchor = max(
                anchor,
                pd.Timestamp(
                    finance_application.
                    submitted_at
                ),
            )

    return anchor


# ============================================================
# CANCELLATION TIME
# ============================================================


def _generate_cancellation_time(
    rng: np.random.Generator,
    anchor: pd.Timestamp,
    generation_end: pd.Timestamp,
    reason: str,
) -> pd.Timestamp | None:
    """
    Generate timestamp after relevant journey event.
    """

    anchor = pd.Timestamp(
        anchor
    )

    if anchor >= generation_end:

        return None

    available_hours = (
        generation_end
        - anchor
    ).total_seconds() / 3600.0

    if available_hours <= 0:

        return None

    # --------------------------------------------------------
    # Finance rejection typically causes a faster exit.
    # --------------------------------------------------------

    if reason == "FINANCE_REJECTED":

        min_hours = 0.5
        max_hours = 48.0

    elif reason == "FINANCE_TAT":

        min_hours = 4.0
        max_hours = 96.0

    else:

        min_hours = 1.0

        max_hours = (
            MAX_CANCELLATION_DELAY_DAYS
            * 24.0
        )

    actual_max = min(
        max_hours,
        available_hours,
    )

    actual_min = min(
        min_hours,
        actual_max,
    )

    delay_hours = float(
        rng.uniform(
            actual_min,
            actual_max,
        )
    )

    return (
        anchor
        + timedelta(
            hours=delay_hours
        )
    )


# ============================================================
# GENERATOR
# ============================================================


def generate_cancellations(
    bookings: pd.DataFrame,
    finance_applications: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate booking cancellation events.

    Not every booking gets a cancellation.

    Only bookings where the generated cancellation event
    occurs create rows in the returned DataFrame.
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    if distributions is None:

        distributions = (
            load_distribution_config()
        )

    # ========================================================
    # INPUT VALIDATION
    # ========================================================

    _validate_inputs(
        bookings=bookings,
        finance_applications=
            finance_applications,
    )

    # ========================================================
    # EXACT CONFIG
    # ========================================================

    cancellation_config = (
        distributions.get(
            "cancellations"
        )
    )

    if not isinstance(
        cancellation_config,
        Mapping,
    ):

        raise KeyError(
            "Missing distributions.cancellations "
            "configuration"
        )

    required_keys = {
        "base_probability",
        "reason_weights",
    }

    missing = (
        required_keys
        .difference(
            cancellation_config.keys()
        )
    )

    if missing:

        raise KeyError(
            "distributions.cancellations "
            "is missing: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    base_probability = (
        _validate_probability(
            cancellation_config[
                "base_probability"
            ],
            (
                "cancellations."
                "base_probability"
            ),
        )
    )

    reason_weights = (
        _normalize_weights(
            cancellation_config[
                "reason_weights"
            ],
            (
                "cancellations."
                "reason_weights"
            ),
        )
    )

    required_reasons = {
        "FINANCE_REJECTED",
        "FINANCE_TAT",
        "DELIVERY_WAIT",
        "COMPETITOR_OFFER",
        "PRICE",
        "MODEL_CHANGE",
        "DEALER_FOLLOWUP",
        "CUSTOMER_CHANGE",
        "OTHER",
    }

    missing_reasons = (
        required_reasons
        -
        set(
            reason_weights.keys()
        )
    )

    if missing_reasons:

        raise KeyError(
            "cancellations.reason_weights "
            "is missing: "
            + ", ".join(
                sorted(
                    missing_reasons
                )
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
            "auto.cancellations",
        )
    )

    # ========================================================
    # TIME
    # ========================================================

    generation_end = (
        _get_generation_end(
            generation
        )
    )

    # ========================================================
    # FINANCE LOOKUP
    # ========================================================

    finance_lookup = (
        _build_finance_lookup(
            finance_applications
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
    # GENERATION
    # ========================================================

    rows: list[
        dict[str, Any]
    ] = []

    cancellation_counter = 1

    for booking in bookings.itertuples(
        index=False
    ):

        # ----------------------------------------------------
        # Only active newly generated bookings are eligible.
        # ----------------------------------------------------

        if (
            booking.booking_status
            != "ACTIVE"
        ):

            continue

        finance_application = (
            finance_lookup.get(
                booking.booking_id
            )
        )

        # ====================================================
        # FINANCE EVIDENCE
        # ====================================================

        finance_application_id = None
        finance_status = None
        finance_risk_band = None
        approval_tat_hours = None

        if finance_application is not None:

            finance_application_id = (
                finance_application.
                finance_application_id
            )

            finance_status = str(
                finance_application.status
            )

            finance_risk_band = str(
                finance_application.risk_band
            )

            approval_tat_hours = float(
                finance_application.
                approval_tat_hours
            )

        # ----------------------------------------------------
        # A finance-assisted booking must have an application.
        # ----------------------------------------------------

        if (
            bool(
                booking.finance_assisted
            )
            and
            finance_application is None
        ):

            raise ValueError(
                f"Finance-assisted booking "
                f"{booking.booking_id} has no "
                "finance application"
            )

        # ----------------------------------------------------
        # A non-finance booking should not unexpectedly
        # have a finance application.
        # ----------------------------------------------------

        if (
            not bool(
                booking.finance_assisted
            )
            and
            finance_application is not None
        ):

            raise ValueError(
                f"Non-finance booking "
                f"{booking.booking_id} unexpectedly "
                "has a finance application"
            )

        # ====================================================
        # DELIVERY PROMISE
        # ====================================================

        promised_wait_days = (
            _calculate_promised_wait_days(
                booking_timestamp=
                    booking.booking_timestamp,

                promised_delivery_date=
                    booking.
                    promised_delivery_date,
            )
        )

        # ====================================================
        # CANCELLATION PROBABILITY
        # ====================================================

        cancellation_probability = (
            _calculate_cancellation_probability(
                base_probability=
                    base_probability,

                finance_status=
                    finance_status,

                approval_tat_hours=
                    approval_tat_hours,

                good_followup=
                    bool(
                        booking.good_followup
                    ),

                long_test_drive_wait=
                    bool(
                        booking.
                        long_test_drive_wait
                    ),

                promised_wait_days=
                    promised_wait_days,
            )
        )

        cancelled = bool(
            float(
                rng.random()
            )
            <
            cancellation_probability
        )

        if not cancelled:
            continue

        # ====================================================
        # REASON
        # ====================================================

        eligible_reason_weights = (
            _build_reason_probabilities(
                configured_weights=
                    reason_weights,

                finance_status=
                    finance_status,

                approval_tat_hours=
                    approval_tat_hours,

                good_followup=
                    bool(
                        booking.good_followup
                    ),

                promised_wait_days=
                    promised_wait_days,
            )
        )

        reason_names = list(
            eligible_reason_weights.keys()
        )

        reason_probabilities = np.asarray(
            list(
                eligible_reason_weights.values()
            ),
            dtype=float,
        )

        cancellation_reason = str(
            rng.choice(
                reason_names,
                p=
                    reason_probabilities,
            )
        )

        # ====================================================
        # TIMESTAMP
        # ====================================================

        anchor = (
            _get_cancellation_anchor(
                booking=
                    booking,

                finance_application=
                    finance_application,

                cancellation_reason=
                    cancellation_reason,
            )
        )

        cancelled_at = (
            _generate_cancellation_time(
                rng=rng,

                anchor=
                    anchor,

                generation_end=
                    generation_end,

                reason=
                    cancellation_reason,
            )
        )

        # No valid future timestamp is available.
        if cancelled_at is None:

            continue

        # ====================================================
        # REFUND
        #
        # Synthetic refund assumption.
        #
        # We keep most of the booking amount refundable,
        # with a small reason-dependent deduction.
        # ====================================================

        booking_amount = int(
            booking.booking_amount_inr
        )

        if cancellation_reason in {
            "FINANCE_REJECTED",
            "FINANCE_TAT",
        }:

            refund_factor = float(
                rng.uniform(
                    0.97,
                    1.00,
                )
            )

        elif cancellation_reason in {
            "DELIVERY_WAIT",
            "DEALER_FOLLOWUP",
        }:

            refund_factor = float(
                rng.uniform(
                    0.95,
                    1.00,
                )
            )

        else:

            refund_factor = float(
                rng.uniform(
                    0.90,
                    0.98,
                )
            )

        refund_amount = int(
            round(
                booking_amount
                * refund_factor
            )
        )

        refund_amount = min(
            booking_amount,
            max(
                refund_amount,
                0,
            ),
        )

        retained_amount = (
            booking_amount
            - refund_amount
        )

        # ====================================================
        # RECORD
        # ====================================================

        rows.append(
            {
                "cancellation_id":
                    make_entity_id(
                        "cancellation",
                        cancellation_counter,
                        width=6,
                    ),

                # --------------------------------------------
                # Journey
                # --------------------------------------------

                "booking_id":
                    booking.booking_id,

                "lead_id":
                    booking.lead_id,

                "customer_id":
                    booking.customer_id,

                # --------------------------------------------
                # Finance
                # --------------------------------------------

                "finance_application_id":
                    finance_application_id,

                "finance_status":
                    finance_status,

                "finance_risk_band":
                    finance_risk_band,

                "finance_approval_tat_hours":
                    approval_tat_hours,

                # --------------------------------------------
                # Dealer
                # --------------------------------------------

                "dealer_id":
                    booking.dealer_id,

                "dealer_name":
                    booking.dealer_name,

                # --------------------------------------------
                # Geography
                # --------------------------------------------

                "region_id":
                    booking.region_id,

                "region_name":
                    booking.region_name,

                "city_id":
                    booking.city_id,

                "city_name":
                    booking.city_name,

                # --------------------------------------------
                # Vehicle
                # --------------------------------------------

                "vehicle_model_id":
                    booking.vehicle_model_id,

                "vehicle_model_name":
                    booking.vehicle_model_name,

                # --------------------------------------------
                # Evidence
                # --------------------------------------------

                "good_followup":
                    bool(
                        booking.good_followup
                    ),

                "long_test_drive_wait":
                    bool(
                        booking.
                        long_test_drive_wait
                    ),

                "promised_delivery_wait_days":
                    round(
                        promised_wait_days,
                        3,
                    ),

                "cancellation_probability":
                    round(
                        cancellation_probability,
                        6,
                    ),

                # --------------------------------------------
                # Cancellation
                # --------------------------------------------

                "cancellation_reason":
                    cancellation_reason,

                "cancelled_at":
                    cancelled_at,

                # --------------------------------------------
                # Commercial
                # --------------------------------------------

                "booking_amount_inr":
                    booking_amount,

                "refund_amount_inr":
                    refund_amount,

                "retained_amount_inr":
                    retained_amount,

                # --------------------------------------------
                # Status
                # --------------------------------------------

                "cancellation_status":
                    "CONFIRMED",

                # --------------------------------------------
                # Provenance
                # --------------------------------------------

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

        cancellation_counter += 1

    # ========================================================
    # DATAFRAME
    # ========================================================

    cancellations = pd.DataFrame(
        rows,
        columns=[
            "cancellation_id",

            "booking_id",
            "lead_id",
            "customer_id",

            "finance_application_id",
            "finance_status",
            "finance_risk_band",
            "finance_approval_tat_hours",

            "dealer_id",
            "dealer_name",

            "region_id",
            "region_name",

            "city_id",
            "city_name",

            "vehicle_model_id",
            "vehicle_model_name",

            "good_followup",
            "long_test_drive_wait",

            "promised_delivery_wait_days",

            "cancellation_probability",
            "cancellation_reason",

            "cancelled_at",

            "booking_amount_inr",
            "refund_amount_inr",
            "retained_amount_inr",

            "cancellation_status",

            "data_origin",
            "generator_version",
        ],
    )

    validate_cancellations(
        cancellations=
            cancellations,

        bookings=
            bookings,

        finance_applications=
            finance_applications,

        valid_reasons=
            required_reasons,

        generation_end=
            generation_end,
    )

    return cancellations


# ============================================================
# VALIDATION
# ============================================================


def validate_cancellations(
    cancellations: pd.DataFrame,
    bookings: pd.DataFrame,
    finance_applications: pd.DataFrame,
    valid_reasons: set[str],
    generation_end: pd.Timestamp,
) -> None:
    """
    Validate cancellation-event records.
    """

    required_columns = {
        "cancellation_id",

        "booking_id",
        "lead_id",
        "customer_id",

        "finance_application_id",
        "finance_status",
        "finance_risk_band",
        "finance_approval_tat_hours",

        "dealer_id",
        "dealer_name",

        "region_id",
        "region_name",

        "city_id",
        "city_name",

        "vehicle_model_id",
        "vehicle_model_name",

        "good_followup",
        "long_test_drive_wait",

        "promised_delivery_wait_days",

        "cancellation_probability",
        "cancellation_reason",

        "cancelled_at",

        "booking_amount_inr",
        "refund_amount_inr",
        "retained_amount_inr",

        "cancellation_status",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        .difference(
            cancellations.columns
        )
    )

    if missing:

        raise ValueError(
            "Cancellations DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    # Zero cancellations is technically possible.
    if cancellations.empty:
        return

    # ========================================================
    # UNIQUE IDS
    # ========================================================

    if cancellations[
        "cancellation_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate cancellation_id values found"
        )

    # One confirmed cancellation per booking.
    if cancellations[
        "booking_id"
    ].duplicated().any():

        raise ValueError(
            "A booking has more than one cancellation"
        )

    # ========================================================
    # BOOKING FK
    # ========================================================

    invalid_bookings = (
        set(
            cancellations[
                "booking_id"
            ]
        )
        -
        set(
            bookings[
                "booking_id"
            ]
        )
    )

    if invalid_bookings:

        raise ValueError(
            "Cancellations reference invalid booking IDs"
        )

    # ========================================================
    # REASON
    # ========================================================

    invalid_reasons = (
        set(
            cancellations[
                "cancellation_reason"
            ]
        )
        -
        valid_reasons
    )

    if invalid_reasons:

        raise ValueError(
            "Invalid cancellation reasons found: "
            + ", ".join(
                sorted(
                    invalid_reasons
                )
            )
        )

    # ========================================================
    # PROBABILITY
    # ========================================================

    probabilities = pd.to_numeric(
        cancellations[
            "cancellation_probability"
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
            "cancellation_probability "
            "must be between 0 and 1"
        )

    # ========================================================
    # COMMERCIAL VALUES
    # ========================================================

    booking_amounts = pd.to_numeric(
        cancellations[
            "booking_amount_inr"
        ],
        errors="raise",
    )

    refunds = pd.to_numeric(
        cancellations[
            "refund_amount_inr"
        ],
        errors="raise",
    )

    retained = pd.to_numeric(
        cancellations[
            "retained_amount_inr"
        ],
        errors="raise",
    )

    if (
        booking_amounts <= 0
    ).any():

        raise ValueError(
            "booking_amount_inr must be > 0"
        )

    if (
        refunds < 0
    ).any():

        raise ValueError(
            "refund_amount_inr cannot be negative"
        )

    if (
        refunds
        > booking_amounts
    ).any():

        raise ValueError(
            "refund_amount_inr cannot exceed "
            "booking_amount_inr"
        )

    if (
        retained < 0
    ).any():

        raise ValueError(
            "retained_amount_inr cannot be negative"
        )

    if not (
        retained
        ==
        (
            booking_amounts
            - refunds
        )
    ).all():

        raise ValueError(
            "retained_amount_inr does not equal "
            "booking amount - refund"
        )

    # ========================================================
    # STATUS
    # ========================================================

    if not (
        cancellations[
            "cancellation_status"
        ]
        ==
        "CONFIRMED"
    ).all():

        raise ValueError(
            "Generated cancellation records "
            "must have CONFIRMED status"
        )

    # ========================================================
    # LOOKUPS
    # ========================================================

    booking_lookup = {
        row.booking_id: row

        for row
        in bookings.itertuples(
            index=False
        )
    }

    finance_lookup = {}

    if not finance_applications.empty:

        finance_lookup = {
            row.booking_id: row

            for row
            in finance_applications.itertuples(
                index=False
            )
        }

    # ========================================================
    # ROW-LEVEL CONSISTENCY
    # ========================================================

    for cancellation in cancellations.itertuples(
        index=False
    ):

        booking = (
            booking_lookup[
                cancellation.booking_id
            ]
        )

        # ----------------------------------------------------
        # Journey IDs
        # ----------------------------------------------------

        if (
            cancellation.lead_id
            != booking.lead_id
        ):

            raise ValueError(
                "lead_id mismatch for "
                f"{cancellation.cancellation_id}"
            )

        if (
            cancellation.customer_id
            != booking.customer_id
        ):

            raise ValueError(
                "customer_id mismatch for "
                f"{cancellation.cancellation_id}"
            )

        if (
            cancellation.dealer_id
            != booking.dealer_id
        ):

            raise ValueError(
                "dealer_id mismatch for "
                f"{cancellation.cancellation_id}"
            )

        if (
            cancellation.vehicle_model_id
            != booking.vehicle_model_id
        ):

            raise ValueError(
                "vehicle_model_id mismatch for "
                f"{cancellation.cancellation_id}"
            )

        # ----------------------------------------------------
        # Time
        # ----------------------------------------------------

        booking_time = pd.Timestamp(
            booking.booking_timestamp
        )

        cancelled_at = pd.Timestamp(
            cancellation.cancelled_at
        )

        if cancelled_at < booking_time:

            raise ValueError(
                f"{cancellation.cancellation_id}: "
                "cancellation occurs before booking"
            )

        if cancelled_at > generation_end:

            raise ValueError(
                f"{cancellation.cancellation_id}: "
                "cancellation exceeds generation end"
            )

        # ====================================================
        # FINANCE REASON CONSISTENCY
        # ====================================================

        if (
            cancellation.cancellation_reason
            == "FINANCE_REJECTED"
        ):

            finance = finance_lookup.get(
                cancellation.booking_id
            )

            if finance is None:

                raise ValueError(
                    "FINANCE_REJECTED cancellation "
                    "has no finance application"
                )

            if (
                finance.status
                != "REJECTED"
            ):

                raise ValueError(
                    "FINANCE_REJECTED reason used "
                    "for a non-rejected application"
                )

        # ====================================================
        # FINANCE TAT CONSISTENCY
        # ====================================================

        if (
            cancellation.cancellation_reason
            == "FINANCE_TAT"
        ):

            finance = finance_lookup.get(
                cancellation.booking_id
            )

            if finance is None:

                raise ValueError(
                    "FINANCE_TAT cancellation "
                    "has no finance application"
                )

            valid_tat_reason = (
                finance.status
                in {
                    "PENDING",
                    "MANUAL_REVIEW",
                }
                or
                float(
                    finance.
                    approval_tat_hours
                )
                >=
                FINANCE_TAT_WARNING_HOURS
            )

            if not valid_tat_reason:

                raise ValueError(
                    "FINANCE_TAT reason used "
                    "without TAT evidence"
                )

        # ====================================================
        # DELIVERY WAIT CONSISTENCY
        # ====================================================

        if (
            cancellation.cancellation_reason
            == "DELIVERY_WAIT"
        ):

            if (
                float(
                    cancellation.
                    promised_delivery_wait_days
                )
                <
                DELIVERY_WAIT_WARNING_DAYS
            ):

                raise ValueError(
                    "DELIVERY_WAIT reason used "
                    "without long promised wait"
                )

        # ====================================================
        # FOLLOW-UP CONSISTENCY
        # ====================================================

        if (
            cancellation.cancellation_reason
            == "DEALER_FOLLOWUP"
        ):

            if bool(
                cancellation.good_followup
            ):

                raise ValueError(
                    "DEALER_FOLLOWUP reason used "
                    "despite good follow-up evidence"
                )


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_cancellation_master(
    bookings: pd.DataFrame,
    finance_applications: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Public entry point later used by generate_all.py.
    """

    return generate_cancellations(
        bookings=bookings,
        finance_applications=
            finance_applications,
        generation=generation,
        distributions=distributions,
    )


# ============================================================
# LOCAL TEST
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

    # --------------------------------------------------------
    # MASTER
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # AUTO JOURNEY
    # --------------------------------------------------------

    customers_df = (
        generate_customer_master(
            regions=regions_df,
            cities=cities_df,
            vehicle_models=
                vehicle_models_df,
        )
    )

    leads_df = (
        generate_lead_master(
            customers=customers_df,
            dealers=dealers_df,
            vehicle_models=
                vehicle_models_df,
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
            vehicle_models=
                vehicle_models_df,
        )
    )

    finance_applications_df = (
        generate_finance_application_master(
            bookings=bookings_df,
            customers=customers_df,
        )
    )

    # --------------------------------------------------------
    # CANCELLATIONS
    # --------------------------------------------------------

    cancellations_df = (
        generate_cancellation_master(
            bookings=bookings_df,
            finance_applications=
                finance_applications_df,
        )
    )

    print(
        "\n=== CANCELLATION SAMPLE ===\n"
    )

    if cancellations_df.empty:

        print(
            "No cancellations generated."
        )

    else:

        display_columns = [
            "cancellation_id",
            "booking_id",

            "city_name",
            "vehicle_model_name",

            "finance_status",

            "good_followup",
            "promised_delivery_wait_days",

            "cancellation_probability",
            "cancellation_reason",

            "booking_amount_inr",
            "refund_amount_inr",

            "cancelled_at",
        ]

        print(
            cancellations_df[
                display_columns
            ]
            .head(30)
            .to_string(
                index=False
            )
        )

    print(
        "\n=== CANCELLATION KPI CHECK ===\n"
    )

    cancellation_rate = (
        len(
            cancellations_df
        )
        /
        len(
            bookings_df
        )
    )

    print(
        "Bookings:",
        len(
            bookings_df
        ),
    )

    print(
        "Cancellations:",
        len(
            cancellations_df
        ),
    )

    print(
        "Cancellation rate:",
        round(
            cancellation_rate,
            4,
        ),
    )

    if not cancellations_df.empty:

        print(
            "\n=== CANCELLATION REASONS ===\n"
        )

        print(
            cancellations_df
            .groupby(
                "cancellation_reason"
            )
            .size()
            .reset_index(
                name="cancellation_count"
            )
            .sort_values(
                "cancellation_count",
                ascending=False,
            )
            .to_string(
                index=False
            )
        )

        print(
            "\n=== CANCELLATIONS BY REGION ===\n"
        )

        print(
            cancellations_df
            .groupby(
                "region_name"
            )
            .size()
            .reset_index(
                name="cancellation_count"
            )
            .to_string(
                index=False
            )
        )

        # ----------------------------------------------------
        # Verify rejected-finance cancellation reason
        # ----------------------------------------------------

        finance_rejected = (
            cancellations_df[
                cancellations_df[
                    "cancellation_reason"
                ]
                ==
                "FINANCE_REJECTED"
            ]
        )

        print(
            "\nFINANCE_REJECTED "
            "cancellations:",
            len(
                finance_rejected
            ),
        )

        if not finance_rejected.empty:

            print(
                "All have finance status REJECTED:",
                bool(
                    (
                        finance_rejected[
                            "finance_status"
                        ]
                        ==
                        "REJECTED"
                    ).all()
                ),
            )

        # ----------------------------------------------------
        # Remaining active bookings
        # ----------------------------------------------------

        cancelled_booking_ids = set(
            cancellations_df[
                "booking_id"
            ]
        )

        active_bookings = (
            bookings_df[
                ~bookings_df[
                    "booking_id"
                ].isin(
                    cancelled_booking_ids
                )
            ]
        )

        print(
            "Remaining active bookings:",
            len(
                active_bookings
            ),
        )

    print(
        "\nGenerated "
        f"{len(cancellations_df)} "
        "synthetic cancellations from "
        f"{len(bookings_df)} bookings "
        "successfully."
    )