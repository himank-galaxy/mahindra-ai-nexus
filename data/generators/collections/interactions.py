"""
Synthetic Collections Interaction Generator
for Mahindra AI Nexus.

Generates operational Collections interactions from:

    Collection Cases
          +
    Finance Customers
          +
    Loan Accounts
          +
    Finance Payment History
          ↓
    Collections Interactions


============================================================
METHODOLOGY
============================================================

Collection interactions contain operational evidence such as:

    interaction_id
    case_id
    timestamp
    channel
    contact_success
    promise_to_pay
    promise_date
    offer_type
    customer_response
    field_visit_flag
    payment_after_contact

These records later become learning evidence for the
Collections & Recovery AI layer.


============================================================
IMPORTANT ARCHITECTURAL RULE
============================================================

This generator creates OPERATIONAL interaction evidence.

It DOES NOT generate runtime AI outputs such as:

    roll_forward_risk
    best_channel_score
    recovery_probability
    recommended_action
    recommended_channel
    confidence
    risk_score

Those must later be derived by the application from
Collections history.


============================================================
PAYMENT OUTCOME RULE
============================================================

payment_after_contact is NOT randomly generated.

Instead:

    Collection interaction
             ↓
    look forward in ACTUAL Finance payment history
             ↓
    find first payment after contact
             ↓
    payment_after_contact = True/False

This preserves the relationship between Collections actions
and observed repayment behaviour.


============================================================
PROMISE TO PAY
============================================================

Configured synthetic assumptions:

    promise_to_pay_probability
    payment_after_promise_probability

are used only internally to create realistic correlation
between promises and future observed payment behaviour.

The probabilities themselves NEVER appear in output.


============================================================
TIMEZONE RULE
============================================================

All business timestamps remain timezone-aware.

Empty datetime placeholders use None/object dtype instead of
plain pd.NaT datetime64 columns.

This prevents Pandas from creating timezone-naive datetime
columns and later rejecting Asia/Kolkata timestamps.


============================================================
INTERACTION COUNTS
============================================================

generation.yaml configures 1-8 interactions per case.

The generator respects that range while also respecting:

    case creation time
    case resolution time
    global generation cutoff

Short-lived cases may naturally receive fewer touchpoints.


============================================================
OUTPUT
============================================================

This module DOES NOT write CSV files.

Later:

    data/scripts/generate_all.py

will write:

    data/synthetic/collections/
        collections_interactions.csv
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
    generate_id,
)

from data.generators.common.seed import (
    derive_seed,
    make_rng,
)


# ============================================================
# CONTACT CHANNELS
# ============================================================


CHANNEL_CALL = "CALL"
CHANNEL_WHATSAPP = "WHATSAPP"
CHANNEL_SMS = "SMS"
CHANNEL_EMAIL = "EMAIL"
CHANNEL_FIELD_VISIT = "FIELD_VISIT"


# ============================================================
# CUSTOMER RESPONSES
# ============================================================


RESPONSE_NO_CONTACT = "NO_CONTACT"
RESPONSE_ACKNOWLEDGED = "ACKNOWLEDGED"
RESPONSE_PROMISE_TO_PAY = "PROMISE_TO_PAY"
RESPONSE_REQUEST_CALLBACK = "REQUEST_CALLBACK"
RESPONSE_DISPUTED = "DISPUTED"
RESPONSE_REFUSED = "REFUSED"


VALID_CUSTOMER_RESPONSES = {
    RESPONSE_NO_CONTACT,
    RESPONSE_ACKNOWLEDGED,
    RESPONSE_PROMISE_TO_PAY,
    RESPONSE_REQUEST_CALLBACK,
    RESPONSE_DISPUTED,
    RESPONSE_REFUSED,
}


# ============================================================
# OFFER TYPES
#
# Synthetic operational categories only.
#
# These are NOT real Mahindra Finance collection policies.
# ============================================================


OFFER_NONE = "NONE"
OFFER_PAYMENT_REMINDER = "PAYMENT_REMINDER"
OFFER_PARTIAL_PAYMENT_PLAN = "PARTIAL_PAYMENT_PLAN"
OFFER_REPAYMENT_PLAN_DISCUSSION = "REPAYMENT_PLAN_DISCUSSION"


VALID_OFFER_TYPES = {
    OFFER_NONE,
    OFFER_PAYMENT_REMINDER,
    OFFER_PARTIAL_PAYMENT_PLAN,
    OFFER_REPAYMENT_PLAN_DISCUSSION,
}


# ============================================================
# SYNTHETIC ENGINEERING ASSUMPTIONS
#
# NOT Mahindra Finance production statistics.
# ============================================================


PAYMENT_AFTER_CONTACT_WINDOW_DAYS = 14

MIN_INTERACTION_GAP_HOURS = 8


# ------------------------------------------------------------
# Digital-first channel mix for early Collections touch.
# ------------------------------------------------------------


EARLY_CHANNEL_WEIGHTS = {
    CHANNEL_CALL: 0.30,
    CHANNEL_WHATSAPP: 0.32,
    CHANNEL_SMS: 0.20,
    CHANNEL_EMAIL: 0.13,
    CHANNEL_FIELD_VISIT: 0.05,
}


# ------------------------------------------------------------
# Mid-stage interaction mix.
# ------------------------------------------------------------


MID_CHANNEL_WEIGHTS = {
    CHANNEL_CALL: 0.34,
    CHANNEL_WHATSAPP: 0.27,
    CHANNEL_SMS: 0.14,
    CHANNEL_EMAIL: 0.10,
    CHANNEL_FIELD_VISIT: 0.15,
}


# ------------------------------------------------------------
# Escalated interaction mix.
# ------------------------------------------------------------


ESCALATED_CHANNEL_WEIGHTS = {
    CHANNEL_CALL: 0.28,
    CHANNEL_WHATSAPP: 0.18,
    CHANNEL_SMS: 0.08,
    CHANNEL_EMAIL: 0.06,
    CHANNEL_FIELD_VISIT: 0.40,
}


# ============================================================
# REQUIRED CASE SCHEMA
# ============================================================


CASE_REQUIRED_COLUMNS: set[str] = {
    "collection_case_id",

    "loan_account_id",
    "finance_customer_id",

    "loan_case_sequence",

    "region_id",
    "region_name",

    "city_id",
    "city_name",

    "finance_product_id",
    "product_code",
    "product_name",
    "product_category",

    "case_created_at",

    "case_trigger_source",

    "case_trigger_dpd",
    "dpd_at_case_creation",

    "arrears_at_trigger_event_inr",

    "priority_at_creation",

    "peak_observed_dpd",

    "case_status",

    "current_dpd",
    "current_arrears_inr",

    "resolved_at",

    "data_origin",
    "generator_version",
}


# ============================================================
# FINANCE CUSTOMER REQUIRED SCHEMA
# ============================================================


FINANCE_CUSTOMER_REQUIRED_COLUMNS: set[str] = {
    "finance_customer_id",

    "region_id",
    "region_name",

    "city_id",
    "city_name",

    "employment_type",
    "rural_urban_segment",
    "finance_customer_segment",

    "income_stability",

    "monthly_income_inr",
    "monthly_obligations_inr",

    "active",

    "data_origin",
    "generator_version",
}


# ============================================================
# LOAN REQUIRED SCHEMA
# ============================================================


LOAN_REQUIRED_COLUMNS: set[str] = {
    "loan_account_id",

    "finance_customer_id",

    "finance_product_id",
    "product_code",
    "product_name",
    "product_category",

    "principal_inr",
    "emi_amount_inr",

    "disbursed_at",
    "scheduled_maturity_at",

    "data_origin",
    "generator_version",
}


# ============================================================
# PAYMENT REQUIRED SCHEMA
# ============================================================


PAYMENT_REQUIRED_COLUMNS: set[str] = {
    "payment_event_id",

    "loan_account_id",
    "finance_customer_id",

    "installment_number",

    "payment_due_at",

    "payment_status",

    "actual_payment_at",
    "actual_payment_amount_inr",

    "days_past_due_after_event",
    "arrears_amount_inr",

    "outstanding_principal_inr",

    "data_origin",
    "generator_version",
}


# ============================================================
# BASIC HELPERS
# ============================================================


def _as_probability(
    value: Any,
    name: str,
) -> float:
    """
    Parse probability configuration.
    """

    if isinstance(
        value,
        bool,
    ):
        raise TypeError(
            f"{name} must be numeric"
        )

    try:
        result = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise TypeError(
            f"{name} must be numeric"
        ) from exc

    if not (
        0.0
        <=
        result
        <=
        1.0
    ):
        raise ValueError(
            f"{name} must be between 0 and 1"
        )

    return result


def _as_positive_int(
    value: Any,
    name: str,
) -> int:
    """
    Parse positive integer configuration.
    """

    if isinstance(
        value,
        bool,
    ):
        raise TypeError(
            f"{name} must be integer"
        )

    try:
        result = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise TypeError(
            f"{name} must be integer"
        ) from exc

    if result <= 0:
        raise ValueError(
            f"{name} must be > 0"
        )

    return result


def _normalise_weights(
    weights: Mapping[
        str,
        float,
    ],
) -> tuple[
    list[str],
    np.ndarray,
]:
    """
    Normalize weighted categorical probabilities.
    """

    labels = list(
        weights.keys()
    )

    values = np.asarray(
        [
            float(
                weights[label]
            )
            for label
            in labels
        ],
        dtype=float,
    )

    values = np.clip(
        values,
        0.0,
        None,
    )

    if values.sum() <= 0:
        raise ValueError(
            "Channel weights must sum to > 0"
        )

    return (
        labels,
        values
        /
        values.sum(),
    )


# ============================================================
# GENERATION WINDOW
# ============================================================


def _get_generation_window(
    generation: Mapping[
        str,
        Any,
    ],
) -> tuple[
    pd.Timestamp,
    pd.Timestamp,
]:
    """
    Return timezone-aware generation start/end.
    """

    try:
        start_value = generation[
            "time"
        ][
            "start_date"
        ]

        end_value = generation[
            "time"
        ][
            "end_date"
        ]

        timezone = str(
            generation[
                "time"
            ].get(
                "timezone",
                "Asia/Kolkata",
            )
        )

    except KeyError as exc:
        raise KeyError(
            "Missing generation.time configuration"
        ) from exc

    start = pd.Timestamp(
        start_value
    )

    end = pd.Timestamp(
        end_value
    )

    if start.tzinfo is None:
        start = start.tz_localize(
            timezone
        )

    else:
        start = start.tz_convert(
            timezone
        )

    if end.tzinfo is None:
        end = end.tz_localize(
            timezone
        )

    else:
        end = end.tz_convert(
            timezone
        )

    if end <= start:
        raise ValueError(
            "Generation end must be after start"
        )

    return (
        start,
        end,
    )


# ============================================================
# INTERACTION COUNT CONFIG
# ============================================================


def _get_interaction_count_range(
    generation: Mapping[
        str,
        Any,
    ],
) -> tuple[
    int,
    int,
]:
    """
    Read configured Collections interaction range.

    Supports equivalent existing config layouts without
    inventing configuration values.
    """

    try:
        collections = generation[
            "collections"
        ]

    except KeyError as exc:
        raise KeyError(
            "Missing generation.collections"
        ) from exc

    candidate_configs = [
        collections.get(
            "interactions_per_case"
        ),
        collections.get(
            "interactions"
        ),
    ]

    for candidate in candidate_configs:

        if isinstance(
            candidate,
            Mapping,
        ):

            if (
                "min"
                in
                candidate
                and
                "max"
                in
                candidate
            ):
                minimum = (
                    _as_positive_int(
                        candidate[
                            "min"
                        ],
                        "collections interactions minimum",
                    )
                )

                maximum = (
                    _as_positive_int(
                        candidate[
                            "max"
                        ],
                        "collections interactions maximum",
                    )
                )

                if maximum < minimum:
                    raise ValueError(
                        "Collections maximum interactions "
                        "must be >= minimum"
                    )

                return (
                    minimum,
                    maximum,
                )

    if (
        "min_interactions_per_case"
        in
        collections
        and
        "max_interactions_per_case"
        in
        collections
    ):
        minimum = (
            _as_positive_int(
                collections[
                    "min_interactions_per_case"
                ],
                "min_interactions_per_case",
            )
        )

        maximum = (
            _as_positive_int(
                collections[
                    "max_interactions_per_case"
                ],
                "max_interactions_per_case",
            )
        )

        if maximum < minimum:
            raise ValueError(
                "Collections maximum interactions "
                "must be >= minimum"
            )

        return (
            minimum,
            maximum,
        )

    raise KeyError(
        "Unable to locate configured Collections "
        "interaction min/max values"
    )


# ============================================================
# ALLOWED CHANNELS
# ============================================================


def _get_allowed_channels(
    generation: Mapping[
        str,
        Any,
    ],
    channel_response_probability: Mapping[
        str,
        float,
    ],
) -> list[str]:
    """
    Use configured Collections channels when available.

    Otherwise distribution config provides the canonical list.
    """

    collections = generation.get(
        "collections",
        {},
    )

    configured_channels = (
        collections.get(
            "channels"
        )
    )

    if configured_channels is None:
        channels = list(
            channel_response_probability.keys()
        )

    else:
        if not isinstance(
            configured_channels,
            (
                list,
                tuple,
            ),
        ):
            raise TypeError(
                "generation.collections.channels "
                "must be a list"
            )

        channels = [
            str(
                channel
            )
            for channel
            in configured_channels
        ]

    if not channels:
        raise ValueError(
            "No Collections interaction channels configured"
        )

    unsupported = (
        set(
            channels
        )
        -
        set(
            channel_response_probability.keys()
        )
    )

    if unsupported:
        raise ValueError(
            "Collections channels missing response "
            "probabilities: "
            +
            ", ".join(
                sorted(
                    unsupported
                )
            )
        )

    return channels


# ============================================================
# COLLECTION DISTRIBUTIONS
# ============================================================


def _get_collection_distributions(
    distributions: Mapping[
        str,
        Any,
    ],
) -> tuple[
    dict[str, float],
    float,
    float,
]:
    """
    Read configured Collections behavioural assumptions.
    """

    try:
        collection_config = (
            distributions[
                "collections"
            ]
        )

        raw_channel_probabilities = (
            collection_config[
                "channel_response_probability"
            ]
        )

        promise_probability = (
            _as_probability(
                collection_config[
                    "promise_to_pay_probability"
                ],
                (
                    "collections."
                    "promise_to_pay_probability"
                ),
            )
        )

        payment_after_promise_probability = (
            _as_probability(
                collection_config[
                    "payment_after_promise_probability"
                ],
                (
                    "collections."
                    "payment_after_promise_probability"
                ),
            )
        )

    except KeyError as exc:
        raise KeyError(
            "Missing Collections distributions"
        ) from exc

    channel_probabilities: dict[
        str,
        float,
    ] = {}

    for (
        channel,
        probability,
    ) in raw_channel_probabilities.items():

        channel_probabilities[
            str(
                channel
            )
        ] = (
            _as_probability(
                probability,
                (
                    "collections."
                    "channel_response_probability."
                    f"{channel}"
                ),
            )
        )

    return (
        channel_probabilities,
        promise_probability,
        payment_after_promise_probability,
    )


# ============================================================
# INPUT VALIDATION
# ============================================================


def _validate_inputs(
    collection_cases: pd.DataFrame,
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
    payment_history: pd.DataFrame,
) -> None:
    """
    Validate all upstream datasets.
    """

    datasets = {
        "collection_cases":
            (
                collection_cases,
                CASE_REQUIRED_COLUMNS,
            ),

        "finance_customers":
            (
                finance_customers,
                FINANCE_CUSTOMER_REQUIRED_COLUMNS,
            ),

        "loan_accounts":
            (
                loan_accounts,
                LOAN_REQUIRED_COLUMNS,
            ),

        "payment_history":
            (
                payment_history,
                PAYMENT_REQUIRED_COLUMNS,
            ),
    }

    for (
        name,
        (
            dataframe,
            required,
        ),
    ) in datasets.items():

        if dataframe.empty:
            raise ValueError(
                f"{name} cannot be empty"
            )

        missing = (
            required
            -
            set(
                dataframe.columns
            )
        )

        if missing:
            raise ValueError(
                f"{name} missing columns: "
                +
                ", ".join(
                    sorted(
                        missing
                    )
                )
            )

    if (
        collection_cases[
            "collection_case_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate collection_case_id found"
        )

    if (
        finance_customers[
            "finance_customer_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate finance_customer_id found"
        )

    if (
        loan_accounts[
            "loan_account_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate loan_account_id found"
        )

    if (
        payment_history[
            "payment_event_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate payment_event_id found"
        )

    # --------------------------------------------------------
    # Case -> Loan
    # --------------------------------------------------------

    valid_loans = set(
        loan_accounts[
            "loan_account_id"
        ]
        .astype(str)
    )

    invalid_case_loans = (
        set(
            collection_cases[
                "loan_account_id"
            ]
            .astype(str)
        )
        -
        valid_loans
    )

    if invalid_case_loans:
        raise ValueError(
            "Collection cases reference invalid loans"
        )

    # --------------------------------------------------------
    # Case -> Customer
    # --------------------------------------------------------

    valid_customers = set(
        finance_customers[
            "finance_customer_id"
        ]
        .astype(str)
    )

    invalid_case_customers = (
        set(
            collection_cases[
                "finance_customer_id"
            ]
            .astype(str)
        )
        -
        valid_customers
    )

    if invalid_case_customers:
        raise ValueError(
            "Collection cases reference invalid customers"
        )


# ============================================================
# PREPARE PAYMENT HISTORY
# ============================================================


def _prepare_payment_history(
    payment_history: pd.DataFrame,
) -> pd.DataFrame:
    """
    Create timestamps representing when payment states became
    operationally known.

    This allows interactions to use only information available
    by the interaction timestamp.
    """

    payments = (
        payment_history
        .copy(
            deep=True
        )
    )

    payments[
        "payment_due_at"
    ] = pd.to_datetime(
        payments[
            "payment_due_at"
        ],
        utc=True,
    )

    payments[
        "actual_payment_at"
    ] = pd.to_datetime(
        payments[
            "actual_payment_at"
        ],
        utc=True,
    )

    payments[
        "days_past_due_after_event"
    ] = pd.to_numeric(
        payments[
            "days_past_due_after_event"
        ],
        errors="raise",
    ).astype(int)

    payments[
        "arrears_amount_inr"
    ] = pd.to_numeric(
        payments[
            "arrears_amount_inr"
        ],
        errors="raise",
    )

    payments[
        "outstanding_principal_inr"
    ] = pd.to_numeric(
        payments[
            "outstanding_principal_inr"
        ],
        errors="raise",
    )

    # ========================================================
    # STATE-KNOWN TIME
    # ========================================================

    payments[
        "_state_known_at"
    ] = (
        payments[
            "actual_payment_at"
        ]
        .copy()
    )

    missed = (
        payments[
            "payment_status"
        ]
        .astype(str)
        ==
        "MISSED"
    )

    payments.loc[
        missed,
        "_state_known_at",
    ] = (
        payments.loc[
            missed,
            "payment_due_at",
        ]
        +
        timedelta(
            days=1
        )
    )

    if (
        payments[
            "_state_known_at"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Unable to determine payment state-known time"
        )

    # ========================================================
    # DPD REFERENCE TIME
    # ========================================================

    payments[
        "_dpd_reference_at"
    ] = (
        payments[
            "payment_due_at"
        ]
        .copy()
    )

    paid = ~missed

    if paid.any():

        paid_reference = pd.concat(
            [
                payments.loc[
                    paid,
                    "payment_due_at",
                ],

                payments.loc[
                    paid,
                    "actual_payment_at",
                ],
            ],
            axis=1,
        ).max(
            axis=1
        )

        payments.loc[
            paid,
            "_dpd_reference_at",
        ] = paid_reference

    payments.loc[
        missed,
        "_dpd_reference_at",
    ] = (
        payments.loc[
            missed,
            "payment_due_at",
        ]
        +
        timedelta(
            days=1
        )
    )

    return (
        payments
        .sort_values(
            [
                "loan_account_id",
                "_state_known_at",
                "installment_number",
            ]
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# CASE INTERACTION WINDOW
# ============================================================


def _case_interaction_window(
    case: Mapping[
        str,
        Any,
    ],
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
) -> tuple[
    pd.Timestamp,
    pd.Timestamp,
]:
    """
    Determine valid interaction interval.
    """

    case_created = pd.Timestamp(
        case[
            "case_created_at"
        ]
    )

    start = max(
        case_created,
        generation_start,
    )

    resolved_at = case.get(
        "resolved_at"
    )

    if (
        resolved_at is not None
        and
        pd.notna(
            resolved_at
        )
    ):
        end = min(
            pd.Timestamp(
                resolved_at
            ),
            generation_end,
        )

    else:
        end = generation_end

    return (
        start,
        end,
    )


# ============================================================
# SAMPLE INTERACTION TIMESTAMPS
# ============================================================


def _sample_interaction_timestamps(
    rng: np.random.Generator,
    start: pd.Timestamp,
    end: pd.Timestamp,
    minimum_count: int,
    maximum_count: int,
) -> list[
    pd.Timestamp
]:
    """
    Generate ordered Collections touchpoints.

    Very short cases naturally receive fewer interactions.
    """

    if end <= start:
        return []

    duration = (
        end
        -
        start
    )

    duration_hours = (
        duration.total_seconds()
        /
        3600.0
    )

    # --------------------------------------------------------
    # Very short case:
    #
    # Use the midpoint rather than blindly adding 30 minutes.
    # This guarantees interaction_at remains inside the case.
    # --------------------------------------------------------

    if duration_hours <= 1.0:

        midpoint = (
            start
            +
            duration
            *
            0.5
        )

        return [
            midpoint
        ]

    desired_count = int(
        rng.integers(
            minimum_count,
            maximum_count
            +
            1,
        )
    )

    maximum_by_time = max(
        1,
        int(
            duration_hours
            //
            MIN_INTERACTION_GAP_HOURS
        )
        +
        1,
    )

    actual_count = min(
        desired_count,
        maximum_count,
        maximum_by_time,
    )

    actual_count = max(
        1,
        actual_count,
    )

    if actual_count == 1:

        fraction = float(
            rng.uniform(
                0.05,
                0.40,
            )
        )

        timestamp = (
            start
            +
            duration
            *
            fraction
        )

        return [
            timestamp
        ]

    fractions = np.sort(
        rng.uniform(
            0.03,
            0.97,
            size=
                actual_count,
        )
    )

    timestamps = [
        start
        +
        duration
        *
        float(
            fraction
        )

        for fraction
        in fractions
    ]

    return timestamps


# ============================================================
# DPD / ARREARS SNAPSHOT AT INTERACTION
# ============================================================


def _payment_state_at_interaction(
    loan_payments: pd.DataFrame,
    interaction_at: pd.Timestamp,
    case: Mapping[
        str,
        Any,
    ],
) -> tuple[
    int,
    float,
    float,
]:
    """
    Derive operational loan state known at interaction time.

    Returns:

        DPD
        arrears
        outstanding principal

    Important:
    if no retained payment row exists before interaction,
    use case-creation evidence instead of CURRENT case values.

    This avoids leaking future cutoff state into an earlier
    interaction.
    """

    known = (
        loan_payments[
            loan_payments[
                "_state_known_at"
            ]
            <=
            interaction_at
        ]
    )

    if known.empty:

        return (
            int(
                case[
                    "dpd_at_case_creation"
                ]
            ),

            float(
                case[
                    "arrears_at_trigger_event_inr"
                ]
            ),

            0.0,
        )

    latest = (
        known
        .sort_values(
            [
                "_state_known_at",
                "installment_number",
            ]
        )
        .iloc[
            -1
        ]
    )

    arrears = float(
        latest[
            "arrears_amount_inr"
        ]
    )

    recorded_dpd = int(
        latest[
            "days_past_due_after_event"
        ]
    )

    outstanding = float(
        latest[
            "outstanding_principal_inr"
        ]
    )

    if (
        arrears
        <=
        0.01
        or
        recorded_dpd
        <=
        0
    ):
        return (
            0,
            max(
                arrears,
                0.0,
            ),
            max(
                outstanding,
                0.0,
            ),
        )

    reference_at = pd.Timestamp(
        latest[
            "_dpd_reference_at"
        ]
    )

    if interaction_at <= reference_at:

        dpd = recorded_dpd

    else:

        additional_days = int(
            np.ceil(
                (
                    interaction_at
                    -
                    reference_at
                ).total_seconds()
                /
                86400.0
            )
        )

        dpd = (
            recorded_dpd
            +
            max(
                additional_days,
                0,
            )
        )

    return (
        int(
            dpd
        ),
        max(
            arrears,
            0.0,
        ),
        max(
            outstanding,
            0.0,
        ),
    )


# ============================================================
# CHANNEL SELECTION
# ============================================================


def _select_channel(
    rng: np.random.Generator,
    allowed_channels: list[str],
    interaction_sequence: int,
    total_interactions: int,
    dpd_at_interaction: int,
) -> str:
    """
    Generate operational Collections channel.

    Earlier touches are more digital-first.

    Repeated or severe delinquency increases FIELD_VISIT use.
    """

    progress = (
        interaction_sequence
        /
        max(
            total_interactions,
            1,
        )
    )

    if (
        dpd_at_interaction
        >=
        90
        or
        progress
        >=
        0.75
    ):
        base = (
            ESCALATED_CHANNEL_WEIGHTS
        )

    elif (
        dpd_at_interaction
        >=
        30
        or
        progress
        >=
        0.40
    ):
        base = (
            MID_CHANNEL_WEIGHTS
        )

    else:
        base = (
            EARLY_CHANNEL_WEIGHTS
        )

    available_weights = {
        channel:
            float(
                base.get(
                    channel,
                    0.0,
                )
            )

        for channel
        in allowed_channels
    }

    if (
        sum(
            available_weights.values()
        )
        <=
        0
    ):
        available_weights = {
            channel:
                1.0

            for channel
            in allowed_channels
        }

    (
        channels,
        probabilities,
    ) = (
        _normalise_weights(
            available_weights
        )
    )

    return str(
        rng.choice(
            channels,
            p=
                probabilities,
        )
    )


# ============================================================
# OFFER TYPE
# ============================================================


def _derive_offer_type(
    contact_success: bool,
    dpd_at_interaction: int,
) -> str:
    """
    Derive interaction type from observable Collections state.
    """

    if not contact_success:
        return OFFER_NONE

    if dpd_at_interaction >= 60:
        return (
            OFFER_REPAYMENT_PLAN_DISCUSSION
        )

    if dpd_at_interaction >= 30:
        return (
            OFFER_PARTIAL_PAYMENT_PLAN
        )

    return (
        OFFER_PAYMENT_REMINDER
    )


# ============================================================
# CUSTOMER RESPONSE WITHOUT PTP
# ============================================================


def _generate_non_ptp_response(
    rng: np.random.Generator,
    contact_success: bool,
    dpd_at_interaction: int,
) -> str:
    """
    Generate contacted-customer response before PTP assignment.
    """

    if not contact_success:
        return RESPONSE_NO_CONTACT

    if dpd_at_interaction >= 90:

        responses = [
            RESPONSE_ACKNOWLEDGED,
            RESPONSE_REQUEST_CALLBACK,
            RESPONSE_DISPUTED,
            RESPONSE_REFUSED,
        ]

        weights = [
            0.34,
            0.22,
            0.18,
            0.26,
        ]

    elif dpd_at_interaction >= 30:

        responses = [
            RESPONSE_ACKNOWLEDGED,
            RESPONSE_REQUEST_CALLBACK,
            RESPONSE_DISPUTED,
            RESPONSE_REFUSED,
        ]

        weights = [
            0.44,
            0.25,
            0.14,
            0.17,
        ]

    else:

        responses = [
            RESPONSE_ACKNOWLEDGED,
            RESPONSE_REQUEST_CALLBACK,
            RESPONSE_DISPUTED,
            RESPONSE_REFUSED,
        ]

        weights = [
            0.55,
            0.27,
            0.08,
            0.10,
        ]

    return str(
        rng.choice(
            responses,
            p=
                np.asarray(
                    weights,
                    dtype=float,
                ),
        )
    )


# ============================================================
# FIND ACTUAL PAYMENT AFTER CONTACT
# ============================================================


def _find_payment_after_contact(
    loan_payments: pd.DataFrame,
    interaction_at: pd.Timestamp,
    observation_end: pd.Timestamp,
) -> dict[
    str,
    Any,
] | None:
    """
    Find first ACTUAL Finance payment after Collection contact.
    """

    if observation_end <= interaction_at:
        return None

    actual_amount = pd.to_numeric(
        loan_payments[
            "actual_payment_amount_inr"
        ],
        errors="coerce",
    )

    eligible = (
        loan_payments[
            (
                loan_payments[
                    "actual_payment_at"
                ]
                .notna()
            )
            &
            (
                loan_payments[
                    "actual_payment_at"
                ]
                >
                interaction_at
            )
            &
            (
                loan_payments[
                    "actual_payment_at"
                ]
                <=
                observation_end
            )
            &
            (
                actual_amount
                >
                0
            )
        ]
        .sort_values(
            "actual_payment_at"
        )
    )

    if eligible.empty:
        return None

    return (
        eligible
        .iloc[
            0
        ]
        .to_dict()
    )


# ============================================================
# ASSIGN PROMISE TO PAY
# ============================================================


def _assign_promises_to_pay(
    interactions: pd.DataFrame,
    rng: np.random.Generator,
    base_ptp_probability: float,
    target_payment_after_promise_probability: float,
) -> pd.DataFrame:
    """
    Assign PTP only to successful contacts.

    Promise occurrence is correlated with actual subsequent
    payment evidence, while remaining probabilistic.

    Internal probabilities are not exported.
    """

    result = (
        interactions
        .copy(
            deep=True
        )
    )

    result[
        "promise_to_pay"
    ] = False

    # Keep object dtype because timestamps are timezone-aware.
    result[
        "promise_date"
    ] = (
        result[
            "promise_date"
        ]
        .astype(
            "object"
        )
    )

    result[
        "payment_after_promise"
    ] = pd.NA

    contacted_mask = (
        result[
            "contact_success"
        ]
        .astype(bool)
    )

    contacted = (
        result.loc[
            contacted_mask
        ]
    )

    if contacted.empty:
        return result

    actual_recovery = (
        contacted[
            "payment_after_contact"
        ]
        .astype(bool)
    )

    recovery_rate = float(
        actual_recovery.mean()
    )

    # ========================================================
    # CALIBRATE PTP CORRELATION
    # ========================================================

    if (
        0.001
        <
        recovery_rate
        <
        0.999
    ):
        p_if_payment = (
            target_payment_after_promise_probability
            *
            base_ptp_probability
            /
            recovery_rate
        )

        p_if_no_payment = (
            base_ptp_probability
            *
            (
                1.0
                -
                target_payment_after_promise_probability
            )
            /
            (
                1.0
                -
                recovery_rate
            )
        )

        p_if_payment = float(
            np.clip(
                p_if_payment,
                0.05,
                0.95,
            )
        )

        p_if_no_payment = float(
            np.clip(
                p_if_no_payment,
                0.05,
                0.95,
            )
        )

    else:

        p_if_payment = (
            base_ptp_probability
        )

        p_if_no_payment = (
            base_ptp_probability
        )

    for index in contacted.index:

        payment_after_contact = bool(
            result.at[
                index,
                "payment_after_contact"
            ]
        )

        ptp_probability = (
            p_if_payment
            if payment_after_contact
            else p_if_no_payment
        )

        promise = (
            float(
                rng.random()
            )
            <
            ptp_probability
        )

        if not promise:
            continue

        result.at[
            index,
            "promise_to_pay"
        ] = True

        result.at[
            index,
            "customer_response"
        ] = (
            RESPONSE_PROMISE_TO_PAY
        )

        interaction_at = pd.Timestamp(
            result.at[
                index,
                "interaction_at"
            ]
        )

        promise_days = int(
            rng.integers(
                1,
                8,
            )
        )

        promise_date = (
            interaction_at
            +
            timedelta(
                days=
                    promise_days
            )
        )

        result.at[
            index,
            "promise_date"
        ] = promise_date

        result.at[
            index,
            "payment_after_promise"
        ] = bool(
            payment_after_contact
        )

    return result


# ============================================================
# GENERATE INTERACTIONS
# ============================================================


def generate_collection_interactions(
    collection_cases: pd.DataFrame,
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
    payment_history: pd.DataFrame,
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
    distributions: Mapping[
        str,
        Any,
    ]
    | None = None,
) -> pd.DataFrame:
    """
    Generate Collections interaction history.
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
        collection_cases=
            collection_cases,

        finance_customers=
            finance_customers,

        loan_accounts=
            loan_accounts,

        payment_history=
            payment_history,
    )

    # ========================================================
    # CONFIG
    # ========================================================

    (
        minimum_interactions,
        maximum_interactions,
    ) = (
        _get_interaction_count_range(
            generation
        )
    )

    (
        channel_response_probability,
        promise_to_pay_probability,
        payment_after_promise_probability,
    ) = (
        _get_collection_distributions(
            distributions
        )
    )

    allowed_channels = (
        _get_allowed_channels(
            generation=
                generation,

            channel_response_probability=
                channel_response_probability,
        )
    )

    (
        generation_start,
        generation_end,
    ) = (
        _get_generation_window(
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
            "collections.interactions",
        )
    )

    # ========================================================
    # PREPARE PAYMENT HISTORY
    # ========================================================

    payments = (
        _prepare_payment_history(
            payment_history
        )
    )

    payments_by_loan = {
        str(
            loan_id
        ):
            group.copy()

        for (
            loan_id,
            group,
        )
        in payments.groupby(
            "loan_account_id",
            sort=False,
        )
    }

    # ========================================================
    # CUSTOMER / LOAN LOOKUPS
    # ========================================================

    customer_lookup = {
        str(
            row.finance_customer_id
        ):
            row._asdict()

        for row
        in finance_customers.itertuples(
            index=False
        )
    }

    loan_lookup = {
        str(
            row.loan_account_id
        ):
            row._asdict()

        for row
        in loan_accounts.itertuples(
            index=False
        )
    }

    # ========================================================
    # CREATE INTERACTION SKELETONS
    # ========================================================

    rows: list[
        dict[str, Any]
    ] = []

    ordered_cases = (
        collection_cases
        .sort_values(
            [
                "case_created_at",
                "collection_case_id",
            ]
        )
    )

    for case in ordered_cases.to_dict(
        orient="records"
    ):

        case_id = str(
            case[
                "collection_case_id"
            ]
        )

        loan_id = str(
            case[
                "loan_account_id"
            ]
        )

        customer_id = str(
            case[
                "finance_customer_id"
            ]
        )

        loan = (
            loan_lookup[
                loan_id
            ]
        )

        customer = (
            customer_lookup[
                customer_id
            ]
        )

        # Referenced intentionally to ensure customer exists.
        _ = customer

        loan_payments = (
            payments_by_loan.get(
                loan_id
            )
        )

        if loan_payments is None:
            raise ValueError(
                "Collection case has no Finance payment "
                f"history: {case_id}"
            )

        (
            interaction_start,
            interaction_end,
        ) = (
            _case_interaction_window(
                case=
                    case,

                generation_start=
                    generation_start,

                generation_end=
                    generation_end,
            )
        )

        timestamps = (
            _sample_interaction_timestamps(
                rng=
                    rng,

                start=
                    interaction_start,

                end=
                    interaction_end,

                minimum_count=
                    minimum_interactions,

                maximum_count=
                    maximum_interactions,
            )
        )

        if not timestamps:
            raise ValueError(
                "Unable to place a Collection interaction "
                f"inside case window: {case_id}"
            )

        total_interactions = len(
            timestamps
        )

        # ====================================================
        # BUILD EACH TOUCHPOINT
        # ====================================================

        for (
            position,
            interaction_at,
        ) in enumerate(
            timestamps,
            start=1,
        ):

            (
                dpd_at_interaction,
                arrears_at_interaction,
                outstanding_at_interaction,
            ) = (
                _payment_state_at_interaction(
                    loan_payments=
                        loan_payments,

                    interaction_at=
                        interaction_at,

                    case=
                        case,
                )
            )

            channel = (
                _select_channel(
                    rng=
                        rng,

                    allowed_channels=
                        allowed_channels,

                    interaction_sequence=
                        position,

                    total_interactions=
                        total_interactions,

                    dpd_at_interaction=
                        dpd_at_interaction,
                )
            )

            channel_success_probability = (
                float(
                    channel_response_probability[
                        channel
                    ]
                )
            )

            contact_success = bool(
                float(
                    rng.random()
                )
                <
                channel_success_probability
            )

            offer_type = (
                _derive_offer_type(
                    contact_success=
                        contact_success,

                    dpd_at_interaction=
                        dpd_at_interaction,
                )
            )

            customer_response = (
                _generate_non_ptp_response(
                    rng=
                        rng,

                    contact_success=
                        contact_success,

                    dpd_at_interaction=
                        dpd_at_interaction,
                )
            )

            rows.append(
                {
                    "collection_interaction_id":
                        None,

                    "collection_case_id":
                        case_id,

                    "loan_account_id":
                        loan_id,

                    "finance_customer_id":
                        customer_id,

                    "interaction_sequence":
                        position,

                    "interaction_at":
                        interaction_at,

                    # ----------------------------------------
                    # Geography
                    # ----------------------------------------

                    "region_id":
                        str(
                            case[
                                "region_id"
                            ]
                        ),

                    "region_name":
                        str(
                            case[
                                "region_name"
                            ]
                        ),

                    "city_id":
                        str(
                            case[
                                "city_id"
                            ]
                        ),

                    "city_name":
                        str(
                            case[
                                "city_name"
                            ]
                        ),

                    # ----------------------------------------
                    # Product
                    # ----------------------------------------

                    "finance_product_id":
                        str(
                            loan[
                                "finance_product_id"
                            ]
                        ),

                    "product_code":
                        str(
                            loan[
                                "product_code"
                            ]
                        ),

                    "product_name":
                        str(
                            loan[
                                "product_name"
                            ]
                        ),

                    "product_category":
                        str(
                            loan[
                                "product_category"
                            ]
                        ),

                    # ----------------------------------------
                    # Contact evidence
                    # ----------------------------------------

                    "channel":
                        channel,

                    "field_visit_flag":
                        (
                            channel
                            ==
                            CHANNEL_FIELD_VISIT
                        ),

                    "contact_success":
                        contact_success,

                    # ----------------------------------------
                    # State visible at contact
                    # ----------------------------------------

                    "dpd_at_interaction":
                        int(
                            dpd_at_interaction
                        ),

                    "arrears_at_interaction_inr":
                        round(
                            float(
                                arrears_at_interaction
                            ),
                            2,
                        ),

                    "outstanding_principal_at_interaction_inr":
                        round(
                            float(
                                outstanding_at_interaction
                            ),
                            2,
                        ),

                    # ----------------------------------------
                    # Interaction
                    # ----------------------------------------

                    "offer_type":
                        offer_type,

                    "customer_response":
                        customer_response,

                    "promise_to_pay":
                        False,

                    # IMPORTANT:
                    # None instead of pd.NaT prevents Pandas
                    # from inferring timezone-naive dtype.
                    "promise_date":
                        None,

                    # ----------------------------------------
                    # Actual repayment evidence
                    # ----------------------------------------

                    "payment_after_contact":
                        False,

                    "payment_after_contact_event_id":
                        None,

                    # IMPORTANT:
                    # None instead of pd.NaT.
                    "payment_after_contact_at":
                        None,

                    "payment_after_contact_amount_inr":
                        0.0,

                    "payment_after_promise":
                        pd.NA,

                    # Internal helper.
                    "_case_end":
                        interaction_end,

                    # ----------------------------------------
                    # Provenance
                    # ----------------------------------------

                    "data_origin":
                        None,

                    "generator_version":
                        None,
                }
            )

    interactions = pd.DataFrame(
        rows
    )

    if interactions.empty:
        raise ValueError(
            "Collections interaction generator "
            "produced no records"
        )

    # ========================================================
    # TIMEZONE-AWARE PLACEHOLDER SAFETY
    #
    # These columns start empty and later receive timezone-aware
    # Asia/Kolkata timestamps.
    #
    # Keep them object dtype during mutation.
    # ========================================================

    interactions[
        "promise_date"
    ] = (
        interactions[
            "promise_date"
        ]
        .astype(
            "object"
        )
    )

    interactions[
        "payment_after_contact_at"
    ] = (
        interactions[
            "payment_after_contact_at"
        ]
        .astype(
            "object"
        )
    )

    # ========================================================
    # SORT FIRST
    # ========================================================

    interactions = (
        interactions
        .sort_values(
            [
                "collection_case_id",
                "interaction_sequence",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # ========================================================
    # DERIVE PAYMENT AFTER CONTACT
    #
    # Observation window:
    #
    # interaction
    #     →
    # earliest of:
    #
    # next interaction
    # +14 days
    # case resolution
    # generation end
    #
    # This prevents one payment being attributed repeatedly.
    # ========================================================

    for (
        case_id,
        case_group,
    ) in interactions.groupby(
        "collection_case_id",
        sort=False,
    ):

        _ = case_id

        group_indices = (
            case_group
            .sort_values(
                "interaction_sequence"
            )
            .index
            .tolist()
        )

        for position, row_index in enumerate(
            group_indices
        ):

            interaction_at = pd.Timestamp(
                interactions.at[
                    row_index,
                    "interaction_at"
                ]
            )

            loan_id = str(
                interactions.at[
                    row_index,
                    "loan_account_id"
                ]
            )

            observation_end = (
                interaction_at
                +
                timedelta(
                    days=
                        PAYMENT_AFTER_CONTACT_WINDOW_DAYS
                )
            )

            case_end = pd.Timestamp(
                interactions.at[
                    row_index,
                    "_case_end"
                ]
            )

            observation_end = min(
                observation_end,
                case_end,
                generation_end,
            )

            if (
                position
                +
                1
                <
                len(
                    group_indices
                )
            ):

                next_interaction_at = (
                    pd.Timestamp(
                        interactions.at[
                            group_indices[
                                position
                                +
                                1
                            ],
                            "interaction_at",
                        ]
                    )
                )

                observation_end = min(
                    observation_end,
                    next_interaction_at,
                )

            payment = (
                _find_payment_after_contact(
                    loan_payments=
                        payments_by_loan[
                            loan_id
                        ],

                    interaction_at=
                        interaction_at,

                    observation_end=
                        observation_end,
                )
            )

            if payment is None:
                continue

            interactions.at[
                row_index,
                "payment_after_contact"
            ] = True

            interactions.at[
                row_index,
                "payment_after_contact_event_id"
            ] = str(
                payment[
                    "payment_event_id"
                ]
            )

            # Timezone-aware timestamp assignment is now safe
            # because this column has object dtype.
            interactions.at[
                row_index,
                "payment_after_contact_at"
            ] = pd.Timestamp(
                payment[
                    "actual_payment_at"
                ]
            )

            interactions.at[
                row_index,
                "payment_after_contact_amount_inr"
            ] = round(
                float(
                    payment[
                        "actual_payment_amount_inr"
                    ]
                ),
                2,
            )

    # ========================================================
    # PROMISE TO PAY ASSIGNMENT
    # ========================================================

    interactions = (
        _assign_promises_to_pay(
            interactions=
                interactions,

            rng=
                rng,

            base_ptp_probability=
                promise_to_pay_probability,

            target_payment_after_promise_probability=
                payment_after_promise_probability,
        )
    )

    # ========================================================
    # DETERMINISTIC IDS
    # ========================================================

    interactions = (
        interactions
        .sort_values(
            [
                "interaction_at",
                "collection_case_id",
                "interaction_sequence",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    interactions[
        "collection_interaction_id"
    ] = [
        generate_id(
            "COLINT_SYN",
            index,
            width=8,
        )

        for index
        in range(
            1,
            len(
                interactions
            )
            +
            1,
        )
    ]

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

    interactions[
        "data_origin"
    ] = data_origin

    interactions[
        "generator_version"
    ] = generator_version

    # ========================================================
    # REMOVE INTERNAL HELPERS / FINAL COLUMN ORDER
    # ========================================================

    interactions = interactions[
        [
            "collection_interaction_id",

            "collection_case_id",

            "loan_account_id",
            "finance_customer_id",

            "interaction_sequence",
            "interaction_at",

            "region_id",
            "region_name",

            "city_id",
            "city_name",

            "finance_product_id",
            "product_code",
            "product_name",
            "product_category",

            "channel",
            "field_visit_flag",

            "contact_success",

            "dpd_at_interaction",
            "arrears_at_interaction_inr",
            "outstanding_principal_at_interaction_inr",

            "offer_type",
            "customer_response",

            "promise_to_pay",
            "promise_date",

            "payment_after_contact",
            "payment_after_contact_event_id",
            "payment_after_contact_at",
            "payment_after_contact_amount_inr",

            "payment_after_promise",

            "data_origin",
            "generator_version",
        ]
    ]

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    validate_collection_interactions(
        collection_interactions=
            interactions,

        collection_cases=
            collection_cases,

        finance_customers=
            finance_customers,

        loan_accounts=
            loan_accounts,

        payment_history=
            payment_history,

        generation=
            generation,

        distributions=
            distributions,
    )

    return interactions


# ============================================================
# VALIDATE INTERACTIONS
# ============================================================


def validate_collection_interactions(
    collection_interactions: pd.DataFrame,
    collection_cases: pd.DataFrame,
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
    payment_history: pd.DataFrame,
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
    distributions: Mapping[
        str,
        Any,
    ]
    | None = None,
) -> None:
    """
    Validate Collections interaction history.
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    if distributions is None:
        distributions = (
            load_distribution_config()
        )

    (
        _,
        maximum_interactions,
    ) = (
        _get_interaction_count_range(
            generation
        )
    )

    (
        channel_response_probability,
        _,
        _,
    ) = (
        _get_collection_distributions(
            distributions
        )
    )

    (
        generation_start,
        generation_end,
    ) = (
        _get_generation_window(
            generation
        )
    )

    # ========================================================
    # REQUIRED COLUMNS
    # ========================================================

    required_columns = {
        "collection_interaction_id",

        "collection_case_id",

        "loan_account_id",
        "finance_customer_id",

        "interaction_sequence",
        "interaction_at",

        "region_id",
        "region_name",

        "city_id",
        "city_name",

        "finance_product_id",
        "product_code",
        "product_name",
        "product_category",

        "channel",
        "field_visit_flag",

        "contact_success",

        "dpd_at_interaction",
        "arrears_at_interaction_inr",
        "outstanding_principal_at_interaction_inr",

        "offer_type",
        "customer_response",

        "promise_to_pay",
        "promise_date",

        "payment_after_contact",
        "payment_after_contact_event_id",
        "payment_after_contact_at",
        "payment_after_contact_amount_inr",

        "payment_after_promise",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        -
        set(
            collection_interactions.columns
        )
    )

    if missing:
        raise ValueError(
            "Collections interactions missing columns: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    if collection_interactions.empty:
        raise ValueError(
            "Collections interactions cannot be empty"
        )

    # ========================================================
    # UNIQUE IDS
    # ========================================================

    if (
        collection_interactions[
            "collection_interaction_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate collection_interaction_id found"
        )

    # ========================================================
    # CASE FK
    # ========================================================

    valid_case_ids = set(
        collection_cases[
            "collection_case_id"
        ]
        .astype(str)
    )

    interaction_case_ids = set(
        collection_interactions[
            "collection_case_id"
        ]
        .astype(str)
    )

    invalid_cases = (
        interaction_case_ids
        -
        valid_case_ids
    )

    if invalid_cases:
        raise ValueError(
            "Interactions reference invalid "
            "Collection cases"
        )

    # ========================================================
    # EVERY CASE REPRESENTED
    # ========================================================

    missing_cases = (
        valid_case_ids
        -
        interaction_case_ids
    )

    if missing_cases:
        raise ValueError(
            "Collection cases missing interactions: "
            +
            ", ".join(
                sorted(
                    missing_cases
                )[
                    :20
                ]
            )
        )

    # ========================================================
    # COUNTS PER CASE
    # ========================================================

    counts = (
        collection_interactions
        .groupby(
            "collection_case_id"
        )
        .size()
    )

    if (
        counts
        >
        maximum_interactions
    ).any():
        raise ValueError(
            "Collection case exceeds configured "
            "maximum interactions"
        )

    if (
        counts
        <
        1
    ).any():
        raise ValueError(
            "Every Collection case requires at least "
            "one interaction"
        )

    # ========================================================
    # CASE / LOAN / CUSTOMER CONSISTENCY
    # ========================================================

    case_lookup = (
        collection_cases
        .set_index(
            "collection_case_id"
        )
    )

    for interaction in (
        collection_interactions
        .itertuples(
            index=False
        )
    ):

        case = case_lookup.loc[
            str(
                interaction.collection_case_id
            )
        ]

        if (
            str(
                case[
                    "loan_account_id"
                ]
            )
            !=
            str(
                interaction.loan_account_id
            )
        ):
            raise ValueError(
                "Interaction case/loan mismatch"
            )

        if (
            str(
                case[
                    "finance_customer_id"
                ]
            )
            !=
            str(
                interaction.finance_customer_id
            )
        ):
            raise ValueError(
                "Interaction case/customer mismatch"
            )

        if (
            str(
                case[
                    "finance_product_id"
                ]
            )
            !=
            str(
                interaction.finance_product_id
            )
        ):
            raise ValueError(
                "Interaction case/product mismatch"
            )

    # ========================================================
    # TIMESTAMP ORDER
    # ========================================================

    interaction_times = pd.to_datetime(
        collection_interactions[
            "interaction_at"
        ],
        utc=True,
    )

    if (
        interaction_times
        <
        generation_start
    ).any():
        raise ValueError(
            "Collection interaction precedes "
            "generation window"
        )

    if (
        interaction_times
        >=
        generation_end
    ).any():
        raise ValueError(
            "Collection interaction occurs on/after "
            "generation cutoff"
        )

    for (
        case_id,
        group,
    ) in collection_interactions.groupby(
        "collection_case_id"
    ):

        case = case_lookup.loc[
            str(
                case_id
            )
        ]

        created_at = max(
            pd.to_datetime(
                case[
                    "case_created_at"
                ],
                utc=True,
            ),
            generation_start,
        )

        resolved_at = case[
            "resolved_at"
        ]

        group_times = pd.to_datetime(
            group[
                "interaction_at"
            ],
            utc=True,
        )

        if (
            group_times
            <
            created_at
        ).any():
            raise ValueError(
                "Collection interaction occurs before "
                "case operational window"
            )

        if pd.notna(
            resolved_at
        ):

            if (
                group_times
                >
                pd.to_datetime(
                    resolved_at,
                    utc=True,
                )
            ).any():
                raise ValueError(
                    "Collection interaction occurs after "
                    "case resolution"
                )

    # ========================================================
    # SEQUENCE
    # ========================================================

    for (
        case_id,
        group,
    ) in collection_interactions.groupby(
        "collection_case_id"
    ):

        ordered = (
            group
            .sort_values(
                "interaction_at"
            )
        )

        actual = (
            ordered[
                "interaction_sequence"
            ]
            .astype(int)
            .tolist()
        )

        expected = list(
            range(
                1,
                len(
                    ordered
                )
                +
                1,
            )
        )

        if actual != expected:
            raise ValueError(
                "Invalid interaction sequence for "
                f"{case_id}"
            )

    # ========================================================
    # CHANNEL
    # ========================================================

    valid_channels = set(
        channel_response_probability.keys()
    )

    invalid_channels = (
        set(
            collection_interactions[
                "channel"
            ]
            .astype(str)
        )
        -
        valid_channels
    )

    if invalid_channels:
        raise ValueError(
            "Invalid Collections channels: "
            +
            ", ".join(
                sorted(
                    invalid_channels
                )
            )
        )

    # ========================================================
    # FIELD VISIT
    # ========================================================

    expected_field_visit = (
        collection_interactions[
            "channel"
        ]
        .astype(str)
        ==
        CHANNEL_FIELD_VISIT
    )

    actual_field_visit = (
        collection_interactions[
            "field_visit_flag"
        ]
        .astype(bool)
    )

    if (
        expected_field_visit
        !=
        actual_field_visit
    ).any():
        raise ValueError(
            "field_visit_flag inconsistent with channel"
        )

    # ========================================================
    # CUSTOMER RESPONSE
    # ========================================================

    invalid_responses = (
        set(
            collection_interactions[
                "customer_response"
            ]
            .astype(str)
        )
        -
        VALID_CUSTOMER_RESPONSES
    )

    if invalid_responses:
        raise ValueError(
            "Invalid Collections customer responses"
        )

    unsuccessful = (
        ~collection_interactions[
            "contact_success"
        ]
        .astype(bool)
    )

    if (
        collection_interactions.loc[
            unsuccessful,
            "customer_response",
        ]
        !=
        RESPONSE_NO_CONTACT
    ).any():
        raise ValueError(
            "Failed contact must have NO_CONTACT response"
        )

    # ========================================================
    # OFFER
    # ========================================================

    invalid_offers = (
        set(
            collection_interactions[
                "offer_type"
            ]
            .astype(str)
        )
        -
        VALID_OFFER_TYPES
    )

    if invalid_offers:
        raise ValueError(
            "Invalid Collections offer_type"
        )

    if (
        collection_interactions.loc[
            unsuccessful,
            "offer_type",
        ]
        !=
        OFFER_NONE
    ).any():
        raise ValueError(
            "Failed contact cannot have Collection offer"
        )

    # ========================================================
    # PTP
    # ========================================================

    promise_mask = (
        collection_interactions[
            "promise_to_pay"
        ]
        .astype(bool)
    )

    if (
        promise_mask
        &
        unsuccessful
    ).any():
        raise ValueError(
            "Promise-to-pay requires successful contact"
        )

    if (
        collection_interactions.loc[
            promise_mask,
            "promise_date",
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Promise-to-pay requires promise_date"
        )

    if (
        collection_interactions.loc[
            ~promise_mask,
            "promise_date",
        ]
        .notna()
        .any()
    ):
        raise ValueError(
            "Non-PTP interaction cannot have promise_date"
        )

    if (
        collection_interactions.loc[
            promise_mask,
            "customer_response",
        ]
        !=
        RESPONSE_PROMISE_TO_PAY
    ).any():
        raise ValueError(
            "Promise-to-pay response mismatch"
        )

    # --------------------------------------------------------
    # Promise must occur after interaction.
    # --------------------------------------------------------

    if promise_mask.any():

        promise_dates = pd.to_datetime(
            collection_interactions.loc[
                promise_mask,
                "promise_date",
            ],
            utc=True,
        )

        promise_interactions = pd.to_datetime(
            collection_interactions.loc[
                promise_mask,
                "interaction_at",
            ],
            utc=True,
        )

        if (
            promise_dates
            <=
            promise_interactions
        ).any():
            raise ValueError(
                "promise_date must be after interaction"
            )

    # ========================================================
    # PAYMENT AFTER CONTACT
    # ========================================================

    payment_mask = (
        collection_interactions[
            "payment_after_contact"
        ]
        .astype(bool)
    )

    if (
        collection_interactions.loc[
            payment_mask,
            "payment_after_contact_event_id",
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "payment_after_contact requires payment event"
        )

    if (
        collection_interactions.loc[
            payment_mask,
            "payment_after_contact_at",
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "payment_after_contact requires timestamp"
        )

    if (
        pd.to_numeric(
            collection_interactions.loc[
                payment_mask,
                "payment_after_contact_amount_inr",
            ],
            errors="raise",
        )
        <=
        0
    ).any():
        raise ValueError(
            "payment_after_contact requires positive amount"
        )

    no_payment = ~payment_mask

    if (
        collection_interactions.loc[
            no_payment,
            "payment_after_contact_event_id",
        ]
        .notna()
        .any()
    ):
        raise ValueError(
            "No-payment interaction cannot reference "
            "payment event"
        )

    if (
        collection_interactions.loc[
            no_payment,
            "payment_after_contact_at",
        ]
        .notna()
        .any()
    ):
        raise ValueError(
            "No-payment interaction cannot have "
            "payment timestamp"
        )

    if (
        pd.to_numeric(
            collection_interactions.loc[
                no_payment,
                "payment_after_contact_amount_inr",
            ],
            errors="raise",
        )
        !=
        0
    ).any():
        raise ValueError(
            "No-payment interaction must have zero "
            "payment amount"
        )

    # ========================================================
    # PAYMENT FK
    # ========================================================

    valid_payment_ids = set(
        payment_history[
            "payment_event_id"
        ]
        .astype(str)
    )

    referenced_payment_ids = set(
        collection_interactions.loc[
            payment_mask,
            "payment_after_contact_event_id",
        ]
        .astype(str)
    )

    invalid_payment_ids = (
        referenced_payment_ids
        -
        valid_payment_ids
    )

    if invalid_payment_ids:
        raise ValueError(
            "Interactions reference invalid Finance "
            "payment events"
        )

    # ========================================================
    # PAYMENT MUST BELONG TO SAME LOAN
    # ========================================================

    payment_lookup = (
        payment_history
        .set_index(
            "payment_event_id"
        )
    )

    for interaction in (
        collection_interactions.loc[
            payment_mask
        ]
        .itertuples(
            index=False
        )
    ):

        payment = payment_lookup.loc[
            str(
                interaction.payment_after_contact_event_id
            )
        ]

        if (
            str(
                payment[
                    "loan_account_id"
                ]
            )
            !=
            str(
                interaction.loan_account_id
            )
        ):
            raise ValueError(
                "Attributed Finance payment belongs to "
                "different loan"
            )

    # ========================================================
    # PAYMENT MUST OCCUR AFTER CONTACT
    # ========================================================

    if payment_mask.any():

        interaction_at = pd.to_datetime(
            collection_interactions.loc[
                payment_mask,
                "interaction_at",
            ],
            utc=True,
        )

        paid_at = pd.to_datetime(
            collection_interactions.loc[
                payment_mask,
                "payment_after_contact_at",
            ],
            utc=True,
        )

        if (
            paid_at
            <=
            interaction_at
        ).any():
            raise ValueError(
                "Attributed payment must occur after "
                "Collection interaction"
            )

    # ========================================================
    # PAYMENT AFTER PROMISE
    # ========================================================

    if (
        collection_interactions.loc[
            ~promise_mask,
            "payment_after_promise",
        ]
        .notna()
        .any()
    ):
        raise ValueError(
            "payment_after_promise must be NULL when "
            "no promise exists"
        )

    # ========================================================
    # DPD / ARREARS / OUTSTANDING
    # ========================================================

    if (
        pd.to_numeric(
            collection_interactions[
                "dpd_at_interaction"
            ],
            errors="raise",
        )
        <
        0
    ).any():
        raise ValueError(
            "DPD cannot be negative"
        )

    if (
        pd.to_numeric(
            collection_interactions[
                "arrears_at_interaction_inr"
            ],
            errors="raise",
        )
        <
        -0.01
    ).any():
        raise ValueError(
            "Interaction arrears cannot be negative"
        )

    if (
        pd.to_numeric(
            collection_interactions[
                "outstanding_principal_at_interaction_inr"
            ],
            errors="raise",
        )
        <
        -0.01
    ).any():
        raise ValueError(
            "Interaction outstanding cannot be negative"
        )

    # ========================================================
    # PROVENANCE
    # ========================================================

    expected_origin = str(
        generation.get(
            "provenance",
            {},
        ).get(
            "data_origin",
            "SYNTHETIC",
        )
    )

    if (
        collection_interactions[
            "data_origin"
        ]
        .astype(str)
        !=
        expected_origin
    ).any():
        raise ValueError(
            "Unexpected Collection interaction data_origin"
        )

    expected_version = str(
        generation.get(
            "generator_version",
            "1.0.0",
        )
    )

    if (
        collection_interactions[
            "generator_version"
        ]
        .astype(str)
        !=
        expected_version
    ).any():
        raise ValueError(
            "Unexpected Collection interaction "
            "generator_version"
        )

    # ========================================================
    # HIDDEN AI / TRUTH LEAKAGE
    # ========================================================

    forbidden_columns = {
        "risk_score",
        "risk_band",

        "roll_forward_risk",

        "recovery_probability",

        "best_channel",
        "recommended_channel",

        "recommended_action",

        "contact_probability",

        "promise_probability",

        "payment_probability",

        "cure_probability",

        "default_probability",

        "true_default",
        "true_cure_outcome",

        "confidence",
        "confidence_score",
    }

    leaked = (
        forbidden_columns
        &
        set(
            collection_interactions.columns
        )
    )

    if leaked:
        raise ValueError(
            "Hidden Collections intelligence leaked "
            "into interactions: "
            +
            ", ".join(
                sorted(
                    leaked
                )
            )
        )


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_collection_interaction_master(
    collection_cases: pd.DataFrame,
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
    payment_history: pd.DataFrame,
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
    distributions: Mapping[
        str,
        Any,
    ]
    | None = None,
) -> pd.DataFrame:
    """
    Public entry point for generate_all.py.
    """

    return generate_collection_interactions(
        collection_cases=
            collection_cases,

        finance_customers=
            finance_customers,

        loan_accounts=
            loan_accounts,

        payment_history=
            payment_history,

        generation=
            generation,

        distributions=
            distributions,
    )


# ============================================================
# LOCAL TEST
# ============================================================


if __name__ == "__main__":

    from data.generators.master.geography import (
        generate_geography,
    )

    from data.generators.master.finance_products import (
        generate_finance_product_master,
    )

    from data.generators.finance.customers import (
        generate_finance_customer_master,
    )

    from data.generators.finance.loans import (
        generate_loan_master,
    )

    from data.generators.finance.payments import (
        generate_payment_master,
    )

    from data.generators.collections.cases import (
        generate_collection_case_master,
    )

    # ========================================================
    # UPSTREAM FINANCE WORLD
    # ========================================================

    (
        regions_df,
        cities_df,
    ) = generate_geography()

    finance_products_df = (
        generate_finance_product_master()
    )

    finance_customers_df = (
        generate_finance_customer_master(
            regions=
                regions_df,

            cities=
                cities_df,
        )
    )

    loan_accounts_df = (
        generate_loan_master(
            finance_customers=
                finance_customers_df,

            finance_products=
                finance_products_df,
        )
    )

    payment_history_df = (
        generate_payment_master(
            finance_customers=
                finance_customers_df,

            loan_accounts=
                loan_accounts_df,
        )
    )

    # ========================================================
    # COLLECTION CASES
    # ========================================================

    collection_cases_df = (
        generate_collection_case_master(
            finance_customers=
                finance_customers_df,

            loan_accounts=
                loan_accounts_df,

            payment_history=
                payment_history_df,
        )
    )

    # ========================================================
    # COLLECTION INTERACTIONS
    # ========================================================

    interactions_df = (
        generate_collection_interaction_master(
            collection_cases=
                collection_cases_df,

            finance_customers=
                finance_customers_df,

            loan_accounts=
                loan_accounts_df,

            payment_history=
                payment_history_df,
        )
    )

    # ========================================================
    # SAMPLE
    # ========================================================

    print(
        "\n=== COLLECTION INTERACTION SAMPLE ===\n"
    )

    print(
        interactions_df[
            [
                "collection_interaction_id",

                "collection_case_id",
                "loan_account_id",

                "interaction_sequence",
                "interaction_at",

                "channel",
                "contact_success",

                "dpd_at_interaction",
                "arrears_at_interaction_inr",

                "offer_type",
                "customer_response",

                "promise_to_pay",
                "promise_date",

                "payment_after_contact",
                "payment_after_contact_at",
                "payment_after_contact_amount_inr",
            ]
        ]
        .head(
            50
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # INTERACTIONS PER CASE
    # ========================================================

    interactions_per_case = (
        interactions_df
        .groupby(
            "collection_case_id"
        )
        .size()
    )

    print(
        "\n=== INTERACTIONS PER CASE ===\n"
    )

    print(
        interactions_per_case
        .value_counts()
        .sort_index()
        .rename_axis(
            "interaction_count"
        )
        .reset_index(
            name=
                "case_count"
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # CHANNEL MIX
    # ========================================================

    print(
        "\n=== COLLECTION CHANNEL MIX ===\n"
    )

    channel_summary = (
        interactions_df[
            "channel"
        ]
        .value_counts()
        .rename_axis(
            "channel"
        )
        .reset_index(
            name=
                "interaction_count"
        )
    )

    channel_summary[
        "rate"
    ] = (
        channel_summary[
            "interaction_count"
        ]
        /
        len(
            interactions_df
        )
    ).round(
        4
    )

    print(
        channel_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # CONTACT SUCCESS BY CHANNEL
    # ========================================================

    print(
        "\n=== CONTACT SUCCESS BY CHANNEL ===\n"
    )

    contact_summary = (
        interactions_df
        .groupby(
            "channel"
        )
        .agg(
            interactions=(
                "collection_interaction_id",
                "size",
            ),

            successful_contacts=(
                "contact_success",
                "sum",
            ),

            contact_success_rate=(
                "contact_success",
                "mean",
            ),
        )
        .reset_index()
    )

    contact_summary[
        "contact_success_rate"
    ] = (
        contact_summary[
            "contact_success_rate"
        ]
        .round(
            4
        )
    )

    print(
        contact_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # CUSTOMER RESPONSE
    # ========================================================

    print(
        "\n=== COLLECTION CUSTOMER RESPONSE ===\n"
    )

    response_summary = (
        interactions_df[
            "customer_response"
        ]
        .value_counts()
        .rename_axis(
            "customer_response"
        )
        .reset_index(
            name=
                "interaction_count"
        )
    )

    response_summary[
        "rate"
    ] = (
        response_summary[
            "interaction_count"
        ]
        /
        len(
            interactions_df
        )
    ).round(
        4
    )

    print(
        response_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # PROMISE TO PAY
    # ========================================================

    contacted_df = (
        interactions_df[
            interactions_df[
                "contact_success"
            ]
            .astype(bool)
        ]
    )

    promised_df = (
        interactions_df[
            interactions_df[
                "promise_to_pay"
            ]
            .astype(bool)
        ]
    )

    print(
        "\n=== PROMISE TO PAY ===\n"
    )

    print(
        "Successful contacts:",
        len(
            contacted_df
        ),
    )

    print(
        "Promises to pay:",
        len(
            promised_df
        ),
    )

    ptp_rate = (
        len(
            promised_df
        )
        /
        max(
            len(
                contacted_df
            ),
            1,
        )
    )

    print(
        "PTP rate among successful contacts:",
        round(
            ptp_rate,
            4,
        ),
    )

    # ========================================================
    # PAYMENT AFTER CONTACT
    # ========================================================

    payment_after_contact_count = int(
        interactions_df[
            "payment_after_contact"
        ]
        .astype(bool)
        .sum()
    )

    print(
        "\n=== PAYMENT AFTER CONTACT ===\n"
    )

    print(
        "Interactions followed by actual payment:",
        payment_after_contact_count,
    )

    print(
        "Payment-after-contact rate:",
        round(
            payment_after_contact_count
            /
            len(
                interactions_df
            ),
            4,
        ),
    )

    # ========================================================
    # PAYMENT AFTER PROMISE
    # ========================================================

    if not promised_df.empty:

        kept_promises = int(
            promised_df[
                "payment_after_promise"
            ]
            .astype(
                "boolean"
            )
            .fillna(
                False
            )
            .sum()
        )

        print(
            "\n=== PAYMENT AFTER PROMISE ===\n"
        )

        print(
            "Promised interactions:",
            len(
                promised_df
            ),
        )

        print(
            "Payments after promise:",
            kept_promises,
        )

        print(
            "Payment-after-promise rate:",
            round(
                kept_promises
                /
                len(
                    promised_df
                ),
                4,
            ),
        )

    # ========================================================
    # FIELD VISITS
    # ========================================================

    print(
        "\n=== FIELD VISITS ===\n"
    )

    field_visits = (
        interactions_df[
            interactions_df[
                "field_visit_flag"
            ]
            .astype(bool)
        ]
    )

    print(
        "Field visits:",
        len(
            field_visits
        ),
    )

    print(
        "Field visit share:",
        round(
            len(
                field_visits
            )
            /
            len(
                interactions_df
            ),
            4,
        ),
    )

    # ========================================================
    # DPD SUMMARY
    # ========================================================

    print(
        "\n=== INTERACTION DPD SUMMARY ===\n"
    )

    print(
        interactions_df[
            "dpd_at_interaction"
        ]
        .describe()
        .round(
            2
        )
        .to_string()
    )

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    print(
        "\n=== COLLECTION INTERACTION VALIDATION ===\n"
    )

    print(
        "Rows:",
        len(
            interactions_df
        ),
    )

    print(
        "Unique interaction IDs:",
        interactions_df[
            "collection_interaction_id"
        ].nunique(),
    )

    print(
        "Cases represented:",
        interactions_df[
            "collection_case_id"
        ].nunique(),
    )

    print(
        "Loans represented:",
        interactions_df[
            "loan_account_id"
        ].nunique(),
    )

    print(
        "Customers represented:",
        interactions_df[
            "finance_customer_id"
        ].nunique(),
    )

    print(
        "Minimum interactions/case:",
        int(
            interactions_per_case.min()
        ),
    )

    print(
        "Maximum interactions/case:",
        int(
            interactions_per_case.max()
        ),
    )

    print(
        "Duplicate interaction IDs:",
        int(
            interactions_df[
                "collection_interaction_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    forbidden_columns = {
        "risk_score",
        "roll_forward_risk",

        "recovery_probability",

        "best_channel",
        "recommended_channel",

        "recommended_action",

        "contact_probability",
        "promise_probability",

        "default_probability",

        "true_default",

        "confidence",
    }

    leaked_columns = sorted(
        forbidden_columns
        &
        set(
            interactions_df.columns
        )
    )

    print(
        "Hidden truth leakage:",
        leaked_columns,
    )

    print(
        "\nGenerated "
        f"{len(interactions_df)} "
        "Collection interactions successfully."
    )