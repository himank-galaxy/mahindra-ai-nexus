"""
Synthetic Logistics Warehouse Event Generator
for Mahindra AI Nexus.

Generates operational warehouse-event evidence from:

    Warehouses
        +
    Validated Logistics Shipments
        ↓
    Warehouse Events

Current model:

    Every shipment creates exactly two warehouse events:

        1. OUTBOUND_HANDOFF
           at shipment origin / dispatch time

        2. INBOUND_RECEIPT
           at shipment destination / actual arrival time

With:

    7,500 shipments

this produces:

    15,000 warehouse events

The generator creates observed operational evidence such as:

    warehouse utilization
    dock queue depth
    dock wait
    handling time
    picking delay
    putaway delay
    congestion flag
    inventory movement

It DOES NOT create runtime AI outputs such as:

    bottleneck probability
    SLA risk prediction
    recommended action
    reroute recommendation
    confidence score
    model score

This module returns a DataFrame only.
It does not write CSV files.
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
# EVENT TYPES
# ============================================================

OUTBOUND_HANDOFF = "OUTBOUND_HANDOFF"
INBOUND_RECEIPT = "INBOUND_RECEIPT"

VALID_EVENT_TYPES = {
    OUTBOUND_HANDOFF,
    INBOUND_RECEIPT,
}

VALID_DIRECTIONS = {
    "OUTBOUND",
    "INBOUND",
}


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
# SYNTHETIC OPERATING ASSUMPTIONS
#
# Engineering assumptions only.
# Not Mahindra operational statistics.
# ============================================================

WAREHOUSE_OPERATING_HOURS_PER_DAY = 16.0

PEAK_OPERATING_HOURS = {
    8,
    9,
    10,
    11,
    16,
    17,
    18,
    19,
    20,
}


# ============================================================
# OBSERVED CONGESTION THRESHOLDS
# ============================================================

CONGESTION_UTILIZATION_THRESHOLD = 0.86

CONGESTION_QUEUE_DEPTH_THRESHOLD = 5

CONGESTION_DOCK_WAIT_THRESHOLD_MINUTES = 30.0


# ============================================================
# FORBIDDEN AI / HIDDEN-TRUTH OUTPUTS
# ============================================================

HIDDEN_RUNTIME_COLUMNS = {
    "delay_probability",
    "predicted_delay_probability",
    "predicted_delay_minutes",

    "sla_risk",
    "sla_risk_score",
    "sla_breach_probability",

    "warehouse_bottleneck_probability",
    "bottleneck_probability",

    "risk_score",
    "risk_band",

    "recommended_action",
    "recommended_reroute",

    "recommendation_score",

    "confidence",
    "confidence_score",

    "model_score",
    "model_probability",

    "true_bottleneck",
    "true_delay_cause",
}


# ============================================================
# REQUIRED WAREHOUSE MASTER SCHEMA
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


# ============================================================
# REQUIRED SHIPMENT SCHEMA
# ============================================================

SHIPMENT_REQUIRED_COLUMNS: set[str] = {
    "shipment_id",

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

    "vehicle_id",

    "units",
    "priority",

    "dispatch_time",
    "actual_arrival",

    "warehouse_delay",

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
    Normalize boolean-like fields safely.
    """

    if pd.api.types.is_bool_dtype(series):
        return (
            series
            .fillna(False)
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
        if pd.isna(value):
            return False

        if isinstance(
            value,
            (
                bool,
                np.bool_,
            ),
        ):
            return bool(value)

        normalized = (
            str(value)
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
        .map(convert)
        .astype(bool)
    )


# ============================================================
# GENERATION WINDOW
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


# ============================================================
# TARGET EVENT COUNT
# ============================================================


def _get_target_event_count(
    generation: Mapping[str, Any],
) -> int:
    """
    Actual generation.yaml structure:

        logistics:
            warehouse_events:
                target_count: 15000
    """

    try:
        target_count = int(
            generation[
                "logistics"
            ][
                "warehouse_events"
            ][
                "target_count"
            ]
        )

    except KeyError as exc:
        raise KeyError(
            "Missing "
            "generation.logistics."
            "warehouse_events.target_count"
        ) from exc

    if target_count <= 0:
        raise ValueError(
            "generation.logistics."
            "warehouse_events.target_count "
            "must be > 0"
        )

    return target_count


# ============================================================
# PREPARE WAREHOUSE MASTER
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
        set(warehouses.columns)
    )

    if missing_columns:
        raise ValueError(
            "Warehouses DataFrame missing columns: "
            +
            ", ".join(
                sorted(missing_columns)
            )
        )

    result = warehouses.copy(
        deep=True
    )

    # --------------------------------------------------------
    # Required identifiers
    # --------------------------------------------------------

    for column in (
        "warehouse_id",
        "city_id",
        "region_id",
    ):
        if (
            result[column]
            .isna()
            .any()
        ):
            raise ValueError(
                "Warehouses DataFrame contains "
                f"missing values in {column}"
            )

    # --------------------------------------------------------
    # PK uniqueness
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Active only
    # --------------------------------------------------------

    result["active"] = (
        _to_bool_series(
            result["active"]
        )
    )

    result = (
        result.loc[
            result["active"]
        ]
        .copy()
    )

    if result.empty:
        raise ValueError(
            "No active warehouses available"
        )

    # --------------------------------------------------------
    # Numeric fields
    # --------------------------------------------------------

    for column in (
        "storage_capacity_units",
        "baseline_utilization_pct",
        "daily_throughput_capacity",
    ):
        result[column] = pd.to_numeric(
            result[column],
            errors="raise",
        )

    if (
        result[
            "storage_capacity_units"
        ]
        <= 0
    ).any():
        raise ValueError(
            "storage_capacity_units must be positive"
        )

    if (
        result[
            "daily_throughput_capacity"
        ]
        <= 0
    ).any():
        raise ValueError(
            "daily_throughput_capacity must be positive"
        )

    utilization = (
        result[
            "baseline_utilization_pct"
        ]
    )

    if (
        (utilization < 0)
        |
        (utilization > 1)
    ).any():
        raise ValueError(
            "baseline_utilization_pct must be "
            "between 0 and 1"
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
# PREPARE SHIPMENTS
# ============================================================


def _prepare_shipments(
    shipments: pd.DataFrame,
    warehouses: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate shipment evidence used by warehouse events.
    """

    if shipments.empty:
        raise ValueError(
            "Shipments DataFrame cannot be empty"
        )

    missing_columns = (
        SHIPMENT_REQUIRED_COLUMNS
        -
        set(shipments.columns)
    )

    if missing_columns:
        raise ValueError(
            "Shipments DataFrame missing columns: "
            +
            ", ".join(
                sorted(missing_columns)
            )
        )

    result = shipments.copy(
        deep=True
    )

    # --------------------------------------------------------
    # Shipment PK
    # --------------------------------------------------------

    if (
        result[
            "shipment_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Shipments contain missing shipment_id"
        )

    if (
        result[
            "shipment_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate shipment_id values found"
        )

    # --------------------------------------------------------
    # Warehouse FKs
    # --------------------------------------------------------

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
            "Shipments reference invalid "
            "origin warehouses"
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
            "Shipments reference invalid "
            "destination warehouses"
        )

    # --------------------------------------------------------
    # Units
    # --------------------------------------------------------

    result["units"] = pd.to_numeric(
        result["units"],
        errors="raise",
    )

    if (
        result["units"]
        <= 0
    ).any():
        raise ValueError(
            "Shipment units must be positive"
        )

    # --------------------------------------------------------
    # Priority
    # --------------------------------------------------------

    invalid_priorities = (
        set(
            result[
                "priority"
            ]
            .astype(str)
        )
        -
        VALID_PRIORITIES
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

    # --------------------------------------------------------
    # Shipment warehouse-delay observation
    # --------------------------------------------------------

    result[
        "warehouse_delay"
    ] = (
        _to_bool_series(
            result[
                "warehouse_delay"
            ]
        )
    )

    # --------------------------------------------------------
    # Time
    # --------------------------------------------------------

    result[
        "dispatch_time"
    ] = pd.to_datetime(
        result[
            "dispatch_time"
        ],
        utc=True,
    )

    result[
        "actual_arrival"
    ] = pd.to_datetime(
        result[
            "actual_arrival"
        ],
        utc=True,
    )

    if (
        result[
            "actual_arrival"
        ]
        <=
        result[
            "dispatch_time"
        ]
    ).any():
        raise ValueError(
            "Shipment actual_arrival must be "
            "after dispatch_time"
        )

    return (
        result
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


# ============================================================
# DOCK COUNT
# ============================================================


def _derive_dock_count(
    daily_throughput_capacity: float,
) -> int:
    """
    Derive synthetic dock count from warehouse throughput.

    Engineering assumption only.
    """

    approximate = int(
        round(
            daily_throughput_capacity
            /
            150.0
        )
    )

    return int(
        np.clip(
            approximate,
            3,
            12,
        )
    )


# ============================================================
# PRIORITY WAIT FACTOR
# ============================================================


def _priority_wait_factor(
    priority: str,
) -> float:
    """
    Operational fast-track assumption.

    Higher priority shipments tend to receive somewhat
    lower dock waits.
    """

    factors = {
        "LOW": 1.08,
        "NORMAL": 1.00,
        "HIGH": 0.90,
        "CRITICAL": 0.78,
    }

    return float(
        factors[priority]
    )


# ============================================================
# BUILD TWO WAREHOUSE TOUCHPOINTS PER SHIPMENT
# ============================================================


def _build_base_events(
    shipments: pd.DataFrame,
    warehouses: pd.DataFrame,
) -> pd.DataFrame:
    """
    Create:

        OUTBOUND_HANDOFF
        INBOUND_RECEIPT

    for every shipment.
    """

    warehouse_lookup = {
        str(row.warehouse_id):
            row._asdict()

        for row in warehouses.itertuples(
            index=False
        )
    }

    rows: list[
        dict[str, Any]
    ] = []

    for shipment in shipments.itertuples(
        index=False
    ):
        units = int(
            shipment.units
        )

        priority = str(
            shipment.priority
        )

        origin_warehouse_id = str(
            shipment.origin_warehouse_id
        )

        destination_warehouse_id = str(
            shipment.destination_warehouse_id
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

        # ====================================================
        # ORIGIN / OUTBOUND
        # ====================================================

        rows.append(
            {
                "shipment_id":
                    str(
                        shipment.shipment_id
                    ),

                "event_sequence":
                    1,

                "route_id":
                    str(
                        shipment.route_id
                    ),

                "vehicle_id":
                    str(
                        shipment.vehicle_id
                    ),

                "event_type":
                    OUTBOUND_HANDOFF,

                "direction":
                    "OUTBOUND",

                "warehouse_id":
                    origin_warehouse_id,

                "warehouse_name":
                    str(
                        origin_warehouse[
                            "warehouse_name"
                        ]
                    ),

                "city_id":
                    str(
                        origin_warehouse[
                            "city_id"
                        ]
                    ),

                "city_name":
                    str(
                        origin_warehouse[
                            "city_name"
                        ]
                    ),

                "region_id":
                    str(
                        origin_warehouse[
                            "region_id"
                        ]
                    ),

                "region_name":
                    str(
                        origin_warehouse[
                            "region_name"
                        ]
                    ),

                "warehouse_type":
                    str(
                        origin_warehouse[
                            "warehouse_type"
                        ]
                    ),

                "event_at":
                    shipment.dispatch_time,

                "units_moved":
                    units,

                "inventory_delta_units":
                    -units,

                "priority":
                    priority,

                # Generation-only fields
                "_baseline_utilization_pct":
                    float(
                        origin_warehouse[
                            "baseline_utilization_pct"
                        ]
                    ),

                "_daily_throughput_capacity":
                    float(
                        origin_warehouse[
                            "daily_throughput_capacity"
                        ]
                    ),

                # shipment warehouse_delay is modeled as
                # origin-side warehouse disruption
                "_source_warehouse_delay":
                    bool(
                        shipment.warehouse_delay
                    ),
            }
        )

        # ====================================================
        # DESTINATION / INBOUND
        # ====================================================

        rows.append(
            {
                "shipment_id":
                    str(
                        shipment.shipment_id
                    ),

                "event_sequence":
                    2,

                "route_id":
                    str(
                        shipment.route_id
                    ),

                "vehicle_id":
                    str(
                        shipment.vehicle_id
                    ),

                "event_type":
                    INBOUND_RECEIPT,

                "direction":
                    "INBOUND",

                "warehouse_id":
                    destination_warehouse_id,

                "warehouse_name":
                    str(
                        destination_warehouse[
                            "warehouse_name"
                        ]
                    ),

                "city_id":
                    str(
                        destination_warehouse[
                            "city_id"
                        ]
                    ),

                "city_name":
                    str(
                        destination_warehouse[
                            "city_name"
                        ]
                    ),

                "region_id":
                    str(
                        destination_warehouse[
                            "region_id"
                        ]
                    ),

                "region_name":
                    str(
                        destination_warehouse[
                            "region_name"
                        ]
                    ),

                "warehouse_type":
                    str(
                        destination_warehouse[
                            "warehouse_type"
                        ]
                    ),

                "event_at":
                    shipment.actual_arrival,

                "units_moved":
                    units,

                "inventory_delta_units":
                    units,

                "priority":
                    priority,

                "_baseline_utilization_pct":
                    float(
                        destination_warehouse[
                            "baseline_utilization_pct"
                        ]
                    ),

                "_daily_throughput_capacity":
                    float(
                        destination_warehouse[
                            "daily_throughput_capacity"
                        ]
                    ),

                "_source_warehouse_delay":
                    False,
            }
        )

    result = pd.DataFrame(
        rows
    )

    result[
        "event_at"
    ] = pd.to_datetime(
        result[
            "event_at"
        ],
        utc=True,
    )

    return (
        result
        .sort_values(
            [
                "event_at",
                "shipment_id",
                "event_sequence",
            ]
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# ADD OBSERVED WAREHOUSE CONDITIONS
# ============================================================


def _add_operational_conditions(
    events: pd.DataFrame,
    rng: np.random.Generator,
    timezone: str,
) -> pd.DataFrame:
    """
    Add observed operational conditions.

    IMPORTANT FIX:

    We deliberately use:

        DataFrame.to_dict(orient="records")

    instead of:

        DataFrame.itertuples()

    because pandas sanitizes tuple-field names for columns
    beginning with "_".

    The temporary columns:

        _baseline_utilization_pct
        _daily_throughput_capacity
        _throughput_pressure
        _source_warehouse_delay
        _peak_hour

    must remain addressable by their exact names.
    """

    result = events.copy(
        deep=True
    )

    # ========================================================
    # HOURLY WAREHOUSE ACTIVITY
    # ========================================================

    result[
        "_event_hour_bucket"
    ] = (
        result[
            "event_at"
        ]
        .dt
        .floor("h")
    )

    result[
        "_hourly_event_count"
    ] = (
        result
        .groupby(
            [
                "warehouse_id",
                "_event_hour_bucket",
            ]
        )[
            "shipment_id"
        ]
        .transform(
            "size"
        )
    )

    result[
        "_hourly_units_moved"
    ] = (
        result
        .groupby(
            [
                "warehouse_id",
                "_event_hour_bucket",
            ]
        )[
            "units_moved"
        ]
        .transform(
            "sum"
        )
    )

    result[
        "_effective_hourly_capacity"
    ] = (
        result[
            "_daily_throughput_capacity"
        ]
        /
        WAREHOUSE_OPERATING_HOURS_PER_DAY
    )

    result[
        "_throughput_pressure"
    ] = (
        result[
            "_hourly_units_moved"
        ]
        /
        result[
            "_effective_hourly_capacity"
        ]
    )

    result[
        "_throughput_pressure"
    ] = (
        result[
            "_throughput_pressure"
        ]
        .clip(
            lower=0.0,
            upper=3.0,
        )
    )

    # ========================================================
    # LOCAL HOUR / PEAK HOUR
    # ========================================================

    local_event_at = (
        result[
            "event_at"
        ]
        .dt
        .tz_convert(
            timezone
        )
    )

    result[
        "_local_hour"
    ] = (
        local_event_at
        .dt
        .hour
    )

    result[
        "_peak_hour"
    ] = (
        result[
            "_local_hour"
        ]
        .isin(
            PEAK_OPERATING_HOURS
        )
    )

    # ========================================================
    # OUTPUT ARRAYS
    # ========================================================

    dock_ids: list[str] = []

    utilization_values: list[float] = []

    queue_depth_values: list[int] = []

    dock_wait_values: list[float] = []

    handling_values: list[float] = []

    picking_delay_values: list[float] = []

    putaway_delay_values: list[float] = []

    congestion_values: list[bool] = []

    # ========================================================
    # FIXED ITERATION METHOD
    # ========================================================

    event_records = (
        result
        .to_dict(
            orient="records"
        )
    )

    for event in event_records:
        baseline_utilization = float(
            event[
                "_baseline_utilization_pct"
            ]
        )

        daily_capacity = float(
            event[
                "_daily_throughput_capacity"
            ]
        )

        throughput_pressure = float(
            event[
                "_throughput_pressure"
            ]
        )

        peak_hour = bool(
            event[
                "_peak_hour"
            ]
        )

        source_warehouse_delay = bool(
            event[
                "_source_warehouse_delay"
            ]
        )

        priority = str(
            event[
                "priority"
            ]
        )

        units = int(
            event[
                "units_moved"
            ]
        )

        event_type = str(
            event[
                "event_type"
            ]
        )

        warehouse_id = str(
            event[
                "warehouse_id"
            ]
        )

        # ====================================================
        # OBSERVED UTILIZATION
        # ====================================================

        pressure_increment = (
            0.14
            *
            min(
                throughput_pressure,
                1.5,
            )
        )

        peak_increment = (
            0.035
            if peak_hour
            else 0.0
        )

        disruption_increment = (
            0.10
            if source_warehouse_delay
            else 0.0
        )

        utilization_noise = float(
            rng.normal(
                loc=0.0,
                scale=0.025,
            )
        )

        warehouse_utilization = float(
            np.clip(
                baseline_utilization
                +
                pressure_increment
                +
                peak_increment
                +
                disruption_increment
                +
                utilization_noise,
                0.25,
                0.98,
            )
        )

        # ====================================================
        # DOCK ASSIGNMENT
        # ====================================================

        dock_count = (
            _derive_dock_count(
                daily_capacity
            )
        )

        dock_number = int(
            rng.integers(
                1,
                dock_count + 1,
            )
        )

        dock_id = (
            f"{warehouse_id}"
            f"_DOCK_"
            f"{dock_number:02d}"
        )

        # ====================================================
        # QUEUE DEPTH
        # ====================================================

        utilization_pressure = max(
            0.0,
            (
                warehouse_utilization
                -
                0.65
            )
            /
            0.35,
        )

        queue_lambda = (
            0.30
            +
            2.40
            *
            throughput_pressure
            +
            1.70
            *
            utilization_pressure
            +
            (
                1.80
                if source_warehouse_delay
                else 0.0
            )
            +
            (
                0.40
                if peak_hour
                else 0.0
            )
        )

        queue_lambda = float(
            np.clip(
                queue_lambda,
                0.10,
                10.0,
            )
        )

        dock_queue_depth = int(
            rng.poisson(
                queue_lambda
            )
        )

        dock_queue_depth = int(
            np.clip(
                dock_queue_depth,
                0,
                20,
            )
        )

        # ====================================================
        # DOCK WAIT
        # ====================================================

        wait_mean = (
            2.0
            +
            6.0
            *
            dock_queue_depth
            +
            10.0
            *
            throughput_pressure
            +
            (
                22.0
                if source_warehouse_delay
                else 0.0
            )
        )

        if (
            warehouse_utilization
            >
            0.80
        ):
            wait_mean += (
                20.0
                *
                (
                    warehouse_utilization
                    -
                    0.80
                )
                /
                0.20
            )

        dock_wait_minutes = float(
            max(
                0.0,
                rng.normal(
                    loc=wait_mean,
                    scale=5.0,
                ),
            )
        )

        dock_wait_minutes *= (
            _priority_wait_factor(
                priority
            )
        )

        dock_wait_minutes = float(
            np.clip(
                dock_wait_minutes,
                0.0,
                180.0,
            )
        )

        # ====================================================
        # HANDLING TIME
        # ====================================================

        if (
            event_type
            ==
            OUTBOUND_HANDOFF
        ):
            base_handling_minutes = (
                10.0
                +
                2.1
                *
                units
            )

        elif (
            event_type
            ==
            INBOUND_RECEIPT
        ):
            base_handling_minutes = (
                9.0
                +
                1.7
                *
                units
            )

        else:
            raise ValueError(
                "Unexpected warehouse event_type: "
                f"{event_type}"
            )

        utilization_multiplier = (
            1.0
            +
            0.50
            *
            max(
                0.0,
                warehouse_utilization
                -
                0.65,
            )
        )

        handling_minutes = (
            base_handling_minutes
            *
            utilization_multiplier
        )

        handling_minutes += float(
            rng.normal(
                loc=0.0,
                scale=3.0,
            )
        )

        if source_warehouse_delay:
            handling_minutes += float(
                rng.uniform(
                    6.0,
                    18.0,
                )
            )

        handling_minutes = float(
            np.clip(
                handling_minutes,
                5.0,
                180.0,
            )
        )

        # ====================================================
        # PROCESS-SPECIFIC OBSERVED DELAY
        # ====================================================

        handling_overrun = max(
            0.0,
            handling_minutes
            -
            (
                base_handling_minutes
                *
                1.05
            ),
        )

        queue_overrun = max(
            0.0,
            dock_wait_minutes
            -
            10.0,
        )

        operation_delay_minutes = (
            handling_overrun
            +
            0.35
            *
            queue_overrun
        )

        if (
            event_type
            ==
            OUTBOUND_HANDOFF
        ):
            picking_delay_minutes = float(
                operation_delay_minutes
            )

            putaway_delay_minutes = 0.0

        else:
            picking_delay_minutes = 0.0

            putaway_delay_minutes = float(
                operation_delay_minutes
            )

        # ====================================================
        # OBSERVED CONGESTION
        # ====================================================

        congestion_flag = bool(
            (
                warehouse_utilization
                >=
                CONGESTION_UTILIZATION_THRESHOLD
            )
            or
            (
                dock_queue_depth
                >=
                CONGESTION_QUEUE_DEPTH_THRESHOLD
            )
            or
            (
                dock_wait_minutes
                >=
                CONGESTION_DOCK_WAIT_THRESHOLD_MINUTES
            )
        )

        # ====================================================
        # APPEND OUTPUTS
        # ====================================================

        dock_ids.append(
            dock_id
        )

        utilization_values.append(
            round(
                warehouse_utilization,
                4,
            )
        )

        queue_depth_values.append(
            dock_queue_depth
        )

        dock_wait_values.append(
            round(
                dock_wait_minutes,
                3,
            )
        )

        handling_values.append(
            round(
                handling_minutes,
                3,
            )
        )

        picking_delay_values.append(
            round(
                picking_delay_minutes,
                3,
            )
        )

        putaway_delay_values.append(
            round(
                putaway_delay_minutes,
                3,
            )
        )

        congestion_values.append(
            congestion_flag
        )

    # ========================================================
    # ASSIGN GENERATED COLUMNS
    # ========================================================

    result["dock_id"] = dock_ids

    result[
        "warehouse_utilization_pct"
    ] = utilization_values

    result[
        "dock_queue_depth"
    ] = queue_depth_values

    result[
        "dock_wait_minutes"
    ] = dock_wait_values

    result[
        "handling_minutes"
    ] = handling_values

    result[
        "picking_delay_minutes"
    ] = picking_delay_values

    result[
        "putaway_delay_minutes"
    ] = putaway_delay_values

    result[
        "congestion_flag"
    ] = congestion_values

    # ========================================================
    # DROP GENERATION-ONLY COLUMNS
    # ========================================================

    internal_columns = [
        "_baseline_utilization_pct",
        "_daily_throughput_capacity",

        "_source_warehouse_delay",

        "_event_hour_bucket",
        "_hourly_event_count",
        "_hourly_units_moved",

        "_effective_hourly_capacity",
        "_throughput_pressure",

        "_local_hour",
        "_peak_hour",
    ]

    return (
        result
        .drop(
            columns=internal_columns
        )
    )


# ============================================================
# GENERATE WAREHOUSE EVENTS
# ============================================================


def generate_warehouse_events(
    shipments: pd.DataFrame,
    warehouses: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate Logistics warehouse events.
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    # --------------------------------------------------------
    # Config
    # --------------------------------------------------------

    (
        generation_start,
        generation_end,
        timezone,
    ) = (
        _get_generation_window(
            generation
        )
    )

    target_event_count = (
        _get_target_event_count(
            generation
        )
    )

    # --------------------------------------------------------
    # Upstream datasets
    # --------------------------------------------------------

    warehouses = (
        _prepare_warehouses(
            warehouses
        )
    )

    shipments = (
        _prepare_shipments(
            shipments=shipments,
            warehouses=warehouses,
        )
    )

    # ========================================================
    # TWO EVENTS PER SHIPMENT
    # ========================================================

    expected_event_count = (
        len(shipments)
        *
        2
    )

    if (
        target_event_count
        !=
        expected_event_count
    ):
        raise ValueError(
            "Warehouse event target does not match "
            "the two-touchpoint shipment model. "
            f"Shipments={len(shipments)}, "
            f"required_events={expected_event_count}, "
            f"configured_target={target_event_count}"
        )

    # --------------------------------------------------------
    # RNG
    # --------------------------------------------------------

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
            "logistics.warehouse_events",
        )
    )

    # --------------------------------------------------------
    # Provenance
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Create shipment touchpoints
    # --------------------------------------------------------

    events = (
        _build_base_events(
            shipments=shipments,
            warehouses=warehouses,
        )
    )

    # --------------------------------------------------------
    # Add operational observations
    # --------------------------------------------------------

    events = (
        _add_operational_conditions(
            events=events,
            rng=rng,
            timezone=timezone,
        )
    )

    # ========================================================
    # EVENT IDS
    # ========================================================

    events.insert(
        0,
        "warehouse_event_id",
        [
            generate_id(
                "WHEVT_SYN",
                position,
                width=8,
            )

            for position in range(
                1,
                len(events) + 1,
            )
        ],
    )

    # ========================================================
    # STATUS / PROVENANCE
    # ========================================================

    events[
        "event_status"
    ] = "COMPLETED"

    events[
        "data_origin"
    ] = data_origin

    events[
        "generator_version"
    ] = generator_version

    # ========================================================
    # FINAL COLUMN ORDER
    # ========================================================

    output_columns = [
        "warehouse_event_id",

        "shipment_id",
        "event_sequence",

        "route_id",
        "vehicle_id",

        "event_type",
        "direction",

        "warehouse_id",
        "warehouse_name",

        "city_id",
        "city_name",

        "region_id",
        "region_name",

        "warehouse_type",

        "event_at",

        "units_moved",
        "inventory_delta_units",

        "priority",

        "dock_id",

        "warehouse_utilization_pct",

        "dock_queue_depth",
        "dock_wait_minutes",

        "handling_minutes",

        "picking_delay_minutes",
        "putaway_delay_minutes",

        "congestion_flag",

        "event_status",

        "data_origin",
        "generator_version",
    ]

    events = events[
        output_columns
    ].copy()

    # ========================================================
    # VALIDATION
    # ========================================================

    validate_warehouse_events(
        events=events,
        shipments=shipments,
        warehouses=warehouses,

        generation_start=generation_start,
        generation_end=generation_end,

        expected_event_count=target_event_count,
    )

    return events


# ============================================================
# VALIDATION
# ============================================================


def validate_warehouse_events(
    events: pd.DataFrame,
    shipments: pd.DataFrame,
    warehouses: pd.DataFrame,
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
    expected_event_count: int,
) -> None:
    """
    Validate warehouse-event integrity.
    """

    required_columns = {
        "warehouse_event_id",

        "shipment_id",
        "event_sequence",

        "route_id",
        "vehicle_id",

        "event_type",
        "direction",

        "warehouse_id",
        "warehouse_name",

        "city_id",
        "city_name",

        "region_id",
        "region_name",

        "warehouse_type",

        "event_at",

        "units_moved",
        "inventory_delta_units",

        "priority",

        "dock_id",

        "warehouse_utilization_pct",

        "dock_queue_depth",
        "dock_wait_minutes",

        "handling_minutes",

        "picking_delay_minutes",
        "putaway_delay_minutes",

        "congestion_flag",

        "event_status",

        "data_origin",
        "generator_version",
    }

    missing_columns = (
        required_columns
        -
        set(events.columns)
    )

    if missing_columns:
        raise ValueError(
            "Warehouse events missing columns: "
            +
            ", ".join(
                sorted(missing_columns)
            )
        )

    if events.empty:
        raise ValueError(
            "Warehouse event generator produced zero rows"
        )

    # ========================================================
    # EXACT ROW COUNT
    # ========================================================

    if (
        len(events)
        !=
        expected_event_count
    ):
        raise ValueError(
            "Unexpected warehouse event count. "
            f"Expected={expected_event_count}, "
            f"actual={len(events)}"
        )

    # ========================================================
    # EVENT PK
    # ========================================================

    if (
        events[
            "warehouse_event_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Warehouse events contain missing IDs"
        )

    if (
        events[
            "warehouse_event_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate warehouse_event_id values found"
        )

    # ========================================================
    # SHIPMENT FK
    # ========================================================

    valid_shipment_ids = set(
        shipments[
            "shipment_id"
        ]
        .astype(str)
    )

    event_shipment_ids = set(
        events[
            "shipment_id"
        ]
        .astype(str)
    )

    invalid_shipment_ids = (
        event_shipment_ids
        -
        valid_shipment_ids
    )

    if invalid_shipment_ids:
        raise ValueError(
            "Warehouse events reference "
            "invalid shipment IDs"
        )

    if (
        event_shipment_ids
        !=
        valid_shipment_ids
    ):
        raise ValueError(
            "Not every shipment is represented "
            "in warehouse events"
        )

    # ========================================================
    # EXACTLY TWO EVENTS PER SHIPMENT
    # ========================================================

    event_count_per_shipment = (
        events
        .groupby(
            "shipment_id"
        )
        .size()
    )

    if (
        event_count_per_shipment
        !=
        2
    ).any():
        raise ValueError(
            "Every shipment must have exactly "
            "two warehouse events"
        )

    # ========================================================
    # EXACT EVENT TYPE PAIR
    # ========================================================

    event_type_counts = (
        events
        .groupby(
            [
                "shipment_id",
                "event_type",
            ]
        )
        .size()
        .unstack(
            fill_value=0
        )
    )

    for event_type in VALID_EVENT_TYPES:
        if (
            event_type
            not in event_type_counts.columns
        ):
            raise ValueError(
                "Missing warehouse event type: "
                f"{event_type}"
            )

        if (
            event_type_counts[
                event_type
            ]
            !=
            1
        ).any():
            raise ValueError(
                "Every shipment must have exactly one "
                f"{event_type}"
            )

    # ========================================================
    # EVENT SEQUENCE
    # ========================================================

    outbound_mask = (
        events[
            "event_type"
        ]
        ==
        OUTBOUND_HANDOFF
    )

    inbound_mask = (
        events[
            "event_type"
        ]
        ==
        INBOUND_RECEIPT
    )

    if (
        events.loc[
            outbound_mask,
            "event_sequence",
        ]
        !=
        1
    ).any():
        raise ValueError(
            "OUTBOUND_HANDOFF must have "
            "event_sequence=1"
        )

    if (
        events.loc[
            inbound_mask,
            "event_sequence",
        ]
        !=
        2
    ).any():
        raise ValueError(
            "INBOUND_RECEIPT must have "
            "event_sequence=2"
        )

    # ========================================================
    # EVENT TYPES
    # ========================================================

    invalid_event_types = (
        set(
            events[
                "event_type"
            ]
            .astype(str)
        )
        -
        VALID_EVENT_TYPES
    )

    if invalid_event_types:
        raise ValueError(
            "Invalid warehouse event types: "
            +
            ", ".join(
                sorted(
                    invalid_event_types
                )
            )
        )

    # ========================================================
    # DIRECTION
    # ========================================================

    invalid_directions = (
        set(
            events[
                "direction"
            ]
            .astype(str)
        )
        -
        VALID_DIRECTIONS
    )

    if invalid_directions:
        raise ValueError(
            "Invalid warehouse directions"
        )

    if (
        events.loc[
            outbound_mask,
            "direction",
        ]
        !=
        "OUTBOUND"
    ).any():
        raise ValueError(
            "OUTBOUND_HANDOFF must use "
            "direction OUTBOUND"
        )

    if (
        events.loc[
            inbound_mask,
            "direction",
        ]
        !=
        "INBOUND"
    ).any():
        raise ValueError(
            "INBOUND_RECEIPT must use "
            "direction INBOUND"
        )

    # ========================================================
    # WAREHOUSE FK
    # ========================================================

    valid_warehouse_ids = set(
        warehouses[
            "warehouse_id"
        ]
        .astype(str)
    )

    invalid_warehouse_ids = (
        set(
            events[
                "warehouse_id"
            ]
            .astype(str)
        )
        -
        valid_warehouse_ids
    )

    if invalid_warehouse_ids:
        raise ValueError(
            "Warehouse events reference "
            "invalid warehouse IDs"
        )

    # ========================================================
    # SHIPMENT RELATIONSHIP CONSISTENCY
    # ========================================================

    shipment_lookup = (
        shipments
        .set_index(
            "shipment_id"
        )
    )

    for event in events.itertuples(
        index=False
    ):
        shipment = shipment_lookup.loc[
            str(
                event.shipment_id
            )
        ]

        if (
            str(
                event.route_id
            )
            !=
            str(
                shipment[
                    "route_id"
                ]
            )
        ):
            raise ValueError(
                f"{event.warehouse_event_id}: "
                "route_id mismatch"
            )

        if (
            str(
                event.vehicle_id
            )
            !=
            str(
                shipment[
                    "vehicle_id"
                ]
            )
        ):
            raise ValueError(
                f"{event.warehouse_event_id}: "
                "vehicle_id mismatch"
            )

        if (
            int(
                event.units_moved
            )
            !=
            int(
                shipment[
                    "units"
                ]
            )
        ):
            raise ValueError(
                f"{event.warehouse_event_id}: "
                "units_moved mismatch"
            )

        if (
            str(
                event.priority
            )
            !=
            str(
                shipment[
                    "priority"
                ]
            )
        ):
            raise ValueError(
                f"{event.warehouse_event_id}: "
                "priority mismatch"
            )

        event_timestamp = pd.Timestamp(
            event.event_at
        )

        if (
            event.event_type
            ==
            OUTBOUND_HANDOFF
        ):
            if (
                str(
                    event.warehouse_id
                )
                !=
                str(
                    shipment[
                        "origin_warehouse_id"
                    ]
                )
            ):
                raise ValueError(
                    f"{event.warehouse_event_id}: "
                    "outbound warehouse does not "
                    "match shipment origin"
                )

            expected_timestamp = pd.Timestamp(
                shipment[
                    "dispatch_time"
                ]
            )

            if (
                event_timestamp
                !=
                expected_timestamp
            ):
                raise ValueError(
                    f"{event.warehouse_event_id}: "
                    "outbound timestamp does not "
                    "match shipment dispatch"
                )

        elif (
            event.event_type
            ==
            INBOUND_RECEIPT
        ):
            if (
                str(
                    event.warehouse_id
                )
                !=
                str(
                    shipment[
                        "destination_warehouse_id"
                    ]
                )
            ):
                raise ValueError(
                    f"{event.warehouse_event_id}: "
                    "inbound warehouse does not "
                    "match shipment destination"
                )

            expected_timestamp = pd.Timestamp(
                shipment[
                    "actual_arrival"
                ]
            )

            if (
                event_timestamp
                !=
                expected_timestamp
            ):
                raise ValueError(
                    f"{event.warehouse_event_id}: "
                    "inbound timestamp does not "
                    "match shipment arrival"
                )

    # ========================================================
    # EVENT TIME WINDOW
    # ========================================================

    event_at = pd.to_datetime(
        events[
            "event_at"
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
        event_at
        <
        generation_start_utc
    ).any():
        raise ValueError(
            "Warehouse event occurs before "
            "generation start"
        )

    if (
        event_at
        >=
        generation_end_utc
    ).any():
        raise ValueError(
            "Warehouse event occurs on/after "
            "generation end"
        )

    # ========================================================
    # OUTBOUND MUST PRECEDE INBOUND
    # ========================================================

    event_time_table = (
        events
        .pivot(
            index="shipment_id",
            columns="event_type",
            values="event_at",
        )
    )

    outbound_time = pd.to_datetime(
        event_time_table[
            OUTBOUND_HANDOFF
        ],
        utc=True,
    )

    inbound_time = pd.to_datetime(
        event_time_table[
            INBOUND_RECEIPT
        ],
        utc=True,
    )

    if (
        inbound_time
        <=
        outbound_time
    ).any():
        raise ValueError(
            "Inbound warehouse receipt must occur "
            "after outbound handoff"
        )

    # ========================================================
    # INVENTORY MOVEMENT
    # ========================================================

    if (
        events.loc[
            outbound_mask,
            "inventory_delta_units",
        ]
        >=
        0
    ).any():
        raise ValueError(
            "Outbound events must decrease inventory"
        )

    if (
        events.loc[
            inbound_mask,
            "inventory_delta_units",
        ]
        <=
        0
    ).any():
        raise ValueError(
            "Inbound events must increase inventory"
        )

    if not np.array_equal(
        np.abs(
            events[
                "inventory_delta_units"
            ]
            .to_numpy(
                dtype=int
            )
        ),
        events[
            "units_moved"
        ]
        .to_numpy(
            dtype=int
        ),
    ):
        raise ValueError(
            "inventory_delta_units magnitude "
            "must equal units_moved"
        )

    # ========================================================
    # UTILIZATION
    # ========================================================

    utilization = pd.to_numeric(
        events[
            "warehouse_utilization_pct"
        ],
        errors="raise",
    )

    if (
        (utilization < 0)
        |
        (utilization > 1)
    ).any():
        raise ValueError(
            "warehouse_utilization_pct must be "
            "between 0 and 1"
        )

    # ========================================================
    # NONNEGATIVE OPERATING METRICS
    # ========================================================

    nonnegative_columns = (
        "dock_queue_depth",
        "dock_wait_minutes",
        "handling_minutes",
        "picking_delay_minutes",
        "putaway_delay_minutes",
    )

    for column in nonnegative_columns:
        values = pd.to_numeric(
            events[column],
            errors="raise",
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
    # PROCESS-SPECIFIC DELAY
    # ========================================================

    if (
        events.loc[
            outbound_mask,
            "putaway_delay_minutes",
        ]
        !=
        0
    ).any():
        raise ValueError(
            "Outbound events cannot have "
            "putaway delay"
        )

    if (
        events.loc[
            inbound_mask,
            "picking_delay_minutes",
        ]
        !=
        0
    ).any():
        raise ValueError(
            "Inbound events cannot have "
            "picking delay"
        )

    # ========================================================
    # DOCK OWNERSHIP
    # ========================================================

    for event in events.itertuples(
        index=False
    ):
        expected_prefix = (
            f"{event.warehouse_id}_DOCK_"
        )

        if not str(
            event.dock_id
        ).startswith(
            expected_prefix
        ):
            raise ValueError(
                f"{event.warehouse_event_id}: "
                "dock_id does not belong to warehouse"
            )

    # ========================================================
    # CONGESTION DERIVATION
    # ========================================================

    calculated_congestion = (
        (
            events[
                "warehouse_utilization_pct"
            ]
            >=
            CONGESTION_UTILIZATION_THRESHOLD
        )
        |
        (
            events[
                "dock_queue_depth"
            ]
            >=
            CONGESTION_QUEUE_DEPTH_THRESHOLD
        )
        |
        (
            events[
                "dock_wait_minutes"
            ]
            >=
            CONGESTION_DOCK_WAIT_THRESHOLD_MINUTES
        )
    )

    if not np.array_equal(
        calculated_congestion.to_numpy(
            dtype=bool
        ),
        events[
            "congestion_flag"
        ]
        .astype(bool)
        .to_numpy(),
    ):
        raise ValueError(
            "congestion_flag inconsistent with "
            "warehouse observations"
        )

    # ========================================================
    # STATUS
    # ========================================================

    if (
        set(
            events[
                "event_status"
            ]
            .astype(str)
        )
        !=
        {
            "COMPLETED"
        }
    ):
        raise ValueError(
            "Warehouse historical events must "
            "have COMPLETED status"
        )

    # ========================================================
    # PROVENANCE
    # ========================================================

    if (
        events[
            "data_origin"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Warehouse events contain "
            "missing data_origin"
        )

    if (
        events[
            "generator_version"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Warehouse events contain missing "
            "generator_version"
        )

    # ========================================================
    # RUNTIME / GROUND-TRUTH LEAKAGE
    # ========================================================

    leaked_columns = (
        HIDDEN_RUNTIME_COLUMNS
        &
        set(events.columns)
    )

    if leaked_columns:
        raise ValueError(
            "Hidden runtime AI / ground truth "
            "leaked into warehouse events: "
            +
            ", ".join(
                sorted(
                    leaked_columns
                )
            )
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

    from data.generators.logistics.shipments import (
        generate_shipment_master,
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
    # MASTER DEPENDENCY CHAIN
    # ========================================================

    (
        regions_df,
        cities_df,
    ) = generate_geography()

    warehouses_df = (
        generate_warehouse_master(
            geography_cities=cities_df,
            generation=generation_config,
        )
    )

    routes_df = (
        generate_route_master(
            warehouses=warehouses_df,
            generation=generation_config,
        )
    )

    # ========================================================
    # SHIPMENTS
    # ========================================================

    shipments_df = (
        generate_shipment_master(
            routes=routes_df,
            warehouses=warehouses_df,

            generation=generation_config,

            distributions=distribution_config,
        )
    )

    # ========================================================
    # WAREHOUSE EVENTS
    # ========================================================

    warehouse_events_df = (
        generate_warehouse_events(
            shipments=shipments_df,
            warehouses=warehouses_df,

            generation=generation_config,
        )
    )

    # ========================================================
    # DEPENDENCY CHECK
    # ========================================================

    print(
        "\n=== WAREHOUSE EVENT DEPENDENCY CHECK ===\n"
    )

    print(
        "Warehouses:",
        len(warehouses_df),
    )

    print(
        "Shipments:",
        len(shipments_df),
    )

    print(
        "Configured warehouse events:",
        _get_target_event_count(
            generation_config
        ),
    )

    # ========================================================
    # SAMPLE
    # ========================================================

    print(
        "\n=== WAREHOUSE EVENT SAMPLE ===\n"
    )

    sample_columns = [
        "warehouse_event_id",

        "shipment_id",

        "event_sequence",
        "event_type",

        "warehouse_id",
        "city_name",

        "vehicle_id",

        "priority",

        "event_at",

        "units_moved",
        "inventory_delta_units",

        "dock_id",

        "warehouse_utilization_pct",

        "dock_queue_depth",
        "dock_wait_minutes",

        "handling_minutes",

        "picking_delay_minutes",
        "putaway_delay_minutes",

        "congestion_flag",
    ]

    print(
        warehouse_events_df[
            sample_columns
        ]
        .head(50)
        .to_string(
            index=False
        )
    )

    # ========================================================
    # EVENT TYPE MIX
    # ========================================================

    print(
        "\n=== WAREHOUSE EVENT TYPE MIX ===\n"
    )

    event_type_summary = (
        warehouse_events_df[
            "event_type"
        ]
        .value_counts()
        .rename_axis(
            "event_type"
        )
        .reset_index(
            name="events"
        )
    )

    event_type_summary[
        "rate"
    ] = (
        event_type_summary[
            "events"
        ]
        /
        len(
            warehouse_events_df
        )
    ).round(4)

    print(
        event_type_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # WAREHOUSE OPERATING SUMMARY
    # ========================================================

    print(
        "\n=== WAREHOUSE OPERATING SUMMARY ===\n"
    )

    warehouse_summary = (
        warehouse_events_df
        .groupby(
            [
                "warehouse_id",
                "warehouse_name",
                "city_name",
                "region_name",
            ],
            as_index=False,
        )
        .agg(
            events=(
                "warehouse_event_id",
                "size",
            ),

            units_moved=(
                "units_moved",
                "sum",
            ),

            average_utilization=(
                "warehouse_utilization_pct",
                "mean",
            ),

            average_queue_depth=(
                "dock_queue_depth",
                "mean",
            ),

            average_dock_wait_minutes=(
                "dock_wait_minutes",
                "mean",
            ),

            average_handling_minutes=(
                "handling_minutes",
                "mean",
            ),

            congestion_events=(
                "congestion_flag",
                "sum",
            ),
        )
        .sort_values(
            "events",
            ascending=False,
        )
    )

    warehouse_summary[
        "congestion_rate"
    ] = (
        warehouse_summary[
            "congestion_events"
        ]
        /
        warehouse_summary[
            "events"
        ]
    )

    for column in (
        "average_utilization",
        "average_queue_depth",
        "average_dock_wait_minutes",
        "average_handling_minutes",
        "congestion_rate",
    ):
        warehouse_summary[
            column
        ] = (
            warehouse_summary[
                column
            ]
            .round(4)
        )

    print(
        warehouse_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # PROCESS DELAYS
    # ========================================================

    print(
        "\n=== WAREHOUSE PROCESS DELAYS ===\n"
    )

    outbound_events = (
        warehouse_events_df.loc[
            warehouse_events_df[
                "event_type"
            ]
            ==
            OUTBOUND_HANDOFF
        ]
    )

    inbound_events = (
        warehouse_events_df.loc[
            warehouse_events_df[
                "event_type"
            ]
            ==
            INBOUND_RECEIPT
        ]
    )

    print(
        "Outbound events:",
        len(
            outbound_events
        ),
    )

    print(
        "Average picking delay minutes:",
        round(
            float(
                outbound_events[
                    "picking_delay_minutes"
                ]
                .mean()
            ),
            2,
        ),
    )

    print(
        "Outbound picking delays > 0:",
        int(
            (
                outbound_events[
                    "picking_delay_minutes"
                ]
                >
                0
            ).sum()
        ),
    )

    print(
        "Inbound events:",
        len(
            inbound_events
        ),
    )

    print(
        "Average putaway delay minutes:",
        round(
            float(
                inbound_events[
                    "putaway_delay_minutes"
                ]
                .mean()
            ),
            2,
        ),
    )

    print(
        "Inbound putaway delays > 0:",
        int(
            (
                inbound_events[
                    "putaway_delay_minutes"
                ]
                >
                0
            ).sum()
        ),
    )

    # ========================================================
    # CONGESTION
    # ========================================================

    print(
        "\n=== WAREHOUSE CONGESTION ===\n"
    )

    print(
        "Congestion events:",
        int(
            warehouse_events_df[
                "congestion_flag"
            ]
            .sum()
        ),
    )

    print(
        "Congestion event rate:",
        round(
            float(
                warehouse_events_df[
                    "congestion_flag"
                ]
                .mean()
            ),
            4,
        ),
    )

    print(
        "Maximum dock queue depth:",
        int(
            warehouse_events_df[
                "dock_queue_depth"
            ]
            .max()
        ),
    )

    print(
        "Maximum dock wait minutes:",
        round(
            float(
                warehouse_events_df[
                    "dock_wait_minutes"
                ]
                .max()
            ),
            2,
        ),
    )

    print(
        "Maximum warehouse utilization:",
        round(
            float(
                warehouse_events_df[
                    "warehouse_utilization_pct"
                ]
                .max()
            ),
            4,
        ),
    )

    # ========================================================
    # PRIORITY WAIT BEHAVIOR
    # ========================================================

    print(
        "\n=== DOCK WAIT BY PRIORITY ===\n"
    )

    priority_summary = (
        warehouse_events_df
        .groupby(
            "priority",
            as_index=False,
        )
        .agg(
            events=(
                "warehouse_event_id",
                "size",
            ),

            average_dock_wait_minutes=(
                "dock_wait_minutes",
                "mean",
            ),

            congestion_rate=(
                "congestion_flag",
                "mean",
            ),
        )
        .sort_values(
            "events",
            ascending=False,
        )
    )

    priority_summary[
        "average_dock_wait_minutes"
    ] = (
        priority_summary[
            "average_dock_wait_minutes"
        ]
        .round(2)
    )

    priority_summary[
        "congestion_rate"
    ] = (
        priority_summary[
            "congestion_rate"
        ]
        .round(4)
    )

    print(
        priority_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # FINAL VALIDATION SUMMARY
    # ========================================================

    print(
        "\n=== WAREHOUSE EVENT VALIDATION ===\n"
    )

    print(
        "Rows:",
        len(
            warehouse_events_df
        ),
    )

    print(
        "Unique warehouse event IDs:",
        warehouse_events_df[
            "warehouse_event_id"
        ]
        .nunique(),
    )

    print(
        "Shipments represented:",
        warehouse_events_df[
            "shipment_id"
        ]
        .nunique(),
    )

    events_per_shipment = (
        warehouse_events_df
        .groupby(
            "shipment_id"
        )
        .size()
    )

    print(
        "Minimum events/shipment:",
        int(
            events_per_shipment.min()
        ),
    )

    print(
        "Maximum events/shipment:",
        int(
            events_per_shipment.max()
        ),
    )

    print(
        "Warehouses represented:",
        warehouse_events_df[
            "warehouse_id"
        ]
        .nunique(),
    )

    print(
        "Duplicate warehouse event IDs:",
        int(
            warehouse_events_df[
                "warehouse_event_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Missing shipment IDs:",
        int(
            warehouse_events_df[
                "shipment_id"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Missing warehouse IDs:",
        int(
            warehouse_events_df[
                "warehouse_id"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Negative dock waits:",
        int(
            (
                warehouse_events_df[
                    "dock_wait_minutes"
                ]
                <
                0
            ).sum()
        ),
    )

    print(
        "Negative handling minutes:",
        int(
            (
                warehouse_events_df[
                    "handling_minutes"
                ]
                <
                0
            ).sum()
        ),
    )

    print(
        "Hidden truth/runtime leakage:",
        sorted(
            HIDDEN_RUNTIME_COLUMNS
            &
            set(
                warehouse_events_df.columns
            )
        ),
    )

    print(
        "\nGenerated "
        f"{len(warehouse_events_df)} "
        "synthetic Logistics warehouse events successfully."
    )