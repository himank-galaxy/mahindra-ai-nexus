"""
Synthetic Auto customer generator for Mahindra AI Nexus.

Generates synthetic customer entities from:
- geography master
- vehicle model master
- generation.yaml
- distributions.yaml

This module DOES NOT write CSV files.
CSV writing is handled later by data/scripts/generate_all.py.

No real customer PII is generated.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.dates import parse_datetime
from data.generators.common.distributions import sample_distribution

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
# BASIC HELPERS
# ============================================================


def _as_positive_int(
    value: Any,
    name: str,
) -> int:
    """
    Convert a config value into a positive integer.
    """

    if isinstance(value, bool):
        raise TypeError(
            f"{name} must be an integer, not bool"
        )

    try:
        result = int(value)

    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"{name} must be an integer"
        ) from exc

    if result <= 0:
        raise ValueError(
            f"{name} must be > 0"
        )

    return result


def _validate_probability(
    value: Any,
    name: str,
) -> float:
    """
    Validate probability in range [0, 1].
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
        not isinstance(weights, Mapping)
        or not weights
    ):
        raise ValueError(
            f"{name} must be a non-empty mapping"
        )

    parsed: dict[str, float] = {}

    for label, raw_weight in weights.items():

        try:
            weight = float(raw_weight)

        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"Weight for {label!r} "
                f"in {name} must be numeric"
            ) from exc

        if weight < 0:
            raise ValueError(
                f"Weight for {label!r} "
                f"in {name} cannot be negative"
            )

        parsed[
            str(label)
        ] = weight

    total = sum(
        parsed.values()
    )

    if total <= 0:
        raise ValueError(
            f"Weights in {name} must sum to > 0"
        )

    return {
        label: weight / total
        for label, weight
        in parsed.items()
    }


# ============================================================
# TIME CONFIG
# ============================================================


def _get_time_window(
    generation: Mapping[str, Any],
) -> tuple[Any, Any, str]:
    """
    Supports:

    time:
      start:
      end:
      timezone:

    OR:

    time_window:
      start:
      end:
      timezone:
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
            "Missing generation time configuration. "
            "Expected generation.time "
            "or generation.time_window."
        )

    start = time_config.get(
        "start",
        time_config.get(
            "start_date"
        ),
    )

    end = time_config.get(
        "end",
        time_config.get(
            "end_date"
        ),
    )

    timezone = str(
        time_config.get(
            "timezone",
            "Asia/Kolkata",
        )
    )

    if start is None:
        raise KeyError(
            "Missing start/start_date "
            "in generation time configuration"
        )

    if end is None:
        raise KeyError(
            "Missing end/end_date "
            "in generation time configuration"
        )

    return (
        start,
        end,
        timezone,
    )


def _random_datetime(
    rng: np.random.Generator,
    start: Any,
    end: Any,
    timezone: str,
):
    """
    Generate a deterministic random datetime using
    the generator-specific NumPy RNG.
    """

    start_dt = parse_datetime(
        start,
        timezone,
    )

    end_dt = parse_datetime(
        end,
        timezone,
    )

    if end_dt <= start_dt:
        raise ValueError(
            "Generation end datetime must "
            "be later than start datetime"
        )

    total_seconds = (
        end_dt - start_dt
    ).total_seconds()

    offset_seconds = float(
        rng.uniform(
            0.0,
            total_seconds,
        )
    )

    return (
        start_dt
        + timedelta(
            seconds=offset_seconds
        )
    )


# ============================================================
# INPUT VALIDATION
# ============================================================


def _validate_inputs(
    regions: pd.DataFrame,
    cities: pd.DataFrame,
    vehicle_models: pd.DataFrame,
) -> None:
    """
    Validate upstream master data.
    """

    region_required = {
        "region_id",
        "region_name",
        "generation_weight",
    }

    city_required = {
        "city_id",
        "city_name",
        "region_id",
        "region_name",
        "generation_weight_within_region",
    }

    vehicle_required = {
        "vehicle_model_id",
        "model_name",
        "generation_weight",
    }

    for (
        name,
        dataframe,
        required,
    ) in (
        (
            "regions",
            regions,
            region_required,
        ),
        (
            "cities",
            cities,
            city_required,
        ),
        (
            "vehicle_models",
            vehicle_models,
            vehicle_required,
        ),
    ):

        missing = (
            required
            .difference(
                dataframe.columns
            )
        )

        if missing:
            raise ValueError(
                f"{name} is missing required columns: "
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

    if regions[
        "region_id"
    ].duplicated().any():
        raise ValueError(
            "Duplicate region_id values found"
        )

    if cities[
        "city_id"
    ].duplicated().any():
        raise ValueError(
            "Duplicate city_id values found"
        )

    if vehicle_models[
        "vehicle_model_id"
    ].duplicated().any():
        raise ValueError(
            "Duplicate vehicle_model_id values found"
        )


# ============================================================
# CITY SAMPLING
# ============================================================


def _build_city_sampling_table(
    regions: pd.DataFrame,
    cities: pd.DataFrame,
) -> pd.DataFrame:
    """
    Global city generation probability:

        region weight
            *
        city weight within region
    """

    region_weights = (
        regions
        .set_index(
            "region_id"
        )[
            "generation_weight"
        ]
        .astype(float)
    )

    city_table = cities.copy()

    city_table[
        "region_generation_weight"
    ] = (
        city_table[
            "region_id"
        ]
        .map(
            region_weights
        )
    )

    if city_table[
        "region_generation_weight"
    ].isna().any():
        raise ValueError(
            "Some cities reference region IDs "
            "not present in regions"
        )

    city_table[
        "global_generation_weight"
    ] = (
        city_table[
            "region_generation_weight"
        ].astype(float)
        *
        city_table[
            "generation_weight_within_region"
        ].astype(float)
    )

    total = float(
        city_table[
            "global_generation_weight"
        ].sum()
    )

    if total <= 0:
        raise ValueError(
            "Calculated city generation weights "
            "must sum to > 0"
        )

    city_table[
        "global_generation_weight"
    ] = (
        city_table[
            "global_generation_weight"
        ]
        / total
    )

    return (
        city_table
        .reset_index(
            drop=True
        )
    )


# ============================================================
# CUSTOMER SEGMENT
# ============================================================


def _derive_customer_segment(
    purchase_horizon_days: int,
    finance_required: bool,
    exchange_vehicle: bool,
) -> str:
    """
    Derive customer segment from generated evidence.

    This is NOT a randomly assigned conversion result.
    """

    if purchase_horizon_days <= 14:
        return "HIGH_INTENT_BUYER"

    if exchange_vehicle:
        return "EXCHANGE_UPGRADER"

    if finance_required:
        return "FINANCE_ORIENTED"

    return "STANDARD_PROSPECT"


# ============================================================
# CUSTOMER GENERATOR
# ============================================================


def generate_customers(
    regions: pd.DataFrame,
    cities: pd.DataFrame,
    vehicle_models: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate synthetic Auto customers.

    Expected generation config:

        auto:
          customers:
            count: 5000

    Exact distribution config:

        auto_customer:
          budget_band_weights: ...
          purchase_horizon_days: ...
          finance_required_probability: ...
          exchange_vehicle_probability: ...
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    if distributions is None:
        distributions = (
            load_distribution_config()
        )

    # --------------------------------------------------------
    # Validate upstream data
    # --------------------------------------------------------

    _validate_inputs(
        regions=regions,
        cities=cities,
        vehicle_models=vehicle_models,
    )

    # --------------------------------------------------------
    # Customer count
    # --------------------------------------------------------

    try:
        customer_count = (
            _as_positive_int(
                generation[
                    "auto"
                ][
                    "customers"
                ][
                    "count"
                ],
                (
                    "generation.auto."
                    "customers.count"
                ),
            )
        )

    except KeyError as exc:
        raise KeyError(
            "Missing configuration key: "
            "generation.auto.customers.count"
        ) from exc

    # --------------------------------------------------------
    # Deterministic customer RNG
    # --------------------------------------------------------

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

    customer_seed = (
        derive_seed(
            base_seed,
            "auto.customers",
        )
    )

    rng = make_rng(
        customer_seed
    )

    # ========================================================
    # EXACT DISTRIBUTION CONFIG
    # ========================================================

    customer_config = (
        distributions.get(
            "auto_customer"
        )
    )

    if not isinstance(
        customer_config,
        Mapping,
    ):
        raise KeyError(
            "Missing distributions.auto_customer "
            "configuration"
        )

    try:

        budget_weights = (
            _normalize_weights(
                customer_config[
                    "budget_band_weights"
                ],
                (
                    "distributions.auto_customer."
                    "budget_band_weights"
                ),
            )
        )

        purchase_horizon_spec = (
            customer_config[
                "purchase_horizon_days"
            ]
        )

        finance_probability = (
            _validate_probability(
                customer_config[
                    "finance_required_probability"
                ],
                (
                    "distributions.auto_customer."
                    "finance_required_probability"
                ),
            )
        )

        exchange_probability = (
            _validate_probability(
                customer_config[
                    "exchange_vehicle_probability"
                ],
                (
                    "distributions.auto_customer."
                    "exchange_vehicle_probability"
                ),
            )
        )

    except KeyError as exc:
        raise KeyError(
            "auto_customer configuration is incomplete. "
            "Required keys: "
            "budget_band_weights, "
            "purchase_horizon_days, "
            "finance_required_probability, "
            "exchange_vehicle_probability."
        ) from exc

    if not isinstance(
        purchase_horizon_spec,
        Mapping,
    ):
        raise TypeError(
            "distributions.auto_customer."
            "purchase_horizon_days must be "
            "a distribution mapping"
        )

    # ========================================================
    # GEOGRAPHY SAMPLING
    # ========================================================

    city_table = (
        _build_city_sampling_table(
            regions=regions,
            cities=cities,
        )
    )

    city_indices = (
        rng.choice(
            np.arange(
                len(
                    city_table
                )
            ),
            size=customer_count,
            p=(
                city_table[
                    "global_generation_weight"
                ]
                .to_numpy(
                    dtype=float
                )
            ),
        )
    )

    # ========================================================
    # VEHICLE-MODEL SAMPLING
    # ========================================================

    model_probabilities = (
        vehicle_models[
            "generation_weight"
        ]
        .astype(float)
        .to_numpy()
    )

    model_total = float(
        model_probabilities.sum()
    )

    if model_total <= 0:
        raise ValueError(
            "Vehicle-model generation weights "
            "must sum to > 0"
        )

    model_probabilities = (
        model_probabilities
        / model_total
    )

    model_indices = (
        rng.choice(
            np.arange(
                len(
                    vehicle_models
                )
            ),
            size=customer_count,
            p=model_probabilities,
        )
    )

    # ========================================================
    # BUDGET BAND
    # ========================================================

    budget_labels = list(
        budget_weights.keys()
    )

    budget_probabilities = (
        np.asarray(
            list(
                budget_weights.values()
            ),
            dtype=float,
        )
    )

    budget_bands = (
        rng.choice(
            budget_labels,
            size=customer_count,
            p=budget_probabilities,
        )
    )

    # ========================================================
    # PURCHASE HORIZON
    #
    # Your YAML:
    #
    # normal(mean=30, std=18)
    # clipped to 1 - 120 days
    # ========================================================

    purchase_horizon_raw = (
        sample_distribution(
            purchase_horizon_spec,
            size=customer_count,
            rng=rng,
        )
    )

    purchase_horizon_days = (
        np.rint(
            np.asarray(
                purchase_horizon_raw,
                dtype=float,
            )
        )
        .astype(int)
    )

    horizon_min = int(
        purchase_horizon_spec.get(
            "min",
            1,
        )
    )

    horizon_max = int(
        purchase_horizon_spec.get(
            "max",
            120,
        )
    )

    purchase_horizon_days = (
        np.clip(
            purchase_horizon_days,
            horizon_min,
            horizon_max,
        )
    )

    # ========================================================
    # FINANCE REQUIRED
    #
    # YAML probability = 0.65
    # ========================================================

    finance_required = (
        rng.random(
            customer_count
        )
        < finance_probability
    )

    # ========================================================
    # EXCHANGE VEHICLE
    #
    # YAML probability = 0.32
    # ========================================================

    exchange_vehicle = (
        rng.random(
            customer_count
        )
        < exchange_probability
    )

    # ========================================================
    # TIME WINDOW
    # ========================================================

    (
        start,
        end,
        timezone,
    ) = _get_time_window(
        generation
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
    # BUILD CUSTOMER RECORDS
    # ========================================================

    rows: list[
        dict[str, Any]
    ] = []

    for index in range(
        customer_count
    ):

        city = (
            city_table.iloc[
                int(
                    city_indices[
                        index
                    ]
                )
            ]
        )

        model = (
            vehicle_models.iloc[
                int(
                    model_indices[
                        index
                    ]
                )
            ]
        )

        horizon_days = int(
            purchase_horizon_days[
                index
            ]
        )

        finance_flag = bool(
            finance_required[
                index
            ]
        )

        exchange_flag = bool(
            exchange_vehicle[
                index
            ]
        )

        rows.append(
            {
                "customer_id":
                    make_entity_id(
                        "customer",
                        index + 1,
                        width=6,
                    ),

                # --------------------------------------------
                # Geography
                # --------------------------------------------

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

                # --------------------------------------------
                # Vehicle preference
                # --------------------------------------------

                "preferred_vehicle_model_id":
                    str(
                        model[
                            "vehicle_model_id"
                        ]
                    ),

                "preferred_vehicle_model_name":
                    str(
                        model[
                            "model_name"
                        ]
                    ),

                # --------------------------------------------
                # Customer evidence
                # --------------------------------------------

                "budget_band":
                    str(
                        budget_bands[
                            index
                        ]
                    ),

                "purchase_horizon_days":
                    horizon_days,

                "finance_required":
                    finance_flag,

                "exchange_vehicle":
                    exchange_flag,

                "customer_segment":
                    _derive_customer_segment(
                        purchase_horizon_days=
                            horizon_days,

                        finance_required=
                            finance_flag,

                        exchange_vehicle=
                            exchange_flag,
                    ),

                # --------------------------------------------
                # Entity creation time
                # --------------------------------------------

                "created_at":
                    _random_datetime(
                        rng=rng,
                        start=start,
                        end=end,
                        timezone=timezone,
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

    customers = (
        pd.DataFrame(
            rows,
            columns=[
                "customer_id",

                "region_id",
                "region_name",

                "city_id",
                "city_name",

                "preferred_vehicle_model_id",
                "preferred_vehicle_model_name",

                "budget_band",
                "purchase_horizon_days",

                "finance_required",
                "exchange_vehicle",

                "customer_segment",
                "created_at",

                "data_origin",
                "generator_version",
            ],
        )
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    validate_customers(
        customers=customers,
        regions=regions,
        cities=cities,
        vehicle_models=vehicle_models,
        expected_count=customer_count,
        horizon_min=horizon_min,
        horizon_max=horizon_max,
    )

    return customers


# ============================================================
# VALIDATION
# ============================================================


def validate_customers(
    customers: pd.DataFrame,
    regions: pd.DataFrame,
    cities: pd.DataFrame,
    vehicle_models: pd.DataFrame,
    expected_count: int,
    horizon_min: int,
    horizon_max: int,
) -> None:
    """
    Validate customer records and foreign keys.
    """

    required_columns = {
        "customer_id",

        "region_id",
        "region_name",

        "city_id",
        "city_name",

        "preferred_vehicle_model_id",
        "preferred_vehicle_model_name",

        "budget_band",
        "purchase_horizon_days",

        "finance_required",
        "exchange_vehicle",

        "customer_segment",
        "created_at",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        .difference(
            customers.columns
        )
    )

    if missing:
        raise ValueError(
            "Customers DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if customers.empty:
        raise ValueError(
            "Customers DataFrame cannot be empty"
        )

    # --------------------------------------------------------
    # Count
    # --------------------------------------------------------

    if len(
        customers
    ) != expected_count:
        raise ValueError(
            f"Expected {expected_count} customers "
            f"but generated {len(customers)}"
        )

    # --------------------------------------------------------
    # Customer ID uniqueness
    # --------------------------------------------------------

    if customers[
        "customer_id"
    ].duplicated().any():
        raise ValueError(
            "Duplicate customer_id values found"
        )

    # --------------------------------------------------------
    # Null validation
    # --------------------------------------------------------

    if customers.isna().any().any():

        null_columns = (
            customers.columns[
                customers.isna().any()
            ]
            .tolist()
        )

        raise ValueError(
            "Customer data contains unexpected "
            "null values in: "
            + ", ".join(
                null_columns
            )
        )

    # ========================================================
    # FOREIGN KEYS
    # ========================================================

    valid_region_ids = set(
        regions[
            "region_id"
        ]
    )

    invalid_region_ids = (
        set(
            customers[
                "region_id"
            ]
        )
        .difference(
            valid_region_ids
        )
    )

    if invalid_region_ids:
        raise ValueError(
            "Customers reference invalid "
            "region IDs: "
            + ", ".join(
                sorted(
                    invalid_region_ids
                )
            )
        )

    valid_city_ids = set(
        cities[
            "city_id"
        ]
    )

    invalid_city_ids = (
        set(
            customers[
                "city_id"
            ]
        )
        .difference(
            valid_city_ids
        )
    )

    if invalid_city_ids:
        raise ValueError(
            "Customers reference invalid "
            "city IDs: "
            + ", ".join(
                sorted(
                    invalid_city_ids
                )
            )
        )

    valid_model_ids = set(
        vehicle_models[
            "vehicle_model_id"
        ]
    )

    invalid_model_ids = (
        set(
            customers[
                "preferred_vehicle_model_id"
            ]
        )
        .difference(
            valid_model_ids
        )
    )

    if invalid_model_ids:
        raise ValueError(
            "Customers reference invalid "
            "vehicle-model IDs: "
            + ", ".join(
                sorted(
                    invalid_model_ids
                )
            )
        )

    # ========================================================
    # CITY -> REGION CONSISTENCY
    # ========================================================

    city_lookup = {
        row.city_id: (
            row.city_name,
            row.region_id,
            row.region_name,
        )

        for row
        in cities.itertuples(
            index=False
        )
    }

    for customer in customers.itertuples(
        index=False
    ):

        (
            expected_city_name,
            expected_region_id,
            expected_region_name,
        ) = city_lookup[
            customer.city_id
        ]

        if (
            customer.city_name
            != expected_city_name
        ):
            raise ValueError(
                "city_name mismatch for "
                f"{customer.customer_id}"
            )

        if (
            customer.region_id
            != expected_region_id
        ):
            raise ValueError(
                "region_id mismatch for "
                f"{customer.customer_id}"
            )

        if (
            customer.region_name
            != expected_region_name
        ):
            raise ValueError(
                "region_name mismatch for "
                f"{customer.customer_id}"
            )

    # ========================================================
    # VEHICLE MODEL CONSISTENCY
    # ========================================================

    model_lookup = dict(
        zip(
            vehicle_models[
                "vehicle_model_id"
            ],
            vehicle_models[
                "model_name"
            ],
        )
    )

    for customer in customers.itertuples(
        index=False
    ):

        expected_model_name = (
            model_lookup[
                customer.
                preferred_vehicle_model_id
            ]
        )

        if (
            customer.
            preferred_vehicle_model_name
            != expected_model_name
        ):
            raise ValueError(
                "Vehicle-model name mismatch "
                f"for {customer.customer_id}"
            )

    # ========================================================
    # PURCHASE HORIZON
    # ========================================================

    horizons = pd.to_numeric(
        customers[
            "purchase_horizon_days"
        ],
        errors="raise",
    )

    if (
        (
            horizons
            < horizon_min
        )
        |
        (
            horizons
            > horizon_max
        )
    ).any():
        raise ValueError(
            "purchase_horizon_days contains "
            f"values outside "
            f"[{horizon_min}, {horizon_max}]"
        )

    # ========================================================
    # BOOLEAN FIELDS
    # ========================================================

    for column in (
        "finance_required",
        "exchange_vehicle",
    ):

        if not customers[
            column
        ].isin(
            [
                True,
                False,
            ]
        ).all():
            raise ValueError(
                f"{column} must contain "
                "only boolean values"
            )


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_customer_master(
    regions: pd.DataFrame,
    cities: pd.DataFrame,
    vehicle_models: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Public entry point later used by generate_all.py.
    """

    return generate_customers(
        regions=regions,
        cities=cities,
        vehicle_models=vehicle_models,
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

    (
        regions_df,
        cities_df,
    ) = generate_geography()

    vehicle_models_df = (
        generate_vehicle_models()
    )

    customers_df = (
        generate_customer_master(
            regions=regions_df,
            cities=cities_df,
            vehicle_models=
                vehicle_models_df,
        )
    )

    print(
        "\n=== CUSTOMERS SAMPLE ===\n"
    )

    print(
        customers_df
        .head(20)
        .to_string(
            index=False
        )
    )

    print(
        "\n=== CUSTOMERS BY REGION ===\n"
    )

    print(
        customers_df
        .groupby(
            "region_name"
        )
        .size()
        .reset_index(
            name="customer_count"
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== CUSTOMERS BY VEHICLE MODEL ===\n"
    )

    print(
        customers_df
        .groupby(
            "preferred_vehicle_model_name"
        )
        .size()
        .reset_index(
            name="customer_count"
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== CUSTOMERS BY BUDGET BAND ===\n"
    )

    print(
        customers_df
        .groupby(
            "budget_band"
        )
        .size()
        .reset_index(
            name="customer_count"
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== CUSTOMER DISTRIBUTION CHECK ===\n"
    )

    print(
        "Finance required rate:",
        round(
            customers_df[
                "finance_required"
            ].mean(),
            4,
        ),
    )

    print(
        "Exchange vehicle rate:",
        round(
            customers_df[
                "exchange_vehicle"
            ].mean(),
            4,
        ),
    )

    print(
        "Average purchase horizon:",
        round(
            customers_df[
                "purchase_horizon_days"
            ].mean(),
            2,
        ),
        "days",
    )

    print(
        "\nGenerated "
        f"{len(customers_df)} "
        "synthetic customers successfully."
    )