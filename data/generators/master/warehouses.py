"""
Warehouse master-data generator for Mahindra AI Nexus.

Generates:
- Warehouse master records

Every warehouse is linked to a valid city and region from
the geography master.

This module DOES NOT write CSV files.

Later:
    data/scripts/generate_all.py

will save the returned DataFrame as:

    data/synthetic/master/warehouses.csv

IMPORTANT:
Warehouse names, capacities and utilization values are synthetic
engineering assumptions for the PoC and are NOT actual Mahindra data.
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
# SYNTHETIC WAREHOUSE TEMPLATES
# ============================================================

WAREHOUSE_TEMPLATES: list[dict[str, Any]] = [
    {
        "warehouse_name": "Pune Distribution Hub",
        "city_name": "Pune",
        "region_name": "West",
        "warehouse_type": "REGIONAL_DISTRIBUTION_CENTER",
        "storage_capacity_units": 8500,
        "baseline_utilization_pct": 0.68,
        "daily_throughput_capacity": 900,
    },
    {
        "warehouse_name": "Mumbai Distribution Hub",
        "city_name": "Mumbai",
        "region_name": "West",
        "warehouse_type": "REGIONAL_DISTRIBUTION_CENTER",
        "storage_capacity_units": 10000,
        "baseline_utilization_pct": 0.72,
        "daily_throughput_capacity": 1100,
    },
    {
        "warehouse_name": "Delhi Distribution Hub",
        "city_name": "Delhi",
        "region_name": "North",
        "warehouse_type": "REGIONAL_DISTRIBUTION_CENTER",
        "storage_capacity_units": 9500,
        "baseline_utilization_pct": 0.70,
        "daily_throughput_capacity": 1050,
    },
    {
        "warehouse_name": "Jaipur Distribution Hub",
        "city_name": "Jaipur",
        "region_name": "North",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 6500,
        "baseline_utilization_pct": 0.61,
        "daily_throughput_capacity": 700,
    },
    {
        "warehouse_name": "Bengaluru Distribution Hub",
        "city_name": "Bengaluru",
        "region_name": "South",
        "warehouse_type": "REGIONAL_DISTRIBUTION_CENTER",
        "storage_capacity_units": 9000,
        "baseline_utilization_pct": 0.69,
        "daily_throughput_capacity": 950,
    },
    {
        "warehouse_name": "Chennai Distribution Hub",
        "city_name": "Chennai",
        "region_name": "South",
        "warehouse_type": "REGIONAL_DISTRIBUTION_CENTER",
        "storage_capacity_units": 8800,
        "baseline_utilization_pct": 0.67,
        "daily_throughput_capacity": 920,
    },
    {
        "warehouse_name": "Kolkata Distribution Hub",
        "city_name": "Kolkata",
        "region_name": "East",
        "warehouse_type": "REGIONAL_DISTRIBUTION_CENTER",
        "storage_capacity_units": 8200,
        "baseline_utilization_pct": 0.65,
        "daily_throughput_capacity": 850,
    },
    {
        "warehouse_name": "Bhubaneswar Distribution Hub",
        "city_name": "Bhubaneswar",
        "region_name": "East",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 6000,
        "baseline_utilization_pct": 0.58,
        "daily_throughput_capacity": 650,
    },
    # --------------------------------------------------------
    # Expansion set — added to widen the Logistics AI Control
    # Tower's route network beyond the original 8-warehouse set.
    # First 8 below reuse cities already present in the geography
    # master (see distributions.yaml); the remaining 10 add new
    # cities there too.
    # --------------------------------------------------------
    {
        "warehouse_name": "Nashik Warehouse",
        "city_name": "Nashik",
        "region_name": "West",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 6200,
        "baseline_utilization_pct": 0.60,
        "daily_throughput_capacity": 620,
    },
    {
        "warehouse_name": "Ahmedabad Distribution Hub",
        "city_name": "Ahmedabad",
        "region_name": "West",
        "warehouse_type": "REGIONAL_DISTRIBUTION_CENTER",
        "storage_capacity_units": 8700,
        "baseline_utilization_pct": 0.66,
        "daily_throughput_capacity": 910,
    },
    {
        "warehouse_name": "Lucknow Warehouse",
        "city_name": "Lucknow",
        "region_name": "North",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 6200,
        "baseline_utilization_pct": 0.62,
        "daily_throughput_capacity": 680,
    },
    {
        "warehouse_name": "Haridwar Warehouse",
        "city_name": "Haridwar",
        "region_name": "North",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 5200,
        "baseline_utilization_pct": 0.55,
        "daily_throughput_capacity": 560,
    },
    {
        "warehouse_name": "Hyderabad Distribution Hub",
        "city_name": "Hyderabad",
        "region_name": "South",
        "warehouse_type": "REGIONAL_DISTRIBUTION_CENTER",
        "storage_capacity_units": 9200,
        "baseline_utilization_pct": 0.71,
        "daily_throughput_capacity": 970,
    },
    {
        "warehouse_name": "Coimbatore Warehouse",
        "city_name": "Coimbatore",
        "region_name": "South",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 6000,
        "baseline_utilization_pct": 0.59,
        "daily_throughput_capacity": 640,
    },
    {
        "warehouse_name": "Guwahati Warehouse",
        "city_name": "Guwahati",
        "region_name": "East",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 5000,
        "baseline_utilization_pct": 0.54,
        "daily_throughput_capacity": 520,
    },
    {
        "warehouse_name": "Patna Warehouse",
        "city_name": "Patna",
        "region_name": "East",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 5400,
        "baseline_utilization_pct": 0.57,
        "daily_throughput_capacity": 560,
    },
    {
        "warehouse_name": "Bhiwandi Distribution Hub",
        "city_name": "Bhiwandi",
        "region_name": "West",
        "warehouse_type": "REGIONAL_DISTRIBUTION_CENTER",
        "storage_capacity_units": 9800,
        "baseline_utilization_pct": 0.74,
        "daily_throughput_capacity": 1050,
    },
    {
        "warehouse_name": "Phaltan Warehouse",
        "city_name": "Phaltan",
        "region_name": "West",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 4200,
        "baseline_utilization_pct": 0.52,
        "daily_throughput_capacity": 420,
    },
    {
        "warehouse_name": "Chakan Warehouse",
        "city_name": "Chakan",
        "region_name": "West",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 7000,
        "baseline_utilization_pct": 0.65,
        "daily_throughput_capacity": 780,
    },
    {
        "warehouse_name": "Luhari Warehouse",
        "city_name": "Luhari",
        "region_name": "North",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 6400,
        "baseline_utilization_pct": 0.53,
        "daily_throughput_capacity": 480,
    },
    {
        "warehouse_name": "Cuddalore Warehouse",
        "city_name": "Cuddalore",
        "region_name": "South",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 4600,
        "baseline_utilization_pct": 0.51,
        "daily_throughput_capacity": 460,
    },
    {
        "warehouse_name": "Hosur Warehouse",
        "city_name": "Hosur",
        "region_name": "South",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 6800,
        "baseline_utilization_pct": 0.63,
        "daily_throughput_capacity": 720,
    },
    {
        "warehouse_name": "Malda Warehouse",
        "city_name": "Malda",
        "region_name": "East",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 4000,
        "baseline_utilization_pct": 0.49,
        "daily_throughput_capacity": 400,
    },
    {
        "warehouse_name": "Agartala Warehouse",
        "city_name": "Agartala",
        "region_name": "East",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 3800,
        "baseline_utilization_pct": 0.47,
        "daily_throughput_capacity": 380,
    },
    {
        "warehouse_name": "Indore Distribution Hub",
        "city_name": "Indore",
        "region_name": "West",
        "warehouse_type": "REGIONAL_DISTRIBUTION_CENTER",
        "storage_capacity_units": 8200,
        "baseline_utilization_pct": 0.64,
        "daily_throughput_capacity": 860,
    },
    {
        "warehouse_name": "Bhopal Warehouse",
        "city_name": "Bhopal",
        "region_name": "West",
        "warehouse_type": "REGIONAL_WAREHOUSE",
        "storage_capacity_units": 6400,
        "baseline_utilization_pct": 0.60,
        "daily_throughput_capacity": 680,
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


# ============================================================
# GENERATOR
# ============================================================


def generate_warehouses(
    geography_cities: pd.DataFrame | None = None,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate warehouse master records.

    Output columns:

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
    """

    if generation is None:
        generation = load_generation_config()

    # --------------------------------------------------------
    # Read warehouse count
    # --------------------------------------------------------

    try:
        warehouse_count = _as_positive_int(
            generation[
                "master"
            ][
                "warehouses"
            ][
                "count"
            ],
            "generation.master.warehouses.count",
        )

    except KeyError as exc:
        raise KeyError(
            "Missing configuration key: "
            "generation.master.warehouses.count"
        ) from exc

    if warehouse_count > len(
        WAREHOUSE_TEMPLATES
    ):
        raise ValueError(
            "Requested warehouse count exceeds "
            "available warehouse templates. "
            f"Requested={warehouse_count}, "
            f"available={len(WAREHOUSE_TEMPLATES)}"
        )

    # --------------------------------------------------------
    # Geography lookup
    # --------------------------------------------------------

    city_lookup: dict[
        tuple[str, str],
        dict[str, str],
    ] = {}

    if geography_cities is not None:

        _validate_geography_input(
            geography_cities
        )

        for row in geography_cities.itertuples(
            index=False
        ):

            city_lookup[
                (
                    row.city_name,
                    row.region_name,
                )
            ] = {
                "city_id":
                    row.city_id,

                "region_id":
                    row.region_id,
            }

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
    # Generate records
    # --------------------------------------------------------

    rows: list[
        dict[str, Any]
    ] = []

    selected_templates = (
        WAREHOUSE_TEMPLATES[
            :warehouse_count
        ]
    )

    for index, template in enumerate(
        selected_templates,
        start=1,
    ):

        city_name = template[
            "city_name"
        ]

        region_name = template[
            "region_name"
        ]

        city_id = None
        region_id = None

        if geography_cities is not None:

            key = (
                city_name,
                region_name,
            )

            if key not in city_lookup:
                raise ValueError(
                    "Warehouse template references "
                    "a city/region combination not "
                    "present in geography master: "
                    f"{city_name}, {region_name}"
                )

            city_id = (
                city_lookup[
                    key
                ][
                    "city_id"
                ]
            )

            region_id = (
                city_lookup[
                    key
                ][
                    "region_id"
                ]
            )

        rows.append(
            {
                "warehouse_id":
                    make_entity_id(
                        "warehouse",
                        index,
                        width=3,
                    ),

                "warehouse_name":
                    template[
                        "warehouse_name"
                    ],

                "city_id":
                    city_id,

                "city_name":
                    city_name,

                "region_id":
                    region_id,

                "region_name":
                    region_name,

                "warehouse_type":
                    template[
                        "warehouse_type"
                    ],

                "storage_capacity_units":
                    int(
                        template[
                            "storage_capacity_units"
                        ]
                    ),

                "baseline_utilization_pct":
                    float(
                        template[
                            "baseline_utilization_pct"
                        ]
                    ),

                "daily_throughput_capacity":
                    int(
                        template[
                            "daily_throughput_capacity"
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

    warehouses = pd.DataFrame(
        rows,
        columns=[
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
        ],
    )

    validate_warehouses(
        warehouses=warehouses,
        geography_cities=geography_cities,
        expected_count=warehouse_count,
    )

    return warehouses


# ============================================================
# GEOGRAPHY INPUT VALIDATION
# ============================================================


def _validate_geography_input(
    geography_cities: pd.DataFrame,
) -> None:
    """
    Validate geography input required by warehouse generator.
    """

    required_columns = {
        "city_id",
        "city_name",
        "region_id",
        "region_name",
    }

    missing_columns = (
        required_columns
        .difference(
            geography_cities.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "Geography DataFrame is missing "
            "columns required by warehouses.py: "
            + ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if geography_cities.empty:
        raise ValueError(
            "Geography cities DataFrame "
            "cannot be empty"
        )

    if geography_cities[
        "city_id"
    ].duplicated().any():
        raise ValueError(
            "Duplicate city_id values found "
            "in geography master"
        )


# ============================================================
# VALIDATION
# ============================================================


def validate_warehouses(
    warehouses: pd.DataFrame,
    geography_cities: pd.DataFrame | None = None,
    expected_count: int | None = None,
) -> None:
    """
    Validate warehouse master records.
    """

    required_columns = {
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

    missing_columns = (
        required_columns
        .difference(
            warehouses.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "Warehouses DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if warehouses.empty:
        raise ValueError(
            "Warehouses DataFrame cannot be empty"
        )

    # --------------------------------------------------------
    # Expected count
    # --------------------------------------------------------

    if (
        expected_count is not None
        and len(warehouses) != expected_count
    ):
        raise ValueError(
            f"Expected {expected_count} warehouses "
            f"but generated {len(warehouses)}."
        )

    # --------------------------------------------------------
    # Required values
    # --------------------------------------------------------

    required_non_null = [
        "warehouse_id",
        "warehouse_name",
        "city_name",
        "region_name",
        "warehouse_type",
    ]

    for column in required_non_null:

        if warehouses[
            column
        ].isna().any():

            raise ValueError(
                f"Warehouses contains missing "
                f"values in {column}"
            )

    # --------------------------------------------------------
    # Unique warehouse IDs
    # --------------------------------------------------------

    if warehouses[
        "warehouse_id"
    ].duplicated().any():

        duplicates = (
            warehouses.loc[
                warehouses[
                    "warehouse_id"
                ].duplicated(
                    keep=False
                ),
                "warehouse_id",
            ]
            .tolist()
        )

        raise ValueError(
            "Duplicate warehouse_id values "
            f"found: {duplicates}"
        )

    # --------------------------------------------------------
    # Unique warehouse names
    # --------------------------------------------------------

    if warehouses[
        "warehouse_name"
    ].duplicated().any():

        duplicates = (
            warehouses.loc[
                warehouses[
                    "warehouse_name"
                ].duplicated(
                    keep=False
                ),
                "warehouse_name",
            ]
            .tolist()
        )

        raise ValueError(
            "Duplicate warehouse names "
            f"found: {duplicates}"
        )

    # --------------------------------------------------------
    # Storage capacity
    # --------------------------------------------------------

    storage = pd.to_numeric(
        warehouses[
            "storage_capacity_units"
        ],
        errors="raise",
    )

    if (
        storage <= 0
    ).any():
        raise ValueError(
            "storage_capacity_units "
            "must be > 0"
        )

    # --------------------------------------------------------
    # Throughput capacity
    # --------------------------------------------------------

    throughput = pd.to_numeric(
        warehouses[
            "daily_throughput_capacity"
        ],
        errors="raise",
    )

    if (
        throughput <= 0
    ).any():
        raise ValueError(
            "daily_throughput_capacity "
            "must be > 0"
        )

    # --------------------------------------------------------
    # Utilization must be between 0 and 1
    # --------------------------------------------------------

    utilization = pd.to_numeric(
        warehouses[
            "baseline_utilization_pct"
        ],
        errors="raise",
    )

    if (
        (utilization < 0)
        | (utilization > 1)
    ).any():

        raise ValueError(
            "baseline_utilization_pct "
            "must be between 0 and 1"
        )

    # --------------------------------------------------------
    # Geography foreign-key validation
    # --------------------------------------------------------

    if geography_cities is not None:

        _validate_geography_input(
            geography_cities
        )

        valid_city_ids = set(
            geography_cities[
                "city_id"
            ]
        )

        valid_region_ids = set(
            geography_cities[
                "region_id"
            ]
        )

        invalid_city_ids = sorted(
            set(
                warehouses[
                    "city_id"
                ]
            )
            .difference(
                valid_city_ids
            )
        )

        if invalid_city_ids:

            raise ValueError(
                "Warehouses reference invalid "
                "city_id values: "
                + ", ".join(
                    invalid_city_ids
                )
            )

        invalid_region_ids = sorted(
            set(
                warehouses[
                    "region_id"
                ]
            )
            .difference(
                valid_region_ids
            )
        )

        if invalid_region_ids:

            raise ValueError(
                "Warehouses reference invalid "
                "region_id values: "
                + ", ".join(
                    invalid_region_ids
                )
            )

        # ----------------------------------------------------
        # Validate exact city-region mapping
        # ----------------------------------------------------

        geography_lookup = {
            row.city_id: {
                "city_name":
                    row.city_name,

                "region_id":
                    row.region_id,

                "region_name":
                    row.region_name,
            }
            for row
            in geography_cities.itertuples(
                index=False
            )
        }

        for warehouse in warehouses.itertuples(
            index=False
        ):

            geo = geography_lookup[
                warehouse.city_id
            ]

            if (
                warehouse.city_name
                != geo["city_name"]
            ):
                raise ValueError(
                    "Warehouse city_name does not "
                    "match geography master for "
                    f"{warehouse.warehouse_id}"
                )

            if (
                warehouse.region_id
                != geo["region_id"]
            ):
                raise ValueError(
                    "Warehouse region_id does not "
                    "match geography master for "
                    f"{warehouse.warehouse_id}"
                )

            if (
                warehouse.region_name
                != geo["region_name"]
            ):
                raise ValueError(
                    "Warehouse region_name does not "
                    "match geography master for "
                    f"{warehouse.warehouse_id}"
                )


# ============================================================
# PUBLIC MASTER GENERATOR
# ============================================================


def generate_warehouse_master(
    geography_cities: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Public function that generate_all.py will use later.

    Returns:
        warehouses_df
    """

    return generate_warehouses(
        geography_cities=geography_cities,
        generation=generation,
    )


# ============================================================
# LOCAL TEST
# ============================================================


if __name__ == "__main__":

    from data.generators.master.geography import (
        generate_geography,
    )

    # ---------------------------------------------
    # Geography
    #     ↓
    # Warehouses
    # ---------------------------------------------

    _, cities_df = (
        generate_geography()
    )

    warehouses_df = (
        generate_warehouse_master(
            geography_cities=cities_df
        )
    )

    print(
        "\n=== WAREHOUSES ===\n"
    )

    print(
        warehouses_df.to_string(
            index=False
        )
    )

    print(
        "\n=== WAREHOUSES BY REGION ===\n"
    )

    region_counts = (
        warehouses_df
        .groupby(
            "region_name"
        )
        .size()
        .reset_index(
            name="warehouse_count"
        )
    )

    print(
        region_counts.to_string(
            index=False
        )
    )

    print(
        "\nGenerated "
        f"{len(warehouses_df)} "
        "warehouses successfully."
    )