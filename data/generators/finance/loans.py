"""
Synthetic Finance Loan Account Generator
for Mahindra AI Nexus.

Generates finance loan accounts from:

    Finance Customer
        +
    Canonical Finance Product Master
        ↓
    Loan Account

Later:

    loans.py
        ↓
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

This generator creates LOAN ORIGINATION / ACCOUNT TERMS only.

It DOES NOT generate:

    payment status
    repayment quality
    DPD
    delinquency
    missed-payment outcome
    default
    collections outcome
    cross-sell outcome
    risk score

Those must emerge later from payment history.


============================================================
IMPORTANT FIX IN THIS VERSION
============================================================

Loan allocation is DYNAMIC.

The previous implementation allocated:

    customer -> number of loans

before generating the actual EMI burden of those loans.

That could produce:

    customer can afford loan #1
        ↓
    customer is pre-allocated loan #2
        ↓
    loan #1 EMI increases obligations
        ↓
    customer can no longer afford any compatible product
        ↓
    ValueError

This version instead:

    choose borrower
        ↓
    choose disbursement date
        ↓
    calculate CURRENT concurrent EMI burden
        ↓
    find actually affordable product/tenure/principal
        ↓
    create account
        ↓
    update borrower state
        ↓
    only then consider another account

Unaffordable repeat-loan attempts are reallocated to another
eligible customer.

The configured total remains exactly:

    5000 loan accounts


============================================================
FINANCE PRODUCT SOURCE OF TRUTH
============================================================

Canonical source:

    data/generators/master/finance_products.py

Free-text product names in generation.yaml are NOT used for
foreign-key joins.


============================================================
OUTPUT
============================================================

This module DOES NOT write CSV files.

Later generate_all.py will write:

    data/synthetic/finance/loans.csv
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


# ============================================================
# SYNTHETIC ENGINEERING ASSUMPTIONS
#
# NOT actual Mahindra Finance commercial policy.
# ============================================================


MAX_LOANS_PER_CUSTOMER = 4

MAX_TOTAL_DEBT_SERVICE_RATIO = 0.75

MIN_REPEAT_LOAN_GAP_DAYS = 30

MAX_REPEAT_DATE_ATTEMPTS = 10

MAX_GLOBAL_GENERATION_ATTEMPTS = 250000


# ============================================================
# RATE MARGIN BY CUSTOMER INCOME STABILITY
# ============================================================


RATE_MARGIN_BY_INCOME_STABILITY: dict[str, float] = {
    "LOW": 1.50,
    "MEDIUM": 0.85,
    "MEDIUM_HIGH": 0.35,
    "HIGH": 0.00,
}


# ============================================================
# CUSTOMER SEGMENT -> PRODUCT TARGET SEGMENT
# ============================================================


PRODUCT_TARGET_WEIGHTS_BY_CUSTOMER_SEGMENT: dict[
    str,
    dict[str, float],
] = {

    "RETAIL_CONSUMER": {
        "RETAIL_AUTO": 0.58,
        "RETAIL_CONSUMER": 0.42,
    },

    "RURAL_AGRI": {
        "RURAL_AGRI": 0.65,
        "RETAIL_AUTO": 0.20,
        "RETAIL_CONSUMER": 0.15,
    },

    "SME": {
        "SME": 0.60,
        "COMMERCIAL_OPERATOR": 0.20,
        "RETAIL_AUTO": 0.20,
    },

    "COMMERCIAL_OPERATOR": {
        "COMMERCIAL_OPERATOR": 0.60,
        "SME": 0.20,
        "RETAIL_AUTO": 0.20,
    },

    "RURAL_SELF_EMPLOYED": {
        "RURAL_AGRI": 0.35,
        "RETAIL_AUTO": 0.35,
        "RETAIL_CONSUMER": 0.15,
        "SME": 0.15,
    },
}


# ============================================================
# SECONDARY PRODUCT PREFERENCE
# ============================================================


PRODUCT_CODE_PREFERENCE: dict[str, float] = {
    "AUTO_LOAN_NEW": 1.00,
    "AUTO_LOAN_USED": 0.70,
    "TRACTOR_LOAN": 1.00,
    "CV_LOAN": 1.00,
    "SME_LOAN": 1.00,
    "PERSONAL_LOAN": 1.00,
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
    "obligation_to_income_ratio",

    "customer_since",

    "active",

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


# ============================================================
# BASIC HELPERS
# ============================================================


def _as_positive_int(
    value: Any,
    name: str,
) -> int:

    if isinstance(value, bool):
        raise TypeError(
            f"{name} must be an integer, not bool"
        )

    try:
        parsed = int(value)

    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"{name} must be an integer"
        ) from exc

    if parsed <= 0:
        raise ValueError(
            f"{name} must be > 0"
        )

    return parsed


def _as_float(
    value: Any,
    name: str,
) -> float:

    if isinstance(value, bool):
        raise TypeError(
            f"{name} must be numeric"
        )

    try:
        return float(value)

    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"{name} must be numeric"
        ) from exc


# ============================================================
# INPUT VALIDATION
# ============================================================


def _validate_inputs(
    finance_customers: pd.DataFrame,
    finance_products: pd.DataFrame,
) -> None:

    if finance_customers.empty:
        raise ValueError(
            "finance_customers cannot be empty"
        )

    if finance_products.empty:
        raise ValueError(
            "finance_products cannot be empty"
        )

    missing_customer_columns = (
        FINANCE_CUSTOMER_REQUIRED_COLUMNS
        -
        set(finance_customers.columns)
    )

    if missing_customer_columns:
        raise ValueError(
            "finance_customers missing columns: "
            +
            ", ".join(
                sorted(missing_customer_columns)
            )
        )

    missing_product_columns = (
        FINANCE_PRODUCT_REQUIRED_COLUMNS
        -
        set(finance_products.columns)
    )

    if missing_product_columns:
        raise ValueError(
            "finance_products missing columns: "
            +
            ", ".join(
                sorted(missing_product_columns)
            )
        )

    if finance_customers[
        "finance_customer_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate finance_customer_id values found"
        )

    if finance_products[
        "finance_product_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate finance_product_id values found"
        )


# ============================================================
# GENERATION END
# ============================================================


def _generation_end_timestamp(
    generation: Mapping[str, Any],
) -> pd.Timestamp:

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
            "Missing generation.time.end_date/timezone"
        ) from exc

    timestamp = pd.Timestamp(end_date)

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
# EMI
# ============================================================


def calculate_emi(
    principal_inr: float,
    annual_interest_rate_pct: float,
    tenure_months: int,
) -> float:

    principal = float(principal_inr)
    annual_rate = float(
        annual_interest_rate_pct
    )
    tenure = int(tenure_months)

    if principal <= 0:
        raise ValueError(
            "principal must be > 0"
        )

    if annual_rate <= 0:
        raise ValueError(
            "annual interest rate must be > 0"
        )

    if tenure <= 0:
        raise ValueError(
            "tenure must be > 0"
        )

    monthly_rate = (
        annual_rate
        /
        12.0
        /
        100.0
    )

    factor = (
        1.0
        +
        monthly_rate
    ) ** tenure

    return float(
        principal
        *
        monthly_rate
        *
        factor
        /
        (
            factor
            -
            1.0
        )
    )


# ============================================================
# REVERSE EMI
# ============================================================


def _principal_for_emi(
    maximum_emi: float,
    annual_interest_rate_pct: float,
    tenure_months: int,
) -> float:

    maximum_emi = float(maximum_emi)

    if maximum_emi <= 0:
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

    tenure = int(tenure_months)

    if tenure <= 0:
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

    return float(
        max(
            maximum_emi
            *
            (
                factor
                -
                1.0
            )
            /
            denominator,
            0.0,
        )
    )


# ============================================================
# FINANCE TENURE DISTRIBUTION
# ============================================================


def _get_tenure_distribution(
    distributions: Mapping[str, Any],
) -> tuple[
    list[int],
    list[float],
]:

    try:

        tenure_config = (
            distributions[
                "finance"
            ][
                "tenure_months"
            ]
        )

        values = [
            int(value)
            for value
            in tenure_config[
                "values"
            ]
        ]

        weights = [
            float(weight)
            for weight
            in tenure_config[
                "weights"
            ]
        ]

    except KeyError as exc:

        raise KeyError(
            "Missing distributions.finance."
            "tenure_months.values/weights"
        ) from exc

    if len(values) != len(weights):
        raise ValueError(
            "Finance tenure values and weights "
            "must have same length"
        )

    if not values:
        raise ValueError(
            "Finance tenure values cannot be empty"
        )

    if any(
        value <= 0
        for value in values
    ):
        raise ValueError(
            "Finance tenure values must be > 0"
        )

    total = float(sum(weights))

    if total <= 0:
        raise ValueError(
            "Finance tenure weights must sum to > 0"
        )

    probabilities = [
        weight / total
        for weight in weights
    ]

    return values, probabilities


# ============================================================
# PRODUCT TENURE FILTER
# ============================================================


def _valid_product_tenures(
    product: Mapping[str, Any],
    tenure_values: list[int],
    tenure_weights: list[float],
) -> tuple[
    list[int],
    list[float],
]:

    minimum = int(
        product[
            "min_tenure_months"
        ]
    )

    maximum = int(
        product[
            "max_tenure_months"
        ]
    )

    values: list[int] = []
    weights: list[float] = []

    for value, weight in zip(
        tenure_values,
        tenure_weights,
    ):

        if minimum <= value <= maximum:
            values.append(value)
            weights.append(weight)

    if not values:

        values = [maximum]
        weights = [1.0]

    total = float(sum(weights))

    probabilities = [
        weight / total
        for weight in weights
    ]

    return values, probabilities


# ============================================================
# PRODUCT COMPATIBILITY
# ============================================================


def _product_compatibility_weight(
    customer_segment: str,
    product: Mapping[str, Any],
) -> float:

    target_weights = (
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

    base_weight = float(
        target_weights.get(
            target_segment,
            0.0,
        )
    )

    if base_weight <= 0:
        return 0.0

    product_code = str(
        product[
            "product_code"
        ]
    )

    preference = float(
        PRODUCT_CODE_PREFERENCE.get(
            product_code,
            1.0,
        )
    )

    return base_weight * preference


# ============================================================
# INTEREST RATE
# ============================================================


def _derive_interest_rate(
    rng: np.random.Generator,
    product: Mapping[str, Any],
    income_stability: str,
    current_obligation_ratio: float,
) -> float:

    base_rate = float(
        product[
            "base_interest_rate_pct"
        ]
    )

    if (
        income_stability
        not in
        RATE_MARGIN_BY_INCOME_STABILITY
    ):
        raise ValueError(
            "Unknown income stability: "
            f"{income_stability}"
        )

    stability_margin = (
        RATE_MARGIN_BY_INCOME_STABILITY[
            income_stability
        ]
    )

    burden_margin = float(
        np.clip(
            (
                current_obligation_ratio
                -
                0.20
            )
            *
            2.5,
            0.0,
            1.25,
        )
    )

    random_margin = float(
        rng.normal(
            loc=0.0,
            scale=0.25,
        )
    )

    rate = (
        base_rate
        +
        stability_margin
        +
        burden_margin
        +
        random_margin
    )

    rate = float(
        np.clip(
            rate,
            base_rate - 0.40,
            base_rate + 4.00,
        )
    )

    return round(
        rate,
        3,
    )


# ============================================================
# PRINCIPAL CONFIG
# ============================================================


def _parse_principal_config(
    distributions: Mapping[str, Any],
) -> dict[str, float]:

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

    distribution_name = str(
        config.get(
            "distribution",
            ""
        )
    ).lower()

    if distribution_name != "lognormal":
        raise ValueError(
            "finance.loan_principal requires "
            "distribution='lognormal'"
        )

    result = {
        "mean": _as_float(
            config[
                "mean"
            ],
            "finance.loan_principal.mean",
        ),

        "sigma": _as_float(
            config[
                "sigma"
            ],
            "finance.loan_principal.sigma",
        ),

        "min": _as_float(
            config[
                "min"
            ],
            "finance.loan_principal.min",
        ),

        "max": _as_float(
            config[
                "max"
            ],
            "finance.loan_principal.max",
        ),
    }

    if result["sigma"] <= 0:
        raise ValueError(
            "finance.loan_principal.sigma must be > 0"
        )

    if result["min"] <= 0:
        raise ValueError(
            "finance.loan_principal.min must be > 0"
        )

    if result["max"] < result["min"]:
        raise ValueError(
            "finance.loan_principal.max must be >= min"
        )

    return result


# ============================================================
# BUILD ACTUALLY FEASIBLE PRODUCT OPTIONS
# ============================================================


def _build_feasible_product_options(
    rng: np.random.Generator,
    customer: Mapping[str, Any],
    finance_products: pd.DataFrame,
    current_monthly_obligations: float,
    tenure_values: list[int],
    tenure_weights: list[float],
    principal_config: Mapping[str, float],
) -> list[dict[str, Any]]:
    """
    Build only products/tenures that are affordable using the
    customer's CURRENT obligations.

    This is the central fix for repeat-loan generation.
    """

    monthly_income = float(
        customer[
            "monthly_income_inr"
        ]
    )

    if monthly_income <= 0:
        return []

    maximum_total_debt_service = (
        monthly_income
        *
        MAX_TOTAL_DEBT_SERVICE_RATIO
    )

    maximum_new_emi = (
        maximum_total_debt_service
        -
        current_monthly_obligations
    )

    if maximum_new_emi <= 0:
        return []

    current_obligation_ratio = (
        current_monthly_obligations
        /
        monthly_income
    )

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

    options: list[
        dict[str, Any]
    ] = []

    active_products = (
        finance_products[
            finance_products[
                "active"
            ].astype(bool)
        ]
    )

    for product in active_products.to_dict(
        orient="records"
    ):

        compatibility_weight = (
            _product_compatibility_weight(
                customer_segment,
                product,
            )
        )

        if compatibility_weight <= 0:
            continue

        rate = _derive_interest_rate(
            rng=rng,
            product=product,
            income_stability=
                income_stability,
            current_obligation_ratio=
                current_obligation_ratio,
        )

        (
            valid_tenures,
            valid_weights,
        ) = _valid_product_tenures(
            product=product,
            tenure_values=
                tenure_values,
            tenure_weights=
                tenure_weights,
        )

        feasible_tenures: list[int] = []
        feasible_tenure_weights: list[float] = []
        maximum_principal_by_tenure: list[
            float
        ] = []

        product_minimum = max(
            float(
                product[
                    "min_loan_amount_inr"
                ]
            ),
            float(
                principal_config[
                    "min"
                ]
            ),
        )

        product_limit = min(
            float(
                product[
                    "max_loan_amount_inr"
                ]
            ),
            float(
                principal_config[
                    "max"
                ]
            ),
        )

        for tenure, weight in zip(
            valid_tenures,
            valid_weights,
        ):

            affordable_principal = (
                _principal_for_emi(
                    maximum_emi=
                        maximum_new_emi,

                    annual_interest_rate_pct=
                        rate,

                    tenure_months=
                        tenure,
                )
            )

            effective_maximum = min(
                product_limit,
                affordable_principal,
            )

            if (
                effective_maximum
                +
                1e-6
                >=
                product_minimum
            ):

                feasible_tenures.append(
                    tenure
                )

                feasible_tenure_weights.append(
                    weight
                )

                maximum_principal_by_tenure.append(
                    effective_maximum
                )

        if not feasible_tenures:
            continue

        tenure_weight_total = float(
            sum(
                feasible_tenure_weights
            )
        )

        feasible_tenure_weights = [
            weight / tenure_weight_total
            for weight
            in feasible_tenure_weights
        ]

        options.append(
            {
                "product": product,

                "compatibility_weight":
                    compatibility_weight,

                "interest_rate_pct":
                    rate,

                "minimum_principal":
                    product_minimum,

                "feasible_tenures":
                    feasible_tenures,

                "feasible_tenure_weights":
                    feasible_tenure_weights,

                "maximum_principal_by_tenure":
                    maximum_principal_by_tenure,
            }
        )

    return options


# ============================================================
# SELECT PRODUCT AND TERMS
# ============================================================


def _select_product_and_terms(
    rng: np.random.Generator,
    customer: Mapping[str, Any],
    finance_products: pd.DataFrame,
    current_monthly_obligations: float,
    tenure_values: list[int],
    tenure_weights: list[float],
    principal_config: Mapping[str, float],
) -> dict[str, Any] | None:
    """
    Return feasible loan terms.

    Returns None when the customer genuinely cannot afford an
    additional compatible loan.

    This is NOT considered a generation error.
    """

    options = _build_feasible_product_options(
        rng=rng,
        customer=customer,
        finance_products=
            finance_products,
        current_monthly_obligations=
            current_monthly_obligations,
        tenure_values=
            tenure_values,
        tenure_weights=
            tenure_weights,
        principal_config=
            principal_config,
    )

    if not options:
        return None

    product_weights = np.asarray(
        [
            float(
                option[
                    "compatibility_weight"
                ]
            )
            for option in options
        ],
        dtype=float,
    )

    product_weights = (
        product_weights
        /
        product_weights.sum()
    )

    option_index = int(
        rng.choice(
            np.arange(
                len(options)
            ),
            p=product_weights,
        )
    )

    option = options[
        option_index
    ]

    feasible_tenures = option[
        "feasible_tenures"
    ]

    feasible_weights = option[
        "feasible_tenure_weights"
    ]

    tenure_position = int(
        rng.choice(
            np.arange(
                len(
                    feasible_tenures
                )
            ),
            p=np.asarray(
                feasible_weights,
                dtype=float,
            ),
        )
    )

    tenure_months = int(
        feasible_tenures[
            tenure_position
        ]
    )

    maximum_principal = float(
        option[
            "maximum_principal_by_tenure"
        ][
            tenure_position
        ]
    )

    minimum_principal = float(
        option[
            "minimum_principal"
        ]
    )

    raw_principal = float(
        rng.lognormal(
            mean=float(
                principal_config[
                    "mean"
                ]
            ),
            sigma=float(
                principal_config[
                    "sigma"
                ]
            ),
        )
    )

    principal = float(
        np.clip(
            raw_principal,
            minimum_principal,
            maximum_principal,
        )
    )

    principal = round(
        principal
        /
        1000.0
    ) * 1000.0

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

    monthly_income = float(
        customer[
            "monthly_income_inr"
        ]
    )

    resulting_dsr = (
        current_monthly_obligations
        +
        emi
    ) / monthly_income

    if (
        resulting_dsr
        >
        MAX_TOTAL_DEBT_SERVICE_RATIO
        +
        0.0001
    ):

        return None

    return {
        "product":
            option[
                "product"
            ],

        "principal_inr":
            principal,

        "interest_rate_pct":
            interest_rate,

        "tenure_months":
            tenure_months,

        "emi_amount_inr":
            emi,

        "resulting_dsr":
            resulting_dsr,
    }


# ============================================================
# SECURITY / LTV
# ============================================================


def _generate_security_values(
    rng: np.random.Generator,
    product: Mapping[str, Any],
    principal_inr: float,
) -> tuple[
    float | None,
    float | None,
]:

    secured = bool(
        product[
            "secured"
        ]
    )

    if not secured:
        return None, None

    max_ltv = product[
        "max_ltv_pct"
    ]

    if pd.isna(max_ltv):
        raise ValueError(
            "Secured Finance product missing max_ltv_pct"
        )

    maximum = float(max_ltv)

    minimum = max(
        45.0,
        maximum - 25.0,
    )

    beta_draw = float(
        rng.beta(
            5.0,
            2.2,
        )
    )

    ltv = (
        minimum
        +
        beta_draw
        *
        (
            maximum
            -
            minimum
        )
    )

    ltv = float(
        np.clip(
            ltv,
            minimum,
            maximum,
        )
    )

    asset_value = (
        float(
            principal_inr
        )
        /
        (
            ltv / 100.0
        )
    )

    return (
        round(
            asset_value,
            2,
        ),

        round(
            ltv,
            3,
        ),
    )


# ============================================================
# RANDOM TIMESTAMP BETWEEN TWO DATES
# ============================================================


def _sample_timestamp_between(
    rng: np.random.Generator,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Timestamp | None:

    if end <= start:
        return None

    seconds = (
        end - start
    ).total_seconds()

    offset = float(
        rng.uniform(
            0.0,
            seconds,
        )
    )

    return (
        start
        +
        pd.to_timedelta(
            offset,
            unit="s",
        )
    )


# ============================================================
# CONCURRENT GENERATED EMI
# ============================================================


def _concurrent_generated_emi(
    previous_accounts: list[
        dict[str, Any]
    ],
    disbursement_at: pd.Timestamp,
) -> float:

    return float(
        sum(
            float(
                account[
                    "emi_amount_inr"
                ]
            )

            for account
            in previous_accounts

            if (
                pd.to_datetime(
                    account[
                        "scheduled_maturity_at"
                    ],
                    utc=True,
                )
                >
                pd.to_datetime(
                    disbursement_at,
                    utc=True,
                )
            )
        )
    )


# ============================================================
# BORROWER WEIGHT FOR REPEAT LOANS
# ============================================================


def _repeat_borrower_weight(
    customer: Mapping[str, Any],
    existing_loan_count: int,
    generation_end: pd.Timestamp,
) -> float:

    customer_since = pd.to_datetime(
        customer[
            "customer_since"
        ],
        utc=True,
    )

    generation_end_utc = pd.to_datetime(
        generation_end,
        utc=True,
    )

    relationship_age_days = max(
        (
            generation_end_utc
            -
            customer_since
        ).days,
        1,
    )

    relationship_factor = (
        1.0
        +
        min(
            relationship_age_days
            /
            365.0,
            2.0,
        )
    )

    repeat_penalty = (
        1.0
        /
        max(
            existing_loan_count,
            1,
        )
    )

    income = float(
        customer[
            "monthly_income_inr"
        ]
    )

    obligations = float(
        customer[
            "monthly_obligations_inr"
        ]
    )

    disposable_ratio = max(
        (
            income
            -
            obligations
        )
        /
        income,
        0.05,
    )

    return float(
        relationship_factor
        *
        repeat_penalty
        *
        disposable_ratio
    )


# ============================================================
# CREATE ONE LOAN ATTEMPT
# ============================================================


def _try_create_loan(
    rng: np.random.Generator,
    customer: Mapping[str, Any],
    finance_products: pd.DataFrame,
    previous_accounts: list[
        dict[str, Any]
    ],
    latest_disbursement: pd.Timestamp,
    tenure_values: list[int],
    tenure_weights: list[float],
    principal_config: Mapping[str, float],
    loan_account_id: str,
    sequence_number: int,
    data_origin: str,
    generator_version: str,
) -> dict[str, Any] | None:
    """
    Try to create one additional account.

    Several possible future disbursement timestamps are tried.

    If none allow an affordable loan, returns None and the loan
    slot can be reassigned to another customer.
    """

    customer_since = pd.to_datetime(
        customer[
            "customer_since"
        ],
        utc=True,
    )

    latest_disbursement = pd.to_datetime(
        latest_disbursement,
        utc=True,
    )

    earliest = (
        customer_since
        +
        timedelta(
            days=7
        )
    )

    if previous_accounts:

        previous_last_disbursement = max(
            pd.to_datetime(
                account[
                    "disbursed_at"
                ],
                utc=True,
            )
            for account
            in previous_accounts
        )

        earliest = max(
            earliest,
            previous_last_disbursement
            +
            timedelta(
                days=
                    MIN_REPEAT_LOAN_GAP_DAYS
            ),
        )

    if earliest >= latest_disbursement:
        return None

    # --------------------------------------------------------
    # Try several random dates plus a late date.
    #
    # A later date may allow an earlier loan to mature,
    # reducing concurrent EMI burden.
    # --------------------------------------------------------

    candidate_dates: list[
        pd.Timestamp
    ] = []

    for _ in range(
        MAX_REPEAT_DATE_ATTEMPTS
    ):

        candidate = (
            _sample_timestamp_between(
                rng=rng,
                start=earliest,
                end=
                    latest_disbursement,
            )
        )

        if candidate is not None:
            candidate_dates.append(
                candidate
            )

    near_latest = (
        latest_disbursement
        -
        timedelta(
            minutes=1
        )
    )

    if near_latest > earliest:
        candidate_dates.append(
            near_latest
        )

    candidate_dates = sorted(
        candidate_dates
    )

    external_obligations = float(
        customer[
            "monthly_obligations_inr"
        ]
    )

    for disbursed_at in candidate_dates:

        concurrent_emi = (
            _concurrent_generated_emi(
                previous_accounts=
                    previous_accounts,

                disbursement_at=
                    disbursed_at,
            )
        )

        current_obligations = (
            external_obligations
            +
            concurrent_emi
        )

        selected = (
            _select_product_and_terms(
                rng=rng,
                customer=customer,
                finance_products=
                    finance_products,
                current_monthly_obligations=
                    current_obligations,
                tenure_values=
                    tenure_values,
                tenure_weights=
                    tenure_weights,
                principal_config=
                    principal_config,
            )
        )

        if selected is None:
            continue

        product = (
            selected[
                "product"
            ]
        )

        principal = float(
            selected[
                "principal_inr"
            ]
        )

        rate = float(
            selected[
                "interest_rate_pct"
            ]
        )

        tenure_months = int(
            selected[
                "tenure_months"
            ]
        )

        emi = float(
            selected[
                "emi_amount_inr"
            ]
        )

        dsr = float(
            selected[
                "resulting_dsr"
            ]
        )

        application_lead_days = int(
            rng.integers(
                1,
                11,
            )
        )

        application_at = (
            disbursed_at
            -
            timedelta(
                days=
                    application_lead_days
            )
        )

        if application_at < customer_since:
            application_at = customer_since

        scheduled_maturity_at = pd.Timestamp(
            disbursed_at.to_pydatetime(
                warn=False
            )
            +
            relativedelta(
                months=
                    tenure_months
            )
        )

        (
            asset_value,
            ltv_pct,
        ) = _generate_security_values(
            rng=rng,
            product=product,
            principal_inr=
                principal,
        )

        return {
            "loan_account_id":
                loan_account_id,

            "finance_customer_id":
                str(
                    customer[
                        "finance_customer_id"
                    ]
                ),

            "customer_loan_sequence":
                sequence_number,

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

            "finance_product_id":
                str(
                    product[
                        "finance_product_id"
                    ]
                ),

            "product_code":
                str(
                    product[
                        "product_code"
                    ]
                ),

            "product_name":
                str(
                    product[
                        "product_name"
                    ]
                ),

            "product_category":
                str(
                    product[
                        "product_category"
                    ]
                ),

            "target_segment":
                str(
                    product[
                        "target_segment"
                    ]
                ),

            "secured":
                bool(
                    product[
                        "secured"
                    ]
                ),

            "application_at":
                application_at,

            "disbursed_at":
                disbursed_at,

            "scheduled_maturity_at":
                scheduled_maturity_at,

            "principal_inr":
                round(
                    principal,
                    2,
                ),

            "interest_rate_pct":
                round(
                    rate,
                    3,
                ),

            "tenure_months":
                tenure_months,

            "emi_amount_inr":
                round(
                    emi,
                    2,
                ),

            "asset_value_inr":
                asset_value,

            "ltv_pct":
                ltv_pct,

            "debt_service_ratio_at_origination":
                round(
                    dsr,
                    4,
                ),

            "data_origin":
                data_origin,

            "generator_version":
                generator_version,
        }

    return None


# ============================================================
# GENERATE LOAN ACCOUNTS
# ============================================================


def generate_loan_accounts(
    finance_customers: pd.DataFrame,
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
        finance_products=
            finance_products,
    )

    # ========================================================
    # CONFIG
    # ========================================================

    try:

        target_loan_count = (
            _as_positive_int(
                generation[
                    "finance"
                ][
                    "loan_accounts"
                ][
                    "count"
                ],
                (
                    "generation.finance."
                    "loan_accounts.count"
                ),
            )
        )

        minimum_history_months = (
            _as_positive_int(
                generation[
                    "finance"
                ][
                    "payment_history_months"
                ][
                    "min"
                ],
                (
                    "generation.finance."
                    "payment_history_months.min"
                ),
            )
        )

    except KeyError as exc:

        raise KeyError(
            "Missing Finance loan configuration"
        ) from exc

    generation_end = (
        _generation_end_timestamp(
            generation
        )
    )

    latest_disbursement = (
        generation_end
        -
        pd.DateOffset(
            months=
                minimum_history_months
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
            "finance.loans",
        )
    )

    # ========================================================
    # CONFIGURED DISTRIBUTIONS
    # ========================================================

    (
        tenure_values,
        tenure_weights,
    ) = _get_tenure_distribution(
        distributions
    )

    principal_config = (
        _parse_principal_config(
            distributions
        )
    )

    # ========================================================
    # PREPARE CUSTOMER TABLE
    # ========================================================

    customers = (
        finance_customers
        .copy(
            deep=True
        )
    )

    customers[
        "customer_since"
    ] = pd.to_datetime(
        customers[
            "customer_since"
        ],
        utc=True,
    )

    latest_disbursement = pd.to_datetime(
        latest_disbursement,
        utc=True,
    )

    generation_end = pd.to_datetime(
        generation_end,
        utc=True,
    )

    relationship_cutoff = (
        latest_disbursement
        -
        timedelta(
            days=7
        )
    )

    eligible_customers = (
        customers[
            (
                customers[
                    "active"
                ].astype(bool)
            )
            &
            (
                customers[
                    "customer_since"
                ]
                <
                relationship_cutoff
            )
        ]
        .copy()
        .reset_index(
            drop=True
        )
    )

    if eligible_customers.empty:
        raise ValueError(
            "No Finance customers have enough history "
            "for loan generation"
        )

    # ========================================================
    # CUSTOMER STATE
    # ========================================================

    customer_lookup: dict[
        str,
        dict[str, Any],
    ] = {
        str(
            customer[
                "finance_customer_id"
            ]
        ):
            customer

        for customer
        in eligible_customers.to_dict(
            orient="records"
        )
    }

    account_state: dict[
        str,
        list[
            dict[str, Any]
        ],
    ] = {
        customer_id: []
        for customer_id
        in customer_lookup
    }

    blocked_for_repeat: set[str] = set()

    # ========================================================
    # STATIC REPEAT-BORROWER WEIGHT CACHE
    #
    # _repeat_borrower_weight() can be decomposed as:
    #
    #     static_customer_weight
    #     /
    #     existing_loan_count
    #
    # The static component depends only on:
    #
    #     relationship age
    #     income
    #     external obligations
    #
    # Those values do not change during this generation run.
    #
    # Caching therefore preserves the exact weighting formula
    # while avoiding millions of repeated timestamp and ratio
    # calculations during PASS 2.
    # ========================================================

    repeat_weight_base: dict[
        str,
        float,
    ] = {
        customer_id:
            _repeat_borrower_weight(
                customer=
                    customer,

                existing_loan_count=
                    1,

                generation_end=
                    generation_end,
            )

        for customer_id, customer
        in customer_lookup.items()
    }

    rows: list[
        dict[str, Any]
    ] = []

    loan_counter = 1

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
    # PASS 1
    #
    # Give as many different customers as possible one loan.
    #
    # Customers that truly cannot afford a canonical product
    # are skipped.
    # ========================================================

    customer_ids = list(
        customer_lookup.keys()
    )

    customer_ids = [
        str(value)
        for value
        in rng.permutation(
            customer_ids
        )
    ]

    for customer_id in customer_ids:

        if len(rows) >= target_loan_count:
            break

        customer = (
            customer_lookup[
                customer_id
            ]
        )

        loan_id = generate_id(
            "FINLOAN_SYN",
            loan_counter,
            width=7,
        )

        loan = _try_create_loan(
            rng=rng,
            customer=customer,
            finance_products=
                finance_products,
            previous_accounts=[],
            latest_disbursement=
                latest_disbursement,
            tenure_values=
                tenure_values,
            tenure_weights=
                tenure_weights,
            principal_config=
                principal_config,
            loan_account_id=
                loan_id,
            sequence_number=1,
            data_origin=
                data_origin,
            generator_version=
                generator_version,
        )

        if loan is None:
            blocked_for_repeat.add(
                customer_id
            )
            continue

        rows.append(
            loan
        )

        account_state[
            customer_id
        ].append(
            loan
        )

        loan_counter += 1

    if not rows:
        raise ValueError(
            "No affordable Finance loan could be generated"
        )

    # ========================================================
    # PASS 2
    #
    # Dynamically add repeat accounts until exactly 5000
    # accounts exist.
    #
    # Each attempt uses ACTUAL previous EMIs.
    # ========================================================

    attempts = 0

    while len(rows) < target_loan_count:

        attempts += 1

        if (
            attempts
            >
            MAX_GLOBAL_GENERATION_ATTEMPTS
        ):

            raise RuntimeError(
                "Unable to generate requested Finance "
                "loan count while preserving affordability. "
                f"Generated={len(rows)}, "
                f"requested={target_loan_count}, "
                f"eligible_customers="
                f"{len(customer_lookup)}, "
                f"blocked_customers="
                f"{len(blocked_for_repeat)}"
            )

        candidates: list[str] = []

        weights: list[float] = []

        for customer_id, customer in (
            customer_lookup.items()
        ):

            existing_accounts = (
                account_state[
                    customer_id
                ]
            )

            existing_count = len(
                existing_accounts
            )

            if existing_count == 0:
                continue

            if (
                existing_count
                >=
                MAX_LOANS_PER_CUSTOMER
            ):
                continue

            if (
                customer_id
                in
                blocked_for_repeat
            ):
                continue

            if existing_accounts:

                latest_existing_disbursement = max(
                    pd.to_datetime(
                        account[
                            "disbursed_at"
                        ],
                        utc=True,
                    )
                    for account
                    in existing_accounts
                )

                earliest_next = (
                    latest_existing_disbursement
                    +
                    timedelta(
                        days=
                            MIN_REPEAT_LOAN_GAP_DAYS
                    )
                )

                if (
                    earliest_next
                    >=
                    latest_disbursement
                ):
                    blocked_for_repeat.add(
                        customer_id
                    )
                    continue

            candidates.append(
                customer_id
            )

            weights.append(
                repeat_weight_base[
                    customer_id
                ]
                /
                float(
                    existing_count
                )
            )

        if not candidates:

            raise RuntimeError(
                "No Finance customers remain capable of "
                "receiving repeat accounts before reaching "
                f"the configured {target_loan_count} loans. "
                f"Generated={len(rows)}"
            )

        probabilities = np.asarray(
            weights,
            dtype=float,
        )

        probabilities = (
            probabilities
            /
            probabilities.sum()
        )

        selected_customer_id = str(
            rng.choice(
                candidates,
                p=probabilities,
            )
        )

        customer = (
            customer_lookup[
                selected_customer_id
            ]
        )

        previous_accounts = (
            account_state[
                selected_customer_id
            ]
        )

        sequence_number = (
            len(
                previous_accounts
            )
            +
            1
        )

        loan_id = generate_id(
            "FINLOAN_SYN",
            loan_counter,
            width=7,
        )

        loan = _try_create_loan(
            rng=rng,
            customer=customer,
            finance_products=
                finance_products,
            previous_accounts=
                previous_accounts,
            latest_disbursement=
                latest_disbursement,
            tenure_values=
                tenure_values,
            tenure_weights=
                tenure_weights,
            principal_config=
                principal_config,
            loan_account_id=
                loan_id,
            sequence_number=
                sequence_number,
            data_origin=
                data_origin,
            generator_version=
                generator_version,
        )

        if loan is None:

            blocked_for_repeat.add(
                selected_customer_id
            )

            continue

        rows.append(
            loan
        )

        account_state[
            selected_customer_id
        ].append(
            loan
        )

        loan_counter += 1

    # ========================================================
    # DATAFRAME
    # ========================================================

    loan_accounts = pd.DataFrame(
        rows,
        columns=[
            "loan_account_id",

            "finance_customer_id",
            "customer_loan_sequence",

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

            "application_at",
            "disbursed_at",
            "scheduled_maturity_at",

            "principal_inr",
            "interest_rate_pct",
            "tenure_months",
            "emi_amount_inr",

            "asset_value_inr",
            "ltv_pct",

            "debt_service_ratio_at_origination",

            "data_origin",
            "generator_version",
        ],
    )

    validate_loan_accounts(
        loan_accounts=
            loan_accounts,
        finance_customers=
            finance_customers,
        finance_products=
            finance_products,
        expected_count=
            target_loan_count,
        generation=
            generation,
    )

    return loan_accounts


# ============================================================
# VALIDATION
# ============================================================


def validate_loan_accounts(
    loan_accounts: pd.DataFrame,
    finance_customers: pd.DataFrame,
    finance_products: pd.DataFrame,
    expected_count: int | None = None,
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
) -> None:

    if generation is None:
        generation = (
            load_generation_config()
        )

    required_columns = {
        "loan_account_id",

        "finance_customer_id",
        "customer_loan_sequence",

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

        "application_at",
        "disbursed_at",
        "scheduled_maturity_at",

        "principal_inr",
        "interest_rate_pct",
        "tenure_months",
        "emi_amount_inr",

        "asset_value_inr",
        "ltv_pct",

        "debt_service_ratio_at_origination",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        -
        set(
            loan_accounts.columns
        )
    )

    if missing:
        raise ValueError(
            "Loan accounts missing required columns: "
            +
            ", ".join(
                sorted(missing)
            )
        )

    if loan_accounts.empty:
        raise ValueError(
            "Loan accounts cannot be empty"
        )

    if (
        expected_count is not None
        and
        len(loan_accounts)
        !=
        expected_count
    ):
        raise ValueError(
            f"Expected {expected_count} loan accounts, "
            f"generated {len(loan_accounts)}"
        )

    # ========================================================
    # UNIQUE IDS
    # ========================================================

    if loan_accounts[
        "loan_account_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate loan_account_id values found"
        )

    # ========================================================
    # CUSTOMER FK
    # ========================================================

    valid_customer_ids = set(
        finance_customers[
            "finance_customer_id"
        ].astype(str)
    )

    invalid_customer_ids = (
        set(
            loan_accounts[
                "finance_customer_id"
            ].astype(str)
        )
        -
        valid_customer_ids
    )

    if invalid_customer_ids:
        raise ValueError(
            "Loans reference invalid Finance customers"
        )

    # ========================================================
    # PRODUCT FK
    # ========================================================

    valid_product_ids = set(
        finance_products[
            "finance_product_id"
        ].astype(str)
    )

    invalid_product_ids = (
        set(
            loan_accounts[
                "finance_product_id"
            ].astype(str)
        )
        -
        valid_product_ids
    )

    if invalid_product_ids:
        raise ValueError(
            "Loans reference invalid Finance products"
        )

    customer_lookup = (
        finance_customers
        .set_index(
            "finance_customer_id"
        )
    )

    product_lookup = (
        finance_products
        .set_index(
            "finance_product_id"
        )
    )

    # ========================================================
    # TIMESTAMPS
    #
    # Normalize to UTC for validation comparisons.
    # This does not mutate the stored source DataFrame.
    # ========================================================

    application_at = pd.to_datetime(
        loan_accounts[
            "application_at"
        ],
        utc=True,
    )

    disbursed_at = pd.to_datetime(
        loan_accounts[
            "disbursed_at"
        ],
        utc=True,
    )

    maturity_at = pd.to_datetime(
        loan_accounts[
            "scheduled_maturity_at"
        ],
        utc=True,
    )

    if application_at.isna().any():
        raise ValueError(
            "Loans contains invalid application_at"
        )

    if disbursed_at.isna().any():
        raise ValueError(
            "Loans contains invalid disbursed_at"
        )

    if maturity_at.isna().any():
        raise ValueError(
            "Loans contains invalid scheduled_maturity_at"
        )

    if (
        application_at
        >
        disbursed_at
    ).any():

        raise ValueError(
            "application_at cannot be after disbursed_at"
        )

    if (
        maturity_at
        <=
        disbursed_at
    ).any():

        raise ValueError(
            "scheduled_maturity_at must be "
            "after disbursed_at"
        )

    # ========================================================
    # ROW-BY-ROW PRODUCT / EMI / LTV VALIDATION
    # ========================================================

    for loan in loan_accounts.itertuples(
        index=False
    ):

        customer = customer_lookup.loc[
            str(
                loan.finance_customer_id
            )
        ]

        product = product_lookup.loc[
            str(
                loan.finance_product_id
            )
        ]

        loan_application_at = pd.to_datetime(
            loan.application_at,
            utc=True,
        )

        customer_since = pd.to_datetime(
            customer[
                "customer_since"
            ],
            utc=True,
        )

        if (
            loan_application_at
            <
            customer_since
        ):
            raise ValueError(
                "Loan application precedes "
                "customer relationship"
            )

        if (
            str(
                loan.product_code
            )
            !=
            str(
                product[
                    "product_code"
                ]
            )
        ):
            raise ValueError(
                "Loan product_code does not match "
                "Finance Product master"
            )

        if (
            str(
                loan.product_name
            )
            !=
            str(
                product[
                    "product_name"
                ]
            )
        ):
            raise ValueError(
                "Loan product_name does not match "
                "Finance Product master"
            )

        if (
            str(
                loan.product_category
            )
            !=
            str(
                product[
                    "product_category"
                ]
            )
        ):
            raise ValueError(
                "Loan product_category does not match "
                "Finance Product master"
            )

        if (
            str(
                loan.target_segment
            )
            !=
            str(
                product[
                    "target_segment"
                ]
            )
        ):
            raise ValueError(
                "Loan target_segment does not match "
                "Finance Product master"
            )

        principal = float(
            loan.principal_inr
        )

        product_minimum = float(
            product[
                "min_loan_amount_inr"
            ]
        )

        product_maximum = float(
            product[
                "max_loan_amount_inr"
            ]
        )

        if not (
            product_minimum
            <=
            principal
            <=
            product_maximum
        ):
            raise ValueError(
                "Loan principal outside product limits"
            )

        tenure = int(
            loan.tenure_months
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
                "Loan tenure outside product limits"
            )

        expected_emi = calculate_emi(
            principal_inr=
                principal,
            annual_interest_rate_pct=
                float(
                    loan.interest_rate_pct
                ),
            tenure_months=
                tenure,
        )

        if (
            abs(
                expected_emi
                -
                float(
                    loan.emi_amount_inr
                )
            )
            >
            1.0
        ):
            raise ValueError(
                "Loan EMI inconsistent with "
                "principal/rate/tenure"
            )

        product_secured = bool(
            product[
                "secured"
            ]
        )

        if bool(
            loan.secured
        ) != product_secured:

            raise ValueError(
                "Loan secured flag does not match product"
            )

        if product_secured:

            if pd.isna(
                loan.asset_value_inr
            ):
                raise ValueError(
                    "Secured loan missing asset value"
                )

            if pd.isna(
                loan.ltv_pct
            ):
                raise ValueError(
                    "Secured loan missing LTV"
                )

            max_ltv = float(
                product[
                    "max_ltv_pct"
                ]
            )

            if (
                float(
                    loan.ltv_pct
                )
                >
                max_ltv
                +
                0.001
            ):
                raise ValueError(
                    "Loan LTV exceeds product maximum"
                )

            calculated_ltv = (
                principal
                /
                float(
                    loan.asset_value_inr
                )
                *
                100.0
            )

            if (
                abs(
                    calculated_ltv
                    -
                    float(
                        loan.ltv_pct
                    )
                )
                >
                0.05
            ):
                raise ValueError(
                    "Loan LTV inconsistent with "
                    "principal / asset value"
                )

        else:

            if not pd.isna(
                loan.asset_value_inr
            ):
                raise ValueError(
                    "Unsecured loan cannot have asset value"
                )

            if not pd.isna(
                loan.ltv_pct
            ):
                raise ValueError(
                    "Unsecured loan cannot have LTV"
                )

    # ========================================================
    # DSR
    # ========================================================

    dsr = pd.to_numeric(
        loan_accounts[
            "debt_service_ratio_at_origination"
        ],
        errors="raise",
    )

    if (
        dsr <= 0
    ).any():

        raise ValueError(
            "DSR must be > 0"
        )

    if (
        dsr
        >
        MAX_TOTAL_DEBT_SERVICE_RATIO
        +
        0.001
    ).any():

        raise ValueError(
            "Loan exceeds maximum synthetic DSR"
        )

    # ========================================================
    # MAX LOANS PER CUSTOMER
    # ========================================================

    counts = (
        loan_accounts
        .groupby(
            "finance_customer_id"
        )
        .size()
    )

    if (
        counts
        >
        MAX_LOANS_PER_CUSTOMER
    ).any():

        raise ValueError(
            "Finance customer exceeded maximum "
            "loan-account count"
        )

    # ========================================================
    # CUSTOMER SEQUENCE
    # ========================================================

    for customer_id, group in (
        loan_accounts.groupby(
            "finance_customer_id"
        )
    ):

        ordered = (
            group
            .sort_values(
                "disbursed_at"
            )
        )

        actual_sequences = (
            ordered[
                "customer_loan_sequence"
            ]
            .astype(int)
            .tolist()
        )

        expected_sequences = list(
            range(
                1,
                len(ordered)
                +
                1,
            )
        )

        if (
            actual_sequences
            !=
            expected_sequences
        ):
            raise ValueError(
                "Invalid customer_loan_sequence for "
                f"{customer_id}"
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
        loan_accounts[
            "data_origin"
        ].astype(str)
        !=
        expected_origin
    ).any():

        raise ValueError(
            "Unexpected loan data_origin"
        )

    expected_version = str(
        generation.get(
            "generator_version",
            "1.0.0",
        )
    )

    if (
        loan_accounts[
            "generator_version"
        ].astype(str)
        !=
        expected_version
    ).any():

        raise ValueError(
            "Unexpected loan generator_version"
        )

    # ========================================================
    # DOWNSTREAM TRUTH LEAKAGE
    # ========================================================

    forbidden_columns = {
        "payment_status",

        "repayment_status",
        "repayment_quality",
        "repayment_outcome",

        "days_past_due",
        "dpd",

        "delinquency_status",
        "delinquency_bucket",

        "missed_payment_count",

        "defaulted",
        "default_probability",
        "true_default",

        "collection_status",
        "collections_status",
        "collections_case_id",

        "cross_sell_eligible",
        "cross_sell_probability",
        "cross_sell_outcome",

        "risk_score",
        "risk_band",
    }

    leaked = (
        forbidden_columns
        &
        set(
            loan_accounts.columns
        )
    )

    if leaked:

        raise ValueError(
            "Payment/Collections/Cross-sell truth leaked "
            "into loan accounts: "
            +
            ", ".join(
                sorted(leaked)
            )
        )


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_loan_master(
    finance_customers: pd.DataFrame,
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

    return generate_loan_accounts(
        finance_customers=
            finance_customers,

        finance_products=
            finance_products,

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

    print(
        "\n=== FINANCE LOAN SAMPLE ===\n"
    )

    print(
        loan_accounts_df[
            [
                "loan_account_id",
                "finance_customer_id",

                "product_name",

                "principal_inr",
                "interest_rate_pct",
                "tenure_months",
                "emi_amount_inr",

                "secured",
                "ltv_pct",

                "debt_service_ratio_at_origination",

                "disbursed_at",
                "scheduled_maturity_at",
            ]
        ]
        .head(30)
        .to_string(
            index=False
        )
    )

    print(
        "\n=== LOANS BY PRODUCT ===\n"
    )

    print(
        loan_accounts_df
        .groupby(
            [
                "product_code",
                "product_name",
            ]
        )
        .size()
        .reset_index(
            name=
                "loan_count"
        )
        .sort_values(
            "loan_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== LOANS BY PRODUCT CATEGORY ===\n"
    )

    print(
        loan_accounts_df
        .groupby(
            "product_category"
        )
        .size()
        .reset_index(
            name=
                "loan_count"
        )
        .sort_values(
            "loan_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== LOANS PER CUSTOMER ===\n"
    )

    loans_per_customer = (
        loan_accounts_df
        .groupby(
            "finance_customer_id"
        )
        .size()
    )

    print(
        loans_per_customer
        .value_counts()
        .sort_index()
        .rename_axis(
            "loan_accounts"
        )
        .reset_index(
            name=
                "customer_count"
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== LOAN FINANCIAL SUMMARY ===\n"
    )

    print(
        loan_accounts_df[
            [
                "principal_inr",
                "interest_rate_pct",
                "tenure_months",
                "emi_amount_inr",
                "debt_service_ratio_at_origination",
            ]
        ]
        .describe()
        .round(2)
        .to_string()
    )

    print(
        "\n=== SECURED / UNSECURED ===\n"
    )

    print(
        loan_accounts_df
        .groupby(
            "secured"
        )
        .size()
        .reset_index(
            name=
                "loan_count"
        )
        .to_string(
            index=False
        )
    )

    secured_loans = (
        loan_accounts_df[
            loan_accounts_df[
                "secured"
            ].astype(bool)
        ]
    )

    if not secured_loans.empty:

        print(
            "\n=== SECURED LOAN LTV SUMMARY ===\n"
        )

        print(
            secured_loans[
                "ltv_pct"
            ]
            .describe()
            .round(2)
            .to_string()
        )

    print(
        "\n=== DISBURSEMENT RANGE ===\n"
    )

    print(
        "First disbursement:",
        loan_accounts_df[
            "disbursed_at"
        ].min(),
    )

    print(
        "Last disbursement:",
        loan_accounts_df[
            "disbursed_at"
        ].max(),
    )

    print(
        "\n=== FINANCE LOAN VALIDATION ===\n"
    )

    print(
        "Rows:",
        len(
            loan_accounts_df
        ),
    )

    print(
        "Unique loan IDs:",
        loan_accounts_df[
            "loan_account_id"
        ].nunique(),
    )

    print(
        "Borrowers:",
        loan_accounts_df[
            "finance_customer_id"
        ].nunique(),
    )

    print(
        "Products used:",
        loan_accounts_df[
            "finance_product_id"
        ].nunique(),
    )

    print(
        "Minimum principal:",
        round(
            float(
                loan_accounts_df[
                    "principal_inr"
                ].min()
            ),
            2,
        ),
    )

    print(
        "Maximum principal:",
        round(
            float(
                loan_accounts_df[
                    "principal_inr"
                ].max()
            ),
            2,
        ),
    )

    print(
        "Maximum DSR:",
        round(
            float(
                loan_accounts_df[
                    "debt_service_ratio_at_origination"
                ].max()
            ),
            4,
        ),
    )

    print(
        "Duplicate loan IDs:",
        int(
            loan_accounts_df[
                "loan_account_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Maximum loans/customer:",
        int(
            loan_accounts_df
            .groupby(
                "finance_customer_id"
            )
            .size()
            .max()
        ),
    )

    forbidden_columns = {
        "payment_status",
        "repayment_status",
        "days_past_due",
        "dpd",
        "delinquency_status",
        "defaulted",
        "collections_case_id",
        "cross_sell_eligible",
        "risk_score",
    }

    leaked_columns = sorted(
        forbidden_columns
        &
        set(
            loan_accounts_df.columns
        )
    )

    print(
        "Downstream truth leakage:",
        leaked_columns,
    )

    print(
        "\nGenerated "
        f"{len(loan_accounts_df)} "
        "Finance loan accounts successfully."
    )