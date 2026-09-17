"""
Machine master-data generator for Mahindra AI Nexus.

Generates:
- Machine master records linked to production lines and plants.

This module DOES NOT write CSV files.

Later:
    data/scripts/generate_all.py

will save the returned DataFrame as:

    data/synthetic/master/machines.csv

IMPORTANT:
Machine types, capacities, loads and maintenance intervals below
are synthetic engineering assumptions for the PoC.
They are NOT actual Mahindra operational values.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from data.generators.common.helpers import (
    load_generation_config,
)

from data.generators.common.ids import (
    make_entity_id,
)


# ============================================================
# MACHINE TEMPLATES BY PRODUCTION-LINE TYPE
# ============================================================

MACHINE_TEMPLATES: dict[str, list[dict[str, Any]]] = {

    # --------------------------------------------------------
    # BODY SHOP
    # --------------------------------------------------------

    "BODY": [
        {
            "machine_type": "WELDING_ROBOT",
            "station_type": "WELDING",
            "rated_capacity_units_per_hour": 45,
            "baseline_load_pct": 0.72,
            "maintenance_interval_hours": 500,
        },
        {
            "machine_type": "BODY_PRESS",
            "station_type": "PRESSING",
            "rated_capacity_units_per_hour": 42,
            "baseline_load_pct": 0.68,
            "maintenance_interval_hours": 600,
        },
        {
            "machine_type": "WELDING_ROBOT",
            "station_type": "WELDING",
            "rated_capacity_units_per_hour": 45,
            "baseline_load_pct": 0.75,
            "maintenance_interval_hours": 500,
        },
        {
            "machine_type": "BODY_ALIGNMENT_SYSTEM",
            "station_type": "ALIGNMENT",
            "rated_capacity_units_per_hour": 40,
            "baseline_load_pct": 0.65,
            "maintenance_interval_hours": 700,
        },
        {
            "machine_type": "SPOT_WELDER",
            "station_type": "WELDING",
            "rated_capacity_units_per_hour": 44,
            "baseline_load_pct": 0.71,
            "maintenance_interval_hours": 450,
        },
        {
            "machine_type": "BODY_CONVEYOR",
            "station_type": "MATERIAL_HANDLING",
            "rated_capacity_units_per_hour": 48,
            "baseline_load_pct": 0.63,
            "maintenance_interval_hours": 800,
        },
        {
            "machine_type": "ROBOTIC_GRIPPER",
            "station_type": "MATERIAL_HANDLING",
            "rated_capacity_units_per_hour": 46,
            "baseline_load_pct": 0.67,
            "maintenance_interval_hours": 550,
        },
        {
            "machine_type": "BODY_INSPECTION_SYSTEM",
            "station_type": "INSPECTION",
            "rated_capacity_units_per_hour": 40,
            "baseline_load_pct": 0.58,
            "maintenance_interval_hours": 900,
        },
    ],

    # --------------------------------------------------------
    # PAINT SHOP
    # --------------------------------------------------------

    "PAINT": [
        {
            "machine_type": "PAINT_SPRAY_ROBOT",
            "station_type": "PAINTING",
            "rated_capacity_units_per_hour": 38,
            "baseline_load_pct": 0.70,
            "maintenance_interval_hours": 450,
        },
        {
            "machine_type": "PAINT_BOOTH_AIRFLOW_SYSTEM",
            "station_type": "PAINT_ENVIRONMENT",
            "rated_capacity_units_per_hour": 40,
            "baseline_load_pct": 0.65,
            "maintenance_interval_hours": 600,
        },
        {
            "machine_type": "PAINT_OVEN",
            "station_type": "CURING",
            "rated_capacity_units_per_hour": 35,
            "baseline_load_pct": 0.76,
            "maintenance_interval_hours": 700,
        },
        {
            "machine_type": "PAINT_CONVEYOR",
            "station_type": "MATERIAL_HANDLING",
            "rated_capacity_units_per_hour": 40,
            "baseline_load_pct": 0.62,
            "maintenance_interval_hours": 800,
        },
        {
            "machine_type": "PRIMER_SPRAY_SYSTEM",
            "station_type": "PAINTING",
            "rated_capacity_units_per_hour": 37,
            "baseline_load_pct": 0.69,
            "maintenance_interval_hours": 450,
        },
        {
            "machine_type": "PAINT_MIXING_SYSTEM",
            "station_type": "PAINT_PREPARATION",
            "rated_capacity_units_per_hour": 42,
            "baseline_load_pct": 0.57,
            "maintenance_interval_hours": 500,
        },
        {
            "machine_type": "PAINT_THICKNESS_SCANNER",
            "station_type": "INSPECTION",
            "rated_capacity_units_per_hour": 36,
            "baseline_load_pct": 0.55,
            "maintenance_interval_hours": 900,
        },
        {
            "machine_type": "PAINT_DEFECT_SCANNER",
            "station_type": "INSPECTION",
            "rated_capacity_units_per_hour": 35,
            "baseline_load_pct": 0.54,
            "maintenance_interval_hours": 900,
        },
    ],

    # --------------------------------------------------------
    # ASSEMBLY LINE
    # --------------------------------------------------------

    "ASSEMBLY": [
        {
            "machine_type": "TORQUE_STATION",
            "station_type": "TORQUE",
            "rated_capacity_units_per_hour": 42,
            "baseline_load_pct": 0.72,
            "maintenance_interval_hours": 500,
        },
        {
            "machine_type": "ASSEMBLY_ROBOT",
            "station_type": "ASSEMBLY",
            "rated_capacity_units_per_hour": 40,
            "baseline_load_pct": 0.74,
            "maintenance_interval_hours": 550,
        },
        {
            "machine_type": "ASSEMBLY_CONVEYOR",
            "station_type": "MATERIAL_HANDLING",
            "rated_capacity_units_per_hour": 45,
            "baseline_load_pct": 0.64,
            "maintenance_interval_hours": 800,
        },
        {
            "machine_type": "FASTENING_SYSTEM",
            "station_type": "FASTENING",
            "rated_capacity_units_per_hour": 41,
            "baseline_load_pct": 0.69,
            "maintenance_interval_hours": 500,
        },
        {
            "machine_type": "ENGINE_MOUNT_STATION",
            "station_type": "ASSEMBLY",
            "rated_capacity_units_per_hour": 37,
            "baseline_load_pct": 0.71,
            "maintenance_interval_hours": 650,
        },
        {
            "machine_type": "WHEEL_FITMENT_STATION",
            "station_type": "ASSEMBLY",
            "rated_capacity_units_per_hour": 40,
            "baseline_load_pct": 0.68,
            "maintenance_interval_hours": 550,
        },
        {
            "machine_type": "ELECTRICAL_TEST_STATION",
            "station_type": "TESTING",
            "rated_capacity_units_per_hour": 38,
            "baseline_load_pct": 0.58,
            "maintenance_interval_hours": 850,
        },
        {
            "machine_type": "FINAL_ASSEMBLY_SCANNER",
            "station_type": "INSPECTION",
            "rated_capacity_units_per_hour": 39,
            "baseline_load_pct": 0.56,
            "maintenance_interval_hours": 900,
        },
    ],

    # --------------------------------------------------------
    # QUALITY LINE
    # --------------------------------------------------------

    "QUALITY": [
        {
            "machine_type": "VISION_INSPECTION_SYSTEM",
            "station_type": "INSPECTION",
            "rated_capacity_units_per_hour": 34,
            "baseline_load_pct": 0.55,
            "maintenance_interval_hours": 900,
        },
        {
            "machine_type": "BRAKE_TESTER",
            "station_type": "TESTING",
            "rated_capacity_units_per_hour": 30,
            "baseline_load_pct": 0.60,
            "maintenance_interval_hours": 750,
        },
        {
            "machine_type": "WHEEL_ALIGNMENT_TESTER",
            "station_type": "TESTING",
            "rated_capacity_units_per_hour": 31,
            "baseline_load_pct": 0.59,
            "maintenance_interval_hours": 800,
        },
        {
            "machine_type": "ROLLER_TEST_BENCH",
            "station_type": "TESTING",
            "rated_capacity_units_per_hour": 29,
            "baseline_load_pct": 0.62,
            "maintenance_interval_hours": 750,
        },
        {
            "machine_type": "LEAK_TEST_SYSTEM",
            "station_type": "TESTING",
            "rated_capacity_units_per_hour": 32,
            "baseline_load_pct": 0.57,
            "maintenance_interval_hours": 850,
        },
        {
            "machine_type": "NOISE_VIBRATION_TESTER",
            "station_type": "TESTING",
            "rated_capacity_units_per_hour": 28,
            "baseline_load_pct": 0.54,
            "maintenance_interval_hours": 850,
        },
        {
            "machine_type": "QUALITY_SCANNER",
            "station_type": "INSPECTION",
            "rated_capacity_units_per_hour": 33,
            "baseline_load_pct": 0.52,
            "maintenance_interval_hours": 900,
        },
        {
            "machine_type": "END_OF_LINE_TESTER",
            "station_type": "FINAL_INSPECTION",
            "rated_capacity_units_per_hour": 30,
            "baseline_load_pct": 0.58,
            "maintenance_interval_hours": 1000,
        },
    ],
}


# ============================================================
# INTERNAL HELPERS
# ============================================================


def _as_positive_int(
    value: Any,
    name: str,
) -> int:
    """
    Convert a configuration value to a positive integer.
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


def _get_machine_range(
    generation: Mapping[str, Any],
) -> tuple[int, int]:
    """
    Read machines-per-line configuration.

    Primary expected structure:

        master:
          machines_per_line:
            min: 4
            max: 8

    A second key name is also accepted for compatibility:

        machines_per_production_line:
    """

    master = generation.get(
        "master"
    )

    if not isinstance(
        master,
        Mapping,
    ):
        raise KeyError(
            "Missing generation.master configuration"
        )

    machine_config = master.get(
        "machines_per_line"
    )

    if machine_config is None:
        machine_config = master.get(
            "machines_per_production_line"
        )

    if not isinstance(
        machine_config,
        Mapping,
    ):
        raise KeyError(
            "Missing machine-count configuration. "
            "Expected either "
            "generation.master.machines_per_line "
            "or generation.master."
            "machines_per_production_line."
        )

    min_machines = _as_positive_int(
        machine_config.get(
            "min"
        ),
        "machines_per_line.min",
    )

    max_machines = _as_positive_int(
        machine_config.get(
            "max"
        ),
        "machines_per_line.max",
    )

    if min_machines > max_machines:
        raise ValueError(
            "machines_per_line.min cannot "
            "be greater than max"
        )

    return (
        min_machines,
        max_machines,
    )


# ============================================================
# GENERATOR
# ============================================================


def generate_machines(
    production_lines: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate machine master records.

    Every machine belongs to exactly one production line
    and one plant.

    Output columns:

        machine_id
        production_line_id
        plant_id
        machine_name
        machine_type
        station_type
        rated_capacity_units_per_hour
        baseline_load_pct
        maintenance_interval_hours
        active
        data_origin
        generator_version
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    # --------------------------------------------------------
    # Validate incoming production lines first
    # --------------------------------------------------------

    _validate_input_production_lines(
        production_lines
    )

    # --------------------------------------------------------
    # Machine count configuration
    # --------------------------------------------------------

    (
        min_machines,
        max_machines,
    ) = _get_machine_range(
        generation
    )

    # --------------------------------------------------------
    # Every supported line must have enough templates
    # --------------------------------------------------------

    for line_type in (
        production_lines[
            "line_type"
        ]
        .dropna()
        .unique()
    ):

        if line_type not in MACHINE_TEMPLATES:
            raise ValueError(
                "No machine templates configured "
                f"for production line type "
                f"{line_type!r}"
            )

        available = len(
            MACHINE_TEMPLATES[
                line_type
            ]
        )

        if max_machines > available:
            raise ValueError(
                f"Configured max machines per line "
                f"is {max_machines}, but line type "
                f"{line_type!r} has only "
                f"{available} machine templates."
            )

    # --------------------------------------------------------
    # Provenance
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Generate machine records
    #
    # We intentionally use a deterministic pattern:
    #
    # if min=4, max=8:
    #
    # line 1 -> 4 machines
    # line 2 -> 5 machines
    # line 3 -> 6 machines
    # line 4 -> 7 machines
    # line 5 -> 8 machines
    # line 6 -> 4 machines
    #
    # This is deterministic and reproducible.
    # --------------------------------------------------------

    machine_span = (
        max_machines
        - min_machines
        + 1
    )

    machine_counter = 1

    rows: list[
        dict[str, Any]
    ] = []

    for line_index, line in enumerate(
        production_lines.itertuples(
            index=False
        )
    ):

        machine_count = (
            min_machines
            + (
                line_index
                % machine_span
            )
        )

        templates = (
            MACHINE_TEMPLATES[
                line.line_type
            ]
        )

        selected_templates = (
            templates[
                :machine_count
            ]
        )

        for local_index, template in enumerate(
            selected_templates,
            start=1,
        ):

            machine_id = make_entity_id(
                "machine",
                machine_counter,
                width=3,
            )

            rows.append(
                {
                    "machine_id":
                        machine_id,

                    "production_line_id":
                        line.production_line_id,

                    "plant_id":
                        line.plant_id,

                    "machine_name":
                        (
                            f"{line.line_type}-"
                            f"{template['machine_type']}-"
                            f"{local_index:02d}"
                        ),

                    "machine_type":
                        template[
                            "machine_type"
                        ],

                    "station_type":
                        template[
                            "station_type"
                        ],

                    "rated_capacity_units_per_hour":
                        int(
                            template[
                                "rated_capacity_units_per_hour"
                            ]
                        ),

                    "baseline_load_pct":
                        float(
                            template[
                                "baseline_load_pct"
                            ]
                        ),

                    "maintenance_interval_hours":
                        int(
                            template[
                                "maintenance_interval_hours"
                            ]
                        ),

                    "active":
                        True,

                    "data_origin":
                        data_origin,

                    "generator_version":
                        generator_version,
                }
            )

            machine_counter += 1

    machines = pd.DataFrame(
        rows,
        columns=[
            "machine_id",
            "production_line_id",
            "plant_id",
            "machine_name",
            "machine_type",
            "station_type",
            "rated_capacity_units_per_hour",
            "baseline_load_pct",
            "maintenance_interval_hours",
            "active",
            "data_origin",
            "generator_version",
        ],
    )

    validate_machines(
        machines=machines,
        production_lines=production_lines,
        min_machines=min_machines,
        max_machines=max_machines,
    )

    return machines


# ============================================================
# INPUT VALIDATION
# ============================================================


def _validate_input_production_lines(
    production_lines: pd.DataFrame,
) -> None:
    """
    Validate the minimum production-line structure
    needed by this generator.
    """

    required_columns = {
        "production_line_id",
        "plant_id",
        "line_type",
    }

    missing_columns = (
        required_columns
        .difference(
            production_lines.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "Production-lines DataFrame is missing "
            "columns required by machines.py: "
            + ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if production_lines.empty:
        raise ValueError(
            "Production-lines DataFrame "
            "cannot be empty"
        )

    for column in required_columns:

        if production_lines[
            column
        ].isna().any():

            raise ValueError(
                "Production-lines DataFrame "
                f"contains missing values "
                f"in {column}"
            )

    if production_lines[
        "production_line_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate production_line_id "
            "values found"
        )


# ============================================================
# MACHINE VALIDATION
# ============================================================


def validate_machines(
    machines: pd.DataFrame,
    production_lines: pd.DataFrame,
    min_machines: int,
    max_machines: int,
) -> None:
    """
    Validate generated machine master records.
    """

    required_columns = {
        "machine_id",
        "production_line_id",
        "plant_id",
        "machine_name",
        "machine_type",
        "station_type",
        "rated_capacity_units_per_hour",
        "baseline_load_pct",
        "maintenance_interval_hours",
        "active",
        "data_origin",
        "generator_version",
    }

    missing_columns = (
        required_columns
        .difference(
            machines.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "Machines DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if machines.empty:
        raise ValueError(
            "Machines DataFrame cannot be empty"
        )

    # --------------------------------------------------------
    # Required values
    # --------------------------------------------------------

    required_non_null = [
        "machine_id",
        "production_line_id",
        "plant_id",
        "machine_name",
        "machine_type",
        "station_type",
    ]

    for column in required_non_null:

        if machines[
            column
        ].isna().any():

            raise ValueError(
                f"Machines contains missing "
                f"values in {column}"
            )

    # --------------------------------------------------------
    # Unique machine IDs
    # --------------------------------------------------------

    if machines[
        "machine_id"
    ].duplicated().any():

        duplicates = (
            machines.loc[
                machines[
                    "machine_id"
                ].duplicated(
                    keep=False
                ),
                "machine_id",
            ]
            .tolist()
        )

        raise ValueError(
            "Duplicate machine_id values "
            f"found: {duplicates}"
        )

    # --------------------------------------------------------
    # Production-line foreign key
    # --------------------------------------------------------

    valid_line_ids = set(
        production_lines[
            "production_line_id"
        ]
    )

    invalid_lines = sorted(
        set(
            machines[
                "production_line_id"
            ]
        )
        .difference(
            valid_line_ids
        )
    )

    if invalid_lines:
        raise ValueError(
            "Machines reference invalid "
            "production_line_id values: "
            + ", ".join(
                invalid_lines
            )
        )

    # --------------------------------------------------------
    # Validate that machine plant_id matches line plant_id
    # --------------------------------------------------------

    line_to_plant = dict(
        zip(
            production_lines[
                "production_line_id"
            ],
            production_lines[
                "plant_id"
            ],
        )
    )

    mismatched = machines[
        machines.apply(
            lambda row:
                line_to_plant[
                    row[
                        "production_line_id"
                    ]
                ]
                != row[
                    "plant_id"
                ],
            axis=1,
        )
    ]

    if not mismatched.empty:
        raise ValueError(
            "Some machines contain a plant_id "
            "that does not match their "
            "production line's plant_id."
        )

    # --------------------------------------------------------
    # Capacity validation
    # --------------------------------------------------------

    capacities = pd.to_numeric(
        machines[
            "rated_capacity_units_per_hour"
        ],
        errors="raise",
    )

    if (
        capacities <= 0
    ).any():

        raise ValueError(
            "All machine rated capacities "
            "must be > 0"
        )

    # --------------------------------------------------------
    # Load validation
    # --------------------------------------------------------

    loads = pd.to_numeric(
        machines[
            "baseline_load_pct"
        ],
        errors="raise",
    )

    if (
        (loads < 0)
        | (loads > 1)
    ).any():

        raise ValueError(
            "baseline_load_pct must "
            "be between 0 and 1"
        )

    # --------------------------------------------------------
    # Maintenance interval validation
    # --------------------------------------------------------

    intervals = pd.to_numeric(
        machines[
            "maintenance_interval_hours"
        ],
        errors="raise",
    )

    if (
        intervals <= 0
    ).any():

        raise ValueError(
            "maintenance_interval_hours "
            "must be > 0"
        )

    # --------------------------------------------------------
    # Number of machines on each line
    # --------------------------------------------------------

    counts = (
        machines
        .groupby(
            "production_line_id"
        )
        .size()
    )

    for line_id in valid_line_ids:

        count = int(
            counts.get(
                line_id,
                0,
            )
        )

        if not (
            min_machines
            <= count
            <= max_machines
        ):

            raise ValueError(
                f"Production line {line_id} "
                f"has {count} machines. "
                f"Expected between "
                f"{min_machines} and "
                f"{max_machines}."
            )


# ============================================================
# MASTER GENERATOR
# ============================================================


def generate_machine_master(
    production_lines: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Public entry point used later by generate_all.py.

    Returns:
        machines_df
    """

    return generate_machines(
        production_lines=production_lines,
        generation=generation,
    )


# ============================================================
# LOCAL TEST
# ============================================================


if __name__ == "__main__":

    # ---------------------------------------------
    # Build upstream dependencies:
    #
    # geography
    #    ↓
    # plants
    #    ↓
    # production lines
    #    ↓
    # machines
    # ---------------------------------------------

    from data.generators.master.geography import (
        generate_geography,
    )

    from data.generators.master.plants import (
        generate_plant_master,
    )

    _, cities_df = (
        generate_geography()
    )

    (
        plants_df,
        production_lines_df,
    ) = generate_plant_master(
        geography_cities=cities_df
    )

    machines_df = generate_machine_master(
        production_lines=production_lines_df
    )

    print(
        "\n=== MACHINES ===\n"
    )

    print(
        machines_df.to_string(
            index=False
        )
    )

    print(
        "\n=== MACHINES PER PRODUCTION LINE ===\n"
    )

    machine_counts = (
        machines_df
        .groupby(
            [
                "plant_id",
                "production_line_id",
            ]
        )
        .size()
        .reset_index(
            name="machine_count"
        )
    )

    print(
        machine_counts.to_string(
            index=False
        )
    )

    print(
        "\nGenerated "
        f"{len(machines_df)} machines "
        f"across "
        f"{len(production_lines_df)} "
        "production lines successfully."
    )