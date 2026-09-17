"""
Causal Ground-Truth Generator
for Mahindra AI Nexus.

This module contains HIDDEN synthetic causal truth used ONLY
for evaluation.

It supports two independent causal domains:

1. Manufacturing / Quality
2. Auto / Mobility Business


============================================================
CRITICAL RULE
============================================================

This file contains answers known by the synthetic generator.

Runtime PCMCI/Tigramite MUST NEVER read these DataFrames.

Runtime flow:

    observable historical data
            ↓
    preprocessing
            ↓
    PCMCI / Tigramite
            ↓
    discovered edges
            ↓
    evaluation against this ground truth

Ground-truth flow:

    synthetic generator knowledge
            ↓
    ground_truth.py
            ↓
    data/ground_truth/causal/
            ↓
    evaluation only


============================================================
THIS MODULE DOES NOT WRITE CSV FILES
============================================================

CSV writing is handled later by:

    generate_all.py
    export_csv.py

Runtime PostgreSQL imports must also keep ground truth
separate from operational observations.
"""

from __future__ import annotations

import inspect

from typing import Any, Callable, Mapping

import pandas as pd

from data.generators.causal.scenarios import (
    FORBIDDEN_RUNTIME_COLUMNS,
    MANUFACTURING_SCENARIOS,
    MOBILITY_SCENARIOS,
    count_inconsistent_supplier_lot_timestamp_pairs,
    generate_and_apply_manufacturing_scenarios,
    generate_and_apply_mobility_scenarios,
)

from data.generators.causal.mobility_timeseries import (
    MOBILITY_PCMCI_PRIMARY_VARIABLES,
)


# ============================================================
# GROUND-TRUTH VERSION
# ============================================================

MANUFACTURING_GROUND_TRUTH_VERSION = (
    "MFG_CAUSAL_GT_V1"
)

MOBILITY_GROUND_TRUTH_VERSION = (
    "MOBILITY_CAUSAL_GT_V1"
)


# ============================================================
# ============================================================
#
# SHARED VALIDATION HELPERS
#
# ============================================================
# ============================================================


def _validate_runtime_leakage(
    dataframe: pd.DataFrame,
    dataset_name: str,
) -> None:
    """
    Confirm that hidden synthetic truth has not leaked into
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


def _require_columns(
    dataframe: pd.DataFrame,
    required_columns: set[str],
    dataset_name: str,
) -> None:
    """
    Validate required columns.
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


def _validate_unique_column(
    dataframe: pd.DataFrame,
    column: str,
    dataset_name: str,
) -> None:
    """
    Validate uniqueness of an identifier column.
    """

    if (
        dataframe[
            column
        ]
        .duplicated()
        .any()
    ):

        duplicates = (
            dataframe.loc[
                dataframe[
                    column
                ].duplicated(
                    keep=False
                ),
                column,
            ]
            .astype(str)
            .unique()
            .tolist()
        )

        raise ValueError(
            f"{dataset_name} contains duplicate "
            f"{column}: "
            +
            ", ".join(
                duplicates[
                    :20
                ]
            )
        )


def _validate_ground_truth_signs(
    edges: pd.DataFrame,
    dataset_name: str,
) -> None:
    """
    Validate supported edge signs.
    """

    supported = {
        "POSITIVE",
        "NEGATIVE",
        "NONLINEAR",
    }

    invalid = (
        set(
            edges[
                "sign"
            ]
            .astype(str)
        )
        -
        supported
    )

    if invalid:

        raise ValueError(
            f"{dataset_name} contains unsupported signs: "
            +
            ", ".join(
                sorted(
                    invalid
                )
            )
        )


# ============================================================
# ============================================================
#
# MANUFACTURING CAUSAL GROUND TRUTH
#
# ============================================================
# ============================================================


# ============================================================
# EXACT MANUFACTURING EDGE CATALOGUE
#
# This preserves the already-validated 41-edge truth:
#
# 25 baseline structural
# 5 baseline autoregressive
# 11 scenario structural
# ============================================================


MANUFACTURING_EDGE_DEFINITIONS: tuple[
    tuple[
        str,
        str,
        int,
        str,
        str,
        str,
        str,
        str | None,
        bool,
    ],
    ...,
] = (

    # ========================================================
    # BASELINE STRUCTURAL EDGES — 25
    # ========================================================

    (
        "ambient_humidity_pct",
        "paint_booth_humidity_pct",
        1,
        "POSITIVE",
        "ENVIRONMENT_TO_PAINT",
        "PAINT",
        "BASELINE_GENERATOR",
        None,
        True,
    ),

    (
        "machine_load",
        "machine_temperature_c",
        0,
        "POSITIVE",
        "LOAD_TO_THERMAL",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "ambient_temperature_c",
        "machine_temperature_c",
        0,
        "POSITIVE",
        "ENVIRONMENT_TO_THERMAL",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "machine_temperature_c",
        "vibration_mm_s",
        1,
        "POSITIVE",
        "THERMAL_TO_VIBRATION",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        True,
    ),

    (
        "machine_load",
        "vibration_mm_s",
        0,
        "POSITIVE",
        "LOAD_TO_VIBRATION",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "machine_load",
        "line_speed_units_per_hour",
        0,
        "POSITIVE",
        "LOAD_TO_LINE_SPEED",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "machine_load",
        "power_kw",
        0,
        "POSITIVE",
        "LOAD_TO_POWER",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "line_speed_units_per_hour",
        "power_kw",
        0,
        "POSITIVE",
        "SPEED_TO_POWER",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "line_speed_units_per_hour",
        "cycle_time_seconds",
        0,
        "NEGATIVE",
        "SPEED_TO_CYCLE_TIME",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "supplier_lot_quality_score",
        "defect_rate",
        0,
        "NEGATIVE",
        "SUPPLIER_TO_DEFECT",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "torque_deviation_nm",
        "defect_rate",
        0,
        "NONLINEAR",
        "TORQUE_TO_DEFECT",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "line_speed_units_per_hour",
        "defect_rate",
        0,
        "POSITIVE",
        "SPEED_TO_DEFECT",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "vibration_mm_s",
        "defect_rate",
        0,
        "POSITIVE",
        "VIBRATION_TO_DEFECT",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "maintenance_overdue_hours",
        "defect_rate",
        0,
        "POSITIVE",
        "MAINTENANCE_TO_DEFECT",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "paint_booth_humidity_pct",
        "paint_defect_rate",
        0,
        "POSITIVE",
        "PAINT_HUMIDITY_TO_DEFECT",
        "PAINT",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "line_speed_units_per_hour",
        "paint_defect_rate",
        0,
        "POSITIVE",
        "SPEED_TO_PAINT_DEFECT",
        "PAINT",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "supplier_lot_quality_score",
        "paint_defect_rate",
        0,
        "NEGATIVE",
        "SUPPLIER_TO_PAINT_DEFECT",
        "PAINT",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "defect_rate",
        "rework_rate",
        0,
        "POSITIVE",
        "DEFECT_TO_REWORK",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "paint_defect_rate",
        "rework_rate",
        0,
        "POSITIVE",
        "PAINT_DEFECT_TO_REWORK",
        "PAINT",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "machine_temperature_c",
        "downtime_minutes",
        0,
        "POSITIVE",
        "THERMAL_TO_DOWNTIME",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "vibration_mm_s",
        "downtime_minutes",
        0,
        "POSITIVE",
        "VIBRATION_TO_DOWNTIME",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "maintenance_overdue_hours",
        "downtime_minutes",
        0,
        "POSITIVE",
        "MAINTENANCE_TO_DOWNTIME",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "defect_rate",
        "quality_score",
        0,
        "NEGATIVE",
        "DEFECT_TO_QUALITY",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "rework_rate",
        "quality_score",
        0,
        "NEGATIVE",
        "REWORK_TO_QUALITY",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "supplier_lot_quality_score",
        "quality_score",
        0,
        "POSITIVE",
        "SUPPLIER_TO_QUALITY",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    # ========================================================
    # AUTOREGRESSIVE EDGES — 5
    # ========================================================

    (
        "ambient_humidity_pct",
        "ambient_humidity_pct",
        1,
        "POSITIVE",
        "AUTOREGRESSIVE",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "machine_temperature_c",
        "machine_temperature_c",
        1,
        "POSITIVE",
        "AUTOREGRESSIVE",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "vibration_mm_s",
        "vibration_mm_s",
        1,
        "POSITIVE",
        "AUTOREGRESSIVE",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "defect_rate",
        "defect_rate",
        1,
        "POSITIVE",
        "AUTOREGRESSIVE",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    (
        "rework_rate",
        "rework_rate",
        1,
        "POSITIVE",
        "AUTOREGRESSIVE",
        "ALL",
        "BASELINE_GENERATOR",
        None,
        False,
    ),

    # ========================================================
    # SCENARIO-GENERATOR LAGGED EDGES — 11
    # ========================================================

    (
        "paint_booth_humidity_pct",
        "paint_defect_rate",
        1,
        "POSITIVE",
        "SCENARIO_LAGGED",
        "PAINT",
        "SCENARIO_GENERATOR",
        "paint_humidity_spike",
        True,
    ),

    (
        "machine_temperature_c",
        "downtime_minutes",
        2,
        "POSITIVE",
        "SCENARIO_LAGGED",
        "ALL",
        "SCENARIO_GENERATOR",
        "machine_temperature_drift",
        True,
    ),

    (
        "vibration_mm_s",
        "downtime_minutes",
        1,
        "POSITIVE",
        "SCENARIO_LAGGED",
        "ALL",
        "SCENARIO_GENERATOR",
        "machine_vibration_anomaly",
        True,
    ),

    (
        "supplier_lot_quality_score",
        "defect_rate",
        1,
        "NEGATIVE",
        "SCENARIO_LAGGED",
        "SUPPLIER_LOT",
        "SCENARIO_GENERATOR",
        "supplier_quality_drop",
        True,
    ),

    (
        "supplier_lot_quality_score",
        "rework_rate",
        2,
        "NEGATIVE",
        "SCENARIO_LAGGED",
        "SUPPLIER_LOT",
        "SCENARIO_GENERATOR",
        "supplier_quality_drop",
        True,
    ),

    (
        "line_speed_units_per_hour",
        "defect_rate",
        1,
        "POSITIVE",
        "SCENARIO_LAGGED",
        "ALL",
        "SCENARIO_GENERATOR",
        "line_speed_pressure",
        True,
    ),

    (
        "line_speed_units_per_hour",
        "rework_rate",
        2,
        "POSITIVE",
        "SCENARIO_LAGGED",
        "ALL",
        "SCENARIO_GENERATOR",
        "line_speed_pressure",
        True,
    ),

    (
        "torque_deviation_nm",
        "defect_rate",
        1,
        "NONLINEAR",
        "SCENARIO_LAGGED_NONLINEAR",
        "ALL",
        "SCENARIO_GENERATOR",
        "torque_deviation",
        False,
    ),

    (
        "torque_deviation_nm",
        "rework_rate",
        2,
        "NONLINEAR",
        "SCENARIO_LAGGED_NONLINEAR",
        "ALL",
        "SCENARIO_GENERATOR",
        "torque_deviation",
        False,
    ),

    (
        "maintenance_overdue_hours",
        "vibration_mm_s",
        1,
        "POSITIVE",
        "SCENARIO_LAGGED",
        "ALL",
        "SCENARIO_GENERATOR",
        "maintenance_overdue",
        True,
    ),

    (
        "maintenance_overdue_hours",
        "downtime_minutes",
        2,
        "POSITIVE",
        "SCENARIO_LAGGED",
        "ALL",
        "SCENARIO_GENERATOR",
        "maintenance_overdue",
        True,
    ),
)


# ============================================================
# GENERATE MANUFACTURING EDGE DATAFRAME
# ============================================================


def generate_manufacturing_causal_edges() -> pd.DataFrame:
    """
    Generate the exact hidden manufacturing causal-edge
    catalogue already validated against the synthetic
    manufacturing generator.
    """

    rows: list[
        dict[str, Any]
    ] = []

    for (
        edge_number,
        definition,
    ) in enumerate(
        MANUFACTURING_EDGE_DEFINITIONS,
        start=1,
    ):

        (
            source_variable,
            target_variable,
            lag_hours,
            sign,
            relationship_type,
            scope,
            origin,
            scenario_name,
            recommended_primary_pcmci,
        ) = definition

        if edge_number <= 25:

            edge_role = "STRUCTURAL"

        elif edge_number <= 30:

            edge_role = "AUTOREGRESSIVE"

        else:

            edge_role = "STRUCTURAL"

        rows.append(
            {
                "ground_truth_edge_id":
                    f"GTEDGE_MFG_{edge_number:04d}",

                "source_variable":
                    source_variable,

                "target_variable":
                    target_variable,

                "lag_hours":
                    int(
                        lag_hours
                    ),

                "sign":
                    sign,

                "relationship_type":
                    relationship_type,

                "scope":
                    scope,

                "origin":
                    origin,

                "edge_role":
                    edge_role,

                "scenario_name":
                    scenario_name,

                "recommended_primary_pcmci":
                    bool(
                        recommended_primary_pcmci
                    ),

                "ground_truth_version":
                    MANUFACTURING_GROUND_TRUTH_VERSION,
            }
        )

    edges = pd.DataFrame(
        rows
    )

    if len(
        edges
    ) != 41:

        raise ValueError(
            "Manufacturing ground-truth edge count "
            f"must be 41, found {len(edges)}"
        )

    return edges


# ============================================================
# MANUFACTURING SCENARIO EXPECTATION TEMPLATES
# ============================================================


MANUFACTURING_SCENARIO_EXPECTATIONS: dict[
    str,
    tuple[
        tuple[
            str,
            str,
            int,
            int,
            str,
        ],
        ...,
    ],
] = {

    # ========================================================
    # PAINT HUMIDITY
    # 4 expectations × 3 events = 12
    # ========================================================

    "paint_humidity_spike": (
        (
            "paint_booth_humidity_pct",
            "UP",
            0,
            0,
            "PAINT_QUALITY_RISK",
        ),

        (
            "paint_defect_rate",
            "UP",
            1,
            1,
            "PAINT_QUALITY_RISK",
        ),

        (
            "rework_rate",
            "UP",
            2,
            2,
            "PAINT_QUALITY_RISK",
        ),

        (
            "quality_score",
            "DOWN",
            2,
            3,
            "PAINT_QUALITY_RISK",
        ),
    ),

    # ========================================================
    # MACHINE TEMPERATURE
    # 3 × 3 = 9
    # ========================================================

    "machine_temperature_drift": (
        (
            "machine_temperature_c",
            "UP",
            0,
            0,
            "EQUIPMENT_HEALTH_RISK",
        ),

        (
            "vibration_mm_s",
            "UP",
            1,
            1,
            "EQUIPMENT_HEALTH_RISK",
        ),

        (
            "downtime_minutes",
            "UP",
            2,
            2,
            "EQUIPMENT_HEALTH_RISK",
        ),
    ),

    # ========================================================
    # MACHINE VIBRATION
    # 2 × 3 = 6
    # ========================================================

    "machine_vibration_anomaly": (
        (
            "vibration_mm_s",
            "UP",
            0,
            0,
            "EQUIPMENT_HEALTH_RISK",
        ),

        (
            "downtime_minutes",
            "UP",
            1,
            1,
            "EQUIPMENT_HEALTH_RISK",
        ),
    ),

    # ========================================================
    # SUPPLIER QUALITY
    # 4 × 3 = 12
    # ========================================================

    "supplier_quality_drop": (
        (
            "supplier_lot_quality_score",
            "DOWN",
            0,
            0,
            "SUPPLIER_QUALITY_RISK",
        ),

        (
            "defect_rate",
            "UP",
            1,
            1,
            "SUPPLIER_QUALITY_RISK",
        ),

        (
            "rework_rate",
            "UP",
            2,
            2,
            "SUPPLIER_QUALITY_RISK",
        ),

        (
            "quality_score",
            "DOWN",
            2,
            3,
            "SUPPLIER_QUALITY_RISK",
        ),
    ),

    # ========================================================
    # LINE SPEED
    # 5 × 3 = 15
    # ========================================================

    "line_speed_pressure": (
        (
            "line_speed_units_per_hour",
            "UP",
            0,
            0,
            "PROCESS_QUALITY_RISK",
        ),

        (
            "cycle_time_seconds",
            "DOWN",
            0,
            1,
            "PROCESS_QUALITY_RISK",
        ),

        (
            "power_kw",
            "UP",
            0,
            1,
            "PROCESS_QUALITY_RISK",
        ),

        (
            "defect_rate",
            "UP",
            1,
            2,
            "PROCESS_QUALITY_RISK",
        ),

        (
            "rework_rate",
            "UP",
            2,
            3,
            "PROCESS_QUALITY_RISK",
        ),
    ),

    # ========================================================
    # TORQUE
    # 4 × 3 = 12
    # ========================================================

    "torque_deviation": (
        (
            "torque_deviation_nm",
            "ABS_DEVIATION_UP",
            0,
            0,
            "PROCESS_QUALITY_RISK",
        ),

        (
            "defect_rate",
            "UP",
            1,
            1,
            "PROCESS_QUALITY_RISK",
        ),

        (
            "rework_rate",
            "UP",
            2,
            2,
            "PROCESS_QUALITY_RISK",
        ),

        (
            "quality_score",
            "DOWN",
            1,
            3,
            "PROCESS_QUALITY_RISK",
        ),
    ),

    # ========================================================
    # MAINTENANCE OVERDUE
    # 4 × 3 = 12
    # ========================================================

    "maintenance_overdue": (
        (
            "maintenance_overdue_hours",
            "UP",
            0,
            0,
            "MAINTENANCE_RISK",
        ),

        (
            "machine_temperature_c",
            "UP",
            0,
            1,
            "MAINTENANCE_RISK",
        ),

        (
            "vibration_mm_s",
            "UP",
            1,
            2,
            "MAINTENANCE_RISK",
        ),

        (
            "downtime_minutes",
            "UP",
            2,
            3,
            "MAINTENANCE_RISK",
        ),
    ),

    # ========================================================
    # MAINTENANCE RECOVERY
    # 5 × 3 = 15
    # ========================================================

    "maintenance_recovery": (
        (
            "maintenance_overdue_hours",
            "DOWN",
            0,
            0,
            "RECOVERY_EXPECTED",
        ),

        (
            "hours_since_maintenance",
            "DOWN",
            0,
            1,
            "RECOVERY_EXPECTED",
        ),

        (
            "machine_temperature_c",
            "DOWN",
            0,
            1,
            "RECOVERY_EXPECTED",
        ),

        (
            "vibration_mm_s",
            "DOWN",
            0,
            2,
            "RECOVERY_EXPECTED",
        ),

        (
            "downtime_minutes",
            "DOWN",
            0,
            3,
            "RECOVERY_EXPECTED",
        ),
    ),
}


# ============================================================
# MANUFACTURING ROOT SIGNAL MAP
# ============================================================


MANUFACTURING_ROOT_SIGNAL: dict[str, str] = {
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


# ============================================================
# GENERATE MANUFACTURING EXPECTATIONS
# ============================================================


def generate_manufacturing_scenario_expectations(
    scenario_events: pd.DataFrame,
) -> pd.DataFrame:
    """
    Generate hidden expected scenario effects for every
    controlled manufacturing event.
    """

    _require_columns(
        scenario_events,
        {
            "scenario_event_id",
            "scenario_name",
        },
        "manufacturing scenario events",
    )

    rows: list[
        dict[str, Any]
    ] = []

    expectation_counter = 1

    for event in scenario_events.to_dict(
        orient="records"
    ):

        scenario_name = str(
            event[
                "scenario_name"
            ]
        )

        if (
            scenario_name
            not in
            MANUFACTURING_SCENARIO_EXPECTATIONS
        ):

            raise ValueError(
                "Unknown manufacturing scenario in "
                f"ground truth: {scenario_name}"
            )

        root_signal = (
            MANUFACTURING_ROOT_SIGNAL[
                scenario_name
            ]
        )

        for (
            target_signal,
            expected_change,
            expected_lag_hours,
            path_order,
            expected_warning,
        ) in (
            MANUFACTURING_SCENARIO_EXPECTATIONS[
                scenario_name
            ]
        ):

            rows.append(
                {
                    "expectation_id":
                        (
                            "GTEXP_MFG_"
                            f"{expectation_counter:06d}"
                        ),

                    "scenario_event_id":
                        event[
                            "scenario_event_id"
                        ],

                    "scenario_name":
                        scenario_name,

                    "true_root_signal":
                        root_signal,

                    "target_signal":
                        target_signal,

                    "expected_change":
                        expected_change,

                    "expected_lag_hours":
                        int(
                            expected_lag_hours
                        ),

                    "path_order":
                        int(
                            path_order
                        ),

                    "expected_warning":
                        expected_warning,

                    "ground_truth_version":
                        MANUFACTURING_GROUND_TRUTH_VERSION,
                }
            )

            expectation_counter += 1

    expectations = pd.DataFrame(
        rows
    )

    return expectations


# ============================================================
# VALIDATE MANUFACTURING GROUND TRUTH
# ============================================================


def validate_manufacturing_ground_truth(
    manufacturing_runtime: pd.DataFrame,
    scenario_events: pd.DataFrame,
    causal_edges: pd.DataFrame,
    scenario_expectations: pd.DataFrame,
) -> None:
    """
    Validate manufacturing hidden truth without exposing it to
    runtime observations.
    """

    _validate_runtime_leakage(
        manufacturing_runtime,
        "manufacturing runtime observations",
    )

    _validate_unique_column(
        causal_edges,
        "ground_truth_edge_id",
        "manufacturing causal edges",
    )

    _validate_unique_column(
        scenario_events,
        "scenario_event_id",
        "manufacturing scenario events",
    )

    _validate_unique_column(
        scenario_expectations,
        "expectation_id",
        "manufacturing scenario expectations",
    )

    _validate_ground_truth_signs(
        causal_edges,
        "manufacturing causal edges",
    )

    # ========================================================
    # EXACT ALREADY-VALIDATED COUNTS
    # ========================================================

    if len(
        causal_edges
    ) != 41:

        raise ValueError(
            "Manufacturing causal-edge count must be 41"
        )

    if len(
        scenario_events
    ) != 24:

        raise ValueError(
            "Manufacturing scenario-event count must be 24"
        )

    if len(
        scenario_expectations
    ) != 93:

        raise ValueError(
            "Manufacturing scenario-expectation count "
            "must be 93"
        )

    primary_edges = (
        causal_edges[
            causal_edges[
                "recommended_primary_pcmci"
            ]
        ]
    )

    if len(
        primary_edges
    ) != 11:

        raise ValueError(
            "Manufacturing primary PCMCI evaluation "
            f"edge count must be 11, found "
            f"{len(primary_edges)}"
        )

    # ========================================================
    # EXPECTATION COVERAGE
    # ========================================================

    expected_event_ids = set(
        scenario_events[
            "scenario_event_id"
        ].astype(str)
    )

    covered_event_ids = set(
        scenario_expectations[
            "scenario_event_id"
        ].astype(str)
    )

    if (
        expected_event_ids
        !=
        covered_event_ids
    ):

        missing = (
            expected_event_ids
            -
            covered_event_ids
        )

        extra = (
            covered_event_ids
            -
            expected_event_ids
        )

        raise ValueError(
            "Manufacturing scenario expectation coverage "
            "mismatch. "
            f"Missing={sorted(missing)}, "
            f"Extra={sorted(extra)}"
        )

    # ========================================================
    # SIGNALS MUST EXIST IN OBSERVABLE RUNTIME SCHEMA
    # ========================================================

    runtime_columns = set(
        manufacturing_runtime.columns
    )

    edge_variables = (
        set(
            causal_edges[
                "source_variable"
            ]
        )
        |
        set(
            causal_edges[
                "target_variable"
            ]
        )
    )

    missing_edge_variables = (
        edge_variables
        -
        runtime_columns
    )

    if missing_edge_variables:

        raise ValueError(
            "Manufacturing ground truth references "
            "variables missing from runtime observations: "
            +
            ", ".join(
                sorted(
                    missing_edge_variables
                )
            )
        )

    expectation_signals = (
        set(
            scenario_expectations[
                "true_root_signal"
            ]
        )
        |
        set(
            scenario_expectations[
                "target_signal"
            ]
        )
    )

    missing_expectation_signals = (
        expectation_signals
        -
        runtime_columns
    )

    if missing_expectation_signals:

        raise ValueError(
            "Manufacturing expectations reference signals "
            "missing from runtime observations: "
            +
            ", ".join(
                sorted(
                    missing_expectation_signals
                )
            )
        )

    # ========================================================
    # EXPECT EXACTLY THREE EVENTS PER SCENARIO
    # ========================================================

    event_counts = (
        scenario_events
        .groupby(
            "scenario_name"
        )
        .size()
    )

    for scenario_name in MANUFACTURING_SCENARIOS:

        if (
            int(
                event_counts.get(
                    scenario_name,
                    0,
                )
            )
            !=
            3
        ):

            raise ValueError(
                f"Manufacturing scenario "
                f"{scenario_name} does not have "
                "exactly three events"
            )


# ============================================================
# PUBLIC MANUFACTURING GROUND-TRUTH API
# ============================================================


def generate_manufacturing_causal_ground_truth(
    manufacturing_runtime: pd.DataFrame,
    scenario_events: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Returns:

        manufacturing_causal_edges
        manufacturing_scenario_events
        manufacturing_scenario_expectations
    """

    causal_edges = (
        generate_manufacturing_causal_edges()
    )

    scenario_expectations = (
        generate_manufacturing_scenario_expectations(
            scenario_events
        )
    )

    scenario_events_output = (
        scenario_events
        .copy(
            deep=True
        )
    )

    validate_manufacturing_ground_truth(
        manufacturing_runtime=
            manufacturing_runtime,

        scenario_events=
            scenario_events_output,

        causal_edges=
            causal_edges,

        scenario_expectations=
            scenario_expectations,
    )

    return (
        causal_edges,
        scenario_events_output,
        scenario_expectations,
    )


# ============================================================
# ============================================================
#
# MOBILITY CAUSAL GROUND TRUTH
#
# ============================================================
# ============================================================


# ============================================================
# MOBILITY EDGE DEFINITIONS
#
# IMPORTANT:
#
# These relationships come from the actual controlled effects
# implemented in scenarios.py.
#
# We do NOT add prototype UI edges.
#
# We do NOT add Campaign Spend, Lead Quality, etc. simply
# because they once existed in the frontend mock.
# ============================================================


MOBILITY_EDGE_DEFINITIONS: tuple[
    tuple[
        str,
        str,
        int,
        str,
        str,
        str,
    ],
    ...,
] = (

    # ========================================================
    # DEALER FOLLOW-UP DETERIORATION
    # ========================================================

    (
        "followup_completed_count",
        "customer_response_count",
        1,
        "POSITIVE",
        "DEALER_EXECUTION_TO_RESPONSE",
        "dealer_followup_deterioration",
    ),

    (
        "followup_completed_count",
        "test_drive_completed_count",
        2,
        "POSITIVE",
        "DEALER_EXECUTION_TO_TEST_DRIVE",
        "dealer_followup_deterioration",
    ),

    (
        "followup_completed_count",
        "booking_count",
        3,
        "POSITIVE",
        "DEALER_EXECUTION_TO_BOOKING",
        "dealer_followup_deterioration",
    ),

    (
        "followup_completed_count",
        "avg_followup_response_minutes",
        1,
        "NEGATIVE",
        "DEALER_EXECUTION_TO_RESPONSE_TIME",
        "dealer_followup_deterioration",
    ),

    # ========================================================
    # FINANCE APPROVAL SLOWDOWN
    # ========================================================

    (
        "avg_finance_approval_tat_hours",
        "finance_approved_count",
        0,
        "NEGATIVE",
        "FINANCE_TAT_TO_APPROVAL",
        "finance_approval_slowdown",
    ),

    (
        "avg_finance_approval_tat_hours",
        "finance_manual_review_count",
        0,
        "POSITIVE",
        "FINANCE_TAT_TO_MANUAL_REVIEW",
        "finance_approval_slowdown",
    ),

    (
        "avg_finance_approval_tat_hours",
        "cancellation_count",
        2,
        "POSITIVE",
        "FINANCE_TAT_TO_CANCELLATION",
        "finance_approval_slowdown",
    ),

    # ========================================================
    # ALLOCATION CONSTRAINT
    # ========================================================

    (
        "allocated_vehicle_count",
        "waitlisted_booking_count",
        0,
        "NEGATIVE",
        "ALLOCATION_TO_WAITLIST",
        "allocation_constraint",
    ),

    (
        "allocated_vehicle_count",
        "avg_allocation_wait_hours",
        0,
        "NEGATIVE",
        "ALLOCATION_TO_WAIT_TIME",
        "allocation_constraint",
    ),

    (
        "allocated_vehicle_count",
        "delivered_vehicle_count",
        2,
        "POSITIVE",
        "ALLOCATION_TO_DELIVERY",
        "allocation_constraint",
    ),

    (
        "allocated_vehicle_count",
        "avg_delivery_delay_days",
        2,
        "NEGATIVE",
        "ALLOCATION_TO_DELIVERY_DELAY",
        "allocation_constraint",
    ),

    # ========================================================
    # DELIVERY DELAY SPIKE
    # ========================================================

    (
        "delayed_delivery_count",
        "avg_delivery_delay_days",
        0,
        "POSITIVE",
        "DELIVERY_DELAY_COUNT_TO_DURATION",
        "delivery_delay_spike",
    ),
)


# ============================================================
# GENERATE MOBILITY EDGE DATAFRAME
# ============================================================


def generate_mobility_causal_edges() -> pd.DataFrame:
    """
    Generate hidden Mobility causal relationships produced by
    the controlled Mobility scenario engine.

    Lag interpretation:

        lag_windows = 1
            =
        12 hours
    """

    rows: list[
        dict[str, Any]
    ] = []

    primary_variables = set(
        MOBILITY_PCMCI_PRIMARY_VARIABLES
    )

    for (
        edge_number,
        definition,
    ) in enumerate(
        MOBILITY_EDGE_DEFINITIONS,
        start=1,
    ):

        (
            source_variable,
            target_variable,
            lag_windows,
            sign,
            relationship_type,
            scenario_name,
        ) = definition

        # Only recommend primary-PCMCI evaluation when:
        #
        # 1. relationship is actually lagged
        # 2. source is in explicit primary allowlist
        # 3. target is in explicit primary allowlist

        recommended_primary_pcmci = (
            lag_windows
            >
            0
            and
            source_variable
            in
            primary_variables
            and
            target_variable
            in
            primary_variables
        )

        rows.append(
            {
                "ground_truth_edge_id":
                    f"GTEDGE_MOB_{edge_number:04d}",

                "source_variable":
                    source_variable,

                "target_variable":
                    target_variable,

                "lag_windows":
                    int(
                        lag_windows
                    ),

                "lag_hours":
                    int(
                        lag_windows
                        *
                        12
                    ),

                "sign":
                    sign,

                "relationship_type":
                    relationship_type,

                "scope":
                    "REGION",

                "origin":
                    "SCENARIO_GENERATOR",

                "edge_role":
                    "STRUCTURAL",

                "scenario_name":
                    scenario_name,

                "recommended_primary_pcmci":
                    bool(
                        recommended_primary_pcmci
                    ),

                "ground_truth_version":
                    MOBILITY_GROUND_TRUTH_VERSION,
            }
        )

    edges = pd.DataFrame(
        rows
    )

    if len(
        edges
    ) != 12:

        raise ValueError(
            "Mobility ground-truth edge count must be 12"
        )

    return edges


# ============================================================
# MOBILITY ROOT SIGNALS
# ============================================================


MOBILITY_ROOT_SIGNAL: dict[str, str] = {

    "dealer_followup_deterioration":
        "followup_completed_count",

    "finance_approval_slowdown":
        "avg_finance_approval_tat_hours",

    "allocation_constraint":
        "allocated_vehicle_count",

    "delivery_delay_spike":
        "delayed_delivery_count",
}


# ============================================================
# MOBILITY SCENARIO EXPECTATION TEMPLATES
#
# Total:
#
# dealer      5 × 3 = 15
# finance     4 × 3 = 12
# allocation  5 × 3 = 15
# delivery    2 × 3 =  6
#
# TOTAL = 48
# ============================================================


MOBILITY_SCENARIO_EXPECTATIONS: dict[
    str,
    tuple[
        tuple[
            str,
            str,
            int,
            int,
            str,
        ],
        ...,
    ],
] = {

    # ========================================================
    # DEALER FOLLOW-UP DETERIORATION
    # ========================================================

    "dealer_followup_deterioration": (
        (
            "followup_completed_count",
            "DOWN",
            0,
            0,
            "DEALER_EXECUTION_RISK",
        ),

        (
            "customer_response_count",
            "DOWN",
            1,
            1,
            "DEALER_EXECUTION_RISK",
        ),

        (
            "avg_followup_response_minutes",
            "UP",
            1,
            1,
            "DEALER_EXECUTION_RISK",
        ),

        (
            "test_drive_completed_count",
            "DOWN",
            2,
            2,
            "DEALER_EXECUTION_RISK",
        ),

        (
            "booking_count",
            "DOWN",
            3,
            3,
            "DEALER_EXECUTION_RISK",
        ),
    ),

    # ========================================================
    # FINANCE APPROVAL SLOWDOWN
    # ========================================================

    "finance_approval_slowdown": (
        (
            "avg_finance_approval_tat_hours",
            "UP",
            0,
            0,
            "FINANCE_APPROVAL_RISK",
        ),

        (
            "finance_approved_count",
            "DOWN",
            0,
            1,
            "FINANCE_APPROVAL_RISK",
        ),

        (
            "finance_manual_review_count",
            "UP",
            0,
            1,
            "FINANCE_APPROVAL_RISK",
        ),

        (
            "cancellation_count",
            "UP",
            2,
            2,
            "FINANCE_APPROVAL_RISK",
        ),
    ),

    # ========================================================
    # ALLOCATION CONSTRAINT
    # ========================================================

    "allocation_constraint": (
        (
            "allocated_vehicle_count",
            "DOWN",
            0,
            0,
            "ALLOCATION_SUPPLY_RISK",
        ),

        (
            "waitlisted_booking_count",
            "UP",
            0,
            1,
            "ALLOCATION_SUPPLY_RISK",
        ),

        (
            "avg_allocation_wait_hours",
            "UP",
            0,
            1,
            "ALLOCATION_SUPPLY_RISK",
        ),

        (
            "delivered_vehicle_count",
            "DOWN",
            2,
            2,
            "ALLOCATION_SUPPLY_RISK",
        ),

        (
            "avg_delivery_delay_days",
            "UP",
            2,
            2,
            "ALLOCATION_SUPPLY_RISK",
        ),
    ),

    # ========================================================
    # DELIVERY DELAY SPIKE
    # ========================================================

    "delivery_delay_spike": (
        (
            "delayed_delivery_count",
            "UP",
            0,
            0,
            "DELIVERY_DELAY_RISK",
        ),

        (
            "avg_delivery_delay_days",
            "UP",
            0,
            1,
            "DELIVERY_DELAY_RISK",
        ),
    ),
}


# ============================================================
# GENERATE MOBILITY SCENARIO EXPECTATIONS
# ============================================================


def generate_mobility_scenario_expectations(
    scenario_events: pd.DataFrame,
) -> pd.DataFrame:
    """
    Generate hidden expected effects for every Mobility
    controlled scenario.

    expected_lag_windows:
        PCMCI observation lag.

    expected_lag_hours:
        human-readable time interpretation.

    1 Mobility window = 12 hours.
    """

    _require_columns(
        scenario_events,
        {
            "scenario_event_id",
            "scenario_name",
            "region_id",
            "region_name",
        },
        "Mobility scenario events",
    )

    rows: list[
        dict[str, Any]
    ] = []

    expectation_counter = 1

    for event in scenario_events.to_dict(
        orient="records"
    ):

        scenario_name = str(
            event[
                "scenario_name"
            ]
        )

        if (
            scenario_name
            not in
            MOBILITY_SCENARIO_EXPECTATIONS
        ):

            raise ValueError(
                "Unknown Mobility scenario in "
                f"ground truth: {scenario_name}"
            )

        root_signal = (
            MOBILITY_ROOT_SIGNAL[
                scenario_name
            ]
        )

        for (
            target_signal,
            expected_change,
            expected_lag_windows,
            path_order,
            expected_warning,
        ) in (
            MOBILITY_SCENARIO_EXPECTATIONS[
                scenario_name
            ]
        ):

            rows.append(
                {
                    "expectation_id":
                        (
                            "GTEXP_MOB_"
                            f"{expectation_counter:06d}"
                        ),

                    "scenario_event_id":
                        event[
                            "scenario_event_id"
                        ],

                    "scenario_name":
                        scenario_name,

                    "region_id":
                        str(
                            event[
                                "region_id"
                            ]
                        ),

                    "region_name":
                        str(
                            event[
                                "region_name"
                            ]
                        ),

                    "true_root_signal":
                        root_signal,

                    "target_signal":
                        target_signal,

                    "expected_change":
                        expected_change,

                    "expected_lag_windows":
                        int(
                            expected_lag_windows
                        ),

                    "expected_lag_hours":
                        int(
                            expected_lag_windows
                            *
                            12
                        ),

                    "path_order":
                        int(
                            path_order
                        ),

                    "expected_warning":
                        expected_warning,

                    "ground_truth_version":
                        MOBILITY_GROUND_TRUTH_VERSION,
                }
            )

            expectation_counter += 1

    return pd.DataFrame(
        rows
    )


# ============================================================
# VALIDATE MOBILITY GROUND TRUTH
# ============================================================


def validate_mobility_ground_truth(
    mobility_runtime: pd.DataFrame,
    scenario_events: pd.DataFrame,
    causal_edges: pd.DataFrame,
    scenario_expectations: pd.DataFrame,
) -> None:
    """
    Validate hidden Mobility truth while preserving strict
    runtime separation.
    """

    _validate_runtime_leakage(
        mobility_runtime,
        "Mobility runtime observations",
    )

    _validate_unique_column(
        causal_edges,
        "ground_truth_edge_id",
        "Mobility causal edges",
    )

    _validate_unique_column(
        scenario_events,
        "scenario_event_id",
        "Mobility scenario events",
    )

    _validate_unique_column(
        scenario_expectations,
        "expectation_id",
        "Mobility scenario expectations",
    )

    _validate_ground_truth_signs(
        causal_edges,
        "Mobility causal edges",
    )

    # ========================================================
    # CURRENT CONTROLLED-SCENARIO COUNTS
    # ========================================================

    if len(
        causal_edges
    ) != 12:

        raise ValueError(
            "Mobility causal-edge count must be 12"
        )

    if len(
        scenario_events
    ) != 12:

        raise ValueError(
            "Mobility scenario-event count must be 12"
        )

    if len(
        scenario_expectations
    ) != 48:

        raise ValueError(
            "Mobility scenario-expectation count must "
            f"be 48, found {len(scenario_expectations)}"
        )

    # ========================================================
    # PRIMARY PCMCI EVALUATION
    #
    # Current primary allowlist gives three directly
    # evaluation-ready scenario edges:
    #
    # followup_completed -> test_drive
    # followup_completed -> booking
    # allocated -> delivered
    #
    # Other hidden relationships remain valid evaluation truth
    # but use auxiliary observables or lag 0.
    # ========================================================

    primary_edges = (
        causal_edges[
            causal_edges[
                "recommended_primary_pcmci"
            ]
        ]
    )

    if len(
        primary_edges
    ) != 3:

        raise ValueError(
            "Mobility primary PCMCI evaluation edge "
            f"count must be 3, found "
            f"{len(primary_edges)}"
        )

    # ========================================================
    # ALL EDGE VARIABLES MUST BE OBSERVABLE
    # ========================================================

    runtime_columns = set(
        mobility_runtime.columns
    )

    edge_variables = (
        set(
            causal_edges[
                "source_variable"
            ]
        )
        |
        set(
            causal_edges[
                "target_variable"
            ]
        )
    )

    missing_edge_variables = (
        edge_variables
        -
        runtime_columns
    )

    if missing_edge_variables:

        raise ValueError(
            "Mobility ground truth references variables "
            "missing from runtime observations: "
            +
            ", ".join(
                sorted(
                    missing_edge_variables
                )
            )
        )

    # ========================================================
    # ALL EXPECTATION SIGNALS MUST BE OBSERVABLE
    # ========================================================

    expectation_signals = (
        set(
            scenario_expectations[
                "true_root_signal"
            ]
        )
        |
        set(
            scenario_expectations[
                "target_signal"
            ]
        )
    )

    missing_expectation_signals = (
        expectation_signals
        -
        runtime_columns
    )

    if missing_expectation_signals:

        raise ValueError(
            "Mobility expectations reference signals "
            "missing from runtime observations: "
            +
            ", ".join(
                sorted(
                    missing_expectation_signals
                )
            )
        )

    # ========================================================
    # EXPECTATION COVERAGE
    # ========================================================

    expected_event_ids = set(
        scenario_events[
            "scenario_event_id"
        ].astype(str)
    )

    covered_event_ids = set(
        scenario_expectations[
            "scenario_event_id"
        ].astype(str)
    )

    if (
        expected_event_ids
        !=
        covered_event_ids
    ):

        missing = (
            expected_event_ids
            -
            covered_event_ids
        )

        extra = (
            covered_event_ids
            -
            expected_event_ids
        )

        raise ValueError(
            "Mobility scenario expectation coverage "
            "mismatch. "
            f"Missing={sorted(missing)}, "
            f"Extra={sorted(extra)}"
        )

    # ========================================================
    # THREE EVENTS PER SCENARIO
    # ========================================================

    event_counts = (
        scenario_events
        .groupby(
            "scenario_name"
        )
        .size()
    )

    for scenario_name in MOBILITY_SCENARIOS:

        actual_count = int(
            event_counts.get(
                scenario_name,
                0,
            )
        )

        if actual_count != 3:

            raise ValueError(
                f"Mobility scenario {scenario_name} "
                f"expected 3 events, found {actual_count}"
            )

    # ========================================================
    # PRIMARY PCMCI EDGES MUST ACTUALLY BE LAGGED
    # ========================================================

    if (
        primary_edges[
            "lag_windows"
        ]
        <=
        0
    ).any():

        raise ValueError(
            "Mobility primary PCMCI ground-truth edges "
            "must have lag_windows > 0"
        )


# ============================================================
# PUBLIC MOBILITY GROUND-TRUTH API
# ============================================================


def generate_mobility_causal_ground_truth(
    mobility_runtime: pd.DataFrame,
    scenario_events: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Returns:

        mobility_causal_edges
        mobility_scenario_events
        mobility_scenario_expectations
    """

    causal_edges = (
        generate_mobility_causal_edges()
    )

    scenario_expectations = (
        generate_mobility_scenario_expectations(
            scenario_events
        )
    )

    scenario_events_output = (
        scenario_events
        .copy(
            deep=True
        )
    )

    validate_mobility_ground_truth(
        mobility_runtime=
            mobility_runtime,

        scenario_events=
            scenario_events_output,

        causal_edges=
            causal_edges,

        scenario_expectations=
            scenario_expectations,
    )

    return (
        causal_edges,
        scenario_events_output,
        scenario_expectations,
    )


# ============================================================
# ============================================================
#
# COMBINED CAUSAL GROUND-TRUTH API
#
# ============================================================
# ============================================================


def generate_all_causal_ground_truth(
    manufacturing_runtime: pd.DataFrame,
    manufacturing_scenario_events: pd.DataFrame,
    mobility_runtime: pd.DataFrame,
    mobility_scenario_events: pd.DataFrame,
) -> dict[
    str,
    pd.DataFrame,
]:
    """
    Convenience API for generate_all.py.

    No files are written here.

    Returned keys correspond to the files that export_csv.py
    can later place under:

        data/ground_truth/causal/
    """

    (
        manufacturing_edges,
        manufacturing_events,
        manufacturing_expectations,
    ) = (
        generate_manufacturing_causal_ground_truth(
            manufacturing_runtime=
                manufacturing_runtime,

            scenario_events=
                manufacturing_scenario_events,
        )
    )

    (
        mobility_edges,
        mobility_events,
        mobility_expectations,
    ) = (
        generate_mobility_causal_ground_truth(
            mobility_runtime=
                mobility_runtime,

            scenario_events=
                mobility_scenario_events,
        )
    )

    return {
        "manufacturing_causal_edges":
            manufacturing_edges,

        "manufacturing_scenario_events":
            manufacturing_events,

        "manufacturing_scenario_expectations":
            manufacturing_expectations,

        "mobility_causal_edges":
            mobility_edges,

        "mobility_scenario_events":
            mobility_events,

        "mobility_scenario_expectations":
            mobility_expectations,
    }


# ============================================================
# ============================================================
#
# LOCAL INTEGRATION HELPER
#
# ============================================================
# ============================================================


def _invoke_generator_for_local_test(
    function: Callable[..., Any],
    available_inputs: Mapping[str, Any],
) -> Any:
    """
    Invoke an existing generator using its actual Python
    signature.

    Used only for this file's integration test.

    This prevents ground_truth.py from modifying or imposing
    incorrect signatures on already-working Auto generators.
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
                "is unavailable in ground_truth.py local "
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
    # CAUSAL TIME-SERIES GENERATORS
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
    # AUTO COMMERCIAL JOURNEY
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
    # SUPPLIER
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

        # MASTER

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

        # AUTO

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

        # SUPPLY

        "suppliers":
            suppliers_df,

        "supplier_lots":
            supplier_lots_df,

        "production_batches":
            production_batches_df,

        # ALLOCATION

        "allocations":
            allocations_df,
    }

    # ========================================================
    # DELIVERY
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
    # MANUFACTURING CONTROLLED SCENARIOS
    # ========================================================

    (
        manufacturing_runtime_df,
        manufacturing_scenario_events_df,
    ) = (
        generate_and_apply_manufacturing_scenarios(
            manufacturing_timeseries=
                manufacturing_baseline_df
        )
    )

    # ========================================================
    # MANUFACTURING GROUND TRUTH
    # ========================================================

    (
        manufacturing_edges_df,
        manufacturing_events_truth_df,
        manufacturing_expectations_df,
    ) = (
        generate_manufacturing_causal_ground_truth(
            manufacturing_runtime=
                manufacturing_runtime_df,

            scenario_events=
                manufacturing_scenario_events_df,
        )
    )

    # ========================================================
    # MANUFACTURING SUMMARY
    # ========================================================

    print(
        "\n=== MANUFACTURING CAUSAL "
        "GROUND-TRUTH CHECK ===\n"
    )

    print(
        "Runtime manufacturing rows:",
        len(
            manufacturing_runtime_df
        ),
    )

    print(
        "Scenario events:",
        len(
            manufacturing_events_truth_df
        ),
    )

    print(
        "Ground-truth causal edges:",
        len(
            manufacturing_edges_df
        ),
    )

    print(
        "Scenario expectation rows:",
        len(
            manufacturing_expectations_df
        ),
    )

    # ========================================================
    # MANUFACTURING EDGE TYPES
    # ========================================================

    print(
        "\n=== GROUND-TRUTH EDGE TYPES ===\n"
    )

    manufacturing_edge_types = (
        manufacturing_edges_df
        .groupby(
            [
                "origin",
                "edge_role",
            ],
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "edge_count"
            }
        )
    )

    print(
        manufacturing_edge_types
        .to_string(
            index=False
        )
    )

    # ========================================================
    # MANUFACTURING PRIMARY PCMCI EDGES
    # ========================================================

    manufacturing_primary_edges = (
        manufacturing_edges_df[
            manufacturing_edges_df[
                "recommended_primary_pcmci"
            ]
        ]
        .copy()
    )

    print(
        "\n=== PRIMARY PCMCI EVALUATION EDGES ===\n"
    )

    print(
        manufacturing_primary_edges[
            [
                "ground_truth_edge_id",
                "source_variable",
                "target_variable",
                "lag_hours",
                "sign",
                "scope",
                "origin",
            ]
        ]
        .to_string(
            index=False
        )
    )

    print(
        "\nPrimary PCMCI evaluation edge count:",
        len(
            manufacturing_primary_edges
        ),
    )

    # ========================================================
    # MANUFACTURING EXPECTATION COUNTS
    # ========================================================

    print(
        "\n=== SCENARIO EXPECTATION COUNTS ===\n"
    )

    manufacturing_expectation_counts = (
        manufacturing_expectations_df
        .groupby(
            "scenario_name"
        )
        .size()
        .reset_index(
            name=
                "expectation_count"
        )
    )

    print(
        manufacturing_expectation_counts
        .to_string(
            index=False
        )
    )

    manufacturing_events_covered = (
        manufacturing_expectations_df[
            "scenario_event_id"
        ]
        .nunique()
    )

    print(
        "\nScenario events covered:",
        manufacturing_events_covered,
        "/",
        len(
            manufacturing_events_truth_df
        ),
    )

    # ========================================================
    # MANUFACTURING EDGE SAMPLE
    # ========================================================

    print(
        "\n=== CAUSAL EDGE GROUND-TRUTH SAMPLE ===\n"
    )

    print(
        manufacturing_edges_df[
            [
                "ground_truth_edge_id",
                "source_variable",
                "target_variable",
                "lag_hours",
                "sign",
                "relationship_type",
                "scope",
                "origin",
                "scenario_name",
                "recommended_primary_pcmci",
            ]
        ]
        .to_string(
            index=False
        )
    )

    # ========================================================
    # MANUFACTURING EXPECTATION SAMPLE
    # ========================================================

    print(
        "\n=== SCENARIO EXPECTATION SAMPLE ===\n"
    )

    print(
        manufacturing_expectations_df[
            [
                "expectation_id",
                "scenario_event_id",
                "scenario_name",
                "true_root_signal",
                "target_signal",
                "expected_change",
                "expected_lag_hours",
                "path_order",
                "expected_warning",
            ]
        ]
        .head(
            40
        )
        .to_string(
            index=False
        )
    )

    manufacturing_leaked = (
        FORBIDDEN_RUNTIME_COLUMNS
        &
        set(
            manufacturing_runtime_df.columns
        )
    )

    print(
        "\n=== MANUFACTURING RUNTIME "
        "GROUND-TRUTH LEAKAGE CHECK ===\n"
    )

    print(
        "Leaked columns:",
        sorted(
            manufacturing_leaked
        ),
    )

    print(
        "\nManufacturing causal ground truth "
        "generated and validated successfully."
    )

    # ========================================================
    # ========================================================
    #
    # MOBILITY BASELINE
    #
    # ========================================================
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
    # MOBILITY CONTROLLED SCENARIOS
    # ========================================================

    (
        mobility_runtime_df,
        mobility_scenario_events_df,
    ) = (
        generate_and_apply_mobility_scenarios(
            mobility_timeseries=
                mobility_baseline_df
        )
    )

    # ========================================================
    # MOBILITY GROUND TRUTH
    # ========================================================

    (
        mobility_edges_df,
        mobility_events_truth_df,
        mobility_expectations_df,
    ) = (
        generate_mobility_causal_ground_truth(
            mobility_runtime=
                mobility_runtime_df,

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
        "=== MOBILITY CAUSAL GROUND-TRUTH CHECK ==="
    )

    print(
        "============================================\n"
    )

    print(
        "Runtime mobility rows:",
        len(
            mobility_runtime_df
        ),
    )

    print(
        "Regions:",
        mobility_runtime_df[
            "region_id"
        ].nunique(),
    )

    print(
        "Scenario events:",
        len(
            mobility_events_truth_df
        ),
    )

    print(
        "Ground-truth causal edges:",
        len(
            mobility_edges_df
        ),
    )

    print(
        "Scenario expectation rows:",
        len(
            mobility_expectations_df
        ),
    )

    # ========================================================
    # MOBILITY EDGE TYPES
    # ========================================================

    print(
        "\n=== MOBILITY GROUND-TRUTH EDGE TYPES ===\n"
    )

    mobility_edge_types = (
        mobility_edges_df
        .groupby(
            [
                "origin",
                "edge_role",
            ],
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "edge_count"
            }
        )
    )

    print(
        mobility_edge_types
        .to_string(
            index=False
        )
    )

    # ========================================================
    # MOBILITY PRIMARY PCMCI EDGES
    # ========================================================

    mobility_primary_edges = (
        mobility_edges_df[
            mobility_edges_df[
                "recommended_primary_pcmci"
            ]
        ]
        .copy()
    )

    print(
        "\n=== MOBILITY PRIMARY PCMCI "
        "EVALUATION EDGES ===\n"
    )

    print(
        mobility_primary_edges[
            [
                "ground_truth_edge_id",
                "source_variable",
                "target_variable",
                "lag_windows",
                "lag_hours",
                "sign",
                "scope",
                "origin",
            ]
        ]
        .to_string(
            index=False
        )
    )

    print(
        "\nMobility primary PCMCI evaluation "
        "edge count:",
        len(
            mobility_primary_edges
        ),
    )

    # ========================================================
    # MOBILITY SCENARIO COUNTS
    # ========================================================

    print(
        "\n=== MOBILITY SCENARIO EVENT COUNTS ===\n"
    )

    print(
        mobility_events_truth_df
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
    # MOBILITY EXPECTATION COUNTS
    # ========================================================

    print(
        "\n=== MOBILITY SCENARIO "
        "EXPECTATION COUNTS ===\n"
    )

    mobility_expectation_counts = (
        mobility_expectations_df
        .groupby(
            "scenario_name"
        )
        .size()
        .reset_index(
            name=
                "expectation_count"
        )
    )

    print(
        mobility_expectation_counts
        .to_string(
            index=False
        )
    )

    mobility_events_covered = (
        mobility_expectations_df[
            "scenario_event_id"
        ]
        .nunique()
    )

    print(
        "\nMobility scenario events covered:",
        mobility_events_covered,
        "/",
        len(
            mobility_events_truth_df
        ),
    )

    # ========================================================
    # MOBILITY EDGE SAMPLE
    # ========================================================

    print(
        "\n=== MOBILITY CAUSAL EDGE "
        "GROUND-TRUTH SAMPLE ===\n"
    )

    print(
        mobility_edges_df[
            [
                "ground_truth_edge_id",
                "source_variable",
                "target_variable",
                "lag_windows",
                "lag_hours",
                "sign",
                "relationship_type",
                "scenario_name",
                "recommended_primary_pcmci",
            ]
        ]
        .to_string(
            index=False
        )
    )

    # ========================================================
    # MOBILITY EXPECTATION SAMPLE
    # ========================================================

    print(
        "\n=== MOBILITY SCENARIO "
        "EXPECTATION SAMPLE ===\n"
    )

    print(
        mobility_expectations_df[
            [
                "expectation_id",
                "scenario_event_id",
                "scenario_name",
                "region_name",
                "true_root_signal",
                "target_signal",
                "expected_change",
                "expected_lag_windows",
                "expected_lag_hours",
                "path_order",
                "expected_warning",
            ]
        ]
        .head(
            60
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # MOBILITY RUNTIME LEAKAGE
    # ========================================================

    mobility_leaked = (
        FORBIDDEN_RUNTIME_COLUMNS
        &
        set(
            mobility_runtime_df.columns
        )
    )

    print(
        "\n=== MOBILITY RUNTIME "
        "GROUND-TRUTH LEAKAGE CHECK ===\n"
    )

    print(
        "Leaked columns:",
        sorted(
            mobility_leaked
        ),
    )

    print(
        "\nMobility causal ground truth "
        "generated and validated successfully."
    )

    # ========================================================
    # SUPPLIER CONSISTENCY — FINAL RECHECK
    # ========================================================

    inconsistent_supplier_pairs = (
        count_inconsistent_supplier_lot_timestamp_pairs(
            manufacturing_runtime_df
        )
    )

    # ========================================================
    # FINAL STATUS
    # ========================================================

    print(
        "\n\n============================================"
    )

    print(
        "=== FINAL CAUSAL GROUND-TRUTH STATUS ==="
    )

    print(
        "============================================\n"
    )

    print(
        "Manufacturing runtime rows:",
        len(
            manufacturing_runtime_df
        ),
    )

    print(
        "Manufacturing edges:",
        len(
            manufacturing_edges_df
        ),
    )

    print(
        "Manufacturing primary PCMCI edges:",
        len(
            manufacturing_primary_edges
        ),
    )

    print(
        "Manufacturing scenario events covered:",
        manufacturing_events_covered,
        "/",
        len(
            manufacturing_events_truth_df
        ),
    )

    print()

    print(
        "Mobility runtime rows:",
        len(
            mobility_runtime_df
        ),
    )

    print(
        "Mobility edges:",
        len(
            mobility_edges_df
        ),
    )

    print(
        "Mobility primary PCMCI edges:",
        len(
            mobility_primary_edges
        ),
    )

    print(
        "Mobility scenario events covered:",
        mobility_events_covered,
        "/",
        len(
            mobility_events_truth_df
        ),
    )

    print()

    print(
        "Supplier inconsistencies:",
        inconsistent_supplier_pairs,
    )

    print(
        "Manufacturing runtime leakage:",
        sorted(
            manufacturing_leaked
        ),
    )

    print(
        "Mobility runtime leakage:",
        sorted(
            mobility_leaked
        ),
    )

    print(
        "\nManufacturing and Mobility causal "
        "ground truth generated and validated "
        "successfully."
    )