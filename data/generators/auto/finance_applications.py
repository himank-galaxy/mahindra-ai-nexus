"""
Synthetic Auto Finance Application generator
for Mahindra AI Nexus.

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

Only finance-assisted bookings create finance applications.

This module DOES NOT write CSV files.

Later generate_all.py will save:

    data/synthetic/auto/finance_applications.csv

All records are synthetic.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.distributions import (
    sample_distribution,
)

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
# ALLOWED VALUES
# ============================================================

ALLOWED_STATUSES = {
    "APPROVED",
    "MANUAL_REVIEW",
    "REJECTED",
    "PENDING",
}

ALLOWED_RISK_BANDS = {
    "LOW",
    "MEDIUM",
    "HIGH",
}

ALLOWED_INCOME_BANDS = {
    "LOW",
    "MEDIUM",
    "HIGH",
}


# ============================================================
# BASIC HELPERS
# ============================================================


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

    parsed: dict[
        str,
        float,
    ] = {}

    for label, raw_value in weights.items():

        try:
            value = float(
                raw_value
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise TypeError(
                f"{name}.{label} "
                "must be numeric"
            ) from exc

        if value < 0:

            raise ValueError(
                f"{name}.{label} "
                "cannot be negative"
            )

        parsed[
            str(
                label
            )
        ] = value

    total = sum(
        parsed.values()
    )

    if total <= 0:

        raise ValueError(
            f"{name} must sum to > 0"
        )

    return {
        key:
            value / total

        for key, value
        in parsed.items()
    }


# ============================================================
# GENERATION END TIME
# ============================================================


def _get_generation_end(
    generation: Mapping[
        str,
        Any,
    ],
) -> pd.Timestamp:
    """
    Read the configured synthetic-data end time.
    """

    time_config = (
        generation.get(
            "time"
        )
    )

    if not isinstance(
        time_config,
        Mapping,
    ):

        time_config = (
            generation.get(
                "time_window"
            )
        )

    if not isinstance(
        time_config,
        Mapping,
    ):

        raise KeyError(
            "Missing generation time configuration"
        )

    end_value = (
        time_config.get(
            "end",
            time_config.get(
                "end_date"
            ),
        )
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
    customers: pd.DataFrame,
) -> None:
    """
    Validate upstream datasets.
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

        "vehicle_base_price_inr",
        "booking_amount_inr",

        "booking_timestamp",

        "finance_assisted",
        "finance_preapproval_signal",

        "booking_status",
    }

    customer_required = {
        "customer_id",
        "budget_band",
        "finance_required",
    }

    datasets = (
        (
            "bookings",
            bookings,
            booking_required,
        ),

        (
            "customers",
            customers,
            customer_required,
        ),
    )

    for (
        name,
        dataframe,
        required,
    ) in datasets:

        missing = (
            required
            .difference(
                dataframe.columns
            )
        )

        if missing:

            raise ValueError(
                f"{name} DataFrame is missing "
                "required columns: "
                + ", ".join(
                    sorted(
                        missing
                    )
                )
            )

        if dataframe.empty:

            raise ValueError(
                f"{name} DataFrame cannot be empty"
            )

    if bookings[
        "booking_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate booking_id values found"
        )

    if customers[
        "customer_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate customer_id values found"
        )


# ============================================================
# INCOME BAND
# ============================================================


def _derive_income_band(
    budget_band: str,
) -> str:
    """
    Derive broad synthetic income band
    from previously generated customer budget band.

    This keeps customer attributes correlated.
    """

    budget = (
        str(
            budget_band
        )
        .strip()
        .upper()
    )

    mapping = {
        "LOW": "LOW",
        "MEDIUM": "MEDIUM",
        "HIGH": "HIGH",
        "PREMIUM": "HIGH",
    }

    return mapping.get(
        budget,
        "MEDIUM",
    )


# ============================================================
# RISK BAND
# ============================================================


def _derive_risk_band(
    bureau_score: float,
    document_completeness: float,
) -> str:
    """
    Derive finance risk from actual generated evidence.

    Higher bureau score
    +
    better document completeness
        ↓
    lower synthetic risk
    """

    bureau_component = float(
        np.clip(
            (
                bureau_score
                - 450.0
            )
            / 400.0,
            0.0,
            1.0,
        )
    )

    document_component = float(
        np.clip(
            document_completeness,
            0.0,
            1.0,
        )
    )

    quality_score = (
        0.72
        * bureau_component
        +
        0.28
        * document_component
    )

    if quality_score >= 0.72:

        return "LOW"

    if quality_score >= 0.52:

        return "MEDIUM"

    return "HIGH"


# ============================================================
# STATUS PROBABILITY
# ============================================================


def _adjust_status_probabilities(
    base_weights: Mapping[
        str,
        float,
    ],
    bureau_score: float,
    document_completeness: float,
    approval_tat_hours: float,
) -> dict[str, float]:
    """
    Use configured status_weights as baseline.

    But do NOT make finance decisions independent
    of the generated evidence.

    Better bureau/document quality increases approval likelihood.

    Poor evidence increases rejection/manual-review likelihood.

    High processing TAT increases pending likelihood.
    """

    bureau_quality = float(
        np.clip(
            (
                bureau_score
                - 450.0
            )
            / 400.0,
            0.0,
            1.0,
        )
    )

    documents = float(
        np.clip(
            document_completeness,
            0.0,
            1.0,
        )
    )

    quality = (
        0.72
        * bureau_quality
        +
        0.28
        * documents
    )

    adjusted = dict(
        base_weights
    )

    # --------------------------------------------------------
    # APPROVED
    # --------------------------------------------------------

    adjusted[
        "APPROVED"
    ] *= (
        0.55
        +
        1.10
        * quality
    )

    # --------------------------------------------------------
    # REJECTED
    # --------------------------------------------------------

    adjusted[
        "REJECTED"
    ] *= (
        1.60
        -
        1.15
        * quality
    )

    # --------------------------------------------------------
    # MANUAL REVIEW
    #
    # Middle-quality or incomplete applications
    # are more likely to need human review.
    # --------------------------------------------------------

    middle_quality = (
        1.0
        -
        min(
            abs(
                quality
                - 0.55
            )
            / 0.55,
            1.0,
        )
    )

    adjusted[
        "MANUAL_REVIEW"
    ] *= (
        0.70
        +
        0.85
        * middle_quality
        +
        0.45
        * (
            1.0
            - documents
        )
    )

    # --------------------------------------------------------
    # PENDING
    # --------------------------------------------------------

    tat_pressure = min(
        max(
            approval_tat_hours
            / 72.0,
            0.0,
        ),
        1.0,
    )

    adjusted[
        "PENDING"
    ] *= (
        0.75
        +
        1.25
        * tat_pressure
    )

    # --------------------------------------------------------
    # Normalize
    # --------------------------------------------------------

    total = sum(
        max(
            value,
            0.0,
        )
        for value
        in adjusted.values()
    )

    if total <= 0:

        raise ValueError(
            "Adjusted finance status "
            "probabilities sum to zero"
        )

    return {
        status:
            max(
                value,
                0.0,
            )
            / total

        for status, value
        in adjusted.items()
    }


# ============================================================
# SUBMISSION TIME
# ============================================================


def _generate_submitted_at(
    rng: np.random.Generator,
    booking_timestamp: pd.Timestamp,
    generation_end: pd.Timestamp,
) -> pd.Timestamp:
    """
    Finance application must occur after booking.

    Submission delay:
        15 minutes → 24 hours
    """

    booking_timestamp = pd.Timestamp(
        booking_timestamp
    )

    if (
        booking_timestamp
        >= generation_end
    ):

        return generation_end

    available_hours = (
        generation_end
        - booking_timestamp
    ).total_seconds() / 3600.0

    max_delay = min(
        24.0,
        available_hours,
    )

    if max_delay <= 0:

        return booking_timestamp

    min_delay = min(
        0.25,
        max_delay,
    )

    delay_hours = float(
        rng.uniform(
            min_delay,
            max_delay,
        )
    )

    return (
        booking_timestamp
        +
        timedelta(
            hours=delay_hours
        )
    )


# ============================================================
# REQUESTED AMOUNT
# ============================================================


def _generate_requested_amount(
    rng: np.random.Generator,
    vehicle_price: float,
    booking_amount: float,
    risk_band: str,
) -> int:
    """
    Generate requested finance amount.

    It is related to:
    - vehicle price
    - amount already paid at booking
    - synthetic risk band
    """

    remaining_price = max(
        vehicle_price
        - booking_amount,
        0.0,
    )

    if risk_band == "LOW":

        finance_share = float(
            rng.uniform(
                0.78,
                0.92,
            )
        )

    elif risk_band == "MEDIUM":

        finance_share = float(
            rng.uniform(
                0.68,
                0.86,
            )
        )

    else:

        finance_share = float(
            rng.uniform(
                0.58,
                0.78,
            )
        )

    requested_amount = min(
        remaining_price,

        vehicle_price
        * finance_share,
    )

    # Avoid meaningless tiny loan values.
    requested_amount = max(
        requested_amount,
        100000.0,
    )

    # Round to nearest ₹1,000.
    return int(
        round(
            requested_amount
            / 1000.0
        )
        * 1000
    )


# ============================================================
# APPROVED AMOUNT
# ============================================================


def _generate_approved_amount(
    rng: np.random.Generator,
    requested_amount: int,
    risk_band: str,
) -> int:
    """
    Generate approved amount.

    Approved amount can never exceed requested amount.
    """

    if risk_band == "LOW":

        factor = float(
            rng.uniform(
                0.94,
                1.00,
            )
        )

    elif risk_band == "MEDIUM":

        factor = float(
            rng.uniform(
                0.86,
                0.98,
            )
        )

    else:

        factor = float(
            rng.uniform(
                0.72,
                0.90,
            )
        )

    approved = int(
        round(
            requested_amount
            * factor
            / 1000.0
        )
        * 1000
    )

    return min(
        requested_amount,
        max(
            approved,
            0,
        ),
    )


# ============================================================
# GENERATOR
# ============================================================


def generate_finance_applications(
    bookings: pd.DataFrame,
    customers: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate exactly one finance application
    for each finance-assisted booking.
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
    # INPUTS
    # ========================================================

    _validate_inputs(
        bookings=bookings,
        customers=customers,
    )

    # ========================================================
    # EXACT CONFIG
    # ========================================================

    finance_config = (
        distributions.get(
            "finance_applications"
        )
    )

    if not isinstance(
        finance_config,
        Mapping,
    ):

        raise KeyError(
            "Missing "
            "distributions.finance_applications "
            "configuration"
        )

    required_keys = {
        "document_completeness",
        "bureau_like_score",
        "approval_tat_hours",
        "status_weights",
    }

    missing = (
        required_keys
        .difference(
            finance_config.keys()
        )
    )

    if missing:

        raise KeyError(
            "distributions.finance_applications "
            "is missing: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    document_spec = (
        finance_config[
            "document_completeness"
        ]
    )

    bureau_spec = (
        finance_config[
            "bureau_like_score"
        ]
    )

    tat_spec = (
        finance_config[
            "approval_tat_hours"
        ]
    )

    status_weights = (
        _normalize_weights(
            finance_config[
                "status_weights"
            ],
            (
                "finance_applications."
                "status_weights"
            ),
        )
    )

    if (
        set(
            status_weights.keys()
        )
        != ALLOWED_STATUSES
    ):

        raise ValueError(
            "status_weights must contain exactly: "
            + ", ".join(
                sorted(
                    ALLOWED_STATUSES
                )
            )
        )

    for (
        name,
        spec,
    ) in (
        (
            "document_completeness",
            document_spec,
        ),
        (
            "bureau_like_score",
            bureau_spec,
        ),
        (
            "approval_tat_hours",
            tat_spec,
        ),
    ):

        if not isinstance(
            spec,
            Mapping,
        ):

            raise TypeError(
                "finance_applications."
                f"{name} must be "
                "a distribution mapping"
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
            "auto.finance_applications",
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
    # CUSTOMER LOOKUP
    # ========================================================

    customer_lookup = {
        row.customer_id:
            row

        for row
        in customers.itertuples(
            index=False
        )
    }

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

    application_counter = 1

    for booking in bookings.itertuples(
        index=False
    ):

        # ----------------------------------------------------
        # Only finance-assisted bookings create applications.
        # ----------------------------------------------------

        if not bool(
            booking.finance_assisted
        ):

            continue

        # ====================================================
        # CUSTOMER
        # ====================================================

        customer = customer_lookup.get(
            booking.customer_id
        )

        if customer is None:

            raise ValueError(
                f"Booking {booking.booking_id} "
                "references unknown customer "
                f"{booking.customer_id}"
            )

        if not bool(
            customer.finance_required
        ):

            raise ValueError(
                f"Booking {booking.booking_id} "
                "is finance-assisted but "
                "customer.finance_required=False"
            )

        # ====================================================
        # DOCUMENT COMPLETENESS
        # ====================================================

        document_completeness = float(
            sample_distribution(
                document_spec,
                rng=rng,
            )
        )

        document_completeness = float(
            np.clip(
                document_completeness,
                0.0,
                1.0,
            )
        )

        # ====================================================
        # BUREAU-LIKE SCORE
        # ====================================================

        bureau_score = float(
            sample_distribution(
                bureau_spec,
                rng=rng,
            )
        )

        bureau_min = float(
            bureau_spec.get(
                "min",
                450,
            )
        )

        bureau_max = float(
            bureau_spec.get(
                "max",
                850,
            )
        )

        bureau_score = int(
            round(
                np.clip(
                    bureau_score,
                    bureau_min,
                    bureau_max,
                )
            )
        )

        # ====================================================
        # APPROVAL TAT
        # ====================================================

        approval_tat_hours = float(
            sample_distribution(
                tat_spec,
                rng=rng,
            )
        )

        tat_min = float(
            tat_spec.get(
                "min",
                1,
            )
        )

        tat_max = float(
            tat_spec.get(
                "max",
                72,
            )
        )

        approval_tat_hours = float(
            np.clip(
                approval_tat_hours,
                tat_min,
                tat_max,
            )
        )

        # ====================================================
        # RISK / INCOME
        # ====================================================

        risk_band = (
            _derive_risk_band(
                bureau_score=
                    bureau_score,

                document_completeness=
                    document_completeness,
            )
        )

        income_band = (
            _derive_income_band(
                customer.budget_band
            )
        )

        # ====================================================
        # REQUESTED AMOUNT
        # ====================================================

        requested_amount = (
            _generate_requested_amount(
                rng=rng,

                vehicle_price=float(
                    booking.
                    vehicle_base_price_inr
                ),

                booking_amount=float(
                    booking.
                    booking_amount_inr
                ),

                risk_band=
                    risk_band,
            )
        )

        # ====================================================
        # SUBMISSION
        # ====================================================

        submitted_at = (
            _generate_submitted_at(
                rng=rng,

                booking_timestamp=
                    pd.Timestamp(
                        booking.
                        booking_timestamp
                    ),

                generation_end=
                    generation_end,
            )
        )

        # ====================================================
        # STATUS
        # ====================================================

        if submitted_at >= generation_end:

            status = "PENDING"

            decision_at = None

        else:

            adjusted_status = (
                _adjust_status_probabilities(
                    base_weights=
                        status_weights,

                    bureau_score=
                        bureau_score,

                    document_completeness=
                        document_completeness,

                    approval_tat_hours=
                        approval_tat_hours,
                )
            )

            status_names = list(
                adjusted_status.keys()
            )

            status_probabilities = (
                np.asarray(
                    list(
                        adjusted_status.values()
                    ),
                    dtype=float,
                )
            )

            status = str(
                rng.choice(
                    status_names,
                    p=
                        status_probabilities,
                )
            )

            candidate_decision_at = (
                submitted_at
                +
                timedelta(
                    hours=
                        approval_tat_hours
                )
            )

            # ------------------------------------------------
            # If decision falls after synthetic cutoff,
            # application remains PENDING.
            # ------------------------------------------------

            if (
                candidate_decision_at
                > generation_end
            ):

                status = "PENDING"

                decision_at = None

            elif status == "PENDING":

                decision_at = None

            else:

                decision_at = (
                    candidate_decision_at
                )

        # ====================================================
        # APPROVED AMOUNT
        # ====================================================

        if status == "APPROVED":

            approved_amount = (
                _generate_approved_amount(
                    rng=rng,

                    requested_amount=
                        requested_amount,

                    risk_band=
                        risk_band,
                )
            )

        else:

            approved_amount = None

        # ====================================================
        # RECORD
        # ====================================================

        rows.append(
            {
                "finance_application_id":
                    make_entity_id(
                        "finance_application",
                        application_counter,
                        width=6,
                    ),

                # --------------------------------------------
                # Journey IDs
                # --------------------------------------------

                "booking_id":
                    booking.booking_id,

                "lead_id":
                    booking.lead_id,

                "customer_id":
                    booking.customer_id,

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
                # Finance lifecycle
                # --------------------------------------------

                "submitted_at":
                    submitted_at,

                "decision_at":
                    decision_at,

                "requested_amount_inr":
                    requested_amount,

                "approved_amount_inr":
                    approved_amount,

                "status":
                    status,

                # --------------------------------------------
                # Evidence
                # --------------------------------------------

                "risk_band":
                    risk_band,

                "income_band":
                    income_band,

                "bureau_like_score_synthetic":
                    bureau_score,

                "document_completeness":
                    round(
                        document_completeness,
                        6,
                    ),

                "approval_tat_hours":
                    round(
                        approval_tat_hours,
                        3,
                    ),

                "preapproval_signal_at_booking":
                    bool(
                        booking.
                        finance_preapproval_signal
                    ),

                # --------------------------------------------
                # Provenance
                # --------------------------------------------

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

        application_counter += 1

    # ========================================================
    # DATAFRAME
    # ========================================================

    finance_applications = pd.DataFrame(
        rows,
        columns=[
            "finance_application_id",

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

            "submitted_at",
            "decision_at",

            "requested_amount_inr",
            "approved_amount_inr",

            "status",

            "risk_band",
            "income_band",

            "bureau_like_score_synthetic",
            "document_completeness",
            "approval_tat_hours",

            "preapproval_signal_at_booking",

            "data_origin",
            "generator_version",
        ],
    )

    validate_finance_applications(
        finance_applications=
            finance_applications,

        bookings=
            bookings,

        customers=
            customers,

        bureau_spec=
            bureau_spec,

        tat_spec=
            tat_spec,

        generation_end=
            generation_end,
    )

    return finance_applications


# ============================================================
# VALIDATION
# ============================================================


def validate_finance_applications(
    finance_applications: pd.DataFrame,
    bookings: pd.DataFrame,
    customers: pd.DataFrame,
    bureau_spec: Mapping[str, Any],
    tat_spec: Mapping[str, Any],
    generation_end: pd.Timestamp,
) -> None:
    """
    Validate finance application data.
    """

    required_columns = {
        "finance_application_id",

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

        "submitted_at",
        "decision_at",

        "requested_amount_inr",
        "approved_amount_inr",

        "status",

        "risk_band",
        "income_band",

        "bureau_like_score_synthetic",
        "document_completeness",
        "approval_tat_hours",

        "preapproval_signal_at_booking",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        .difference(
            finance_applications.columns
        )
    )

    if missing:

        raise ValueError(
            "Finance-applications DataFrame "
            "is missing required columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    # ========================================================
    # EXPECTED FINANCE BOOKINGS
    # ========================================================

    finance_bookings = (
        bookings[
            bookings[
                "finance_assisted"
            ].astype(bool)
        ]
    )

    if finance_bookings.empty:

        if not finance_applications.empty:

            raise ValueError(
                "Finance applications exist "
                "without finance-assisted bookings"
            )

        return

    if finance_applications.empty:

        raise ValueError(
            "Finance-assisted bookings exist "
            "but no finance applications were generated"
        )

    # ========================================================
    # UNIQUE IDS
    # ========================================================

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
            "A booking has more than "
            "one finance application"
        )

    # ========================================================
    # 1:1 COVERAGE
    # ========================================================

    expected_booking_ids = set(
        finance_bookings[
            "booking_id"
        ]
    )

    actual_booking_ids = set(
        finance_applications[
            "booking_id"
        ]
    )

    if (
        actual_booking_ids
        != expected_booking_ids
    ):

        missing_apps = (
            expected_booking_ids
            - actual_booking_ids
        )

        extra_apps = (
            actual_booking_ids
            - expected_booking_ids
        )

        raise ValueError(
            "Finance application coverage mismatch. "
            f"Missing={len(missing_apps)}, "
            f"Extra={len(extra_apps)}"
        )

    # ========================================================
    # CUSTOMER FK
    # ========================================================

    invalid_customers = (
        set(
            finance_applications[
                "customer_id"
            ]
        )
        -
        set(
            customers[
                "customer_id"
            ]
        )
    )

    if invalid_customers:

        raise ValueError(
            "Finance applications reference "
            "invalid customer IDs"
        )

    # ========================================================
    # ENUMS
    # ========================================================

    invalid_statuses = (
        set(
            finance_applications[
                "status"
            ]
        )
        -
        ALLOWED_STATUSES
    )

    if invalid_statuses:

        raise ValueError(
            "Invalid finance application statuses: "
            + ", ".join(
                sorted(
                    invalid_statuses
                )
            )
        )

    invalid_risk = (
        set(
            finance_applications[
                "risk_band"
            ]
        )
        -
        ALLOWED_RISK_BANDS
    )

    if invalid_risk:

        raise ValueError(
            "Invalid finance risk bands found"
        )

    invalid_income = (
        set(
            finance_applications[
                "income_band"
            ]
        )
        -
        ALLOWED_INCOME_BANDS
    )

    if invalid_income:

        raise ValueError(
            "Invalid income bands found"
        )

    # ========================================================
    # DOCUMENT COMPLETENESS
    # ========================================================

    documents = pd.to_numeric(
        finance_applications[
            "document_completeness"
        ],
        errors="raise",
    )

    if (
        (
            documents < 0
        )
        |
        (
            documents > 1
        )
    ).any():

        raise ValueError(
            "document_completeness "
            "must be between 0 and 1"
        )

    # ========================================================
    # BUREAU SCORE
    # ========================================================

    bureau_scores = pd.to_numeric(
        finance_applications[
            "bureau_like_score_synthetic"
        ],
        errors="raise",
    )

    bureau_min = float(
        bureau_spec.get(
            "min",
            450,
        )
    )

    bureau_max = float(
        bureau_spec.get(
            "max",
            850,
        )
    )

    if (
        (
            bureau_scores < bureau_min
        )
        |
        (
            bureau_scores > bureau_max
        )
    ).any():

        raise ValueError(
            "bureau_like_score_synthetic "
            "outside configured range"
        )

    # ========================================================
    # TAT
    # ========================================================

    tat = pd.to_numeric(
        finance_applications[
            "approval_tat_hours"
        ],
        errors="raise",
    )

    tat_min = float(
        tat_spec.get(
            "min",
            1,
        )
    )

    tat_max = float(
        tat_spec.get(
            "max",
            72,
        )
    )

    if (
        (
            tat < tat_min
        )
        |
        (
            tat > tat_max
        )
    ).any():

        raise ValueError(
            "approval_tat_hours outside "
            "configured range"
        )

    # ========================================================
    # REQUESTED AMOUNT
    # ========================================================

    requested = pd.to_numeric(
        finance_applications[
            "requested_amount_inr"
        ],
        errors="raise",
    )

    if (
        requested <= 0
    ).any():

        raise ValueError(
            "requested_amount_inr "
            "must be > 0"
        )

    # ========================================================
    # APPROVED AMOUNT
    # ========================================================

    approved_rows = (
        finance_applications[
            "status"
        ]
        ==
        "APPROVED"
    )

    if (
        finance_applications.loc[
            approved_rows,
            "approved_amount_inr",
        ]
        .isna()
        .any()
    ):

        raise ValueError(
            "Approved applications must "
            "have approved_amount_inr"
        )

    nonapproved_rows = (
        ~approved_rows
    )

    if (
        finance_applications.loc[
            nonapproved_rows,
            "approved_amount_inr",
        ]
        .notna()
        .any()
    ):

        raise ValueError(
            "Non-approved applications cannot "
            "have approved_amount_inr"
        )

    approved_amounts = pd.to_numeric(
        finance_applications.loc[
            approved_rows,
            "approved_amount_inr",
        ],
        errors="raise",
    )

    approved_requested = pd.to_numeric(
        finance_applications.loc[
            approved_rows,
            "requested_amount_inr",
        ],
        errors="raise",
    )

    if (
        approved_amounts <= 0
    ).any():

        raise ValueError(
            "approved_amount_inr must "
            "be > 0"
        )

    if (
        approved_amounts
        > approved_requested
    ).any():

        raise ValueError(
            "approved_amount_inr cannot exceed "
            "requested_amount_inr"
        )

    # ========================================================
    # BOOKING LOOKUP
    # ========================================================

    booking_lookup = {
        row.booking_id:
            row

        for row
        in bookings.itertuples(
            index=False
        )
    }

    # ========================================================
    # ROW BUSINESS RULES
    # ========================================================

    for application in (
        finance_applications.itertuples(
            index=False
        )
    ):

        booking = (
            booking_lookup[
                application.booking_id
            ]
        )

        # ----------------------------------------------------
        # Finance application must belong to finance booking.
        # ----------------------------------------------------

        if not bool(
            booking.finance_assisted
        ):

            raise ValueError(
                f"{application.finance_application_id} "
                "belongs to a non-finance booking"
            )

        # ----------------------------------------------------
        # Journey consistency
        # ----------------------------------------------------

        if (
            application.customer_id
            != booking.customer_id
        ):

            raise ValueError(
                "customer_id mismatch for "
                f"{application.finance_application_id}"
            )

        if (
            application.lead_id
            != booking.lead_id
        ):

            raise ValueError(
                "lead_id mismatch for "
                f"{application.finance_application_id}"
            )

        if (
            application.dealer_id
            != booking.dealer_id
        ):

            raise ValueError(
                "dealer_id mismatch for "
                f"{application.finance_application_id}"
            )

        if (
            application.vehicle_model_id
            != booking.vehicle_model_id
        ):

            raise ValueError(
                "vehicle_model_id mismatch for "
                f"{application.finance_application_id}"
            )

        # ----------------------------------------------------
        # TIME
        # ----------------------------------------------------

        booking_time = pd.Timestamp(
            booking.booking_timestamp
        )

        submitted_at = pd.Timestamp(
            application.submitted_at
        )

        if submitted_at < booking_time:

            raise ValueError(
                f"{application.finance_application_id}: "
                "finance application submitted "
                "before booking"
            )

        if submitted_at > generation_end:

            raise ValueError(
                f"{application.finance_application_id}: "
                "submitted_at exceeds generation end"
            )

        # ----------------------------------------------------
        # PENDING
        # ----------------------------------------------------

        if (
            application.status
            == "PENDING"
        ):

            if (
                application.decision_at
                is not None
                and not pd.isna(
                    application.decision_at
                )
            ):

                raise ValueError(
                    f"{application.finance_application_id}: "
                    "pending application cannot "
                    "have decision_at"
                )

        # ----------------------------------------------------
        # DECIDED
        # ----------------------------------------------------

        else:

            if (
                application.decision_at
                is None
                or pd.isna(
                    application.decision_at
                )
            ):

                raise ValueError(
                    f"{application.finance_application_id}: "
                    "decided application must "
                    "have decision_at"
                )

            decision_at = pd.Timestamp(
                application.decision_at
            )

            if decision_at < submitted_at:

                raise ValueError(
                    f"{application.finance_application_id}: "
                    "decision occurs before submission"
                )

            if decision_at > generation_end:

                raise ValueError(
                    f"{application.finance_application_id}: "
                    "decision exceeds generation end"
                )


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_finance_application_master(
    bookings: pd.DataFrame,
    customers: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Public entry point later used by generate_all.py.
    """

    return generate_finance_applications(
        bookings=bookings,
        customers=customers,
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
    # CUSTOMER JOURNEY
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

    # --------------------------------------------------------
    # FINANCE APPLICATIONS
    # --------------------------------------------------------

    finance_applications_df = (
        generate_finance_application_master(
            bookings=bookings_df,
            customers=customers_df,
        )
    )

    print(
        "\n=== FINANCE APPLICATION SAMPLE ===\n"
    )

    display_columns = [
        "finance_application_id",
        "booking_id",

        "city_name",
        "vehicle_model_name",

        "requested_amount_inr",
        "approved_amount_inr",

        "risk_band",

        "bureau_like_score_synthetic",
        "document_completeness",
        "approval_tat_hours",

        "status",
    ]

    print(
        finance_applications_df[
            display_columns
        ]
        .head(25)
        .to_string(
            index=False
        )
    )

    print(
        "\n=== FINANCE APPLICATION STATUS ===\n"
    )

    print(
        finance_applications_df
        .groupby(
            "status"
        )
        .size()
        .reset_index(
            name="application_count"
        )
        .sort_values(
            "application_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== FINANCE KPI CHECK ===\n"
    )

    finance_booking_count = int(
        bookings_df[
            "finance_assisted"
        ].sum()
    )

    print(
        "Finance-assisted bookings:",
        finance_booking_count,
    )

    print(
        "Finance applications:",
        len(
            finance_applications_df
        ),
    )

    if finance_booking_count:

        print(
            "Application coverage:",
            round(
                len(
                    finance_applications_df
                )
                /
                finance_booking_count,
                4,
            ),
        )

    print(
        "Approval rate:",
        round(
            (
                finance_applications_df[
                    "status"
                ]
                ==
                "APPROVED"
            ).mean(),
            4,
        ),
    )

    print(
        "Manual-review rate:",
        round(
            (
                finance_applications_df[
                    "status"
                ]
                ==
                "MANUAL_REVIEW"
            ).mean(),
            4,
        ),
    )

    print(
        "Rejection rate:",
        round(
            (
                finance_applications_df[
                    "status"
                ]
                ==
                "REJECTED"
            ).mean(),
            4,
        ),
    )

    print(
        "Pending rate:",
        round(
            (
                finance_applications_df[
                    "status"
                ]
                ==
                "PENDING"
            ).mean(),
            4,
        ),
    )

    print(
        "Average approval TAT:",
        round(
            finance_applications_df[
                "approval_tat_hours"
            ].mean(),
            3,
        ),
        "hours",
    )

    print(
        "Average document completeness:",
        round(
            finance_applications_df[
                "document_completeness"
            ].mean(),
            4,
        ),
    )

    print(
        "\nGenerated "
        f"{len(finance_applications_df)} "
        "synthetic finance applications from "
        f"{len(bookings_df)} bookings "
        "successfully."
    )