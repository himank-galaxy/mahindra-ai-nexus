"""
Synthetic Logistics Shipment Generator
for Mahindra AI Nexus.

============================================================
PURPOSE
============================================================

Generates operational Logistics shipment history from:

    Geography
        ↓
    Warehouses
        ↓
    Routes
        ↓
    Synthetic Logistics Fleet
        ↓
    Shipments


The output becomes underlying evidence for the future:

    Logistics AI Control Tower
    shipment delay prediction
    SLA breach prediction
    route optimization
    warehouse bottleneck detection
    auto-heal workflows


============================================================
IMPORTANT ARCHITECTURAL RULE
============================================================

This generator creates OBSERVED BUSINESS RECORDS.

It DOES NOT generate runtime AI outputs such as:

    delay_probability
    predicted_delay
    sla_risk_score
    recommended_reroute
    recommended_action
    model_confidence

Those values must later be derived from shipment evidence by
the FastAPI / model / rules / simulation layer.


============================================================
OBSERVED OUTCOMES ARE ALLOWED
============================================================

The shipment table may contain:

    actual arrival
    actual transit time
    delay minutes
    SLA breach
    weather disruption
    warehouse delay
    vehicle breakdown

because these are operational observations, not model outputs.


============================================================
ACTUAL CONFIG SHAPE
============================================================

generation.yaml:

    logistics:

        priorities:
            - LOW
            - NORMAL
            - HIGH
            - CRITICAL

        shipments:
            count: 7500

        vehicle_fleet_size: 300

        warehouse_events:
            target_count: 15000


============================================================
ACTUAL ROUTE MASTER SCHEMA
============================================================

The existing frozen route generator produces:

    route_id

    origin_warehouse_id
    origin_warehouse_name
    origin_city_id
    origin_city_name
    origin_region_id
    origin_region_name

    destination_warehouse_id
    destination_warehouse_name
    destination_city_id
    destination_city_name
    destination_region_id
    destination_region_name

    route_type
    transport_mode

    distance_km
    typical_transit_hours
    sla_hours

    baseline_cost_inr
    baseline_risk_score

    active
    data_origin
    generator_version


============================================================
ACTUAL WAREHOUSE MASTER SCHEMA
============================================================

The frozen warehouse generator produces:

    warehouse_id
    warehouse_name

    city_id
    city_name

    region_id
    region_name

    warehouse_type

    storage_capacity_units
    baseline_utilization_pct
    daily_throughput_capacity

    active

    data_origin
    generator_version


============================================================
OUTPUT
============================================================

This module DOES NOT write CSV files.

Later generate_all.py will export the returned DataFrame to:

    data/synthetic/logistics/shipments.csv
"""

from __future__ import annotations

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
# VALID PRIORITIES
# ============================================================


VALID_PRIORITIES = {
    "LOW",
    "NORMAL",
    "HIGH",
    "CRITICAL",
}


# ============================================================
# SYNTHETIC PRIORITY MIX
#
# Engineering assumption only.
# NOT a Mahindra operational statistic.
# ============================================================


PRIORITY_WEIGHTS = {
    "LOW": 0.18,
    "NORMAL": 0.55,
    "HIGH": 0.22,
    "CRITICAL": 0.05,
}


# ============================================================
# FLEET TURNAROUND
#
# Synthetic operating assumption.
# ============================================================


VEHICLE_TURNAROUND_MIN_HOURS = 1.5
VEHICLE_TURNAROUND_MAX_HOURS = 8.0


# ============================================================
# DISRUPTION DURATIONS
#
# Event occurrence probabilities come from distributions.yaml.
#
# These ranges only determine how long an observed disruption
# lasts once it occurs.
# ============================================================


WEATHER_DELAY_HOURS = (
    1.0,
    18.0,
)

BREAKDOWN_DELAY_HOURS = (
    3.0,
    24.0,
)

WAREHOUSE_DELAY_HOURS = (
    1.0,
    12.0,
)

PORT_DELAY_HOURS = (
    4.0,
    36.0,
)

CUSTOMS_DELAY_HOURS = (
    3.0,
    30.0,
)


# ============================================================
# SAFE GENERATION BUFFER
#
# Ensures generated historical shipments finish before
# generation_end.
# ============================================================


MAX_EXTRA_TRANSIT_BUFFER_HOURS = 144.0


# ============================================================
# FORBIDDEN AI / TRUTH COLUMNS
# ============================================================


HIDDEN_RUNTIME_COLUMNS = {
    "delay_probability",

    "predicted_delay",
    "predicted_delay_minutes",
    "predicted_delay_probability",

    "sla_risk",
    "sla_risk_score",
    "sla_breach_probability",

    "risk_score",
    "risk_band",

    "recommended_action",
    "recommended_reroute",

    "recommendation_score",

    "confidence",
    "confidence_score",

    "model_score",
    "model_probability",

    "true_delay_cause",
    "true_sla_breach",
}


# ============================================================
# REQUIRED MASTER SCHEMAS
# ============================================================


WAREHOUSE_REQUIRED_COLUMNS: set[str] = {
    "warehouse_id",
    "warehouse_name",

    "city_id",
    "city_name",

    "region_id",
    "region_name",

    "warehouse_type",

    "storage_capacity_units",
    "baseline_utilization_pct",
    "daily_throughput_capacity",

    "active",

    "data_origin",
    "generator_version",
}


ROUTE_REQUIRED_COLUMNS: set[str] = {
    "route_id",

    "origin_warehouse_id",
    "origin_warehouse_name",

    "origin_city_id",
    "origin_city_name",

    "origin_region_id",
    "origin_region_name",

    "destination_warehouse_id",
    "destination_warehouse_name",

    "destination_city_id",
    "destination_city_name",

    "destination_region_id",
    "destination_region_name",

    "route_type",
    "transport_mode",

    "distance_km",

    "typical_transit_hours",

    "sla_hours",

    "baseline_cost_inr",
    "baseline_risk_score",

    "active",

    "data_origin",
    "generator_version",
}


# ============================================================
# BOOLEAN NORMALIZER
# ============================================================


def _to_bool_series(
    series: pd.Series,
) -> pd.Series:
    """
    Normalize boolean-like master fields.
    """

    if pd.api.types.is_bool_dtype(
        series
    ):

        return (
            series
            .fillna(
                False
            )
            .astype(bool)
        )

    true_values = {
        "TRUE",
        "YES",
        "Y",
        "1",
        "ACTIVE",
    }

    false_values = {
        "FALSE",
        "NO",
        "N",
        "0",
        "INACTIVE",
    }

    def convert(
        value: Any,
    ) -> bool:

        if pd.isna(
            value
        ):

            return False

        if isinstance(
            value,
            (
                bool,
                np.bool_,
            ),
        ):

            return bool(
                value
            )

        normalized = (
            str(
                value
            )
            .strip()
            .upper()
        )

        if normalized in true_values:

            return True

        if normalized in false_values:

            return False

        raise ValueError(
            "Unable to interpret boolean value: "
            f"{value!r}"
        )

    return (
        series
        .map(
            convert
        )
        .astype(bool)
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

        time_config = generation[
            "time"
        ]

        start_value = time_config[
            "start_date"
        ]

        end_value = time_config[
            "end_date"
        ]

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
            "generation.time.end_date must be after start_date"
        )

    return (
        start,
        end,
    )


# ============================================================
# ACTUAL LOGISTICS CONFIG
# ============================================================


def _get_logistics_generation_settings(
    generation: Mapping[
        str,
        Any,
    ],
) -> tuple[
    int,
    int,
    list[str],
]:
    """
    Read the ACTUAL generation.yaml Logistics structure:

        logistics:
            priorities: [...]
            shipments:
                count: 7500
            vehicle_fleet_size: 300
            warehouse_events:
                target_count: 15000
    """

    try:

        logistics = generation[
            "logistics"
        ]

        shipment_count = int(
            logistics[
                "shipments"
            ][
                "count"
            ]
        )

        fleet_size = int(
            logistics[
                "vehicle_fleet_size"
            ]
        )

        raw_priorities = (
            logistics[
                "priorities"
            ]
        )

    except KeyError as exc:

        raise KeyError(
            "Missing Logistics configuration. Expected: "
            "logistics.shipments.count, "
            "logistics.vehicle_fleet_size, "
            "logistics.priorities"
        ) from exc

    if shipment_count <= 0:

        raise ValueError(
            "generation.logistics.shipments.count "
            "must be > 0"
        )

    if fleet_size <= 0:

        raise ValueError(
            "generation.logistics.vehicle_fleet_size "
            "must be > 0"
        )

    if not isinstance(
        raw_priorities,
        (
            list,
            tuple,
        ),
    ):

        raise TypeError(
            "generation.logistics.priorities "
            "must be a list"
        )

    priorities = [
        str(
            priority
        )
        .strip()
        .upper()

        for priority
        in raw_priorities
    ]

    priorities = list(
        dict.fromkeys(
            priorities
        )
    )

    if not priorities:

        raise ValueError(
            "generation.logistics.priorities "
            "cannot be empty"
        )

    invalid_priorities = (
        set(
            priorities
        )
        -
        VALID_PRIORITIES
    )

    if invalid_priorities:

        raise ValueError(
            "Unsupported Logistics priorities: "
            +
            ", ".join(
                sorted(
                    invalid_priorities
                )
            )
        )

    return (
        shipment_count,
        fleet_size,
        priorities,
    )


# ============================================================
# LOGISTICS DISTRIBUTIONS
# ============================================================


def _get_disruption_probabilities(
    distributions: Mapping[
        str,
        Any,
    ],
) -> dict[
    str,
    float,
]:
    """
    Read configured operational disruption probabilities.
    """

    try:

        logistics = distributions[
            "logistics"
        ]

    except KeyError as exc:

        raise KeyError(
            "Missing distributions.logistics"
        ) from exc

    required_probability_keys = (
        "weather_disruption_probability",
        "vehicle_breakdown_probability",
        "port_delay_probability",
        "customs_delay_probability",
        "warehouse_delay_probability",
    )

    result: dict[
        str,
        float,
    ] = {}

    for key in required_probability_keys:

        if key not in logistics:

            raise KeyError(
                "Missing distributions.logistics."
                f"{key}"
            )

        probability = float(
            logistics[
                key
            ]
        )

        if not (
            0.0
            <=
            probability
            <=
            1.0
        ):

            raise ValueError(
                "Probability must be between 0 and 1: "
                f"distributions.logistics.{key}"
            )

        result[
            key
        ] = probability

    return result


# ============================================================
# PRIORITY PROBABILITIES
# ============================================================


def _get_priority_probabilities(
    priorities: list[str],
) -> np.ndarray:
    """
    Return normalized priority probabilities.
    """

    weights = np.asarray(
        [
            PRIORITY_WEIGHTS[
                priority
            ]

            for priority
            in priorities
        ],
        dtype=float,
    )

    if weights.sum() <= 0:

        raise ValueError(
            "Shipment priority weights sum to zero"
        )

    return (
        weights
        /
        weights.sum()
    )


# ============================================================
# VALIDATE / PREPARE WAREHOUSE MASTER
# ============================================================


def _prepare_warehouses(
    warehouses: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate the frozen warehouse master.
    """

    if warehouses.empty:

        raise ValueError(
            "Warehouses DataFrame cannot be empty"
        )

    missing_columns = (
        WAREHOUSE_REQUIRED_COLUMNS
        -
        set(
            warehouses.columns
        )
    )

    if missing_columns:

        raise ValueError(
            "Warehouses DataFrame missing columns: "
            +
            ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    result = (
        warehouses
        .copy(
            deep=True
        )
    )

    # ========================================================
    # REQUIRED KEYS
    # ========================================================

    for column in (
        "warehouse_id",
        "city_id",
        "region_id",
    ):

        if (
            result[
                column
            ]
            .isna()
            .any()
        ):

            raise ValueError(
                "Warehouses DataFrame contains "
                f"missing values in {column}"
            )

    # ========================================================
    # UNIQUE WAREHOUSE ID
    # ========================================================

    if (
        result[
            "warehouse_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Duplicate warehouse_id values found"
        )

    # ========================================================
    # ACTIVE
    # ========================================================

    result[
        "active"
    ] = (
        _to_bool_series(
            result[
                "active"
            ]
        )
    )

    result = (
        result.loc[
            result[
                "active"
            ]
        ]
        .copy()
    )

    if result.empty:

        raise ValueError(
            "No active warehouses available"
        )

    # ========================================================
    # NUMERIC VALUES
    # ========================================================

    for column in (
        "storage_capacity_units",
        "baseline_utilization_pct",
        "daily_throughput_capacity",
    ):

        result[
            column
        ] = pd.to_numeric(
            result[
                column
            ],
            errors=
                "raise",
        )

    if (
        result[
            "storage_capacity_units"
        ]
        <=
        0
    ).any():

        raise ValueError(
            "Warehouse storage capacity must be positive"
        )

    if (
        result[
            "daily_throughput_capacity"
        ]
        <=
        0
    ).any():

        raise ValueError(
            "Warehouse daily throughput must be positive"
        )

    if (
        (
            result[
                "baseline_utilization_pct"
            ]
            <
            0
        )
        |
        (
            result[
                "baseline_utilization_pct"
            ]
            >
            1
        )
    ).any():

        raise ValueError(
            "Warehouse baseline_utilization_pct "
            "must be between 0 and 1"
        )

    return (
        result
        .sort_values(
            "warehouse_id"
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# VALIDATE / PREPARE ROUTE MASTER
# ============================================================


def _prepare_routes(
    routes: pd.DataFrame,
    warehouses: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate the frozen route master.

    Important:
        actual transit column is:

            typical_transit_hours

        NOT:

            standard_transit_hours
    """

    if routes.empty:

        raise ValueError(
            "Routes DataFrame cannot be empty"
        )

    missing_columns = (
        ROUTE_REQUIRED_COLUMNS
        -
        set(
            routes.columns
        )
    )

    if missing_columns:

        raise ValueError(
            "Routes DataFrame missing columns: "
            +
            ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    result = (
        routes
        .copy(
            deep=True
        )
    )

    # ========================================================
    # ROUTE PK
    # ========================================================

    if (
        result[
            "route_id"
        ]
        .isna()
        .any()
    ):

        raise ValueError(
            "Route master contains missing route_id"
        )

    if (
        result[
            "route_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Duplicate route_id values found"
        )

    # ========================================================
    # ROUTE WAREHOUSE FKS
    # ========================================================

    valid_warehouse_ids = set(
        warehouses[
            "warehouse_id"
        ]
        .astype(str)
    )

    invalid_origin_warehouses = (
        set(
            result[
                "origin_warehouse_id"
            ]
            .astype(str)
        )
        -
        valid_warehouse_ids
    )

    if invalid_origin_warehouses:

        raise ValueError(
            "Routes reference invalid origin warehouses: "
            +
            ", ".join(
                sorted(
                    invalid_origin_warehouses
                )
            )
        )

    invalid_destination_warehouses = (
        set(
            result[
                "destination_warehouse_id"
            ]
            .astype(str)
        )
        -
        valid_warehouse_ids
    )

    if invalid_destination_warehouses:

        raise ValueError(
            "Routes reference invalid destination warehouses: "
            +
            ", ".join(
                sorted(
                    invalid_destination_warehouses
                )
            )
        )

    # ========================================================
    # ACTIVE
    # ========================================================

    result[
        "active"
    ] = (
        _to_bool_series(
            result[
                "active"
            ]
        )
    )

    result = (
        result.loc[
            result[
                "active"
            ]
        ]
        .copy()
    )

    if result.empty:

        raise ValueError(
            "No active Logistics routes available"
        )

    # ========================================================
    # NUMERIC ROUTE VALUES
    # ========================================================

    for column in (
        "distance_km",
        "typical_transit_hours",
        "sla_hours",
        "baseline_cost_inr",
        "baseline_risk_score",
    ):

        result[
            column
        ] = pd.to_numeric(
            result[
                column
            ],
            errors=
                "raise",
        )

    if (
        result[
            "distance_km"
        ]
        <=
        0
    ).any():

        raise ValueError(
            "Route distance_km must be positive"
        )

    if (
        result[
            "typical_transit_hours"
        ]
        <=
        0
    ).any():

        raise ValueError(
            "Route typical_transit_hours "
            "must be positive"
        )

    if (
        result[
            "sla_hours"
        ]
        <=
        0
    ).any():

        raise ValueError(
            "Route sla_hours must be positive"
        )

    if (
        result[
            "baseline_cost_inr"
        ]
        <=
        0
    ).any():

        raise ValueError(
            "Route baseline_cost_inr must be positive"
        )

    if (
        (
            result[
                "baseline_risk_score"
            ]
            <
            0
        )
        |
        (
            result[
                "baseline_risk_score"
            ]
            >
            1
        )
    ).any():

        raise ValueError(
            "Route baseline_risk_score "
            "must be between 0 and 1"
        )

    # ========================================================
    # LOGICAL ROUTE CHECK
    # ========================================================

    if (
        result[
            "origin_warehouse_id"
        ]
        .astype(str)
        ==
        result[
            "destination_warehouse_id"
        ]
        .astype(str)
    ).any():

        raise ValueError(
            "A Logistics route cannot have the same "
            "origin and destination warehouse"
        )

    return (
        result
        .sort_values(
            "route_id"
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# CROSS-BORDER / PORT ELIGIBILITY
# ============================================================


def _is_cross_border_or_port_route(
    route: Mapping[
        str,
        Any,
    ],
) -> bool:
    """
    Port/customs disruptions are only generated when route
    metadata suggests that they are applicable.

    Current frozen route master is domestic ROAD network, so
    these may legitimately remain zero until port/cross-border
    routes are introduced.
    """

    text = " ".join(
        [
            str(
                route.get(
                    "route_type",
                    "",
                )
            ),

            str(
                route.get(
                    "transport_mode",
                    "",
                )
            ),

            str(
                route.get(
                    "origin_warehouse_name",
                    "",
                )
            ),

            str(
                route.get(
                    "destination_warehouse_name",
                    "",
                )
            ),

            str(
                route.get(
                    "origin_city_name",
                    "",
                )
            ),

            str(
                route.get(
                    "destination_city_name",
                    "",
                )
            ),
        ]
    ).upper()

    tokens = (
        "PORT",
        "SEAPORT",

        "MUNDRA",
        "JNPT",
        "NHAVA",

        "INTERNATIONAL",

        "CROSS_BORDER",
        "CROSS-BORDER",

        "CUSTOMS",
    )

    return any(
        token in text
        for token
        in tokens
    )


# ============================================================
# DISRUPTION DURATION
# ============================================================


def _sample_delay_hours(
    rng: np.random.Generator,
    bounds: tuple[
        float,
        float,
    ],
) -> float:
    """
    Sample synthetic observed disruption duration.
    """

    low, high = bounds

    mode = (
        low
        +
        0.35
        *
        (
            high
            -
            low
        )
    )

    return float(
        rng.triangular(
            left=
                low,

            mode=
                mode,

            right=
                high,
        )
    )


# ============================================================
# VEHICLE ASSIGNMENT
# ============================================================


def _choose_vehicle(
    rng: np.random.Generator,
    vehicle_available_at: dict[
        str,
        pd.Timestamp,
    ],
    desired_dispatch_time: pd.Timestamp,
) -> tuple[
    str,
    pd.Timestamp,
    float,
]:
    """
    Allocate Logistics vehicle without overlapping assignments.

    Returns:

        vehicle_id
        dispatch_time
        dispatch_delay_minutes
    """

    available_vehicle_ids = [
        vehicle_id

        for (
            vehicle_id,
            available_at,
        )
        in vehicle_available_at.items()

        if available_at
        <=
        desired_dispatch_time
    ]

    if available_vehicle_ids:

        vehicle_id = str(
            rng.choice(
                np.asarray(
                    sorted(
                        available_vehicle_ids
                    ),
                    dtype=object,
                )
            )
        )

        dispatch_time = (
            desired_dispatch_time
        )

    else:

        vehicle_id = min(
            vehicle_available_at,
            key=lambda current_vehicle_id: (
                vehicle_available_at[
                    current_vehicle_id
                ],
                current_vehicle_id,
            ),
        )

        dispatch_time = (
            vehicle_available_at[
                vehicle_id
            ]
        )

    dispatch_delay_minutes = max(
        0.0,
        (
            dispatch_time
            -
            desired_dispatch_time
        )
        .total_seconds()
        /
        60.0,
    )

    return (
        vehicle_id,
        dispatch_time,
        dispatch_delay_minutes,
    )


# ============================================================
# SHIPMENT LOAD SIZE
# ============================================================


def _generate_shipment_units(
    rng: np.random.Generator,
    distance_km: float,
) -> int:
    """
    Generate plausible shipment load based on route distance.
    """

    if distance_km >= 1500:

        return int(
            rng.integers(
                6,
                13,
            )
        )

    if distance_km >= 1000:

        return int(
            rng.integers(
                5,
                12,
            )
        )

    if distance_km >= 500:

        return int(
            rng.integers(
                4,
                11,
            )
        )

    if distance_km >= 200:

        return int(
            rng.integers(
                3,
                10,
            )
        )

    return int(
        rng.integers(
            1,
            8,
        )
    )


# ============================================================
# SHIPMENT GENERATOR
# ============================================================


def generate_shipments(
    routes: pd.DataFrame,
    warehouses: pd.DataFrame,
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
    Generate synthetic Logistics shipment history.
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
    # PREPARE MASTER DATA
    # ========================================================

    warehouses = (
        _prepare_warehouses(
            warehouses
        )
    )

    routes = (
        _prepare_routes(
            routes=
                routes,

            warehouses=
                warehouses,
        )
    )

    # ========================================================
    # CONFIG
    # ========================================================

    (
        generation_start,
        generation_end,
    ) = (
        _get_generation_window(
            generation
        )
    )

    (
        shipment_count,
        fleet_size,
        priorities,
    ) = (
        _get_logistics_generation_settings(
            generation
        )
    )

    disruption_probabilities = (
        _get_disruption_probabilities(
            distributions
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
            "logistics.shipments",
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
    # PRIORITY DISTRIBUTION
    # ========================================================

    priority_probabilities = (
        _get_priority_probabilities(
            priorities
        )
    )

    # ========================================================
    # SAFE DESIRED DISPATCH WINDOW
    # ========================================================

    maximum_typical_transit_hours = float(
        routes[
            "typical_transit_hours"
        ]
        .max()
    )

    maximum_sla_hours = float(
        routes[
            "sla_hours"
        ]
        .max()
    )

    maximum_route_window = max(
        maximum_typical_transit_hours,
        maximum_sla_hours,
    )

    latest_desired_dispatch = (
        generation_end
        -
        pd.Timedelta(
            hours=(
                maximum_route_window
                +
                MAX_EXTRA_TRANSIT_BUFFER_HOURS
            )
        )
    )

    if (
        latest_desired_dispatch
        <=
        generation_start
    ):

        raise ValueError(
            "Configured generation window is too short "
            "for Logistics shipment generation"
        )

    dispatch_span_seconds = (
        latest_desired_dispatch
        -
        generation_start
    ).total_seconds()

    # ========================================================
    # CREATE DESIRED SHIPMENT SCHEDULE
    # ========================================================

    desired_dispatch_offsets = np.sort(
        rng.uniform(
            low=
                0.0,

            high=
                dispatch_span_seconds,

            size=
                shipment_count,
        )
    )

    # --------------------------------------------------------
    # Uniform route sampling.
    #
    # No route-volume weights currently exist in the frozen
    # route master, so we do NOT invent fake master weights.
    # --------------------------------------------------------

    route_positions = rng.integers(
        low=
            0,

        high=
            len(
                routes
            ),

        size=
            shipment_count,
    )

    priority_positions = rng.choice(
        np.arange(
            len(
                priorities
            )
        ),
        size=
            shipment_count,
        p=
            priority_probabilities,
    )

    # ========================================================
    # SYNTHETIC FLEET
    # ========================================================

    vehicle_ids = [
        generate_id(
            "LOGVEH_SYN",
            index,
            width=4,
        )

        for index
        in range(
            1,
            fleet_size
            +
            1,
        )
    ]

    vehicle_available_at = {
        vehicle_id:
            generation_start

        for vehicle_id
        in vehicle_ids
    }

    # ========================================================
    # WAREHOUSE LOOKUP
    # ========================================================

    warehouse_lookup = {
        str(
            row.warehouse_id
        ):
            row._asdict()

        for row
        in warehouses.itertuples(
            index=False
        )
    }

    rows: list[
        dict[
            str,
            Any,
        ]
    ] = []

    # ========================================================
    # GENERATE SHIPMENTS
    # ========================================================

    for shipment_position in range(
        shipment_count
    ):

        # ====================================================
        # DESIRED DISPATCH
        # ====================================================

        desired_dispatch_time = (
            generation_start
            +
            pd.Timedelta(
                seconds=float(
                    desired_dispatch_offsets[
                        shipment_position
                    ]
                )
            )
        )

        # ====================================================
        # ROUTE
        # ====================================================

        route = (
            routes.iloc[
                int(
                    route_positions[
                        shipment_position
                    ]
                )
            ]
        )

        route_id = str(
            route[
                "route_id"
            ]
        )

        origin_warehouse_id = str(
            route[
                "origin_warehouse_id"
            ]
        )

        destination_warehouse_id = str(
            route[
                "destination_warehouse_id"
            ]
        )

        origin_warehouse = (
            warehouse_lookup[
                origin_warehouse_id
            ]
        )

        destination_warehouse = (
            warehouse_lookup[
                destination_warehouse_id
            ]
        )

        distance_km = float(
            route[
                "distance_km"
            ]
        )

        typical_transit_hours = float(
            route[
                "typical_transit_hours"
            ]
        )

        sla_hours = float(
            route[
                "sla_hours"
            ]
        )

        # ====================================================
        # FLEET ASSIGNMENT
        # ====================================================

        (
            vehicle_id,
            dispatch_time,
            dispatch_delay_minutes,
        ) = (
            _choose_vehicle(
                rng=
                    rng,

                vehicle_available_at=
                    vehicle_available_at,

                desired_dispatch_time=
                    desired_dispatch_time,
            )
        )

        # ====================================================
        # PLANNED ARRIVAL / SLA
        # ====================================================

        expected_arrival = (
            dispatch_time
            +
            pd.Timedelta(
                hours=
                    typical_transit_hours
            )
        )

        sla_deadline = (
            dispatch_time
            +
            pd.Timedelta(
                hours=
                    sla_hours
            )
        )

        # ====================================================
        # OBSERVED DISRUPTION PROBABILITIES
        #
        # Config values act as network baselines.
        #
        # Small observable adjustments introduce useful
        # relationships for future predictive models.
        # ====================================================

        distance_factor = float(
            np.clip(
                distance_km
                /
                2000.0,
                0.0,
                1.0,
            )
        )

        origin_utilization = float(
            origin_warehouse[
                "baseline_utilization_pct"
            ]
        )

        weather_probability = float(
            np.clip(
                disruption_probabilities[
                    "weather_disruption_probability"
                ]
                *
                (
                    0.90
                    +
                    0.20
                    *
                    distance_factor
                ),
                0.0,
                1.0,
            )
        )

        breakdown_probability = float(
            np.clip(
                disruption_probabilities[
                    "vehicle_breakdown_probability"
                ]
                *
                (
                    0.75
                    +
                    0.50
                    *
                    distance_factor
                ),
                0.0,
                1.0,
            )
        )

        warehouse_delay_probability = float(
            np.clip(
                disruption_probabilities[
                    "warehouse_delay_probability"
                ]
                *
                (
                    0.65
                    +
                    0.70
                    *
                    origin_utilization
                ),
                0.0,
                1.0,
            )
        )

        cross_border_eligible = (
            _is_cross_border_or_port_route(
                route
            )
        )

        # ====================================================
        # OBSERVED DISRUPTION EVENTS
        # ====================================================

        weather_disruption = bool(
            rng.random()
            <
            weather_probability
        )

        vehicle_breakdown = bool(
            rng.random()
            <
            breakdown_probability
        )

        warehouse_delay = bool(
            rng.random()
            <
            warehouse_delay_probability
        )

        port_delay = bool(
            cross_border_eligible
            and
            (
                rng.random()
                <
                disruption_probabilities[
                    "port_delay_probability"
                ]
            )
        )

        customs_delay = bool(
            cross_border_eligible
            and
            (
                rng.random()
                <
                disruption_probabilities[
                    "customs_delay_probability"
                ]
            )
        )

        # ====================================================
        # DISRUPTION DURATION
        # ====================================================

        disruption_hours = 0.0

        if weather_disruption:

            disruption_hours += (
                _sample_delay_hours(
                    rng=
                        rng,

                    bounds=
                        WEATHER_DELAY_HOURS,
                )
            )

        if vehicle_breakdown:

            disruption_hours += (
                _sample_delay_hours(
                    rng=
                        rng,

                    bounds=
                        BREAKDOWN_DELAY_HOURS,
                )
            )

        if warehouse_delay:

            disruption_hours += (
                _sample_delay_hours(
                    rng=
                        rng,

                    bounds=
                        WAREHOUSE_DELAY_HOURS,
                )
            )

        if port_delay:

            disruption_hours += (
                _sample_delay_hours(
                    rng=
                        rng,

                    bounds=
                        PORT_DELAY_HOURS,
                )
            )

        if customs_delay:

            disruption_hours += (
                _sample_delay_hours(
                    rng=
                        rng,

                    bounds=
                        CUSTOMS_DELAY_HOURS,
                )
            )

        # ====================================================
        # NORMAL OPERATING VARIATION
        #
        # This is observed transit variation.
        #
        # It is NOT predicted delay.
        # ====================================================

        normal_transit_factor = float(
            np.clip(
                rng.normal(
                    loc=
                        1.0,

                    scale=
                        0.055,
                ),
                0.85,
                1.18,
            )
        )

        actual_transit_hours = max(
            0.25,
            (
                typical_transit_hours
                *
                normal_transit_factor
            )
            +
            disruption_hours,
        )

        # ====================================================
        # ACTUAL ARRIVAL
        # ====================================================

        actual_arrival = (
            dispatch_time
            +
            pd.Timedelta(
                hours=
                    actual_transit_hours
            )
        )

        if (
            actual_arrival
            >=
            generation_end
        ):

            raise ValueError(
                "Generated shipment exceeds generation_end. "
                "Inspect Logistics transit assumptions."
            )

        # ====================================================
        # OBSERVED OUTCOMES
        # ====================================================

        arrival_variance_minutes = (
            (
                actual_arrival
                -
                expected_arrival
            )
            .total_seconds()
            /
            60.0
        )

        delay_minutes = max(
            0.0,
            arrival_variance_minutes,
        )

        early_arrival_minutes = max(
            0.0,
            -arrival_variance_minutes,
        )

        sla_breach = bool(
            actual_arrival
            >
            sla_deadline
        )

        units = (
            _generate_shipment_units(
                rng=
                    rng,

                distance_km=
                    distance_km,
            )
        )

        priority = str(
            priorities[
                int(
                    priority_positions[
                        shipment_position
                    ]
                )
            ]
        )

        # ====================================================
        # VEHICLE READY FOR NEXT SHIPMENT
        # ====================================================

        turnaround_hours = float(
            rng.uniform(
                VEHICLE_TURNAROUND_MIN_HOURS,
                VEHICLE_TURNAROUND_MAX_HOURS,
            )
        )

        vehicle_available_at[
            vehicle_id
        ] = (
            actual_arrival
            +
            pd.Timedelta(
                hours=
                    turnaround_hours
            )
        )

        # ====================================================
        # OUTPUT
        # ====================================================

        rows.append(
            {
                # --------------------------------------------
                # PK
                # --------------------------------------------

                "shipment_id":
                    generate_id(
                        "SHIP_SYN",
                        shipment_position
                        +
                        1,
                        width=7,
                    ),

                # --------------------------------------------
                # Route FK
                # --------------------------------------------

                "route_id":
                    route_id,

                "route_type":
                    str(
                        route[
                            "route_type"
                        ]
                    ),

                "transport_mode":
                    str(
                        route[
                            "transport_mode"
                        ]
                    ),

                # --------------------------------------------
                # Origin
                # --------------------------------------------

                "origin_warehouse_id":
                    origin_warehouse_id,

                "origin_warehouse_name":
                    str(
                        origin_warehouse[
                            "warehouse_name"
                        ]
                    ),

                "origin_city_id":
                    str(
                        origin_warehouse[
                            "city_id"
                        ]
                    ),

                "origin_city_name":
                    str(
                        origin_warehouse[
                            "city_name"
                        ]
                    ),

                "origin_region_id":
                    str(
                        origin_warehouse[
                            "region_id"
                        ]
                    ),

                "origin_region_name":
                    str(
                        origin_warehouse[
                            "region_name"
                        ]
                    ),

                # --------------------------------------------
                # Destination
                # --------------------------------------------

                "destination_warehouse_id":
                    destination_warehouse_id,

                "destination_warehouse_name":
                    str(
                        destination_warehouse[
                            "warehouse_name"
                        ]
                    ),

                "destination_city_id":
                    str(
                        destination_warehouse[
                            "city_id"
                        ]
                    ),

                "destination_city_name":
                    str(
                        destination_warehouse[
                            "city_name"
                        ]
                    ),

                "destination_region_id":
                    str(
                        destination_warehouse[
                            "region_id"
                        ]
                    ),

                "destination_region_name":
                    str(
                        destination_warehouse[
                            "region_name"
                        ]
                    ),

                # --------------------------------------------
                # Route operating attributes
                # --------------------------------------------

                "distance_km":
                    round(
                        distance_km,
                        2,
                    ),

                "typical_transit_hours":
                    round(
                        typical_transit_hours,
                        2,
                    ),

                "sla_hours":
                    round(
                        sla_hours,
                        2,
                    ),

                "baseline_cost_inr":
                    round(
                        float(
                            route[
                                "baseline_cost_inr"
                            ]
                        ),
                        2,
                    ),

                # --------------------------------------------
                # Fleet
                # --------------------------------------------

                "vehicle_id":
                    vehicle_id,

                # --------------------------------------------
                # Shipment
                # --------------------------------------------

                "units":
                    units,

                "priority":
                    priority,

                # --------------------------------------------
                # Timeline
                # --------------------------------------------

                "desired_dispatch_time":
                    desired_dispatch_time,

                "dispatch_time":
                    dispatch_time,

                "expected_arrival":
                    expected_arrival,

                "sla_deadline":
                    sla_deadline,

                "actual_arrival":
                    actual_arrival,

                # --------------------------------------------
                # Observed disruptions
                # --------------------------------------------

                "weather_disruption":
                    weather_disruption,

                "vehicle_breakdown":
                    vehicle_breakdown,

                "warehouse_delay":
                    warehouse_delay,

                "port_delay":
                    port_delay,

                "customs_delay":
                    customs_delay,

                # --------------------------------------------
                # Observed operating outcome
                # --------------------------------------------

                "dispatch_delay_minutes":
                    round(
                        dispatch_delay_minutes,
                        3,
                    ),

                "actual_transit_hours":
                    round(
                        actual_transit_hours,
                        3,
                    ),

                "arrival_variance_minutes":
                    round(
                        arrival_variance_minutes,
                        3,
                    ),

                "delay_minutes":
                    round(
                        delay_minutes,
                        3,
                    ),

                "early_arrival_minutes":
                    round(
                        early_arrival_minutes,
                        3,
                    ),

                "sla_breach":
                    sla_breach,

                "shipment_status":
                    "DELIVERED",

                # --------------------------------------------
                # Provenance
                # --------------------------------------------

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    shipments = pd.DataFrame(
        rows
    )

    # ========================================================
    # VALIDATE
    # ========================================================

    validate_shipments(
        shipments=
            shipments,

        routes=
            routes,

        warehouses=
            warehouses,

        generation_start=
            generation_start,

        generation_end=
            generation_end,

        expected_shipment_count=
            shipment_count,

        fleet_size=
            fleet_size,

        configured_priorities=
            set(
                priorities
            ),
    )

    return shipments


# ============================================================
# SHIPMENT VALIDATION
# ============================================================


def validate_shipments(
    shipments: pd.DataFrame,
    routes: pd.DataFrame,
    warehouses: pd.DataFrame,
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
    expected_shipment_count: int,
    fleet_size: int,
    configured_priorities: set[str],
) -> None:
    """
    Validate shipment integrity.
    """

    required_columns = {
        "shipment_id",

        "route_id",
        "route_type",
        "transport_mode",

        "origin_warehouse_id",
        "origin_warehouse_name",

        "origin_city_id",
        "origin_city_name",

        "origin_region_id",
        "origin_region_name",

        "destination_warehouse_id",
        "destination_warehouse_name",

        "destination_city_id",
        "destination_city_name",

        "destination_region_id",
        "destination_region_name",

        "distance_km",
        "typical_transit_hours",
        "sla_hours",
        "baseline_cost_inr",

        "vehicle_id",

        "units",
        "priority",

        "desired_dispatch_time",
        "dispatch_time",

        "expected_arrival",
        "sla_deadline",
        "actual_arrival",

        "weather_disruption",
        "vehicle_breakdown",
        "warehouse_delay",
        "port_delay",
        "customs_delay",

        "dispatch_delay_minutes",

        "actual_transit_hours",

        "arrival_variance_minutes",

        "delay_minutes",
        "early_arrival_minutes",

        "sla_breach",

        "shipment_status",

        "data_origin",
        "generator_version",
    }

    missing_columns = (
        required_columns
        -
        set(
            shipments.columns
        )
    )

    if missing_columns:

        raise ValueError(
            "Shipments missing columns: "
            +
            ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if shipments.empty:

        raise ValueError(
            "Shipment generator produced zero rows"
        )

    # ========================================================
    # EXACT COUNT
    # ========================================================

    if (
        len(
            shipments
        )
        !=
        expected_shipment_count
    ):

        raise ValueError(
            "Unexpected Logistics shipment count. "
            f"Expected={expected_shipment_count}, "
            f"actual={len(shipments)}"
        )

    # ========================================================
    # PK
    # ========================================================

    if (
        shipments[
            "shipment_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Duplicate shipment_id values found"
        )

    # ========================================================
    # ROUTE FK
    # ========================================================

    valid_route_ids = set(
        routes[
            "route_id"
        ]
        .astype(str)
    )

    invalid_route_ids = (
        set(
            shipments[
                "route_id"
            ]
            .astype(str)
        )
        -
        valid_route_ids
    )

    if invalid_route_ids:

        raise ValueError(
            "Shipments reference invalid route IDs: "
            +
            ", ".join(
                sorted(
                    invalid_route_ids
                )[
                    :20
                ]
            )
        )

    # ========================================================
    # WAREHOUSE FKS
    # ========================================================

    valid_warehouse_ids = set(
        warehouses[
            "warehouse_id"
        ]
        .astype(str)
    )

    invalid_origin_warehouses = (
        set(
            shipments[
                "origin_warehouse_id"
            ]
            .astype(str)
        )
        -
        valid_warehouse_ids
    )

    if invalid_origin_warehouses:

        raise ValueError(
            "Shipments reference invalid origin warehouses"
        )

    invalid_destination_warehouses = (
        set(
            shipments[
                "destination_warehouse_id"
            ]
            .astype(str)
        )
        -
        valid_warehouse_ids
    )

    if invalid_destination_warehouses:

        raise ValueError(
            "Shipments reference invalid "
            "destination warehouses"
        )

    # ========================================================
    # PRIORITIES
    # ========================================================

    invalid_priorities = (
        set(
            shipments[
                "priority"
            ]
            .astype(str)
        )
        -
        configured_priorities
    )

    if invalid_priorities:

        raise ValueError(
            "Invalid shipment priorities: "
            +
            ", ".join(
                sorted(
                    invalid_priorities
                )
            )
        )

    # ========================================================
    # FLEET SIZE
    # ========================================================

    if (
        shipments[
            "vehicle_id"
        ]
        .nunique()
        >
        fleet_size
    ):

        raise ValueError(
            "Generated shipments use more vehicles "
            "than configured fleet"
        )

    # ========================================================
    # NUMERIC VALUES
    # ========================================================

    positive_columns = (
        "distance_km",
        "typical_transit_hours",
        "sla_hours",
        "baseline_cost_inr",
        "units",
        "actual_transit_hours",
    )

    for column in positive_columns:

        values = pd.to_numeric(
            shipments[
                column
            ],
            errors=
                "raise",
        )

        if (
            values
            <=
            0
        ).any():

            raise ValueError(
                f"{column} must be positive"
            )

    nonnegative_columns = (
        "dispatch_delay_minutes",
        "delay_minutes",
        "early_arrival_minutes",
    )

    for column in nonnegative_columns:

        values = pd.to_numeric(
            shipments[
                column
            ],
            errors=
                "raise",
        )

        if (
            values
            <
            0
        ).any():

            raise ValueError(
                f"{column} cannot be negative"
            )

    # ========================================================
    # TIME NORMALIZATION
    # ========================================================

    desired_dispatch = pd.to_datetime(
        shipments[
            "desired_dispatch_time"
        ],
        utc=True,
    )

    dispatch = pd.to_datetime(
        shipments[
            "dispatch_time"
        ],
        utc=True,
    )

    expected_arrival = pd.to_datetime(
        shipments[
            "expected_arrival"
        ],
        utc=True,
    )

    sla_deadline = pd.to_datetime(
        shipments[
            "sla_deadline"
        ],
        utc=True,
    )

    actual_arrival = pd.to_datetime(
        shipments[
            "actual_arrival"
        ],
        utc=True,
    )

    generation_start_utc = (
        generation_start
        .tz_convert(
            "UTC"
        )
    )

    generation_end_utc = (
        generation_end
        .tz_convert(
            "UTC"
        )
    )

    # ========================================================
    # TIMELINE
    # ========================================================

    if (
        desired_dispatch
        <
        generation_start_utc
    ).any():

        raise ValueError(
            "Shipment desired dispatch precedes "
            "generation start"
        )

    if (
        dispatch
        <
        desired_dispatch
    ).any():

        raise ValueError(
            "Shipment dispatch cannot occur before "
            "desired dispatch"
        )

    if (
        dispatch
        >=
        generation_end_utc
    ).any():

        raise ValueError(
            "Shipment dispatch occurs on/after "
            "generation cutoff"
        )

    if (
        expected_arrival
        <=
        dispatch
    ).any():

        raise ValueError(
            "expected_arrival must occur after dispatch"
        )

    if (
        sla_deadline
        <=
        dispatch
    ).any():

        raise ValueError(
            "sla_deadline must occur after dispatch"
        )

    if (
        actual_arrival
        <=
        dispatch
    ).any():

        raise ValueError(
            "actual_arrival must occur after dispatch"
        )

    if (
        actual_arrival
        >=
        generation_end_utc
    ).any():

        raise ValueError(
            "Shipment actual arrival occurs on/after "
            "generation cutoff"
        )

    # ========================================================
    # DISPATCH WAIT VALIDATION
    # ========================================================

    calculated_dispatch_delay = (
        (
            dispatch
            -
            desired_dispatch
        )
        .dt
        .total_seconds()
        /
        60.0
    )

    stored_dispatch_delay = pd.to_numeric(
        shipments[
            "dispatch_delay_minutes"
        ],
        errors=
            "raise",
    )

    if not np.allclose(
        calculated_dispatch_delay.to_numpy(
            dtype=float
        ),
        stored_dispatch_delay.to_numpy(
            dtype=float
        ),
        atol=
            0.02,
    ):

        raise ValueError(
            "dispatch_delay_minutes inconsistent "
            "with timestamps"
        )

    # ========================================================
    # ACTUAL TRANSIT VALIDATION
    # ========================================================

    calculated_transit_hours = (
        (
            actual_arrival
            -
            dispatch
        )
        .dt
        .total_seconds()
        /
        3600.0
    )

    stored_transit_hours = pd.to_numeric(
        shipments[
            "actual_transit_hours"
        ],
        errors=
            "raise",
    )

    if not np.allclose(
        calculated_transit_hours.to_numpy(
            dtype=float
        ),
        stored_transit_hours.to_numpy(
            dtype=float
        ),
        atol=
            0.02,
    ):

        raise ValueError(
            "actual_transit_hours inconsistent "
            "with timestamps"
        )

    # ========================================================
    # ARRIVAL VARIANCE
    # ========================================================

    calculated_variance = (
        (
            actual_arrival
            -
            expected_arrival
        )
        .dt
        .total_seconds()
        /
        60.0
    )

    stored_variance = pd.to_numeric(
        shipments[
            "arrival_variance_minutes"
        ],
        errors=
            "raise",
    )

    if not np.allclose(
        calculated_variance.to_numpy(
            dtype=float
        ),
        stored_variance.to_numpy(
            dtype=float
        ),
        atol=
            0.02,
    ):

        raise ValueError(
            "arrival_variance_minutes inconsistent "
            "with timestamps"
        )

    # ========================================================
    # DELAY / EARLY ARRIVAL
    # ========================================================

    expected_delay = (
        calculated_variance
        .clip(
            lower=
                0.0
        )
    )

    expected_early = (
        (
            -
            calculated_variance
        )
        .clip(
            lower=
                0.0
        )
    )

    stored_delay = pd.to_numeric(
        shipments[
            "delay_minutes"
        ],
        errors=
            "raise",
    )

    stored_early = pd.to_numeric(
        shipments[
            "early_arrival_minutes"
        ],
        errors=
            "raise",
    )

    if not np.allclose(
        expected_delay.to_numpy(
            dtype=float
        ),
        stored_delay.to_numpy(
            dtype=float
        ),
        atol=
            0.02,
    ):

        raise ValueError(
            "delay_minutes inconsistent with timestamps"
        )

    if not np.allclose(
        expected_early.to_numpy(
            dtype=float
        ),
        stored_early.to_numpy(
            dtype=float
        ),
        atol=
            0.02,
    ):

        raise ValueError(
            "early_arrival_minutes inconsistent "
            "with timestamps"
        )

    # ========================================================
    # SLA
    # ========================================================

    calculated_sla_breach = (
        actual_arrival
        >
        sla_deadline
    )

    stored_sla_breach = (
        shipments[
            "sla_breach"
        ]
        .astype(bool)
    )

    if not np.array_equal(
        calculated_sla_breach.to_numpy(
            dtype=bool
        ),
        stored_sla_breach.to_numpy(
            dtype=bool
        ),
    ):

        raise ValueError(
            "sla_breach inconsistent with "
            "actual_arrival and sla_deadline"
        )

    # ========================================================
    # ROUTE CONSISTENCY
    # ========================================================

    route_lookup = (
        routes
        .set_index(
            "route_id"
        )
    )

    for shipment in shipments.itertuples(
        index=False
    ):

        route = route_lookup.loc[
            str(
                shipment.route_id
            )
        ]

        checks = {
            "origin_warehouse_id":
                route[
                    "origin_warehouse_id"
                ],

            "destination_warehouse_id":
                route[
                    "destination_warehouse_id"
                ],

            "origin_city_id":
                route[
                    "origin_city_id"
                ],

            "destination_city_id":
                route[
                    "destination_city_id"
                ],

            "origin_region_id":
                route[
                    "origin_region_id"
                ],

            "destination_region_id":
                route[
                    "destination_region_id"
                ],
        }

        for (
            shipment_column,
            expected_value,
        ) in checks.items():

            actual_value = getattr(
                shipment,
                shipment_column,
            )

            if (
                str(
                    actual_value
                )
                !=
                str(
                    expected_value
                )
            ):

                raise ValueError(
                    f"{shipment.shipment_id}: "
                    f"{shipment_column} differs "
                    "from route master"
                )

    # ========================================================
    # VEHICLE OVERLAP
    # ========================================================

    for (
        vehicle_id,
        vehicle_shipments,
    ) in shipments.groupby(
        "vehicle_id"
    ):

        ordered = (
            vehicle_shipments
            .sort_values(
                [
                    "dispatch_time",
                    "shipment_id",
                ]
            )
            .reset_index(
                drop=True
            )
        )

        if len(
            ordered
        ) <= 1:

            continue

        previous_arrivals = (
            pd.to_datetime(
                ordered[
                    "actual_arrival"
                ]
                .iloc[
                    :-1
                ],
                utc=True,
            )
            .reset_index(
                drop=True
            )
        )

        next_dispatches = (
            pd.to_datetime(
                ordered[
                    "dispatch_time"
                ]
                .iloc[
                    1:
                ],
                utc=True,
            )
            .reset_index(
                drop=True
            )
        )

        if (
            next_dispatches
            <
            previous_arrivals
        ).any():

            raise ValueError(
                "Vehicle has overlapping shipments: "
                f"{vehicle_id}"
            )

    # ========================================================
    # BOOLEAN FLAGS
    # ========================================================

    boolean_columns = (
        "weather_disruption",
        "vehicle_breakdown",
        "warehouse_delay",
        "port_delay",
        "customs_delay",
        "sla_breach",
    )

    for column in boolean_columns:

        invalid = (
            ~shipments[
                column
            ]
            .isin(
                [
                    True,
                    False,
                ]
            )
        )

        if invalid.any():

            raise ValueError(
                f"{column} must contain boolean values only"
            )

    # ========================================================
    # STATUS
    # ========================================================

    if (
        set(
            shipments[
                "shipment_status"
            ]
            .astype(str)
        )
        !=
        {
            "DELIVERED"
        }
    ):

        raise ValueError(
            "Historical shipment generator currently "
            "expects DELIVERED records only"
        )

    # ========================================================
    # HIDDEN AI / TRUTH LEAKAGE
    # ========================================================

    leaked_columns = (
        HIDDEN_RUNTIME_COLUMNS
        &
        set(
            shipments.columns
        )
    )

    if leaked_columns:

        raise ValueError(
            "Hidden AI/runtime intelligence leaked "
            "into shipment records: "
            +
            ", ".join(
                sorted(
                    leaked_columns
                )
            )
        )


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_shipment_master(
    routes: pd.DataFrame,
    warehouses: pd.DataFrame,
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
    Public entry point later used by generate_all.py.
    """

    return generate_shipments(
        routes=
            routes,

        warehouses=
            warehouses,

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

    from data.generators.master.warehouses import (
        generate_warehouse_master,
    )

    from data.generators.master.routes import (
        generate_route_master,
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
    # GEOGRAPHY
    # ========================================================

    (
        regions_df,
        cities_df,
    ) = generate_geography()

    # ========================================================
    # WAREHOUSES
    #
    # ACTUAL confirmed signature:
    #
    # generate_warehouse_master(
    #     geography_cities,
    #     generation=None,
    # )
    # ========================================================

    warehouses_df = (
        generate_warehouse_master(
            geography_cities=
                cities_df,

            generation=
                generation_config,
        )
    )

    # ========================================================
    # ROUTES
    #
    # ACTUAL confirmed signature:
    #
    # generate_route_master(
    #     warehouses,
    #     generation=None,
    # )
    # ========================================================

    routes_df = (
        generate_route_master(
            warehouses=
                warehouses_df,

            generation=
                generation_config,
        )
    )

    # ========================================================
    # MASTER DEPENDENCY CHECK
    # ========================================================

    print(
        "\n=== LOGISTICS MASTER DEPENDENCY CHECK ===\n"
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
        "Warehouses:",
        len(
            warehouses_df
        ),
    )

    print(
        "Warehouse missing city_id:",
        int(
            warehouses_df[
                "city_id"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Warehouse missing region_id:",
        int(
            warehouses_df[
                "region_id"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Routes:",
        len(
            routes_df
        ),
    )

    print(
        "Unique routes:",
        routes_df[
            "route_id"
        ]
        .nunique(),
    )

    print(
        "Duplicate route IDs:",
        int(
            routes_df[
                "route_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    # ========================================================
    # CONFIG CHECK
    # ========================================================

    (
        configured_shipment_count,
        configured_fleet_size,
        configured_priorities,
    ) = (
        _get_logistics_generation_settings(
            generation_config
        )
    )

    print(
        "\n=== LOGISTICS CONFIG CHECK ===\n"
    )

    print(
        "Configured shipments:",
        configured_shipment_count,
    )

    print(
        "Configured fleet size:",
        configured_fleet_size,
    )

    print(
        "Configured priorities:",
        configured_priorities,
    )

    # ========================================================
    # GENERATE SHIPMENTS
    # ========================================================

    shipments_df = (
        generate_shipment_master(
            routes=
                routes_df,

            warehouses=
                warehouses_df,

            generation=
                generation_config,

            distributions=
                distribution_config,
        )
    )

    # ========================================================
    # SAMPLE
    # ========================================================

    print(
        "\n=== SHIPMENT SAMPLE ===\n"
    )

    print(
        shipments_df[
            [
                "shipment_id",

                "route_id",

                "origin_city_name",
                "destination_city_name",

                "vehicle_id",

                "priority",
                "units",

                "dispatch_time",

                "expected_arrival",
                "actual_arrival",

                "delay_minutes",
                "sla_breach",

                "weather_disruption",
                "vehicle_breakdown",
                "warehouse_delay",
                "port_delay",
                "customs_delay",
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
    # ROUTE COVERAGE
    # ========================================================

    print(
        "\n=== SHIPMENTS BY ROUTE ===\n"
    )

    route_summary = (
        shipments_df
        .groupby(
            [
                "route_id",
                "origin_city_name",
                "destination_city_name",
            ],
            as_index=False,
        )
        .agg(
            shipments=(
                "shipment_id",
                "size",
            ),

            units=(
                "units",
                "sum",
            ),

            delayed_shipments=(
                "delay_minutes",
                lambda values:
                    int(
                        (
                            values
                            >
                            0
                        )
                        .sum()
                    ),
            ),

            sla_breaches=(
                "sla_breach",
                "sum",
            ),

            average_delay_minutes=(
                "delay_minutes",
                "mean",
            ),
        )
        .sort_values(
            "shipments",
            ascending=False,
        )
    )

    route_summary[
        "sla_breach_rate"
    ] = (
        route_summary[
            "sla_breaches"
        ]
        /
        route_summary[
            "shipments"
        ]
    ).round(
        4
    )

    route_summary[
        "average_delay_minutes"
    ] = (
        route_summary[
            "average_delay_minutes"
        ]
        .round(
            2
        )
    )

    print(
        route_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # PRIORITY
    # ========================================================

    print(
        "\n=== SHIPMENT PRIORITY MIX ===\n"
    )

    priority_summary = (
        shipments_df[
            "priority"
        ]
        .value_counts()
        .rename_axis(
            "priority"
        )
        .reset_index(
            name=
                "shipments"
        )
    )

    priority_summary[
        "rate"
    ] = (
        priority_summary[
            "shipments"
        ]
        /
        len(
            shipments_df
        )
    ).round(
        4
    )

    print(
        priority_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # DISRUPTION RATES
    # ========================================================

    print(
        "\n=== LOGISTICS DISRUPTION RATES ===\n"
    )

    disruption_columns = [
        "weather_disruption",
        "vehicle_breakdown",
        "warehouse_delay",
        "port_delay",
        "customs_delay",
    ]

    for column in disruption_columns:

        print(
            f"{column}:",
            round(
                float(
                    shipments_df[
                        column
                    ]
                    .mean()
                ),
                4,
            ),
            (
                "("
                f"{int(shipments_df[column].sum())} "
                "shipments)"
            ),
        )

    # ========================================================
    # CROSS-BORDER ELIGIBILITY
    # ========================================================

    cross_border_routes = int(
        sum(
            _is_cross_border_or_port_route(
                route
            )

            for route
            in routes_df.to_dict(
                orient="records"
            )
        )
    )

    print(
        "Cross-border/port eligible routes:",
        cross_border_routes,
    )

    # ========================================================
    # SLA
    # ========================================================

    print(
        "\n=== LOGISTICS SLA PERFORMANCE ===\n"
    )

    delayed_mask = (
        shipments_df[
            "delay_minutes"
        ]
        >
        0
    )

    print(
        "Delayed shipments:",
        int(
            delayed_mask.sum()
        ),
    )

    print(
        "Delayed shipment rate:",
        round(
            float(
                delayed_mask.mean()
            ),
            4,
        ),
    )

    print(
        "SLA breaches:",
        int(
            shipments_df[
                "sla_breach"
            ]
            .sum()
        ),
    )

    print(
        "SLA breach rate:",
        round(
            float(
                shipments_df[
                    "sla_breach"
                ]
                .mean()
            ),
            4,
        ),
    )

    positive_delays = (
        shipments_df.loc[
            delayed_mask,
            "delay_minutes",
        ]
    )

    print(
        "Average positive delay minutes:",
        (
            round(
                float(
                    positive_delays.mean()
                ),
                2,
            )

            if not positive_delays.empty

            else 0.0
        ),
    )

    print(
        "Maximum delay minutes:",
        round(
            float(
                shipments_df[
                    "delay_minutes"
                ]
                .max()
            ),
            2,
        ),
    )

    # ========================================================
    # FLEET
    # ========================================================

    print(
        "\n=== LOGISTICS FLEET UTILIZATION ===\n"
    )

    shipments_per_vehicle = (
        shipments_df
        .groupby(
            "vehicle_id"
        )
        .size()
    )

    print(
        "Unique vehicles used:",
        shipments_df[
            "vehicle_id"
        ]
        .nunique(),
    )

    print(
        "Average shipments per used vehicle:",
        round(
            float(
                shipments_per_vehicle.mean()
            ),
            2,
        ),
    )

    print(
        "Maximum shipments per vehicle:",
        int(
            shipments_per_vehicle.max()
        ),
    )

    print(
        "Shipments with dispatch wait:",
        int(
            (
                shipments_df[
                    "dispatch_delay_minutes"
                ]
                >
                0
            )
            .sum()
        ),
    )

    print(
        "Maximum dispatch wait minutes:",
        round(
            float(
                shipments_df[
                    "dispatch_delay_minutes"
                ]
                .max()
            ),
            2,
        ),
    )

    # ========================================================
    # WAREHOUSE COVERAGE
    # ========================================================

    print(
        "\n=== SHIPMENT ORIGIN WAREHOUSE COVERAGE ===\n"
    )

    warehouse_summary = (
        shipments_df
        .groupby(
            [
                "origin_warehouse_id",
                "origin_warehouse_name",
                "origin_city_name",
                "origin_region_name",
            ],
            as_index=False,
        )
        .agg(
            shipments=(
                "shipment_id",
                "size",
            ),

            total_units=(
                "units",
                "sum",
            ),

            sla_breaches=(
                "sla_breach",
                "sum",
            ),
        )
        .sort_values(
            "shipments",
            ascending=False,
        )
    )

    print(
        warehouse_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    print(
        "\n=== SHIPMENT VALIDATION ===\n"
    )

    print(
        "Rows:",
        len(
            shipments_df
        ),
    )

    print(
        "Unique shipment IDs:",
        shipments_df[
            "shipment_id"
        ]
        .nunique(),
    )

    print(
        "Routes represented:",
        shipments_df[
            "route_id"
        ]
        .nunique(),
    )

    print(
        "Origin warehouses represented:",
        shipments_df[
            "origin_warehouse_id"
        ]
        .nunique(),
    )

    print(
        "Destination warehouses represented:",
        shipments_df[
            "destination_warehouse_id"
        ]
        .nunique(),
    )

    print(
        "Vehicles represented:",
        shipments_df[
            "vehicle_id"
        ]
        .nunique(),
    )

    print(
        "Duplicate shipment IDs:",
        int(
            shipments_df[
                "shipment_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Missing origin city IDs:",
        int(
            shipments_df[
                "origin_city_id"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Missing origin region IDs:",
        int(
            shipments_df[
                "origin_region_id"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Missing destination city IDs:",
        int(
            shipments_df[
                "destination_city_id"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Missing destination region IDs:",
        int(
            shipments_df[
                "destination_region_id"
            ]
            .isna()
            .sum()
        ),
    )

    impossible_arrivals = (
        pd.to_datetime(
            shipments_df[
                "actual_arrival"
            ],
            utc=True,
        )
        <=
        pd.to_datetime(
            shipments_df[
                "dispatch_time"
            ],
            utc=True,
        )
    )

    print(
        "Arrival before/equal dispatch:",
        int(
            impossible_arrivals.sum()
        ),
    )

    print(
        "Hidden truth/runtime leakage:",
        sorted(
            HIDDEN_RUNTIME_COLUMNS
            &
            set(
                shipments_df.columns
            )
        ),
    )

    print(
        "\nGenerated "
        f"{len(shipments_df)} "
        "synthetic Logistics shipments successfully."
    )