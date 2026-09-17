"""
Synthetic Finance Customer generator for Mahindra AI Nexus.

Generates stable customer-level evidence used later by:

    finance/loans.py
        ↓
    finance/payments.py
        ↓
    finance/cross_sell.py
        ↓
    collections/cases.py
        ↓
    collections/interactions.py


============================================================
IMPORTANT DATA-MODELING RULE
============================================================

This generator creates CUSTOMER CHARACTERISTICS only.

It DOES NOT generate:

    loan outcome
    repayment outcome
    DPD
    delinquency
    collections status
    cross-sell outcome
    default probability
    approval probability
    risk score

Those values must emerge later from:

    customer evidence
        +
    loan terms
        +
    payment history
        ↓
    derived financial behaviour


============================================================
NO REAL CUSTOMER PII
============================================================

No:

    name
    email
    phone
    Aadhaar
    PAN
    street address

is generated.

The generated geography uses synthetic/reference master IDs.


============================================================
OUTPUT
============================================================

This module DOES NOT write CSV files.

Later:

    data/scripts/generate_all.py

will write the returned DataFrame to:

    data/synthetic/finance/customers.csv
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.dates import (
    parse_datetime,
)

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
# INTERNAL SYNTHETIC ENGINEERING ASSUMPTIONS
#
# IMPORTANT:
#
# These are NOT Mahindra operational statistics.
#
# They exist only because generation.yaml /
# distributions.yaml currently do not contain an employment
# mix or rural/semi-urban/urban mix.
#
# Do NOT treat these values as business truth.
# ============================================================


EMPLOYMENT_TYPE_WEIGHTS: dict[str, float] = {
    "SALARIED":
        0.38,

    "SELF_EMPLOYED":
        0.24,

    "AGRICULTURE":
        0.15,

    "SME_OWNER":
        0.13,

    "COMMERCIAL_OPERATOR":
        0.10,
}


# ------------------------------------------------------------
# Rural / semi-urban / urban mix depends on employment type.
#
# This intentionally creates a business relationship instead
# of generating employment and geography segment completely
# independently.
# ------------------------------------------------------------

RURAL_URBAN_WEIGHTS_BY_EMPLOYMENT: dict[
    str,
    dict[str, float],
] = {

    "SALARIED": {
        "URBAN":
            0.70,

        "SEMI_URBAN":
            0.25,

        "RURAL":
            0.05,
    },

    "SELF_EMPLOYED": {
        "URBAN":
            0.55,

        "SEMI_URBAN":
            0.35,

        "RURAL":
            0.10,
    },

    "AGRICULTURE": {
        "URBAN":
            0.03,

        "SEMI_URBAN":
            0.12,

        "RURAL":
            0.85,
    },

    "SME_OWNER": {
        "URBAN":
            0.45,

        "SEMI_URBAN":
            0.40,

        "RURAL":
            0.15,
    },

    "COMMERCIAL_OPERATOR": {
        "URBAN":
            0.40,

        "SEMI_URBAN":
            0.45,

        "RURAL":
            0.15,
    },
}


# ------------------------------------------------------------
# Income scaling.
#
# The base income comes from distributions.yaml.
#
# Employment type introduces correlated heterogeneity rather
# than independently generating unrelated income values.
# ------------------------------------------------------------

INCOME_MULTIPLIER_BY_EMPLOYMENT: dict[
    str,
    float,
] = {
    "SALARIED":
        1.00,

    "SELF_EMPLOYED":
        1.08,

    "AGRICULTURE":
        0.78,

    "SME_OWNER":
        1.25,

    "COMMERCIAL_OPERATOR":
        1.12,
}


# ------------------------------------------------------------
# Monthly-obligation generation.
#
# More stable-income profiles generally receive lower
# synthetic obligation ratios.
#
# These are customer characteristics — NOT loan outcomes.
# ------------------------------------------------------------

OBLIGATION_RATIO_BETA_BY_STABILITY: dict[
    str,
    tuple[
        float,
        float,
        float,
    ],
] = {

    # alpha, beta, maximum ratio

    "LOW":
        (
            4.0,
            4.0,
            0.65,
        ),

    "MEDIUM":
        (
            3.5,
            5.0,
            0.60,
        ),

    "MEDIUM_HIGH":
        (
            3.0,
            6.0,
            0.55,
        ),

    "HIGH":
        (
            2.5,
            7.0,
            0.50,
        ),
}


# ============================================================
# REQUIRED INPUT COLUMNS
# ============================================================


REGION_REQUIRED_COLUMNS: set[str] = {
    "region_id",
    "region_name",
    "generation_weight",
}


CITY_REQUIRED_COLUMNS: set[str] = {
    "city_id",
    "city_name",

    "region_id",
    "region_name",

    "generation_weight_within_region",
}


# ============================================================
# BASIC CONFIG HELPERS
# ============================================================


def _as_positive_int(
    value: Any,
    name: str,
) -> int:
    """
    Convert a configuration value into a positive integer.
    """

    if isinstance(
        value,
        bool,
    ):

        raise TypeError(
            f"{name} must be an integer, not bool"
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
            f"{name} must be an integer"
        ) from exc

    if result <= 0:

        raise ValueError(
            f"{name} must be > 0"
        )

    return result


def _as_float(
    value: Any,
    name: str,
) -> float:
    """
    Convert configuration value to float.
    """

    if isinstance(
        value,
        bool,
    ):

        raise TypeError(
            f"{name} must be numeric, not bool"
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

    return result


# ============================================================
# WEIGHT NORMALIZATION
# ============================================================


def _normalise_weight_mapping(
    mapping: Mapping[
        str,
        Any,
    ],
    name: str,
) -> dict[
    str,
    float,
]:
    """
    Normalize categorical weights.
    """

    if not mapping:

        raise ValueError(
            f"{name} cannot be empty"
        )

    parsed: dict[
        str,
        float,
    ] = {}

    for (
        label,
        raw_weight,
    ) in mapping.items():

        weight = _as_float(
            raw_weight,
            f"{name}.{label}",
        )

        if weight < 0:

            raise ValueError(
                f"{name}.{label} cannot be negative"
            )

        parsed[
            str(
                label
            )
        ] = weight

    total = float(
        sum(
            parsed.values()
        )
    )

    if total <= 0:

        raise ValueError(
            f"{name} weights must sum to > 0"
        )

    return {
        label:
            weight
            /
            total

        for (
            label,
            weight,
        ) in parsed.items()
    }


def _sample_weighted_label(
    rng: np.random.Generator,
    weights: Mapping[
        str,
        float,
    ],
) -> str:
    """
    Sample one categorical value.
    """

    normalized = (
        _normalise_weight_mapping(
            weights,
            "categorical weights",
        )
    )

    labels = list(
        normalized.keys()
    )

    probabilities = np.asarray(
        list(
            normalized.values()
        ),
        dtype=float,
    )

    return str(
        rng.choice(
            labels,
            p=probabilities,
        )
    )


# ============================================================
# FINANCE DISTRIBUTION CONFIG
# ============================================================


def _get_finance_distribution_config(
    distributions: Mapping[
        str,
        Any,
    ],
) -> Mapping[
    str,
    Any,
]:
    """
    Return distributions.finance.
    """

    finance = distributions.get(
        "finance"
    )

    if not isinstance(
        finance,
        Mapping,
    ):

        raise KeyError(
            "Missing distributions.finance configuration"
        )

    return finance


# ============================================================
# INPUT VALIDATION
# ============================================================


def _validate_inputs(
    regions: pd.DataFrame,
    cities: pd.DataFrame,
) -> None:
    """
    Validate geography master inputs.
    """

    if regions.empty:

        raise ValueError(
            "regions DataFrame cannot be empty"
        )

    if cities.empty:

        raise ValueError(
            "cities DataFrame cannot be empty"
        )

    region_missing = (
        REGION_REQUIRED_COLUMNS
        -
        set(
            regions.columns
        )
    )

    if region_missing:

        raise ValueError(
            "regions DataFrame is missing columns: "
            +
            ", ".join(
                sorted(
                    region_missing
                )
            )
        )

    city_missing = (
        CITY_REQUIRED_COLUMNS
        -
        set(
            cities.columns
        )
    )

    if city_missing:

        raise ValueError(
            "cities DataFrame is missing columns: "
            +
            ", ".join(
                sorted(
                    city_missing
                )
            )
        )

    if (
        regions[
            "region_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Duplicate region_id values found"
        )

    if (
        cities[
            "city_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Duplicate city_id values found"
        )

    valid_region_ids = set(
        regions[
            "region_id"
        ].astype(str)
    )

    city_region_ids = set(
        cities[
            "region_id"
        ].astype(str)
    )

    invalid_region_ids = (
        city_region_ids
        -
        valid_region_ids
    )

    if invalid_region_ids:

        raise ValueError(
            "cities reference invalid region IDs: "
            +
            ", ".join(
                sorted(
                    invalid_region_ids
                )
            )
        )


# ============================================================
# GEOGRAPHY SAMPLING TABLE
# ============================================================


def _build_city_sampling_table(
    regions: pd.DataFrame,
    cities: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build global city probability:

        region generation weight
            ×
        within-region city generation weight
    """

    region_weights = (
        regions[
            [
                "region_id",
                "generation_weight",
            ]
        ]
        .copy()
    )

    region_weights[
        "region_id"
    ] = (
        region_weights[
            "region_id"
        ]
        .astype(str)
    )

    region_weights[
        "generation_weight"
    ] = pd.to_numeric(
        region_weights[
            "generation_weight"
        ],
        errors="raise",
    )

    region_weight_lookup = (
        region_weights
        .set_index(
            "region_id"
        )[
            "generation_weight"
        ]
    )

    table = cities.copy()

    table[
        "region_id"
    ] = (
        table[
            "region_id"
        ]
        .astype(str)
    )

    table[
        "region_generation_weight"
    ] = (
        table[
            "region_id"
        ]
        .map(
            region_weight_lookup
        )
    )

    if (
        table[
            "region_generation_weight"
        ]
        .isna()
        .any()
    ):

        raise ValueError(
            "Could not map region generation weight "
            "for one or more cities"
        )

    table[
        "generation_weight_within_region"
    ] = pd.to_numeric(
        table[
            "generation_weight_within_region"
        ],
        errors="raise",
    )

    table[
        "global_generation_weight"
    ] = (
        table[
            "region_generation_weight"
        ]
        *
        table[
            "generation_weight_within_region"
        ]
    )

    if (
        table[
            "global_generation_weight"
        ]
        <
        0
    ).any():

        raise ValueError(
            "City generation weights cannot be negative"
        )

    total = float(
        table[
            "global_generation_weight"
        ]
        .sum()
    )

    if total <= 0:

        raise ValueError(
            "City generation weights must sum to > 0"
        )

    table[
        "global_generation_weight"
    ] = (
        table[
            "global_generation_weight"
        ]
        /
        total
    )

    return (
        table
        .reset_index(
            drop=True
        )
    )


# ============================================================
# TIME WINDOW
# ============================================================


def _get_generation_window(
    generation: Mapping[
        str,
        Any,
    ],
) -> tuple[
    pd.Timestamp,
    pd.Timestamp,
    str,
]:
    """
    Read configured synthetic time window.
    """

    time_config = generation.get(
        "time"
    )

    if not isinstance(
        time_config,
        Mapping,
    ):

        raise KeyError(
            "Missing generation.time configuration"
        )

    try:

        start_value = (
            time_config[
                "start_date"
            ]
        )

        end_value = (
            time_config[
                "end_date"
            ]
        )

    except KeyError as exc:

        raise KeyError(
            "generation.time must contain "
            "start_date and end_date"
        ) from exc

    timezone = str(
        time_config.get(
            "timezone",
            "Asia/Kolkata",
        )
    )

    start = parse_datetime(
        start_value,
        timezone,
    )

    end = parse_datetime(
        end_value,
        timezone,
    )

    if end <= start:

        raise ValueError(
            "generation.time.end_date must be "
            "after start_date"
        )

    return (
        pd.Timestamp(
            start
        ),
        pd.Timestamp(
            end
        ),
        timezone,
    )


# ============================================================
# CUSTOMER-SINCE TIMESTAMP
# ============================================================


def _generate_customer_since(
    rng: np.random.Generator,
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
    maximum_payment_history_months: int,
) -> pd.Timestamp:
    """
    Generate a finance relationship-start timestamp.

    Finance payment history is configured for as much as
    24 months, while the main 2026 generation window is much
    shorter.

    Therefore Finance customers may legitimately pre-date the
    main operational observation window.

    Earliest possible customer relationship:

        generation_start
            -
        finance.payment_history_months.max

    This supports future historical loans/payments without
    inventing a second unrelated customer timeline.
    """

    earliest = (
        generation_start
        -
        pd.DateOffset(
            months=
                maximum_payment_history_months
        )
    )

    total_seconds = (
        generation_end
        -
        earliest
    ).total_seconds()

    if total_seconds <= 0:

        raise ValueError(
            "Invalid Finance customer generation window"
        )

    offset_seconds = float(
        rng.uniform(
            0.0,
            total_seconds,
        )
    )

    return (
        earliest
        +
        pd.to_timedelta(
            offset_seconds,
            unit="s",
        )
    )


# ============================================================
# MONTHLY INCOME
# ============================================================


def _sample_monthly_income(
    rng: np.random.Generator,
    income_config: Mapping[
        str,
        Any,
    ],
    employment_type: str,
) -> int:
    """
    Generate monthly income using distributions.yaml.

    Current configured distribution:

        lognormal

    The configured lognormal draw is then adjusted using the
    employment profile to create correlated customer evidence.
    """

    distribution = str(
        income_config.get(
            "distribution",
            ""
        )
    ).lower()

    if distribution != "lognormal":

        raise ValueError(
            "finance.monthly_income currently requires "
            "distribution='lognormal'"
        )

    mean = _as_float(
        income_config.get(
            "mean"
        ),
        "finance.monthly_income.mean",
    )

    sigma = _as_float(
        income_config.get(
            "sigma"
        ),
        "finance.monthly_income.sigma",
    )

    minimum = _as_float(
        income_config.get(
            "min"
        ),
        "finance.monthly_income.min",
    )

    maximum = _as_float(
        income_config.get(
            "max"
        ),
        "finance.monthly_income.max",
    )

    if sigma <= 0:

        raise ValueError(
            "finance.monthly_income.sigma must be > 0"
        )

    if minimum <= 0:

        raise ValueError(
            "finance.monthly_income.min must be > 0"
        )

    if maximum < minimum:

        raise ValueError(
            "finance.monthly_income.max must be >= min"
        )

    base_income = float(
        rng.lognormal(
            mean=
                mean,

            sigma=
                sigma,
        )
    )

    multiplier = (
        INCOME_MULTIPLIER_BY_EMPLOYMENT[
            employment_type
        ]
    )

    adjusted_income = (
        base_income
        *
        multiplier
    )

    adjusted_income = float(
        np.clip(
            adjusted_income,
            minimum,
            maximum,
        )
    )

    # Round to nearest ₹100 for cleaner synthetic data.

    return int(
        round(
            adjusted_income
            /
            100.0
        )
        *
        100
    )


# ============================================================
# MONTHLY OBLIGATIONS
# ============================================================


def _generate_obligation_ratio(
    rng: np.random.Generator,
    income_stability: str,
) -> float:
    """
    Generate existing monthly-obligation ratio.

    This is stable customer evidence.

    It is NOT generated from the future synthetic loan that
    loans.py will create.
    """

    if (
        income_stability
        not in
        OBLIGATION_RATIO_BETA_BY_STABILITY
    ):

        raise ValueError(
            "Unsupported income stability: "
            f"{income_stability}"
        )

    (
        alpha,
        beta,
        maximum_ratio,
    ) = (
        OBLIGATION_RATIO_BETA_BY_STABILITY[
            income_stability
        ]
    )

    raw = float(
        rng.beta(
            alpha,
            beta,
        )
    )

    ratio = (
        raw
        *
        maximum_ratio
    )

    # Keep a small existing-obligation floor while preventing
    # unrealistic debt burden at customer creation.

    return float(
        np.clip(
            ratio,
            0.02,
            maximum_ratio,
        )
    )


# ============================================================
# CUSTOMER SEGMENT
# ============================================================


def _derive_finance_customer_segment(
    employment_type: str,
    rural_urban_segment: str,
) -> str:
    """
    Derive finance customer segment from underlying evidence.

    This is not independently randomized.
    """

    if employment_type == "AGRICULTURE":

        return "RURAL_AGRI"

    if employment_type == "SME_OWNER":

        return "SME"

    if employment_type == "COMMERCIAL_OPERATOR":

        return "COMMERCIAL_OPERATOR"

    if (
        rural_urban_segment
        ==
        "RURAL"
        and
        employment_type
        ==
        "SELF_EMPLOYED"
    ):

        return "RURAL_SELF_EMPLOYED"

    return "RETAIL_CONSUMER"


# ============================================================
# FINANCE CUSTOMER GENERATOR
# ============================================================


def generate_finance_customers(
    regions: pd.DataFrame,
    cities: pd.DataFrame,
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
    Generate stable synthetic Finance customers.

    Expected generation config:

        finance:
          customers:
            count: 3000

          payment_history_months:
            min: 6
            max: 24

    Expected distribution config:

        finance:
          income_stability_weights:
            ...

          monthly_income:
            distribution: lognormal
            ...

    Output columns:

        finance_customer_id

        region_id
        region_name

        city_id
        city_name

        employment_type
        rural_urban_segment
        finance_customer_segment

        income_stability

        monthly_income_inr
        monthly_obligations_inr
        obligation_to_income_ratio

        customer_since

        active

        data_origin
        generator_version
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
    # MASTER VALIDATION
    # ========================================================

    _validate_inputs(
        regions=
            regions,

        cities=
            cities,
    )

    # ========================================================
    # FINANCE CONFIG
    # ========================================================

    try:

        finance_config = generation[
            "finance"
        ]

    except KeyError as exc:

        raise KeyError(
            "Missing generation.finance"
        ) from exc

    if not isinstance(
        finance_config,
        Mapping,
    ):

        raise TypeError(
            "generation.finance must be a mapping"
        )

    try:

        customer_count = (
            _as_positive_int(
                finance_config[
                    "customers"
                ][
                    "count"
                ],
                (
                    "generation.finance."
                    "customers.count"
                ),
            )
        )

    except KeyError as exc:

        raise KeyError(
            "Missing configuration key: "
            "generation.finance.customers.count"
        ) from exc

    # ========================================================
    # PAYMENT HISTORY CONFIG
    #
    # Used only to establish how far back an existing Finance
    # customer relationship may begin.
    # ========================================================

    try:

        payment_history_config = (
            finance_config[
                "payment_history_months"
            ]
        )

        minimum_history_months = (
            _as_positive_int(
                payment_history_config[
                    "min"
                ],
                (
                    "generation.finance."
                    "payment_history_months.min"
                ),
            )
        )

        maximum_history_months = (
            _as_positive_int(
                payment_history_config[
                    "max"
                ],
                (
                    "generation.finance."
                    "payment_history_months.max"
                ),
            )
        )

    except KeyError as exc:

        raise KeyError(
            "Missing generation.finance."
            "payment_history_months.min/max"
        ) from exc

    if (
        maximum_history_months
        <
        minimum_history_months
    ):

        raise ValueError(
            "finance.payment_history_months.max "
            "must be >= min"
        )

    # ========================================================
    # DETERMINISTIC RNG
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
            "finance.customers",
        )
    )

    # ========================================================
    # DISTRIBUTIONS
    # ========================================================

    finance_distributions = (
        _get_finance_distribution_config(
            distributions
        )
    )

    try:

        stability_weights = (
            _normalise_weight_mapping(
                finance_distributions[
                    "income_stability_weights"
                ],
                (
                    "distributions.finance."
                    "income_stability_weights"
                ),
            )
        )

    except KeyError as exc:

        raise KeyError(
            "Missing distributions.finance."
            "income_stability_weights"
        ) from exc

    try:

        monthly_income_config = (
            finance_distributions[
                "monthly_income"
            ]
        )

    except KeyError as exc:

        raise KeyError(
            "Missing distributions.finance.monthly_income"
        ) from exc

    if not isinstance(
        monthly_income_config,
        Mapping,
    ):

        raise TypeError(
            "distributions.finance.monthly_income "
            "must be a mapping"
        )

    # Validate expected stability categories because obligation
    # generation depends on them.

    configured_stabilities = set(
        stability_weights.keys()
    )

    supported_stabilities = set(
        OBLIGATION_RATIO_BETA_BY_STABILITY.keys()
    )

    unsupported_stabilities = (
        configured_stabilities
        -
        supported_stabilities
    )

    if unsupported_stabilities:

        raise ValueError(
            "Unsupported Finance income-stability labels: "
            +
            ", ".join(
                sorted(
                    unsupported_stabilities
                )
            )
        )

    # ========================================================
    # GEOGRAPHY SAMPLING
    # ========================================================

    city_table = (
        _build_city_sampling_table(
            regions=
                regions,

            cities=
                cities,
        )
    )

    city_probabilities = (
        city_table[
            "global_generation_weight"
        ]
        .to_numpy(
            dtype=float
        )
    )

    city_indices = rng.choice(
        np.arange(
            len(
                city_table
            )
        ),
        size=
            customer_count,
        p=
            city_probabilities,
    )

    # ========================================================
    # EMPLOYMENT SAMPLING
    # ========================================================

    employment_weights = (
        _normalise_weight_mapping(
            EMPLOYMENT_TYPE_WEIGHTS,
            "EMPLOYMENT_TYPE_WEIGHTS",
        )
    )

    employment_labels = list(
        employment_weights.keys()
    )

    employment_probabilities = np.asarray(
        list(
            employment_weights.values()
        ),
        dtype=float,
    )

    employment_types = rng.choice(
        employment_labels,
        size=
            customer_count,
        p=
            employment_probabilities,
    )

    # ========================================================
    # INCOME-STABILITY SAMPLING
    # ========================================================

    stability_labels = list(
        stability_weights.keys()
    )

    stability_probabilities = np.asarray(
        list(
            stability_weights.values()
        ),
        dtype=float,
    )

    income_stabilities = rng.choice(
        stability_labels,
        size=
            customer_count,
        p=
            stability_probabilities,
    )

    # ========================================================
    # GENERATION WINDOW
    # ========================================================

    (
        generation_start,
        generation_end,
        _,
    ) = (
        _get_generation_window(
            generation
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
    # BUILD CUSTOMERS
    # ========================================================

    rows: list[
        dict[str, Any]
    ] = []

    for index in range(
        customer_count
    ):

        # ----------------------------------------------------
        # Geography
        # ----------------------------------------------------

        city = (
            city_table.iloc[
                int(
                    city_indices[
                        index
                    ]
                )
            ]
        )

        # ----------------------------------------------------
        # Employment
        # ----------------------------------------------------

        employment_type = str(
            employment_types[
                index
            ]
        )

        # ----------------------------------------------------
        # Rural / semi-urban / urban
        #
        # Depends on employment type.
        # ----------------------------------------------------

        rural_urban_segment = (
            _sample_weighted_label(
                rng=
                    rng,

                weights=
                    RURAL_URBAN_WEIGHTS_BY_EMPLOYMENT[
                        employment_type
                    ],
            )
        )

        # ----------------------------------------------------
        # Income stability
        # ----------------------------------------------------

        income_stability = str(
            income_stabilities[
                index
            ]
        )

        # ----------------------------------------------------
        # Income
        # ----------------------------------------------------

        monthly_income_inr = (
            _sample_monthly_income(
                rng=
                    rng,

                income_config=
                    monthly_income_config,

                employment_type=
                    employment_type,
            )
        )

        # ----------------------------------------------------
        # Existing obligations
        # ----------------------------------------------------

        obligation_ratio = (
            _generate_obligation_ratio(
                rng=
                    rng,

                income_stability=
                    income_stability,
            )
        )

        monthly_obligations_inr = int(
            round(
                monthly_income_inr
                *
                obligation_ratio
                /
                100.0
            )
            *
            100
        )

        monthly_obligations_inr = int(
            min(
                monthly_obligations_inr,
                monthly_income_inr,
            )
        )

        actual_obligation_ratio = (
            monthly_obligations_inr
            /
            monthly_income_inr
        )

        # ----------------------------------------------------
        # Derived Finance customer segment
        # ----------------------------------------------------

        finance_customer_segment = (
            _derive_finance_customer_segment(
                employment_type=
                    employment_type,

                rural_urban_segment=
                    rural_urban_segment,
            )
        )

        # ----------------------------------------------------
        # Customer relationship start
        # ----------------------------------------------------

        customer_since = (
            _generate_customer_since(
                rng=
                    rng,

                generation_start=
                    generation_start,

                generation_end=
                    generation_end,

                maximum_payment_history_months=
                    maximum_history_months,
            )
        )

        # ----------------------------------------------------
        # Stable Finance customer row
        # ----------------------------------------------------

        rows.append(
            {
                "finance_customer_id":
                    generate_id(
                        "FINCUST_SYN",
                        index
                        +
                        1,
                        width=6,
                    ),

                "region_id":
                    str(
                        city[
                            "region_id"
                        ]
                    ),

                "region_name":
                    str(
                        city[
                            "region_name"
                        ]
                    ),

                "city_id":
                    str(
                        city[
                            "city_id"
                        ]
                    ),

                "city_name":
                    str(
                        city[
                            "city_name"
                        ]
                    ),

                "employment_type":
                    employment_type,

                "rural_urban_segment":
                    rural_urban_segment,

                "finance_customer_segment":
                    finance_customer_segment,

                "income_stability":
                    income_stability,

                "monthly_income_inr":
                    monthly_income_inr,

                "monthly_obligations_inr":
                    monthly_obligations_inr,

                "obligation_to_income_ratio":
                    round(
                        float(
                            actual_obligation_ratio
                        ),
                        4,
                    ),

                "customer_since":
                    customer_since,

                "active":
                    True,

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    finance_customers = pd.DataFrame(
        rows,
        columns=[
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
        ],
    )

    # ========================================================
    # VALIDATE
    # ========================================================

    validate_finance_customers(
        finance_customers=
            finance_customers,

        regions=
            regions,

        cities=
            cities,

        expected_count=
            customer_count,

        generation=
            generation,

        distributions=
            distributions,
    )

    return finance_customers


# ============================================================
# VALIDATION
# ============================================================


def validate_finance_customers(
    finance_customers: pd.DataFrame,
    regions: pd.DataFrame,
    cities: pd.DataFrame,
    expected_count: int | None = None,
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
    Validate Finance customer dataset.
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
    # REQUIRED COLUMNS
    # ========================================================

    required_columns = {
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

    missing = (
        required_columns
        -
        set(
            finance_customers.columns
        )
    )

    if missing:

        raise ValueError(
            "Finance customers DataFrame is missing "
            "required columns: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    # ========================================================
    # NON-EMPTY / COUNT
    # ========================================================

    if finance_customers.empty:

        raise ValueError(
            "Finance customers DataFrame cannot be empty"
        )

    if (
        expected_count is not None
        and
        len(
            finance_customers
        )
        !=
        expected_count
    ):

        raise ValueError(
            f"Expected {expected_count} Finance customers, "
            f"generated {len(finance_customers)}"
        )

    # ========================================================
    # UNIQUE IDS
    # ========================================================

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

    # ========================================================
    # REQUIRED NON-NULL VALUES
    # ========================================================

    required_non_null = [
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
    ]

    for column in required_non_null:

        if (
            finance_customers[
                column
            ]
            .isna()
            .any()
        ):

            raise ValueError(
                f"Missing Finance customer values "
                f"in {column}"
            )

    # ========================================================
    # REGION FK
    # ========================================================

    valid_region_ids = set(
        regions[
            "region_id"
        ]
        .astype(str)
    )

    customer_region_ids = set(
        finance_customers[
            "region_id"
        ]
        .astype(str)
    )

    invalid_region_ids = (
        customer_region_ids
        -
        valid_region_ids
    )

    if invalid_region_ids:

        raise ValueError(
            "Finance customers reference invalid "
            "region IDs: "
            +
            ", ".join(
                sorted(
                    invalid_region_ids
                )
            )
        )

    # ========================================================
    # CITY FK
    # ========================================================

    valid_city_ids = set(
        cities[
            "city_id"
        ]
        .astype(str)
    )

    customer_city_ids = set(
        finance_customers[
            "city_id"
        ]
        .astype(str)
    )

    invalid_city_ids = (
        customer_city_ids
        -
        valid_city_ids
    )

    if invalid_city_ids:

        raise ValueError(
            "Finance customers reference invalid city IDs: "
            +
            ", ".join(
                sorted(
                    invalid_city_ids
                )
            )
        )

    # ========================================================
    # CITY -> REGION CONSISTENCY
    # ========================================================

    city_lookup = {
        str(
            row.city_id
        ):
            (
                str(
                    row.city_name
                ),
                str(
                    row.region_id
                ),
                str(
                    row.region_name
                ),
            )

        for row in cities.itertuples(
            index=False
        )
    }

    for customer in finance_customers.itertuples(
        index=False
    ):

        (
            expected_city_name,
            expected_region_id,
            expected_region_name,
        ) = city_lookup[
            str(
                customer.city_id
            )
        ]

        if (
            str(
                customer.city_name
            )
            !=
            expected_city_name
        ):

            raise ValueError(
                "Finance customer city-name mismatch "
                f"for {customer.finance_customer_id}"
            )

        if (
            str(
                customer.region_id
            )
            !=
            expected_region_id
        ):

            raise ValueError(
                "Finance customer region-ID mismatch "
                f"for {customer.finance_customer_id}"
            )

        if (
            str(
                customer.region_name
            )
            !=
            expected_region_name
        ):

            raise ValueError(
                "Finance customer region-name mismatch "
                f"for {customer.finance_customer_id}"
            )

    # ========================================================
    # EMPLOYMENT
    # ========================================================

    valid_employment_types = set(
        EMPLOYMENT_TYPE_WEIGHTS.keys()
    )

    observed_employment_types = set(
        finance_customers[
            "employment_type"
        ]
        .astype(str)
    )

    invalid_employment = (
        observed_employment_types
        -
        valid_employment_types
    )

    if invalid_employment:

        raise ValueError(
            "Invalid employment types: "
            +
            ", ".join(
                sorted(
                    invalid_employment
                )
            )
        )

    # ========================================================
    # RURAL / URBAN
    # ========================================================

    allowed_geo_segments = {
        "URBAN",
        "SEMI_URBAN",
        "RURAL",
    }

    observed_geo_segments = set(
        finance_customers[
            "rural_urban_segment"
        ]
        .astype(str)
    )

    invalid_geo_segments = (
        observed_geo_segments
        -
        allowed_geo_segments
    )

    if invalid_geo_segments:

        raise ValueError(
            "Invalid rural/urban segments: "
            +
            ", ".join(
                sorted(
                    invalid_geo_segments
                )
            )
        )

    # ========================================================
    # INCOME STABILITY
    # ========================================================

    finance_distributions = (
        _get_finance_distribution_config(
            distributions
        )
    )

    configured_stability = set(
        finance_distributions[
            "income_stability_weights"
        ].keys()
    )

    observed_stability = set(
        finance_customers[
            "income_stability"
        ]
        .astype(str)
    )

    invalid_stability = (
        observed_stability
        -
        configured_stability
    )

    if invalid_stability:

        raise ValueError(
            "Finance customers contain invalid "
            "income-stability labels: "
            +
            ", ".join(
                sorted(
                    invalid_stability
                )
            )
        )

    # ========================================================
    # MONTHLY INCOME RANGE
    # ========================================================

    monthly_income_config = (
        finance_distributions[
            "monthly_income"
        ]
    )

    minimum_income = _as_float(
        monthly_income_config[
            "min"
        ],
        "finance.monthly_income.min",
    )

    maximum_income = _as_float(
        monthly_income_config[
            "max"
        ],
        "finance.monthly_income.max",
    )

    income = pd.to_numeric(
        finance_customers[
            "monthly_income_inr"
        ],
        errors="raise",
    )

    if (
        income
        <
        minimum_income
    ).any():

        raise ValueError(
            "Finance customer monthly income fell "
            "below configured minimum"
        )

    if (
        income
        >
        maximum_income
    ).any():

        raise ValueError(
            "Finance customer monthly income exceeded "
            "configured maximum"
        )

    # ========================================================
    # OBLIGATIONS
    # ========================================================

    obligations = pd.to_numeric(
        finance_customers[
            "monthly_obligations_inr"
        ],
        errors="raise",
    )

    if (
        obligations
        <
        0
    ).any():

        raise ValueError(
            "monthly_obligations_inr cannot be negative"
        )

    if (
        obligations
        >
        income
    ).any():

        raise ValueError(
            "Monthly obligations cannot exceed "
            "monthly income"
        )

    ratios = pd.to_numeric(
        finance_customers[
            "obligation_to_income_ratio"
        ],
        errors="raise",
    )

    if (
        ratios
        <
        0
    ).any():

        raise ValueError(
            "obligation_to_income_ratio cannot be negative"
        )

    if (
        ratios
        >
        0.65
    ).any():

        raise ValueError(
            "obligation_to_income_ratio exceeds "
            "synthetic customer limit of 0.65"
        )

    calculated_ratio = (
        obligations
        /
        income
    )

    ratio_difference = (
        calculated_ratio
        -
        ratios
    ).abs()

    if (
        ratio_difference
        >
        0.001
    ).any():

        raise ValueError(
            "obligation_to_income_ratio is inconsistent "
            "with income and obligations"
        )

    # ========================================================
    # DERIVED CUSTOMER SEGMENT CONSISTENCY
    # ========================================================

    expected_segments = [
        _derive_finance_customer_segment(
            employment_type=
                str(
                    row.employment_type
                ),

            rural_urban_segment=
                str(
                    row.rural_urban_segment
                ),
        )

        for row in finance_customers.itertuples(
            index=False
        )
    ]

    expected_segment_series = pd.Series(
        expected_segments,
        index=
            finance_customers.index,
    )

    actual_segment_series = (
        finance_customers[
            "finance_customer_segment"
        ]
        .astype(str)
    )

    if (
        expected_segment_series
        !=
        actual_segment_series
    ).any():

        raise ValueError(
            "finance_customer_segment is inconsistent "
            "with underlying customer evidence"
        )

    # ========================================================
    # CUSTOMER-SINCE TIME VALIDATION
    # ========================================================

    (
        generation_start,
        generation_end,
        _,
    ) = (
        _get_generation_window(
            generation
        )
    )

    maximum_history_months = (
        _as_positive_int(
            generation[
                "finance"
            ][
                "payment_history_months"
            ][
                "max"
            ],
            (
                "generation.finance."
                "payment_history_months.max"
            ),
        )
    )

    earliest_allowed = (
        generation_start
        -
        pd.DateOffset(
            months=
                maximum_history_months
        )
    )

    customer_since = pd.to_datetime(
        finance_customers[
            "customer_since"
        ],
    )

    if (
        customer_since
        <
        earliest_allowed
    ).any():

        raise ValueError(
            "Finance customer_since is earlier than "
            "allowed historical horizon"
        )

    if (
        customer_since
        >=
        generation_end
    ).any():

        raise ValueError(
            "Finance customer_since must be before "
            "generation end"
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
        finance_customers[
            "data_origin"
        ]
        .astype(str)
        !=
        expected_origin
    ).any():

        raise ValueError(
            "Unexpected Finance customer data_origin"
        )

    expected_version = str(
        generation.get(
            "generator_version",
            "1.0.0",
        )
    )

    if (
        finance_customers[
            "generator_version"
        ]
        .astype(str)
        !=
        expected_version
    ).any():

        raise ValueError(
            "Unexpected Finance customer "
            "generator_version"
        )

    # ========================================================
    # NO OUTCOME / TRUTH LEAKAGE
    #
    # These values belong to downstream loan/payment/
    # collections generation and must not be synthesized here.
    # ========================================================

    forbidden_customer_columns = {
        "loan_status",
        "loan_outcome",

        "approval_probability",
        "default_probability",

        "repayment_outcome",
        "repayment_quality",

        "dpd",
        "days_past_due",

        "delinquency_status",

        "collections_status",

        "cross_sell_eligible",
        "cross_sell_probability",

        "risk_score",

        "true_default",
        "true_repayment_outcome",
    }

    leaked = (
        forbidden_customer_columns
        &
        set(
            finance_customers.columns
        )
    )

    if leaked:

        raise ValueError(
            "Downstream Finance/Collections truth leaked "
            "into finance customers: "
            +
            ", ".join(
                sorted(
                    leaked
                )
            )
        )


# ============================================================
# PUBLIC FINANCE CUSTOMER GENERATOR
# ============================================================


def generate_finance_customer_master(
    regions: pd.DataFrame,
    cities: pd.DataFrame,
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

    return generate_finance_customers(
        regions=
            regions,

        cities=
            cities,

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

    # ========================================================
    # MASTER GEOGRAPHY
    # ========================================================

    (
        regions_df,
        cities_df,
    ) = generate_geography()

    # ========================================================
    # FINANCE CUSTOMERS
    # ========================================================

    finance_customers_df = (
        generate_finance_customer_master(
            regions=
                regions_df,

            cities=
                cities_df,
        )
    )

    # ========================================================
    # SAMPLE
    # ========================================================

    print(
        "\n=== FINANCE CUSTOMER SAMPLE ===\n"
    )

    sample_columns = [
        "finance_customer_id",

        "region_name",
        "city_name",

        "employment_type",
        "rural_urban_segment",
        "finance_customer_segment",

        "income_stability",

        "monthly_income_inr",
        "monthly_obligations_inr",
        "obligation_to_income_ratio",

        "customer_since",
    ]

    print(
        finance_customers_df[
            sample_columns
        ]
        .head(
            30
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # REGION DISTRIBUTION
    # ========================================================

    print(
        "\n=== FINANCE CUSTOMERS BY REGION ===\n"
    )

    print(
        finance_customers_df
        .groupby(
            "region_name"
        )
        .size()
        .reset_index(
            name=
                "customer_count"
        )
        .sort_values(
            "customer_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # EMPLOYMENT DISTRIBUTION
    # ========================================================

    print(
        "\n=== EMPLOYMENT TYPE ===\n"
    )

    print(
        finance_customers_df
        .groupby(
            "employment_type"
        )
        .size()
        .reset_index(
            name=
                "customer_count"
        )
        .sort_values(
            "customer_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # RURAL / URBAN DISTRIBUTION
    # ========================================================

    print(
        "\n=== RURAL / URBAN SEGMENT ===\n"
    )

    print(
        finance_customers_df
        .groupby(
            "rural_urban_segment"
        )
        .size()
        .reset_index(
            name=
                "customer_count"
        )
        .sort_values(
            "customer_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # FINANCE CUSTOMER SEGMENT
    # ========================================================

    print(
        "\n=== FINANCE CUSTOMER SEGMENT ===\n"
    )

    print(
        finance_customers_df
        .groupby(
            "finance_customer_segment"
        )
        .size()
        .reset_index(
            name=
                "customer_count"
        )
        .sort_values(
            "customer_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # INCOME STABILITY
    # ========================================================

    print(
        "\n=== INCOME STABILITY ===\n"
    )

    print(
        finance_customers_df
        .groupby(
            "income_stability"
        )
        .size()
        .reset_index(
            name=
                "customer_count"
        )
        .sort_values(
            "customer_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # FINANCIAL PROFILE SUMMARY
    # ========================================================

    print(
        "\n=== FINANCIAL PROFILE SUMMARY ===\n"
    )

    summary = (
        finance_customers_df[
            [
                "monthly_income_inr",
                "monthly_obligations_inr",
                "obligation_to_income_ratio",
            ]
        ]
        .describe()
        .round(
            2
        )
    )

    print(
        summary.to_string()
    )

    # ========================================================
    # INCOME BY EMPLOYMENT
    # ========================================================

    print(
        "\n=== AVG INCOME BY EMPLOYMENT ===\n"
    )

    income_by_employment = (
        finance_customers_df
        .groupby(
            "employment_type"
        )[
            "monthly_income_inr"
        ]
        .agg(
            [
                "count",
                "mean",
                "median",
                "min",
                "max",
            ]
        )
        .round(
            2
        )
        .reset_index()
    )

    print(
        income_by_employment
        .to_string(
            index=False
        )
    )

    # ========================================================
    # OBLIGATION RATIO BY INCOME STABILITY
    #
    # Useful validation that our generated evidence is
    # internally related rather than independent random noise.
    # ========================================================

    print(
        "\n=== OBLIGATION RATIO BY INCOME STABILITY ===\n"
    )

    obligation_by_stability = (
        finance_customers_df
        .groupby(
            "income_stability"
        )[
            "obligation_to_income_ratio"
        ]
        .agg(
            [
                "count",
                "mean",
                "median",
            ]
        )
        .round(
            4
        )
        .reset_index()
    )

    print(
        obligation_by_stability
        .to_string(
            index=False
        )
    )

    # ========================================================
    # FINAL VALIDATION STATUS
    # ========================================================

    print(
        "\n=== FINANCE CUSTOMER VALIDATION ===\n"
    )

    print(
        "Rows:",
        len(
            finance_customers_df
        ),
    )

    print(
        "Unique customer IDs:",
        finance_customers_df[
            "finance_customer_id"
        ].nunique(),
    )

    print(
        "Regions:",
        finance_customers_df[
            "region_id"
        ].nunique(),
    )

    print(
        "Cities:",
        finance_customers_df[
            "city_id"
        ].nunique(),
    )

    print(
        "Minimum monthly income:",
        int(
            finance_customers_df[
                "monthly_income_inr"
            ].min()
        ),
    )

    print(
        "Maximum monthly income:",
        int(
            finance_customers_df[
                "monthly_income_inr"
            ].max()
        ),
    )

    print(
        "Maximum obligation ratio:",
        round(
            float(
                finance_customers_df[
                    "obligation_to_income_ratio"
                ].max()
            ),
            4,
        ),
    )

    print(
        "Duplicate IDs:",
        int(
            finance_customers_df[
                "finance_customer_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    forbidden_columns = {
        "loan_status",
        "loan_outcome",
        "default_probability",
        "repayment_outcome",
        "days_past_due",
        "collections_status",
        "cross_sell_eligible",
        "risk_score",
        "true_default",
    }

    leaked_columns = sorted(
        forbidden_columns
        &
        set(
            finance_customers_df.columns
        )
    )

    print(
        "Downstream truth leakage:",
        leaked_columns,
    )

    print(
        "\nGenerated "
        f"{len(finance_customers_df)} "
        "Finance customers successfully."
    )