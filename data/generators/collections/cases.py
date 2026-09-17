"""
Synthetic Collections Case Generator
for Mahindra AI Nexus.

Generates operational collection cases from synthetic Finance
payment history.

Dependency chain:

    Finance Customers
          +
    Loan Accounts
          +
    Payment History
          ↓
    Collection Cases
          ↓
    Collection Interactions


============================================================
IMPORTANT ARCHITECTURAL RULE
============================================================

Collection cases are NOT generated randomly.

A case is created only when observable payment evidence reaches
the configured Collections DPD threshold:

    generation.yaml

        collections:
            create_case_at_dpd: 15


============================================================
IMPORTANT TEMPORAL RULE
============================================================

A Collection case can start in TWO ways.

1. PAYMENT_EVENT

   A recorded payment event already shows:

       DPD >= threshold
       arrears > 0


2. AGED_TO_CUTOFF

   The latest payment event still has unresolved arrears but
   has not yet reached the threshold.

   Example:

       latest event DPD = 4
       no further payment
       11 more days pass
       DPD reaches 15

   The case must therefore open when the arrears AGE into the
   Collections threshold even though there was no new payment
   event at exactly that moment.

This is essential for accurate point-in-time Collections state.


============================================================
CASE EPISODES
============================================================

A loan may create multiple collection cases.

Example:

    DPD reaches 15
        ↓
    Case 1
        ↓
    arrears cured
        ↓
    Case 1 RESOLVED
        ↓
    another missed installment
        ↓
    DPD reaches 15 again
        ↓
    Case 2


============================================================
CASE STATUS
============================================================

OPEN
    unresolved arrears remain and DPD is currently at or above
    the configured Collections threshold.

MONITORING
    a Collection case existed but remaining arrears currently
    have DPD below the threshold.

RESOLVED
    arrears were completely cured.


============================================================
NO HIDDEN TRUTH
============================================================

This generator DOES NOT expose:

    default_probability
    collection_probability
    cure_probability
    risk_score
    recommended_action
    recommended_channel
    true_default
    true_cure_outcome


============================================================
OUTPUT
============================================================

This module DOES NOT write CSV files.

Later generate_all.py will write:

    data/synthetic/collections/cases.csv
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
    generate_id,
)


# ============================================================
# CASE STATUS
# ============================================================


CASE_STATUS_OPEN = "OPEN"
CASE_STATUS_MONITORING = "MONITORING"
CASE_STATUS_RESOLVED = "RESOLVED"


VALID_CASE_STATUSES = {
    CASE_STATUS_OPEN,
    CASE_STATUS_MONITORING,
    CASE_STATUS_RESOLVED,
}


# ============================================================
# CASE TRIGGER SOURCES
# ============================================================


CASE_TRIGGER_PAYMENT_EVENT = "PAYMENT_EVENT"
CASE_TRIGGER_AGED_TO_CUTOFF = "AGED_TO_CUTOFF"


VALID_CASE_TRIGGER_SOURCES = {
    CASE_TRIGGER_PAYMENT_EVENT,
    CASE_TRIGGER_AGED_TO_CUTOFF,
}


# ============================================================
# PRIORITIES
# ============================================================


PRIORITY_LOW = "LOW"
PRIORITY_MEDIUM = "MEDIUM"
PRIORITY_HIGH = "HIGH"
PRIORITY_CRITICAL = "CRITICAL"


VALID_PRIORITIES = {
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    PRIORITY_HIGH,
    PRIORITY_CRITICAL,
}


# ============================================================
# REQUIRED INPUT COLUMNS
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


LOAN_REQUIRED_COLUMNS: set[str] = {
    "loan_account_id",

    "finance_customer_id",

    "region_id",
    "region_name",

    "city_id",
    "city_name",

    "finance_product_id",
    "product_code",
    "product_name",
    "product_category",

    "disbursed_at",
    "scheduled_maturity_at",

    "principal_inr",
    "interest_rate_pct",
    "tenure_months",
    "emi_amount_inr",

    "data_origin",
    "generator_version",
}


PAYMENT_REQUIRED_COLUMNS: set[str] = {
    "payment_event_id",

    "loan_account_id",
    "finance_customer_id",

    "installment_number",

    "payment_due_at",

    "payment_status",
    "actual_payment_at",

    "days_past_due_after_event",
    "arrears_amount_inr",

    "outstanding_principal_inr",

    "data_origin",
    "generator_version",
}


# ============================================================
# BASIC HELPERS
# ============================================================


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
            f"{name} must be an integer"
        )

    try:

        parsed = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as exc:

        raise TypeError(
            f"{name} must be an integer"
        ) from exc

    if parsed <= 0:

        raise ValueError(
            f"{name} must be > 0"
        )

    return parsed


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

        start_value = (
            generation[
                "time"
            ][
                "start_date"
            ]
        )

        end_value = (
            generation[
                "time"
            ][
                "end_date"
            ]
        )

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
            "generation end must be after start"
        )

    return (
        start,
        end,
    )


# ============================================================
# COLLECTION CONFIG
# ============================================================


def _get_collection_config(
    generation: Mapping[
        str,
        Any,
    ],
) -> tuple[
    int,
    int,
]:
    """
    Return configured:

        Collections DPD threshold
        maximum Collection cases
    """

    try:

        collections = (
            generation[
                "collections"
            ]
        )

        dpd_threshold = (
            _as_positive_int(
                collections[
                    "create_case_at_dpd"
                ],
                (
                    "generation.collections."
                    "create_case_at_dpd"
                ),
            )
        )

        maximum_cases = (
            _as_positive_int(
                collections[
                    "maximum_cases"
                ],
                (
                    "generation.collections."
                    "maximum_cases"
                ),
            )
        )

    except KeyError as exc:

        raise KeyError(
            "Missing Collections case configuration"
        ) from exc

    return (
        dpd_threshold,
        maximum_cases,
    )


# ============================================================
# INPUT VALIDATION
# ============================================================


def _validate_inputs(
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
    payment_history: pd.DataFrame,
) -> None:
    """
    Validate Finance dependencies.
    """

    datasets = {
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
        dataset_name,
        (
            dataframe,
            required_columns,
        ),
    ) in datasets.items():

        if dataframe.empty:

            raise ValueError(
                f"{dataset_name} cannot be empty"
            )

        missing = (
            required_columns
            -
            set(
                dataframe.columns
            )
        )

        if missing:

            raise ValueError(
                f"{dataset_name} missing columns: "
                +
                ", ".join(
                    sorted(
                        missing
                    )
                )
            )

    # --------------------------------------------------------
    # Unique IDs
    # --------------------------------------------------------

    if (
        finance_customers[
            "finance_customer_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Duplicate finance_customer_id values found"
        )

    if (
        loan_accounts[
            "loan_account_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Duplicate loan_account_id values found"
        )

    if (
        payment_history[
            "payment_event_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Duplicate payment_event_id values found"
        )

    # --------------------------------------------------------
    # Loan -> Customer FK
    # --------------------------------------------------------

    valid_customer_ids = set(
        finance_customers[
            "finance_customer_id"
        ]
        .astype(str)
    )

    invalid_loan_customers = (
        set(
            loan_accounts[
                "finance_customer_id"
            ]
            .astype(str)
        )
        -
        valid_customer_ids
    )

    if invalid_loan_customers:

        raise ValueError(
            "Loans reference invalid Finance customers"
        )

    # --------------------------------------------------------
    # Payment -> Loan FK
    # --------------------------------------------------------

    valid_loan_ids = set(
        loan_accounts[
            "loan_account_id"
        ]
        .astype(str)
    )

    invalid_payment_loans = (
        set(
            payment_history[
                "loan_account_id"
            ]
            .astype(str)
        )
        -
        valid_loan_ids
    )

    if invalid_payment_loans:

        raise ValueError(
            "Payments reference invalid Finance loans"
        )


# ============================================================
# PREPARE PAYMENT TIMELINE
# ============================================================


def _prepare_payment_history(
    payment_history: pd.DataFrame,
) -> pd.DataFrame:
    """
    Prepare internal temporal columns.

    _state_known_at
        When payment outcome became observable.

    _dpd_reference_at
        Timestamp corresponding to the recorded DPD value.

    These helper columns are NOT included in output.
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

    # ========================================================
    # PAYMENT STATE-KNOWN TIME
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
            "Unable to determine payment "
            "state-known timestamp"
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

        paid_due = (
            payments.loc[
                paid,
                "payment_due_at",
            ]
        )

        paid_actual = (
            payments.loc[
                paid,
                "actual_payment_at",
            ]
        )

        paid_reference = pd.concat(
            [
                paid_due,
                paid_actual,
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

    if (
        payments[
            "_dpd_reference_at"
        ]
        .isna()
        .any()
    ):

        raise ValueError(
            "Unable to determine DPD reference timestamp"
        )

    return (
        payments
        .sort_values(
            [
                "loan_account_id",
                "installment_number",
            ]
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# PRIORITY
# ============================================================


def _derive_case_priority(
    dpd: int,
) -> str:
    """
    Synthetic Collection priority from observable DPD.

        15-29  LOW
        30-59  MEDIUM
        60-89  HIGH
        90+    CRITICAL
    """

    dpd = int(
        dpd
    )

    if dpd >= 90:

        return PRIORITY_CRITICAL

    if dpd >= 60:

        return PRIORITY_HIGH

    if dpd >= 30:

        return PRIORITY_MEDIUM

    return PRIORITY_LOW


# ============================================================
# CURRENT DPD AT CUTOFF
# ============================================================


def _current_dpd_as_of_cutoff(
    latest_payment_row: Mapping[
        str,
        Any,
    ],
    cutoff: pd.Timestamp,
) -> int:
    """
    Age unresolved arrears from the latest recorded payment
    state until the requested observation cutoff.

    Example:

        recorded DPD = 4
        reference time = July 15

        cutoff = Aug 1

        current DPD ~= 21
    """

    arrears = float(
        latest_payment_row[
            "arrears_amount_inr"
        ]
    )

    recorded_dpd = int(
        latest_payment_row[
            "days_past_due_after_event"
        ]
    )

    if (
        arrears
        <=
        0.01
    ):

        return 0

    if recorded_dpd <= 0:

        return 0

    reference_at = pd.to_datetime(
        latest_payment_row[
            "_dpd_reference_at"
        ],
        utc=True,
    )

    if cutoff <= reference_at:

        return recorded_dpd

    elapsed_seconds = (
        cutoff
        -
        reference_at
    ).total_seconds()

    additional_days = int(
        np.ceil(
            elapsed_seconds
            /
            86400.0
        )
    )

    return max(
        recorded_dpd
        +
        additional_days,
        recorded_dpd,
    )


# ============================================================
# ESTIMATE THRESHOLD CROSSING
# ============================================================


def _estimate_threshold_crossing(
    reference_at: pd.Timestamp,
    observed_dpd: int,
    dpd_threshold: int,
    disbursed_at: pd.Timestamp,
    generation_end: pd.Timestamp,
) -> pd.Timestamp:
    """
    Estimate timestamp at which unresolved arrears crossed the
    configured DPD threshold.

    Works both when:

        observed_dpd >= threshold

    and when:

        observed_dpd < threshold
        but arrears later aged into the threshold.
    """

    observed_dpd = int(
        observed_dpd
    )

    dpd_threshold = int(
        dpd_threshold
    )

    difference_days = (
        dpd_threshold
        -
        observed_dpd
    )

    estimated = (
        reference_at
        +
        timedelta(
            days=
                difference_days
        )
    )

    estimated = max(
        estimated,
        disbursed_at,
    )

    if estimated >= generation_end:

        estimated = (
            generation_end
            -
            timedelta(
                seconds=1
            )
        )

    return estimated


# ============================================================
# NEW CASE DICTIONARY
# ============================================================


def _new_case(
    loan: Mapping[
        str,
        Any,
    ],
    sequence_number: int,
    trigger_payment: Mapping[
        str,
        Any,
    ],
    trigger_source: str,
    dpd_threshold: int,
    trigger_dpd: int,
    case_created_at: pd.Timestamp,
) -> dict[
    str,
    Any,
]:
    """
    Build common Collection case structure.
    """

    arrears = float(
        trigger_payment[
            "arrears_amount_inr"
        ]
    )

    return {
        "loan_account_id":
            str(
                loan[
                    "loan_account_id"
                ]
            ),

        "finance_customer_id":
            str(
                loan[
                    "finance_customer_id"
                ]
            ),

        "loan_case_sequence":
            int(
                sequence_number
            ),

        "region_id":
            str(
                loan[
                    "region_id"
                ]
            ),

        "region_name":
            str(
                loan[
                    "region_name"
                ]
            ),

        "city_id":
            str(
                loan[
                    "city_id"
                ]
            ),

        "city_name":
            str(
                loan[
                    "city_name"
                ]
            ),

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

        "case_created_at":
            case_created_at,

        "case_trigger_source":
            trigger_source,

        "trigger_payment_event_id":
            str(
                trigger_payment[
                    "payment_event_id"
                ]
            ),

        "case_trigger_dpd":
            int(
                dpd_threshold
            ),

        "observed_dpd_at_trigger_event":
            int(
                trigger_payment[
                    "days_past_due_after_event"
                ]
            ),

        "dpd_at_case_creation":
            int(
                trigger_dpd
            ),

        "arrears_at_trigger_event_inr":
            round(
                arrears,
                2,
            ),

        "priority_at_creation":
            _derive_case_priority(
                trigger_dpd
            ),

        "peak_observed_dpd":
            int(
                trigger_dpd
            ),

        "peak_observed_arrears_inr":
            round(
                arrears,
                2,
            ),

        "case_status":
            None,

        "current_dpd":
            None,

        "current_arrears_inr":
            None,

        "resolved_at":
            None,

        "resolution_payment_event_id":
            None,

        "resolution_type":
            None,
    }


# ============================================================
# BUILD CASE EPISODES FOR ONE LOAN
# ============================================================


def _build_loan_case_episodes(
    loan: Mapping[
        str,
        Any,
    ],
    loan_payments: pd.DataFrame,
    dpd_threshold: int,
    generation_end: pd.Timestamp,
) -> list[
    dict[str, Any]
]:
    """
    Build all Collection episodes for a single loan.
    """

    if loan_payments.empty:

        return []

    payments = (
        loan_payments
        .sort_values(
            "installment_number"
        )
        .reset_index(
            drop=True
        )
    )

    disbursed_at = pd.to_datetime(
        loan[
            "disbursed_at"
        ],
        utc=True,
    )

    episodes: list[
        dict[str, Any]
    ] = []

    active_case: dict[
        str,
        Any,
    ] | None = None

    sequence_number = 0

    # ========================================================
    # PROCESS OBSERVED PAYMENT EVENTS
    # ========================================================

    for payment in payments.to_dict(
        orient="records"
    ):

        observed_dpd = int(
            payment[
                "days_past_due_after_event"
            ]
        )

        arrears = float(
            payment[
                "arrears_amount_inr"
            ]
        )

        # ====================================================
        # OPEN CASE FROM PAYMENT EVENT
        # ====================================================

        if (
            active_case is None
            and
            arrears
            >
            0.01
            and
            observed_dpd
            >=
            dpd_threshold
        ):

            sequence_number += 1

            reference_at = pd.to_datetime(
                payment[
                    "_dpd_reference_at"
                ],
                utc=True,
            )

            created_at = (
                _estimate_threshold_crossing(
                    reference_at=
                        reference_at,

                    observed_dpd=
                        observed_dpd,

                    dpd_threshold=
                        dpd_threshold,

                    disbursed_at=
                        disbursed_at,

                    generation_end=
                        generation_end,
                )
            )

            active_case = (
                _new_case(
                    loan=
                        loan,

                    sequence_number=
                        sequence_number,

                    trigger_payment=
                        payment,

                    trigger_source=
                        CASE_TRIGGER_PAYMENT_EVENT,

                    dpd_threshold=
                        dpd_threshold,

                    trigger_dpd=
                        dpd_threshold,

                    case_created_at=
                        created_at,
                )
            )

        # ====================================================
        # UPDATE ACTIVE CASE
        # ====================================================

        if active_case is not None:

            active_case[
                "peak_observed_dpd"
            ] = max(
                int(
                    active_case[
                        "peak_observed_dpd"
                    ]
                ),
                observed_dpd,
            )

            active_case[
                "peak_observed_arrears_inr"
            ] = round(
                max(
                    float(
                        active_case[
                            "peak_observed_arrears_inr"
                        ]
                    ),
                    arrears,
                ),
                2,
            )

            # =================================================
            # CURE
            # =================================================

            if (
                arrears
                <=
                0.01
                and
                observed_dpd
                ==
                0
            ):

                if pd.notna(
                    payment[
                        "actual_payment_at"
                    ]
                ):

                    resolved_at = pd.to_datetime(
                        payment[
                            "actual_payment_at"
                        ],
                        utc=True,
                    )

                else:

                    resolved_at = pd.to_datetime(
                        payment[
                            "_state_known_at"
                        ],
                        utc=True,
                    )

                active_case[
                    "case_status"
                ] = (
                    CASE_STATUS_RESOLVED
                )

                active_case[
                    "current_dpd"
                ] = 0

                active_case[
                    "current_arrears_inr"
                ] = 0.0

                active_case[
                    "resolved_at"
                ] = resolved_at

                active_case[
                    "resolution_payment_event_id"
                ] = str(
                    payment[
                        "payment_event_id"
                    ]
                )

                active_case[
                    "resolution_type"
                ] = "PAYMENT_CURE"

                episodes.append(
                    active_case
                )

                active_case = None

    # ========================================================
    # LATEST OBSERVED PAYMENT STATE
    # ========================================================

    latest_payment = (
        payments.iloc[
            -1
        ]
        .to_dict()
    )

    latest_arrears = float(
        latest_payment[
            "arrears_amount_inr"
        ]
    )

    latest_observed_dpd = int(
        latest_payment[
            "days_past_due_after_event"
        ]
    )

    current_dpd = (
        _current_dpd_as_of_cutoff(
            latest_payment_row=
                latest_payment,

            cutoff=
                generation_end,
        )
    )

    # ========================================================
    # CRITICAL FIX:
    #
    # No payment event crossed 15 DPD, but unresolved arrears
    # aged beyond 15 DPD before generation_end.
    # ========================================================

    if (
        active_case is None
        and
        latest_arrears
        >
        0.01
        and
        latest_observed_dpd
        <
        dpd_threshold
        and
        current_dpd
        >=
        dpd_threshold
    ):

        sequence_number += 1

        reference_at = pd.to_datetime(
            latest_payment[
                "_dpd_reference_at"
            ],
            utc=True,
        )

        created_at = (
            _estimate_threshold_crossing(
                reference_at=
                    reference_at,

                observed_dpd=
                    latest_observed_dpd,

                dpd_threshold=
                    dpd_threshold,

                disbursed_at=
                    disbursed_at,

                generation_end=
                    generation_end,
            )
        )

        active_case = (
            _new_case(
                loan=
                    loan,

                sequence_number=
                    sequence_number,

                trigger_payment=
                    latest_payment,

                trigger_source=
                    CASE_TRIGGER_AGED_TO_CUTOFF,

                dpd_threshold=
                    dpd_threshold,

                trigger_dpd=
                    dpd_threshold,

                case_created_at=
                    created_at,
            )
        )

        active_case[
            "peak_observed_dpd"
        ] = max(
            int(
                active_case[
                    "peak_observed_dpd"
                ]
            ),
            current_dpd,
        )

    # ========================================================
    # FINALIZE UNRESOLVED CASE
    # ========================================================

    if active_case is not None:

        if (
            latest_arrears
            <=
            0.01
        ):

            active_case[
                "case_status"
            ] = (
                CASE_STATUS_RESOLVED
            )

            active_case[
                "current_dpd"
            ] = 0

            active_case[
                "current_arrears_inr"
            ] = 0.0

            active_case[
                "resolved_at"
            ] = pd.to_datetime(
                latest_payment[
                    "_state_known_at"
                ],
                utc=True,
            )

            active_case[
                "resolution_payment_event_id"
            ] = str(
                latest_payment[
                    "payment_event_id"
                ]
            )

            active_case[
                "resolution_type"
            ] = "PAYMENT_CURE"

        elif current_dpd >= dpd_threshold:

            active_case[
                "case_status"
            ] = (
                CASE_STATUS_OPEN
            )

            active_case[
                "current_dpd"
            ] = int(
                current_dpd
            )

            active_case[
                "current_arrears_inr"
            ] = round(
                latest_arrears,
                2,
            )

            active_case[
                "peak_observed_dpd"
            ] = max(
                int(
                    active_case[
                        "peak_observed_dpd"
                    ]
                ),
                current_dpd,
            )

            active_case[
                "peak_observed_arrears_inr"
            ] = round(
                max(
                    float(
                        active_case[
                            "peak_observed_arrears_inr"
                        ]
                    ),
                    latest_arrears,
                ),
                2,
            )

        else:

            active_case[
                "case_status"
            ] = (
                CASE_STATUS_MONITORING
            )

            active_case[
                "current_dpd"
            ] = int(
                current_dpd
            )

            active_case[
                "current_arrears_inr"
            ] = round(
                latest_arrears,
                2,
            )

        episodes.append(
            active_case
        )

    return episodes


# ============================================================
# APPLY CASE LIMIT
# ============================================================


def _apply_case_limit(
    cases: pd.DataFrame,
    maximum_cases: int,
) -> pd.DataFrame:
    """
    Respect collections.maximum_cases.

    Current unresolved cases are never dropped.

    If unresolved cases alone exceed the configured maximum,
    fail loudly instead of silently discarding them.
    """

    if len(
        cases
    ) <= maximum_cases:

        return (
            cases
            .copy()
            .reset_index(
                drop=True
            )
        )

    unresolved = (
        cases[
            cases[
                "case_status"
            ]
            .isin(
                [
                    CASE_STATUS_OPEN,
                    CASE_STATUS_MONITORING,
                ]
            )
        ]
        .copy()
    )

    resolved = (
        cases[
            cases[
                "case_status"
            ]
            ==
            CASE_STATUS_RESOLVED
        ]
        .copy()
    )

    if len(
        unresolved
    ) > maximum_cases:

        raise ValueError(
            "Current unresolved Collection cases exceed "
            "configured maximum_cases. "
            f"Unresolved={len(unresolved)}, "
            f"maximum={maximum_cases}"
        )

    remaining_capacity = (
        maximum_cases
        -
        len(
            unresolved
        )
    )

    if remaining_capacity <= 0:

        result = unresolved

    else:

        retained_resolved = (
            resolved
            .sort_values(
                [
                    "resolved_at",
                    "peak_observed_dpd",
                    "peak_observed_arrears_inr",
                ],
                ascending=[
                    False,
                    False,
                    False,
                ],
            )
            .head(
                remaining_capacity
            )
        )

        result = pd.concat(
            [
                unresolved,
                retained_resolved,
            ],
            ignore_index=True,
        )

    return (
        result
        .sort_values(
            [
                "case_created_at",
                "loan_account_id",
                "loan_case_sequence",
            ]
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# GENERATE COLLECTION CASES
# ============================================================


def generate_collection_cases(
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
    payment_history: pd.DataFrame,
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
) -> pd.DataFrame:
    """
    Generate Collection cases from Finance payment evidence.
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    # ========================================================
    # VALIDATE INPUTS
    # ========================================================

    _validate_inputs(
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
        dpd_threshold,
        maximum_cases,
    ) = (
        _get_collection_config(
            generation
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
    # PREPARE PAYMENTS
    # ========================================================

    payments = (
        _prepare_payment_history(
            payment_history
        )
    )

    # ========================================================
    # PREPARE LOANS
    # ========================================================

    loans = (
        loan_accounts
        .copy(
            deep=True
        )
    )

    loans[
        "disbursed_at"
    ] = pd.to_datetime(
        loans[
            "disbursed_at"
        ],
        utc=True,
    )

    loans[
        "scheduled_maturity_at"
    ] = pd.to_datetime(
        loans[
            "scheduled_maturity_at"
        ],
        utc=True,
    )

    loan_lookup = {
        str(
            row.loan_account_id
        ):
            row._asdict()

        for row in loans.itertuples(
            index=False
        )
    }

    # ========================================================
    # GENERATE CASE EPISODES
    # ========================================================

    rows: list[
        dict[str, Any]
    ] = []

    for (
        loan_account_id,
        loan_payments,
    ) in payments.groupby(
        "loan_account_id",
        sort=True,
    ):

        loan_id = str(
            loan_account_id
        )

        loan = (
            loan_lookup.get(
                loan_id
            )
        )

        if loan is None:

            raise ValueError(
                "Payments reference unknown loan "
                f"{loan_id}"
            )

        episodes = (
            _build_loan_case_episodes(
                loan=
                    loan,

                loan_payments=
                    loan_payments,

                dpd_threshold=
                    dpd_threshold,

                generation_end=
                    generation_end,
            )
        )

        rows.extend(
            episodes
        )

    if not rows:

        raise ValueError(
            "Collections generator produced no cases"
        )

    cases = pd.DataFrame(
        rows
    )

    # ========================================================
    # DATETIME NORMALIZATION
    # ========================================================

    cases[
        "case_created_at"
    ] = pd.to_datetime(
        cases[
            "case_created_at"
        ],
        utc=True,
    )

    cases[
        "resolved_at"
    ] = pd.to_datetime(
        cases[
            "resolved_at"
        ],
        utc=True,
    )

    # ========================================================
    # RETAIN CASES RELEVANT TO MAIN 2026 WINDOW
    #
    # Keep:
    #
    #   unresolved cases
    #   cases created in 2026
    #   cases resolved in 2026
    #
    # Drop historical cases opened AND resolved before 2026.
    # ========================================================

    relevant = (
        cases[
            "resolved_at"
        ].isna()
        |
        (
            cases[
                "case_created_at"
            ]
            >=
            generation_start
        )
        |
        (
            cases[
                "resolved_at"
            ]
            >=
            generation_start
        )
    )

    cases = (
        cases.loc[
            relevant
        ]
        .copy()
    )

    if cases.empty:

        raise ValueError(
            "No Collection cases are relevant to "
            "configured generation window"
        )

    # ========================================================
    # CARRY-IN FLAG
    # ========================================================

    cases[
        "carried_into_generation_window"
    ] = (
        cases[
            "case_created_at"
        ]
        <
        generation_start
    )

    # ========================================================
    # MAXIMUM CASE LIMIT
    # ========================================================

    cases = (
        _apply_case_limit(
            cases=
                cases,

            maximum_cases=
                maximum_cases,
        )
    )

    # ========================================================
    # DETERMINISTIC ORDER
    # ========================================================

    cases = (
        cases
        .sort_values(
            [
                "case_created_at",
                "loan_account_id",
                "loan_case_sequence",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # ========================================================
    # CASE IDS
    # ========================================================

    cases[
        "collection_case_id"
    ] = [
        generate_id(
            "COLCASE_SYN",
            index,
            width=7,
        )

        for index in range(
            1,
            len(
                cases
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

    cases[
        "data_origin"
    ] = data_origin

    cases[
        "generator_version"
    ] = generator_version

    # ========================================================
    # FINAL COLUMN ORDER
    # ========================================================

    cases = cases[
        [
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
            "carried_into_generation_window",

            "case_trigger_source",
            "trigger_payment_event_id",

            "case_trigger_dpd",
            "observed_dpd_at_trigger_event",
            "dpd_at_case_creation",

            "arrears_at_trigger_event_inr",

            "priority_at_creation",

            "peak_observed_dpd",
            "peak_observed_arrears_inr",

            "case_status",

            "current_dpd",
            "current_arrears_inr",

            "resolved_at",
            "resolution_payment_event_id",
            "resolution_type",

            "data_origin",
            "generator_version",
        ]
    ]

    # ========================================================
    # VALIDATE
    # ========================================================

    validate_collection_cases(
        collection_cases=
            cases,

        finance_customers=
            finance_customers,

        loan_accounts=
            loan_accounts,

        payment_history=
            payment_history,

        generation=
            generation,
    )

    return cases


# ============================================================
# VALIDATE COLLECTION CASES
# ============================================================


def validate_collection_cases(
    collection_cases: pd.DataFrame,
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
    payment_history: pd.DataFrame,
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
) -> None:
    """
    Validate Collection cases against Finance evidence.
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    (
        dpd_threshold,
        maximum_cases,
    ) = (
        _get_collection_config(
            generation
        )
    )

    (
        _,
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
        "carried_into_generation_window",

        "case_trigger_source",
        "trigger_payment_event_id",

        "case_trigger_dpd",
        "observed_dpd_at_trigger_event",
        "dpd_at_case_creation",

        "arrears_at_trigger_event_inr",

        "priority_at_creation",

        "peak_observed_dpd",
        "peak_observed_arrears_inr",

        "case_status",

        "current_dpd",
        "current_arrears_inr",

        "resolved_at",
        "resolution_payment_event_id",
        "resolution_type",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        -
        set(
            collection_cases.columns
        )
    )

    if missing:

        raise ValueError(
            "Collection cases missing columns: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    if collection_cases.empty:

        raise ValueError(
            "Collection cases cannot be empty"
        )

    # ========================================================
    # MAXIMUM COUNT
    # ========================================================

    if (
        len(
            collection_cases
        )
        >
        maximum_cases
    ):

        raise ValueError(
            "Collection cases exceed configured "
            "maximum_cases"
        )

    # ========================================================
    # UNIQUE CASE ID
    # ========================================================

    if (
        collection_cases[
            "collection_case_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Duplicate collection_case_id values found"
        )

    # ========================================================
    # UNIQUE LOAN CASE SEQUENCE
    # ========================================================

    if (
        collection_cases[
            [
                "loan_account_id",
                "loan_case_sequence",
            ]
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Duplicate loan/case sequence found"
        )

    # ========================================================
    # FKS
    # ========================================================

    valid_customers = set(
        finance_customers[
            "finance_customer_id"
        ]
        .astype(str)
    )

    invalid_customers = (
        set(
            collection_cases[
                "finance_customer_id"
            ]
            .astype(str)
        )
        -
        valid_customers
    )

    if invalid_customers:

        raise ValueError(
            "Collection cases reference invalid customers"
        )

    valid_loans = set(
        loan_accounts[
            "loan_account_id"
        ]
        .astype(str)
    )

    invalid_loans = (
        set(
            collection_cases[
                "loan_account_id"
            ]
            .astype(str)
        )
        -
        valid_loans
    )

    if invalid_loans:

        raise ValueError(
            "Collection cases reference invalid loans"
        )

    valid_payment_events = set(
        payment_history[
            "payment_event_id"
        ]
        .astype(str)
    )

    invalid_trigger_events = (
        set(
            collection_cases[
                "trigger_payment_event_id"
            ]
            .astype(str)
        )
        -
        valid_payment_events
    )

    if invalid_trigger_events:

        raise ValueError(
            "Collection cases reference invalid trigger "
            "payment events"
        )

    # ========================================================
    # LOAN / CUSTOMER / PRODUCT CONSISTENCY
    # ========================================================

    loan_lookup = (
        loan_accounts
        .set_index(
            "loan_account_id"
        )
    )

    for case in collection_cases.itertuples(
        index=False
    ):

        loan = loan_lookup.loc[
            str(
                case.loan_account_id
            )
        ]

        if (
            str(
                loan[
                    "finance_customer_id"
                ]
            )
            !=
            str(
                case.finance_customer_id
            )
        ):

            raise ValueError(
                "Collection case loan/customer mismatch"
            )

        if (
            str(
                loan[
                    "finance_product_id"
                ]
            )
            !=
            str(
                case.finance_product_id
            )
        ):

            raise ValueError(
                "Collection case product mismatch"
            )

    # ========================================================
    # TRIGGER PAYMENT OWNERSHIP
    # ========================================================

    payment_lookup = (
        payment_history
        .set_index(
            "payment_event_id"
        )
    )

    for case in collection_cases.itertuples(
        index=False
    ):

        payment = payment_lookup.loc[
            str(
                case.trigger_payment_event_id
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
                case.loan_account_id
            )
        ):

            raise ValueError(
                "Case trigger payment belongs to "
                "different loan"
            )

    # ========================================================
    # TRIGGER SOURCE
    # ========================================================

    invalid_trigger_sources = (
        set(
            collection_cases[
                "case_trigger_source"
            ]
            .astype(str)
        )
        -
        VALID_CASE_TRIGGER_SOURCES
    )

    if invalid_trigger_sources:

        raise ValueError(
            "Invalid Collection case trigger sources: "
            +
            ", ".join(
                sorted(
                    invalid_trigger_sources
                )
            )
        )

    # ========================================================
    # CONFIGURED CASE THRESHOLD
    # ========================================================

    if (
        collection_cases[
            "case_trigger_dpd"
        ]
        .astype(int)
        !=
        dpd_threshold
    ).any():

        raise ValueError(
            "Unexpected Collection DPD threshold"
        )

    if (
        collection_cases[
            "dpd_at_case_creation"
        ]
        .astype(int)
        <
        dpd_threshold
    ).any():

        raise ValueError(
            "Collection case cannot be created below "
            "configured DPD threshold"
        )

    # ========================================================
    # PAYMENT EVENT TRIGGER VALIDATION
    # ========================================================

    payment_event_cases = (
        collection_cases[
            collection_cases[
                "case_trigger_source"
            ]
            ==
            CASE_TRIGGER_PAYMENT_EVENT
        ]
    )

    if not payment_event_cases.empty:

        if (
            payment_event_cases[
                "observed_dpd_at_trigger_event"
            ]
            .astype(int)
            <
            dpd_threshold
        ).any():

            raise ValueError(
                "PAYMENT_EVENT Collection case has "
                "trigger payment below threshold"
            )

    # ========================================================
    # AGED-TO-CUTOFF VALIDATION
    #
    # These cases are specifically allowed to have the latest
    # payment-event DPD below 15 because time itself pushed the
    # arrears into the threshold afterward.
    # ========================================================

    aged_cases = (
        collection_cases[
            collection_cases[
                "case_trigger_source"
            ]
            ==
            CASE_TRIGGER_AGED_TO_CUTOFF
        ]
    )

    if not aged_cases.empty:

        if (
            aged_cases[
                "observed_dpd_at_trigger_event"
            ]
            .astype(int)
            >=
            dpd_threshold
        ).any():

            raise ValueError(
                "AGED_TO_CUTOFF case should only be used "
                "when payment-event DPD was below threshold"
            )

        if (
            aged_cases[
                "case_status"
            ]
            !=
            CASE_STATUS_OPEN
        ).any():

            raise ValueError(
                "AGED_TO_CUTOFF cases must currently be OPEN"
            )

    # ========================================================
    # ARREARS AT CASE CREATION
    # ========================================================

    if (
        pd.to_numeric(
            collection_cases[
                "arrears_at_trigger_event_inr"
            ],
            errors="raise",
        )
        <=
        0
    ).any():

        raise ValueError(
            "Collection case creation requires "
            "positive arrears"
        )

    # ========================================================
    # STATUS
    # ========================================================

    invalid_statuses = (
        set(
            collection_cases[
                "case_status"
            ]
            .astype(str)
        )
        -
        VALID_CASE_STATUSES
    )

    if invalid_statuses:

        raise ValueError(
            "Invalid Collection case statuses: "
            +
            ", ".join(
                sorted(
                    invalid_statuses
                )
            )
        )

    # ========================================================
    # PRIORITY
    # ========================================================

    invalid_priorities = (
        set(
            collection_cases[
                "priority_at_creation"
            ]
            .astype(str)
        )
        -
        VALID_PRIORITIES
    )

    if invalid_priorities:

        raise ValueError(
            "Invalid Collection priorities"
        )

    # ========================================================
    # OPEN CASES
    # ========================================================

    open_cases = (
        collection_cases[
            collection_cases[
                "case_status"
            ]
            ==
            CASE_STATUS_OPEN
        ]
    )

    if not open_cases.empty:

        if (
            open_cases[
                "resolved_at"
            ]
            .notna()
            .any()
        ):

            raise ValueError(
                "OPEN cases cannot have resolved_at"
            )

        if (
            pd.to_numeric(
                open_cases[
                    "current_dpd"
                ],
                errors="raise",
            )
            <
            dpd_threshold
        ).any():

            raise ValueError(
                "OPEN cases must currently have "
                "DPD >= case threshold"
            )

        if (
            pd.to_numeric(
                open_cases[
                    "current_arrears_inr"
                ],
                errors="raise",
            )
            <=
            0
        ).any():

            raise ValueError(
                "OPEN cases require current arrears"
            )

    # ========================================================
    # MONITORING CASES
    # ========================================================

    monitoring_cases = (
        collection_cases[
            collection_cases[
                "case_status"
            ]
            ==
            CASE_STATUS_MONITORING
        ]
    )

    if not monitoring_cases.empty:

        if (
            monitoring_cases[
                "resolved_at"
            ]
            .notna()
            .any()
        ):

            raise ValueError(
                "MONITORING cases cannot have resolved_at"
            )

        if (
            pd.to_numeric(
                monitoring_cases[
                    "current_dpd"
                ],
                errors="raise",
            )
            >=
            dpd_threshold
        ).any():

            raise ValueError(
                "MONITORING cases must be below "
                "Collection DPD threshold"
            )

        if (
            pd.to_numeric(
                monitoring_cases[
                    "current_arrears_inr"
                ],
                errors="raise",
            )
            <=
            0
        ).any():

            raise ValueError(
                "MONITORING cases require "
                "unresolved arrears"
            )

    # ========================================================
    # RESOLVED CASES
    # ========================================================

    resolved_cases = (
        collection_cases[
            collection_cases[
                "case_status"
            ]
            ==
            CASE_STATUS_RESOLVED
        ]
    )

    if not resolved_cases.empty:

        if (
            resolved_cases[
                "resolved_at"
            ]
            .isna()
            .any()
        ):

            raise ValueError(
                "RESOLVED cases require resolved_at"
            )

        if (
            pd.to_numeric(
                resolved_cases[
                    "current_dpd"
                ],
                errors="raise",
            )
            !=
            0
        ).any():

            raise ValueError(
                "RESOLVED case current DPD must be zero"
            )

        if (
            pd.to_numeric(
                resolved_cases[
                    "current_arrears_inr"
                ],
                errors="raise",
            )
            >
            0.01
        ).any():

            raise ValueError(
                "RESOLVED cases cannot have "
                "current arrears"
            )

        if (
            resolved_cases[
                "resolution_payment_event_id"
            ]
            .isna()
            .any()
        ):

            raise ValueError(
                "RESOLVED cases require resolution "
                "payment event"
            )

        invalid_resolution_events = (
            set(
                resolved_cases[
                    "resolution_payment_event_id"
                ]
                .astype(str)
            )
            -
            valid_payment_events
        )

        if invalid_resolution_events:

            raise ValueError(
                "Resolved cases reference invalid "
                "payment events"
            )

    # ========================================================
    # TIMELINES
    # ========================================================

    case_created_at = pd.to_datetime(
        collection_cases[
            "case_created_at"
        ],
        utc=True,
    )

    if (
        case_created_at
        >=
        generation_end
    ).any():

        raise ValueError(
            "Collection case cannot be created on/after "
            "generation cutoff"
        )

    if not resolved_cases.empty:

        resolved_created = pd.to_datetime(
            resolved_cases[
                "case_created_at"
            ],
            utc=True,
        )

        resolved_at = pd.to_datetime(
            resolved_cases[
                "resolved_at"
            ],
            utc=True,
        )

        if (
            resolved_at
            <
            resolved_created
        ).any():

            raise ValueError(
                "Collection case cannot resolve before "
                "case creation"
            )

    # ========================================================
    # PEAK DPD / ARREARS
    # ========================================================

    if (
        pd.to_numeric(
            collection_cases[
                "peak_observed_dpd"
            ],
            errors="raise",
        )
        <
        pd.to_numeric(
            collection_cases[
                "dpd_at_case_creation"
            ],
            errors="raise",
        )
    ).any():

        raise ValueError(
            "Peak DPD cannot be below DPD at case creation"
        )

    if (
        pd.to_numeric(
            collection_cases[
                "peak_observed_arrears_inr"
            ],
            errors="raise",
        )
        <
        pd.to_numeric(
            collection_cases[
                "arrears_at_trigger_event_inr"
            ],
            errors="raise",
        )
        -
        0.01
    ).any():

        raise ValueError(
            "Peak arrears cannot be below trigger arrears"
        )

    # ========================================================
    # CRITICAL END-TO-END COVERAGE VALIDATION
    #
    # Every loan with unresolved arrears and current DPD >=15
    # at Aug 1 must have an OPEN Collection case.
    # ========================================================

    prepared_payments = (
        _prepare_payment_history(
            payment_history
        )
    )

    latest_states = (
        prepared_payments
        .sort_values(
            [
                "loan_account_id",
                "installment_number",
            ]
        )
        .groupby(
            "loan_account_id",
            as_index=False,
        )
        .tail(
            1
        )
    )

    currently_collectible_loans: set[
        str
    ] = set()

    for latest in latest_states.to_dict(
        orient="records"
    ):

        if (
            float(
                latest[
                    "arrears_amount_inr"
                ]
            )
            <=
            0.01
        ):

            continue

        current_dpd = (
            _current_dpd_as_of_cutoff(
                latest_payment_row=
                    latest,

                cutoff=
                    generation_end,
            )
        )

        if current_dpd >= dpd_threshold:

            currently_collectible_loans.add(
                str(
                    latest[
                        "loan_account_id"
                    ]
                )
            )

    open_case_loans = set(
        collection_cases.loc[
            collection_cases[
                "case_status"
            ]
            ==
            CASE_STATUS_OPEN,
            "loan_account_id",
        ]
        .astype(str)
    )

    missing_current_cases = (
        currently_collectible_loans
        -
        open_case_loans
    )

    if missing_current_cases:

        raise ValueError(
            "Currently collectible loans are missing "
            "OPEN Collection cases: "
            +
            ", ".join(
                sorted(
                    missing_current_cases
                )[
                    :20
                ]
            )
        )

    # ========================================================
    # NO FALSE OPEN CASES
    # ========================================================

    false_open_cases = (
        open_case_loans
        -
        currently_collectible_loans
    )

    if false_open_cases:

        raise ValueError(
            "OPEN Collection cases exist for loans that "
            "are not currently collectible: "
            +
            ", ".join(
                sorted(
                    false_open_cases
                )[
                    :20
                ]
            )
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
        collection_cases[
            "data_origin"
        ]
        .astype(str)
        !=
        expected_origin
    ).any():

        raise ValueError(
            "Unexpected Collection case data_origin"
        )

    expected_version = str(
        generation.get(
            "generator_version",
            "1.0.0",
        )
    )

    if (
        collection_cases[
            "generator_version"
        ]
        .astype(str)
        !=
        expected_version
    ).any():

        raise ValueError(
            "Unexpected Collection case "
            "generator_version"
        )

    # ========================================================
    # HIDDEN TRUTH LEAKAGE
    # ========================================================

    forbidden_columns = {
        "default_probability",

        "collection_probability",
        "cure_probability",

        "contact_probability",
        "promise_probability",

        "latent_repayment_quality",

        "risk_score",
        "risk_band",

        "recommended_action",
        "recommended_channel",

        "true_default",
        "true_cure_outcome",

        "confidence",
        "confidence_score",
    }

    leaked = (
        forbidden_columns
        &
        set(
            collection_cases.columns
        )
    )

    if leaked:

        raise ValueError(
            "Hidden Collections truth leaked into cases: "
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


def generate_collection_case_master(
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
    payment_history: pd.DataFrame,
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
) -> pd.DataFrame:
    """
    Public entry point used later by generate_all.py.
    """

    return generate_collection_cases(
        finance_customers=
            finance_customers,

        loan_accounts=
            loan_accounts,

        payment_history=
            payment_history,

        generation=
            generation,
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

    # ========================================================
    # UPSTREAM
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
    # SAMPLE
    # ========================================================

    print(
        "\n=== COLLECTION CASE SAMPLE ===\n"
    )

    print(
        collection_cases_df[
            [
                "collection_case_id",

                "loan_account_id",
                "finance_customer_id",

                "loan_case_sequence",

                "product_name",

                "case_created_at",

                "case_trigger_source",

                "observed_dpd_at_trigger_event",
                "dpd_at_case_creation",

                "arrears_at_trigger_event_inr",

                "priority_at_creation",

                "peak_observed_dpd",

                "case_status",

                "current_dpd",
                "current_arrears_inr",

                "resolved_at",
            ]
        ]
        .head(
            40
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # STATUS
    # ========================================================

    print(
        "\n=== COLLECTION CASE STATUS ===\n"
    )

    status_counts = (
        collection_cases_df[
            "case_status"
        ]
        .value_counts()
        .rename_axis(
            "case_status"
        )
        .reset_index(
            name=
                "case_count"
        )
    )

    status_counts[
        "rate"
    ] = (
        status_counts[
            "case_count"
        ]
        /
        len(
            collection_cases_df
        )
    ).round(
        4
    )

    print(
        status_counts.to_string(
            index=False
        )
    )

    # ========================================================
    # TRIGGER SOURCE
    # ========================================================

    print(
        "\n=== COLLECTION CASE TRIGGER SOURCE ===\n"
    )

    print(
        collection_cases_df[
            "case_trigger_source"
        ]
        .value_counts()
        .rename_axis(
            "trigger_source"
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
    # PRIORITY
    # ========================================================

    print(
        "\n=== COLLECTION PRIORITY ===\n"
    )

    print(
        collection_cases_df[
            "priority_at_creation"
        ]
        .value_counts()
        .rename_axis(
            "priority"
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
    # REGION
    # ========================================================

    print(
        "\n=== COLLECTION CASES BY REGION ===\n"
    )

    print(
        collection_cases_df
        .groupby(
            "region_name"
        )
        .size()
        .reset_index(
            name=
                "case_count"
        )
        .sort_values(
            "case_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # PRODUCT
    # ========================================================

    print(
        "\n=== COLLECTION CASES BY PRODUCT ===\n"
    )

    print(
        collection_cases_df
        .groupby(
            [
                "product_code",
                "product_name",
            ]
        )
        .size()
        .reset_index(
            name=
                "case_count"
        )
        .sort_values(
            "case_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # DPD SUMMARY
    # ========================================================

    print(
        "\n=== COLLECTION DPD SUMMARY ===\n"
    )

    print(
        collection_cases_df[
            [
                "observed_dpd_at_trigger_event",
                "dpd_at_case_creation",
                "peak_observed_dpd",
                "current_dpd",
            ]
        ]
        .describe()
        .round(
            2
        )
        .to_string()
    )

    # ========================================================
    # ARREARS SUMMARY
    # ========================================================

    print(
        "\n=== COLLECTION ARREARS SUMMARY ===\n"
    )

    print(
        collection_cases_df[
            [
                "arrears_at_trigger_event_inr",
                "peak_observed_arrears_inr",
                "current_arrears_inr",
            ]
        ]
        .describe()
        .round(
            2
        )
        .to_string()
    )

    # ========================================================
    # CASES PER LOAN
    # ========================================================

    cases_per_loan = (
        collection_cases_df
        .groupby(
            "loan_account_id"
        )
        .size()
    )

    print(
        "\n=== COLLECTION CASES PER LOAN ===\n"
    )

    print(
        cases_per_loan
        .value_counts()
        .sort_index()
        .rename_axis(
            "cases_per_loan"
        )
        .reset_index(
            name=
                "loan_count"
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # CARRY-IN
    # ========================================================

    print(
        "\n=== COLLECTION WINDOW CARRY-IN ===\n"
    )

    print(
        "Cases carried into 2026 window:",
        int(
            collection_cases_df[
                "carried_into_generation_window"
            ]
            .sum()
        ),
    )

    # ========================================================
    # FINAL
    # ========================================================

    print(
        "\n=== COLLECTION CASE VALIDATION ===\n"
    )

    print(
        "Rows:",
        len(
            collection_cases_df
        ),
    )

    print(
        "Unique case IDs:",
        collection_cases_df[
            "collection_case_id"
        ].nunique(),
    )

    print(
        "Loans represented:",
        collection_cases_df[
            "loan_account_id"
        ].nunique(),
    )

    print(
        "Customers represented:",
        collection_cases_df[
            "finance_customer_id"
        ].nunique(),
    )

    print(
        "Open cases:",
        int(
            (
                collection_cases_df[
                    "case_status"
                ]
                ==
                CASE_STATUS_OPEN
            )
            .sum()
        ),
    )

    print(
        "Monitoring cases:",
        int(
            (
                collection_cases_df[
                    "case_status"
                ]
                ==
                CASE_STATUS_MONITORING
            )
            .sum()
        ),
    )

    print(
        "Resolved cases:",
        int(
            (
                collection_cases_df[
                    "case_status"
                ]
                ==
                CASE_STATUS_RESOLVED
            )
            .sum()
        ),
    )

    print(
        "Payment-event triggers:",
        int(
            (
                collection_cases_df[
                    "case_trigger_source"
                ]
                ==
                CASE_TRIGGER_PAYMENT_EVENT
            )
            .sum()
        ),
    )

    print(
        "Aged-to-cutoff triggers:",
        int(
            (
                collection_cases_df[
                    "case_trigger_source"
                ]
                ==
                CASE_TRIGGER_AGED_TO_CUTOFF
            )
            .sum()
        ),
    )

    print(
        "Maximum current DPD:",
        int(
            collection_cases_df[
                "current_dpd"
            ].max()
        ),
    )

    print(
        "Duplicate case IDs:",
        int(
            collection_cases_df[
                "collection_case_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    forbidden_columns = {
        "default_probability",
        "collection_probability",
        "cure_probability",

        "risk_score",

        "recommended_action",
        "recommended_channel",

        "true_default",
        "true_cure_outcome",
    }

    leaked_columns = sorted(
        forbidden_columns
        &
        set(
            collection_cases_df.columns
        )
    )

    print(
        "Hidden truth leakage:",
        leaked_columns,
    )

    print(
        "\nGenerated "
        f"{len(collection_cases_df)} "
        "Collection cases successfully."
    )