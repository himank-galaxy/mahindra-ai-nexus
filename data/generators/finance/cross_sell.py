"""
Synthetic Finance Cross-Sell Event Generator
for Mahindra AI Nexus.

Builds historical operational cross-sell events from:

    Finance Customers
          +
    Loan Accounts
          +
    Payment History
          +
    Finance Product Master
          ↓
    Cross-Sell Offer / Response Events


============================================================
IMPORTANT ARCHITECTURAL RULE
============================================================

This file generates BUSINESS EVENTS.

It does NOT generate fake dashboard/model outputs such as:

    cross_sell_score
    recommendation_probability
    acceptance_probability
    eligibility_probability
    risk_score
    confidence

Instead, offer creation is driven internally from observable
evidence:

    current products
    repayment history
    current DPD
    income stability
    existing debt-service burden
    product compatibility

The resulting event contains only what an operational system
could actually observe:

    product offered
    offer terms
    offer timestamp
    channel
    customer response
    response timestamp


============================================================
IMPORTANT PRODUCT RULE
============================================================

Only canonical products from:

    master/finance_products.py

are referenced.

We DO NOT invent product IDs for:

    insurance
    fixed deposits
    mutual funds
    leasing
    rural housing

until those products actually exist in the canonical Finance
Product master.

This preserves foreign-key integrity.


============================================================
NO FUTURE LEAKAGE
============================================================

For every cross-sell event:

    only customer loans existing before offer_at are used;

    only payment states that were known before offer_at
    are used;

    future payment events are not consulted.


============================================================
ONE EVENT PER CUSTOMER
============================================================

For this first synthetic version:

    at most one cross-sell event per Finance customer.

The number of events is evidence-derived.

There is deliberately no arbitrary:

    cross_sell_events.count

configuration.


============================================================
OUTPUT
============================================================

This module DOES NOT write CSV files.

Later:

    data/scripts/generate_all.py

will write:

    data/synthetic/finance/cross_sell_events.csv
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

from data.generators.finance.loans import (
    PRODUCT_CODE_PREFERENCE,
    PRODUCT_TARGET_WEIGHTS_BY_CUSTOMER_SEGMENT,
    RATE_MARGIN_BY_INCOME_STABILITY,
    calculate_emi,
)


CROSS_SELL_EVENT_VERSION = "FIN_CROSS_SELL_V1"


MINIMUM_PAYMENT_EVENTS_FOR_CROSS_SELL = 6

MAX_CURRENT_DPD_FOR_CROSS_SELL = 14

MINIMUM_ON_TIME_RATE = 0.72

MAXIMUM_MISSED_RATE = 0.12

MAXIMUM_CURRENT_DSR = 0.65

MAXIMUM_POST_OFFER_DSR = 0.70

MINIMUM_DAYS_BEFORE_GENERATION_END = 7


CHANNEL_WEIGHTS_BY_GEO_SEGMENT: dict[
    str,
    dict[str, float],
] = {
    "URBAN": {
        "WHATSAPP": 0.42,
        "CALL": 0.28,
        "EMAIL": 0.20,
        "BRANCH": 0.10,
    },

    "SEMI_URBAN": {
        "WHATSAPP": 0.38,
        "CALL": 0.35,
        "EMAIL": 0.10,
        "BRANCH": 0.17,
    },

    "RURAL": {
        "WHATSAPP": 0.30,
        "CALL": 0.42,
        "EMAIL": 0.05,
        "BRANCH": 0.23,
    },
}


CHANNEL_CONTACT_PROBABILITY: dict[
    str,
    float,
] = {
    "WHATSAPP": 0.82,
    "CALL": 0.77,
    "EMAIL": 0.60,
    "BRANCH": 0.90,
}


RESPONSE_INTERESTED = "INTERESTED"

RESPONSE_DECLINED = "DECLINED"

RESPONSE_NO_RESPONSE = "NO_RESPONSE"


VALID_RESPONSES = {
    RESPONSE_INTERESTED,
    RESPONSE_DECLINED,
    RESPONSE_NO_RESPONSE,
}


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
    "obligation_to_income_ratio",

    "customer_since",

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
    "target_segment",
    "secured",

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


FINANCE_PRODUCT_REQUIRED_COLUMNS: set[str] = {
    "finance_product_id",

    "product_code",
    "product_name",
    "product_category",

    "secured",

    "min_loan_amount_inr",
    "max_loan_amount_inr",

    "min_tenure_months",
    "max_tenure_months",

    "base_interest_rate_pct",
    "max_ltv_pct",

    "target_segment",

    "active",

    "data_origin",
    "generator_version",
}


def _as_float(
    value: Any,
    name: str,
) -> float:

    if isinstance(
        value,
        bool,
    ):

        raise TypeError(
            f"{name} must be numeric"
        )

    try:

        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as exc:

        raise TypeError(
            f"{name} must be numeric"
        ) from exc


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
    Return timezone-aware start/end timestamps.
    """

    try:

        start_date = generation[
            "time"
        ][
            "start_date"
        ]

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
            "Missing generation.time configuration"
        ) from exc

    start = pd.Timestamp(
        start_date
    )

    end = pd.Timestamp(
        end_date
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


def _validate_inputs(
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
    payment_history: pd.DataFrame,
    finance_products: pd.DataFrame,
) -> None:
    """
    Validate Finance chain before cross-sell generation.
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

        "finance_products":
            (
                finance_products,
                FINANCE_PRODUCT_REQUIRED_COLUMNS,
            ),
    }

    for (
        dataset_name,
        (
            dataframe,
            required,
        ),
    ) in datasets.items():

        if dataframe.empty:

            raise ValueError(
                f"{dataset_name} cannot be empty"
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
                f"{dataset_name} is missing columns: "
                +
                ", ".join(
                    sorted(
                        missing
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

    if (
        finance_products[
            "finance_product_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Duplicate finance_product_id values found"
        )

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

    valid_product_ids = set(
        finance_products[
            "finance_product_id"
        ]
        .astype(str)
    )

    invalid_products = (
        set(
            loan_accounts[
                "finance_product_id"
            ]
            .astype(str)
        )
        -
        valid_product_ids
    )

    if invalid_products:

        raise ValueError(
            "Loans reference invalid Finance products"
        )


def _prepare_payment_history(
    payment_history: pd.DataFrame,
) -> pd.DataFrame:
    """
    Add internal timestamp representing when the event state
    became observable.

    ON_TIME / LATE:
        actual payment time.

    MISSED:
        due date + 1 day.

    This prevents cross-sell decisions from reading future
    payment outcomes.
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
        pd.to_timedelta(
            1,
            unit="D",
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
            "Unable to determine payment state-known "
            "timestamp for one or more rows"
        )

    return payments


def _get_tenure_distribution(
    distributions: Mapping[
        str,
        Any,
    ],
) -> tuple[
    list[int],
    list[float],
]:
    """
    Reuse configured Finance tenure distribution.
    """

    try:

        config = (
            distributions[
                "finance"
            ][
                "tenure_months"
            ]
        )

        values = [
            int(
                value
            )

            for value in config[
                "values"
            ]
        ]

        weights = [
            float(
                value
            )

            for value in config[
                "weights"
            ]
        ]

    except KeyError as exc:

        raise KeyError(
            "Missing distributions.finance."
            "tenure_months"
        ) from exc

    if len(
        values
    ) != len(
        weights
    ):

        raise ValueError(
            "Finance tenure values/weights length mismatch"
        )

    if not values:

        raise ValueError(
            "Finance tenure values cannot be empty"
        )

    total = float(
        sum(
            weights
        )
    )

    if total <= 0:

        raise ValueError(
            "Finance tenure weights must sum to > 0"
        )

    probabilities = [
        weight
        /
        total

        for weight in weights
    ]

    return (
        values,
        probabilities,
    )


def _get_principal_distribution(
    distributions: Mapping[
        str,
        Any,
    ],
) -> dict[
    str,
    float,
]:
    """
    Read Finance loan principal configuration.
    """

    try:

        config = (
            distributions[
                "finance"
            ][
                "loan_principal"
            ]
        )

    except KeyError as exc:

        raise KeyError(
            "Missing distributions.finance.loan_principal"
        ) from exc

    if (
        str(
            config.get(
                "distribution",
                "",
            )
        ).lower()
        !=
        "lognormal"
    ):

        raise ValueError(
            "Cross-sell currently requires Finance "
            "loan_principal distribution='lognormal'"
        )

    parsed = {
        "mean":
            _as_float(
                config[
                    "mean"
                ],
                "finance.loan_principal.mean",
            ),

        "sigma":
            _as_float(
                config[
                    "sigma"
                ],
                "finance.loan_principal.sigma",
            ),

        "min":
            _as_float(
                config[
                    "min"
                ],
                "finance.loan_principal.min",
            ),

        "max":
            _as_float(
                config[
                    "max"
                ],
                "finance.loan_principal.max",
            ),
    }

    if parsed[
        "sigma"
    ] <= 0:

        raise ValueError(
            "Finance loan-principal sigma must be > 0"
        )

    return parsed


def _normalize_weights(
    values: list[
        float
    ],
) -> np.ndarray:
    """
    Normalize positive weights.
    """

    array = np.asarray(
        values,
        dtype=float,
    )

    array = np.clip(
        array,
        0.0,
        None,
    )

    total = float(
        array.sum()
    )

    if total <= 0:

        raise ValueError(
            "Weights must sum to > 0"
        )

    return (
        array
        /
        total
    )


def _product_compatibility_weight(
    customer_segment: str,
    product: Mapping[
        str,
        Any,
    ],
) -> float:
    """
    Use same business segmentation logic as loan generation.
    """

    segment_weights = (
        PRODUCT_TARGET_WEIGHTS_BY_CUSTOMER_SEGMENT.get(
            customer_segment,
            {},
        )
    )

    target_segment = str(
        product[
            "target_segment"
        ]
    )

    target_weight = float(
        segment_weights.get(
            target_segment,
            0.0,
        )
    )

    if target_weight <= 0:

        return 0.0

    code = str(
        product[
            "product_code"
        ]
    )

    product_preference = float(
        PRODUCT_CODE_PREFERENCE.get(
            code,
            1.0,
        )
    )

    return (
        target_weight
        *
        product_preference
    )


def _principal_for_emi(
    maximum_emi: float,
    annual_interest_rate_pct: float,
    tenure_months: int,
) -> float:
    """
    Calculate maximum principal compatible with a monthly EMI.
    """

    maximum_emi = float(
        maximum_emi
    )

    if maximum_emi <= 0:

        return 0.0

    tenure = int(
        tenure_months
    )

    if tenure <= 0:

        return 0.0

    monthly_rate = (
        float(
            annual_interest_rate_pct
        )
        /
        12.0
        /
        100.0
    )

    if monthly_rate <= 0:

        return 0.0

    factor = (
        1.0
        +
        monthly_rate
    ) ** tenure

    denominator = (
        monthly_rate
        *
        factor
    )

    if denominator <= 0:

        return 0.0

    principal = (
        maximum_emi
        *
        (
            factor
            -
            1.0
        )
        /
        denominator
    )

    return float(
        max(
            principal,
            0.0,
        )
    )


def _derive_offer_rate(
    rng: np.random.Generator,
    product: Mapping[
        str,
        Any,
    ],
    income_stability: str,
) -> float:
    """
    Derive offer rate from canonical base rate and observable
    income stability.

    This is not a hidden default score.
    """

    base_rate = float(
        product[
            "base_interest_rate_pct"
        ]
    )

    stability_margin = float(
        RATE_MARGIN_BY_INCOME_STABILITY.get(
            income_stability,
            0.75,
        )
    )

    rate = (
        base_rate
        +
        0.70
        *
        stability_margin
        +
        float(
            rng.normal(
                0.0,
                0.15,
            )
        )
    )

    rate = float(
        np.clip(
            rate,
            base_rate
            -
            0.25,
            base_rate
            +
            2.75,
        )
    )

    return round(
        rate,
        3,
    )


def _build_customer_snapshot(
    customer_id: str,
    offer_at: pd.Timestamp,
    customer: Mapping[
        str,
        Any,
    ],
    customer_loans: pd.DataFrame,
    customer_payments: pd.DataFrame,
) -> dict[
    str,
    Any,
] | None:
    """
    Build evidence available at offer_at.

    Returns None if insufficient evidence exists.
    """

    known_payments = (
        customer_payments[
            customer_payments[
                "_state_known_at"
            ]
            <=
            offer_at
        ]
        .copy()
    )

    if (
        len(
            known_payments
        )
        <
        MINIMUM_PAYMENT_EVENTS_FOR_CROSS_SELL
    ):

        return None

    existing_loans = (
        customer_loans[
            customer_loans[
                "disbursed_at"
            ]
            <=
            offer_at
        ]
        .copy()
    )

    if existing_loans.empty:

        return None

    historical_product_codes = set(
        existing_loans[
            "product_code"
        ]
        .astype(str)
    )

    latest_state = (
        known_payments
        .sort_values(
            [
                "loan_account_id",
                "_state_known_at",
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

    latest_state_lookup = {
        str(
            row.loan_account_id
        ):
            row._asdict()

        for row in latest_state.itertuples(
            index=False
        )
    }

    active_loans: list[
        dict[str, Any]
    ] = []

    for loan in existing_loans.to_dict(
        orient="records"
    ):

        loan_id = str(
            loan[
                "loan_account_id"
            ]
        )

        maturity = pd.to_datetime(
            loan[
                "scheduled_maturity_at"
            ],
            utc=True,
        )

        latest_payment = (
            latest_state_lookup.get(
                loan_id
            )
        )

        if latest_payment is None:

            outstanding = float(
                loan[
                    "principal_inr"
                ]
            )

        else:

            outstanding = float(
                latest_payment[
                    "outstanding_principal_inr"
                ]
            )

        active = (
            maturity
            >
            offer_at
            or
            outstanding
            >
            0.01
        )

        if active:

            enriched = dict(
                loan
            )

            enriched[
                "_outstanding_principal"
            ] = outstanding

            enriched[
                "_current_dpd"
            ] = (
                0
                if latest_payment is None
                else int(
                    latest_payment[
                        "days_past_due_after_event"
                    ]
                )
            )

            active_loans.append(
                enriched
            )

    if not active_loans:

        current_max_dpd = 0

        active_emi = 0.0

    else:

        current_max_dpd = max(
            int(
                loan[
                    "_current_dpd"
                ]
            )

            for loan in active_loans
        )

        active_emi = float(
            sum(
                float(
                    loan[
                        "emi_amount_inr"
                    ]
                )

                for loan in active_loans
            )
        )

    total_events = len(
        known_payments
    )

    on_time_count = int(
        (
            known_payments[
                "payment_status"
            ]
            .astype(str)
            ==
            "ON_TIME"
        )
        .sum()
    )

    missed_count = int(
        (
            known_payments[
                "payment_status"
            ]
            .astype(str)
            ==
            "MISSED"
        )
        .sum()
    )

    late_count = int(
        (
            known_payments[
                "payment_status"
            ]
            .astype(str)
            ==
            "LATE"
        )
        .sum()
    )

    on_time_rate = (
        on_time_count
        /
        total_events
    )

    missed_rate = (
        missed_count
        /
        total_events
    )

    late_rate = (
        late_count
        /
        total_events
    )

    monthly_income = float(
        customer[
            "monthly_income_inr"
        ]
    )

    existing_external_obligations = float(
        customer[
            "monthly_obligations_inr"
        ]
    )

    total_monthly_debt_service = (
        existing_external_obligations
        +
        active_emi
    )

    current_dsr = (
        total_monthly_debt_service
        /
        monthly_income
    )

    source_loan = (
        existing_loans
        .sort_values(
            [
                "disbursed_at",
                "loan_account_id",
            ]
        )
        .iloc[
            -1
        ]
    )

    return {
        "finance_customer_id":
            customer_id,

        "known_payment_event_count":
            total_events,

        "on_time_rate":
            float(
                on_time_rate
            ),

        "late_rate":
            float(
                late_rate
            ),

        "missed_rate":
            float(
                missed_rate
            ),

        "current_max_dpd":
            int(
                current_max_dpd
            ),

        "active_emi_inr":
            float(
                active_emi
            ),

        "current_dsr":
            float(
                current_dsr
            ),

        "historical_product_codes":
            historical_product_codes,

        "source_loan_account_id":
            str(
                source_loan[
                    "loan_account_id"
                ]
            ),

        "source_product_code":
            str(
                source_loan[
                    "product_code"
                ]
            ),
    }


def _snapshot_is_cross_sell_ready(
    snapshot: Mapping[
        str,
        Any,
    ],
) -> bool:
    """
    Evidence-based rule deciding whether to create an
    historical cross-sell event.

    The rule itself is generator knowledge and is not exported.
    """

    if (
        int(
            snapshot[
                "known_payment_event_count"
            ]
        )
        <
        MINIMUM_PAYMENT_EVENTS_FOR_CROSS_SELL
    ):

        return False

    if (
        int(
            snapshot[
                "current_max_dpd"
            ]
        )
        >
        MAX_CURRENT_DPD_FOR_CROSS_SELL
    ):

        return False

    if (
        float(
            snapshot[
                "on_time_rate"
            ]
        )
        <
        MINIMUM_ON_TIME_RATE
    ):

        return False

    if (
        float(
            snapshot[
                "missed_rate"
            ]
        )
        >
        MAXIMUM_MISSED_RATE
    ):

        return False

    if (
        float(
            snapshot[
                "current_dsr"
            ]
        )
        >
        MAXIMUM_CURRENT_DSR
    ):

        return False

    return True


def _build_product_options(
    rng: np.random.Generator,
    customer: Mapping[
        str,
        Any,
    ],
    snapshot: Mapping[
        str,
        Any,
    ],
    finance_products: pd.DataFrame,
    tenure_values: list[int],
    tenure_weights: list[float],
    principal_distribution: Mapping[
        str,
        float,
    ],
) -> list[
    dict[str, Any]
]:
    """
    Build affordable cross-product candidates.

    Previously-held product codes are excluded.
    """

    monthly_income = float(
        customer[
            "monthly_income_inr"
        ]
    )

    monthly_external_obligations = float(
        customer[
            "monthly_obligations_inr"
        ]
    )

    active_emi = float(
        snapshot[
            "active_emi_inr"
        ]
    )

    maximum_monthly_debt_service = (
        monthly_income
        *
        MAXIMUM_POST_OFFER_DSR
    )

    maximum_new_emi = (
        maximum_monthly_debt_service
        -
        monthly_external_obligations
        -
        active_emi
    )

    if maximum_new_emi <= 0:

        return []

    customer_segment = str(
        customer[
            "finance_customer_segment"
        ]
    )

    income_stability = str(
        customer[
            "income_stability"
        ]
    )

    already_held = set(
        snapshot[
            "historical_product_codes"
        ]
    )

    options: list[
        dict[str, Any]
    ] = []

    active_products = (
        finance_products[
            finance_products[
                "active"
            ]
            .astype(bool)
        ]
    )

    for product in active_products.to_dict(
        orient="records"
    ):

        product_code = str(
            product[
                "product_code"
            ]
        )

        if product_code in already_held:

            continue

        compatibility_weight = (
            _product_compatibility_weight(
                customer_segment=
                    customer_segment,

                product=
                    product,
            )
        )

        if compatibility_weight <= 0:

            continue

        interest_rate = (
            _derive_offer_rate(
                rng=
                    rng,

                product=
                    product,

                income_stability=
                    income_stability,
            )
        )

        product_minimum = max(
            float(
                product[
                    "min_loan_amount_inr"
                ]
            ),
            float(
                principal_distribution[
                    "min"
                ]
            ),
        )

        product_maximum = min(
            float(
                product[
                    "max_loan_amount_inr"
                ]
            ),
            float(
                principal_distribution[
                    "max"
                ]
            ),
        )

        valid_tenures: list[
            int
        ] = []

        valid_weights: list[
            float
        ] = []

        valid_max_principal: list[
            float
        ] = []

        for (
            tenure,
            tenure_weight,
        ) in zip(
            tenure_values,
            tenure_weights,
        ):

            if not (
                int(
                    product[
                        "min_tenure_months"
                    ]
                )
                <=
                tenure
                <=
                int(
                    product[
                        "max_tenure_months"
                    ]
                )
            ):

                continue

            affordable_principal = (
                _principal_for_emi(
                    maximum_emi=
                        maximum_new_emi,

                    annual_interest_rate_pct=
                        interest_rate,

                    tenure_months=
                        tenure,
                )
            )

            effective_maximum = min(
                product_maximum,
                affordable_principal,
            )

            if (
                effective_maximum
                +
                1e-6
                <
                product_minimum
            ):

                continue

            valid_tenures.append(
                tenure
            )

            valid_weights.append(
                tenure_weight
            )

            valid_max_principal.append(
                effective_maximum
            )

        if not valid_tenures:

            continue

        valid_weights_array = (
            _normalize_weights(
                valid_weights
            )
        )

        options.append(
            {
                "product":
                    product,

                "compatibility_weight":
                    float(
                        compatibility_weight
                    ),

                "interest_rate_pct":
                    float(
                        interest_rate
                    ),

                "minimum_principal":
                    float(
                        product_minimum
                    ),

                "valid_tenures":
                    valid_tenures,

                "valid_tenure_weights":
                    valid_weights_array,

                "maximum_principal_by_tenure":
                    valid_max_principal,
            }
        )

    return options


def _select_offer_terms(
    rng: np.random.Generator,
    customer: Mapping[
        str,
        Any,
    ],
    snapshot: Mapping[
        str,
        Any,
    ],
    finance_products: pd.DataFrame,
    tenure_values: list[int],
    tenure_weights: list[float],
    principal_distribution: Mapping[
        str,
        float,
    ],
) -> dict[
    str,
    Any,
] | None:
    """
    Select one evidence-compatible product and affordable
    cross-sell offer.
    """

    options = (
        _build_product_options(
            rng=
                rng,

            customer=
                customer,

            snapshot=
                snapshot,

            finance_products=
                finance_products,

            tenure_values=
                tenure_values,

            tenure_weights=
                tenure_weights,

            principal_distribution=
                principal_distribution,
        )
    )

    if not options:

        return None

    option_probabilities = (
        _normalize_weights(
            [
                float(
                    option[
                        "compatibility_weight"
                    ]
                )

                for option in options
            ]
        )
    )

    selected_option_index = int(
        rng.choice(
            np.arange(
                len(
                    options
                )
            ),
            p=
                option_probabilities,
        )
    )

    option = options[
        selected_option_index
    ]

    tenure_index = int(
        rng.choice(
            np.arange(
                len(
                    option[
                        "valid_tenures"
                    ]
                )
            ),
            p=
                option[
                    "valid_tenure_weights"
                ],
        )
    )

    tenure_months = int(
        option[
            "valid_tenures"
        ][
            tenure_index
        ]
    )

    maximum_principal = float(
        option[
            "maximum_principal_by_tenure"
        ][
            tenure_index
        ]
    )

    minimum_principal = float(
        option[
            "minimum_principal"
        ]
    )

    principal = float(
        rng.lognormal(
            mean=
                float(
                    principal_distribution[
                        "mean"
                    ]
                ),

            sigma=
                float(
                    principal_distribution[
                        "sigma"
                    ]
                ),
        )
    )

    principal = float(
        np.clip(
            principal,
            minimum_principal,
            maximum_principal,
        )
    )

    principal = float(
        round(
            principal
            /
            1000.0
        )
        *
        1000.0
    )

    principal = float(
        np.clip(
            principal,
            minimum_principal,
            maximum_principal,
        )
    )

    interest_rate = float(
        option[
            "interest_rate_pct"
        ]
    )

    emi = calculate_emi(
        principal_inr=
            principal,

        annual_interest_rate_pct=
            interest_rate,

        tenure_months=
            tenure_months,
    )

    product = (
        option[
            "product"
        ]
    )

    return {
        "product":
            product,

        "offer_amount_inr":
            round(
                principal,
                2,
            ),

        "offer_interest_rate_pct":
            round(
                interest_rate,
                3,
            ),

        "offer_tenure_months":
            tenure_months,

        "estimated_offer_emi_inr":
            round(
                emi,
                2,
            ),

        "_product_fit":
            float(
                option[
                    "compatibility_weight"
                ]
            ),
    }


def _select_offer_channel(
    rng: np.random.Generator,
    rural_urban_segment: str,
) -> str:
    """
    Generate offer channel using geography/segment evidence.
    """

    weights = (
        CHANNEL_WEIGHTS_BY_GEO_SEGMENT.get(
            rural_urban_segment
        )
    )

    if weights is None:

        raise ValueError(
            "Unsupported rural_urban_segment: "
            f"{rural_urban_segment}"
        )

    channels = list(
        weights.keys()
    )

    probabilities = (
        _normalize_weights(
            list(
                weights.values()
            )
        )
    )

    return str(
        rng.choice(
            channels,
            p=
                probabilities,
        )
    )


def _generate_customer_response(
    rng: np.random.Generator,
    offer_at: pd.Timestamp,
    generation_end: pd.Timestamp,
    channel: str,
    customer: Mapping[
        str,
        Any,
    ],
    snapshot: Mapping[
        str,
        Any,
    ],
    product_fit: float,
) -> tuple[
    str,
    pd.Timestamp | None,
]:
    """
    Generate an observed response.

    Internal response probability is evidence-derived and is
    NOT stored in runtime output.
    """

    contact_probability = float(
        CHANNEL_CONTACT_PROBABILITY[
            channel
        ]
    )

    if (
        float(
            rng.random()
        )
        >
        contact_probability
    ):

        return (
            RESPONSE_NO_RESPONSE,
            None,
        )

    on_time_rate = float(
        snapshot[
            "on_time_rate"
        ]
    )

    missed_rate = float(
        snapshot[
            "missed_rate"
        ]
    )

    current_dsr = float(
        snapshot[
            "current_dsr"
        ]
    )

    income_stability = str(
        customer[
            "income_stability"
        ]
    )

    interest_probability = 0.38

    interest_probability += (
        0.25
        *
        (
            on_time_rate
            -
            0.72
        )
    )

    interest_probability -= (
        0.70
        *
        missed_rate
    )

    if income_stability == "HIGH":

        interest_probability += 0.07

    elif (
        income_stability
        ==
        "MEDIUM_HIGH"
    ):

        interest_probability += 0.04

    elif income_stability == "LOW":

        interest_probability -= 0.04

    if current_dsr > 0.50:

        interest_probability -= (
            0.40
            *
            (
                current_dsr
                -
                0.50
            )
        )

    interest_probability += (
        min(
            product_fit,
            1.0,
        )
        *
        0.05
    )

    interest_probability = float(
        np.clip(
            interest_probability,
            0.10,
            0.75,
        )
    )

    if (
        float(
            rng.random()
        )
        <
        interest_probability
    ):

        response = (
            RESPONSE_INTERESTED
        )

    else:

        response = (
            RESPONSE_DECLINED
        )

    response_delay_hours = float(
        np.clip(
            rng.lognormal(
                mean=3.0,
                sigma=0.70,
            ),
            1.0,
            120.0,
        )
    )

    responded_at = (
        offer_at
        +
        pd.to_timedelta(
            response_delay_hours,
            unit="h",
        )
    )

    if responded_at >= generation_end:

        return (
            RESPONSE_NO_RESPONSE,
            None,
        )

    return (
        response,
        responded_at,
    )


def _choose_offer_timestamp(
    rng: np.random.Generator,
    customer_payments: pd.DataFrame,
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
) -> pd.Timestamp | None:
    """
    Choose a historical 2026 offer timestamp from payment
    states that were already known.

    This avoids future leakage.
    """

    latest_allowed = (
        generation_end
        -
        timedelta(
            days=
                MINIMUM_DAYS_BEFORE_GENERATION_END
        )
    )

    candidates = (
        customer_payments[
            (
                customer_payments[
                    "_state_known_at"
                ]
                >=
                generation_start
            )
            &
            (
                customer_payments[
                    "_state_known_at"
                ]
                <
                latest_allowed
            )
        ]
        .sort_values(
            "_state_known_at"
        )
        .copy()
    )

    if (
        len(
            candidates
        )
        <
        MINIMUM_PAYMENT_EVENTS_FOR_CROSS_SELL
    ):

        return None

    candidates = (
        candidates.iloc[
            MINIMUM_PAYMENT_EVENTS_FOR_CROSS_SELL
            -
            1:
        ]
    )

    recent_candidates = (
        candidates.tail(
            min(
                6,
                len(
                    candidates
                ),
            )
        )
    )

    selected_position = int(
        rng.integers(
            0,
            len(
                recent_candidates
            ),
        )
    )

    anchor_at = pd.Timestamp(
        recent_candidates.iloc[
            selected_position
        ][
            "_state_known_at"
        ]
    )

    delay_hours = int(
        rng.integers(
            12,
            49,
        )
    )

    offer_at = (
        anchor_at
        +
        timedelta(
            hours=
                delay_hours
        )
    )

    if offer_at >= latest_allowed:

        offer_at = (
            latest_allowed
            -
            timedelta(
                minutes=1
            )
        )

    if offer_at <= generation_start:

        return None

    return offer_at


def generate_cross_sell_events(
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
    payment_history: pd.DataFrame,
    finance_products: pd.DataFrame,
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
    Generate evidence-driven historical cross-sell events.
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

        payment_history=
            payment_history,

        finance_products=
            finance_products,
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
            "finance.cross_sell",
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

    (
        tenure_values,
        tenure_weights,
    ) = (
        _get_tenure_distribution(
            distributions
        )
    )

    principal_distribution = (
        _get_principal_distribution(
            distributions
        )
    )

    payments = (
        _prepare_payment_history(
            payment_history
        )
    )

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

    customer_lookup = {
        str(
            row.finance_customer_id
        ):
            row._asdict()

        for row in finance_customers.itertuples(
            index=False
        )
    }

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

    borrower_ids = sorted(
        set(
            loans[
                "finance_customer_id"
            ]
            .astype(str)
        )
    )

    rows: list[
        dict[str, Any]
    ] = []

    # --------------------------------------------------------
    # Performance-only optimization.
    #
    # Previously each customer iteration scanned the complete
    # loans and payment tables again.
    #
    # These caches preserve row content/order and do not
    # consume RNG state, so business behaviour remains the
    # same while generation becomes substantially cheaper.
    # --------------------------------------------------------

    loan_groups = {
        str(
            customer_id
        ):
            group.copy()

        for customer_id, group
        in loans.groupby(
            loans[
                "finance_customer_id"
            ]
            .astype(str),
            sort=False,
        )
    }

    payment_groups = {
        str(
            customer_id
        ):
            group.copy()

        for customer_id, group
        in payments.groupby(
            payments[
                "finance_customer_id"
            ]
            .astype(str),
            sort=False,
        )
    }

    for customer_id in borrower_ids:

        customer = (
            customer_lookup.get(
                customer_id
            )
        )

        if customer is None:

            raise ValueError(
                "Loan borrower missing from Finance "
                "customer master"
            )

        if not bool(
            customer[
                "active"
            ]
        ):

            continue

        customer_loans = (
            loan_groups[
                customer_id
            ]
        )

        customer_payments = (
            payment_groups.get(
                customer_id
            )
        )

        if customer_payments is None:

            continue

        if customer_payments.empty:

            continue

        offer_at = (
            _choose_offer_timestamp(
                rng=
                    rng,

                customer_payments=
                    customer_payments,

                generation_start=
                    generation_start,

                generation_end=
                    generation_end,
            )
        )

        if offer_at is None:

            continue

        snapshot = (
            _build_customer_snapshot(
                customer_id=
                    customer_id,

                offer_at=
                    offer_at,

                customer=
                    customer,

                customer_loans=
                    customer_loans,

                customer_payments=
                    customer_payments,
            )
        )

        if snapshot is None:

            continue

        if not (
            _snapshot_is_cross_sell_ready(
                snapshot
            )
        ):

            continue

        selected_offer = (
            _select_offer_terms(
                rng=
                    rng,

                customer=
                    customer,

                snapshot=
                    snapshot,

                finance_products=
                    finance_products,

                tenure_values=
                    tenure_values,

                tenure_weights=
                    tenure_weights,

                principal_distribution=
                    principal_distribution,
            )
        )

        if selected_offer is None:

            continue

        product = (
            selected_offer[
                "product"
            ]
        )

        channel = (
            _select_offer_channel(
                rng=
                    rng,

                rural_urban_segment=
                    str(
                        customer[
                            "rural_urban_segment"
                        ]
                    ),
            )
        )

        (
            customer_response,
            responded_at,
        ) = (
            _generate_customer_response(
                rng=
                    rng,

                offer_at=
                    offer_at,

                generation_end=
                    generation_end,

                channel=
                    channel,

                customer=
                    customer,

                snapshot=
                    snapshot,

                product_fit=
                    float(
                        selected_offer[
                            "_product_fit"
                        ]
                    ),
            )
        )

        rows.append(
            {
                "cross_sell_event_id":
                    None,

                "finance_customer_id":
                    customer_id,

                "source_loan_account_id":
                    str(
                        snapshot[
                            "source_loan_account_id"
                        ]
                    ),

                "source_product_code":
                    str(
                        snapshot[
                            "source_product_code"
                        ]
                    ),

                "region_id":
                    str(
                        customer[
                            "region_id"
                        ]
                    ),

                "region_name":
                    str(
                        customer[
                            "region_name"
                        ]
                    ),

                "city_id":
                    str(
                        customer[
                            "city_id"
                        ]
                    ),

                "city_name":
                    str(
                        customer[
                            "city_name"
                        ]
                    ),

                "offered_finance_product_id":
                    str(
                        product[
                            "finance_product_id"
                        ]
                    ),

                "offered_product_code":
                    str(
                        product[
                            "product_code"
                        ]
                    ),

                "offered_product_name":
                    str(
                        product[
                            "product_name"
                        ]
                    ),

                "offered_product_category":
                    str(
                        product[
                            "product_category"
                        ]
                    ),

                "offered_at":
                    offer_at,

                "offer_channel":
                    channel,

                "offer_amount_inr":
                    float(
                        selected_offer[
                            "offer_amount_inr"
                        ]
                    ),

                "offer_interest_rate_pct":
                    float(
                        selected_offer[
                            "offer_interest_rate_pct"
                        ]
                    ),

                "offer_tenure_months":
                    int(
                        selected_offer[
                            "offer_tenure_months"
                        ]
                    ),

                "estimated_offer_emi_inr":
                    float(
                        selected_offer[
                            "estimated_offer_emi_inr"
                        ]
                    ),

                "customer_response":
                    customer_response,

                "responded_at":
                    responded_at,

                "event_version":
                    CROSS_SELL_EVENT_VERSION,

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    if not rows:

        raise ValueError(
            "Cross-sell generator produced no events. "
            "Review Finance evidence thresholds."
        )

    cross_sell_events = (
        pd.DataFrame(
            rows
        )
        .sort_values(
            [
                "offered_at",
                "finance_customer_id",
                "offered_product_code",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    cross_sell_events[
        "cross_sell_event_id"
    ] = [
        generate_id(
            "FINXSELL_SYN",
            index,
            width=7,
        )

        for index in range(
            1,
            len(
                cross_sell_events
            )
            +
            1,
        )
    ]

    cross_sell_events = (
        cross_sell_events[
            [
                "cross_sell_event_id",

                "finance_customer_id",

                "source_loan_account_id",
                "source_product_code",

                "region_id",
                "region_name",

                "city_id",
                "city_name",

                "offered_finance_product_id",
                "offered_product_code",
                "offered_product_name",
                "offered_product_category",

                "offered_at",
                "offer_channel",

                "offer_amount_inr",
                "offer_interest_rate_pct",
                "offer_tenure_months",
                "estimated_offer_emi_inr",

                "customer_response",
                "responded_at",

                "event_version",

                "data_origin",
                "generator_version",
            ]
        ]
    )

    validate_cross_sell_events(
        cross_sell_events=
            cross_sell_events,

        finance_customers=
            finance_customers,

        loan_accounts=
            loan_accounts,

        payment_history=
            payment_history,

        finance_products=
            finance_products,

        generation=
            generation,
    )

    return cross_sell_events


def validate_cross_sell_events(
    cross_sell_events: pd.DataFrame,
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
    payment_history: pd.DataFrame,
    finance_products: pd.DataFrame,
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
) -> None:
    """
    Validate cross-sell operational history.
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    required_columns = {
        "cross_sell_event_id",

        "finance_customer_id",

        "source_loan_account_id",
        "source_product_code",

        "region_id",
        "region_name",

        "city_id",
        "city_name",

        "offered_finance_product_id",
        "offered_product_code",
        "offered_product_name",
        "offered_product_category",

        "offered_at",
        "offer_channel",

        "offer_amount_inr",
        "offer_interest_rate_pct",
        "offer_tenure_months",
        "estimated_offer_emi_inr",

        "customer_response",
        "responded_at",

        "event_version",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        -
        set(
            cross_sell_events.columns
        )
    )

    if missing:

        raise ValueError(
            "Cross-sell events missing columns: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    if cross_sell_events.empty:

        raise ValueError(
            "Cross-sell events cannot be empty"
        )

    if (
        cross_sell_events[
            "cross_sell_event_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Duplicate cross_sell_event_id values found"
        )

    if (
        cross_sell_events[
            "finance_customer_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Current cross-sell generator permits at most "
            "one event per Finance customer"
        )

    valid_customer_ids = set(
        finance_customers[
            "finance_customer_id"
        ]
        .astype(str)
    )

    invalid_customers = (
        set(
            cross_sell_events[
                "finance_customer_id"
            ]
            .astype(str)
        )
        -
        valid_customer_ids
    )

    if invalid_customers:

        raise ValueError(
            "Cross-sell events reference invalid customers"
        )

    valid_loan_ids = set(
        loan_accounts[
            "loan_account_id"
        ]
        .astype(str)
    )

    invalid_source_loans = (
        set(
            cross_sell_events[
                "source_loan_account_id"
            ]
            .astype(str)
        )
        -
        valid_loan_ids
    )

    if invalid_source_loans:

        raise ValueError(
            "Cross-sell events reference invalid "
            "source loans"
        )

    valid_product_ids = set(
        finance_products[
            "finance_product_id"
        ]
        .astype(str)
    )

    invalid_products = (
        set(
            cross_sell_events[
                "offered_finance_product_id"
            ]
            .astype(str)
        )
        -
        valid_product_ids
    )

    if invalid_products:

        raise ValueError(
            "Cross-sell events reference invalid "
            "Finance products"
        )

    customer_lookup = (
        finance_customers
        .set_index(
            "finance_customer_id"
        )
    )

    loan_lookup = (
        loan_accounts
        .set_index(
            "loan_account_id"
        )
    )

    product_lookup = (
        finance_products
        .set_index(
            "finance_product_id"
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

    offered_at = pd.to_datetime(
        cross_sell_events[
            "offered_at"
        ],
        utc=True,
    )

    if (
        offered_at
        <
        generation_start
    ).any():

        raise ValueError(
            "Cross-sell offer precedes generation start"
        )

    if (
        offered_at
        >=
        generation_end
    ).any():

        raise ValueError(
            "Cross-sell offer must precede generation end"
        )

    invalid_responses = (
        set(
            cross_sell_events[
                "customer_response"
            ]
            .astype(str)
        )
        -
        VALID_RESPONSES
    )

    if invalid_responses:

        raise ValueError(
            "Invalid cross-sell responses: "
            +
            ", ".join(
                sorted(
                    invalid_responses
                )
            )
        )

    no_response = (
        cross_sell_events[
            "customer_response"
        ]
        ==
        RESPONSE_NO_RESPONSE
    )

    if (
        cross_sell_events.loc[
            no_response,
            "responded_at",
        ]
        .notna()
        .any()
    ):

        raise ValueError(
            "NO_RESPONSE events cannot have responded_at"
        )

    responded = ~no_response

    if (
        cross_sell_events.loc[
            responded,
            "responded_at",
        ]
        .isna()
        .any()
    ):

        raise ValueError(
            "Responded cross-sell events require "
            "responded_at"
        )

    if responded.any():

        responded_at = pd.to_datetime(
            cross_sell_events.loc[
                responded,
                "responded_at",
            ],
            utc=True,
        )

        responded_offer_at = (
            pd.to_datetime(
                cross_sell_events.loc[
                    responded,
                    "offered_at",
                ],
                utc=True,
            )
        )

        if (
            responded_at
            <=
            responded_offer_at
        ).any():

            raise ValueError(
                "Cross-sell response must occur "
                "after offer"
            )

        if (
            responded_at
            >=
            generation_end
        ).any():

            raise ValueError(
                "Cross-sell response cannot occur "
                "after generation end"
            )

    for event in cross_sell_events.itertuples(
        index=False
    ):

        source_loan = loan_lookup.loc[
            str(
                event.source_loan_account_id
            )
        ]

        if (
            str(
                source_loan[
                    "finance_customer_id"
                ]
            )
            !=
            str(
                event.finance_customer_id
            )
        ):

            raise ValueError(
                "Cross-sell source loan/customer mismatch"
            )

        if (
            pd.to_datetime(
                source_loan[
                    "disbursed_at"
                ],
                utc=True,
            )
            >
            pd.to_datetime(
                event.offered_at,
                utc=True,
            )
        ):

            raise ValueError(
                "Cross-sell source loan cannot be "
                "disbursed after offer"
            )

        if (
            str(
                source_loan[
                    "product_code"
                ]
            )
            !=
            str(
                event.source_product_code
            )
        ):

            raise ValueError(
                "Cross-sell source_product_code mismatch"
            )

    for event in cross_sell_events.itertuples(
        index=False
    ):

        product = product_lookup.loc[
            str(
                event.offered_finance_product_id
            )
        ]

        if (
            str(
                product[
                    "product_code"
                ]
            )
            !=
            str(
                event.offered_product_code
            )
        ):

            raise ValueError(
                "Offered product_code does not match "
                "Finance Product master"
            )

        if (
            str(
                product[
                    "product_name"
                ]
            )
            !=
            str(
                event.offered_product_name
            )
        ):

            raise ValueError(
                "Offered product_name does not match "
                "Finance Product master"
            )

        if (
            str(
                product[
                    "product_category"
                ]
            )
            !=
            str(
                event.offered_product_category
            )
        ):

            raise ValueError(
                "Offered product_category does not match "
                "Finance Product master"
            )

        amount = float(
            event.offer_amount_inr
        )

        if not (
            float(
                product[
                    "min_loan_amount_inr"
                ]
            )
            <=
            amount
            <=
            float(
                product[
                    "max_loan_amount_inr"
                ]
            )
        ):

            raise ValueError(
                "Cross-sell offer amount outside product "
                "limits"
            )

        tenure = int(
            event.offer_tenure_months
        )

        if not (
            int(
                product[
                    "min_tenure_months"
                ]
            )
            <=
            tenure
            <=
            int(
                product[
                    "max_tenure_months"
                ]
            )
        ):

            raise ValueError(
                "Cross-sell offer tenure outside product "
                "limits"
            )

        expected_emi = calculate_emi(
            principal_inr=
                amount,

            annual_interest_rate_pct=
                float(
                    event.offer_interest_rate_pct
                ),

            tenure_months=
                tenure,
        )

        if (
            abs(
                expected_emi
                -
                float(
                    event.estimated_offer_emi_inr
                )
            )
            >
            1.0
        ):

            raise ValueError(
                "Cross-sell EMI inconsistent with offer "
                "amount/rate/tenure"
            )

    loans_for_check = (
        loan_accounts
        .copy()
    )

    loans_for_check[
        "disbursed_at"
    ] = pd.to_datetime(
        loans_for_check[
            "disbursed_at"
        ],
        utc=True,
    )

    for event in cross_sell_events.itertuples(
        index=False
    ):

        prior_same_product = (
            loans_for_check[
                (
                    loans_for_check[
                        "finance_customer_id"
                    ]
                    .astype(str)
                    ==
                    str(
                        event.finance_customer_id
                    )
                )
                &
                (
                    loans_for_check[
                        "product_code"
                    ]
                    .astype(str)
                    ==
                    str(
                        event.offered_product_code
                    )
                )
                &
                (
                    loans_for_check[
                        "disbursed_at"
                    ]
                    <=
                    pd.to_datetime(
                        event.offered_at,
                        utc=True,
                    )
                )
            ]
        )

        if not prior_same_product.empty:

            raise ValueError(
                "Cross-sell event offered a product "
                "already held by the customer"
            )

    for event in cross_sell_events.itertuples(
        index=False
    ):

        customer = customer_lookup.loc[
            str(
                event.finance_customer_id
            )
        ]

        if (
            str(
                customer[
                    "region_id"
                ]
            )
            !=
            str(
                event.region_id
            )
        ):

            raise ValueError(
                "Cross-sell region mismatch"
            )

        if (
            str(
                customer[
                    "city_id"
                ]
            )
            !=
            str(
                event.city_id
            )
        ):

            raise ValueError(
                "Cross-sell city mismatch"
            )

    valid_channels = set(
        CHANNEL_CONTACT_PROBABILITY.keys()
    )

    invalid_channels = (
        set(
            cross_sell_events[
                "offer_channel"
            ]
            .astype(str)
        )
        -
        valid_channels
    )

    if invalid_channels:

        raise ValueError(
            "Invalid cross-sell channels: "
            +
            ", ".join(
                sorted(
                    invalid_channels
                )
            )
        )

    if (
        cross_sell_events[
            "event_version"
        ]
        .astype(str)
        !=
        CROSS_SELL_EVENT_VERSION
    ).any():

        raise ValueError(
            "Unexpected cross-sell event_version"
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
        cross_sell_events[
            "data_origin"
        ]
        .astype(str)
        !=
        expected_origin
    ).any():

        raise ValueError(
            "Unexpected cross-sell data_origin"
        )

    expected_generator_version = str(
        generation.get(
            "generator_version",
            "1.0.0",
        )
    )

    if (
        cross_sell_events[
            "generator_version"
        ]
        .astype(str)
        !=
        expected_generator_version
    ).any():

        raise ValueError(
            "Unexpected cross-sell generator_version"
        )

    forbidden_columns = {
        "cross_sell_score",

        "cross_sell_probability",
        "cross_sell_eligible",

        "eligibility_score",
        "eligibility_probability",

        "recommendation_score",
        "recommendation_probability",

        "acceptance_probability",

        "product_fit_score",

        "risk_score",
        "risk_band",

        "confidence",
        "confidence_score",

        "true_best_product",
        "true_cross_sell_product",
    }

    leaked = (
        forbidden_columns
        &
        set(
            cross_sell_events.columns
        )
    )

    if leaked:

        raise ValueError(
            "Hidden recommendation truth leaked into "
            "cross-sell events: "
            +
            ", ".join(
                sorted(
                    leaked
                )
            )
        )


def generate_cross_sell_master(
    finance_customers: pd.DataFrame,
    loan_accounts: pd.DataFrame,
    payment_history: pd.DataFrame,
    finance_products: pd.DataFrame,
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

    return generate_cross_sell_events(
        finance_customers=
            finance_customers,

        loan_accounts=
            loan_accounts,

        payment_history=
            payment_history,

        finance_products=
            finance_products,

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

    from data.generators.finance.payments import (
        generate_payment_master,
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

    payment_history_df = (
        generate_payment_master(
            finance_customers=
                finance_customers_df,

            loan_accounts=
                loan_accounts_df,
        )
    )

    cross_sell_events_df = (
        generate_cross_sell_master(
            finance_customers=
                finance_customers_df,

            loan_accounts=
                loan_accounts_df,

            payment_history=
                payment_history_df,

            finance_products=
                finance_products_df,
        )
    )

    print(
        "\n=== FINANCE CROSS-SELL SAMPLE ===\n"
    )

    print(
        cross_sell_events_df[
            [
                "cross_sell_event_id",

                "finance_customer_id",

                "source_product_code",

                "offered_product_code",
                "offered_product_name",

                "offered_at",

                "offer_channel",

                "offer_amount_inr",
                "offer_interest_rate_pct",
                "offer_tenure_months",
                "estimated_offer_emi_inr",

                "customer_response",
                "responded_at",
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
        "\n=== CROSS-SELL OFFERS BY PRODUCT ===\n"
    )

    print(
        cross_sell_events_df
        .groupby(
            [
                "offered_product_code",
                "offered_product_name",
            ]
        )
        .size()
        .reset_index(
            name=
                "offer_count"
        )
        .sort_values(
            "offer_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== SOURCE PRODUCT -> OFFER PRODUCT ===\n"
    )

    print(
        cross_sell_events_df
        .groupby(
            [
                "source_product_code",
                "offered_product_code",
            ]
        )
        .size()
        .reset_index(
            name=
                "event_count"
        )
        .sort_values(
            "event_count",
            ascending=False,
        )
        .head(
            30
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== CROSS-SELL CHANNEL MIX ===\n"
    )

    channel_counts = (
        cross_sell_events_df[
            "offer_channel"
        ]
        .value_counts()
        .rename_axis(
            "offer_channel"
        )
        .reset_index(
            name=
                "event_count"
        )
    )

    channel_counts[
        "rate"
    ] = (
        channel_counts[
            "event_count"
        ]
        /
        len(
            cross_sell_events_df
        )
    ).round(
        4
    )

    print(
        channel_counts
        .to_string(
            index=False
        )
    )

    print(
        "\n=== CROSS-SELL CUSTOMER RESPONSE ===\n"
    )

    response_counts = (
        cross_sell_events_df[
            "customer_response"
        ]
        .value_counts()
        .rename_axis(
            "customer_response"
        )
        .reset_index(
            name=
                "event_count"
        )
    )

    response_counts[
        "rate"
    ] = (
        response_counts[
            "event_count"
        ]
        /
        len(
            cross_sell_events_df
        )
    ).round(
        4
    )

    print(
        response_counts
        .to_string(
            index=False
        )
    )

    print(
        "\n=== CROSS-SELL EVENTS BY REGION ===\n"
    )

    print(
        cross_sell_events_df
        .groupby(
            "region_name"
        )
        .size()
        .reset_index(
            name=
                "event_count"
        )
        .sort_values(
            "event_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== CROSS-SELL OFFER SUMMARY ===\n"
    )

    print(
        cross_sell_events_df[
            [
                "offer_amount_inr",
                "offer_interest_rate_pct",
                "offer_tenure_months",
                "estimated_offer_emi_inr",
            ]
        ]
        .describe()
        .round(
            2
        )
        .to_string()
    )

    print(
        "\n=== FINANCE CROSS-SELL VALIDATION ===\n"
    )

    print(
        "Rows:",
        len(
            cross_sell_events_df
        ),
    )

    print(
        "Unique event IDs:",
        cross_sell_events_df[
            "cross_sell_event_id"
        ].nunique(),
    )

    print(
        "Unique customers:",
        cross_sell_events_df[
            "finance_customer_id"
        ].nunique(),
    )

    print(
        "Products offered:",
        cross_sell_events_df[
            "offered_finance_product_id"
        ].nunique(),
    )

    print(
        "Duplicate event IDs:",
        int(
            cross_sell_events_df[
                "cross_sell_event_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Duplicate customers:",
        int(
            cross_sell_events_df[
                "finance_customer_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    same_product = (
        cross_sell_events_df[
            "source_product_code"
        ]
        ==
        cross_sell_events_df[
            "offered_product_code"
        ]
    )

    print(
        "Same source/offered product rows:",
        int(
            same_product.sum()
        ),
    )

    forbidden_columns = {
        "cross_sell_score",

        "cross_sell_probability",
        "cross_sell_eligible",

        "eligibility_score",

        "recommendation_score",

        "acceptance_probability",

        "risk_score",

        "true_best_product",
    }

    leaked_columns = sorted(
        forbidden_columns
        &
        set(
            cross_sell_events_df.columns
        )
    )

    print(
        "Hidden truth leakage:",
        leaked_columns,
    )

    print(
        "\nGenerated "
        f"{len(cross_sell_events_df)} "
        "Finance cross-sell events successfully."
    )