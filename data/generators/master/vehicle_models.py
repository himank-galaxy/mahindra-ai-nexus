"""
Vehicle Model master-data generator for Mahindra AI Nexus.

Generates:
- Vehicle model master records

This module DOES NOT write CSV files.
It only generates and validates a pandas DataFrame.

CSV writing will later be handled centrally by:
    data/scripts/generate_all.py

IMPORTANT:
Commercial values such as base price, margin and baseline rates
are synthetic engineering assumptions for the PoC.
They are NOT actual Mahindra business figures.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from data.generators.common.helpers import (
    load_generation_config,
    load_distribution_config,
)

from data.generators.common.ids import (
    make_vehicle_model_id,
)


# ============================================================
# SYNTHETIC VEHICLE MODEL METADATA
#
# These values are engineering assumptions for synthetic data.
# They are intentionally stable master/reference values.
# ============================================================

VEHICLE_MODEL_METADATA: dict[str, dict[str, Any]] = {

    "XUV700": {
        "segment": "SUV",
        "base_price": 2400000,
        "gross_margin_pct": 0.14,
        "typical_lead_to_booking_rate": 0.19,
        "typical_cancellation_rate": 0.065,
        "typical_finance_share": 0.68,
        "production_complexity": 0.85,
    },

    "Scorpio-N": {
        "segment": "SUV",
        "base_price": 2100000,
        "gross_margin_pct": 0.13,
        "typical_lead_to_booking_rate": 0.18,
        "typical_cancellation_rate": 0.060,
        "typical_finance_share": 0.66,
        "production_complexity": 0.78,
    },

    "Thar": {
        "segment": "Lifestyle SUV",
        "base_price": 1800000,
        "gross_margin_pct": 0.15,
        "typical_lead_to_booking_rate": 0.20,
        "typical_cancellation_rate": 0.070,
        "typical_finance_share": 0.60,
        "production_complexity": 0.72,
    },

    "Bolero": {
        "segment": "Utility Vehicle",
        "base_price": 1200000,
        "gross_margin_pct": 0.11,
        "typical_lead_to_booking_rate": 0.16,
        "typical_cancellation_rate": 0.050,
        "typical_finance_share": 0.72,
        "production_complexity": 0.55,
    },

    "XUV 3XO": {
        "segment": "Compact SUV",
        "base_price": 1400000,
        "gross_margin_pct": 0.12,
        "typical_lead_to_booking_rate": 0.18,
        "typical_cancellation_rate": 0.060,
        "typical_finance_share": 0.70,
        "production_complexity": 0.65,
    },
}


# ============================================================
# INTERNAL HELPERS
# ============================================================


def _normalize_weights(
    weights: Mapping[str, Any],
) -> dict[str, float]:
    """
    Validate and normalize model generation weights.

    Example:

        {
            "XUV700": 0.25,
            "Scorpio-N": 0.22,
            ...
        }

    Returned values always sum to 1.0.
    """

    if not weights:
        raise ValueError(
            "Vehicle model weights cannot be empty"
        )

    parsed: dict[str, float] = {}

    for model_name, value in weights.items():

        if (
            not isinstance(model_name, str)
            or not model_name.strip()
        ):
            raise ValueError(
                f"Invalid vehicle model name: {model_name!r}"
            )

        try:
            numeric_weight = float(value)

        except (TypeError, ValueError) as exc:

            raise TypeError(
                f"Generation weight for "
                f"{model_name!r} must be numeric"
            ) from exc

        if numeric_weight < 0:
            raise ValueError(
                f"Generation weight for "
                f"{model_name!r} cannot be negative"
            )

        parsed[
            model_name.strip()
        ] = numeric_weight

    total = sum(
        parsed.values()
    )

    if total <= 0:
        raise ValueError(
            "Vehicle model weights must "
            "have a positive total"
        )

    return {
        model_name: weight / total
        for model_name, weight
        in parsed.items()
    }


def _validate_rate(
    value: Any,
    field_name: str,
    model_name: str,
) -> float:
    """
    Validate a numeric value expected in [0, 1].
    """

    try:
        numeric = float(value)

    except (TypeError, ValueError) as exc:

        raise TypeError(
            f"{field_name} for {model_name} "
            f"must be numeric"
        ) from exc

    if not 0 <= numeric <= 1:
        raise ValueError(
            f"{field_name} for {model_name} "
            f"must be between 0 and 1. "
            f"Received {numeric}."
        )

    return numeric


# ============================================================
# GENERATOR
# ============================================================


def generate_vehicle_models(
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate vehicle-model master data.

    Expected columns:

        vehicle_model_id
        model_name
        segment
        base_price
        currency
        gross_margin_pct
        typical_lead_to_booking_rate
        typical_cancellation_rate
        typical_finance_share
        production_complexity
        generation_weight
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

    # --------------------------------------------------------
    # Read configured canonical vehicle models
    # --------------------------------------------------------

    try:
        configured_models = (
            generation[
                "master"
            ][
                "vehicle_models"
            ][
                "models"
            ]
        )

    except KeyError as exc:

        raise KeyError(
            "Missing configuration key: "
            "generation.master."
            "vehicle_models.models"
        ) from exc

    if not isinstance(
        configured_models,
        list,
    ):
        raise TypeError(
            "generation.master.vehicle_models.models "
            "must be a list"
        )

    if not configured_models:
        raise ValueError(
            "At least one vehicle model "
            "must be configured"
        )

    # Remove accidental spaces while preserving order.
    configured_models = [
        str(model).strip()
        for model in configured_models
    ]

    # --------------------------------------------------------
    # Duplicate model check
    # --------------------------------------------------------

    if (
        len(configured_models)
        != len(set(configured_models))
    ):
        raise ValueError(
            "Duplicate vehicle models found "
            "in generation.yaml"
        )

    # --------------------------------------------------------
    # Read generation weights
    # --------------------------------------------------------

    try:
        raw_weights = (
            distributions[
                "vehicle_models"
            ][
                "interest_weights"
            ]
        )

    except KeyError as exc:

        raise KeyError(
            "Missing configuration key: "
            "distributions.vehicle_models."
            "interest_weights"
        ) from exc

    if not isinstance(
        raw_weights,
        Mapping,
    ):
        raise TypeError(
            "distributions.vehicle_models."
            "interest_weights must be a mapping"
        )

    generation_weights = (
        _normalize_weights(
            raw_weights
        )
    )

    # --------------------------------------------------------
    # Check generation.yaml and distributions.yaml agree
    # --------------------------------------------------------

    configured_set = set(
        configured_models
    )

    weighted_set = set(
        generation_weights.keys()
    )

    missing_weights = (
        configured_set
        - weighted_set
    )

    extra_weights = (
        weighted_set
        - configured_set
    )

    if missing_weights:
        raise ValueError(
            "Missing vehicle-model generation weights "
            "for: "
            + ", ".join(
                sorted(
                    missing_weights
                )
            )
        )

    if extra_weights:
        raise ValueError(
            "distributions.yaml contains weights "
            "for vehicle models not present in "
            "generation.yaml: "
            + ", ".join(
                sorted(
                    extra_weights
                )
            )
        )

    # --------------------------------------------------------
    # Provenance
    # --------------------------------------------------------

    generator_version = str(
        generation.get(
            "generator_version",
            "1.0.0",
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

    # --------------------------------------------------------
    # Build vehicle records
    # --------------------------------------------------------

    rows: list[
        dict[str, Any]
    ] = []

    for model_name in configured_models:

        if (
            model_name
            not in VEHICLE_MODEL_METADATA
        ):
            raise KeyError(
                "No synthetic metadata is defined "
                f"for vehicle model {model_name!r}. "
                "Add it to VEHICLE_MODEL_METADATA."
            )

        metadata = (
            VEHICLE_MODEL_METADATA[
                model_name
            ]
        )

        rows.append(
            {
                "vehicle_model_id":
                    make_vehicle_model_id(
                        model_name
                    ),

                "model_name":
                    model_name,

                "segment":
                    metadata[
                        "segment"
                    ],

                "base_price":
                    int(
                        metadata[
                            "base_price"
                        ]
                    ),

                "currency":
                    "INR",

                "gross_margin_pct":
                    _validate_rate(
                        metadata[
                            "gross_margin_pct"
                        ],
                        "gross_margin_pct",
                        model_name,
                    ),

                "typical_lead_to_booking_rate":
                    _validate_rate(
                        metadata[
                            "typical_lead_to_booking_rate"
                        ],
                        (
                            "typical_lead_to_"
                            "booking_rate"
                        ),
                        model_name,
                    ),

                "typical_cancellation_rate":
                    _validate_rate(
                        metadata[
                            "typical_cancellation_rate"
                        ],
                        "typical_cancellation_rate",
                        model_name,
                    ),

                "typical_finance_share":
                    _validate_rate(
                        metadata[
                            "typical_finance_share"
                        ],
                        "typical_finance_share",
                        model_name,
                    ),

                "production_complexity":
                    _validate_rate(
                        metadata[
                            "production_complexity"
                        ],
                        "production_complexity",
                        model_name,
                    ),

                "generation_weight":
                    generation_weights[
                        model_name
                    ],

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    vehicle_models = pd.DataFrame(
        rows,
        columns=[
            "vehicle_model_id",
            "model_name",
            "segment",
            "base_price",
            "currency",
            "gross_margin_pct",
            "typical_lead_to_booking_rate",
            "typical_cancellation_rate",
            "typical_finance_share",
            "production_complexity",
            "generation_weight",
            "data_origin",
            "generator_version",
        ],
    )

    validate_vehicle_models(
        vehicle_models
    )

    return vehicle_models


# ============================================================
# VALIDATION
# ============================================================


def validate_vehicle_models(
    vehicle_models: pd.DataFrame,
) -> None:
    """
    Validate vehicle-model master data.
    """

    required_columns = {
        "vehicle_model_id",
        "model_name",
        "segment",
        "base_price",
        "currency",
        "gross_margin_pct",
        "typical_lead_to_booking_rate",
        "typical_cancellation_rate",
        "typical_finance_share",
        "production_complexity",
        "generation_weight",
        "data_origin",
        "generator_version",
    }

    missing_columns = (
        required_columns
        .difference(
            vehicle_models.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "Vehicle-model DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if vehicle_models.empty:
        raise ValueError(
            "Vehicle-model DataFrame "
            "cannot be empty"
        )

    # --------------------------------------------------------
    # Missing required values
    # --------------------------------------------------------

    required_non_null = [
        "vehicle_model_id",
        "model_name",
        "segment",
        "base_price",
        "currency",
    ]

    for column in required_non_null:

        if vehicle_models[
            column
        ].isna().any():

            raise ValueError(
                f"Missing values found "
                f"in {column}"
            )

    # --------------------------------------------------------
    # Duplicate IDs
    # --------------------------------------------------------

    if vehicle_models[
        "vehicle_model_id"
    ].duplicated().any():

        duplicates = (
            vehicle_models.loc[
                vehicle_models[
                    "vehicle_model_id"
                ].duplicated(
                    keep=False
                ),
                "vehicle_model_id",
            ]
            .tolist()
        )

        raise ValueError(
            "Duplicate vehicle_model_id "
            f"values found: {duplicates}"
        )

    # --------------------------------------------------------
    # Duplicate model names
    # --------------------------------------------------------

    if vehicle_models[
        "model_name"
    ].duplicated().any():

        duplicates = (
            vehicle_models.loc[
                vehicle_models[
                    "model_name"
                ].duplicated(
                    keep=False
                ),
                "model_name",
            ]
            .tolist()
        )

        raise ValueError(
            "Duplicate model names found: "
            f"{duplicates}"
        )

    # --------------------------------------------------------
    # Price validation
    # --------------------------------------------------------

    prices = pd.to_numeric(
        vehicle_models[
            "base_price"
        ],
        errors="raise",
    )

    if (
        prices <= 0
    ).any():
        raise ValueError(
            "All vehicle base prices "
            "must be > 0"
        )

    # --------------------------------------------------------
    # Rate/range validation
    # --------------------------------------------------------

    bounded_columns = [
        "gross_margin_pct",
        "typical_lead_to_booking_rate",
        "typical_cancellation_rate",
        "typical_finance_share",
        "production_complexity",
        "generation_weight",
    ]

    for column in bounded_columns:

        values = pd.to_numeric(
            vehicle_models[
                column
            ],
            errors="raise",
        )

        if (
            (values < 0)
            | (values > 1)
        ).any():

            raise ValueError(
                f"{column} must contain "
                "values between 0 and 1"
            )

    # --------------------------------------------------------
    # Generation weights must add to 1
    # --------------------------------------------------------

    total_weight = float(
        vehicle_models[
            "generation_weight"
        ].sum()
    )

    if abs(
        total_weight - 1.0
    ) > 1e-9:

        raise ValueError(
            "Vehicle generation weights "
            "must sum to 1.0. "
            f"Received {total_weight}."
        )

    # --------------------------------------------------------
    # Model IDs must match canonical ID helper
    # --------------------------------------------------------

    for row in vehicle_models.itertuples(
        index=False
    ):

        expected_id = (
            make_vehicle_model_id(
                row.model_name
            )
        )

        if (
            row.vehicle_model_id
            != expected_id
        ):

            raise ValueError(
                "Invalid vehicle_model_id "
                f"for {row.model_name}: "
                f"expected {expected_id}, "
                f"received "
                f"{row.vehicle_model_id}"
            )


# ============================================================
# LOCAL TEST
# ============================================================


if __name__ == "__main__":

    vehicle_models_df = (
        generate_vehicle_models()
    )

    print(
        "\n=== VEHICLE MODELS ===\n"
    )

    print(
        vehicle_models_df.to_string(
            index=False
        )
    )

    print(
        "\nGenerated "
        f"{len(vehicle_models_df)} "
        "vehicle models successfully."
    )