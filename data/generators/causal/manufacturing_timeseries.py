"""
Synthetic Manufacturing Time-Series Generator
for Mahindra AI Nexus.

Purpose
-------
Generate minute-level historical manufacturing observations that can
later be used by Tigramite PCMCI for causal discovery and
early-warning analysis.

This is NOT the causal graph itself.

Flow:

Plants
    ↓
Production Lines
    ↓
Machines
    ↓
Production Batches / Supplier Quality
    ↓
Hourly Manufacturing Signals
    ↓
PCMCI
    ↓
Filtered Causal Graph
    ↓
Early Warning / Root Cause Explanation


Important design rule
---------------------

The output contains only observable manufacturing evidence.

It DOES NOT expose:

    anomaly labels
    scenario labels
    true causal coefficients
    generator causal edges
    root-cause labels

Those belong later in:

    data/ground_truth/causal/

and must not be given to PCMCI.


Main signals
------------

Context columns:

    timestamp
    plant_id
    production_line_id
    machine_id
    production_batch_id
    supplier_lot_id

PCMCI candidate signals:

    ambient_temperature_c
    ambient_humidity_pct

    machine_load
    machine_temperature_c
    vibration_mm_s
    power_kw

    line_speed_units_per_hour
    cycle_time_seconds

    hours_since_maintenance
    maintenance_overdue_hours

    supplier_lot_quality_score

    torque_deviation_nm

    defect_rate
    rework_rate

    downtime_minutes

    quality_score


Paint-line additional signals:

    paint_booth_temperature_c
    paint_booth_humidity_pct
    paint_defect_rate


This module DOES NOT write CSV files.

Later generate_all.py will save:

    data/synthetic/causal/manufacturing_timeseries.csv


All generated values are synthetic PoC data and are not real
Mahindra manufacturing measurements.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

import math

import numpy as np
import pandas as pd

from data.generators.common.helpers import (
    load_generation_config,
    load_distribution_config,
)

from data.generators.common.seed import (
    derive_seed,
    make_rng,
)


# ============================================================
# SYNTHETIC PROCESS ASSUMPTIONS
# ============================================================

MIN_PCMCI_CONTEXT_OBSERVATIONS = 2000


# ============================================================
# MAINTENANCE
#
# Synthetic preventive-maintenance cycle.
# ============================================================

BASE_MAINTENANCE_INTERVAL_HOURS = 14 * 24

MAINTENANCE_INTERVAL_JITTER_HOURS = 48


# ============================================================
# NATURAL OPERATIONAL ANOMALIES
#
# These are intentionally NOT output as labels.
#
# They only perturb the observable measurements.
# ============================================================

MIN_ANOMALY_WINDOW_HOURS = 12
MAX_ANOMALY_WINDOW_HOURS = 42

ANOMALY_WINDOW_GAP_MIN_HOURS = 650
ANOMALY_WINDOW_GAP_MAX_HOURS = 1100


# ============================================================
# OUTPUT LIMITS
# ============================================================

MAX_DEFECT_RATE = 0.22
MAX_REWORK_RATE = 0.25
MAX_DOWNTIME_MINUTES = 1.0


# ============================================================
# COLUMN HELPER
# ============================================================


def _find_column(
    dataframe: pd.DataFrame,
    candidates: Sequence[str],
    dataset_name: str,
    logical_name: str,
) -> str:
    """
    Resolve a required upstream column from accepted names.
    """

    for candidate in candidates:

        if candidate in dataframe.columns:

            return candidate

    raise ValueError(
        f"{dataset_name} is missing the column "
        f"required for {logical_name}. "
        "Expected one of: "
        + ", ".join(
            candidates
        )
    )


# ============================================================
# TIME WINDOW
# ============================================================


def _get_generation_window(
    generation: Mapping[str, Any],
) -> tuple[
    pd.Timestamp,
    pd.Timestamp,
    str,
]:
    """
    Read generation start/end/timezone.
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
            "Missing generation time configuration"
        )

    start_value = time_config.get(
        "start",
        time_config.get(
            "start_date"
        ),
    )

    end_value = time_config.get(
        "end",
        time_config.get(
            "end_date"
        ),
    )

    if start_value is None:

        raise KeyError(
            "Missing generation start/start_date"
        )

    if end_value is None:

        raise KeyError(
            "Missing generation end/end_date"
        )

    timezone = str(
        time_config.get(
            "timezone",
            "Asia/Kolkata",
        )
    )

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
            "Generation end must be later "
            "than generation start"
        )

    return (
        start,
        end,
        timezone,
    )


# ============================================================
# CONFIG VALUE HELPERS
# ============================================================


def _normal_config(
    config: Mapping[str, Any],
    default_mean: float,
    default_std: float,
    default_min: float,
    default_max: float,
) -> tuple[
    float,
    float,
    float,
    float,
]:
    """
    Read a normal-distribution configuration.
    """

    mean = float(
        config.get(
            "mean",
            default_mean,
        )
    )

    std = float(
        config.get(
            "std",
            default_std,
        )
    )

    minimum = float(
        config.get(
            "min",
            default_min,
        )
    )

    maximum = float(
        config.get(
            "max",
            default_max,
        )
    )

    return (
        mean,
        std,
        minimum,
        maximum,
    )


def _beta_scaled_expected_value(
    config: Mapping[str, Any],
    default_alpha: float,
    default_beta: float,
    default_min: float,
    default_max: float,
) -> float:
    """
    Calculate expected value for beta_scaled config.

    Used only as a fallback if no production batch exists.
    """

    alpha = float(
        config.get(
            "alpha",
            default_alpha,
        )
    )

    beta = float(
        config.get(
            "beta",
            default_beta,
        )
    )

    minimum = float(
        config.get(
            "min",
            default_min,
        )
    )

    maximum = float(
        config.get(
            "max",
            default_max,
        )
    )

    beta_mean = (
        alpha
        /
        (
            alpha
            +
            beta
        )
    )

    return (
        minimum
        +
        beta_mean
        *
        (
            maximum
            -
            minimum
        )
    )


# ============================================================
# CLIP
# ============================================================


def _clip(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    """
    Numeric clip helper.
    """

    return float(
        np.clip(
            value,
            minimum,
            maximum,
        )
    )


# ============================================================
# MACHINE LOAD NORMALIZATION
# ============================================================


def _normalize_load(
    value: Any,
) -> float:
    """
    Normalize machine load to [0, 1].

    Supports:

        0.75

    and:

        75
    """

    load = float(
        value
    )

    if load > 1.0:

        load /= 100.0

    return _clip(
        load,
        0.20,
        1.00,
    )


# ============================================================
# PREPARE MASTER INPUTS
# ============================================================


def _prepare_inputs(
    plants: pd.DataFrame,
    production_lines: pd.DataFrame,
    machines: pd.DataFrame,
    production_batches: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Convert upstream master data into a canonical schema.
    """

    if plants.empty:

        raise ValueError(
            "plants DataFrame cannot be empty"
        )

    if production_lines.empty:

        raise ValueError(
            "production_lines DataFrame cannot be empty"
        )

    if machines.empty:

        raise ValueError(
            "machines DataFrame cannot be empty"
        )

    if production_batches.empty:

        raise ValueError(
            "production_batches DataFrame cannot be empty"
        )

    # ========================================================
    # PLANTS
    # ========================================================

    plant_id_col = _find_column(
        plants,
        (
            "plant_id",
        ),
        "plants",
        "plant ID",
    )

    plant_name_col = _find_column(
        plants,
        (
            "plant_name",
            "name",
        ),
        "plants",
        "plant name",
    )

    canonical_plants = (
        plants[
            [
                plant_id_col,
                plant_name_col,
            ]
        ]
        .copy()
        .rename(
            columns={
                plant_id_col:
                    "plant_id",

                plant_name_col:
                    "plant_name",
            }
        )
    )

    if "active" in plants.columns:

        canonical_plants[
            "active"
        ] = (
            plants[
                "active"
            ]
            .astype(bool)
            .values
        )

    else:

        canonical_plants[
            "active"
        ] = True

    # ========================================================
    # PRODUCTION LINES
    # ========================================================

    line_id_col = _find_column(
        production_lines,
        (
            "production_line_id",
            "line_id",
        ),
        "production_lines",
        "production-line ID",
    )

    line_plant_col = _find_column(
        production_lines,
        (
            "plant_id",
        ),
        "production_lines",
        "plant ID",
    )

    line_name_col = _find_column(
        production_lines,
        (
            "production_line_name",
            "line_name",
        ),
        "production_lines",
        "line name",
    )

    line_type_col = _find_column(
        production_lines,
        (
            "line_type",
            "station_type",
        ),
        "production_lines",
        "line type",
    )

    canonical_lines = (
        production_lines[
            [
                line_id_col,
                line_plant_col,
                line_name_col,
                line_type_col,
            ]
        ]
        .copy()
        .rename(
            columns={
                line_id_col:
                    "production_line_id",

                line_plant_col:
                    "plant_id",

                line_name_col:
                    "production_line_name",

                line_type_col:
                    "line_type",
            }
        )
    )

    if "active" in production_lines.columns:

        canonical_lines[
            "active"
        ] = (
            production_lines[
                "active"
            ]
            .astype(bool)
            .values
        )

    else:

        canonical_lines[
            "active"
        ] = True

    # ========================================================
    # MACHINES
    # ========================================================

    machine_required = {
        "machine_id",
        "plant_id",
        "production_line_id",
        "machine_name",
        "rated_capacity_units_per_hour",
        "baseline_load_pct",
    }

    missing = (
        machine_required
        .difference(
            machines.columns
        )
    )

    if missing:

        raise ValueError(
            "machines DataFrame is missing: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    canonical_machines = (
        machines[
            list(
                machine_required
            )
        ]
        .copy()
    )

    if "active" in machines.columns:

        canonical_machines[
            "active"
        ] = (
            machines[
                "active"
            ]
            .astype(bool)
            .values
        )

    else:

        canonical_machines[
            "active"
        ] = True

    # ========================================================
    # PRODUCTION BATCHES
    # ========================================================

    batch_required = {
        "production_batch_id",

        "plant_id",

        "vehicle_model_id",
        "vehicle_model_name",

        "primary_supplier_lot_id",

        "supplier_lot_quality_score",

        "quality_score",

        "production_date",

        "batch_status",
    }

    missing = (
        batch_required
        .difference(
            production_batches.columns
        )
    )

    if missing:

        raise ValueError(
            "production_batches DataFrame is missing "
            "columns required by manufacturing_timeseries.py: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    canonical_batches = (
        production_batches[
            list(
                batch_required
            )
        ]
        .copy()
    )

    canonical_batches[
        "production_date"
    ] = pd.to_datetime(
        canonical_batches[
            "production_date"
        ]
    ).dt.date

    # ========================================================
    # DUPLICATES
    # ========================================================

    for dataframe, column in (
        (
            canonical_plants,
            "plant_id",
        ),
        (
            canonical_lines,
            "production_line_id",
        ),
        (
            canonical_machines,
            "machine_id",
        ),
        (
            canonical_batches,
            "production_batch_id",
        ),
    ):

        if dataframe[
            column
        ].duplicated().any():

            raise ValueError(
                f"Duplicate {column} values found"
            )

    return (
        canonical_plants,
        canonical_lines,
        canonical_machines,
        canonical_batches,
    )


# ============================================================
# BATCH CONTEXT LOOKUP
# ============================================================


def _build_batch_context(
    production_batches: pd.DataFrame,
) -> dict[
    tuple[str, date],
    dict[str, Any],
]:
    """
    Build:

        (plant_id, calendar_day) -> production context

    Production batches give the manufacturing time series
    connection to:

        vehicle model
        supplier lot
        supplier lot quality
        daily production quality
    """

    lookup: dict[
        tuple[str, date],
        dict[str, Any],
    ] = {}

    batches = (
        production_batches
        .sort_values(
            [
                "plant_id",
                "production_date",
                "production_batch_id",
            ]
        )
    )

    for batch in batches.itertuples(
        index=False
    ):

        key = (
            str(
                batch.plant_id
            ),
            batch.production_date,
        )

        lookup[
            key
        ] = {
            "production_batch_id":
                str(
                    batch.
                    production_batch_id
                ),

            "vehicle_model_id":
                str(
                    batch.
                    vehicle_model_id
                ),

            "vehicle_model_name":
                str(
                    batch.
                    vehicle_model_name
                ),

            "supplier_lot_id":
                str(
                    batch.
                    primary_supplier_lot_id
                ),

            "supplier_lot_quality_score":
                float(
                    batch.
                    supplier_lot_quality_score
                ),

            "batch_quality_score":
                float(
                    batch.
                    quality_score
                ),

            "batch_status":
                str(
                    batch.
                    batch_status
                ),
        }

    return lookup


# ============================================================
# NATURAL PERTURBATION WINDOWS
# ============================================================


def _create_perturbation_arrays(
    rng: np.random.Generator,
    count: int,
    steps_per_hour: int,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    """
    Create hidden natural process disturbances.

    IMPORTANT:

    These arrays are internal generator state.

    They are NOT written into the final DataFrame.

    Outputs:

        temperature drift
        vibration disturbance
        production/load pressure
    """

    temperature_drift = np.zeros(
        count,
        dtype=float,
    )

    vibration_disturbance = np.zeros(
        count,
        dtype=float,
    )

    load_pressure = np.zeros(
        count,
        dtype=float,
    )

    position = int(
        rng.integers(
            250 * steps_per_hour,
            500 * steps_per_hour,
        )
    )

    while (
        position
        <
        count
    ):

        duration = int(
            rng.integers(
                MIN_ANOMALY_WINDOW_HOURS * steps_per_hour,
                MAX_ANOMALY_WINDOW_HOURS * steps_per_hour
                +
                1,
            )
        )

        end_position = min(
            count,
            position
            +
            duration,
        )

        anomaly_type = int(
            rng.integers(
                0,
                3,
            )
        )

        if anomaly_type == 0:

            amplitude = float(
                rng.uniform(
                    2.5,
                    7.0,
                )
            )

            temperature_drift[
                position:end_position
            ] += np.linspace(
                0.2
                * amplitude,
                amplitude,
                end_position
                -
                position,
            )

        elif anomaly_type == 1:

            amplitude = float(
                rng.uniform(
                    0.6,
                    2.2,
                )
            )

            vibration_disturbance[
                position:end_position
            ] += np.linspace(
                0.3
                * amplitude,
                amplitude,
                end_position
                -
                position,
            )

        else:

            amplitude = float(
                rng.uniform(
                    0.08,
                    0.20,
                )
            )

            load_pressure[
                position:end_position
            ] += amplitude

        gap = int(
            rng.integers(
                ANOMALY_WINDOW_GAP_MIN_HOURS * steps_per_hour,
                ANOMALY_WINDOW_GAP_MAX_HOURS * steps_per_hour
                +
                1,
            )
        )

        position = (
            end_position
            +
            gap
        )

    return (
        temperature_drift,
        vibration_disturbance,
        load_pressure,
    )


# ============================================================
# LINE TYPE
# ============================================================


def _is_paint_line(
    line_type: str,
) -> bool:
    """
    Detect paint-related production line.
    """

    text = (
        str(
            line_type
        )
        .strip()
        .upper()
    )

    return (
        "PAINT"
        in text
    )


# ============================================================
# GENERATOR
# ============================================================


def generate_manufacturing_timeseries(
    plants: pd.DataFrame,

    production_lines: pd.DataFrame,

    machines: pd.DataFrame,

    production_batches: pd.DataFrame,

    generation: Mapping[str, Any] | None = None,

    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate minute-level manufacturing observations.

    Each machine is an independent coherent time-series context.

    PCMCI should later be run on one coherent context or
    carefully aggregated context at a time.

    Do NOT simply concatenate all machine rows and run PCMCI
    as if they belonged to one continuous machine history.
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
    # INPUTS
    # ========================================================

    (
        plants,
        production_lines,
        machines,
        production_batches,
    ) = _prepare_inputs(
        plants=
            plants,

        production_lines=
            production_lines,

        machines=
            machines,

        production_batches=
            production_batches,
    )

    # ========================================================
    # TIME WINDOW
    # ========================================================

    (
        generation_start,
        generation_end,
        _,
    ) = _get_generation_window(
        generation
    )

    manufacturing_config = generation.get(
        "manufacturing",
        {},
    )

    frequency = str(
        manufacturing_config.get(
            "frequency",
            generation.get("time", {}).get(
                "manufacturing_frequency",
                "1min",
            ),
        )
    )

    history_days = int(
        manufacturing_config.get(
            "history_days",
            7,
        )
    )

    if history_days <= 0:
        raise ValueError("manufacturing.history_days must be positive")

    generation_start = max(
        generation_start,
        generation_end - pd.Timedelta(days=history_days),
    )

    step_hours = float(
        pd.Timedelta(frequency).total_seconds()
        /
        3600.0
    )

    if not math.isclose(step_hours, 1.0 / 60.0):
        raise ValueError("manufacturing.frequency must be exactly 1min")

    steps_per_hour = int(round(1.0 / step_hours))

    timestamps = pd.date_range(
        start=
            generation_start,

        end=
            generation_end,

        freq=
            frequency,

        inclusive=
            "left",
    )

    if len(
        timestamps
    ) == 0:

        raise ValueError(
            "No timestamps generated"
        )

    # ========================================================
    # SEED
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
    # SENSOR CONFIG
    # ========================================================

    try:

        sensor_config = (
            distributions[
                "manufacturing"
            ][
                "sensors"
            ]
        )

    except KeyError as exc:

        raise KeyError(
            "Missing distributions.manufacturing.sensors"
        ) from exc

    # --------------------------------------------------------
    # Ambient temperature
    # --------------------------------------------------------

    (
        ambient_temp_mean,
        ambient_temp_std,
        ambient_temp_min,
        ambient_temp_max,
    ) = _normal_config(
        sensor_config.get(
            "ambient_temperature",
            sensor_config.get(
                "ambient_temp",
                {},
            ),
        ),
        30.0,
        4.0,
        15.0,
        45.0,
    )

    # --------------------------------------------------------
    # Ambient humidity
    # --------------------------------------------------------

    (
        ambient_humidity_mean,
        ambient_humidity_std,
        ambient_humidity_min,
        ambient_humidity_max,
    ) = _normal_config(
        sensor_config.get(
            "humidity",
            sensor_config.get(
                "ambient_humidity",
                {},
            ),
        ),
        60.0,
        12.0,
        25.0,
        95.0,
    )

    # --------------------------------------------------------
    # Machine temperature
    # --------------------------------------------------------

    (
        machine_temp_mean,
        machine_temp_std,
        machine_temp_min,
        machine_temp_max,
    ) = _normal_config(
        sensor_config.get(
            "machine_temperature",
            sensor_config.get(
                "machine_temp",
                {},
            ),
        ),
        64.0,
        5.0,
        45.0,
        90.0,
    )

    # --------------------------------------------------------
    # Vibration
    # --------------------------------------------------------

    (
        vibration_mean,
        vibration_std,
        vibration_min,
        vibration_max,
    ) = _normal_config(
        sensor_config.get(
            "vibration",
            {},
        ),
        2.3,
        0.45,
        0.5,
        8.0,
    )

    # --------------------------------------------------------
    # Power
    # --------------------------------------------------------

    (
        power_mean,
        power_std,
        power_min,
        power_max,
    ) = _normal_config(
        sensor_config.get(
            "power",
            {},
        ),
        120.0,
        15.0,
        70.0,
        200.0,
    )

    # --------------------------------------------------------
    # Line speed
    # --------------------------------------------------------

    (
        line_speed_mean,
        line_speed_std,
        line_speed_min,
        line_speed_max,
    ) = _normal_config(
        sensor_config.get(
            "line_speed",
            {},
        ),
        42.0,
        4.0,
        25.0,
        60.0,
    )

    # --------------------------------------------------------
    # Cycle time
    # --------------------------------------------------------

    (
        cycle_time_mean,
        cycle_time_std,
        cycle_time_min,
        cycle_time_max,
    ) = _normal_config(
        sensor_config.get(
            "cycle_time",
            {},
        ),
        85.0,
        10.0,
        50.0,
        140.0,
    )

    # --------------------------------------------------------
    # Paint temperature
    # --------------------------------------------------------

    (
        paint_temp_mean,
        paint_temp_std,
        paint_temp_min,
        paint_temp_max,
    ) = _normal_config(
        sensor_config.get(
            "paint_temperature",
            sensor_config.get(
                "paint_temp",
                {},
            ),
        ),
        26.0,
        2.0,
        18.0,
        35.0,
    )

    # --------------------------------------------------------
    # Paint humidity
    # --------------------------------------------------------

    (
        paint_humidity_mean,
        paint_humidity_std,
        paint_humidity_min,
        paint_humidity_max,
    ) = _normal_config(
        sensor_config.get(
            "paint_humidity",
            {},
        ),
        58.0,
        8.0,
        30.0,
        90.0,
    )

    # --------------------------------------------------------
    # Torque deviation
    # --------------------------------------------------------

    (
        torque_mean,
        torque_std,
        torque_min,
        torque_max,
    ) = _normal_config(
        sensor_config.get(
            "torque_deviation",
            {},
        ),
        0.0,
        0.8,
        -5.0,
        5.0,
    )

    # --------------------------------------------------------
    # Supplier quality fallback
    # --------------------------------------------------------

    supplier_quality_config = (
        sensor_config.get(
            "supplier_lot_quality",
            sensor_config.get(
                "supplier_quality",
                {},
            ),
        )
    )

    supplier_quality_fallback = (
        _beta_scaled_expected_value(
            supplier_quality_config,
            8.0,
            2.0,
            0.50,
            1.00,
        )
    )

    # ========================================================
    # LOOKUPS
    # ========================================================

    plant_lookup = {
        str(
            row.plant_id
        ):
            row

        for row
        in plants.itertuples(
            index=False
        )
    }

    line_lookup = {
        str(
            row.production_line_id
        ):
            row

        for row
        in production_lines.itertuples(
            index=False
        )
    }

    batch_context = (
        _build_batch_context(
            production_batches
        )
    )

    # ========================================================
    # ACTIVE MACHINES
    # ========================================================

    active_machines = (
        machines[
            machines[
                "active"
            ].astype(bool)
        ]
        .sort_values(
            "machine_id"
        )
        .reset_index(
            drop=True
        )
    )

    if active_machines.empty:

        raise ValueError(
            "No active machines available"
        )

    # ========================================================
    # OUTPUT
    # ========================================================

    all_machine_frames: list[
        pd.DataFrame
    ] = []

    # ========================================================
    # EACH MACHINE IS ONE COHERENT TIME-SERIES CONTEXT
    # ========================================================

    for machine in active_machines.itertuples(
        index=False
    ):

        machine_id = str(
            machine.machine_id
        )

        plant_id = str(
            machine.plant_id
        )

        production_line_id = str(
            machine.production_line_id
        )

        plant = plant_lookup.get(
            plant_id
        )

        if plant is None:

            raise ValueError(
                f"Machine {machine_id} references "
                f"unknown plant {plant_id}"
            )

        line = line_lookup.get(
            production_line_id
        )

        if line is None:

            raise ValueError(
                f"Machine {machine_id} references "
                "unknown production line "
                f"{production_line_id}"
            )

        if (
            str(
                line.plant_id
            )
            !=
            plant_id
        ):

            raise ValueError(
                f"Machine {machine_id}: "
                "production line / plant mismatch"
            )

        if not bool(
            line.active
        ):

            continue

        # ====================================================
        # MACHINE RNG
        #
        # Machine-specific seed keeps the history stable even
        # if machine ordering changes later.
        # ====================================================

        rng = make_rng(
            derive_seed(
                base_seed,
                (
                    "causal."
                    "manufacturing_timeseries."
                    f"{machine_id}"
                ),
            )
        )

        observation_count = len(
            timestamps
        )

        # ====================================================
        # HIDDEN NATURAL DISTURBANCES
        # ====================================================

        (
            temperature_drift,
            vibration_disturbance,
            load_pressure,
        ) = _create_perturbation_arrays(
            rng,
            observation_count,
            steps_per_hour,
        )

        # ====================================================
        # MACHINE BASELINES
        # ====================================================

        baseline_load = (
            _normalize_load(
                machine.
                baseline_load_pct
            )
        )

        rated_capacity = float(
            machine.
            rated_capacity_units_per_hour
        )

        capacity_factor = float(
            np.clip(
                rated_capacity
                /
                50.0,
                0.60,
                1.40,
            )
        )

        machine_temperature_baseline = (
            machine_temp_mean
            +
            float(
                rng.normal(
                    0.0,
                    1.5,
                )
            )
        )

        vibration_baseline = (
            vibration_mean
            +
            float(
                rng.normal(
                    0.0,
                    0.15,
                )
            )
        )

        power_baseline = (
            power_mean
            *
            (
                0.85
                +
                0.20
                * capacity_factor
            )
        )

        line_speed_baseline = (
            line_speed_mean
            *
            (
                0.90
                +
                0.10
                * capacity_factor
            )
        )

        # ====================================================
        # MAINTENANCE SCHEDULE
        # ====================================================

        maintenance_interval = int(
            BASE_MAINTENANCE_INTERVAL_HOURS
            +
            rng.integers(
                -MAINTENANCE_INTERVAL_JITTER_HOURS,
                MAINTENANCE_INTERVAL_JITTER_HOURS
                +
                1,
            )
        )

        maintenance_interval = max(
            7 * 24,
            maintenance_interval,
        )

        hours_since_maintenance = float(
            rng.integers(
                0,
                maintenance_interval
                //
                2
                +
                1,
            )
        )

        # ====================================================
        # PREVIOUS-LAG VALUES
        # ====================================================

        previous_machine_temperature = (
            machine_temperature_baseline
        )

        previous_ambient_temperature = ambient_temp_mean
        previous_machine_load = baseline_load

        previous_vibration = (
            vibration_baseline
        )

        previous_ambient_humidity = (
            ambient_humidity_mean
        )

        previous_defect_rate = 0.012

        previous_rework_rate = 0.006

        machine_load_history: list[float] = []
        machine_temperature_history: list[float] = []
        ambient_humidity_history: list[float] = []

        # ====================================================
        # ROW BUFFERS
        # ====================================================

        rows: list[
            dict[str, Any]
        ] = []

        # ====================================================
        # HOURLY GENERATION
        # ====================================================

        for index, timestamp in enumerate(
            timestamps
        ):

            hour = (
                float(timestamp.hour)
                + float(timestamp.minute) / 60.0
            )

            day_of_week = int(
                timestamp.dayofweek
            )

            calendar_day = (
                timestamp.date()
            )

            # =================================================
            # PRODUCTION BATCH CONTEXT
            # =================================================

            batch = batch_context.get(
                (
                    plant_id,
                    calendar_day,
                )
            )

            if batch is None:

                production_batch_id = None

                vehicle_model_id = None

                vehicle_model_name = None

                supplier_lot_id = None

                supplier_quality = (
                    supplier_quality_fallback
                )

                batch_quality_score = 0.96

                batch_status = None

            else:

                production_batch_id = (
                    batch[
                        "production_batch_id"
                    ]
                )

                vehicle_model_id = (
                    batch[
                        "vehicle_model_id"
                    ]
                )

                vehicle_model_name = (
                    batch[
                        "vehicle_model_name"
                    ]
                )

                supplier_lot_id = (
                    batch[
                        "supplier_lot_id"
                    ]
                )

                supplier_quality = float(
                    batch[
                        "supplier_lot_quality_score"
                    ]
                )

                batch_quality_score = float(
                    batch[
                        "batch_quality_score"
                    ]
                )

                batch_status = (
                    batch[
                        "batch_status"
                    ]
                )

            supplier_quality = _clip(
                supplier_quality,
                0.50,
                1.00,
            )

            # =================================================
            # TIME-OF-DAY PROCESS PATTERN
            # =================================================

            daily_wave = math.sin(
                2.0
                *
                math.pi
                *
                (
                    hour
                    -
                    6
                )
                /
                24.0
            )

            second_daily_wave = math.sin(
                2.0
                *
                math.pi
                *
                (
                    hour
                    -
                    14
                )
                /
                24.0
            )

            # Weekend lines are slightly less loaded.
            weekend_factor = (
                -0.05
                if day_of_week
                >=
                5
                else
                0.0
            )

            # =================================================
            # AMBIENT TEMPERATURE
            # =================================================

            ambient_temperature_target = (
                ambient_temp_mean
                + 3.0 * daily_wave
            )

            ambient_temperature = (
                (0.55 ** step_hours) * previous_ambient_temperature
                + (1.0 - 0.55 ** step_hours) * ambient_temperature_target
                + float(rng.normal(0.0, ambient_temp_std * 0.35 * math.sqrt(step_hours)))
            )

            ambient_temperature = _clip(
                ambient_temperature,
                ambient_temp_min,
                ambient_temp_max,
            )

            # =================================================
            # AMBIENT HUMIDITY
            #
            # Humidity tends to move inversely with daytime
            # temperature but remains noisy/autocorrelated.
            # =================================================

            humidity_target = (
                ambient_humidity_mean
                -
                6.0
                * daily_wave
                +
                float(
                    rng.normal(
                        0.0,
                        ambient_humidity_std
                        *
                        0.30
                        * math.sqrt(step_hours),
                    )
                )
            )

            ambient_humidity = (
                (0.55 ** step_hours)
                * previous_ambient_humidity
                +
                (1.0 - 0.55 ** step_hours)
                * humidity_target
            )

            ambient_humidity = _clip(
                ambient_humidity,
                ambient_humidity_min,
                ambient_humidity_max,
            )

            # =================================================
            # MACHINE LOAD
            # =================================================

            machine_load_target = (
                baseline_load
                +
                0.07
                * second_daily_wave
                +
                weekend_factor
                +
                float(
                    load_pressure[
                        index
                    ]
                )
            )

            machine_load = (
                (0.85 ** step_hours) * previous_machine_load
                + (1.0 - 0.85 ** step_hours) * machine_load_target
                + float(rng.normal(0.0, 0.035 * math.sqrt(step_hours)))
            )

            machine_load = _clip(
                machine_load,
                0.20,
                1.00,
            )

            lag_index = index - steps_per_hour
            lagged_machine_load = (
                machine_load_history[lag_index]
                if lag_index >= 0
                else previous_machine_load
            )
            lagged_machine_temperature = (
                machine_temperature_history[lag_index]
                if lag_index >= 0
                else previous_machine_temperature
            )
            lagged_ambient_humidity = (
                ambient_humidity_history[lag_index]
                if lag_index >= 0
                else previous_ambient_humidity
            )

            # =================================================
            # LINE SPEED
            #
            # Load affects line speed.
            # =================================================

            line_speed = (
                line_speed_baseline
                +
                16.0
                * (
                    machine_load
                    -
                    baseline_load
                )
                +
                float(
                    rng.normal(
                        0.0,
                        line_speed_std
                        *
                        0.40,
                    )
                )
            )

            line_speed = _clip(
                line_speed,
                line_speed_min,
                line_speed_max,
            )

            # =================================================
            # MACHINE TEMPERATURE
            #
            # Lag structure:
            #
            # load(t-60 minutes) / load pressure
            #       ↓
            # machine temperature(t)
            #
            # plus AR(1)
            # =================================================

            temperature_target = (
                machine_temperature_baseline
                +
                17.0
                * (
                    lagged_machine_load
                    -
                    baseline_load
                )
                +
                0.18
                * (
                    ambient_temperature
                    -
                    ambient_temp_mean
                )
                +
                float(
                    temperature_drift[
                        index
                    ]
                )
            )

            machine_temperature = (
                (0.65 ** step_hours)
                * previous_machine_temperature
                +
                (1.0 - 0.65 ** step_hours)
                * temperature_target
                +
                float(
                    rng.normal(
                        0.0,
                        machine_temp_std
                        *
                        0.12
                        * math.sqrt(step_hours),
                    )
                )
            )

            machine_temperature = _clip(
                machine_temperature,
                machine_temp_min,
                machine_temp_max,
            )

            # =================================================
            # VIBRATION
            #
            # Lag structure:
            #
            # machine temperature(t-60 minutes)
            # machine load(t)
            #       ↓
            # vibration(t)
            #
            # plus AR(1)
            # =================================================

            temperature_stress = max(
                0.0,
                (
                    lagged_machine_temperature
                    -
                    machine_temperature_baseline
                )
                /
                15.0,
            )

            vibration_target = (
                vibration_baseline
                +
                1.50
                * temperature_stress
                +
                1.30
                * max(
                    machine_load
                    -
                    0.78,
                    0.0,
                )
                +
                float(
                    vibration_disturbance[
                        index
                    ]
                )
            )

            vibration = (
                (0.65 ** step_hours)
                * previous_vibration
                +
                (1.0 - 0.65 ** step_hours)
                * vibration_target
                +
                float(
                    rng.normal(
                        0.0,
                        vibration_std
                        *
                        0.18
                        * math.sqrt(step_hours),
                    )
                )
            )

            vibration = _clip(
                vibration,
                vibration_min,
                vibration_max,
            )

            # =================================================
            # POWER
            #
            # Load + line speed drive power consumption.
            # =================================================

            power = (
                power_baseline
                +
                78.0
                * (
                    machine_load
                    -
                    0.50
                )
                +
                0.65
                * (
                    line_speed
                    -
                    line_speed_baseline
                )
                +
                float(
                    rng.normal(
                        0.0,
                        power_std
                        *
                        0.25,
                    )
                )
            )

            power = _clip(
                power,
                power_min,
                power_max,
            )

            # =================================================
            # CYCLE TIME
            #
            # Faster line speed usually reduces cycle time.
            # =================================================

            speed_ratio = (
                line_speed_baseline
                /
                max(
                    line_speed,
                    1.0,
                )
            )

            cycle_time = (
                cycle_time_mean
                *
                speed_ratio
                +
                float(
                    rng.normal(
                        0.0,
                        cycle_time_std
                        *
                        0.20,
                    )
                )
            )

            cycle_time = _clip(
                cycle_time,
                cycle_time_min,
                cycle_time_max,
            )

            # =================================================
            # MAINTENANCE CLOCK
            # =================================================

            hours_since_maintenance += step_hours

            if (
                hours_since_maintenance
                >
                maintenance_interval
            ):

                # High stress may delay the actual maintenance
                # slightly, creating overdue observations.
                maintenance_completion_probability = (
                    0.20
                    if machine_load
                    >
                    0.85
                    else
                    0.45
                )

                if (
                    float(
                        rng.random()
                    )
                    <
                    1.0 - (1.0 - maintenance_completion_probability) ** step_hours
                ):

                    hours_since_maintenance = 0.0

                    maintenance_interval = int(
                        BASE_MAINTENANCE_INTERVAL_HOURS
                        +
                        rng.integers(
                            -MAINTENANCE_INTERVAL_JITTER_HOURS,
                            MAINTENANCE_INTERVAL_JITTER_HOURS
                            +
                            1,
                        )
                    )

                    maintenance_interval = max(
                        7 * 24,
                        maintenance_interval,
                    )

            maintenance_overdue_hours = max(
                0.0,
                hours_since_maintenance
                -
                maintenance_interval,
            )

            # =================================================
            # TORQUE DEVIATION
            #
            # Higher load / vibration / supplier variability
            # makes deviation larger.
            # =================================================

            torque_deviation = (
                torque_mean
                +
                float(
                    rng.normal(
                        0.0,
                        torque_std
                        *
                        0.60,
                    )
                )
                +
                1.10
                * max(
                    machine_load
                    -
                    0.82,
                    0.0,
                )
                +
                0.20
                * max(
                    vibration
                    -
                    vibration_mean,
                    0.0,
                )
                +
                0.60
                * (
                    0.90
                    -
                    supplier_quality
                )
            )

            torque_deviation = _clip(
                torque_deviation,
                torque_min,
                torque_max,
            )

            # =================================================
            # PAINT-LINE SIGNALS
            # =================================================

            paint_line = _is_paint_line(
                str(
                    line.line_type
                )
            )

            if paint_line:

                paint_booth_temperature = (
                    paint_temp_mean
                    +
                    0.22
                    * (
                        ambient_temperature
                        -
                        ambient_temp_mean
                    )
                    +
                    float(
                        rng.normal(
                            0.0,
                            paint_temp_std
                            *
                            0.25,
                        )
                    )
                )

                paint_booth_temperature = _clip(
                    paint_booth_temperature,
                    paint_temp_min,
                    paint_temp_max,
                )

                paint_humidity_target = (
                    paint_humidity_mean
                    +
                    0.40
                    * (
                        lagged_ambient_humidity
                        -
                        ambient_humidity_mean
                    )
                    +
                    float(
                        rng.normal(
                            0.0,
                            paint_humidity_std
                            *
                            0.20,
                        )
                    )
                )

                paint_booth_humidity = _clip(
                    paint_humidity_target,
                    paint_humidity_min,
                    paint_humidity_max,
                )

            else:

                paint_booth_temperature = np.nan

                paint_booth_humidity = np.nan

            # =================================================
            # DEFECT RATE
            #
            # Observed evidence relationship:
            #
            # lower supplier quality
            # torque deviation
            # line speed pressure
            # vibration
            # maintenance overdue
            #        ↓
            # defect rate
            # =================================================

            supplier_quality_risk = max(
                0.0,
                0.94
                -
                supplier_quality,
            )

            torque_risk = min(
                abs(
                    torque_deviation
                )
                /
                5.0,
                1.0,
            )

            speed_pressure = max(
                0.0,
                (
                    line_speed
                    -
                    48.0
                )
                /
                12.0,
            )

            vibration_risk = max(
                0.0,
                (
                    vibration
                    -
                    2.7
                )
                /
                4.0,
            )

            maintenance_risk = min(
                maintenance_overdue_hours
                /
                96.0,
                1.0,
            )

            defect_target = (
                0.007
                +
                0.34
                * supplier_quality_risk
                +
                0.025
                * torque_risk
                +
                0.030
                * speed_pressure
                +
                0.035
                * vibration_risk
                +
                0.025
                * maintenance_risk
                +
                float(
                    rng.normal(
                        0.0,
                        0.0025,
                    )
                )
            )

            # Slight persistence.
            defect_rate = (
                (0.30 ** step_hours)
                * previous_defect_rate
                +
                (1.0 - 0.30 ** step_hours)
                * defect_target
            )

            defect_rate = _clip(
                defect_rate,
                0.0,
                MAX_DEFECT_RATE,
            )

            # =================================================
            # PAINT DEFECT RATE
            # =================================================

            if paint_line:

                paint_humidity_risk = max(
                    0.0,
                    (
                        float(
                            paint_booth_humidity
                        )
                        -
                        65.0
                    )
                    /
                    25.0,
                )

                paint_speed_risk = max(
                    0.0,
                    (
                        line_speed
                        -
                        46.0
                    )
                    /
                    14.0,
                )

                paint_defect_rate = (
                    0.004
                    +
                    0.035
                    * paint_humidity_risk
                    +
                    0.022
                    * paint_speed_risk
                    +
                    0.22
                    * supplier_quality_risk
                    +
                    float(
                        rng.normal(
                            0.0,
                            0.0020,
                        )
                    )
                )

                paint_defect_rate = _clip(
                    paint_defect_rate,
                    0.0,
                    0.18,
                )

            else:

                paint_defect_rate = np.nan

            # =================================================
            # REWORK RATE
            #
            # Defect pressure drives rework.
            # =================================================

            rework_target = (
                0.55
                * defect_rate
            )

            if paint_line:

                rework_target += (
                    0.35
                    * float(
                        paint_defect_rate
                    )
                )

            rework_target += float(
                rng.normal(
                    0.0,
                    0.0018,
                )
            )

            rework_rate = (
                (0.35 ** step_hours)
                * previous_rework_rate
                +
                (1.0 - 0.35 ** step_hours)
                * rework_target
            )

            rework_rate = _clip(
                rework_rate,
                0.0,
                MAX_REWORK_RATE,
            )

            # =================================================
            # DOWNTIME
            #
            # Temperature + vibration + overdue maintenance
            # raise downtime risk.
            # =================================================

            temperature_risk = max(
                0.0,
                (
                    machine_temperature
                    -
                    70.0
                )
                /
                20.0,
            )

            downtime_expected = (
                0.40
                +
                11.0
                * temperature_risk
                +
                13.0
                * vibration_risk
                +
                15.0
                * maintenance_risk
            )

            if (
                downtime_expected
                <=
                0.5
            ):

                downtime_minutes = 0.0

            else:

                downtime_probability = _clip(
                    1.0 - (
                        1.0 - min(downtime_expected / 40.0, 0.75)
                    ) ** step_hours,
                    0.0,
                    0.75,
                )

                if (
                    float(
                        rng.random()
                    )
                    <
                    downtime_probability
                ):

                    downtime_minutes = float(
                        rng.gamma(
                            shape=2.0,
                            scale=max(
                                downtime_expected
                                /
                                2.0,
                                0.5,
                            ),
                        )
                    )

                else:

                    downtime_minutes = 0.0

            downtime_minutes = _clip(
                downtime_minutes,
                0.0,
                MAX_DOWNTIME_MINUTES,
            )

            # =================================================
            # QUALITY SCORE
            #
            # Derived from observed operational evidence.
            # =================================================

            quality_score = (
                1.0
                -
                2.10
                * defect_rate
                -
                1.15
                * rework_rate
                -
                0.030
                * torque_risk
                -
                0.08
                * (
                    1.0
                    -
                    supplier_quality
                )
            )

            # Weak daily connection to production batch
            # quality keeps transactional production and
            # time-series manufacturing worlds coherent.
            quality_score = (
                0.78
                * quality_score
                +
                0.22
                * batch_quality_score
            )

            quality_score += float(
                rng.normal(
                    0.0,
                    0.004,
                )
            )

            quality_score = _clip(
                quality_score,
                0.50,
                1.00,
            )

            # =================================================
            # RECORD
            # =================================================

            rows.append(
                {
                    # ----------------------------------------
                    # TIME
                    # ----------------------------------------

                    "timestamp":
                        timestamp,

                    # ----------------------------------------
                    # CONTEXT IDENTIFIERS
                    #
                    # These are not PCMCI numeric variables.
                    # ----------------------------------------

                    "plant_id":
                        plant_id,

                    "plant_name":
                        str(
                            plant.plant_name
                        ),

                    "production_line_id":
                        production_line_id,

                    "production_line_name":
                        str(
                            line.
                            production_line_name
                        ),

                    "line_type":
                        str(
                            line.line_type
                        ),

                    "machine_id":
                        machine_id,

                    "machine_name":
                        str(
                            machine.
                            machine_name
                        ),

                    # ----------------------------------------
                    # CURRENT PRODUCTION CONTEXT
                    # ----------------------------------------

                    "production_batch_id":
                        production_batch_id,

                    "vehicle_model_id":
                        vehicle_model_id,

                    "vehicle_model_name":
                        vehicle_model_name,

                    "supplier_lot_id":
                        supplier_lot_id,

                    "batch_status":
                        batch_status,

                    # ----------------------------------------
                    # ENVIRONMENT
                    # ----------------------------------------

                    "ambient_temperature_c":
                        round(
                            ambient_temperature,
                            4,
                        ),

                    "ambient_humidity_pct":
                        round(
                            ambient_humidity,
                            4,
                        ),

                    # ----------------------------------------
                    # MACHINE STATE
                    # ----------------------------------------

                    "machine_load":
                        round(
                            machine_load,
                            6,
                        ),

                    "machine_temperature_c":
                        round(
                            machine_temperature,
                            4,
                        ),

                    "vibration_mm_s":
                        round(
                            vibration,
                            4,
                        ),

                    "power_kw":
                        round(
                            power,
                            4,
                        ),

                    # ----------------------------------------
                    # PROCESS
                    # ----------------------------------------

                    "line_speed_units_per_hour":
                        round(
                            line_speed,
                            4,
                        ),

                    "cycle_time_seconds":
                        round(
                            cycle_time,
                            4,
                        ),

                    # ----------------------------------------
                    # MAINTENANCE
                    # ----------------------------------------

                    "hours_since_maintenance":
                        round(
                            hours_since_maintenance,
                            3,
                        ),

                    "maintenance_overdue_hours":
                        round(
                            maintenance_overdue_hours,
                            3,
                        ),

                    # ----------------------------------------
                    # SUPPLIER / MATERIAL QUALITY
                    # ----------------------------------------

                    "supplier_lot_quality_score":
                        round(
                            supplier_quality,
                            6,
                        ),

                    # ----------------------------------------
                    # ASSEMBLY / PROCESS QUALITY
                    # ----------------------------------------

                    "torque_deviation_nm":
                        round(
                            torque_deviation,
                            4,
                        ),

                    # ----------------------------------------
                    # PAINT-SPECIFIC SIGNALS
                    # ----------------------------------------

                    "paint_booth_temperature_c":
                        (
                            round(
                                float(
                                    paint_booth_temperature
                                ),
                                4,
                            )
                            if paint_line
                            else np.nan
                        ),

                    "paint_booth_humidity_pct":
                        (
                            round(
                                float(
                                    paint_booth_humidity
                                ),
                                4,
                            )
                            if paint_line
                            else np.nan
                        ),

                    "paint_defect_rate":
                        (
                            round(
                                float(
                                    paint_defect_rate
                                ),
                                6,
                            )
                            if paint_line
                            else np.nan
                        ),

                    # ----------------------------------------
                    # QUALITY OUTCOMES
                    # ----------------------------------------

                    "defect_rate":
                        round(
                            defect_rate,
                            6,
                        ),

                    "rework_rate":
                        round(
                            rework_rate,
                            6,
                        ),

                    "downtime_minutes":
                        round(
                            downtime_minutes,
                            4,
                        ),

                    "quality_score":
                        round(
                            quality_score,
                            6,
                        ),

                    # ----------------------------------------
                    # PROVENANCE
                    # ----------------------------------------

                    "data_origin":
                        data_origin,

                    "generator_version":
                        generator_version,
                }
            )

            # =================================================
            # LAG UPDATE
            # =================================================

            previous_machine_temperature = (
                machine_temperature
            )

            previous_ambient_temperature = ambient_temperature
            previous_machine_load = machine_load

            previous_vibration = (
                vibration
            )

            previous_ambient_humidity = (
                ambient_humidity
            )

            previous_defect_rate = (
                defect_rate
            )

            previous_rework_rate = (
                rework_rate
            )

            machine_load_history.append(machine_load)
            machine_temperature_history.append(machine_temperature)
            ambient_humidity_history.append(ambient_humidity)

        # ====================================================
        # MACHINE FRAME
        # ====================================================

        machine_frame = pd.DataFrame(
            rows
        )

        all_machine_frames.append(
            machine_frame
        )

    # ========================================================
    # COMBINE
    # ========================================================

    if not all_machine_frames:

        raise ValueError(
            "No manufacturing time-series "
            "contexts were generated"
        )

    manufacturing_timeseries = pd.concat(
        all_machine_frames,
        ignore_index=True,
    )

    manufacturing_timeseries = (
        manufacturing_timeseries
        .sort_values(
            [
                "machine_id",
                "timestamp",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # ========================================================
    # VALIDATE
    # ========================================================

    validate_manufacturing_timeseries(
        manufacturing_timeseries=
            manufacturing_timeseries,

        plants=
            plants,

        production_lines=
            production_lines,

        machines=
            machines,

        production_batches=
            production_batches,

        generation_start=
            generation_start,

        generation_end=
            generation_end,
    )

    return manufacturing_timeseries


# ============================================================
# VALIDATION
# ============================================================


def validate_manufacturing_timeseries(
    manufacturing_timeseries: pd.DataFrame,

    plants: pd.DataFrame,

    production_lines: pd.DataFrame,

    machines: pd.DataFrame,

    production_batches: pd.DataFrame,

    generation_start: pd.Timestamp,

    generation_end: pd.Timestamp,
) -> None:
    """
    Validate generated manufacturing time-series data.
    """

    required_columns = {
        "timestamp",

        "plant_id",
        "plant_name",

        "production_line_id",
        "production_line_name",
        "line_type",

        "machine_id",
        "machine_name",

        "production_batch_id",

        "vehicle_model_id",
        "vehicle_model_name",

        "supplier_lot_id",

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

        "supplier_lot_quality_score",

        "torque_deviation_nm",

        "paint_booth_temperature_c",
        "paint_booth_humidity_pct",
        "paint_defect_rate",

        "defect_rate",
        "rework_rate",

        "downtime_minutes",

        "quality_score",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        .difference(
            manufacturing_timeseries.columns
        )
    )

    if missing:

        raise ValueError(
            "Manufacturing time series is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if manufacturing_timeseries.empty:

        raise ValueError(
            "Manufacturing time series cannot be empty"
        )

    # ========================================================
    # TIMESTAMP
    # ========================================================

    timestamps = pd.to_datetime(
        manufacturing_timeseries[
            "timestamp"
        ]
    )

    if (
        timestamps
        <
        generation_start
    ).any():

        raise ValueError(
            "Manufacturing observations occur "
            "before generation start"
        )

    if (
        timestamps
        >=
        generation_end
    ).any():

        raise ValueError(
            "Manufacturing observations occur "
            "at/after generation end"
        )

    # ========================================================
    # COMPOSITE UNIQUENESS
    # ========================================================

    if manufacturing_timeseries.duplicated(
        subset=[
            "machine_id",
            "timestamp",
        ]
    ).any():

        raise ValueError(
            "Duplicate machine_id/timestamp "
            "observations found"
        )

    # ========================================================
    # FK VALIDATION
    # ========================================================

    valid_plant_ids = set(
        plants[
            "plant_id"
        ].astype(str)
    )

    valid_line_ids = set(
        production_lines[
            "production_line_id"
        ].astype(str)
    )

    valid_machine_ids = set(
        machines[
            "machine_id"
        ].astype(str)
    )

    valid_batch_ids = set(
        production_batches[
            "production_batch_id"
        ].astype(str)
    )

    if (
        set(
            manufacturing_timeseries[
                "plant_id"
            ].astype(str)
        )
        -
        valid_plant_ids
    ):

        raise ValueError(
            "Manufacturing time series references "
            "invalid plant IDs"
        )

    if (
        set(
            manufacturing_timeseries[
                "production_line_id"
            ].astype(str)
        )
        -
        valid_line_ids
    ):

        raise ValueError(
            "Manufacturing time series references "
            "invalid production-line IDs"
        )

    if (
        set(
            manufacturing_timeseries[
                "machine_id"
            ].astype(str)
        )
        -
        valid_machine_ids
    ):

        raise ValueError(
            "Manufacturing time series references "
            "invalid machine IDs"
        )

    non_null_batch_ids = set(
        manufacturing_timeseries[
            "production_batch_id"
        ]
        .dropna()
        .astype(str)
    )

    if (
        non_null_batch_ids
        -
        valid_batch_ids
    ):

        raise ValueError(
            "Manufacturing time series references "
            "invalid production batch IDs"
        )

    # ========================================================
    # MACHINE LOAD
    # ========================================================

    load = pd.to_numeric(
        manufacturing_timeseries[
            "machine_load"
        ],
        errors="raise",
    )

    if (
        (
            load < 0
        )
        |
        (
            load > 1
        )
    ).any():

        raise ValueError(
            "machine_load must be between 0 and 1"
        )

    # ========================================================
    # SUPPLIER QUALITY
    # ========================================================

    supplier_quality = pd.to_numeric(
        manufacturing_timeseries[
            "supplier_lot_quality_score"
        ],
        errors="raise",
    )

    if (
        (
            supplier_quality < 0
        )
        |
        (
            supplier_quality > 1
        )
    ).any():

        raise ValueError(
            "supplier_lot_quality_score "
            "must be between 0 and 1"
        )

    # ========================================================
    # OUTCOME RATES
    # ========================================================

    for column in (
        "defect_rate",
        "rework_rate",
        "quality_score",
    ):

        values = pd.to_numeric(
            manufacturing_timeseries[
                column
            ],
            errors="raise",
        )

        if (
            (
                values < 0
            )
            |
            (
                values > 1
            )
        ).any():

            raise ValueError(
                f"{column} must be between 0 and 1"
            )

    # ========================================================
    # DOWNTIME
    # ========================================================

    downtime = pd.to_numeric(
        manufacturing_timeseries[
            "downtime_minutes"
        ],
        errors="raise",
    )

    if (
        downtime < 0
    ).any():

        raise ValueError(
            "downtime_minutes cannot be negative"
        )

    if (
        downtime > 60
    ).any():

        raise ValueError(
            "downtime_minutes cannot exceed "
            "one minute in a minute-level observation"
        )

    # ========================================================
    # MAINTENANCE
    # ========================================================

    if (
        pd.to_numeric(
            manufacturing_timeseries[
                "hours_since_maintenance"
            ],
            errors="raise",
        )
        <
        0
    ).any():

        raise ValueError(
            "hours_since_maintenance cannot be negative"
        )

    if (
        pd.to_numeric(
            manufacturing_timeseries[
                "maintenance_overdue_hours"
            ],
            errors="raise",
        )
        <
        0
    ).any():

        raise ValueError(
            "maintenance_overdue_hours "
            "cannot be negative"
        )

    # ========================================================
    # PCMCI SAMPLE SIZE CHECK
    #
    # With the configured Jan-Aug window each machine should
    # have roughly 5,088 hourly observations.
    # ========================================================

    observations_per_machine = (
        manufacturing_timeseries
        .groupby(
            "machine_id"
        )
        .size()
    )

    total_window_hours = int(
        (
            generation_end
            -
            generation_start
        ).total_seconds()
        /
        3600
    )

    if (
        total_window_hours
        >=
        MIN_PCMCI_CONTEXT_OBSERVATIONS
    ):

        too_small = (
            observations_per_machine[
                observations_per_machine
                <
                MIN_PCMCI_CONTEXT_OBSERVATIONS
            ]
        )

        if not too_small.empty:

            raise ValueError(
                "Some machine contexts have fewer than "
                f"{MIN_PCMCI_CONTEXT_OBSERVATIONS} "
                "observations required for the PoC "
                "PCMCI history"
            )

    # ========================================================
    # MACHINE -> LINE -> PLANT RELATIONSHIP
    # ========================================================

    machine_lookup = {
        str(
            row.machine_id
        ):
            row

        for row
        in machines.itertuples(
            index=False
        )
    }

    line_lookup = {
        str(
            row.production_line_id
        ):
            row

        for row
        in production_lines.itertuples(
            index=False
        )
    }

    context_rows = (
        manufacturing_timeseries[
            [
                "machine_id",
                "production_line_id",
                "plant_id",
            ]
        ]
        .drop_duplicates()
    )

    for context in context_rows.itertuples(
        index=False
    ):

        machine = machine_lookup[
            str(
                context.machine_id
            )
        ]

        line = line_lookup[
            str(
                context.production_line_id
            )
        ]

        if (
            str(
                machine.
                production_line_id
            )
            !=
            str(
                context.
                production_line_id
            )
        ):

            raise ValueError(
                f"Machine {context.machine_id} "
                "has inconsistent production line"
            )

        if (
            str(
                machine.plant_id
            )
            !=
            str(
                context.plant_id
            )
        ):

            raise ValueError(
                f"Machine {context.machine_id} "
                "has inconsistent plant"
            )

        if (
            str(
                line.plant_id
            )
            !=
            str(
                context.plant_id
            )
        ):

            raise ValueError(
                f"Production line "
                f"{context.production_line_id} "
                "has inconsistent plant"
            )

    # ========================================================
    # IMPORTANT LEAKAGE CHECK
    #
    # These columns must NEVER appear in the runtime
    # manufacturing time-series.
    # ========================================================

    forbidden_truth_columns = {
        "scenario_name",
        "scenario_id",

        "is_anomaly",
        "anomaly_type",

        "true_root_cause",

        "true_causal_parent",
        "true_causal_child",

        "causal_coefficient",

        "ground_truth_edge",

        "expected_warning",
    }

    leaked = (
        forbidden_truth_columns
        .intersection(
            manufacturing_timeseries.columns
        )
    )

    if leaked:

        raise ValueError(
            "Generator truth leaked into runtime "
            "manufacturing time-series: "
            + ", ".join(
                sorted(
                    leaked
                )
            )
        )


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================


def generate_manufacturing_timeseries_master(
    plants: pd.DataFrame,

    production_lines: pd.DataFrame,

    machines: pd.DataFrame,

    production_batches: pd.DataFrame,

    generation: Mapping[str, Any] | None = None,

    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Public entry point later used by generate_all.py.
    """

    return generate_manufacturing_timeseries(
        plants=
            plants,

        production_lines=
            production_lines,

        machines=
            machines,

        production_batches=
            production_batches,

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

    from data.generators.master.vehicle_models import (
        generate_vehicle_models,
    )

    from data.generators.master.plants import (
        generate_plant_master,
    )

    from data.generators.master.machines import (
        generate_machine_master,
    )

    from data.generators.auto.suppliers import (
        generate_supplier_master,
    )

    from data.generators.auto.production import (
        generate_production_batch_master,
    )

    # ========================================================
    # MASTER
    # ========================================================

    (
        regions_df,
        cities_df,
    ) = generate_geography()

    vehicle_models_df = (
        generate_vehicle_models()
    )

    (
        plants_df,
        production_lines_df,
    ) = generate_plant_master(
        cities_df
    )

    machines_df = (
        generate_machine_master(
            production_lines_df
        )
    )

    # ========================================================
    # SUPPLIERS
    # ========================================================

    (
        suppliers_df,
        supplier_lots_df,
    ) = generate_supplier_master(
        cities=
            cities_df
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
    # MANUFACTURING TIME SERIES
    # ========================================================

    manufacturing_df = (
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
    # BASIC INFO
    # ========================================================

    print(
        "\n=== MANUFACTURING TIME-SERIES INFO ===\n"
    )

    print(
        "Rows:",
        len(
            manufacturing_df
        ),
    )

    print(
        "Machines:",
        manufacturing_df[
            "machine_id"
        ].nunique(),
    )

    print(
        "Production lines:",
        manufacturing_df[
            "production_line_id"
        ].nunique(),
    )

    print(
        "Plants:",
        manufacturing_df[
            "plant_id"
        ].nunique(),
    )

    print(
        "Start:",
        manufacturing_df[
            "timestamp"
        ].min(),
    )

    print(
        "End:",
        manufacturing_df[
            "timestamp"
        ].max(),
    )

    # ========================================================
    # OBSERVATIONS PER MACHINE
    # ========================================================

    print(
        "\n=== OBSERVATIONS PER MACHINE ===\n"
    )

    machine_counts = (
        manufacturing_df
        .groupby(
            "machine_id"
        )
        .size()
        .reset_index(
            name="observations"
        )
    )

    print(
        machine_counts
        .head(
            30
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # SAMPLE
    # ========================================================

    print(
        "\n=== MANUFACTURING SAMPLE ===\n"
    )

    sample_columns = [
        "timestamp",

        "plant_name",

        "production_line_name",
        "line_type",

        "machine_name",

        "vehicle_model_name",

        "machine_load",

        "machine_temperature_c",

        "vibration_mm_s",

        "power_kw",

        "line_speed_units_per_hour",

        "supplier_lot_quality_score",

        "defect_rate",

        "rework_rate",

        "downtime_minutes",

        "quality_score",
    ]

    print(
        manufacturing_df[
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
    # KPI / SIGNAL SUMMARY
    # ========================================================

    print(
        "\n=== MANUFACTURING SIGNAL CHECK ===\n"
    )

    print(
        "Average machine load:",
        round(
            manufacturing_df[
                "machine_load"
            ].mean(),
            4,
        ),
    )

    print(
        "Average machine temperature:",
        round(
            manufacturing_df[
                "machine_temperature_c"
            ].mean(),
            3,
        ),
    )

    print(
        "Average vibration:",
        round(
            manufacturing_df[
                "vibration_mm_s"
            ].mean(),
            3,
        ),
    )

    print(
        "Average defect rate:",
        round(
            manufacturing_df[
                "defect_rate"
            ].mean(),
            5,
        ),
    )

    print(
        "Average rework rate:",
        round(
            manufacturing_df[
                "rework_rate"
            ].mean(),
            5,
        ),
    )

    print(
        "Average quality score:",
        round(
            manufacturing_df[
                "quality_score"
            ].mean(),
            4,
        ),
    )

    print(
        "Hours with downtime:",
        int(
            (
                manufacturing_df[
                    "downtime_minutes"
                ]
                >
                0
            )
            .sum()
        ),
    )

    print(
        "Hours with overdue maintenance:",
        int(
            (
                manufacturing_df[
                    "maintenance_overdue_hours"
                ]
                >
                0
            )
            .sum()
        ),
    )

    # ========================================================
    # PCMCI CANDIDATE VARIABLES
    # ========================================================

    print(
        "\n=== GENERIC PCMCI CANDIDATE VARIABLES ===\n"
    )

    generic_pcmci_variables = [
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

        "supplier_lot_quality_score",

        "torque_deviation_nm",

        "defect_rate",
        "rework_rate",

        "downtime_minutes",

        "quality_score",
    ]

    for variable in generic_pcmci_variables:

        print(
            "-",
            variable,
        )

    print(
        "\nGenerated "
        f"{len(manufacturing_df)} "
        "synthetic minute-level manufacturing observations "
        "across "
        f"{manufacturing_df['machine_id'].nunique()} "
        "machine contexts successfully."
    )