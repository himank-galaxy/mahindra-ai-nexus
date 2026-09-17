"""
Plant and Production Line master-data generator
for Mahindra AI Nexus.

Generates:
- Plant master records
- Production line master records

This module DOES NOT write CSV files.

CSV writing is handled centrally by:

    data/scripts/export_csv.py

The plant names and locations below represent the canonical
automotive-facility reference set used by this PoC.

IMPORTANT:

The following remain SYNTHETIC engineering assumptions:

- daily production capacity
- number of production lines
- production-line type allocation
- units per hour
- shift count
- downstream machine topology
- production batches
- manufacturing telemetry

They must NOT be interpreted as actual Mahindra operational
capacity or plant configuration.

The purpose of using canonical facility names is to make the
synthetic manufacturing world business-relevant while keeping
all operational observations synthetic.
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
# CANONICAL AUTOMOTIVE FACILITY TEMPLATES
#
# Facility identity/location:
#     canonical reference data for the PoC
#
# Capacity:
#     synthetic engineering assumption
#
# plant_type:
#     normalized PoC taxonomy. We intentionally preserve the
#     broad AUTO_MANUFACTURING value so downstream generators
#     remain compatible with the existing synthetic factory.
# ============================================================

PLANT_TEMPLATES: list[dict[str, Any]] = [

    # --------------------------------------------------------
    # 1. CHAKAN
    #
    # Reference location:
    #     Pune, Maharashtra
    #
    # PoC focus:
    #     large automotive manufacturing facility
    #
    # Capacity below is synthetic.
    # --------------------------------------------------------

    {
        "plant_name": "Chakan Plant",
        "city_name": "Pune",
        "region_name": "West",
        "plant_type": "AUTO_MANUFACTURING",
        "base_daily_capacity": 900,
    },

    # --------------------------------------------------------
    # 2. NASHIK
    #
    # Reference location:
    #     Nashik, Maharashtra
    #
    # Capacity below is synthetic.
    # --------------------------------------------------------

    {
        "plant_name": "Nashik Plant",
        "city_name": "Nashik",
        "region_name": "West",
        "plant_type": "AUTO_MANUFACTURING",
        "base_daily_capacity": 750,
    },

    # --------------------------------------------------------
    # 3. KANDIVALI
    #
    # Reference location:
    #     Mumbai, Maharashtra
    #
    # Capacity below is synthetic.
    # --------------------------------------------------------

    {
        "plant_name": "Kandivali Plant",
        "city_name": "Mumbai",
        "region_name": "West",
        "plant_type": "AUTO_MANUFACTURING",
        "base_daily_capacity": 650,
    },

    # --------------------------------------------------------
    # 4. HARIDWAR
    #
    # Reference location:
    #     Haridwar, Uttarakhand
    #
    # Capacity below is synthetic.
    # --------------------------------------------------------

    {
        "plant_name": "Haridwar Plant",
        "city_name": "Haridwar",
        "region_name": "North",
        "plant_type": "AUTO_MANUFACTURING",
        "base_daily_capacity": 700,
    },

    # --------------------------------------------------------
    # 5. ZAHEERABAD
    #
    # Reference location:
    #     Zaheerabad, Telangana
    #
    # Capacity below is synthetic.
    # --------------------------------------------------------

    {
        "plant_name": "Zaheerabad Plant",
        "city_name": "Zaheerabad",
        "region_name": "South",
        "plant_type": "AUTO_MANUFACTURING",
        "base_daily_capacity": 650,
    },

    # --------------------------------------------------------
    # 6. IGATPURI
    #
    # Reference location:
    #     Igatpuri, Maharashtra
    #
    # This site has a specialized powertrain role in the
    # supplied business reference.
    #
    # We retain AUTO_MANUFACTURING as the normalized PoC
    # plant_type for now because downstream synthetic
    # production generators currently operate on a common
    # automotive-facility abstraction.
    #
    # Capacity below is synthetic.
    # --------------------------------------------------------

    {
        "plant_name": "Igatpuri Plant",
        "city_name": "Igatpuri",
        "region_name": "West",
        "plant_type": "AUTO_MANUFACTURING",
        "base_daily_capacity": 600,
    },

    # --------------------------------------------------------
    # 7. BENGALURU
    #
    # Reference location:
    #     Bengaluru, Karnataka
    #
    # Capacity below is synthetic.
    # --------------------------------------------------------

    {
        "plant_name": "Bengaluru Plant",
        "city_name": "Bengaluru",
        "region_name": "South",
        "plant_type": "AUTO_MANUFACTURING",
        "base_daily_capacity": 800,
    },
]


# ============================================================
# PRODUCTION LINE TEMPLATES
#
# IMPORTANT:
# These are synthetic production-line assumptions.
# They are not intended to reproduce actual plant layouts.
# ============================================================

LINE_TYPES: list[dict[str, Any]] = [

    {
        "line_type": "BODY",
        "line_name_suffix": "Body Line",
        "base_units_per_hour": 38,
    },

    {
        "line_type": "PAINT",
        "line_name_suffix": "Paint Line",
        "base_units_per_hour": 34,
    },

    {
        "line_type": "ASSEMBLY",
        "line_name_suffix": "Assembly Line",
        "base_units_per_hour": 36,
    },

    {
        "line_type": "QUALITY",
        "line_name_suffix": "Quality Line",
        "base_units_per_hour": 30,
    },
]


# ============================================================
# INTERNAL HELPERS
# ============================================================


def _as_positive_int(
    value: Any,
    name: str,
) -> int:
    """
    Convert a configuration value into a positive integer.
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


# ============================================================
# PLANT GENERATOR
# ============================================================


def generate_plants(
    geography_cities: pd.DataFrame | None = None,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate plant master data.

    If geography_cities is supplied, each plant's city and
    region are checked against the geography master.

    Output columns:

        plant_id
        plant_name
        city_name
        region_name
        plant_type
        daily_capacity_units
        data_origin
        generator_version
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    # --------------------------------------------------------
    # Read plant count from generation.yaml
    # --------------------------------------------------------

    try:
        plant_count = _as_positive_int(
            generation[
                "master"
            ][
                "plants"
            ][
                "count"
            ],
            "generation.master.plants.count",
        )

    except KeyError as exc:
        raise KeyError(
            "Missing configuration key: "
            "generation.master.plants.count"
        ) from exc

    # --------------------------------------------------------
    # Ensure enough canonical templates exist
    # --------------------------------------------------------

    if plant_count > len(
        PLANT_TEMPLATES
    ):
        raise ValueError(
            "Requested plant count exceeds "
            "available plant templates. "
            f"Requested={plant_count}, "
            f"available={len(PLANT_TEMPLATES)}"
        )

    # --------------------------------------------------------
    # Provenance
    #
    # Entire generated dataset remains SYNTHETIC even though
    # plant names and locations are canonical reference
    # anchors.
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
    # Generate plant rows
    # --------------------------------------------------------

    rows: list[
        dict[str, Any]
    ] = []

    for index, template in enumerate(
        PLANT_TEMPLATES[
            :plant_count
        ],
        start=1,
    ):

        rows.append(
            {
                "plant_id":
                    make_entity_id(
                        "plant",
                        index,
                        width=3,
                    ),

                "plant_name":
                    template[
                        "plant_name"
                    ],

                "city_name":
                    template[
                        "city_name"
                    ],

                "region_name":
                    template[
                        "region_name"
                    ],

                "plant_type":
                    template[
                        "plant_type"
                    ],

                "daily_capacity_units":
                    int(
                        template[
                            "base_daily_capacity"
                        ]
                    ),

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    plants = pd.DataFrame(
        rows,
        columns=[
            "plant_id",
            "plant_name",
            "city_name",
            "region_name",
            "plant_type",
            "daily_capacity_units",
            "data_origin",
            "generator_version",
        ],
    )

    validate_plants(
        plants=plants,
        geography_cities=geography_cities,
    )

    return plants


# ============================================================
# PRODUCTION LINE GENERATOR
# ============================================================


def generate_production_lines(
    plants: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate synthetic production lines for every plant.

    Uses:

        generation.master.production_lines_per_plant.min
        generation.master.production_lines_per_plant.max

    Example with:

        min = 2
        max = 4

    Plant 1 -> 2 lines
    Plant 2 -> 3 lines
    Plant 3 -> 4 lines
    Plant 4 -> 2 lines

    The pattern repeats deterministically.

    IMPORTANT:

    Production-line assignments are synthetic PoC topology,
    not actual Mahindra plant-line configurations.

    Output columns:

        production_line_id
        plant_id
        line_name
        line_type
        units_per_hour
        shift_count
        active
        data_origin
        generator_version
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    validate_plants(
        plants
    )

    # --------------------------------------------------------
    # Read configuration
    # --------------------------------------------------------

    try:

        min_lines = _as_positive_int(
            generation[
                "master"
            ][
                "production_lines_per_plant"
            ][
                "min"
            ],
            (
                "generation.master."
                "production_lines_per_plant.min"
            ),
        )

        max_lines = _as_positive_int(
            generation[
                "master"
            ][
                "production_lines_per_plant"
            ][
                "max"
            ],
            (
                "generation.master."
                "production_lines_per_plant.max"
            ),
        )

    except KeyError as exc:

        raise KeyError(
            "Missing configuration under "
            "generation.master."
            "production_lines_per_plant"
        ) from exc

    if min_lines > max_lines:

        raise ValueError(
            "production_lines_per_plant.min "
            "cannot be greater than max"
        )

    if max_lines > len(
        LINE_TYPES
    ):

        raise ValueError(
            "Configured maximum production lines "
            "per plant exceeds available line "
            "templates. "
            f"max={max_lines}, "
            f"templates={len(LINE_TYPES)}"
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
    # Generate lines
    # --------------------------------------------------------

    rows: list[
        dict[str, Any]
    ] = []

    line_counter = 1

    line_span = (
        max_lines
        - min_lines
        + 1
    )

    for plant_index, plant in enumerate(
        plants.itertuples(
            index=False
        ),
        start=0,
    ):

        # Example:
        #
        # min=2 max=4
        #
        # plant 0 -> 2
        # plant 1 -> 3
        # plant 2 -> 4
        # plant 3 -> 2
        #
        # For 7 plants:
        #
        # 2, 3, 4, 2, 3, 4, 2
        #
        # Total = 20 synthetic production lines.

        line_count = (
            min_lines
            + (
                plant_index
                % line_span
            )
        )

        for line_index in range(
            line_count
        ):

            template = (
                LINE_TYPES[
                    line_index
                ]
            )

            rows.append(
                {
                    "production_line_id":
                        make_entity_id(
                            "production_line",
                            line_counter,
                            width=3,
                        ),

                    "plant_id":
                        plant.plant_id,

                    "line_name":
                        (
                            f"{plant.plant_name}"
                            " - "
                            f"{template['line_name_suffix']}"
                            f" {line_index + 1}"
                        ),

                    "line_type":
                        template[
                            "line_type"
                        ],

                    "units_per_hour":
                        int(
                            template[
                                "base_units_per_hour"
                            ]
                        ),

                    "shift_count":
                        3,

                    "active":
                        True,

                    "data_origin":
                        data_origin,

                    "generator_version":
                        generator_version,
                }
            )

            line_counter += 1

    production_lines = pd.DataFrame(
        rows,
        columns=[
            "production_line_id",
            "plant_id",
            "line_name",
            "line_type",
            "units_per_hour",
            "shift_count",
            "active",
            "data_origin",
            "generator_version",
        ],
    )

    validate_production_lines(
        production_lines=production_lines,
        plants=plants,
        min_lines=min_lines,
        max_lines=max_lines,
    )

    return production_lines


# ============================================================
# PLANT VALIDATION
# ============================================================


def validate_plants(
    plants: pd.DataFrame,
    geography_cities: pd.DataFrame | None = None,
) -> None:
    """
    Validate plant master records.
    """

    required_columns = {
        "plant_id",
        "plant_name",
        "city_name",
        "region_name",
        "plant_type",
        "daily_capacity_units",
        "data_origin",
        "generator_version",
    }

    missing_columns = (
        required_columns
        .difference(
            plants.columns
        )
    )

    if missing_columns:

        raise ValueError(
            "Plants DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if plants.empty:

        raise ValueError(
            "Plants DataFrame cannot be empty"
        )

    # --------------------------------------------------------
    # Required fields
    # --------------------------------------------------------

    required_non_null = [
        "plant_id",
        "plant_name",
        "city_name",
        "region_name",
        "plant_type",
    ]

    for column in required_non_null:

        if plants[
            column
        ].isna().any():

            raise ValueError(
                f"Plants contains missing "
                f"values in {column}"
            )

    # --------------------------------------------------------
    # Duplicate IDs
    # --------------------------------------------------------

    if plants[
        "plant_id"
    ].duplicated().any():

        duplicates = (
            plants.loc[
                plants[
                    "plant_id"
                ].duplicated(
                    keep=False
                ),
                "plant_id",
            ]
            .tolist()
        )

        raise ValueError(
            "Duplicate plant_id values "
            f"found: {duplicates}"
        )

    # --------------------------------------------------------
    # Duplicate plant names
    # --------------------------------------------------------

    if plants[
        "plant_name"
    ].duplicated().any():

        duplicates = (
            plants.loc[
                plants[
                    "plant_name"
                ].duplicated(
                    keep=False
                ),
                "plant_name",
            ]
            .tolist()
        )

        raise ValueError(
            "Duplicate plant_name values "
            f"found: {duplicates}"
        )

    # --------------------------------------------------------
    # Capacity validation
    # --------------------------------------------------------

    capacities = pd.to_numeric(
        plants[
            "daily_capacity_units"
        ],
        errors="raise",
    )

    if (
        capacities <= 0
    ).any():

        raise ValueError(
            "All plant daily capacities "
            "must be > 0"
        )

    # --------------------------------------------------------
    # Optional geography validation
    #
    # Expected canonical pairs:
    #
    # Pune       + West
    # Nashik     + West
    # Mumbai     + West
    # Haridwar   + North
    # Zaheerabad + South
    # Igatpuri   + West
    # Bengaluru  + South
    # --------------------------------------------------------

    if geography_cities is not None:

        required_geo_columns = {
            "city_name",
            "region_name",
        }

        geo_missing = (
            required_geo_columns
            .difference(
                geography_cities.columns
            )
        )

        if geo_missing:

            raise ValueError(
                "geography_cities is missing "
                "required columns: "
                + ", ".join(
                    sorted(
                        geo_missing
                    )
                )
            )

        valid_pairs = set(
            zip(
                geography_cities[
                    "city_name"
                ],
                geography_cities[
                    "region_name"
                ],
            )
        )

        invalid_rows = [

            (
                row.city_name,
                row.region_name,
            )

            for row
            in plants.itertuples(
                index=False
            )

            if (
                row.city_name,
                row.region_name,
            )
            not in valid_pairs
        ]

        if invalid_rows:

            raise ValueError(
                "Plants contains city/region "
                "combinations not present in "
                "the geography master: "
                f"{invalid_rows}"
            )


# ============================================================
# PRODUCTION LINE VALIDATION
# ============================================================


def validate_production_lines(
    production_lines: pd.DataFrame,
    plants: pd.DataFrame,
    min_lines: int,
    max_lines: int,
) -> None:
    """
    Validate production-line records.
    """

    required_columns = {
        "production_line_id",
        "plant_id",
        "line_name",
        "line_type",
        "units_per_hour",
        "shift_count",
        "active",
        "data_origin",
        "generator_version",
    }

    missing_columns = (
        required_columns
        .difference(
            production_lines.columns
        )
    )

    if missing_columns:

        raise ValueError(
            "Production-lines DataFrame "
            "is missing required columns: "
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

    # --------------------------------------------------------
    # Duplicate line IDs
    # --------------------------------------------------------

    if production_lines[
        "production_line_id"
    ].duplicated().any():

        duplicates = (
            production_lines.loc[
                production_lines[
                    "production_line_id"
                ].duplicated(
                    keep=False
                ),
                "production_line_id",
            ]
            .tolist()
        )

        raise ValueError(
            "Duplicate production_line_id "
            f"values found: {duplicates}"
        )

    # --------------------------------------------------------
    # Validate plant foreign key
    # --------------------------------------------------------

    valid_plant_ids = set(
        plants[
            "plant_id"
        ]
    )

    invalid_plant_ids = sorted(
        set(
            production_lines[
                "plant_id"
            ]
        )
        .difference(
            valid_plant_ids
        )
    )

    if invalid_plant_ids:

        raise ValueError(
            "Production lines reference "
            "invalid plant_id values: "
            + ", ".join(
                invalid_plant_ids
            )
        )

    # --------------------------------------------------------
    # Units/hour validation
    # --------------------------------------------------------

    units_per_hour = pd.to_numeric(
        production_lines[
            "units_per_hour"
        ],
        errors="raise",
    )

    if (
        units_per_hour <= 0
    ).any():

        raise ValueError(
            "All production-line "
            "units_per_hour values "
            "must be > 0"
        )

    # --------------------------------------------------------
    # Shift validation
    # --------------------------------------------------------

    shifts = pd.to_numeric(
        production_lines[
            "shift_count"
        ],
        errors="raise",
    )

    if (
        shifts <= 0
    ).any():

        raise ValueError(
            "All production-line "
            "shift_count values "
            "must be > 0"
        )

    # --------------------------------------------------------
    # Ensure every plant has between min/max lines
    # --------------------------------------------------------

    counts = (
        production_lines
        .groupby(
            "plant_id"
        )
        .size()
    )

    for plant_id in valid_plant_ids:

        count = int(
            counts.get(
                plant_id,
                0,
            )
        )

        if not (
            min_lines
            <= count
            <= max_lines
        ):

            raise ValueError(
                f"Plant {plant_id} has "
                f"{count} production lines. "
                f"Expected between "
                f"{min_lines} and "
                f"{max_lines}."
            )


# ============================================================
# MAIN MASTER GENERATOR
# ============================================================


def generate_plant_master(
    geography_cities: pd.DataFrame | None = None,
    generation: Mapping[str, Any] | None = None,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Generate both:

        plants
        production_lines

    Returns:

        plants_df,
        production_lines_df
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    plants = generate_plants(
        geography_cities=geography_cities,
        generation=generation,
    )

    production_lines = (
        generate_production_lines(
            plants=plants,
            generation=generation,
        )
    )

    return (
        plants,
        production_lines,
    )


# ============================================================
# LOCAL TEST
# ============================================================


if __name__ == "__main__":

    # Geography master is generated first so canonical plant
    # locations are validated before production lines are built.

    from data.generators.master.geography import (
        generate_geography,
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

    print(
        "\n=== PLANTS ===\n"
    )

    print(
        plants_df.to_string(
            index=False
        )
    )

    print(
        "\n=== PRODUCTION LINES ===\n"
    )

    print(
        production_lines_df.to_string(
            index=False
        )
    )

    print(
        "\nGenerated "
        f"{len(plants_df)} plants and "
        f"{len(production_lines_df)} "
        "production lines successfully."
    )