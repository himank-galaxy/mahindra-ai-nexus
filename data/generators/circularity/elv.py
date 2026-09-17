"""
Synthetic End-of-Life Vehicle (ELV) Assessment Generator
for Mahindra AI Nexus.

============================================================
PURPOSE
============================================================

Generate operational ELV assessment records that become the
evidence layer for the Circularity / RVSF / DMRV workflows.

Dependency chain:

    Geography
        +
    Vehicle Model Master
        ↓
    ELV Assessments
        ↓
    RVSF Job Cards
        ↓
    DMRV Records
        ↓
    Carbon Credit Listings


============================================================
IMPORTANT ARCHITECTURAL RULE
============================================================

This generator produces OBSERVED / ASSESSED operational data.

It DOES NOT generate runtime AI outputs such as:

    predicted recoverable value
    recovery probability
    recommended disposition
    recommended dismantling route
    recommended resale channel
    carbon-credit estimate
    confidence score
    model score

Those must later be derived by backend rules/models.

Likewise, hidden synthetic truth must NOT leak into this
runtime dataset.


============================================================
ACTUAL generation.yaml STRUCTURE
============================================================

circularity:

    elv_assessments:
        count: 750

    rvsf_job_cards:
        count: 1500

    dmrv_records:
        count: 3000

    carbon_credit_listings:
        count: 750


============================================================
ACTUAL distributions.yaml STRUCTURE
============================================================

circularity:

    vehicle_age_years:
        distribution: normal
        mean: 11
        std: 4
        min: 3
        max: 25

    condition_score:
        distribution: normal
        mean: 62
        std: 18
        min: 5
        max: 100

    document_completeness:
        distribution: beta_scaled
        alpha: 6.0
        beta: 2.0
        min: 0.2
        max: 1.0

    traceability_score:
        distribution: beta_scaled
        alpha: 7.0
        beta: 2.0
        min: 0.2
        max: 1.0

    buyer_demand_index:
        distribution: beta_scaled
        alpha: 4.0
        beta: 3.0
        min: 0.1
        max: 1.0


============================================================
ACTUAL VEHICLE MODEL MASTER
============================================================

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


============================================================
OUTPUT PRINCIPLES
============================================================

Allowed operational evidence includes:

    vehicle age
    odometer
    condition score
    body condition
    chassis condition
    powertrain condition
    interior condition
    document completeness
    traceability score
    buyer demand index
    reusable-parts assessment
    recyclable-material assessment
    vehicle mass
    inspection timestamp/location

These are inspection / operating observations.

The generator does NOT write CSV files.
generate_all.py will eventually export the returned DataFrame.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.helpers import (
    load_distribution_config,
    load_generation_config,
)

from data.generators.common.ids import generate_id

from data.generators.common.seed import (
    derive_seed,
    make_rng,
)


# ============================================================
# STATUS VALUES
# ============================================================

ASSESSMENT_STATUS_COMPLETED = "COMPLETED"

VALID_DOCUMENT_STATUSES = {
    "COMPLETE",
    "PARTIAL",
    "INCOMPLETE",
}

VALID_TRACEABILITY_STATUSES = {
    "VERIFIED",
    "PARTIAL",
    "LIMITED",
}

VALID_SOURCE_CHANNELS = {
    "OWNER_HANDOVER",
    "DEALER_TRADE_IN",
    "FLEET_RETIREMENT",
    "AUCTION",
}


# ============================================================
# SOURCE-CHANNEL MIX
#
# Synthetic engineering assumption only.
# NOT a Mahindra operational statistic.
# ============================================================

SOURCE_CHANNELS = [
    "OWNER_HANDOVER",
    "DEALER_TRADE_IN",
    "FLEET_RETIREMENT",
    "AUCTION",
]

SOURCE_CHANNEL_WEIGHTS = np.asarray(
    [
        0.42,
        0.24,
        0.22,
        0.12,
    ],
    dtype=float,
)


# ============================================================
# SEGMENT-LEVEL VEHICLE MASS ASSUMPTIONS
#
# Synthetic engineering assumptions only.
# They are used to create internally consistent material and
# dismantling evidence.
# ============================================================

SEGMENT_MASS_KG = {
    "SUV": 1850.0,
    "Lifestyle SUV": 1750.0,
    "Utility Vehicle": 1650.0,
    "Compact SUV": 1400.0,
}


# ============================================================
# APPROXIMATE ANNUAL UTILIZATION ASSUMPTIONS
#
# Synthetic engineering assumptions only.
# ============================================================

SEGMENT_ANNUAL_KM = {
    "SUV": 17000.0,
    "Lifestyle SUV": 14000.0,
    "Utility Vehicle": 22000.0,
    "Compact SUV": 16000.0,
}


# ============================================================
# HIDDEN / RUNTIME OUTPUTS THAT MUST NEVER APPEAR
# ============================================================

HIDDEN_RUNTIME_COLUMNS = {
    "predicted_recoverable_value",
    "predicted_recoverable_value_inr",

    "recoverable_value",
    "recoverable_value_inr",

    "true_recoverable_value",
    "true_recoverable_value_inr",

    "salvage_value",
    "salvage_value_inr",

    "predicted_resale_value",
    "predicted_resale_value_inr",

    "recovery_probability",
    "predicted_recovery_probability",

    "recommended_action",
    "recommended_disposition",
    "recommended_channel",
    "recommended_dismantling_route",

    "carbon_credit_estimate",
    "estimated_carbon_credits",
    "predicted_carbon_credits",

    "credit_value",
    "credit_value_inr",

    "confidence",
    "confidence_score",

    "model_score",
    "model_probability",

    "risk_score",
    "risk_band",

    "true_disposition",
    "true_recovery_rate",

    "target_recoverable_value",
    "target_disposition",
}


# ============================================================
# REQUIRED MASTER SCHEMAS
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

VEHICLE_MODEL_REQUIRED_COLUMNS: set[str] = {
    "vehicle_model_id",
    "model_name",
    "segment",

    "base_price",
    "currency",

    "generation_weight",

    "data_origin",
    "generator_version",
}


# ============================================================
# CONFIG HELPERS
# ============================================================


def _get_generation_window(
    generation: Mapping[str, Any],
) -> tuple[
    pd.Timestamp,
    pd.Timestamp,
    str,
]:
    """
    Return timezone-aware generation boundaries.
    """

    try:
        time_config = generation["time"]

        start_value = time_config["start_date"]
        end_value = time_config["end_date"]

        timezone = str(
            time_config.get(
                "timezone",
                "Asia/Kolkata",
            )
        )

    except KeyError as exc:
        raise KeyError(
            "Missing generation.time configuration"
        ) from exc

    start = pd.Timestamp(start_value)
    end = pd.Timestamp(end_value)

    if start.tzinfo is None:
        start = start.tz_localize(timezone)
    else:
        start = start.tz_convert(timezone)

    if end.tzinfo is None:
        end = end.tz_localize(timezone)
    else:
        end = end.tz_convert(timezone)

    if end <= start:
        raise ValueError(
            "generation.time.end_date must be "
            "after generation.time.start_date"
        )

    return (
        start,
        end,
        timezone,
    )


def _get_elv_count(
    generation: Mapping[str, Any],
) -> int:
    """
    Read:

        circularity:
            elv_assessments:
                count: 750
    """

    try:
        count = int(
            generation[
                "circularity"
            ][
                "elv_assessments"
            ][
                "count"
            ]
        )

    except KeyError as exc:
        raise KeyError(
            "Missing "
            "generation.circularity."
            "elv_assessments.count"
        ) from exc

    if count <= 0:
        raise ValueError(
            "generation.circularity."
            "elv_assessments.count must be > 0"
        )

    return count


def _get_circularity_distributions(
    distributions: Mapping[str, Any],
) -> Mapping[str, Any]:
    """
    Validate presence of required Circularity distributions.
    """

    try:
        circularity = distributions["circularity"]

    except KeyError as exc:
        raise KeyError(
            "Missing distributions.circularity"
        ) from exc

    required = {
        "vehicle_age_years",
        "condition_score",
        "document_completeness",
        "traceability_score",
        "buyer_demand_index",
    }

    missing = (
        required
        -
        set(circularity.keys())
    )

    if missing:
        raise KeyError(
            "Missing Circularity distributions: "
            +
            ", ".join(
                sorted(missing)
            )
        )

    return circularity


# ============================================================
# DISTRIBUTION SAMPLING
# ============================================================


def _sample_clipped_normal(
    rng: np.random.Generator,
    config: Mapping[str, Any],
    size: int,
) -> np.ndarray:
    """
    Sample a configured clipped normal distribution.
    """

    distribution_name = str(
        config.get(
            "distribution",
            "",
        )
    ).strip().lower()

    if distribution_name != "normal":
        raise ValueError(
            "Expected normal distribution, got: "
            f"{distribution_name!r}"
        )

    try:
        mean = float(config["mean"])
        std = float(config["std"])
        minimum = float(config["min"])
        maximum = float(config["max"])

    except KeyError as exc:
        raise KeyError(
            "Normal distribution requires "
            "mean/std/min/max"
        ) from exc

    if std <= 0:
        raise ValueError(
            "Normal distribution std must be > 0"
        )

    if maximum < minimum:
        raise ValueError(
            "Normal distribution max must be >= min"
        )

    values = rng.normal(
        loc=mean,
        scale=std,
        size=size,
    )

    return np.clip(
        values,
        minimum,
        maximum,
    )


def _sample_beta_scaled(
    rng: np.random.Generator,
    config: Mapping[str, Any],
    size: int,
) -> np.ndarray:
    """
    Sample configured beta distribution and scale it into
    [min, max].
    """

    distribution_name = str(
        config.get(
            "distribution",
            "",
        )
    ).strip().lower()

    if distribution_name != "beta_scaled":
        raise ValueError(
            "Expected beta_scaled distribution, got: "
            f"{distribution_name!r}"
        )

    try:
        alpha = float(config["alpha"])
        beta = float(config["beta"])

        minimum = float(config["min"])
        maximum = float(config["max"])

    except KeyError as exc:
        raise KeyError(
            "beta_scaled distribution requires "
            "alpha/beta/min/max"
        ) from exc

    if alpha <= 0 or beta <= 0:
        raise ValueError(
            "Beta alpha and beta must be > 0"
        )

    if maximum < minimum:
        raise ValueError(
            "Beta-scaled max must be >= min"
        )

    raw = rng.beta(
        a=alpha,
        b=beta,
        size=size,
    )

    return (
        minimum
        +
        raw
        *
        (
            maximum
            -
            minimum
        )
    )


# ============================================================
# MASTER VALIDATION
# ============================================================


def _prepare_regions(
    regions: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate region master.
    """

    if regions.empty:
        raise ValueError(
            "Regions DataFrame cannot be empty"
        )

    missing = (
        REGION_REQUIRED_COLUMNS
        -
        set(regions.columns)
    )

    if missing:
        raise ValueError(
            "Regions DataFrame missing columns: "
            +
            ", ".join(
                sorted(missing)
            )
        )

    result = regions.copy(
        deep=True
    )

    if (
        result[
            "region_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Regions contain missing region_id"
        )

    if (
        result[
            "region_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate region_id values found"
        )

    result[
        "generation_weight"
    ] = pd.to_numeric(
        result[
            "generation_weight"
        ],
        errors="raise",
    )

    if (
        result[
            "generation_weight"
        ]
        <= 0
    ).any():
        raise ValueError(
            "Region generation_weight must be positive"
        )

    return (
        result
        .sort_values(
            "region_id"
        )
        .reset_index(
            drop=True
        )
    )


def _prepare_cities(
    cities: pd.DataFrame,
    regions: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate city master and region FKs.
    """

    if cities.empty:
        raise ValueError(
            "Cities DataFrame cannot be empty"
        )

    missing = (
        CITY_REQUIRED_COLUMNS
        -
        set(cities.columns)
    )

    if missing:
        raise ValueError(
            "Cities DataFrame missing columns: "
            +
            ", ".join(
                sorted(missing)
            )
        )

    result = cities.copy(
        deep=True
    )

    if (
        result[
            "city_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Cities contain missing city_id"
        )

    if (
        result[
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
        ]
        .astype(str)
    )

    invalid_region_ids = (
        set(
            result[
                "region_id"
            ]
            .astype(str)
        )
        -
        valid_region_ids
    )

    if invalid_region_ids:
        raise ValueError(
            "Cities reference invalid regions: "
            +
            ", ".join(
                sorted(
                    invalid_region_ids
                )
            )
        )

    result[
        "generation_weight_within_region"
    ] = pd.to_numeric(
        result[
            "generation_weight_within_region"
        ],
        errors="raise",
    )

    if (
        result[
            "generation_weight_within_region"
        ]
        <= 0
    ).any():
        raise ValueError(
            "City generation weights must be positive"
        )

    return (
        result
        .sort_values(
            "city_id"
        )
        .reset_index(
            drop=True
        )
    )


def _prepare_vehicle_models(
    vehicle_models: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate frozen vehicle-model master.
    """

    if vehicle_models.empty:
        raise ValueError(
            "Vehicle models DataFrame cannot be empty"
        )

    missing = (
        VEHICLE_MODEL_REQUIRED_COLUMNS
        -
        set(vehicle_models.columns)
    )

    if missing:
        raise ValueError(
            "Vehicle models DataFrame missing columns: "
            +
            ", ".join(
                sorted(missing)
            )
        )

    result = vehicle_models.copy(
        deep=True
    )

    if (
        result[
            "vehicle_model_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Vehicle models contain missing vehicle_model_id"
        )

    if (
        result[
            "vehicle_model_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate vehicle_model_id values found"
        )

    result[
        "base_price"
    ] = pd.to_numeric(
        result[
            "base_price"
        ],
        errors="raise",
    )

    result[
        "generation_weight"
    ] = pd.to_numeric(
        result[
            "generation_weight"
        ],
        errors="raise",
    )

    if (
        result[
            "base_price"
        ]
        <= 0
    ).any():
        raise ValueError(
            "Vehicle-model base_price must be positive"
        )

    if (
        result[
            "generation_weight"
        ]
        <= 0
    ).any():
        raise ValueError(
            "Vehicle-model generation_weight "
            "must be positive"
        )

    unsupported_segments = (
        set(
            result[
                "segment"
            ]
            .astype(str)
        )
        -
        set(
            SEGMENT_MASS_KG.keys()
        )
    )

    if unsupported_segments:
        raise ValueError(
            "ELV generator has no engineering assumptions "
            "for vehicle segments: "
            +
            ", ".join(
                sorted(
                    unsupported_segments
                )
            )
        )

    return (
        result
        .sort_values(
            "vehicle_model_id"
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# CITY SAMPLING WEIGHTS
# ============================================================


def _build_city_probabilities(
    cities: pd.DataFrame,
    regions: pd.DataFrame,
) -> np.ndarray:
    """
    Construct city probabilities using:

        region generation_weight
        ×
        city generation_weight_within_region
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

    merged = cities.merge(
        region_weights,
        on="region_id",
        how="left",
        validate="many_to_one",
    )

    if (
        merged[
            "generation_weight"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Unable to resolve city region weights"
        )

    weights = (
        merged[
            "generation_weight"
        ]
        .to_numpy(
            dtype=float
        )
        *
        merged[
            "generation_weight_within_region"
        ]
        .to_numpy(
            dtype=float
        )
    )

    if weights.sum() <= 0:
        raise ValueError(
            "City generation weights sum to zero"
        )

    return (
        weights
        /
        weights.sum()
    )


# ============================================================
# DERIVED OPERATIONAL STATUS
# ============================================================


def _document_status(
    completeness: float,
) -> str:
    """
    Convert observed completeness ratio to operational status.
    """

    if completeness >= 0.85:
        return "COMPLETE"

    if completeness >= 0.55:
        return "PARTIAL"

    return "INCOMPLETE"


def _traceability_status(
    score: float,
) -> str:
    """
    Convert observed traceability score to status.
    """

    if score >= 0.82:
        return "VERIFIED"

    if score >= 0.55:
        return "PARTIAL"

    return "LIMITED"


# ============================================================
# CONDITION COMPONENT
# ============================================================


def _component_condition_score(
    rng: np.random.Generator,
    overall_condition: float,
    offset: float = 0.0,
    noise_std: float = 8.0,
) -> float:
    """
    Produce an inspection component score correlated with the
    overall observed condition score.
    """

    value = (
        overall_condition
        +
        offset
        +
        float(
            rng.normal(
                loc=0.0,
                scale=noise_std,
            )
        )
    )

    return float(
        np.clip(
            value,
            0.0,
            100.0,
        )
    )


# ============================================================
# ELV GENERATOR
# ============================================================


def generate_elv_assessments(
    vehicle_models: pd.DataFrame,
    cities: pd.DataFrame,
    regions: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate synthetic ELV assessment records.

    This is the public generator used later by generate_all.py.
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

    regions = (
        _prepare_regions(
            regions
        )
    )

    cities = (
        _prepare_cities(
            cities=cities,
            regions=regions,
        )
    )

    vehicle_models = (
        _prepare_vehicle_models(
            vehicle_models
        )
    )

    # ========================================================
    # CONFIG
    # ========================================================

    (
        generation_start,
        generation_end,
        timezone,
    ) = (
        _get_generation_window(
            generation
        )
    )

    elv_count = (
        _get_elv_count(
            generation
        )
    )

    circularity_distributions = (
        _get_circularity_distributions(
            distributions
        )
    )

    # ========================================================
    # RNG
    # ========================================================

    try:
        base_seed = int(
            generation["seed"]
        )

    except KeyError as exc:
        raise KeyError(
            "Missing generation.seed"
        ) from exc

    rng = make_rng(
        derive_seed(
            base_seed,
            "circularity.elv",
        )
    )

    # ========================================================
    # PROVENANCE
    # ========================================================

    data_origin = str(
        generation.get(
            "provenance",
            {},
        ).get(
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
    # MASTER SAMPLING
    # ========================================================

    model_weights = (
        vehicle_models[
            "generation_weight"
        ]
        .to_numpy(
            dtype=float
        )
    )

    model_weights = (
        model_weights
        /
        model_weights.sum()
    )

    model_positions = rng.choice(
        np.arange(
            len(vehicle_models)
        ),
        size=elv_count,
        replace=True,
        p=model_weights,
    )

    city_probabilities = (
        _build_city_probabilities(
            cities=cities,
            regions=regions,
        )
    )

    city_positions = rng.choice(
        np.arange(
            len(cities)
        ),
        size=elv_count,
        replace=True,
        p=city_probabilities,
    )

    source_channel_positions = rng.choice(
        np.arange(
            len(SOURCE_CHANNELS)
        ),
        size=elv_count,
        replace=True,
        p=SOURCE_CHANNEL_WEIGHTS,
    )

    # ========================================================
    # CORE DISTRIBUTIONS
    # ========================================================

    raw_vehicle_age = (
        _sample_clipped_normal(
            rng=rng,
            config=circularity_distributions[
                "vehicle_age_years"
            ],
            size=elv_count,
        )
    )

    vehicle_age_years = np.rint(
        raw_vehicle_age
    ).astype(int)

    vehicle_age_config = (
        circularity_distributions[
            "vehicle_age_years"
        ]
    )

    minimum_age = int(
        vehicle_age_config["min"]
    )

    maximum_age = int(
        vehicle_age_config["max"]
    )

    vehicle_age_years = np.clip(
        vehicle_age_years,
        minimum_age,
        maximum_age,
    )

    base_condition_scores = (
        _sample_clipped_normal(
            rng=rng,
            config=circularity_distributions[
                "condition_score"
            ],
            size=elv_count,
        )
    )

    document_completeness_values = (
        _sample_beta_scaled(
            rng=rng,
            config=circularity_distributions[
                "document_completeness"
            ],
            size=elv_count,
        )
    )

    raw_traceability_values = (
        _sample_beta_scaled(
            rng=rng,
            config=circularity_distributions[
                "traceability_score"
            ],
            size=elv_count,
        )
    )

    buyer_demand_values = (
        _sample_beta_scaled(
            rng=rng,
            config=circularity_distributions[
                "buyer_demand_index"
            ],
            size=elv_count,
        )
    )

    # Correlate traceability modestly with actual document
    # completeness while retaining its configured distribution.
    traceability_values = (
        0.78
        *
        raw_traceability_values
        +
        0.22
        *
        document_completeness_values
    )

    traceability_config = (
        circularity_distributions[
            "traceability_score"
        ]
    )

    traceability_values = np.clip(
        traceability_values,
        float(
            traceability_config["min"]
        ),
        float(
            traceability_config["max"]
        ),
    )

    # ========================================================
    # ASSESSMENT TIMESTAMPS
    # ========================================================

    window_seconds = (
        generation_end
        -
        generation_start
    ).total_seconds()

    assessment_offsets = np.sort(
        rng.uniform(
            low=0.0,
            high=window_seconds,
            size=elv_count,
        )
    )

    rows: list[
        dict[str, Any]
    ] = []

    # ========================================================
    # GENERATE ELV RECORDS
    # ========================================================

    for index in range(
        elv_count
    ):
        model = vehicle_models.iloc[
            int(
                model_positions[index]
            )
        ]

        city = cities.iloc[
            int(
                city_positions[index]
            )
        ]

        age_years = int(
            vehicle_age_years[index]
        )

        segment = str(
            model["segment"]
        )

        source_channel = str(
            SOURCE_CHANNELS[
                int(
                    source_channel_positions[index]
                )
            ]
        )

        assessment_at = (
            generation_start
            +
            pd.Timedelta(
                seconds=float(
                    assessment_offsets[index]
                )
            )
        )

        assessment_at = (
            assessment_at
            .tz_convert(
                timezone
            )
        )

        # ====================================================
        # MANUFACTURE YEAR
        # ====================================================

        manufacture_year = int(
            assessment_at.year
            -
            age_years
        )

        # ====================================================
        # ODOMETER
        # ====================================================

        annual_km_baseline = float(
            SEGMENT_ANNUAL_KM[
                segment
            ]
        )

        annual_usage_factor = float(
            np.clip(
                rng.lognormal(
                    mean=0.0,
                    sigma=0.28,
                ),
                0.50,
                1.80,
            )
        )

        odometer_km = int(
            round(
                age_years
                *
                annual_km_baseline
                *
                annual_usage_factor
            )
        )

        odometer_km = int(
            np.clip(
                odometer_km,
                12000,
                650000,
            )
        )

        # ====================================================
        # ACCIDENT / DAMAGE OBSERVATIONS
        # ====================================================

        accident_lambda = (
            0.05
            *
            age_years
        )

        accident_history_count = int(
            np.clip(
                rng.poisson(
                    accident_lambda
                ),
                0,
                6,
            )
        )

        major_accident_probability = float(
            np.clip(
                0.035
                +
                0.055
                *
                accident_history_count,
                0.035,
                0.33,
            )
        )

        major_accident_flag = bool(
            rng.random()
            <
            major_accident_probability
        )

        # Small synthetic environmental exposure indicator.
        flood_exposure_flag = bool(
            rng.random()
            <
            0.035
        )

        # ====================================================
        # OVERALL CONDITION
        #
        # Start from configured condition distribution, then
        # apply modest observable age/use/damage effects.
        # ====================================================

        condition_score = float(
            base_condition_scores[index]
        )

        age_deviation = (
            age_years
            -
            float(
                circularity_distributions[
                    "vehicle_age_years"
                ][
                    "mean"
                ]
            )
        )

        condition_score -= (
            2.25
            *
            max(
                age_deviation,
                0.0,
            )
        )

        expected_odometer = max(
            1.0,
            age_years
            *
            annual_km_baseline
        )

        odometer_ratio = (
            odometer_km
            /
            expected_odometer
        )

        if odometer_ratio > 1.0:
            condition_score -= (
                5.0
                *
                (
                    odometer_ratio
                    -
                    1.0
                )
            )

        condition_score -= (
            2.5
            *
            accident_history_count
        )

        if major_accident_flag:
            condition_score -= 9.0

        if flood_exposure_flag:
            condition_score -= 7.0

        condition_config = (
            circularity_distributions[
                "condition_score"
            ]
        )

        condition_score = float(
            np.clip(
                condition_score,
                float(
                    condition_config["min"]
                ),
                float(
                    condition_config["max"]
                ),
            )
        )

        # ====================================================
        # COMPONENT CONDITION
        # ====================================================

        body_condition_score = (
            _component_condition_score(
                rng=rng,
                overall_condition=condition_score,
                offset=(
                    -7.0
                    if major_accident_flag
                    else 0.0
                ),
            )
        )

        chassis_integrity_score = (
            _component_condition_score(
                rng=rng,
                overall_condition=condition_score,
                offset=(
                    -10.0
                    if major_accident_flag
                    else 2.0
                ),
                noise_std=6.5,
            )
        )

        powertrain_condition_score = (
            _component_condition_score(
                rng=rng,
                overall_condition=condition_score,
                offset=(
                    -5.0
                    if flood_exposure_flag
                    else 1.5
                ),
                noise_std=7.0,
            )
        )

        interior_condition_score = (
            _component_condition_score(
                rng=rng,
                overall_condition=condition_score,
                offset=-1.0,
                noise_std=9.0,
            )
        )

        engine_operable_probability = float(
            np.clip(
                0.15
                +
                0.0085
                *
                powertrain_condition_score,
                0.15,
                0.97,
            )
        )

        engine_operable = bool(
            rng.random()
            <
            engine_operable_probability
        )

        # ====================================================
        # DOCUMENT / TRACEABILITY
        # ====================================================

        document_completeness = float(
            document_completeness_values[
                index
            ]
        )

        traceability_score = float(
            traceability_values[
                index
            ]
        )

        buyer_demand_index = float(
            buyer_demand_values[
                index
            ]
        )

        document_status = (
            _document_status(
                document_completeness
            )
        )

        traceability_status = (
            _traceability_status(
                traceability_score
            )
        )

        # ====================================================
        # VEHICLE MASS
        # ====================================================

        base_mass_kg = float(
            SEGMENT_MASS_KG[
                segment
            ]
        )

        estimated_vehicle_mass_kg = float(
            np.clip(
                rng.normal(
                    loc=base_mass_kg,
                    scale=(
                        0.055
                        *
                        base_mass_kg
                    ),
                ),
                1100.0,
                2300.0,
            )
        )

        # ====================================================
        # REUSABLE-PARTS ASSESSMENT
        #
        # Inspector-style operational estimate.
        # Not hidden truth and not monetary valuation.
        # ====================================================

        condition_fraction = (
            condition_score
            /
            100.0
        )

        powertrain_fraction = (
            powertrain_condition_score
            /
            100.0
        )

        chassis_fraction = (
            chassis_integrity_score
            /
            100.0
        )

        reusable_parts_pct = (
            0.08
            +
            0.34
            *
            condition_fraction
            +
            0.10
            *
            powertrain_fraction
            +
            0.08
            *
            buyer_demand_index
            +
            float(
                rng.normal(
                    loc=0.0,
                    scale=0.035,
                )
            )
        )

        if major_accident_flag:
            reusable_parts_pct -= 0.06

        if flood_exposure_flag:
            reusable_parts_pct -= 0.05

        reusable_parts_pct = float(
            np.clip(
                reusable_parts_pct,
                0.05,
                0.72,
            )
        )

        # ====================================================
        # RECYCLABLE-MATERIAL ASSESSMENT
        #
        # This represents technical recyclability of material
        # after reusable components are removed.
        # ====================================================

        recyclable_material_pct = (
            0.70
            +
            0.11
            *
            traceability_score
            +
            0.05
            *
            chassis_fraction
            +
            float(
                rng.normal(
                    loc=0.0,
                    scale=0.025,
                )
            )
        )

        recyclable_material_pct = float(
            np.clip(
                recyclable_material_pct,
                0.65,
                0.94,
            )
        )

        # ====================================================
        # OBSERVED MATERIAL / FLUID HANDLING FLAGS
        # ====================================================

        battery_present = bool(
            rng.random()
            <
            0.94
        )

        tyre_set_present = bool(
            rng.random()
            <
            0.97
        )

        catalytic_converter_present = bool(
            rng.random()
            <
            0.91
        )

        hazardous_fluids_present = bool(
            rng.random()
            <
            0.96
        )

        # ====================================================
        # OUTPUT
        # ====================================================

        rows.append(
            {
                # --------------------------------------------
                # PK / Synthetic asset identifier
                # --------------------------------------------

                "elv_assessment_id":
                    generate_id(
                        "ELV_SYN",
                        index + 1,
                        width=6,
                    ),

                "elv_vehicle_id":
                    generate_id(
                        "ELVVEH_SYN",
                        index + 1,
                        width=6,
                    ),

                # --------------------------------------------
                # Vehicle model
                # --------------------------------------------

                "vehicle_model_id":
                    str(
                        model[
                            "vehicle_model_id"
                        ]
                    ),

                "model_name":
                    str(
                        model[
                            "model_name"
                        ]
                    ),

                "segment":
                    segment,

                # --------------------------------------------
                # Geography
                # --------------------------------------------

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

                # --------------------------------------------
                # Assessment
                # --------------------------------------------

                "assessment_at":
                    assessment_at,

                "assessment_status":
                    ASSESSMENT_STATUS_COMPLETED,

                "source_channel":
                    source_channel,

                # --------------------------------------------
                # Vehicle age / use
                # --------------------------------------------

                "manufacture_year":
                    manufacture_year,

                "vehicle_age_years":
                    age_years,

                "odometer_km":
                    odometer_km,

                # --------------------------------------------
                # Damage / operating history
                # --------------------------------------------

                "accident_history_count":
                    accident_history_count,

                "major_accident_flag":
                    major_accident_flag,

                "flood_exposure_flag":
                    flood_exposure_flag,

                # --------------------------------------------
                # Condition inspection
                # --------------------------------------------

                "condition_score":
                    round(
                        condition_score,
                        2,
                    ),

                "body_condition_score":
                    round(
                        body_condition_score,
                        2,
                    ),

                "chassis_integrity_score":
                    round(
                        chassis_integrity_score,
                        2,
                    ),

                "powertrain_condition_score":
                    round(
                        powertrain_condition_score,
                        2,
                    ),

                "interior_condition_score":
                    round(
                        interior_condition_score,
                        2,
                    ),

                "engine_operable":
                    engine_operable,

                # --------------------------------------------
                # Documentation / provenance evidence
                # --------------------------------------------

                "document_completeness":
                    round(
                        document_completeness,
                        4,
                    ),

                "document_status":
                    document_status,

                "traceability_score":
                    round(
                        traceability_score,
                        4,
                    ),

                "traceability_status":
                    traceability_status,

                # --------------------------------------------
                # Market evidence
                # --------------------------------------------

                "buyer_demand_index":
                    round(
                        buyer_demand_index,
                        4,
                    ),

                # --------------------------------------------
                # Circularity inspection evidence
                # --------------------------------------------

                "estimated_vehicle_mass_kg":
                    round(
                        estimated_vehicle_mass_kg,
                        2,
                    ),

                "assessed_reusable_parts_pct":
                    round(
                        reusable_parts_pct,
                        4,
                    ),

                "assessed_recyclable_material_pct":
                    round(
                        recyclable_material_pct,
                        4,
                    ),

                "battery_present":
                    battery_present,

                "tyre_set_present":
                    tyre_set_present,

                "catalytic_converter_present":
                    catalytic_converter_present,

                "hazardous_fluids_present":
                    hazardous_fluids_present,

                # --------------------------------------------
                # Provenance
                # --------------------------------------------

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    elv = pd.DataFrame(
        rows
    )

    # ========================================================
    # VALIDATE
    # ========================================================

    validate_elv_assessments(
        elv=elv,

        vehicle_models=vehicle_models,
        cities=cities,
        regions=regions,

        generation_start=generation_start,
        generation_end=generation_end,

        expected_count=elv_count,

        circularity_distributions=
            circularity_distributions,
    )

    return elv


# ============================================================
# VALIDATION
# ============================================================


def validate_elv_assessments(
    elv: pd.DataFrame,
    vehicle_models: pd.DataFrame,
    cities: pd.DataFrame,
    regions: pd.DataFrame,
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
    expected_count: int,
    circularity_distributions: Mapping[str, Any],
) -> None:
    """
    Validate ELV operational-assessment integrity.
    """

    required_columns = {
        "elv_assessment_id",
        "elv_vehicle_id",

        "vehicle_model_id",
        "model_name",
        "segment",

        "city_id",
        "city_name",

        "region_id",
        "region_name",

        "assessment_at",
        "assessment_status",

        "source_channel",

        "manufacture_year",
        "vehicle_age_years",
        "odometer_km",

        "accident_history_count",
        "major_accident_flag",
        "flood_exposure_flag",

        "condition_score",
        "body_condition_score",
        "chassis_integrity_score",
        "powertrain_condition_score",
        "interior_condition_score",

        "engine_operable",

        "document_completeness",
        "document_status",

        "traceability_score",
        "traceability_status",

        "buyer_demand_index",

        "estimated_vehicle_mass_kg",

        "assessed_reusable_parts_pct",
        "assessed_recyclable_material_pct",

        "battery_present",
        "tyre_set_present",
        "catalytic_converter_present",
        "hazardous_fluids_present",

        "data_origin",
        "generator_version",
    }

    missing_columns = (
        required_columns
        -
        set(elv.columns)
    )

    if missing_columns:
        raise ValueError(
            "ELV assessments missing columns: "
            +
            ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if elv.empty:
        raise ValueError(
            "ELV generator produced zero rows"
        )

    # ========================================================
    # EXACT COUNT
    # ========================================================

    if (
        len(elv)
        !=
        expected_count
    ):
        raise ValueError(
            "Unexpected ELV assessment count. "
            f"Expected={expected_count}, "
            f"actual={len(elv)}"
        )

    # ========================================================
    # PK / ASSET IDS
    # ========================================================

    if (
        elv[
            "elv_assessment_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "ELV assessments contain missing IDs"
        )

    if (
        elv[
            "elv_assessment_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate elv_assessment_id values found"
        )

    if (
        elv[
            "elv_vehicle_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate elv_vehicle_id values found"
        )

    # ========================================================
    # VEHICLE MODEL FK
    # ========================================================

    valid_model_ids = set(
        vehicle_models[
            "vehicle_model_id"
        ]
        .astype(str)
    )

    invalid_model_ids = (
        set(
            elv[
                "vehicle_model_id"
            ]
            .astype(str)
        )
        -
        valid_model_ids
    )

    if invalid_model_ids:
        raise ValueError(
            "ELV assessments reference invalid "
            "vehicle models"
        )

    # ========================================================
    # MODEL METADATA CONSISTENCY
    # ========================================================

    model_lookup = (
        vehicle_models
        .set_index(
            "vehicle_model_id"
        )
    )

    for record in elv.itertuples(
        index=False
    ):
        model = model_lookup.loc[
            str(
                record.vehicle_model_id
            )
        ]

        if (
            str(
                record.model_name
            )
            !=
            str(
                model[
                    "model_name"
                ]
            )
        ):
            raise ValueError(
                f"{record.elv_assessment_id}: "
                "model_name does not match "
                "vehicle-model master"
            )

        if (
            str(
                record.segment
            )
            !=
            str(
                model[
                    "segment"
                ]
            )
        ):
            raise ValueError(
                f"{record.elv_assessment_id}: "
                "segment does not match "
                "vehicle-model master"
            )

    # ========================================================
    # CITY / REGION FK
    # ========================================================

    valid_city_ids = set(
        cities[
            "city_id"
        ]
        .astype(str)
    )

    invalid_city_ids = (
        set(
            elv[
                "city_id"
            ]
            .astype(str)
        )
        -
        valid_city_ids
    )

    if invalid_city_ids:
        raise ValueError(
            "ELV assessments reference invalid cities"
        )

    valid_region_ids = set(
        regions[
            "region_id"
        ]
        .astype(str)
    )

    invalid_region_ids = (
        set(
            elv[
                "region_id"
            ]
            .astype(str)
        )
        -
        valid_region_ids
    )

    if invalid_region_ids:
        raise ValueError(
            "ELV assessments reference invalid regions"
        )

    # ========================================================
    # CITY ↔ REGION CONSISTENCY
    # ========================================================

    city_lookup = (
        cities
        .set_index(
            "city_id"
        )
    )

    for record in elv.itertuples(
        index=False
    ):
        city = city_lookup.loc[
            str(
                record.city_id
            )
        ]

        if (
            str(
                record.region_id
            )
            !=
            str(
                city[
                    "region_id"
                ]
            )
        ):
            raise ValueError(
                f"{record.elv_assessment_id}: "
                "region_id inconsistent with city"
            )

        if (
            str(
                record.city_name
            )
            !=
            str(
                city[
                    "city_name"
                ]
            )
        ):
            raise ValueError(
                f"{record.elv_assessment_id}: "
                "city_name inconsistent with city master"
            )

        if (
            str(
                record.region_name
            )
            !=
            str(
                city[
                    "region_name"
                ]
            )
        ):
            raise ValueError(
                f"{record.elv_assessment_id}: "
                "region_name inconsistent with city master"
            )

    # ========================================================
    # TIME WINDOW
    # ========================================================

    assessment_at = pd.to_datetime(
        elv[
            "assessment_at"
        ],
        utc=True,
    )

    generation_start_utc = (
        generation_start
        .tz_convert("UTC")
    )

    generation_end_utc = (
        generation_end
        .tz_convert("UTC")
    )

    if (
        assessment_at
        <
        generation_start_utc
    ).any():
        raise ValueError(
            "ELV assessment occurs before generation start"
        )

    if (
        assessment_at
        >=
        generation_end_utc
    ).any():
        raise ValueError(
            "ELV assessment occurs on/after generation end"
        )

    # ========================================================
    # STATUS
    # ========================================================

    if (
        set(
            elv[
                "assessment_status"
            ]
            .astype(str)
        )
        !=
        {
            ASSESSMENT_STATUS_COMPLETED
        }
    ):
        raise ValueError(
            "Historical ELV assessments must have "
            "COMPLETED status"
        )

    # ========================================================
    # SOURCE CHANNEL
    # ========================================================

    invalid_source_channels = (
        set(
            elv[
                "source_channel"
            ]
            .astype(str)
        )
        -
        VALID_SOURCE_CHANNELS
    )

    if invalid_source_channels:
        raise ValueError(
            "Invalid ELV source channels: "
            +
            ", ".join(
                sorted(
                    invalid_source_channels
                )
            )
        )

    # ========================================================
    # VEHICLE AGE
    # ========================================================

    age_config = (
        circularity_distributions[
            "vehicle_age_years"
        ]
    )

    age_values = pd.to_numeric(
        elv[
            "vehicle_age_years"
        ],
        errors="raise",
    )

    if (
        age_values
        <
        float(
            age_config["min"]
        )
    ).any():
        raise ValueError(
            "vehicle_age_years below configured minimum"
        )

    if (
        age_values
        >
        float(
            age_config["max"]
        )
    ).any():
        raise ValueError(
            "vehicle_age_years above configured maximum"
        )

    # ========================================================
    # MANUFACTURE YEAR
    # ========================================================

    local_assessment_year = (
        pd.to_datetime(
            elv[
                "assessment_at"
            ],
            utc=True,
        )
        .dt
        .tz_convert(
            "Asia/Kolkata"
        )
        .dt
        .year
    )

    expected_manufacture_year = (
        local_assessment_year
        -
        age_values.astype(int)
    )

    if not np.array_equal(
        expected_manufacture_year.to_numpy(
            dtype=int
        ),
        elv[
            "manufacture_year"
        ]
        .to_numpy(
            dtype=int
        ),
    ):
        raise ValueError(
            "manufacture_year inconsistent with "
            "vehicle_age_years"
        )

    # ========================================================
    # ODOMETER
    # ========================================================

    odometer_values = pd.to_numeric(
        elv[
            "odometer_km"
        ],
        errors="raise",
    )

    if (
        odometer_values
        <= 0
    ).any():
        raise ValueError(
            "odometer_km must be positive"
        )

    # ========================================================
    # ACCIDENT HISTORY
    # ========================================================

    accident_counts = pd.to_numeric(
        elv[
            "accident_history_count"
        ],
        errors="raise",
    )

    if (
        accident_counts
        <
        0
    ).any():
        raise ValueError(
            "accident_history_count cannot be negative"
        )

    # ========================================================
    # CONDITION SCORES
    # ========================================================

    condition_config = (
        circularity_distributions[
            "condition_score"
        ]
    )

    condition_values = pd.to_numeric(
        elv[
            "condition_score"
        ],
        errors="raise",
    )

    if (
        condition_values
        <
        float(
            condition_config["min"]
        )
    ).any():
        raise ValueError(
            "condition_score below configured minimum"
        )

    if (
        condition_values
        >
        float(
            condition_config["max"]
        )
    ).any():
        raise ValueError(
            "condition_score above configured maximum"
        )

    component_columns = (
        "body_condition_score",
        "chassis_integrity_score",
        "powertrain_condition_score",
        "interior_condition_score",
    )

    for column in component_columns:
        values = pd.to_numeric(
            elv[column],
            errors="raise",
        )

        if (
            (values < 0)
            |
            (values > 100)
        ).any():
            raise ValueError(
                f"{column} must be between 0 and 100"
            )

    # ========================================================
    # CONFIGURED 0–1 DISTRIBUTIONS
    # ========================================================

    bounded_distribution_columns = {
        "document_completeness":
            "document_completeness",

        "traceability_score":
            "traceability_score",

        "buyer_demand_index":
            "buyer_demand_index",
    }

    for (
        column,
        config_name,
    ) in bounded_distribution_columns.items():
        values = pd.to_numeric(
            elv[column],
            errors="raise",
        )

        config = (
            circularity_distributions[
                config_name
            ]
        )

        minimum = float(
            config["min"]
        )

        maximum = float(
            config["max"]
        )

        if (
            (values < minimum)
            |
            (values > maximum)
        ).any():
            raise ValueError(
                f"{column} outside configured bounds"
            )

    # ========================================================
    # DOCUMENT STATUS DERIVATION
    # ========================================================

    calculated_document_status = (
        elv[
            "document_completeness"
        ]
        .map(
            _document_status
        )
    )

    if not np.array_equal(
        calculated_document_status.to_numpy(
            dtype=object
        ),
        elv[
            "document_status"
        ]
        .to_numpy(
            dtype=object
        ),
    ):
        raise ValueError(
            "document_status inconsistent with "
            "document_completeness"
        )

    invalid_document_statuses = (
        set(
            elv[
                "document_status"
            ]
            .astype(str)
        )
        -
        VALID_DOCUMENT_STATUSES
    )

    if invalid_document_statuses:
        raise ValueError(
            "Invalid document statuses"
        )

    # ========================================================
    # TRACEABILITY STATUS DERIVATION
    # ========================================================

    calculated_traceability_status = (
        elv[
            "traceability_score"
        ]
        .map(
            _traceability_status
        )
    )

    if not np.array_equal(
        calculated_traceability_status.to_numpy(
            dtype=object
        ),
        elv[
            "traceability_status"
        ]
        .to_numpy(
            dtype=object
        ),
    ):
        raise ValueError(
            "traceability_status inconsistent with "
            "traceability_score"
        )

    invalid_traceability_statuses = (
        set(
            elv[
                "traceability_status"
            ]
            .astype(str)
        )
        -
        VALID_TRACEABILITY_STATUSES
    )

    if invalid_traceability_statuses:
        raise ValueError(
            "Invalid traceability statuses"
        )

    # ========================================================
    # VEHICLE MASS
    # ========================================================

    mass_values = pd.to_numeric(
        elv[
            "estimated_vehicle_mass_kg"
        ],
        errors="raise",
    )

    if (
        (mass_values < 1000)
        |
        (mass_values > 2500)
    ).any():
        raise ValueError(
            "estimated_vehicle_mass_kg outside "
            "supported synthetic range"
        )

    # ========================================================
    # CIRCULARITY INSPECTION RATIOS
    # ========================================================

    for column in (
        "assessed_reusable_parts_pct",
        "assessed_recyclable_material_pct",
    ):
        values = pd.to_numeric(
            elv[column],
            errors="raise",
        )

        if (
            (values < 0)
            |
            (values > 1)
        ).any():
            raise ValueError(
                f"{column} must be between 0 and 1"
            )

    # ========================================================
    # BOOLEAN FIELDS
    # ========================================================

    boolean_columns = (
        "major_accident_flag",
        "flood_exposure_flag",

        "engine_operable",

        "battery_present",
        "tyre_set_present",
        "catalytic_converter_present",
        "hazardous_fluids_present",
    )

    for column in boolean_columns:
        if (
            ~elv[
                column
            ]
            .isin(
                [
                    True,
                    False,
                ]
            )
        ).any():
            raise ValueError(
                f"{column} must contain booleans only"
            )

    # ========================================================
    # PROVENANCE
    # ========================================================

    if (
        elv[
            "data_origin"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "ELV assessments contain missing data_origin"
        )

    if (
        elv[
            "generator_version"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "ELV assessments contain missing "
            "generator_version"
        )

    # ========================================================
    # HIDDEN TRUTH / RUNTIME LEAKAGE
    # ========================================================

    leaked_columns = (
        HIDDEN_RUNTIME_COLUMNS
        &
        set(elv.columns)
    )

    if leaked_columns:
        raise ValueError(
            "Hidden runtime / ground-truth fields leaked "
            "into ELV assessments: "
            +
            ", ".join(
                sorted(
                    leaked_columns
                )
            )
        )


# ============================================================
# CONVENIENCE ALIAS
# ============================================================


def generate_elv(
    vehicle_models: pd.DataFrame,
    cities: pd.DataFrame,
    regions: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Convenience alias.
    """

    return generate_elv_assessments(
        vehicle_models=vehicle_models,
        cities=cities,
        regions=regions,
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

    # ========================================================
    # CONFIG
    # ========================================================

    generation_config = (
        load_generation_config()
    )

    distribution_config = (
        load_distribution_config()
    )

    # ========================================================
    # MASTER DEPENDENCIES
    # ========================================================

    (
        regions_df,
        cities_df,
    ) = generate_geography()

    vehicle_models_df = (
        generate_vehicle_models(
            generation=generation_config,
            distributions=distribution_config,
        )
    )

    print(
        "\n=== ELV DEPENDENCY CHECK ===\n"
    )

    print(
        "Regions:",
        len(
            regions_df
        ),
    )

    print(
        "Cities:",
        len(
            cities_df
        ),
    )

    print(
        "Vehicle models:",
        len(
            vehicle_models_df
        ),
    )

    print(
        "Configured ELV assessments:",
        _get_elv_count(
            generation_config
        ),
    )

    # ========================================================
    # GENERATE
    # ========================================================

    elv_df = (
        generate_elv_assessments(
            vehicle_models=vehicle_models_df,
            cities=cities_df,
            regions=regions_df,

            generation=generation_config,
            distributions=distribution_config,
        )
    )

    # ========================================================
    # SAMPLE
    # ========================================================

    print(
        "\n=== ELV SAMPLE ===\n"
    )

    sample_columns = [
        "elv_assessment_id",
        "elv_vehicle_id",

        "model_name",
        "segment",

        "city_name",
        "region_name",

        "assessment_at",

        "manufacture_year",
        "vehicle_age_years",
        "odometer_km",

        "condition_score",
        "chassis_integrity_score",
        "powertrain_condition_score",

        "engine_operable",

        "document_completeness",
        "document_status",

        "traceability_score",
        "traceability_status",

        "buyer_demand_index",

        "estimated_vehicle_mass_kg",

        "assessed_reusable_parts_pct",
        "assessed_recyclable_material_pct",

        "major_accident_flag",
        "flood_exposure_flag",
    ]

    print(
        elv_df[
            sample_columns
        ]
        .head(40)
        .to_string(
            index=False
        )
    )

    # ========================================================
    # MODEL MIX
    # ========================================================

    print(
        "\n=== ELV MODEL MIX ===\n"
    )

    model_summary = (
        elv_df
        .groupby(
            [
                "vehicle_model_id",
                "model_name",
                "segment",
            ],
            as_index=False,
        )
        .agg(
            assessments=(
                "elv_assessment_id",
                "size",
            ),

            average_age_years=(
                "vehicle_age_years",
                "mean",
            ),

            average_condition=(
                "condition_score",
                "mean",
            ),

            average_reusable_parts_pct=(
                "assessed_reusable_parts_pct",
                "mean",
            ),
        )
        .sort_values(
            "assessments",
            ascending=False,
        )
    )

    for column in (
        "average_age_years",
        "average_condition",
        "average_reusable_parts_pct",
    ):
        model_summary[
            column
        ] = (
            model_summary[
                column
            ]
            .round(3)
        )

    print(
        model_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # REGION MIX
    # ========================================================

    print(
        "\n=== ELV REGION MIX ===\n"
    )

    region_summary = (
        elv_df[
            "region_name"
        ]
        .value_counts()
        .rename_axis(
            "region_name"
        )
        .reset_index(
            name="assessments"
        )
    )

    region_summary[
        "rate"
    ] = (
        region_summary[
            "assessments"
        ]
        /
        len(
            elv_df
        )
    ).round(4)

    print(
        region_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # SOURCE CHANNEL
    # ========================================================

    print(
        "\n=== ELV SOURCE CHANNEL MIX ===\n"
    )

    source_summary = (
        elv_df[
            "source_channel"
        ]
        .value_counts()
        .rename_axis(
            "source_channel"
        )
        .reset_index(
            name="assessments"
        )
    )

    source_summary[
        "rate"
    ] = (
        source_summary[
            "assessments"
        ]
        /
        len(
            elv_df
        )
    ).round(4)

    print(
        source_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # VEHICLE AGE / USAGE
    # ========================================================

    print(
        "\n=== ELV AGE / USAGE ===\n"
    )

    print(
        "Average vehicle age:",
        round(
            float(
                elv_df[
                    "vehicle_age_years"
                ]
                .mean()
            ),
            2,
        ),
    )

    print(
        "Minimum vehicle age:",
        int(
            elv_df[
                "vehicle_age_years"
            ]
            .min()
        ),
    )

    print(
        "Maximum vehicle age:",
        int(
            elv_df[
                "vehicle_age_years"
            ]
            .max()
        ),
    )

    print(
        "Average odometer km:",
        round(
            float(
                elv_df[
                    "odometer_km"
                ]
                .mean()
            ),
            2,
        ),
    )

    print(
        "Maximum odometer km:",
        int(
            elv_df[
                "odometer_km"
            ]
            .max()
        ),
    )

    # ========================================================
    # CONDITION
    # ========================================================

    print(
        "\n=== ELV CONDITION ===\n"
    )

    print(
        "Average condition score:",
        round(
            float(
                elv_df[
                    "condition_score"
                ]
                .mean()
            ),
            2,
        ),
    )

    print(
        "Minimum condition score:",
        round(
            float(
                elv_df[
                    "condition_score"
                ]
                .min()
            ),
            2,
        ),
    )

    print(
        "Maximum condition score:",
        round(
            float(
                elv_df[
                    "condition_score"
                ]
                .max()
            ),
            2,
        ),
    )

    print(
        "Engine operable rate:",
        round(
            float(
                elv_df[
                    "engine_operable"
                ]
                .mean()
            ),
            4,
        ),
    )

    print(
        "Major accident rate:",
        round(
            float(
                elv_df[
                    "major_accident_flag"
                ]
                .mean()
            ),
            4,
        ),
    )

    print(
        "Flood exposure rate:",
        round(
            float(
                elv_df[
                    "flood_exposure_flag"
                ]
                .mean()
            ),
            4,
        ),
    )

    # ========================================================
    # DOCUMENT / TRACEABILITY
    # ========================================================

    print(
        "\n=== ELV DOCUMENTATION / TRACEABILITY ===\n"
    )

    print(
        "Average document completeness:",
        round(
            float(
                elv_df[
                    "document_completeness"
                ]
                .mean()
            ),
            4,
        ),
    )

    print(
        "\nDocument status:"
    )

    print(
        elv_df[
            "document_status"
        ]
        .value_counts()
        .to_string()
    )

    print(
        "\nAverage traceability score:",
        round(
            float(
                elv_df[
                    "traceability_score"
                ]
                .mean()
            ),
            4,
        ),
    )

    print(
        "\nTraceability status:"
    )

    print(
        elv_df[
            "traceability_status"
        ]
        .value_counts()
        .to_string()
    )

    # ========================================================
    # CIRCULARITY SIGNALS
    # ========================================================

    print(
        "\n=== ELV CIRCULARITY SIGNALS ===\n"
    )

    print(
        "Average buyer demand index:",
        round(
            float(
                elv_df[
                    "buyer_demand_index"
                ]
                .mean()
            ),
            4,
        ),
    )

    print(
        "Average reusable parts pct:",
        round(
            float(
                elv_df[
                    "assessed_reusable_parts_pct"
                ]
                .mean()
            ),
            4,
        ),
    )

    print(
        "Average recyclable material pct:",
        round(
            float(
                elv_df[
                    "assessed_recyclable_material_pct"
                ]
                .mean()
            ),
            4,
        ),
    )

    print(
        "Average vehicle mass kg:",
        round(
            float(
                elv_df[
                    "estimated_vehicle_mass_kg"
                ]
                .mean()
            ),
            2,
        ),
    )

    # ========================================================
    # CONDITION RELATIONSHIPS
    # ========================================================

    print(
        "\n=== ELV RELATIONSHIP CHECKS ===\n"
    )

    print(
        "Correlation age vs condition:",
        round(
            float(
                elv_df[
                    [
                        "vehicle_age_years",
                        "condition_score",
                    ]
                ]
                .corr()
                .iloc[
                    0,
                    1
                ]
            ),
            4,
        ),
    )

    print(
        "Correlation condition vs reusable parts:",
        round(
            float(
                elv_df[
                    [
                        "condition_score",
                        "assessed_reusable_parts_pct",
                    ]
                ]
                .corr()
                .iloc[
                    0,
                    1
                ]
            ),
            4,
        ),
    )

    print(
        "Correlation docs vs traceability:",
        round(
            float(
                elv_df[
                    [
                        "document_completeness",
                        "traceability_score",
                    ]
                ]
                .corr()
                .iloc[
                    0,
                    1
                ]
            ),
            4,
        ),
    )

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    print(
        "\n=== ELV VALIDATION ===\n"
    )

    print(
        "Rows:",
        len(
            elv_df
        ),
    )

    print(
        "Unique assessment IDs:",
        elv_df[
            "elv_assessment_id"
        ]
        .nunique(),
    )

    print(
        "Unique ELV vehicle IDs:",
        elv_df[
            "elv_vehicle_id"
        ]
        .nunique(),
    )

    print(
        "Vehicle models represented:",
        elv_df[
            "vehicle_model_id"
        ]
        .nunique(),
    )

    print(
        "Cities represented:",
        elv_df[
            "city_id"
        ]
        .nunique(),
    )

    print(
        "Regions represented:",
        elv_df[
            "region_id"
        ]
        .nunique(),
    )

    print(
        "Duplicate assessment IDs:",
        int(
            elv_df[
                "elv_assessment_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Duplicate ELV vehicle IDs:",
        int(
            elv_df[
                "elv_vehicle_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Missing vehicle-model IDs:",
        int(
            elv_df[
                "vehicle_model_id"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Missing city IDs:",
        int(
            elv_df[
                "city_id"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Missing region IDs:",
        int(
            elv_df[
                "region_id"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Hidden truth/runtime leakage:",
        sorted(
            HIDDEN_RUNTIME_COLUMNS
            &
            set(
                elv_df.columns
            )
        ),
    )

    print(
        "\nGenerated "
        f"{len(elv_df)} "
        "synthetic ELV assessments successfully."
    )