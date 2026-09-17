"""
Synthetic Finance Payment History Generator
for Mahindra AI Nexus.

Generates installment-level operational repayment evidence:

    Finance Customer
          +
    Loan Account
          ↓
    Payment History

Later:

    payments.py
        ↓
    cross_sell.py
        ↓
    collections/cases.py
        ↓
    collections/interactions.py


============================================================
IMPORTANT ARCHITECTURAL RULE
============================================================

This file generates OBSERVABLE repayment history.

It MAY contain runtime operational facts such as:

    payment_status
    payment_delay_days
    days_past_due_after_event
    arrears_amount_inr
    outstanding_principal_inr

It MUST NOT expose hidden generator truth such as:

    on_time_probability
    late_probability
    missed_probability
    latent_repayment_quality
    default_probability
    true_default
    risk_score


============================================================
PAYMENT BEHAVIOUR
============================================================

Base probabilities come from:

    distributions.finance

        payment_on_time_probability: 0.82
        late_payment_probability:    0.13
        missed_payment_probability:  0.05

Those are engineering assumptions for synthetic generation.

The probabilities are adjusted slightly using OBSERVABLE
customer/account evidence:

    income stability
    debt-service ratio
    unresolved previous delinquency

The adjusted probabilities are NEVER written to runtime data.


============================================================
PAYMENT HISTORY WINDOW
============================================================

generation.yaml defines:

    payment_history_months:
        min: 6
        max: 24

For old loans we internally simulate the complete repayment
sequence required to maintain correct account state, but only
retain the latest configured 6-24 months.

This allows:

    realistic running arrears
    realistic outstanding principal
    consistent DPD

without exposing unnecessary old history.


============================================================
OUTPUT
============================================================

This module DOES NOT write CSV files.

Later:

    data/scripts/generate_all.py

will write:

    data/synthetic/finance/payments.csv
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Mapping

from dateutil.relativedelta import relativedelta

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


PAYMENT_STATUS_ON_TIME = "ON_TIME"
PAYMENT_STATUS_LATE = "LATE"
PAYMENT_STATUS_MISSED = "MISSED"

VALID_PAYMENT_STATUSES: set[str] = {
    PAYMENT_STATUS_ON_TIME,
    PAYMENT_STATUS_LATE,
    PAYMENT_STATUS_MISSED,
}

MAX_LATE_DAYS = 30


STABILITY_PROBABILITY_ADJUSTMENT: dict[
    str,
    tuple[
        float,
        float,
        float,
    ],
] = {
    "LOW": (
        -0.020,
        +0.012,
        +0.008,
    ),
    "MEDIUM": (
        -0.005,
        +0.003,
        +0.002,
    ),
    "MEDIUM_HIGH": (
        0.000,
        0.000,
        0.000,
    ),
    "HIGH": (
        +0.015,
        -0.010,
        -0.005,
    ),
}


ARREARS_CATCHUP_PROBABILITY: dict[
    str,
    float,
] = {
    "LOW": 0.20,
    "MEDIUM": 0.30,
    "MEDIUM_HIGH": 0.40,
    "HIGH": 0.50,
}


FINANCE_CUSTOMER_REQUIRED_COLUMNS: set[str] = {
    "finance_customer_id",
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
    "debt_service_ratio_at_origination",
    "data_origin",
    "generator_version",
}


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


def _as_probability(
    value: Any,
    name: str,
) -> float:
    """
    Parse probability configuration.
    """

    try:
        parsed = float(
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
        parsed
        <=
        1.0
    ):
        raise ValueError(
            f"{name} must be between 0 and 1"
        )

    return parsed


def _validate_inputs(
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
) -> None:
    """
    Validate upstream Finance datasets.
    """

    if finance_customers.empty:
        raise ValueError(
            "finance_customers cannot be empty"
        )

    if loan_accounts.empty:
        raise ValueError(
            "loan_accounts cannot be empty"
        )

    customer_missing = (
        FINANCE_CUSTOMER_REQUIRED_COLUMNS
        -
        set(
            finance_customers.columns
        )
    )

    if customer_missing:
        raise ValueError(
            "finance_customers missing columns: "
            +
            ", ".join(
                sorted(
                    customer_missing
                )
            )
        )

    loan_missing = (
        LOAN_REQUIRED_COLUMNS
        -
        set(
            loan_accounts.columns
        )
    )

    if loan_missing:
        raise ValueError(
            "loan_accounts missing columns: "
            +
            ", ".join(
                sorted(
                    loan_missing
                )
            )
        )

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

    valid_customer_ids = set(
        finance_customers[
            "finance_customer_id"
        ]
        .astype(str)
    )

    loan_customer_ids = set(
        loan_accounts[
            "finance_customer_id"
        ]
        .astype(str)
    )

    invalid = (
        loan_customer_ids
        -
        valid_customer_ids
    )

    if invalid:
        raise ValueError(
            "Loan accounts reference invalid "
            "Finance customers"
        )


def _generation_end_timestamp(
    generation: Mapping[
        str,
        Any,
    ],
) -> pd.Timestamp:
    """
    Return configured end timestamp.
    """

    try:
        end_date = generation[
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
            "Missing generation.time.end_date"
        ) from exc

    timestamp = pd.Timestamp(
        end_date
    )

    if timestamp.tzinfo is None:
        timestamp = (
            timestamp
            .tz_localize(
                timezone
            )
        )

    else:
        timestamp = (
            timestamp
            .tz_convert(
                timezone
            )
        )

    return timestamp


def _base_payment_probabilities(
    distributions: Mapping[
        str,
        Any,
    ],
) -> tuple[
    float,
    float,
    float,
]:
    """
    Load configured base payment probabilities.
    """

    try:
        finance_config = (
            distributions[
                "finance"
            ]
        )

        on_time = (
            _as_probability(
                finance_config[
                    "payment_on_time_probability"
                ],
                "finance."
                "payment_on_time_probability",
            )
        )

        late = (
            _as_probability(
                finance_config[
                    "late_payment_probability"
                ],
                "finance."
                "late_payment_probability",
            )
        )

        missed = (
            _as_probability(
                finance_config[
                    "missed_payment_probability"
                ],
                "finance."
                "missed_payment_probability",
            )
        )

    except KeyError as exc:
        raise KeyError(
            "Missing Finance payment probabilities"
        ) from exc

    total = (
        on_time
        +
        late
        +
        missed
    )

    if abs(
        total
        -
        1.0
    ) > 1e-8:
        raise ValueError(
            "Finance payment probabilities must sum to 1"
        )

    return (
        on_time,
        late,
        missed,
    )


def _derive_payment_probabilities(
    base_probabilities: tuple[
        float,
        float,
        float,
    ],
    income_stability: str,
    origination_dsr: float,
    previous_status: str | None,
    previous_dpd: int,
) -> np.ndarray:
    """
    Adjust configured base payment probabilities using only
    observable evidence.

    The adjusted probabilities remain hidden inside the
    generator.
    """

    if (
        income_stability
        not in
        STABILITY_PROBABILITY_ADJUSTMENT
    ):
        raise ValueError(
            "Unknown income stability: "
            f"{income_stability}"
        )

    probabilities = np.asarray(
        base_probabilities,
        dtype=float,
    )

    probabilities += np.asarray(
        STABILITY_PROBABILITY_ADJUSTMENT[
            income_stability
        ],
        dtype=float,
    )

    dsr_risk = float(
        np.clip(
            (
                float(
                    origination_dsr
                )
                -
                0.45
            )
            /
            0.30,
            -1.0,
            1.0,
        )
    )

    probabilities[
        0
    ] -= (
        0.025
        *
        dsr_risk
    )

    probabilities[
        1
    ] += (
        0.0175
        *
        dsr_risk
    )

    probabilities[
        2
    ] += (
        0.0075
        *
        dsr_risk
    )

    if previous_dpd > 0:

        probabilities[
            0
        ] -= 0.020

        probabilities[
            1
        ] += 0.012

        probabilities[
            2
        ] += 0.008

    if (
        previous_status
        ==
        PAYMENT_STATUS_MISSED
    ):

        probabilities[
            0
        ] -= 0.020

        probabilities[
            1
        ] += 0.010

        probabilities[
            2
        ] += 0.010

    probabilities = np.clip(
        probabilities,
        0.001,
        None,
    )

    probabilities = (
        probabilities
        /
        probabilities.sum()
    )

    return probabilities


def _sample_payment_status(
    rng: np.random.Generator,
    probabilities: np.ndarray,
) -> str:
    """
    Sample one payment status.
    """

    return str(
        rng.choice(
            [
                PAYMENT_STATUS_ON_TIME,
                PAYMENT_STATUS_LATE,
                PAYMENT_STATUS_MISSED,
            ],
            p=
                probabilities,
        )
    )


def _sample_late_days(
    rng: np.random.Generator,
) -> int:
    """
    Generate 1-30 day payment delay.

    Most late payments are relatively short.
    """

    raw = float(
        rng.lognormal(
            mean=1.7,
            sigma=0.70,
        )
    )

    return int(
        np.clip(
            np.ceil(
                raw
            ),
            1,
            MAX_LATE_DAYS,
        )
    )


def _generate_actual_payment_time(
    rng: np.random.Generator,
    payment_status: str,
    due_at: pd.Timestamp,
    generation_end: pd.Timestamp,
) -> tuple[
    pd.Timestamp | None,
    int | None,
    str,
]:
    """
    Generate actual payment timestamp.

    A payment sampled as LATE but occurring after the
    observation cutoff is treated as MISSED / still unpaid
    in the observable dataset.
    """

    if (
        payment_status
        ==
        PAYMENT_STATUS_ON_TIME
    ):

        early_days = int(
            rng.integers(
                0,
                4,
            )
        )

        early_hours = int(
            rng.integers(
                0,
                12,
            )
        )

        payment_at = (
            due_at
            -
            timedelta(
                days=
                    early_days,
                hours=
                    early_hours,
            )
        )

        return (
            payment_at,
            0,
            PAYMENT_STATUS_ON_TIME,
        )

    if (
        payment_status
        ==
        PAYMENT_STATUS_LATE
    ):

        late_days = (
            _sample_late_days(
                rng
            )
        )

        late_hours = int(
            rng.integers(
                0,
                24,
            )
        )

        payment_at = (
            due_at
            +
            timedelta(
                days=
                    late_days,
                hours=
                    late_hours,
            )
        )

        if (
            payment_at
            >=
            generation_end
        ):
            return (
                None,
                None,
                PAYMENT_STATUS_MISSED,
            )

        return (
            payment_at,
            late_days,
            PAYMENT_STATUS_LATE,
        )

    if (
        payment_status
        ==
        PAYMENT_STATUS_MISSED
    ):
        return (
            None,
            None,
            PAYMENT_STATUS_MISSED,
        )

    raise ValueError(
        "Unknown payment status: "
        f"{payment_status}"
    )


def _arrears_amount(
    arrears_buckets: list[
        dict[str, Any]
    ],
) -> float:
    """
    Total unresolved arrears.
    """

    return float(
        sum(
            float(
                bucket[
                    "principal"
                ]
            )
            +
            float(
                bucket[
                    "interest"
                ]
            )

            for bucket
            in arrears_buckets
        )
    )


def _arrears_principal(
    arrears_buckets: list[
        dict[str, Any]
    ],
) -> float:
    """
    Outstanding principal component of unresolved arrears.
    """

    return float(
        sum(
            float(
                bucket[
                    "principal"
                ]
            )

            for bucket
            in arrears_buckets
        )
    )


def _recover_arrears(
    arrears_buckets: list[
        dict[str, Any]
    ],
    amount: float,
) -> tuple[
    float,
    float,
]:
    """
    Apply recovery payment to oldest arrears first.

    Returns:

        amount actually recovered
        principal component recovered
    """

    remaining = float(
        max(
            amount,
            0.0,
        )
    )

    total_recovered = 0.0

    principal_recovered = 0.0

    bucket_index = 0

    while (
        remaining
        >
        0.005
        and
        bucket_index
        <
        len(
            arrears_buckets
        )
    ):

        bucket = (
            arrears_buckets[
                bucket_index
            ]
        )

        interest_due = float(
            bucket[
                "interest"
            ]
        )

        interest_payment = min(
            remaining,
            interest_due,
        )

        bucket[
            "interest"
        ] = max(
            interest_due
            -
            interest_payment,
            0.0,
        )

        remaining -= (
            interest_payment
        )

        total_recovered += (
            interest_payment
        )

        principal_due = float(
            bucket[
                "principal"
            ]
        )

        principal_payment = min(
            remaining,
            principal_due,
        )

        bucket[
            "principal"
        ] = max(
            principal_due
            -
            principal_payment,
            0.0,
        )

        remaining -= (
            principal_payment
        )

        total_recovered += (
            principal_payment
        )

        principal_recovered += (
            principal_payment
        )

        if (
            float(
                bucket[
                    "principal"
                ]
            )
            <=
            0.005
            and
            float(
                bucket[
                    "interest"
                ]
            )
            <=
            0.005
        ):
            arrears_buckets.pop(
                bucket_index
            )

        else:
            bucket_index += 1

    return (
        total_recovered,
        principal_recovered,
    )


def _days_past_due(
    arrears_buckets: list[
        dict[str, Any]
    ],
    reference_at: pd.Timestamp,
) -> int:
    """
    Calculate DPD from oldest unresolved missed installment.
    """

    if not arrears_buckets:
        return 0

    oldest_due = min(
        pd.Timestamp(
            bucket[
                "due_at"
            ]
        )
        for bucket
        in arrears_buckets
    )

    elapsed = (
        reference_at
        -
        oldest_due
    ).total_seconds()

    if elapsed <= 0:
        return 1

    days = int(
        np.ceil(
            elapsed
            /
            86400.0
        )
    )

    return max(
        days,
        1,
    )


def _simulate_loan_history(
    rng: np.random.Generator,
    loan: Mapping[
        str,
        Any,
    ],
    customer: Mapping[
        str,
        Any,
    ],
    generation_end: pd.Timestamp,
    history_months: int,
    base_probabilities: tuple[
        float,
        float,
        float,
    ],
) -> list[
    dict[str, Any]
]:
    """
    Simulate complete required loan history and retain only the
    configured latest history window.
    """

    principal = float(
        loan[
            "principal_inr"
        ]
    )

    annual_rate = float(
        loan[
            "interest_rate_pct"
        ]
    )

    monthly_rate = (
        annual_rate
        /
        12.0
        /
        100.0
    )

    contractual_emi = float(
        loan[
            "emi_amount_inr"
        ]
    )

    tenure_months = int(
        loan[
            "tenure_months"
        ]
    )

    disbursed_at = pd.to_datetime(
        loan[
            "disbursed_at"
        ],
        utc=True,
    )

    income_stability = str(
        customer[
            "income_stability"
        ]
    )

    origination_dsr = float(
        loan[
            "debt_service_ratio_at_origination"
        ]
    )

    if (
        income_stability
        not in
        ARREARS_CATCHUP_PROBABILITY
    ):
        raise ValueError(
            "Unknown customer income stability: "
            f"{income_stability}"
        )

    contractual_balance = (
        principal
    )

    actual_outstanding_principal = (
        principal
    )

    arrears_buckets: list[
        dict[str, Any]
    ] = []

    previous_status: str | None = None

    previous_dpd = 0

    all_events: list[
        dict[str, Any]
    ] = []

    for installment_number in range(
        1,
        tenure_months
        +
        1,
    ):

        # Calendar-month arithmetic is intentionally used here.
        #
        # Converting to Python datetime avoids the NumPy
        # generic-timedelta warning raised by DateOffset with
        # nanosecond-resolution timestamps.
        #
        # Python datetime has microsecond precision, so the
        # Timestamp.nanosecond remainder is restored below.

        due_at = pd.Timestamp(
            disbursed_at.to_pydatetime(
                warn=False
            )
            +
            relativedelta(
                months=
                    installment_number
            )
        )

        if disbursed_at.nanosecond:

            due_at = (
                due_at
                +
                pd.to_timedelta(
                    disbursed_at.nanosecond,
                    unit="ns",
                )
            )

        if (
            due_at
            >=
            generation_end
        ):
            break

        if contractual_balance <= 0.005:
            break

        scheduled_interest = (
            contractual_balance
            *
            monthly_rate
        )

        scheduled_principal = max(
            contractual_emi
            -
            scheduled_interest,
            0.0,
        )

        scheduled_principal = min(
            scheduled_principal,
            contractual_balance,
        )

        if (
            installment_number
            ==
            tenure_months
        ):
            scheduled_principal = (
                contractual_balance
            )

        scheduled_payment_amount = (
            scheduled_principal
            +
            scheduled_interest
        )

        contractual_balance_after = max(
            contractual_balance
            -
            scheduled_principal,
            0.0,
        )

        probabilities = (
            _derive_payment_probabilities(
                base_probabilities=
                    base_probabilities,
                income_stability=
                    income_stability,
                origination_dsr=
                    origination_dsr,
                previous_status=
                    previous_status,
                previous_dpd=
                    previous_dpd,
            )
        )

        sampled_status = (
            _sample_payment_status(
                rng=
                    rng,
                probabilities=
                    probabilities,
            )
        )

        (
            actual_payment_at,
            payment_delay_days,
            payment_status,
        ) = (
            _generate_actual_payment_time(
                rng=
                    rng,
                payment_status=
                    sampled_status,
                due_at=
                    due_at,
                generation_end=
                    generation_end,
            )
        )

        actual_current_payment = 0.0

        current_principal_paid = 0.0

        if (
            payment_status
            in
            {
                PAYMENT_STATUS_ON_TIME,
                PAYMENT_STATUS_LATE,
            }
        ):

            actual_current_payment = (
                scheduled_payment_amount
            )

            current_principal_paid = (
                scheduled_principal
            )

            actual_outstanding_principal = max(
                actual_outstanding_principal
                -
                current_principal_paid,
                0.0,
            )

        else:

            arrears_buckets.append(
                {
                    "due_at":
                        due_at,
                    "principal":
                        float(
                            scheduled_principal
                        ),
                    "interest":
                        float(
                            scheduled_interest
                        ),
                }
            )

        arrears_recovery_amount = 0.0

        recovered_principal = 0.0

        if (
            payment_status
            ==
            PAYMENT_STATUS_ON_TIME
            and
            arrears_buckets
        ):

            catchup_probability = (
                ARREARS_CATCHUP_PROBABILITY[
                    income_stability
                ]
            )

            if (
                float(
                    rng.random()
                )
                <
                catchup_probability
            ):

                arrears_before = (
                    _arrears_amount(
                        arrears_buckets
                    )
                )

                recovery_cap = min(
                    arrears_before,
                    contractual_emi
                    *
                    float(
                        rng.uniform(
                            0.50,
                            1.25,
                        )
                    ),
                )

                (
                    arrears_recovery_amount,
                    recovered_principal,
                ) = (
                    _recover_arrears(
                        arrears_buckets=
                            arrears_buckets,
                        amount=
                            recovery_cap,
                    )
                )

                actual_outstanding_principal = max(
                    actual_outstanding_principal
                    -
                    recovered_principal,
                    0.0,
                )

        actual_outstanding_principal = max(
            actual_outstanding_principal,
            contractual_balance_after,
        )

        actual_payment_amount = (
            actual_current_payment
            +
            arrears_recovery_amount
        )

        arrears_amount_after = (
            _arrears_amount(
                arrears_buckets
            )
        )

        if (
            payment_status
            ==
            PAYMENT_STATUS_MISSED
        ):

            reference_at = (
                due_at
                +
                timedelta(
                    days=1
                )
            )

        else:

            reference_at = max(
                due_at,
                (
                    actual_payment_at
                    if actual_payment_at
                    is not None
                    else due_at
                ),
            )

        dpd_after_event = (
            _days_past_due(
                arrears_buckets=
                    arrears_buckets,
                reference_at=
                    reference_at,
            )
        )

        all_events.append(
            {
                "payment_event_id":
                    None,

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

                "installment_number":
                    installment_number,

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

                "payment_due_at":
                    due_at,

                "scheduled_payment_amount_inr":
                    round(
                        scheduled_payment_amount,
                        2,
                    ),

                "scheduled_interest_inr":
                    round(
                        scheduled_interest,
                        2,
                    ),

                "scheduled_principal_inr":
                    round(
                        scheduled_principal,
                        2,
                    ),

                "payment_status":
                    payment_status,

                "actual_payment_at":
                    actual_payment_at,

                "actual_payment_amount_inr":
                    round(
                        actual_payment_amount,
                        2,
                    ),

                "arrears_recovery_amount_inr":
                    round(
                        arrears_recovery_amount,
                        2,
                    ),

                "payment_delay_days":
                    payment_delay_days,

                "days_past_due_after_event":
                    int(
                        dpd_after_event
                    ),

                "arrears_amount_inr":
                    round(
                        arrears_amount_after,
                        2,
                    ),

                "contractual_outstanding_principal_inr":
                    round(
                        contractual_balance_after,
                        2,
                    ),

                "outstanding_principal_inr":
                    round(
                        actual_outstanding_principal,
                        2,
                    ),

                "data_origin":
                    None,

                "generator_version":
                    None,
            }
        )

        contractual_balance = (
            contractual_balance_after
        )

        previous_status = (
            payment_status
        )

        previous_dpd = (
            dpd_after_event
        )

    if not all_events:

        raise ValueError(
            "Loan produced no observable payment history: "
            f"{loan['loan_account_id']}"
        )

    retained_count = min(
        history_months,
        len(
            all_events
        ),
    )

    return all_events[
        -retained_count:
    ]


def generate_payment_history(
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
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
    Generate installment-level Finance payment history.
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    if distributions is None:
        distributions = (
            load_distribution_config()
        )

    _validate_inputs(
        finance_customers=
            finance_customers,
        loan_accounts=
            loan_accounts,
    )

    try:

        history_config = (
            generation[
                "finance"
            ][
                "payment_history_months"
            ]
        )

        minimum_history_months = (
            _as_positive_int(
                history_config[
                    "min"
                ],
                "generation.finance."
                "payment_history_months.min",
            )
        )

        maximum_history_months = (
            _as_positive_int(
                history_config[
                    "max"
                ],
                "generation.finance."
                "payment_history_months.max",
            )
        )

    except KeyError as exc:

        raise KeyError(
            "Missing generation.finance."
            "payment_history_months"
        ) from exc

    if (
        maximum_history_months
        <
        minimum_history_months
    ):
        raise ValueError(
            "payment_history_months.max "
            "must be >= min"
        )

    base_probabilities = (
        _base_payment_probabilities(
            distributions
        )
    )

    generation_end = (
        _generation_end_timestamp(
            generation
        )
    )

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
            "finance.payments",
        )
    )

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

    rows: list[
        dict[str, Any]
    ] = []

    ordered_loans = (
        loan_accounts
        .sort_values(
            "loan_account_id"
        )
    )

    for loan in ordered_loans.to_dict(
        orient="records"
    ):

        customer_id = str(
            loan[
                "finance_customer_id"
            ]
        )

        customer = (
            customer_lookup[
                customer_id
            ]
        )

        history_months = int(
            rng.integers(
                minimum_history_months,
                maximum_history_months
                +
                1,
            )
        )

        loan_events = (
            _simulate_loan_history(
                rng=
                    rng,
                loan=
                    loan,
                customer=
                    customer,
                generation_end=
                    generation_end,
                history_months=
                    history_months,
                base_probabilities=
                    base_probabilities,
            )
        )

        rows.extend(
            loan_events
        )

    payments = (
        pd.DataFrame(
            rows
        )
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

    payments[
        "payment_event_id"
    ] = [
        generate_id(
            "FINPAY_SYN",
            index,
            width=8,
        )

        for index in range(
            1,
            len(
                payments
            )
            +
            1,
        )
    ]

    payments[
        "data_origin"
    ] = data_origin

    payments[
        "generator_version"
    ] = generator_version

    payments = payments[
        [
            "payment_event_id",
            "loan_account_id",
            "finance_customer_id",
            "installment_number",
            "region_id",
            "region_name",
            "city_id",
            "city_name",
            "finance_product_id",
            "product_code",
            "product_name",
            "product_category",
            "payment_due_at",
            "scheduled_payment_amount_inr",
            "scheduled_interest_inr",
            "scheduled_principal_inr",
            "payment_status",
            "actual_payment_at",
            "actual_payment_amount_inr",
            "arrears_recovery_amount_inr",
            "payment_delay_days",
            "days_past_due_after_event",
            "arrears_amount_inr",
            "contractual_outstanding_principal_inr",
            "outstanding_principal_inr",
            "data_origin",
            "generator_version",
        ]
    ]

    validate_payment_history(
        payments=
            payments,
        finance_customers=
            finance_customers,
        loan_accounts=
            loan_accounts,
        generation=
            generation,
        minimum_history_months=
            minimum_history_months,
        maximum_history_months=
            maximum_history_months,
    )

    return payments


def validate_payment_history(
    payments: pd.DataFrame,
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
    minimum_history_months: int | None = None,
    maximum_history_months: int | None = None,
) -> None:
    """
    Validate payment history.
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    if minimum_history_months is None:

        minimum_history_months = int(
            generation[
                "finance"
            ][
                "payment_history_months"
            ][
                "min"
            ]
        )

    if maximum_history_months is None:

        maximum_history_months = int(
            generation[
                "finance"
            ][
                "payment_history_months"
            ][
                "max"
            ]
        )

    required_columns = {
        "payment_event_id",
        "loan_account_id",
        "finance_customer_id",
        "installment_number",
        "region_id",
        "region_name",
        "city_id",
        "city_name",
        "finance_product_id",
        "product_code",
        "product_name",
        "product_category",
        "payment_due_at",
        "scheduled_payment_amount_inr",
        "scheduled_interest_inr",
        "scheduled_principal_inr",
        "payment_status",
        "actual_payment_at",
        "actual_payment_amount_inr",
        "arrears_recovery_amount_inr",
        "payment_delay_days",
        "days_past_due_after_event",
        "arrears_amount_inr",
        "contractual_outstanding_principal_inr",
        "outstanding_principal_inr",
        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        -
        set(
            payments.columns
        )
    )

    if missing:

        raise ValueError(
            "Payment history missing columns: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    if payments.empty:

        raise ValueError(
            "Payment history cannot be empty"
        )

    if (
        payments[
            "payment_event_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Duplicate payment_event_id values found"
        )

    valid_loans = set(
        loan_accounts[
            "loan_account_id"
        ]
        .astype(str)
    )

    payment_loans = set(
        payments[
            "loan_account_id"
        ]
        .astype(str)
    )

    invalid_loans = (
        payment_loans
        -
        valid_loans
    )

    if invalid_loans:

        raise ValueError(
            "Payments reference invalid loans"
        )

    valid_customers = set(
        finance_customers[
            "finance_customer_id"
        ]
        .astype(str)
    )

    payment_customers = set(
        payments[
            "finance_customer_id"
        ]
        .astype(str)
    )

    invalid_customers = (
        payment_customers
        -
        valid_customers
    )

    if invalid_customers:

        raise ValueError(
            "Payments reference invalid customers"
        )

    missing_loans = (
        valid_loans
        -
        payment_loans
    )

    if missing_loans:

        raise ValueError(
            "Some loans have no retained payment history"
        )

    history_counts = (
        payments
        .groupby(
            "loan_account_id"
        )
        .size()
    )

    if (
        history_counts
        <
        minimum_history_months
    ).any():

        raise ValueError(
            "One or more loans have fewer than configured "
            "minimum payment-history months"
        )

    if (
        history_counts
        >
        maximum_history_months
    ).any():

        raise ValueError(
            "One or more loans exceed configured maximum "
            "payment-history months"
        )

    invalid_status = (
        set(
            payments[
                "payment_status"
            ]
            .astype(str)
        )
        -
        VALID_PAYMENT_STATUSES
    )

    if invalid_status:

        raise ValueError(
            "Invalid payment statuses: "
            +
            ", ".join(
                sorted(
                    invalid_status
                )
            )
        )

    observed_status = set(
        payments[
            "payment_status"
        ]
        .astype(str)
    )

    if (
        observed_status
        !=
        VALID_PAYMENT_STATUSES
    ):

        raise ValueError(
            "Expected ON_TIME, LATE and MISSED payment "
            "states to all be present"
        )

    due_at = pd.to_datetime(
        payments[
            "payment_due_at"
        ],
        utc=True,
    )

    generation_end = (
        _generation_end_timestamp(
            generation
        )
    )

    if (
        due_at
        >=
        generation_end
    ).any():

        raise ValueError(
            "Payment due dates cannot be on/after "
            "generation end"
        )

    loan_lookup = (
        loan_accounts
        .set_index(
            "loan_account_id"
        )
    )

    for payment in payments.itertuples(
        index=False
    ):

        loan = loan_lookup.loc[
            str(
                payment.loan_account_id
            )
        ]

        if (
            pd.to_datetime(
                payment.payment_due_at,
                utc=True,
            )
            <=
            pd.to_datetime(
                loan[
                    "disbursed_at"
                ],
                utc=True,
            )
        ):

            raise ValueError(
                "Payment due date must be after disbursement"
            )

        if (
            int(
                payment.installment_number
            )
            >
            int(
                loan[
                    "tenure_months"
                ]
            )
        ):

            raise ValueError(
                "Installment number exceeds loan tenure"
            )

    scheduled_amount = pd.to_numeric(
        payments[
            "scheduled_payment_amount_inr"
        ],
        errors="raise",
    )

    scheduled_interest = pd.to_numeric(
        payments[
            "scheduled_interest_inr"
        ],
        errors="raise",
    )

    scheduled_principal = pd.to_numeric(
        payments[
            "scheduled_principal_inr"
        ],
        errors="raise",
    )

    if (
        scheduled_amount
        <=
        0
    ).any():

        raise ValueError(
            "Scheduled payment amount must be > 0"
        )

    if (
        scheduled_interest
        <
        0
    ).any():

        raise ValueError(
            "Scheduled interest cannot be negative"
        )

    if (
        scheduled_principal
        <
        0
    ).any():

        raise ValueError(
            "Scheduled principal cannot be negative"
        )

    scheduled_difference = (
        scheduled_amount
        -
        (
            scheduled_interest
            +
            scheduled_principal
        )
    ).abs()

    if (
        scheduled_difference
        >
        0.02
    ).any():

        raise ValueError(
            "Scheduled amount is inconsistent with "
            "principal + interest"
        )

    on_time = (
        payments[
            "payment_status"
        ]
        ==
        PAYMENT_STATUS_ON_TIME
    )

    if (
        payments.loc[
            on_time,
            "actual_payment_at",
        ]
        .isna()
        .any()
    ):

        raise ValueError(
            "ON_TIME payments require actual_payment_at"
        )

    if (
        pd.to_numeric(
            payments.loc[
                on_time,
                "payment_delay_days",
            ],
            errors="raise",
        )
        !=
        0
    ).any():

        raise ValueError(
            "ON_TIME payments must have zero delay"
        )

    late = (
        payments[
            "payment_status"
        ]
        ==
        PAYMENT_STATUS_LATE
    )

    if (
        payments.loc[
            late,
            "actual_payment_at",
        ]
        .isna()
        .any()
    ):

        raise ValueError(
            "LATE payments require actual_payment_at"
        )

    late_delay = pd.to_numeric(
        payments.loc[
            late,
            "payment_delay_days",
        ],
        errors="raise",
    )

    if (
        late_delay
        <
        1
    ).any():

        raise ValueError(
            "LATE payments must have delay >= 1"
        )

    if (
        late_delay
        >
        MAX_LATE_DAYS
    ).any():

        raise ValueError(
            "LATE payments exceed maximum synthetic delay"
        )

    late_payment_time = pd.to_datetime(
        payments.loc[
            late,
            "actual_payment_at",
        ],
        utc=True,
    )

    late_due_time = pd.to_datetime(
        payments.loc[
            late,
            "payment_due_at",
        ],
        utc=True,
    )

    if (
        late_payment_time
        <=
        late_due_time
    ).any():

        raise ValueError(
            "LATE actual payment must occur after due date"
        )

    missed = (
        payments[
            "payment_status"
        ]
        ==
        PAYMENT_STATUS_MISSED
    )

    if (
        payments.loc[
            missed,
            "actual_payment_at",
        ]
        .notna()
        .any()
    ):

        raise ValueError(
            "MISSED payments cannot have actual_payment_at"
        )

    missed_amount = pd.to_numeric(
        payments.loc[
            missed,
            "actual_payment_amount_inr",
        ],
        errors="raise",
    )

    if (
        missed_amount
        !=
        0
    ).any():

        raise ValueError(
            "MISSED payments must have zero actual amount"
        )

    if (
        payments.loc[
            missed,
            "payment_delay_days",
        ]
        .notna()
        .any()
    ):

        raise ValueError(
            "MISSED payment_delay_days must be NULL"
        )

    paid = (
        on_time
        |
        late
    )

    actual_amount = pd.to_numeric(
        payments.loc[
            paid,
            "actual_payment_amount_inr",
        ],
        errors="raise",
    )

    paid_scheduled = pd.to_numeric(
        payments.loc[
            paid,
            "scheduled_payment_amount_inr",
        ],
        errors="raise",
    )

    if (
        actual_amount
        +
        0.02
        <
        paid_scheduled
    ).any():

        raise ValueError(
            "Paid installment amount cannot be below "
            "scheduled installment in current model"
        )

    dpd = pd.to_numeric(
        payments[
            "days_past_due_after_event"
        ],
        errors="raise",
    )

    if (
        dpd
        <
        0
    ).any():

        raise ValueError(
            "DPD cannot be negative"
        )

    arrears = pd.to_numeric(
        payments[
            "arrears_amount_inr"
        ],
        errors="raise",
    )

    if (
        arrears
        <
        -0.01
    ).any():

        raise ValueError(
            "Arrears amount cannot be negative"
        )

    if (
        (
            arrears
            <=
            0.01
        )
        &
        (
            dpd
            !=
            0
        )
    ).any():

        raise ValueError(
            "DPD must be zero when no arrears remain"
        )

    if (
        (
            arrears
            >
            0.01
        )
        &
        (
            dpd
            <=
            0
        )
    ).any():

        raise ValueError(
            "Positive arrears require positive DPD"
        )

    contractual_outstanding = pd.to_numeric(
        payments[
            "contractual_outstanding_principal_inr"
        ],
        errors="raise",
    )

    actual_outstanding = pd.to_numeric(
        payments[
            "outstanding_principal_inr"
        ],
        errors="raise",
    )

    if (
        contractual_outstanding
        <
        -0.01
    ).any():

        raise ValueError(
            "Contractual outstanding principal "
            "cannot be negative"
        )

    if (
        actual_outstanding
        <
        -0.01
    ).any():

        raise ValueError(
            "Actual outstanding principal "
            "cannot be negative"
        )

    if (
        actual_outstanding
        +
        0.02
        <
        contractual_outstanding
    ).any():

        raise ValueError(
            "Actual outstanding principal cannot be below "
            "contractual balance"
        )

    for (
        loan_account_id,
        group,
    ) in payments.groupby(
        "loan_account_id"
    ):

        installment_numbers = (
            group
            .sort_values(
                "installment_number"
            )[
                "installment_number"
            ]
            .astype(int)
            .tolist()
        )

        if (
            installment_numbers
            !=
            list(
                range(
                    installment_numbers[
                        0
                    ],
                    installment_numbers[
                        -1
                    ]
                    +
                    1,
                )
            )
        ):

            raise ValueError(
                "Retained payment installment sequence "
                "contains gaps for "
                f"{loan_account_id}"
            )

    status_rates = (
        payments[
            "payment_status"
        ]
        .value_counts(
            normalize=True
        )
    )

    on_time_rate = float(
        status_rates.get(
            PAYMENT_STATUS_ON_TIME,
            0.0,
        )
    )

    late_rate = float(
        status_rates.get(
            PAYMENT_STATUS_LATE,
            0.0,
        )
    )

    missed_rate = float(
        status_rates.get(
            PAYMENT_STATUS_MISSED,
            0.0,
        )
    )

    if not (
        0.65
        <=
        on_time_rate
        <=
        0.90
    ):

        raise ValueError(
            "Synthetic ON_TIME payment rate is "
            "outside expected engineering range"
        )

    if not (
        0.05
        <=
        late_rate
        <=
        0.25
    ):

        raise ValueError(
            "Synthetic LATE payment rate is "
            "outside expected engineering range"
        )

    if not (
        0.02
        <=
        missed_rate
        <=
        0.15
    ):

        raise ValueError(
            "Synthetic MISSED payment rate is "
            "outside expected engineering range"
        )

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
        payments[
            "data_origin"
        ]
        .astype(str)
        !=
        expected_origin
    ).any():

        raise ValueError(
            "Unexpected payment data_origin"
        )

    expected_version = str(
        generation.get(
            "generator_version",
            "1.0.0",
        )
    )

    if (
        payments[
            "generator_version"
        ]
        .astype(str)
        !=
        expected_version
    ).any():

        raise ValueError(
            "Unexpected payment generator_version"
        )

    forbidden_columns = {
        "payment_probability",
        "on_time_probability",
        "late_probability",
        "missed_probability",
        "latent_repayment_quality",
        "latent_payment_reliability",
        "default_probability",
        "true_default",
        "collection_probability",
        "cross_sell_probability",
        "risk_score",
        "risk_band",
    }

    leaked = (
        forbidden_columns
        &
        set(
            payments.columns
        )
    )

    if leaked:

        raise ValueError(
            "Hidden Finance truth leaked into payment "
            "history: "
            +
            ", ".join(
                sorted(
                    leaked
                )
            )
        )


def generate_payment_master(
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
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
    Public entry point used later by generate_all.py.
    """

    return generate_payment_history(
        finance_customers=
            finance_customers,
        loan_accounts=
            loan_accounts,
        generation=
            generation,
        distributions=
            distributions,
    )


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

    payments_df = (
        generate_payment_master(
            finance_customers=
                finance_customers_df,
            loan_accounts=
                loan_accounts_df,
        )
    )

    print(
        "\n=== FINANCE PAYMENT SAMPLE ===\n"
    )

    print(
        payments_df[
            [
                "payment_event_id",
                "loan_account_id",
                "installment_number",
                "payment_due_at",
                "scheduled_payment_amount_inr",
                "payment_status",
                "actual_payment_at",
                "actual_payment_amount_inr",
                "payment_delay_days",
                "days_past_due_after_event",
                "arrears_amount_inr",
                "outstanding_principal_inr",
            ]
        ]
        .head(
            40
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== PAYMENT STATUS COUNTS ===\n"
    )

    payment_status_counts = (
        payments_df[
            "payment_status"
        ]
        .value_counts()
        .rename_axis(
            "payment_status"
        )
        .reset_index(
            name=
                "payment_count"
        )
    )

    payment_status_counts[
        "rate"
    ] = (
        payment_status_counts[
            "payment_count"
        ]
        /
        len(
            payments_df
        )
    )

    payment_status_counts[
        "rate"
    ] = (
        payment_status_counts[
            "rate"
        ]
        .round(
            4
        )
    )

    print(
        payment_status_counts
        .to_string(
            index=False
        )
    )

    print(
        "\n=== PAYMENT HISTORY LENGTH PER LOAN ===\n"
    )

    history_counts = (
        payments_df
        .groupby(
            "loan_account_id"
        )
        .size()
    )

    print(
        history_counts
        .describe()
        .round(
            2
        )
        .to_string()
    )

    print(
        "\n=== DPD SUMMARY ===\n"
    )

    print(
        payments_df[
            "days_past_due_after_event"
        ]
        .describe()
        .round(
            2
        )
        .to_string()
    )

    print(
        "\nPayments with DPD >= 15:",
        int(
            (
                payments_df[
                    "days_past_due_after_event"
                ]
                >=
                15
            ).sum()
        ),
    )

    print(
        "Payments with DPD >= 30:",
        int(
            (
                payments_df[
                    "days_past_due_after_event"
                ]
                >=
                30
            ).sum()
        ),
    )

    print(
        "Payments with DPD >= 60:",
        int(
            (
                payments_df[
                    "days_past_due_after_event"
                ]
                >=
                60
            ).sum()
        ),
    )

    print(
        "\n=== ARREARS SUMMARY ===\n"
    )

    arrears_active = (
        payments_df[
            payments_df[
                "arrears_amount_inr"
            ]
            >
            0
        ]
    )

    print(
        "Rows with active arrears:",
        len(
            arrears_active
        ),
    )

    if not arrears_active.empty:

        print(
            arrears_active[
                "arrears_amount_inr"
            ]
            .describe()
            .round(
                2
            )
            .to_string()
        )

    payment_with_customer = (
        payments_df[
            [
                "payment_event_id",
                "finance_customer_id",
                "payment_status",
            ]
        ]
        .merge(
            finance_customers_df[
                [
                    "finance_customer_id",
                    "income_stability",
                ]
            ],
            on=
                "finance_customer_id",
            how=
                "left",
            validate=
                "many_to_one",
        )
    )

    print(
        "\n=== PAYMENT STATUS BY INCOME STABILITY ===\n"
    )

    stability_status = (
        payment_with_customer
        .groupby(
            [
                "income_stability",
                "payment_status",
            ]
        )
        .size()
        .reset_index(
            name=
                "payment_count"
        )
    )

    stability_totals = (
        stability_status
        .groupby(
            "income_stability"
        )[
            "payment_count"
        ]
        .transform(
            "sum"
        )
    )

    stability_status[
        "rate"
    ] = (
        stability_status[
            "payment_count"
        ]
        /
        stability_totals
    ).round(
        4
    )

    print(
        stability_status
        .to_string(
            index=False
        )
    )

    latest_payment_state = (
        payments_df
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

    print(
        "\n=== LATEST LOAN PAYMENT STATE ===\n"
    )

    print(
        "Loans with active arrears:",
        int(
            (
                latest_payment_state[
                    "arrears_amount_inr"
                ]
                >
                0
            ).sum()
        ),
    )

    print(
        "Loans currently DPD >= 15:",
        int(
            (
                latest_payment_state[
                    "days_past_due_after_event"
                ]
                >=
                15
            ).sum()
        ),
    )

    print(
        "Loans currently DPD >= 30:",
        int(
            (
                latest_payment_state[
                    "days_past_due_after_event"
                ]
                >=
                30
            ).sum()
        ),
    )

    print(
        "\n=== FINANCE PAYMENT VALIDATION ===\n"
    )

    print(
        "Rows:",
        len(
            payments_df
        ),
    )

    print(
        "Unique payment event IDs:",
        payments_df[
            "payment_event_id"
        ].nunique(),
    )

    print(
        "Loans represented:",
        payments_df[
            "loan_account_id"
        ].nunique(),
    )

    print(
        "Customers represented:",
        payments_df[
            "finance_customer_id"
        ].nunique(),
    )

    print(
        "Minimum history rows/loan:",
        int(
            history_counts.min()
        ),
    )

    print(
        "Maximum history rows/loan:",
        int(
            history_counts.max()
        ),
    )

    print(
        "Maximum observed DPD:",
        int(
            payments_df[
                "days_past_due_after_event"
            ].max()
        ),
    )

    print(
        "Duplicate payment IDs:",
        int(
            payments_df[
                "payment_event_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    forbidden_columns = {
        "payment_probability",
        "on_time_probability",
        "late_probability",
        "missed_probability",
        "latent_repayment_quality",
        "default_probability",
        "true_default",
        "risk_score",
    }

    leaked_columns = sorted(
        forbidden_columns
        &
        set(
            payments_df.columns
        )
    )

    print(
        "Hidden truth leakage:",
        leaked_columns,
    )

    print(
        "\nGenerated "
        f"{len(payments_df)} "
        "Finance payment events successfully."
    )