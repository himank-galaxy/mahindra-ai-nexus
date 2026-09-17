"""
Controlled Causal Scenario Generator
for Mahindra AI Nexus.

This module supports two independent causal domains:

1. Manufacturing / Quality
2. Auto / Mobility Business


============================================================
MANUFACTURING FLOW
============================================================

manufacturing_timeseries.py
        ↓
baseline observable manufacturing history
        ↓
scenarios.py
        ↓
adjusted observable manufacturing history
        +
separate manufacturing scenario-event truth


============================================================
MOBILITY FLOW
============================================================

mobility_timeseries.py
        ↓
baseline regional mobility history
        ↓
scenarios.py
        ↓
adjusted observable mobility history
        +
separate mobility scenario-event truth


============================================================
CRITICAL ARCHITECTURAL RULE
============================================================

Runtime DataFrames MUST NOT contain hidden synthetic truth:

    scenario_name
    scenario_event_id
    scenario_severity
    is_anomaly
    root_cause
    expected_warning
    expected_direction
    causal_coefficient
    true causal edges

Scenario metadata is returned separately.

It later belongs under:

    data/ground_truth/causal/

PCMCI receives ONLY observable historical signals.

This module DOES NOT save CSV files.
"""

from __future__ import annotations

import inspect
import json

from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.helpers import (
    load_generation_config,
)

from data.generators.common.seed import (
    derive_seed,
    make_rng,
)


# ============================================================
# SHARED VERSION CONSTANTS
# ============================================================

MANUFACTURING_SCENARIO_VERSION = "MFG_SCENARIO_V1"

MOBILITY_SCENARIO_VERSION = "MOBILITY_SCENARIO_V1"


# ============================================================
# HARD RUNTIME GROUND-TRUTH LEAKAGE GUARD
# ============================================================

FORBIDDEN_RUNTIME_COLUMNS: set[str] = {
    "scenario_name",
    "scenario_id",
    "scenario_event_id",
    "scenario_type",
    "scenario_severity",
    "severity",

    "target_scope",

    "is_anomaly",
    "anomaly_type",

    "root_cause",
    "root_cause_domain",
    "true_root_cause",

    "expected_warning",
    "expected_primary_signal",
    "expected_direction",

    "affected_supplier_lot_ids",
    "affected_supplier_lot_count",

    "parent_scenario_event_id",

    "true_causal_parent",
    "true_causal_child",

    "causal_coefficient",

    "ground_truth_edge",
    "ground_truth_edge_id",

    "expectation_id",

    "true_root_signal",

    "expected_change",
    "expected_lag_hours",

    "generator_effect",

    "ground_truth_version",
}


# ============================================================
# BASIC HELPERS
# ============================================================


def _require_columns(
    dataframe: pd.DataFrame,
    required_columns: set[str],
    dataset_name: str,
) -> None:
    """
    Validate required DataFrame columns.
    """

    missing = (
        required_columns
        -
        set(
            dataframe.columns
        )
    )

    if missing:

        raise ValueError(
            f"{dataset_name} is missing required columns: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )


def _numeric(
    dataframe: pd.DataFrame,
    column: str,
) -> pd.Series:
    """
    Convert an observable column to numeric.
    """

    return pd.to_numeric(
        dataframe[
            column
        ],
        errors="raise",
    )


def _clip_count(
    values: pd.Series | np.ndarray,
) -> np.ndarray:
    """
    Convert scenario-adjusted event counts into
    non-negative integers.
    """

    return (
        np.maximum(
            np.rint(
                np.asarray(
                    values,
                    dtype=float,
                )
            ),
            0,
        )
        .astype(int)
    )


def _scenario_curve(
    length: int,
    start_strength: float = 0.75,
    peak_strength: float = 1.0,
) -> np.ndarray:
    """
    Smooth deterministic deterioration curve.

    Produces a controlled rise/fall instead of an
    unrealistic square-wave scenario.
    """

    if length <= 0:

        return np.array(
            [],
            dtype=float,
        )

    if length == 1:

        return np.array(
            [
                peak_strength
            ],
            dtype=float,
        )

    x = np.linspace(
        0.0,
        1.0,
        length,
    )

    shape = (
        0.55
        +
        0.45
        *
        np.sin(
            np.pi
            *
            x
        )
    )

    return (
        start_strength
        +
        (
            peak_strength
            -
            start_strength
        )
        *
        shape
    )


def _validate_runtime_leakage(
    dataframe: pd.DataFrame,
    dataset_name: str,
) -> None:
    """
    Ensure hidden scenario/causal truth has not entered
    runtime observations.
    """

    leaked = (
        FORBIDDEN_RUNTIME_COLUMNS
        &
        set(
            dataframe.columns
        )
    )

    if leaked:

        raise ValueError(
            f"Ground truth leaked into {dataset_name}: "
            +
            ", ".join(
                sorted(
                    leaked
                )
            )
        )


# ============================================================
# ============================================================
#
# MANUFACTURING SCENARIOS
#
# ============================================================
# ============================================================


MANUFACTURING_SCENARIOS: tuple[str, ...] = (
    "paint_humidity_spike",
    "machine_temperature_drift",
    "machine_vibration_anomaly",
    "supplier_quality_drop",
    "line_speed_pressure",
    "torque_deviation",
    "maintenance_overdue",
    "maintenance_recovery",
)


# ============================================================
# PUBLIC PRIMARY SIGNAL MAP
#
# Used later by ground_truth.py.
# ============================================================

PRIMARY_SIGNAL: dict[str, str] = {
    "paint_humidity_spike":
        "paint_booth_humidity_pct",

    "machine_temperature_drift":
        "machine_temperature_c",

    "machine_vibration_anomaly":
        "vibration_mm_s",

    "supplier_quality_drop":
        "supplier_lot_quality_score",

    "line_speed_pressure":
        "line_speed_units_per_hour",

    "torque_deviation":
        "torque_deviation_nm",

    "maintenance_overdue":
        "maintenance_overdue_hours",

    "maintenance_recovery":
        "maintenance_overdue_hours",
}


MANUFACTURING_EXPECTED_DIRECTION: dict[str, str] = {
    "paint_humidity_spike":
        "UP",

    "machine_temperature_drift":
        "UP",

    "machine_vibration_anomaly":
        "UP",

    "supplier_quality_drop":
        "DOWN",

    "line_speed_pressure":
        "UP",

    "torque_deviation":
        "DEVIATE",

    "maintenance_overdue":
        "UP",

    "maintenance_recovery":
        "DOWN",
}


MANUFACTURING_SEVERITY: dict[str, str] = {
    "paint_humidity_spike":
        "ANOMALY",

    "machine_temperature_drift":
        "DETERIORATION",

    "machine_vibration_anomaly":
        "ANOMALY",

    "supplier_quality_drop":
        "DETERIORATION",

    "line_speed_pressure":
        "MODERATE",

    "torque_deviation":
        "ANOMALY",

    "maintenance_overdue":
        "DETERIORATION",

    "maintenance_recovery":
        "RECOVERY",
}


MANUFACTURING_DURATION_HOURS: dict[str, int] = {
    "paint_humidity_spike":
        36,

    "machine_temperature_drift":
        48,

    "machine_vibration_anomaly":
        30,

    "supplier_quality_drop":
        72,

    "line_speed_pressure":
        48,

    "torque_deviation":
        36,

    "maintenance_overdue":
        72,

    "maintenance_recovery":
        24,
}


MANUFACTURING_EVENTS_PER_SCENARIO = 3


MANUFACTURING_REQUIRED_COLUMNS: set[str] = {
    "timestamp",

    "plant_id",
    "plant_name",

    "production_line_id",
    "production_line_name",

    "machine_id",
    "machine_name",

    "production_batch_id",

    "supplier_lot_id",
    "supplier_lot_quality_score",

    "ambient_temperature_c",
    "ambient_humidity_pct",

    "machine_load",
    "machine_temperature_c",
    "vibration_mm_s",

    "power_kw",

    "line_speed_units_per_hour",
    "cycle_time_seconds",

    "hours_since_maintenance",
    "maintenance_overdue_hours",

    "torque_deviation_nm",

    "paint_booth_humidity_pct",
    "paint_defect_rate",

    "defect_rate",
    "rework_rate",

    "downtime_minutes",

    "quality_score",
}


# ============================================================
# MANUFACTURING MACHINE TABLE
# ============================================================


def _manufacturing_machine_table(
    manufacturing_timeseries: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build one metadata row per machine.
    """

    columns = [
        "plant_id",
        "plant_name",

        "production_line_id",
        "production_line_name",

        "machine_id",
        "machine_name",
    ]

    return (
        manufacturing_timeseries[
            columns
        ]
        .drop_duplicates(
            subset=[
                "machine_id"
            ]
        )
        .sort_values(
            "machine_id"
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# MANUFACTURING MACHINE ELIGIBILITY
# ============================================================


def _eligible_manufacturing_machines(
    machine_table: pd.DataFrame,
    scenario_name: str,
) -> pd.DataFrame:
    """
    Choose realistic target machines.
    """

    if scenario_name == "paint_humidity_spike":

        paint_mask = (
            machine_table[
                "production_line_name"
            ]
            .astype(str)
            .str.upper()
            .str.contains(
                "PAINT",
                na=False,
            )
            |
            machine_table[
                "machine_name"
            ]
            .astype(str)
            .str.upper()
            .str.contains(
                "PAINT|PRIMER",
                regex=True,
                na=False,
            )
        )

        eligible = (
            machine_table[
                paint_mask
            ]
            .copy()
        )

        if not eligible.empty:

            return eligible

    return machine_table.copy()


# ============================================================
# MANUFACTURING START SELECTION
# ============================================================


def _choose_manufacturing_start(
    manufacturing_timeseries: pd.DataFrame,
    machine_id: str,
    duration_hours: int,
    rng: np.random.Generator,
) -> pd.Timestamp:
    """
    Choose deterministic scenario start with enough baseline
    history on both sides.
    """

    machine_rows = (
        manufacturing_timeseries[
            manufacturing_timeseries[
                "machine_id"
            ].astype(str)
            ==
            str(
                machine_id
            )
        ]
        .sort_values(
            "timestamp"
        )
    )

    timestamps = (
        pd.to_datetime(
            machine_rows[
                "timestamp"
            ]
        )
        .drop_duplicates()
        .sort_values()
        .reset_index(
            drop=True
        )
    )

    cadence = timestamps.diff().dropna().median()
    steps_per_hour = int(round(pd.Timedelta(hours=1) / cadence))
    duration_steps = duration_hours * steps_per_hour
    baseline_steps = 24 * steps_per_hour

    if len(timestamps) < duration_steps + 2 * baseline_steps:

        raise ValueError(
            f"Machine {machine_id} does not have "
            "enough history for scenarios"
        )

    earliest_index = baseline_steps

    latest_index = (
        len(timestamps)
        - duration_steps
        - baseline_steps
    )

    if latest_index <= earliest_index:

        raise ValueError(
            "Manufacturing history is too short "
            "for scenario scheduling"
        )

    start_index = int(
        rng.integers(
            earliest_index,
            latest_index
            +
            1,
        )
    )

    return pd.Timestamp(
        timestamps.iloc[
            start_index
        ]
    )


# ============================================================
# MANUFACTURING SCENARIO SCHEDULE
# ============================================================


def generate_manufacturing_scenario_schedule(
    manufacturing_timeseries: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate hidden manufacturing scenario metadata.
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    _require_columns(
        manufacturing_timeseries,
        MANUFACTURING_REQUIRED_COLUMNS,
        "manufacturing_timeseries",
    )

    if manufacturing_timeseries.empty:

        raise ValueError(
            "manufacturing_timeseries cannot be empty"
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
            "causal.manufacturing.scenarios",
        )
    )

    machine_table = (
        _manufacturing_machine_table(
            manufacturing_timeseries
        )
    )

    rows: list[
        dict[str, Any]
    ] = []

    event_counter = 1

    overdue_events: list[
        dict[str, Any]
    ] = []

    # --------------------------------------------------------
    # All scenarios except recovery.
    # --------------------------------------------------------

    for scenario_name in MANUFACTURING_SCENARIOS:

        if scenario_name == "maintenance_recovery":

            continue

        eligible = (
            _eligible_manufacturing_machines(
                machine_table,
                scenario_name,
            )
        )

        if eligible.empty:

            raise ValueError(
                f"No eligible machines for "
                f"{scenario_name}"
            )

        for _ in range(
            MANUFACTURING_EVENTS_PER_SCENARIO
        ):

            selected_position = int(
                rng.integers(
                    0,
                    len(
                        eligible
                    ),
                )
            )

            machine = (
                eligible.iloc[
                    selected_position
                ]
            )

            machine_id = str(
                machine[
                    "machine_id"
                ]
            )

            duration_hours = (
                MANUFACTURING_DURATION_HOURS[
                    scenario_name
                ]
            )

            start_timestamp = (
                _choose_manufacturing_start(
                    manufacturing_timeseries=
                        manufacturing_timeseries,

                    machine_id=
                        machine_id,

                    duration_hours=
                        duration_hours,

                    rng=
                        rng,
                )
            )

            end_timestamp = (
                start_timestamp
                +
                pd.Timedelta(
                    hours=
                        duration_hours
                )
            )

            scenario_event_id = (
                f"SCENARIO_SYN_{event_counter:06d}"
            )

            target_scope = (
                "SUPPLIER_LOT"
                if scenario_name
                ==
                "supplier_quality_drop"
                else
                "MACHINE"
            )

            row = {
                "scenario_event_id":
                    scenario_event_id,

                "scenario_name":
                    scenario_name,

                "severity":
                    MANUFACTURING_SEVERITY[
                        scenario_name
                    ],

                "target_scope":
                    target_scope,

                "plant_id":
                    str(
                        machine[
                            "plant_id"
                        ]
                    ),

                "plant_name":
                    str(
                        machine[
                            "plant_name"
                        ]
                    ),

                "production_line_id":
                    str(
                        machine[
                            "production_line_id"
                        ]
                    ),

                "production_line_name":
                    str(
                        machine[
                            "production_line_name"
                        ]
                    ),

                "machine_id":
                    machine_id,

                "machine_name":
                    str(
                        machine[
                            "machine_name"
                        ]
                    ),

                "start_timestamp":
                    start_timestamp,

                "end_timestamp":
                    end_timestamp,

                "expected_primary_signal":
                    PRIMARY_SIGNAL[
                        scenario_name
                    ],

                "expected_direction":
                    MANUFACTURING_EXPECTED_DIRECTION[
                        scenario_name
                    ],

                "affected_supplier_lot_ids":
                    None,

                "affected_supplier_lot_count":
                    0,

                "parent_scenario_event_id":
                    None,

                "scenario_version":
                    MANUFACTURING_SCENARIO_VERSION,
            }

            rows.append(
                row
            )

            if (
                scenario_name
                ==
                "maintenance_overdue"
            ):

                overdue_events.append(
                    row
                )

            event_counter += 1

    # --------------------------------------------------------
    # Maintenance recovery follows maintenance overdue.
    # --------------------------------------------------------

    if (
        len(
            overdue_events
        )
        !=
        MANUFACTURING_EVENTS_PER_SCENARIO
    ):

        raise ValueError(
            "Expected exactly three maintenance-overdue "
            "scenario events"
        )

    for overdue_event in overdue_events:

        start_timestamp = pd.Timestamp(
            overdue_event[
                "end_timestamp"
            ]
        )

        duration_hours = (
            MANUFACTURING_DURATION_HOURS[
                "maintenance_recovery"
            ]
        )

        end_timestamp = (
            start_timestamp
            +
            pd.Timedelta(
                hours=
                    duration_hours
            )
        )

        rows.append(
            {
                "scenario_event_id":
                    (
                        "SCENARIO_SYN_"
                        f"{event_counter:06d}"
                    ),

                "scenario_name":
                    "maintenance_recovery",

                "severity":
                    MANUFACTURING_SEVERITY[
                        "maintenance_recovery"
                    ],

                "target_scope":
                    "MACHINE",

                "plant_id":
                    overdue_event[
                        "plant_id"
                    ],

                "plant_name":
                    overdue_event[
                        "plant_name"
                    ],

                "production_line_id":
                    overdue_event[
                        "production_line_id"
                    ],

                "production_line_name":
                    overdue_event[
                        "production_line_name"
                    ],

                "machine_id":
                    overdue_event[
                        "machine_id"
                    ],

                "machine_name":
                    overdue_event[
                        "machine_name"
                    ],

                "start_timestamp":
                    start_timestamp,

                "end_timestamp":
                    end_timestamp,

                "expected_primary_signal":
                    PRIMARY_SIGNAL[
                        "maintenance_recovery"
                    ],

                "expected_direction":
                    MANUFACTURING_EXPECTED_DIRECTION[
                        "maintenance_recovery"
                    ],

                "affected_supplier_lot_ids":
                    None,

                "affected_supplier_lot_count":
                    0,

                "parent_scenario_event_id":
                    overdue_event[
                        "scenario_event_id"
                    ],

                "scenario_version":
                    MANUFACTURING_SCENARIO_VERSION,
            }
        )

        event_counter += 1

    scenario_events = pd.DataFrame(
        rows
    )

    # --------------------------------------------------------
    # Supplier lot scope resolution.
    # --------------------------------------------------------

    supplier_mask = (
        scenario_events[
            "scenario_name"
        ]
        ==
        "supplier_quality_drop"
    )

    manufacturing_timestamps = pd.to_datetime(
        manufacturing_timeseries[
            "timestamp"
        ]
    )

    for index in (
        scenario_events[
            supplier_mask
        ]
        .index
    ):

        event = (
            scenario_events.loc[
                index
            ]
        )

        target_rows = (
            manufacturing_timeseries[
                (
                    manufacturing_timeseries[
                        "machine_id"
                    ].astype(str)
                    ==
                    str(
                        event[
                            "machine_id"
                        ]
                    )
                )
                &
                (
                    manufacturing_timestamps
                    >=
                    pd.Timestamp(
                        event[
                            "start_timestamp"
                        ]
                    )
                )
                &
                (
                    manufacturing_timestamps
                    <
                    pd.Timestamp(
                        event[
                            "end_timestamp"
                        ]
                    )
                )
            ]
        )

        lot_ids = (
            target_rows[
                "supplier_lot_id"
            ]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        lot_ids = sorted(
            lot_ids
        )

        scenario_events.at[
            index,
            "affected_supplier_lot_ids",
        ] = json.dumps(
            lot_ids
        )

        scenario_events.at[
            index,
            "affected_supplier_lot_count",
        ] = len(
            lot_ids
        )

    expected_event_count = (
        len(
            MANUFACTURING_SCENARIOS
        )
        *
        MANUFACTURING_EVENTS_PER_SCENARIO
    )

    if (
        len(
            scenario_events
        )
        !=
        expected_event_count
    ):

        raise ValueError(
            "Manufacturing scenario event count mismatch. "
            f"Expected {expected_event_count}, "
            f"found {len(scenario_events)}"
        )

    return (
        scenario_events
        .sort_values(
            [
                "start_timestamp",
                "scenario_event_id",
            ]
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# MANUFACTURING EVENT MASK
# ============================================================


def _manufacturing_machine_mask(
    dataframe: pd.DataFrame,
    event: Mapping[str, Any],
    lag_hours: int = 0,
) -> pd.Series:
    """
    Machine-specific scenario mask.
    """

    start = (
        pd.Timestamp(
            event[
                "start_timestamp"
            ]
        )
        +
        pd.Timedelta(
            hours=
                lag_hours
        )
    )

    end = (
        pd.Timestamp(
            event[
                "end_timestamp"
            ]
        )
        +
        pd.Timedelta(
            hours=
                lag_hours
        )
    )

    timestamps = pd.to_datetime(
        dataframe[
            "timestamp"
        ]
    )

    return (
        (
            dataframe[
                "machine_id"
            ].astype(str)
            ==
            str(
                event[
                    "machine_id"
                ]
            )
        )
        &
        (
            timestamps
            >=
            start
        )
        &
        (
            timestamps
            <
            end
        )
    )


# ============================================================
# APPLY ONE MANUFACTURING EVENT
# ============================================================


def _apply_manufacturing_event(
    adjusted: pd.DataFrame,
    event: Mapping[str, Any],
) -> None:
    """
    Apply one controlled manufacturing scenario.
    """

    scenario_name = str(
        event[
            "scenario_name"
        ]
    )

    primary_mask = (
        _manufacturing_machine_mask(
            adjusted,
            event,
        )
    )

    primary_indices = (
        adjusted.index[
            primary_mask
        ]
    )

    if len(
        primary_indices
    ) == 0:

        raise ValueError(
            f"{event['scenario_event_id']} has no "
            "manufacturing observations"
        )

    curve = _scenario_curve(
        len(
            primary_indices
        )
    )

    # ========================================================
    # PAINT HUMIDITY SPIKE
    # ========================================================

    if scenario_name == "paint_humidity_spike":

        adjusted.loc[
            primary_indices,
            "paint_booth_humidity_pct",
        ] = np.clip(
            _numeric(
                adjusted.loc[
                    primary_indices
                ],
                "paint_booth_humidity_pct",
            ).to_numpy()
            +
            14.0
            *
            curve,
            0.0,
            100.0,
        )

        lag1_mask = (
            _manufacturing_machine_mask(
                adjusted,
                event,
                lag_hours=1,
            )
        )

        lag1_indices = (
            adjusted.index[
                lag1_mask
            ]
        )

        if len(
            lag1_indices
        ):

            lag_curve = _scenario_curve(
                len(
                    lag1_indices
                )
            )

            adjusted.loc[
                lag1_indices,
                "paint_defect_rate",
            ] = np.clip(
                _numeric(
                    adjusted.loc[
                        lag1_indices
                    ],
                    "paint_defect_rate",
                ).to_numpy()
                +
                0.012
                *
                lag_curve,
                0.0,
                1.0,
            )

        lag2_mask = (
            _manufacturing_machine_mask(
                adjusted,
                event,
                lag_hours=2,
            )
        )

        lag2_indices = (
            adjusted.index[
                lag2_mask
            ]
        )

        if len(
            lag2_indices
        ):

            lag_curve = _scenario_curve(
                len(
                    lag2_indices
                )
            )

            adjusted.loc[
                lag2_indices,
                "rework_rate",
            ] = np.clip(
                _numeric(
                    adjusted.loc[
                        lag2_indices
                    ],
                    "rework_rate",
                ).to_numpy()
                +
                0.008
                *
                lag_curve,
                0.0,
                1.0,
            )

            adjusted.loc[
                lag2_indices,
                "quality_score",
            ] = np.clip(
                _numeric(
                    adjusted.loc[
                        lag2_indices
                    ],
                    "quality_score",
                ).to_numpy()
                -
                0.018
                *
                lag_curve,
                0.0,
                1.0,
            )

        return

    # ========================================================
    # MACHINE TEMPERATURE DRIFT
    # ========================================================

    if scenario_name == "machine_temperature_drift":

        adjusted.loc[
            primary_indices,
            "machine_temperature_c",
        ] = (
            _numeric(
                adjusted.loc[
                    primary_indices
                ],
                "machine_temperature_c",
            ).to_numpy()
            +
            5.4
            *
            curve
        )

        lag1_mask = (
            _manufacturing_machine_mask(
                adjusted,
                event,
                lag_hours=1,
            )
        )

        lag1_indices = (
            adjusted.index[
                lag1_mask
            ]
        )

        if len(
            lag1_indices
        ):

            lag_curve = _scenario_curve(
                len(
                    lag1_indices
                )
            )

            adjusted.loc[
                lag1_indices,
                "vibration_mm_s",
            ] = np.maximum(
                _numeric(
                    adjusted.loc[
                        lag1_indices
                    ],
                    "vibration_mm_s",
                ).to_numpy()
                +
                0.55
                *
                lag_curve,
                0.0,
            )

        lag2_mask = (
            _manufacturing_machine_mask(
                adjusted,
                event,
                lag_hours=2,
            )
        )

        lag2_indices = (
            adjusted.index[
                lag2_mask
            ]
        )

        if len(
            lag2_indices
        ):

            lag_curve = _scenario_curve(
                len(
                    lag2_indices
                )
            )

            downtime_increment = np.where(
                lag_curve
                >
                0.80,
                4.0
                *
                lag_curve,
                0.0,
            )

            adjusted.loc[
                lag2_indices,
                "downtime_minutes",
            ] = np.maximum(
                _numeric(
                    adjusted.loc[
                        lag2_indices
                    ],
                    "downtime_minutes",
                ).to_numpy()
                +
                downtime_increment,
                0.0,
            )

        return

    # ========================================================
    # MACHINE VIBRATION ANOMALY
    # ========================================================

    if scenario_name == "machine_vibration_anomaly":

        adjusted.loc[
            primary_indices,
            "vibration_mm_s",
        ] = np.maximum(
            _numeric(
                adjusted.loc[
                    primary_indices
                ],
                "vibration_mm_s",
            ).to_numpy()
            +
            1.6
            *
            curve,
            0.0,
        )

        lag1_mask = (
            _manufacturing_machine_mask(
                adjusted,
                event,
                lag_hours=1,
            )
        )

        lag1_indices = (
            adjusted.index[
                lag1_mask
            ]
        )

        if len(
            lag1_indices
        ):

            lag_curve = _scenario_curve(
                len(
                    lag1_indices
                )
            )

            downtime_increment = np.where(
                lag_curve
                >
                0.82,
                5.0
                *
                lag_curve,
                0.0,
            )

            adjusted.loc[
                lag1_indices,
                "downtime_minutes",
            ] = np.maximum(
                _numeric(
                    adjusted.loc[
                        lag1_indices
                    ],
                    "downtime_minutes",
                ).to_numpy()
                +
                downtime_increment,
                0.0,
            )

        return

    # ========================================================
    # SUPPLIER QUALITY DROP
    # ========================================================

    if scenario_name == "supplier_quality_drop":

        lot_ids = json.loads(
            str(
                event[
                    "affected_supplier_lot_ids"
                ]
            )
        )

        if not lot_ids:

            raise ValueError(
                f"{event['scenario_event_id']} has no "
                "affected supplier lots"
            )

        timestamps = pd.to_datetime(
            adjusted[
                "timestamp"
            ]
        )

        supplier_mask = (
            (
                timestamps
                >=
                pd.Timestamp(
                    event[
                        "start_timestamp"
                    ]
                )
            )
            &
            (
                timestamps
                <
                pd.Timestamp(
                    event[
                        "end_timestamp"
                    ]
                )
            )
            &
            (
                adjusted[
                    "supplier_lot_id"
                ]
                .astype(str)
                .isin(
                    lot_ids
                )
            )
        )

        supplier_indices = (
            adjusted.index[
                supplier_mask
            ]
        )

        if len(
            supplier_indices
        ) == 0:

            raise ValueError(
                "Supplier quality scenario has no "
                "affected runtime observations"
            )

        affected = (
            adjusted.loc[
                supplier_indices,
                [
                    "timestamp",
                    "supplier_lot_id",
                    "supplier_lot_quality_score",
                ],
            ]
            .copy()
        )

        grouped = (
            affected
            .groupby(
                [
                    "timestamp",
                    "supplier_lot_id",
                ],
                as_index=False,
            )[
                "supplier_lot_quality_score"
            ]
            .mean()
        )

        group_curve = (
            _scenario_curve(
                len(
                    grouped
                )
            )
        )

        grouped[
            "supplier_lot_quality_score"
        ] = np.clip(
            pd.to_numeric(
                grouped[
                    "supplier_lot_quality_score"
                ],
                errors="raise",
            ).to_numpy()
            -
            0.12
            *
            group_curve,
            0.0,
            1.0,
        )

        quality_lookup = {
            (
                pd.Timestamp(
                    row.timestamp
                ),
                str(
                    row.supplier_lot_id
                ),
            ):
                float(
                    row.supplier_lot_quality_score
                )

            for row in grouped.itertuples(
                index=False
            )
        }

        for index in supplier_indices:

            key = (
                pd.Timestamp(
                    adjusted.at[
                        index,
                        "timestamp",
                    ]
                ),
                str(
                    adjusted.at[
                        index,
                        "supplier_lot_id",
                    ]
                ),
            )

            adjusted.at[
                index,
                "supplier_lot_quality_score",
            ] = quality_lookup[
                key
            ]

        downstream_curve = (
            _scenario_curve(
                len(
                    supplier_indices
                )
            )
        )

        adjusted.loc[
            supplier_indices,
            "defect_rate",
        ] = np.clip(
            _numeric(
                adjusted.loc[
                    supplier_indices
                ],
                "defect_rate",
            ).to_numpy()
            +
            0.010
            *
            downstream_curve,
            0.0,
            1.0,
        )

        adjusted.loc[
            supplier_indices,
            "rework_rate",
        ] = np.clip(
            _numeric(
                adjusted.loc[
                    supplier_indices
                ],
                "rework_rate",
            ).to_numpy()
            +
            0.006
            *
            downstream_curve,
            0.0,
            1.0,
        )

        adjusted.loc[
            supplier_indices,
            "quality_score",
        ] = np.clip(
            _numeric(
                adjusted.loc[
                    supplier_indices
                ],
                "quality_score",
            ).to_numpy()
            -
            0.020
            *
            downstream_curve,
            0.0,
            1.0,
        )

        return

    # ========================================================
    # LINE SPEED PRESSURE
    # ========================================================

    if scenario_name == "line_speed_pressure":

        adjusted.loc[
            primary_indices,
            "line_speed_units_per_hour",
        ] = np.maximum(
            _numeric(
                adjusted.loc[
                    primary_indices
                ],
                "line_speed_units_per_hour",
            ).to_numpy()
            +
            7.5
            *
            curve,
            1.0,
        )

        adjusted.loc[
            primary_indices,
            "cycle_time_seconds",
        ] = np.maximum(
            _numeric(
                adjusted.loc[
                    primary_indices
                ],
                "cycle_time_seconds",
            ).to_numpy()
            -
            4.0
            *
            curve,
            1.0,
        )

        adjusted.loc[
            primary_indices,
            "power_kw",
        ] = np.maximum(
            _numeric(
                adjusted.loc[
                    primary_indices
                ],
                "power_kw",
            ).to_numpy()
            +
            6.0
            *
            curve,
            0.0,
        )

        lag1_mask = (
            _manufacturing_machine_mask(
                adjusted,
                event,
                lag_hours=1,
            )
        )

        lag1_indices = (
            adjusted.index[
                lag1_mask
            ]
        )

        if len(
            lag1_indices
        ):

            lag_curve = _scenario_curve(
                len(
                    lag1_indices
                )
            )

            adjusted.loc[
                lag1_indices,
                "defect_rate",
            ] = np.clip(
                _numeric(
                    adjusted.loc[
                        lag1_indices
                    ],
                    "defect_rate",
                ).to_numpy()
                +
                0.008
                *
                lag_curve,
                0.0,
                1.0,
            )

        lag2_mask = (
            _manufacturing_machine_mask(
                adjusted,
                event,
                lag_hours=2,
            )
        )

        lag2_indices = (
            adjusted.index[
                lag2_mask
            ]
        )

        if len(
            lag2_indices
        ):

            lag_curve = _scenario_curve(
                len(
                    lag2_indices
                )
            )

            adjusted.loc[
                lag2_indices,
                "rework_rate",
            ] = np.clip(
                _numeric(
                    adjusted.loc[
                        lag2_indices
                    ],
                    "rework_rate",
                ).to_numpy()
                +
                0.005
                *
                lag_curve,
                0.0,
                1.0,
            )

        return

    # ========================================================
    # TORQUE DEVIATION
    # ========================================================

    if scenario_name == "torque_deviation":

        baseline = (
            _numeric(
                adjusted.loc[
                    primary_indices
                ],
                "torque_deviation_nm",
            )
            .to_numpy()
        )

        direction = np.where(
            baseline
            >=
            0,
            1.0,
            -1.0,
        )

        adjusted.loc[
            primary_indices,
            "torque_deviation_nm",
        ] = (
            baseline
            +
            direction
            *
            2.3
            *
            curve
        )

        lag1_mask = (
            _manufacturing_machine_mask(
                adjusted,
                event,
                lag_hours=1,
            )
        )

        lag1_indices = (
            adjusted.index[
                lag1_mask
            ]
        )

        if len(
            lag1_indices
        ):

            lag_curve = _scenario_curve(
                len(
                    lag1_indices
                )
            )

            adjusted.loc[
                lag1_indices,
                "defect_rate",
            ] = np.clip(
                _numeric(
                    adjusted.loc[
                        lag1_indices
                    ],
                    "defect_rate",
                ).to_numpy()
                +
                0.010
                *
                lag_curve,
                0.0,
                1.0,
            )

            adjusted.loc[
                lag1_indices,
                "quality_score",
            ] = np.clip(
                _numeric(
                    adjusted.loc[
                        lag1_indices
                    ],
                    "quality_score",
                ).to_numpy()
                -
                0.015
                *
                lag_curve,
                0.0,
                1.0,
            )

        lag2_mask = (
            _manufacturing_machine_mask(
                adjusted,
                event,
                lag_hours=2,
            )
        )

        lag2_indices = (
            adjusted.index[
                lag2_mask
            ]
        )

        if len(
            lag2_indices
        ):

            lag_curve = _scenario_curve(
                len(
                    lag2_indices
                )
            )

            adjusted.loc[
                lag2_indices,
                "rework_rate",
            ] = np.clip(
                _numeric(
                    adjusted.loc[
                        lag2_indices
                    ],
                    "rework_rate",
                ).to_numpy()
                +
                0.006
                *
                lag_curve,
                0.0,
                1.0,
            )

        return

    # ========================================================
    # MAINTENANCE OVERDUE
    # ========================================================

    if scenario_name == "maintenance_overdue":

        trajectory = np.linspace(
            12.0,
            72.0,
            len(
                primary_indices
            ),
        )

        adjusted.loc[
            primary_indices,
            "maintenance_overdue_hours",
        ] = np.maximum(
            _numeric(
                adjusted.loc[
                    primary_indices
                ],
                "maintenance_overdue_hours",
            ).to_numpy(),
            trajectory,
        )

        adjusted.loc[
            primary_indices,
            "machine_temperature_c",
        ] = (
            _numeric(
                adjusted.loc[
                    primary_indices
                ],
                "machine_temperature_c",
            ).to_numpy()
            +
            2.0
            *
            curve
        )

        lag1_mask = (
            _manufacturing_machine_mask(
                adjusted,
                event,
                lag_hours=1,
            )
        )

        lag1_indices = (
            adjusted.index[
                lag1_mask
            ]
        )

        if len(
            lag1_indices
        ):

            lag_curve = _scenario_curve(
                len(
                    lag1_indices
                )
            )

            adjusted.loc[
                lag1_indices,
                "vibration_mm_s",
            ] = np.maximum(
                _numeric(
                    adjusted.loc[
                        lag1_indices
                    ],
                    "vibration_mm_s",
                ).to_numpy()
                +
                0.65
                *
                lag_curve,
                0.0,
            )

        lag2_mask = (
            _manufacturing_machine_mask(
                adjusted,
                event,
                lag_hours=2,
            )
        )

        lag2_indices = (
            adjusted.index[
                lag2_mask
            ]
        )

        if len(
            lag2_indices
        ):

            lag_curve = _scenario_curve(
                len(
                    lag2_indices
                )
            )

            adjusted.loc[
                lag2_indices,
                "downtime_minutes",
            ] = np.maximum(
                _numeric(
                    adjusted.loc[
                        lag2_indices
                    ],
                    "downtime_minutes",
                ).to_numpy()
                +
                4.0
                *
                lag_curve,
                0.0,
            )

        return

    # ========================================================
    # MAINTENANCE RECOVERY
    # ========================================================

    if scenario_name == "maintenance_recovery":

        overdue_trajectory = np.linspace(
            72.0,
            0.0,
            len(
                primary_indices
            ),
        )

        adjusted.loc[
            primary_indices,
            "maintenance_overdue_hours",
        ] = overdue_trajectory

        adjusted.loc[
            primary_indices,
            "hours_since_maintenance",
        ] = np.linspace(
            8.0,
            1.0,
            len(
                primary_indices
            ),
        )

        recovery_curve = np.linspace(
            1.0,
            0.25,
            len(
                primary_indices
            ),
        )

        adjusted.loc[
            primary_indices,
            "machine_temperature_c",
        ] = np.maximum(
            _numeric(
                adjusted.loc[
                    primary_indices
                ],
                "machine_temperature_c",
            ).to_numpy()
            -
            2.2
            *
            recovery_curve,
            0.0,
        )

        adjusted.loc[
            primary_indices,
            "vibration_mm_s",
        ] = np.maximum(
            _numeric(
                adjusted.loc[
                    primary_indices
                ],
                "vibration_mm_s",
            ).to_numpy()
            -
            0.6
            *
            recovery_curve,
            0.0,
        )

        adjusted.loc[
            primary_indices,
            "downtime_minutes",
        ] = np.maximum(
            _numeric(
                adjusted.loc[
                    primary_indices
                ],
                "downtime_minutes",
            ).to_numpy()
            -
            3.0
            *
            recovery_curve,
            0.0,
        )

        return

    raise ValueError(
        f"Unknown manufacturing scenario: "
        f"{scenario_name}"
    )


# ============================================================
# APPLY ALL MANUFACTURING SCENARIOS
# ============================================================


def apply_manufacturing_scenarios(
    manufacturing_timeseries: pd.DataFrame,
    scenario_events: pd.DataFrame,
) -> pd.DataFrame:
    """
    Apply manufacturing scenarios without modifying runtime
    schema.
    """

    adjusted = (
        manufacturing_timeseries
        .copy(
            deep=True
        )
    )

    original_columns = list(
        adjusted.columns
    )

    original_row_count = len(
        adjusted
    )

    for event in scenario_events.to_dict(
        orient="records"
    ):

        _apply_manufacturing_event(
            adjusted=
                adjusted,

            event=
                event,
        )

    if (
        len(
            adjusted
        )
        !=
        original_row_count
    ):

        raise ValueError(
            "Manufacturing scenarios changed row count"
        )

    if (
        list(
            adjusted.columns
        )
        !=
        original_columns
    ):

        raise ValueError(
            "Manufacturing scenarios changed runtime schema"
        )

    _validate_runtime_leakage(
        adjusted,
        "manufacturing runtime observations",
    )

    return adjusted


# ============================================================
# MANUFACTURING EFFECT VALIDATION
# ============================================================


def validate_manufacturing_scenario_effects(
    baseline: pd.DataFrame,
    adjusted: pd.DataFrame,
    scenario_events: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate each controlled manufacturing event.
    """

    rows: list[
        dict[str, Any]
    ] = []

    for event in scenario_events.to_dict(
        orient="records"
    ):

        scenario_name = str(
            event[
                "scenario_name"
            ]
        )

        signal = str(
            event[
                "expected_primary_signal"
            ]
        )

        direction = str(
            event[
                "expected_direction"
            ]
        )

        if scenario_name == "supplier_quality_drop":

            lot_ids = json.loads(
                str(
                    event[
                        "affected_supplier_lot_ids"
                    ]
                )
            )

            timestamps = pd.to_datetime(
                baseline[
                    "timestamp"
                ]
            )

            mask = (
                (
                    timestamps
                    >=
                    pd.Timestamp(
                        event[
                            "start_timestamp"
                        ]
                    )
                )
                &
                (
                    timestamps
                    <
                    pd.Timestamp(
                        event[
                            "end_timestamp"
                        ]
                    )
                )
                &
                (
                    baseline[
                        "supplier_lot_id"
                    ]
                    .astype(str)
                    .isin(
                        lot_ids
                    )
                )
            )

        else:

            mask = (
                _manufacturing_machine_mask(
                    baseline,
                    event,
                )
            )

        baseline_values = pd.to_numeric(
            baseline.loc[
                mask,
                signal,
            ],
            errors="raise",
        )

        adjusted_values = pd.to_numeric(
            adjusted.loc[
                mask,
                signal,
            ],
            errors="raise",
        )

        if baseline_values.empty:

            raise ValueError(
                f"No validation observations for "
                f"{event['scenario_event_id']}"
            )

        baseline_mean = float(
            baseline_values.mean()
        )

        adjusted_mean = float(
            adjusted_values.mean()
        )

        if direction == "UP":

            metric = (
                adjusted_mean
                -
                baseline_mean
            )

            passed = (
                metric
                >
                1e-8
            )

        elif direction == "DOWN":

            if scenario_name == "maintenance_recovery":

                event_values = (
                    adjusted.loc[
                        mask,
                        signal,
                    ]
                    .astype(float)
                    .to_numpy()
                )

                quarter = max(
                    1,
                    len(
                        event_values
                    )
                    //
                    4,
                )

                first_mean = float(
                    np.mean(
                        event_values[
                            :quarter
                        ]
                    )
                )

                last_mean = float(
                    np.mean(
                        event_values[
                            -quarter:
                        ]
                    )
                )

                metric = (
                    first_mean
                    -
                    last_mean
                )

                passed = (
                    metric
                    >
                    1.0
                )

            else:

                metric = (
                    baseline_mean
                    -
                    adjusted_mean
                )

                passed = (
                    metric
                    >
                    1e-8
                )

        elif direction == "DEVIATE":

            baseline_abs = float(
                np.mean(
                    np.abs(
                        baseline_values.to_numpy()
                    )
                )
            )

            adjusted_abs = float(
                np.mean(
                    np.abs(
                        adjusted_values.to_numpy()
                    )
                )
            )

            metric = (
                adjusted_abs
                -
                baseline_abs
            )

            passed = (
                metric
                >
                1e-8
            )

        else:

            raise ValueError(
                f"Unsupported expected direction: "
                f"{direction}"
            )

        rows.append(
            {
                "scenario_event_id":
                    event[
                        "scenario_event_id"
                    ],

                "scenario_name":
                    scenario_name,

                "machine_id":
                    event[
                        "machine_id"
                    ],

                "primary_signal":
                    signal,

                "expected_direction":
                    direction,

                "baseline_mean":
                    baseline_mean,

                "adjusted_mean":
                    adjusted_mean,

                "validation_metric":
                    float(
                        metric
                    ),

                "passed":
                    bool(
                        passed
                    ),
            }
        )

    validation = pd.DataFrame(
        rows
    )

    failed = (
        validation[
            ~validation[
                "passed"
            ]
        ]
    )

    if not failed.empty:

        raise ValueError(
            "Manufacturing scenario validation failed:\n"
            +
            failed.to_string(
                index=False
            )
        )

    return validation


# ============================================================
# SUPPLIER LOT CONSISTENCY
# ============================================================


def count_inconsistent_supplier_lot_timestamp_pairs(
    manufacturing_timeseries: pd.DataFrame,
) -> int:
    """
    Same supplier lot at same timestamp must expose exactly
    one supplier-lot quality score.
    """

    consistency = (
        manufacturing_timeseries
        .groupby(
            [
                "timestamp",
                "supplier_lot_id",
            ]
        )[
            "supplier_lot_quality_score"
        ]
        .nunique(
            dropna=False
        )
    )

    return int(
        (
            consistency
            >
            1
        )
        .sum()
    )


# ============================================================
# PUBLIC MANUFACTURING API
# ============================================================


def generate_and_apply_manufacturing_scenarios(
    manufacturing_timeseries: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Generate and apply controlled manufacturing scenarios.

    Returns:
        adjusted runtime observations
        hidden scenario-event truth
    """

    _validate_runtime_leakage(
        manufacturing_timeseries,
        "baseline manufacturing observations",
    )

    scenario_events = (
        generate_manufacturing_scenario_schedule(
            manufacturing_timeseries=
                manufacturing_timeseries,

            generation=
                generation,
        )
    )

    adjusted = (
        apply_manufacturing_scenarios(
            manufacturing_timeseries=
                manufacturing_timeseries,

            scenario_events=
                scenario_events,
        )
    )

    validate_manufacturing_scenario_effects(
        baseline=
            manufacturing_timeseries,

        adjusted=
            adjusted,

        scenario_events=
            scenario_events,
    )

    inconsistent_pairs = (
        count_inconsistent_supplier_lot_timestamp_pairs(
            adjusted
        )
    )

    if inconsistent_pairs != 0:

        raise ValueError(
            "Supplier-lot quality consistency failed. "
            f"Inconsistent timestamp/lot pairs: "
            f"{inconsistent_pairs}"
        )

    return (
        adjusted,
        scenario_events,
    )


# ============================================================
# ============================================================
#
# MOBILITY SCENARIOS
#
# ============================================================
# ============================================================


MOBILITY_SCENARIOS: tuple[str, ...] = (
    "dealer_followup_deterioration",
    "finance_approval_slowdown",
    "allocation_constraint",
    "delivery_delay_spike",
)


MOBILITY_PRIMARY_SIGNAL: dict[str, str] = {
    "dealer_followup_deterioration":
        "followup_completed_count",

    "finance_approval_slowdown":
        "avg_finance_approval_tat_hours",

    "allocation_constraint":
        "allocated_vehicle_count",

    "delivery_delay_spike":
        "delayed_delivery_count",
}


MOBILITY_EXPECTED_DIRECTION: dict[str, str] = {
    "dealer_followup_deterioration":
        "DOWN",

    "finance_approval_slowdown":
        "UP",

    "allocation_constraint":
        "DOWN",

    "delivery_delay_spike":
        "UP",
}


MOBILITY_SEVERITY: dict[str, str] = {
    "dealer_followup_deterioration":
        "DETERIORATION",

    "finance_approval_slowdown":
        "DETERIORATION",

    "allocation_constraint":
        "DETERIORATION",

    "delivery_delay_spike":
        "ANOMALY",
}


# ============================================================
# MOBILITY DURATION
#
# 1 window = 12 hours.
# ============================================================

MOBILITY_DURATION_WINDOWS: dict[str, int] = {
    "dealer_followup_deterioration":
        8,

    "finance_approval_slowdown":
        10,

    "allocation_constraint":
        12,

    "delivery_delay_spike":
        8,
}


# ============================================================
# MAXIMUM DOWNSTREAM EFFECT LAG
#
# 1 lag = 12 hours.
# ============================================================

MOBILITY_MAX_EFFECT_LAG_WINDOWS: dict[str, int] = {
    "dealer_followup_deterioration":
        3,

    "finance_approval_slowdown":
        2,

    "allocation_constraint":
        2,

    "delivery_delay_spike":
        0,
}


MOBILITY_EVENTS_PER_SCENARIO = 3


MOBILITY_REQUIRED_COLUMNS: set[str] = {
    "region_id",
    "region_name",

    "window_start",
    "window_end",

    "lead_count",

    "followup_count",
    "followup_completed_count",
    "customer_response_count",
    "avg_followup_response_minutes",

    "test_drive_requested_count",
    "test_drive_completed_count",
    "test_drive_no_show_count",

    "booking_count",

    "finance_application_count",
    "finance_approved_count",
    "finance_rejected_count",
    "finance_manual_review_count",
    "avg_finance_approval_tat_hours",

    "cancellation_count",

    "allocated_vehicle_count",
    "waitlisted_booking_count",
    "avg_allocation_wait_hours",

    "delivered_vehicle_count",
    "delayed_delivery_count",
    "avg_delivery_delay_days",

    "service_event_count",
    "unscheduled_repair_count",

    "warranty_claim_count",
    "warranty_approved_count",
}


# ============================================================
# MOBILITY REGION HISTORY
# ============================================================


def _mobility_region_rows(
    mobility_timeseries: pd.DataFrame,
    region_id: str,
) -> pd.DataFrame:
    """
    Ordered observations for one region.
    """

    return (
        mobility_timeseries[
            mobility_timeseries[
                "region_id"
            ].astype(str)
            ==
            str(
                region_id
            )
        ]
        .sort_values(
            "window_start"
        )
        .copy()
    )


# ============================================================
# MOBILITY ACTIVITY SCORE
# ============================================================


def _mobility_activity_score(
    rows: pd.DataFrame,
    scenario_name: str,
) -> float:
    """
    Determine whether a proposed scenario window contains
    enough real observable activity to perturb.
    """

    if scenario_name == "dealer_followup_deterioration":

        return float(
            rows[
                "followup_completed_count"
            ].sum()
        )

    if scenario_name == "finance_approval_slowdown":

        decisions = (
            rows[
                "finance_approved_count"
            ]
            +
            rows[
                "finance_rejected_count"
            ]
            +
            rows[
                "finance_manual_review_count"
            ]
        )

        return float(
            decisions.sum()
        )

    if scenario_name == "allocation_constraint":

        return float(
            rows[
                "allocated_vehicle_count"
            ].sum()
        )

    if scenario_name == "delivery_delay_spike":

        headroom = (
            rows[
                "delivered_vehicle_count"
            ]
            -
            rows[
                "delayed_delivery_count"
            ]
        )

        return float(
            np.maximum(
                headroom,
                0,
            ).sum()
        )

    raise ValueError(
        f"Unknown Mobility scenario: "
        f"{scenario_name}"
    )


MOBILITY_MIN_ACTIVITY: dict[str, float] = {
    "dealer_followup_deterioration":
        20.0,

    "finance_approval_slowdown":
        5.0,

    "allocation_constraint":
        5.0,

    "delivery_delay_spike":
        3.0,
}


# ============================================================
# MOBILITY CANDIDATE SUPPORT VALIDATION
# ============================================================


def _mobility_candidate_supports_scenario(
    region_rows: pd.DataFrame,
    start_position: int,
    duration_windows: int,
    scenario_name: str,
    lag_step_count: int,
) -> bool:
    """
    Verify that a candidate scenario window contains enough
    activity for both the primary scenario and its intended
    downstream lagged effects.
    """

    def window(
        lag_windows: int,
    ) -> pd.DataFrame:

        start = (
            start_position
            +
            lag_windows * lag_step_count
        )

        end = (
            start
            +
            duration_windows
        )

        return (
            region_rows.iloc[
                start:end
            ]
        )

    primary = window(
        0
    )

    if (
        len(
            primary
        )
        !=
        duration_windows
    ):

        return False

    primary_activity = (
        _mobility_activity_score(
            primary,
            scenario_name,
        )
    )

    if (
        primary_activity
        <
        MOBILITY_MIN_ACTIVITY[
            scenario_name
        ]
    ):

        return False

    # ========================================================
    # DEALER FOLLOW-UP DETERIORATION
    # ========================================================

    if (
        scenario_name
        ==
        "dealer_followup_deterioration"
    ):

        response_window = window(
            1
        )

        test_drive_window = window(
            2
        )

        booking_window = window(
            3
        )

        if (
            len(
                response_window
            )
            !=
            duration_windows
        ):

            return False

        if (
            len(
                test_drive_window
            )
            !=
            duration_windows
        ):

            return False

        if (
            len(
                booking_window
            )
            !=
            duration_windows
        ):

            return False

        if (
            response_window[
                "customer_response_count"
            ].sum()
            <=
            0
        ):

            return False

        if (
            test_drive_window[
                "test_drive_completed_count"
            ].sum()
            <=
            0
        ):

            return False

        if (
            booking_window[
                "booking_count"
            ].sum()
            <=
            0
        ):

            return False

        return True

    # ========================================================
    # FINANCE APPROVAL SLOWDOWN
    # ========================================================

    if (
        scenario_name
        ==
        "finance_approval_slowdown"
    ):

        if (
            primary[
                "finance_approved_count"
            ].sum()
            <=
            0
        ):

            return False

        cancellation_window = window(
            2
        )

        if (
            len(
                cancellation_window
            )
            !=
            duration_windows
        ):

            return False

        return True

    # ========================================================
    # ALLOCATION CONSTRAINT
    # ========================================================

    if (
        scenario_name
        ==
        "allocation_constraint"
    ):

        delivery_window = window(
            2
        )

        if (
            len(
                delivery_window
            )
            !=
            duration_windows
        ):

            return False

        if (
            delivery_window[
                "delivered_vehicle_count"
            ].sum()
            <=
            0
        ):

            return False

        return True

    # ========================================================
    # DELIVERY DELAY SPIKE
    # ========================================================

    if (
        scenario_name
        ==
        "delivery_delay_spike"
    ):

        return True

    raise ValueError(
        f"Unknown Mobility scenario: "
        f"{scenario_name}"
    )


# ============================================================
# MOBILITY INTERVAL OVERLAP
# ============================================================


def _mobility_intervals_overlap(
    start_a: pd.Timestamp,
    end_a: pd.Timestamp,
    start_b: pd.Timestamp,
    end_b: pd.Timestamp,
) -> bool:
    """
    Half-open interval overlap check.
    """

    return (
        start_a
        <
        end_b
        and
        start_b
        <
        end_a
    )


# ============================================================
# MOBILITY SCENARIO SCHEDULE
# ============================================================


def generate_mobility_scenario_schedule(
    mobility_timeseries: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate:

        4 Mobility scenario types
        ×
        3 events
        =
        12 controlled scenario events.

    Candidate windows are validated against both primary and
    downstream activity.

    Complete causal-effect horizons cannot overlap within the
    same region.
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    _require_columns(
        mobility_timeseries,
        MOBILITY_REQUIRED_COLUMNS,
        "mobility_timeseries",
    )

    if mobility_timeseries.empty:

        raise ValueError(
            "mobility_timeseries cannot be empty"
        )

    _validate_runtime_leakage(
        mobility_timeseries,
        "baseline Mobility observations",
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
            "causal.mobility.scenarios",
        )
    )

    region_table = (
        mobility_timeseries[
            [
                "region_id",
                "region_name",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            "region_id"
        )
        .reset_index(
            drop=True
        )
    )

    if region_table.empty:

        raise ValueError(
            "Mobility time series contains no regions"
        )

    # Complete scenario-effect horizons already occupied
    # within each region.

    occupied: dict[
        str,
        list[
            tuple[
                pd.Timestamp,
                pd.Timestamp,
            ]
        ],
    ] = {
        str(
            region_id
        ):
            []

        for region_id in region_table[
            "region_id"
        ]
    }

    scenario_rows: list[
        dict[str, Any]
    ] = []

    event_counter = 1

    sample_region = _mobility_region_rows(
        mobility_timeseries,
        str(region_table.iloc[0]["region_id"]),
    )
    cadence = (
        pd.to_datetime(sample_region["window_start"])
        .diff()
        .dropna()
        .median()
    )
    steps_per_12_hours = int(
        round(pd.Timedelta(hours=12) / cadence)
    )
    baseline_context_steps = 6 * steps_per_12_hours

    for scenario_name in MOBILITY_SCENARIOS:

        duration_windows = (
            MOBILITY_DURATION_WINDOWS[
                scenario_name
            ]
        )
        duration_steps = duration_windows * steps_per_12_hours

        max_lag_windows = (
            MOBILITY_MAX_EFFECT_LAG_WINDOWS[
                scenario_name
            ]
        )

        generated_for_scenario = 0

        attempts = 0

        while (
            generated_for_scenario
            <
            MOBILITY_EVENTS_PER_SCENARIO
        ):

            attempts += 1

            if attempts > 10000:

                raise RuntimeError(
                    "Could not find enough valid "
                    "non-overlapping Mobility windows for "
                    f"{scenario_name}. "
                    "Underlying business history may be "
                    "too sparse."
                )

            # ------------------------------------------------
            # REGION
            # ------------------------------------------------

            region_position = int(
                rng.integers(
                    0,
                    len(
                        region_table
                    ),
                )
            )

            region = (
                region_table.iloc[
                    region_position
                ]
            )

            region_id = str(
                region[
                    "region_id"
                ]
            )

            region_name = str(
                region[
                    "region_name"
                ]
            )

            region_rows = (
                _mobility_region_rows(
                    mobility_timeseries,
                    region_id,
                )
            )

            # Three days of baseline context on each side.

            earliest = baseline_context_steps

            latest = (
                len(
                    region_rows
                )
                -
                duration_steps
                -
                max_lag_windows * steps_per_12_hours
                -
                baseline_context_steps
            )

            if latest <= earliest:

                continue

            start_position = int(
                rng.integers(
                    earliest,
                    latest
                    +
                    1,
                )
            )

            # ------------------------------------------------
            # PRIMARY + DOWNSTREAM SUPPORT
            # ------------------------------------------------

            if not _mobility_candidate_supports_scenario(
                region_rows=
                    region_rows,

                start_position=
                    start_position,

                duration_windows=
                    duration_steps,

                scenario_name=
                    scenario_name,

                lag_step_count=
                    steps_per_12_hours,
            ):

                continue

            candidate = (
                region_rows.iloc[
                    start_position:
                    start_position
                    +
                    duration_steps
                ]
            )

            start_timestamp = pd.Timestamp(
                candidate[
                    "window_start"
                ].iloc[
                    0
                ]
            )

            end_timestamp = pd.Timestamp(
                candidate[
                    "window_end"
                ].iloc[
                    -1
                ]
            )

            # Complete causal effect horizon.

            effect_end_timestamp = (
                end_timestamp
                +
                pd.Timedelta(
                    hours=
                        12
                        *
                        max_lag_windows
                )
            )

            # ------------------------------------------------
            # COLLISION CHECK
            # ------------------------------------------------

            conflict = any(
                _mobility_intervals_overlap(
                    start_timestamp,
                    effect_end_timestamp,
                    existing_start,
                    existing_end,
                )

                for (
                    existing_start,
                    existing_end,
                ) in occupied[
                    region_id
                ]
            )

            if conflict:

                continue

            # ------------------------------------------------
            # HIDDEN SCENARIO EVENT
            # ------------------------------------------------

            scenario_rows.append(
                {
                    "scenario_event_id":
                        (
                            "MOB_SCENARIO_SYN_"
                            f"{event_counter:06d}"
                        ),

                    "scenario_name":
                        scenario_name,

                    "severity":
                        MOBILITY_SEVERITY[
                            scenario_name
                        ],

                    "target_scope":
                        "REGION",

                    "region_id":
                        region_id,

                    "region_name":
                        region_name,

                    "start_timestamp":
                        start_timestamp,

                    "end_timestamp":
                        end_timestamp,

                    "duration_windows":
                        duration_windows,

                    "expected_primary_signal":
                        MOBILITY_PRIMARY_SIGNAL[
                            scenario_name
                        ],

                    "expected_direction":
                        MOBILITY_EXPECTED_DIRECTION[
                            scenario_name
                        ],

                    "parent_scenario_event_id":
                        None,

                    "scenario_version":
                        MOBILITY_SCENARIO_VERSION,
                }
            )

            occupied[
                region_id
            ].append(
                (
                    start_timestamp,
                    effect_end_timestamp,
                )
            )

            generated_for_scenario += 1

            event_counter += 1

    scenario_events = pd.DataFrame(
        scenario_rows
    )

    expected_count = (
        len(
            MOBILITY_SCENARIOS
        )
        *
        MOBILITY_EVENTS_PER_SCENARIO
    )

    if (
        len(
            scenario_events
        )
        !=
        expected_count
    ):

        raise ValueError(
            "Mobility scenario event count mismatch. "
            f"Expected {expected_count}, "
            f"found {len(scenario_events)}"
        )

    counts = (
        scenario_events
        .groupby(
            "scenario_name"
        )
        .size()
    )

    for scenario_name in MOBILITY_SCENARIOS:

        actual_count = int(
            counts.get(
                scenario_name,
                0,
            )
        )

        if (
            actual_count
            !=
            MOBILITY_EVENTS_PER_SCENARIO
        ):

            raise ValueError(
                f"{scenario_name} expected "
                f"{MOBILITY_EVENTS_PER_SCENARIO} events, "
                f"found {actual_count}"
            )

    return (
        scenario_events
        .sort_values(
            [
                "start_timestamp",
                "scenario_event_id",
            ]
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# MOBILITY EVENT MASK
# ============================================================


def _mobility_event_mask(
    dataframe: pd.DataFrame,
    event: Mapping[str, Any],
    lag_windows: int = 0,
) -> pd.Series:
    """
    Region-specific Mobility scenario mask.

    1 lag window = 12 hours.
    """

    lag = pd.Timedelta(
        hours=
            12
            *
            lag_windows
    )

    start = (
        pd.Timestamp(
            event[
                "start_timestamp"
            ]
        )
        +
        lag
    )

    end = (
        pd.Timestamp(
            event[
                "end_timestamp"
            ]
        )
        +
        lag
    )

    timestamps = pd.to_datetime(
        dataframe[
            "window_start"
        ]
    )

    return (
        (
            dataframe[
                "region_id"
            ].astype(str)
            ==
            str(
                event[
                    "region_id"
                ]
            )
        )
        &
        (
            timestamps
            >=
            start
        )
        &
        (
            timestamps
            <
            end
        )
    )


# ============================================================
# COUNT REDUCTION
# ============================================================


def _reduce_count_signal(
    adjusted: pd.DataFrame,
    indices: pd.Index,
    column: str,
    fraction: float,
    curve: np.ndarray,
) -> np.ndarray:
    """
    Reduce integer event counts deterministically.

    Returns number removed per observation.
    """

    original = (
        pd.to_numeric(
            adjusted.loc[
                indices,
                column,
            ],
            errors="raise",
        )
        .to_numpy(
            dtype=float
        )
    )

    removed = np.floor(
        original
        *
        fraction
        *
        curve
    ).astype(int)

    active = (
        original
        >
        0
    )

    force = (
        active
        &
        (
            removed
            ==
            0
        )
        &
        (
            curve
            >
            0.80
        )
    )

    removed[
        force
    ] = 1

    removed = np.minimum(
        removed,
        original.astype(int),
    )

    new_values = (
        original.astype(int)
        -
        removed
    )

    adjusted.loc[
        indices,
        column,
    ] = new_values

    return removed


# ============================================================
# APPLY ONE MOBILITY EVENT
# ============================================================


def _apply_mobility_event(
    adjusted: pd.DataFrame,
    event: Mapping[str, Any],
) -> None:
    """
    Apply one controlled Mobility scenario.

    Only observable runtime signals are changed.
    """

    scenario_name = str(
        event[
            "scenario_name"
        ]
    )

    primary_mask = (
        _mobility_event_mask(
            adjusted,
            event,
        )
    )

    primary_indices = (
        adjusted.index[
            primary_mask
        ]
    )

    if len(
        primary_indices
    ) == 0:

        raise ValueError(
            f"{event['scenario_event_id']} has no "
            "Mobility observations"
        )

    curve = (
        _scenario_curve(
            len(
                primary_indices
            )
        )
    )

    # ========================================================
    # DEALER FOLLOW-UP DETERIORATION
    #
    # scheduled followups unchanged
    #
    # completed ↓ at t
    # response ↓ at t+1
    # test drive ↓ at t+2
    # booking ↓ at t+3
    # ========================================================

    if (
        scenario_name
        ==
        "dealer_followup_deterioration"
    ):

        _reduce_count_signal(
            adjusted=
                adjusted,

            indices=
                primary_indices,

            column=
                "followup_completed_count",

            fraction=
                0.40,

            curve=
                curve,
        )

        response_mask = (
            _mobility_event_mask(
                adjusted,
                event,
                lag_windows=1,
            )
        )

        response_indices = (
            adjusted.index[
                response_mask
            ]
        )

        if len(
            response_indices
        ):

            response_curve = (
                _scenario_curve(
                    len(
                        response_indices
                    )
                )
            )

            _reduce_count_signal(
                adjusted=
                    adjusted,

                indices=
                    response_indices,

                column=
                    "customer_response_count",

                fraction=
                    0.35,

                curve=
                    response_curve,
            )

            active_response_mask = (
                adjusted.loc[
                    response_indices,
                    "customer_response_count",
                ]
                >
                0
            )

            active_response_indices = (
                response_indices[
                    active_response_mask.to_numpy()
                ]
            )

            if len(
                active_response_indices
            ):

                adjusted.loc[
                    active_response_indices,
                    "avg_followup_response_minutes",
                ] = (
                    pd.to_numeric(
                        adjusted.loc[
                            active_response_indices,
                            "avg_followup_response_minutes",
                        ],
                        errors="raise",
                    )
                    +
                    25.0
                )

        test_mask = (
            _mobility_event_mask(
                adjusted,
                event,
                lag_windows=2,
            )
        )

        test_indices = (
            adjusted.index[
                test_mask
            ]
        )

        if len(
            test_indices
        ):

            _reduce_count_signal(
                adjusted=
                    adjusted,

                indices=
                    test_indices,

                column=
                    "test_drive_completed_count",

                fraction=
                    0.30,

                curve=
                    _scenario_curve(
                        len(
                            test_indices
                        )
                    ),
            )

        booking_mask = (
            _mobility_event_mask(
                adjusted,
                event,
                lag_windows=3,
            )
        )

        booking_indices = (
            adjusted.index[
                booking_mask
            ]
        )

        if len(
            booking_indices
        ):

            _reduce_count_signal(
                adjusted=
                    adjusted,

                indices=
                    booking_indices,

                column=
                    "booking_count",

                fraction=
                    0.28,

                curve=
                    _scenario_curve(
                        len(
                            booking_indices
                        )
                    ),
            )

        return

    # ========================================================
    # FINANCE APPROVAL SLOWDOWN
    #
    # TAT ↑
    # approvals ↓
    # manual review ↑
    # cancellations ↑ at t+2
    # ========================================================

    if (
        scenario_name
        ==
        "finance_approval_slowdown"
    ):

        decision_count = (
            adjusted.loc[
                primary_indices,
                "finance_approved_count",
            ].to_numpy(
                dtype=int
            )
            +
            adjusted.loc[
                primary_indices,
                "finance_rejected_count",
            ].to_numpy(
                dtype=int
            )
            +
            adjusted.loc[
                primary_indices,
                "finance_manual_review_count",
            ].to_numpy(
                dtype=int
            )
        )

        active_positions = (
            decision_count
            >
            0
        )

        active_indices = (
            primary_indices[
                active_positions
            ]
        )

        if len(
            active_indices
        ) == 0:

            raise ValueError(
                "Finance slowdown scenario has no "
                "decision activity"
            )

        active_curve = (
            curve[
                active_positions
            ]
        )

        existing_tat = (
            pd.to_numeric(
                adjusted.loc[
                    active_indices,
                    "avg_finance_approval_tat_hours",
                ],
                errors="raise",
            )
            .to_numpy(
                dtype=float
            )
        )

        existing_tat = np.where(
            existing_tat
            >
            0,
            existing_tat,
            12.0,
        )

        adjusted.loc[
            active_indices,
            "avg_finance_approval_tat_hours",
        ] = (
            existing_tat
            +
            12.0
            *
            active_curve
        )

        removed_approvals = (
            _reduce_count_signal(
                adjusted=
                    adjusted,

                indices=
                    primary_indices,

                column=
                    "finance_approved_count",

                fraction=
                    0.35,

                curve=
                    curve,
            )
        )

        # Removed approvals enter manual review instead of
        # disappearing from the decision process.

        adjusted.loc[
            primary_indices,
            "finance_manual_review_count",
        ] = (
            adjusted.loc[
                primary_indices,
                "finance_manual_review_count",
            ].to_numpy(
                dtype=int
            )
            +
            removed_approvals
        )

        cancellation_mask = (
            _mobility_event_mask(
                adjusted,
                event,
                lag_windows=2,
            )
        )

        cancellation_indices = (
            adjusted.index[
                cancellation_mask
            ]
        )

        if len(
            cancellation_indices
        ):

            cancellation_curve = (
                _scenario_curve(
                    len(
                        cancellation_indices
                    )
                )
            )

            existing_cancellations = (
                adjusted.loc[
                    cancellation_indices,
                    "cancellation_count",
                ]
                .to_numpy(
                    dtype=int
                )
            )

            increment = (
                cancellation_curve
                >
                0.78
            ).astype(int)

            adjusted.loc[
                cancellation_indices,
                "cancellation_count",
            ] = (
                existing_cancellations
                +
                increment
            )

        return

    # ========================================================
    # ALLOCATION CONSTRAINT
    #
    # allocation ↓
    # waitlist ↑
    # allocation wait ↑
    # delivery ↓ at t+2
    # delivery delay duration ↑
    # ========================================================

    if (
        scenario_name
        ==
        "allocation_constraint"
    ):

        removed_allocations = (
            _reduce_count_signal(
                adjusted=
                    adjusted,

                indices=
                    primary_indices,

                column=
                    "allocated_vehicle_count",

                fraction=
                    0.40,

                curve=
                    curve,
            )
        )

        adjusted.loc[
            primary_indices,
            "waitlisted_booking_count",
        ] = (
            adjusted.loc[
                primary_indices,
                "waitlisted_booking_count",
            ].to_numpy(
                dtype=int
            )
            +
            removed_allocations
        )

        allocation_activity = (
            (
                adjusted.loc[
                    primary_indices,
                    "allocated_vehicle_count",
                ].to_numpy(
                    dtype=int
                )
                +
                adjusted.loc[
                    primary_indices,
                    "waitlisted_booking_count",
                ].to_numpy(
                    dtype=int
                )
            )
            >
            0
        )

        allocation_activity_indices = (
            primary_indices[
                allocation_activity
            ]
        )

        if len(
            allocation_activity_indices
        ):

            activity_curve = (
                curve[
                    allocation_activity
                ]
            )

            current_wait = (
                pd.to_numeric(
                    adjusted.loc[
                        allocation_activity_indices,
                        "avg_allocation_wait_hours",
                    ],
                    errors="raise",
                )
                .to_numpy(
                    dtype=float
                )
            )

            adjusted.loc[
                allocation_activity_indices,
                "avg_allocation_wait_hours",
            ] = (
                current_wait
                +
                18.0
                *
                activity_curve
            )

        delivery_mask = (
            _mobility_event_mask(
                adjusted,
                event,
                lag_windows=2,
            )
        )

        delivery_indices = (
            adjusted.index[
                delivery_mask
            ]
        )

        if len(
            delivery_indices
        ):

            delivery_curve = (
                _scenario_curve(
                    len(
                        delivery_indices
                    )
                )
            )

            _reduce_count_signal(
                adjusted=
                    adjusted,

                indices=
                    delivery_indices,

                column=
                    "delivered_vehicle_count",

                fraction=
                    0.28,

                curve=
                    delivery_curve,
            )

            delivered = (
                adjusted.loc[
                    delivery_indices,
                    "delivered_vehicle_count",
                ]
                .to_numpy(
                    dtype=int
                )
            )

            delayed = (
                adjusted.loc[
                    delivery_indices,
                    "delayed_delivery_count",
                ]
                .to_numpy(
                    dtype=int
                )
            )

            delayed = np.minimum(
                delayed,
                delivered,
            )

            adjusted.loc[
                delivery_indices,
                "delayed_delivery_count",
            ] = delayed

            active_delivery = (
                delivered
                >
                0
            )

            active_delivery_indices = (
                delivery_indices[
                    active_delivery
                ]
            )

            if len(
                active_delivery_indices
            ):

                current_delay = (
                    pd.to_numeric(
                        adjusted.loc[
                            active_delivery_indices,
                            "avg_delivery_delay_days",
                        ],
                        errors="raise",
                    )
                    .to_numpy(
                        dtype=float
                    )
                )

                adjusted.loc[
                    active_delivery_indices,
                    "avg_delivery_delay_days",
                ] = (
                    current_delay
                    +
                    1.8
                )

        return

    # ========================================================
    # DELIVERY DELAY SPIKE
    #
    # delivered volume unchanged
    # delayed subset ↑
    # delay duration ↑
    # ========================================================

    if (
        scenario_name
        ==
        "delivery_delay_spike"
    ):

        delivered = (
            adjusted.loc[
                primary_indices,
                "delivered_vehicle_count",
            ]
            .to_numpy(
                dtype=int
            )
        )

        delayed = (
            adjusted.loc[
                primary_indices,
                "delayed_delivery_count",
            ]
            .to_numpy(
                dtype=int
            )
        )

        headroom = np.maximum(
            delivered
            -
            delayed,
            0,
        )

        increment = np.floor(
            headroom
            *
            0.65
            *
            curve
        ).astype(int)

        force = (
            (
                headroom
                >
                0
            )
            &
            (
                increment
                ==
                0
            )
            &
            (
                curve
                >
                0.80
            )
        )

        increment[
            force
        ] = 1

        new_delayed = np.minimum(
            delayed
            +
            increment,
            delivered,
        )

        adjusted.loc[
            primary_indices,
            "delayed_delivery_count",
        ] = new_delayed

        delayed_active = (
            new_delayed
            >
            0
        )

        delayed_indices = (
            primary_indices[
                delayed_active
            ]
        )

        if len(
            delayed_indices
        ):

            active_curve = (
                curve[
                    delayed_active
                ]
            )

            current_delay = (
                pd.to_numeric(
                    adjusted.loc[
                        delayed_indices,
                        "avg_delivery_delay_days",
                    ],
                    errors="raise",
                )
                .to_numpy(
                    dtype=float
                )
            )

            current_delay = np.where(
                current_delay
                >
                0,
                current_delay,
                1.0,
            )

            adjusted.loc[
                delayed_indices,
                "avg_delivery_delay_days",
            ] = (
                current_delay
                +
                3.0
                *
                active_curve
            )

        return

    raise ValueError(
        f"Unknown Mobility scenario: "
        f"{scenario_name}"
    )


# ============================================================
# MOBILITY POST-SCENARIO CONSTRAINTS
# ============================================================


def _enforce_mobility_runtime_constraints(
    adjusted: pd.DataFrame,
) -> None:
    """
    Keep scenario-adjusted runtime observations valid.
    """

    integer_columns = [
        "lead_count",

        "followup_count",
        "followup_completed_count",
        "customer_response_count",

        "test_drive_requested_count",
        "test_drive_completed_count",
        "test_drive_no_show_count",

        "booking_count",

        "finance_application_count",
        "finance_approved_count",
        "finance_rejected_count",
        "finance_manual_review_count",

        "cancellation_count",

        "allocated_vehicle_count",
        "waitlisted_booking_count",

        "delivered_vehicle_count",
        "delayed_delivery_count",

        "service_event_count",
        "unscheduled_repair_count",

        "warranty_claim_count",
        "warranty_approved_count",
    ]

    for column in integer_columns:

        adjusted[
            column
        ] = _clip_count(
            adjusted[
                column
            ]
        )

    # Delayed deliveries are a subset of delivered vehicles.

    adjusted[
        "delayed_delivery_count"
    ] = np.minimum(
        adjusted[
            "delayed_delivery_count"
        ].to_numpy(
            dtype=int
        ),
        adjusted[
            "delivered_vehicle_count"
        ].to_numpy(
            dtype=int
        ),
    )

    continuous_nonnegative = [
        "avg_followup_response_minutes",
        "avg_finance_approval_tat_hours",
        "avg_allocation_wait_hours",
        "avg_delivery_delay_days",
    ]

    for column in continuous_nonnegative:

        adjusted[
            column
        ] = np.maximum(
            pd.to_numeric(
                adjusted[
                    column
                ],
                errors="raise",
            ).to_numpy(
                dtype=float
            ),
            0.0,
        )


# ============================================================
# APPLY ALL MOBILITY SCENARIOS
# ============================================================


def apply_mobility_scenarios(
    mobility_timeseries: pd.DataFrame,
    scenario_events: pd.DataFrame,
) -> pd.DataFrame:
    """
    Apply Mobility scenarios while preserving runtime schema.
    """

    adjusted = (
        mobility_timeseries
        .copy(
            deep=True
        )
    )

    original_columns = list(
        adjusted.columns
    )

    original_row_count = len(
        adjusted
    )

    for event in scenario_events.to_dict(
        orient="records"
    ):

        _apply_mobility_event(
            adjusted=
                adjusted,

            event=
                event,
        )

    _enforce_mobility_runtime_constraints(
        adjusted
    )

    if (
        len(
            adjusted
        )
        !=
        original_row_count
    ):

        raise ValueError(
            "Mobility scenarios changed runtime row count"
        )

    if (
        list(
            adjusted.columns
        )
        !=
        original_columns
    ):

        raise ValueError(
            "Mobility scenarios changed runtime schema"
        )

    if (
        adjusted[
            [
                "region_id",
                "window_start",
            ]
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Mobility scenarios created duplicate "
            "region/window observations"
        )

    _validate_runtime_leakage(
        adjusted,
        "Mobility runtime observations",
    )

    return adjusted


# ============================================================
# MOBILITY VALIDATION HELPERS
# ============================================================


def _mobility_sum(
    dataframe: pd.DataFrame,
    mask: pd.Series,
    column: str,
) -> float:
    """
    Sum observable Mobility signal over fixed event scope.
    """

    return float(
        pd.to_numeric(
            dataframe.loc[
                mask,
                column,
            ],
            errors="raise",
        ).sum()
    )


def _mobility_mean_active(
    dataframe: pd.DataFrame,
    mask: pd.Series,
    column: str,
) -> float:
    """
    Mean positive values.

    Kept for diagnostic/helper use.
    """

    values = pd.to_numeric(
        dataframe.loc[
            mask,
            column,
        ],
        errors="raise",
    )

    active = (
        values[
            values
            >
            0
        ]
    )

    if active.empty:

        return 0.0

    return float(
        active.mean()
    )


def _mobility_mean_all(
    dataframe: pd.DataFrame,
    mask: pd.Series,
    column: str,
) -> float:
    """
    Mean across the complete fixed scenario window,
    INCLUDING zero-valued observations.

    Important for:

        avg_delivery_delay_days
        avg_finance_approval_tat_hours
        avg_allocation_wait_hours

    because a scenario may make previously inactive windows
    become positive.
    """

    values = pd.to_numeric(
        dataframe.loc[
            mask,
            column,
        ],
        errors="raise",
    )

    if values.empty:

        return 0.0

    return float(
        values.mean()
    )


# ============================================================
# VALIDATE MOBILITY SCENARIO EFFECTS
# ============================================================


def validate_mobility_scenario_effects(
    baseline: pd.DataFrame,
    adjusted: pd.DataFrame,
    scenario_events: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate every Mobility event using exact before/after
    region/time scopes.

    Count signals use sums.

    Continuous metrics use complete fixed-window means.
    """

    validation_rows: list[
        dict[str, Any]
    ] = []

    for event in scenario_events.to_dict(
        orient="records"
    ):

        scenario_name = str(
            event[
                "scenario_name"
            ]
        )

        primary_signal = str(
            event[
                "expected_primary_signal"
            ]
        )

        direction = str(
            event[
                "expected_direction"
            ]
        )

        primary_mask = (
            _mobility_event_mask(
                baseline,
                event,
            )
        )

        # ====================================================
        # PRIMARY SIGNAL
        # ====================================================

        if (
            scenario_name
            ==
            "finance_approval_slowdown"
        ):

            baseline_primary = (
                _mobility_mean_all(
                    baseline,
                    primary_mask,
                    primary_signal,
                )
            )

            adjusted_primary = (
                _mobility_mean_all(
                    adjusted,
                    primary_mask,
                    primary_signal,
                )
            )

        else:

            baseline_primary = (
                _mobility_sum(
                    baseline,
                    primary_mask,
                    primary_signal,
                )
            )

            adjusted_primary = (
                _mobility_sum(
                    adjusted,
                    primary_mask,
                    primary_signal,
                )
            )

        # ====================================================
        # PRIMARY DIRECTION
        # ====================================================

        if direction == "UP":

            validation_metric = (
                adjusted_primary
                -
                baseline_primary
            )

            primary_passed = (
                validation_metric
                >
                0
            )

        elif direction == "DOWN":

            validation_metric = (
                baseline_primary
                -
                adjusted_primary
            )

            primary_passed = (
                validation_metric
                >
                0
            )

        else:

            raise ValueError(
                f"Unsupported Mobility direction: "
                f"{direction}"
            )

        secondary_passed = True

        secondary_details: list[str] = []

        # ====================================================
        # DEALER FOLLOW-UP DETERIORATION
        # ====================================================

        if (
            scenario_name
            ==
            "dealer_followup_deterioration"
        ):

            response_mask = (
                _mobility_event_mask(
                    baseline,
                    event,
                    lag_windows=1,
                )
            )

            test_drive_mask = (
                _mobility_event_mask(
                    baseline,
                    event,
                    lag_windows=2,
                )
            )

            booking_mask = (
                _mobility_event_mask(
                    baseline,
                    event,
                    lag_windows=3,
                )
            )

            response_before = (
                _mobility_sum(
                    baseline,
                    response_mask,
                    "customer_response_count",
                )
            )

            response_after = (
                _mobility_sum(
                    adjusted,
                    response_mask,
                    "customer_response_count",
                )
            )

            test_drive_before = (
                _mobility_sum(
                    baseline,
                    test_drive_mask,
                    "test_drive_completed_count",
                )
            )

            test_drive_after = (
                _mobility_sum(
                    adjusted,
                    test_drive_mask,
                    "test_drive_completed_count",
                )
            )

            booking_before = (
                _mobility_sum(
                    baseline,
                    booking_mask,
                    "booking_count",
                )
            )

            booking_after = (
                _mobility_sum(
                    adjusted,
                    booking_mask,
                    "booking_count",
                )
            )

            checks = {
                "customer_response_down":
                    (
                        response_after
                        <
                        response_before
                    ),

                "test_drive_completed_down":
                    (
                        test_drive_after
                        <
                        test_drive_before
                    ),

                "bookings_down":
                    (
                        booking_after
                        <
                        booking_before
                    ),
            }

            secondary_passed = all(
                checks.values()
            )

            secondary_details = [
                (
                    "customer_response_down="
                    f"{checks['customer_response_down']}"
                    f"({response_before:.1f}"
                    "->"
                    f"{response_after:.1f})"
                ),

                (
                    "test_drive_completed_down="
                    f"{checks['test_drive_completed_down']}"
                    f"({test_drive_before:.1f}"
                    "->"
                    f"{test_drive_after:.1f})"
                ),

                (
                    "bookings_down="
                    f"{checks['bookings_down']}"
                    f"({booking_before:.1f}"
                    "->"
                    f"{booking_after:.1f})"
                ),
            ]

        # ====================================================
        # FINANCE APPROVAL SLOWDOWN
        # ====================================================

        elif (
            scenario_name
            ==
            "finance_approval_slowdown"
        ):

            cancellation_mask = (
                _mobility_event_mask(
                    baseline,
                    event,
                    lag_windows=2,
                )
            )

            approval_before = (
                _mobility_sum(
                    baseline,
                    primary_mask,
                    "finance_approved_count",
                )
            )

            approval_after = (
                _mobility_sum(
                    adjusted,
                    primary_mask,
                    "finance_approved_count",
                )
            )

            manual_before = (
                _mobility_sum(
                    baseline,
                    primary_mask,
                    "finance_manual_review_count",
                )
            )

            manual_after = (
                _mobility_sum(
                    adjusted,
                    primary_mask,
                    "finance_manual_review_count",
                )
            )

            cancellation_before = (
                _mobility_sum(
                    baseline,
                    cancellation_mask,
                    "cancellation_count",
                )
            )

            cancellation_after = (
                _mobility_sum(
                    adjusted,
                    cancellation_mask,
                    "cancellation_count",
                )
            )

            checks = {
                "finance_approved_down":
                    (
                        approval_after
                        <
                        approval_before
                    ),

                "manual_review_up":
                    (
                        manual_after
                        >
                        manual_before
                    ),

                "cancellations_up":
                    (
                        cancellation_after
                        >
                        cancellation_before
                    ),
            }

            secondary_passed = all(
                checks.values()
            )

            secondary_details = [
                (
                    "finance_approved_down="
                    f"{checks['finance_approved_down']}"
                    f"({approval_before:.1f}"
                    "->"
                    f"{approval_after:.1f})"
                ),

                (
                    "manual_review_up="
                    f"{checks['manual_review_up']}"
                    f"({manual_before:.1f}"
                    "->"
                    f"{manual_after:.1f})"
                ),

                (
                    "cancellations_up="
                    f"{checks['cancellations_up']}"
                    f"({cancellation_before:.1f}"
                    "->"
                    f"{cancellation_after:.1f})"
                ),
            ]

        # ====================================================
        # ALLOCATION CONSTRAINT
        # ====================================================

        elif (
            scenario_name
            ==
            "allocation_constraint"
        ):

            delivery_mask = (
                _mobility_event_mask(
                    baseline,
                    event,
                    lag_windows=2,
                )
            )

            waitlist_before = (
                _mobility_sum(
                    baseline,
                    primary_mask,
                    "waitlisted_booking_count",
                )
            )

            waitlist_after = (
                _mobility_sum(
                    adjusted,
                    primary_mask,
                    "waitlisted_booking_count",
                )
            )

            allocation_wait_before = (
                _mobility_mean_all(
                    baseline,
                    primary_mask,
                    "avg_allocation_wait_hours",
                )
            )

            allocation_wait_after = (
                _mobility_mean_all(
                    adjusted,
                    primary_mask,
                    "avg_allocation_wait_hours",
                )
            )

            deliveries_before = (
                _mobility_sum(
                    baseline,
                    delivery_mask,
                    "delivered_vehicle_count",
                )
            )

            deliveries_after = (
                _mobility_sum(
                    adjusted,
                    delivery_mask,
                    "delivered_vehicle_count",
                )
            )

            checks = {
                "waitlist_up":
                    (
                        waitlist_after
                        >
                        waitlist_before
                    ),

                "allocation_wait_up":
                    (
                        allocation_wait_after
                        >
                        allocation_wait_before
                    ),

                "deliveries_down":
                    (
                        deliveries_after
                        <
                        deliveries_before
                    ),
            }

            secondary_passed = all(
                checks.values()
            )

            secondary_details = [
                (
                    "waitlist_up="
                    f"{checks['waitlist_up']}"
                    f"({waitlist_before:.1f}"
                    "->"
                    f"{waitlist_after:.1f})"
                ),

                (
                    "allocation_wait_up="
                    f"{checks['allocation_wait_up']}"
                    f"({allocation_wait_before:.3f}"
                    "->"
                    f"{allocation_wait_after:.3f})"
                ),

                (
                    "deliveries_down="
                    f"{checks['deliveries_down']}"
                    f"({deliveries_before:.1f}"
                    "->"
                    f"{deliveries_after:.1f})"
                ),
            ]

        # ====================================================
        # DELIVERY DELAY SPIKE
        # ====================================================

        elif (
            scenario_name
            ==
            "delivery_delay_spike"
        ):

            delay_count_before = (
                _mobility_sum(
                    baseline,
                    primary_mask,
                    "delayed_delivery_count",
                )
            )

            delay_count_after = (
                _mobility_sum(
                    adjusted,
                    primary_mask,
                    "delayed_delivery_count",
                )
            )

            delay_days_before = (
                _mobility_mean_all(
                    baseline,
                    primary_mask,
                    "avg_delivery_delay_days",
                )
            )

            delay_days_after = (
                _mobility_mean_all(
                    adjusted,
                    primary_mask,
                    "avg_delivery_delay_days",
                )
            )

            checks = {
                "delay_count_up":
                    (
                        delay_count_after
                        >
                        delay_count_before
                    ),

                "delay_days_up":
                    (
                        delay_days_after
                        >
                        delay_days_before
                    ),
            }

            secondary_passed = all(
                checks.values()
            )

            secondary_details = [
                (
                    "delay_count_up="
                    f"{checks['delay_count_up']}"
                    f"({delay_count_before:.1f}"
                    "->"
                    f"{delay_count_after:.1f})"
                ),

                (
                    "delay_days_up="
                    f"{checks['delay_days_up']}"
                    f"({delay_days_before:.3f}"
                    "->"
                    f"{delay_days_after:.3f})"
                ),
            ]

        else:

            raise ValueError(
                f"Unknown Mobility scenario during "
                f"validation: {scenario_name}"
            )

        passed = (
            primary_passed
            and
            secondary_passed
        )

        validation_rows.append(
            {
                "scenario_event_id":
                    event[
                        "scenario_event_id"
                    ],

                "scenario_name":
                    scenario_name,

                "region_id":
                    event[
                        "region_id"
                    ],

                "region_name":
                    event[
                        "region_name"
                    ],

                "primary_signal":
                    primary_signal,

                "expected_direction":
                    direction,

                "baseline_value":
                    baseline_primary,

                "adjusted_value":
                    adjusted_primary,

                "validation_metric":
                    float(
                        validation_metric
                    ),

                "secondary_checks":
                    "; ".join(
                        secondary_details
                    ),

                "passed":
                    bool(
                        passed
                    ),
            }
        )

    validation = pd.DataFrame(
        validation_rows
    )

    expected_validation_count = (
        len(
            MOBILITY_SCENARIOS
        )
        *
        MOBILITY_EVENTS_PER_SCENARIO
    )

    if (
        len(
            validation
        )
        !=
        expected_validation_count
    ):

        raise ValueError(
            "Mobility scenario validation-count mismatch. "
            f"Expected {expected_validation_count}, "
            f"found {len(validation)}"
        )

    failed = (
        validation[
            ~validation[
                "passed"
            ]
        ]
    )

    if not failed.empty:

        raise ValueError(
            "Mobility scenario validation failed:\n"
            +
            failed.to_string(
                index=False
            )
        )

    return validation


# ============================================================
# PUBLIC MOBILITY API
# ============================================================


def generate_and_apply_mobility_scenarios(
    mobility_timeseries: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Generate and apply controlled Mobility scenarios.

    Returns:

        adjusted runtime-safe Mobility observations

        separate hidden scenario-event truth
    """

    _validate_runtime_leakage(
        mobility_timeseries,
        "baseline Mobility observations",
    )

    scenario_events = (
        generate_mobility_scenario_schedule(
            mobility_timeseries=
                mobility_timeseries,

            generation=
                generation,
        )
    )

    adjusted = (
        apply_mobility_scenarios(
            mobility_timeseries=
                mobility_timeseries,

            scenario_events=
                scenario_events,
        )
    )

    validate_mobility_scenario_effects(
        baseline=
            mobility_timeseries,

        adjusted=
            adjusted,

        scenario_events=
            scenario_events,
    )

    return (
        adjusted,
        scenario_events,
    )


# ============================================================
# ============================================================
#
# LOCAL INTEGRATION HELPER
#
# ============================================================
# ============================================================


def _invoke_generator_for_local_test(
    function,
    available_inputs: Mapping[str, Any],
):
    """
    Invoke an existing generator using its actual Python
    signature.

    Extra DataFrames are ignored.

    Missing required parameters fail loudly.

    This prevents scenarios.py from forcing incorrect
    signatures onto already-working Auto generators.
    """

    signature = inspect.signature(
        function
    )

    kwargs: dict[
        str,
        Any,
    ] = {}

    for (
        parameter_name,
        parameter,
    ) in signature.parameters.items():

        if (
            parameter.kind
            in
            {
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }
        ):

            continue

        if parameter_name in available_inputs:

            kwargs[
                parameter_name
            ] = available_inputs[
                parameter_name
            ]

            continue

        if (
            parameter.default
            is
            inspect.Parameter.empty
        ):

            raise TypeError(
                f"Cannot run {function.__name__}: "
                f"required parameter '{parameter_name}' "
                "is unavailable in scenarios.py local "
                "integration test.\n"
                f"Function signature: {signature}\n"
                "Available inputs: "
                +
                ", ".join(
                    sorted(
                        available_inputs.keys()
                    )
                )
            )

    return function(
        **kwargs
    )


# ============================================================
# ============================================================
#
# LOCAL FULL INTEGRATION TEST
#
# ============================================================
# ============================================================


if __name__ == "__main__":

    # ========================================================
    # MASTER GENERATORS
    # ========================================================

    from data.generators.master.geography import (
        generate_geography,
    )

    from data.generators.master.vehicle_models import (
        generate_vehicle_models,
    )

    from data.generators.master.dealers import (
        generate_dealer_master,
    )

    from data.generators.master.plants import (
        generate_plant_master,
    )

    from data.generators.master.machines import (
        generate_machine_master,
    )

    # ========================================================
    # AUTO GENERATORS
    # ========================================================

    from data.generators.auto.customers import (
        generate_customer_master,
    )

    from data.generators.auto.leads import (
        generate_lead_master,
    )

    from data.generators.auto.followups import (
        generate_followup_master,
    )

    from data.generators.auto.test_drives import (
        generate_test_drive_master,
    )

    from data.generators.auto.bookings import (
        generate_booking_master,
    )

    from data.generators.auto.finance_applications import (
        generate_finance_application_master,
    )

    from data.generators.auto.cancellations import (
        generate_cancellation_master,
    )

    from data.generators.auto.suppliers import (
        generate_supplier_master,
    )

    from data.generators.auto.production import (
        generate_production_batch_master,
    )

    from data.generators.auto.allocations import (
        generate_allocation_master,
    )

    from data.generators.auto.deliveries import (
        generate_delivery_master,
    )

    from data.generators.auto.service import (
        generate_service_master,
    )

    from data.generators.auto.warranty import (
        generate_warranty_master,
    )

    # ========================================================
    # CAUSAL GENERATORS
    # ========================================================

    from data.generators.causal.manufacturing_timeseries import (
        generate_manufacturing_timeseries_master,
    )

    from data.generators.causal.mobility_timeseries import (
        generate_mobility_timeseries_master,
    )

    # ========================================================
    # MASTER DATA
    # ========================================================

    (
        regions_df,
        cities_df,
    ) = generate_geography()

    vehicle_models_df = (
        generate_vehicle_models()
    )

    dealers_df = (
        generate_dealer_master(
            regions=
                regions_df,

            cities=
                cities_df,
        )
    )

    (
        plants_df,
        production_lines_df,
    ) = (
        generate_plant_master(
            cities_df
        )
    )

    machines_df = (
        generate_machine_master(
            production_lines_df
        )
    )

    # ========================================================
    # AUTO BUSINESS CHAIN
    # ========================================================

    customers_df = (
        generate_customer_master(
            regions=
                regions_df,

            cities=
                cities_df,

            vehicle_models=
                vehicle_models_df,
        )
    )

    leads_df = (
        generate_lead_master(
            customers=
                customers_df,

            dealers=
                dealers_df,

            vehicle_models=
                vehicle_models_df,
        )
    )

    followups_df = (
        generate_followup_master(
            leads=
                leads_df,

            dealers=
                dealers_df,
        )
    )

    test_drives_df = (
        generate_test_drive_master(
            leads=
                leads_df,

            followups=
                followups_df,
        )
    )

    bookings_df = (
        generate_booking_master(
            customers=
                customers_df,

            leads=
                leads_df,

            followups=
                followups_df,

            test_drives=
                test_drives_df,

            vehicle_models=
                vehicle_models_df,
        )
    )

    finance_applications_df = (
        generate_finance_application_master(
            bookings=
                bookings_df,

            customers=
                customers_df,
        )
    )

    cancellations_df = (
        generate_cancellation_master(
            bookings=
                bookings_df,

            finance_applications=
                finance_applications_df,
        )
    )

    # ========================================================
    # SUPPLIER DATA
    # ========================================================

    (
        suppliers_df,
        supplier_lots_df,
    ) = (
        generate_supplier_master(
            cities=
                cities_df
        )
    )

    # ========================================================
    # PRODUCTION
    # ========================================================

    production_batches_df = (
        generate_production_batch_master(
            plants=
                plants_df,

            production_lines=
                production_lines_df,

            machines=
                machines_df,

            vehicle_models=
                vehicle_models_df,

            suppliers=
                suppliers_df,

            supplier_lots=
                supplier_lots_df,
        )
    )

    # ========================================================
    # ALLOCATION
    # ========================================================

    allocations_df = (
        generate_allocation_master(
            bookings=
                bookings_df,

            cancellations=
                cancellations_df,

            production_batches=
                production_batches_df,

            dealers=
                dealers_df,

            finance_applications=
                finance_applications_df,
        )
    )

    # ========================================================
    # AVAILABLE INPUT REGISTRY
    # ========================================================

    available_inputs: dict[
        str,
        Any,
    ] = {
        # Master

        "regions":
            regions_df,

        "cities":
            cities_df,

        "vehicle_models":
            vehicle_models_df,

        "dealers":
            dealers_df,

        "plants":
            plants_df,

        "production_lines":
            production_lines_df,

        "machines":
            machines_df,

        # Auto

        "customers":
            customers_df,

        "leads":
            leads_df,

        "followups":
            followups_df,

        "test_drives":
            test_drives_df,

        "bookings":
            bookings_df,

        "finance_applications":
            finance_applications_df,

        "cancellations":
            cancellations_df,

        # Supply

        "suppliers":
            suppliers_df,

        "supplier_lots":
            supplier_lots_df,

        "production_batches":
            production_batches_df,

        # Allocation

        "allocations":
            allocations_df,
    }

    # ========================================================
    # DELIVERY
    #
    # Uses ACTUAL delivery generator signature.
    # ========================================================

    deliveries_df = (
        _invoke_generator_for_local_test(
            generate_delivery_master,
            available_inputs,
        )
    )

    available_inputs[
        "deliveries"
    ] = deliveries_df

    available_inputs[
        "delivery"
    ] = deliveries_df

    # ========================================================
    # SERVICE
    # ========================================================

    service_events_df = (
        _invoke_generator_for_local_test(
            generate_service_master,
            available_inputs,
        )
    )

    available_inputs[
        "service_events"
    ] = service_events_df

    available_inputs[
        "services"
    ] = service_events_df

    available_inputs[
        "service"
    ] = service_events_df

    # ========================================================
    # WARRANTY
    # ========================================================

    warranty_claims_df = (
        _invoke_generator_for_local_test(
            generate_warranty_master,
            available_inputs,
        )
    )

    available_inputs[
        "warranty_claims"
    ] = warranty_claims_df

    available_inputs[
        "warranty"
    ] = warranty_claims_df

    # ========================================================
    # MANUFACTURING BASELINE
    # ========================================================

    manufacturing_baseline_df = (
        generate_manufacturing_timeseries_master(
            plants=
                plants_df,

            production_lines=
                production_lines_df,

            machines=
                machines_df,

            production_batches=
                production_batches_df,
        )
    )

    # ========================================================
    # MANUFACTURING SCENARIOS
    # ========================================================

    (
        manufacturing_adjusted_df,
        manufacturing_scenario_events_df,
    ) = (
        generate_and_apply_manufacturing_scenarios(
            manufacturing_timeseries=
                manufacturing_baseline_df
        )
    )

    manufacturing_validation_df = (
        validate_manufacturing_scenario_effects(
            baseline=
                manufacturing_baseline_df,

            adjusted=
                manufacturing_adjusted_df,

            scenario_events=
                manufacturing_scenario_events_df,
        )
    )

    # ========================================================
    # MANUFACTURING SUMMARY
    # ========================================================

    print(
        "\n=== MANUFACTURING SCENARIO CHECK ===\n"
    )

    print(
        "Baseline rows:",
        len(
            manufacturing_baseline_df
        ),
    )

    print(
        "Adjusted rows:",
        len(
            manufacturing_adjusted_df
        ),
    )

    print(
        "Scenario events:",
        len(
            manufacturing_scenario_events_df
        ),
    )

    print(
        "Target machines:",
        manufacturing_scenario_events_df[
            "machine_id"
        ].nunique(),
    )

    print(
        "\n=== MANUFACTURING SCENARIO EVENT COUNTS ===\n"
    )

    print(
        manufacturing_scenario_events_df
        .groupby(
            "scenario_name"
        )
        .size()
        .reset_index(
            name=
                "event_count"
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== MANUFACTURING PER-SCENARIO "
        "EFFECT VALIDATION ===\n"
    )

    print(
        manufacturing_validation_df
        .to_string(
            index=False
        )
    )

    print(
        "\nManufacturing scenario validations passed:",
        int(
            manufacturing_validation_df[
                "passed"
            ].sum()
        ),
        "/",
        len(
            manufacturing_validation_df
        ),
    )

    inconsistent_pairs = (
        count_inconsistent_supplier_lot_timestamp_pairs(
            manufacturing_adjusted_df
        )
    )

    print(
        "\n=== SUPPLIER LOT CONSISTENCY CHECK ===\n"
    )

    print(
        "Inconsistent lot/timestamp pairs:",
        inconsistent_pairs,
    )

    manufacturing_leaked = (
        FORBIDDEN_RUNTIME_COLUMNS
        &
        set(
            manufacturing_adjusted_df.columns
        )
    )

    print(
        "\n=== MANUFACTURING RUNTIME GROUND-TRUTH "
        "LEAKAGE CHECK ===\n"
    )

    print(
        "Leaked columns:",
        sorted(
            manufacturing_leaked
        ),
    )

    # ========================================================
    # MOBILITY BASELINE
    # ========================================================

    mobility_baseline_df = (
        generate_mobility_timeseries_master(
            regions=
                regions_df,

            leads=
                leads_df,

            followups=
                followups_df,

            test_drives=
                test_drives_df,

            bookings=
                bookings_df,

            finance_applications=
                finance_applications_df,

            cancellations=
                cancellations_df,

            allocations=
                allocations_df,

            deliveries=
                deliveries_df,

            service_events=
                service_events_df,

            warranty_claims=
                warranty_claims_df,
        )
    )

    # ========================================================
    # MOBILITY SCENARIOS
    # ========================================================

    (
        mobility_adjusted_df,
        mobility_scenario_events_df,
    ) = (
        generate_and_apply_mobility_scenarios(
            mobility_timeseries=
                mobility_baseline_df
        )
    )

    mobility_validation_df = (
        validate_mobility_scenario_effects(
            baseline=
                mobility_baseline_df,

            adjusted=
                mobility_adjusted_df,

            scenario_events=
                mobility_scenario_events_df,
        )
    )

    # ========================================================
    # MOBILITY SUMMARY
    # ========================================================

    print(
        "\n\n============================================"
    )

    print(
        "=== MOBILITY SCENARIO CHECK ==="
    )

    print(
        "============================================\n"
    )

    print(
        "Baseline rows:",
        len(
            mobility_baseline_df
        ),
    )

    print(
        "Adjusted rows:",
        len(
            mobility_adjusted_df
        ),
    )

    print(
        "Scenario events:",
        len(
            mobility_scenario_events_df
        ),
    )

    print(
        "Regions affected:",
        mobility_scenario_events_df[
            "region_id"
        ].nunique(),
    )

    # ========================================================
    # SCENARIO COUNTS
    # ========================================================

    print(
        "\n=== MOBILITY SCENARIO EVENT COUNTS ===\n"
    )

    print(
        mobility_scenario_events_df
        .groupby(
            "scenario_name"
        )
        .size()
        .reset_index(
            name=
                "event_count"
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # HIDDEN SCENARIO GROUND TRUTH
    # ========================================================

    print(
        "\n=== MOBILITY SCENARIO GROUND-TRUTH SAMPLE ===\n"
    )

    print(
        mobility_scenario_events_df[
            [
                "scenario_event_id",
                "scenario_name",

                "severity",

                "region_id",
                "region_name",

                "start_timestamp",
                "end_timestamp",

                "duration_windows",

                "expected_primary_signal",
                "expected_direction",
            ]
        ]
        .to_string(
            index=False
        )
    )

    # ========================================================
    # MOBILITY EFFECT VALIDATION
    # ========================================================

    print(
        "\n=== MOBILITY PER-SCENARIO EFFECT "
        "VALIDATION ===\n"
    )

    print(
        mobility_validation_df
        .to_string(
            index=False
        )
    )

    print(
        "\nMobility scenario validations passed:",
        int(
            mobility_validation_df[
                "passed"
            ].sum()
        ),
        "/",
        len(
            mobility_validation_df
        ),
    )

    # ========================================================
    # GLOBAL DIAGNOSTIC
    #
    # Diagnostic only.
    #
    # Event-level validation above is authoritative.
    # ========================================================

    print(
        "\n=== MOBILITY GLOBAL BEFORE / AFTER CHECK ===\n"
    )

    mobility_diagnostic_columns = [
        "followup_completed_count",
        "customer_response_count",

        "test_drive_completed_count",

        "booking_count",

        "finance_approved_count",
        "avg_finance_approval_tat_hours",

        "cancellation_count",

        "allocated_vehicle_count",
        "waitlisted_booking_count",
        "avg_allocation_wait_hours",

        "delivered_vehicle_count",
        "delayed_delivery_count",
        "avg_delivery_delay_days",
    ]

    for column in mobility_diagnostic_columns:

        before = float(
            pd.to_numeric(
                mobility_baseline_df[
                    column
                ],
                errors="raise",
            ).mean()
        )

        after = float(
            pd.to_numeric(
                mobility_adjusted_df[
                    column
                ],
                errors="raise",
            ).mean()
        )

        print(
            f"{column}: "
            f"{before:.6f} -> {after:.6f}"
        )

    # ========================================================
    # MOBILITY RUNTIME LEAKAGE
    # ========================================================

    mobility_leaked = (
        FORBIDDEN_RUNTIME_COLUMNS
        &
        set(
            mobility_adjusted_df.columns
        )
    )

    print(
        "\n=== MOBILITY RUNTIME GROUND-TRUTH "
        "LEAKAGE CHECK ===\n"
    )

    print(
        "Leaked columns:",
        sorted(
            mobility_leaked
        ),
    )

    # ========================================================
    # FINAL STATUS
    # ========================================================

    print(
        "\n=== FINAL CAUSAL SCENARIO STATUS ===\n"
    )

    print(
        "Manufacturing validations:",
        int(
            manufacturing_validation_df[
                "passed"
            ].sum()
        ),
        "/",
        len(
            manufacturing_validation_df
        ),
    )

    print(
        "Mobility validations:",
        int(
            mobility_validation_df[
                "passed"
            ].sum()
        ),
        "/",
        len(
            mobility_validation_df
        ),
    )

    print(
        "Supplier inconsistencies:",
        inconsistent_pairs,
    )

    print(
        "Manufacturing leaked columns:",
        sorted(
            manufacturing_leaked
        ),
    )

    print(
        "Mobility leaked columns:",
        sorted(
            mobility_leaked
        ),
    )

    print(
        "\nManufacturing and Mobility controlled "
        "causal scenarios generated successfully."
    )