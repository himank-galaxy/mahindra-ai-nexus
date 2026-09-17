"""
Logistics Route master-data generator for Mahindra AI Nexus.

Generates:
- Logistics route master records between warehouses.

Every route:
- references a valid origin warehouse
- references a valid destination warehouse
- never has the same origin and destination
- has deterministic synthetic distance, transit time, SLA and cost

This module DOES NOT write CSV files.

Later:
    data/scripts/generate_all.py

will save the returned DataFrame as:

    data/synthetic/master/logistics_routes.csv

IMPORTANT:
Distances, costs, SLA values and transit assumptions are synthetic
engineering assumptions for the PoC.
They are NOT actual Mahindra logistics data.
"""

from __future__ import annotations

import math

from typing import Any, Mapping

import pandas as pd

from data.generators.common.helpers import (
    load_generation_config,
)

from data.generators.common.ids import (
    make_entity_id,
)


# ============================================================
# SYNTHETIC CITY COORDINATES
#
# Used only to create realistic relative route distances.
# These are approximate reference coordinates.
# ============================================================

CITY_COORDINATES: dict[
    str,
    tuple[float, float],
] = {

    "Pune": (
        18.5204,
        73.8567,
    ),

    "Mumbai": (
        19.0760,
        72.8777,
    ),

    "Delhi": (
        28.6139,
        77.2090,
    ),

    "Jaipur": (
        26.9124,
        75.7873,
    ),

    "Bengaluru": (
        12.9716,
        77.5946,
    ),

    "Chennai": (
        13.0827,
        80.2707,
    ),

    "Kolkata": (
        22.5726,
        88.3639,
    ),

    "Bhubaneswar": (
        20.2961,
        85.8245,
    ),
}


# ============================================================
# SYNTHETIC LOGISTICS ASSUMPTIONS
# ============================================================

ROAD_DISTANCE_FACTOR = 1.18

AVERAGE_ROAD_SPEED_KMPH = 48.0

FIXED_HANDLING_HOURS = 3.0

COST_PER_KM_INR = 62.0

FIXED_ROUTE_COST_INR = 2500.0


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

    if isinstance(
        value,
        bool,
    ):
        raise TypeError(
            f"{name} must be an integer, not bool"
        )

    try:
        result = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as exc:

        raise TypeError(
            f"{name} must be an integer"
        ) from exc

    if result <= 0:
        raise ValueError(
            f"{name} must be > 0"
        )

    return result


def _haversine_distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculate straight-line distance between two coordinates.

    The value is later multiplied by ROAD_DISTANCE_FACTOR
    to approximate a synthetic road distance.
    """

    earth_radius_km = 6371.0

    lat1_rad = math.radians(
        lat1
    )

    lon1_rad = math.radians(
        lon1
    )

    lat2_rad = math.radians(
        lat2
    )

    lon2_rad = math.radians(
        lon2
    )

    delta_lat = (
        lat2_rad
        - lat1_rad
    )

    delta_lon = (
        lon2_rad
        - lon1_rad
    )

    a = (
        math.sin(
            delta_lat / 2
        ) ** 2
        +
        math.cos(
            lat1_rad
        )
        *
        math.cos(
            lat2_rad
        )
        *
        math.sin(
            delta_lon / 2
        ) ** 2
    )

    c = (
        2
        * math.atan2(
            math.sqrt(a),
            math.sqrt(
                1 - a
            ),
        )
    )

    return (
        earth_radius_km
        * c
    )


def _calculate_route_distance(
    origin_city: str,
    destination_city: str,
    origin_region: str,
    destination_region: str,
) -> float:
    """
    Calculate synthetic road distance.

    Preferred method:
        city coordinates -> haversine -> road factor

    Fallback:
        deterministic regional distance assumption
    """

    if (
        origin_city
        in CITY_COORDINATES
        and destination_city
        in CITY_COORDINATES
    ):

        (
            lat1,
            lon1,
        ) = CITY_COORDINATES[
            origin_city
        ]

        (
            lat2,
            lon2,
        ) = CITY_COORDINATES[
            destination_city
        ]

        straight_line = (
            _haversine_distance_km(
                lat1,
                lon1,
                lat2,
                lon2,
            )
        )

        road_distance = (
            straight_line
            * ROAD_DISTANCE_FACTOR
        )

        return round(
            road_distance,
            1,
        )

    # --------------------------------------------------------
    # Fallback if new cities are added later.
    # --------------------------------------------------------

    if (
        origin_region
        == destination_region
    ):
        return 450.0

    return 1100.0


def _calculate_transit_hours(
    distance_km: float,
) -> float:
    """
    Estimate synthetic normal transit duration.

    Transit =
        road travel time
        +
        loading / unloading / handling time
    """

    drive_hours = (
        distance_km
        / AVERAGE_ROAD_SPEED_KMPH
    )

    transit = (
        drive_hours
        + FIXED_HANDLING_HOURS
    )

    return round(
        transit,
        1,
    )


def _calculate_sla_hours(
    normal_transit_hours: float,
) -> int:
    """
    Generate a slightly relaxed SLA relative to
    typical transit duration.

    Adds approximately 20% buffer and rounds upward.
    """

    buffered = (
        normal_transit_hours
        * 1.20
    )

    return int(
        math.ceil(
            buffered
        )
    )


def _calculate_route_cost(
    distance_km: float,
) -> float:
    """
    Synthetic baseline logistics cost.

    Cost =
        fixed route cost
        +
        distance-based variable cost
    """

    cost = (
        FIXED_ROUTE_COST_INR
        + (
            distance_km
            * COST_PER_KM_INR
        )
    )

    return round(
        cost,
        2,
    )


def _calculate_route_risk(
    distance_km: float,
    origin_region: str,
    destination_region: str,
) -> float:
    """
    Generate a baseline route risk score in [0, 1].

    Longer and inter-region lanes get slightly
    higher baseline risk.

    This is only a master-data baseline.
    Actual shipment risk later comes from operational data.
    """

    distance_component = min(
        distance_km / 2500.0,
        1.0,
    )

    inter_region_component = (
        0.12
        if origin_region
        != destination_region
        else 0.03
    )

    risk = (
        0.08
        + (
            0.25
            * distance_component
        )
        + inter_region_component
    )

    return round(
        min(
            risk,
            1.0,
        ),
        4,
    )


# ============================================================
# INPUT VALIDATION
# ============================================================


def _validate_warehouse_input(
    warehouses: pd.DataFrame,
) -> None:
    """
    Validate warehouse fields needed by routes.py.
    """

    required_columns = {
        "warehouse_id",
        "warehouse_name",
        "city_id",
        "city_name",
        "region_id",
        "region_name",
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
            "columns required by routes.py: "
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

    for column in required_columns:

        if warehouses[
            column
        ].isna().any():

            raise ValueError(
                "Warehouses DataFrame contains "
                f"missing values in {column}"
            )

    if warehouses[
        "warehouse_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate warehouse_id values "
            "found in warehouse master"
        )

    if len(
        warehouses
    ) < 2:

        raise ValueError(
            "At least two warehouses are required "
            "to generate logistics routes"
        )


# ============================================================
# ROUTE GENERATOR
# ============================================================


def generate_routes(
    warehouses: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate logistics route master records.

    Output columns:

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
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    _validate_warehouse_input(
        warehouses
    )

    # --------------------------------------------------------
    # Route count
    # --------------------------------------------------------

    try:

        route_count = (
            _as_positive_int(
                generation[
                    "master"
                ][
                    "logistics_routes"
                ][
                    "target_count"
                ],
                "generation.master."
                "logistics_routes.target_count"
            )
        )

    except KeyError as exc:

        raise KeyError(
            "Missing configuration key: "
            "generation.master."
            "logistics_routes.target_count"
        ) from exc

    warehouse_count = len(
        warehouses
    )

    # Directed route:
    #
    # A -> B
    # and
    # B -> A
    #
    # are allowed as different routes.
    #
    # Maximum possible routes:
    #
    # n * (n - 1)
    # --------------------------------------------------------

    maximum_routes = (
        warehouse_count
        * (
            warehouse_count - 1
        )
    )

    if route_count > maximum_routes:

        raise ValueError(
            "Requested route count exceeds "
            "maximum possible unique directed "
            "warehouse routes. "
            f"Requested={route_count}, "
            f"maximum={maximum_routes}"
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
    # Create deterministic candidate lane list.
    #
    # We rotate destination offsets:
    #
    # offset = 1
    # WH1 -> WH2
    # WH2 -> WH3
    # ...
    #
    # offset = 2
    # WH1 -> WH3
    # WH2 -> WH4
    #
    # This generates unique and geographically diverse routes
    # without random route duplication.
    # --------------------------------------------------------

    warehouse_records = list(
        warehouses.itertuples(
            index=False
        )
    )

    candidate_pairs: list[
        tuple[Any, Any]
    ] = []

    for offset in range(
        1,
        warehouse_count,
    ):

        for origin_index in range(
            warehouse_count
        ):

            destination_index = (
                origin_index
                + offset
            ) % warehouse_count

            origin = (
                warehouse_records[
                    origin_index
                ]
            )

            destination = (
                warehouse_records[
                    destination_index
                ]
            )

            candidate_pairs.append(
                (
                    origin,
                    destination,
                )
            )

    selected_pairs = (
        candidate_pairs[
            :route_count
        ]
    )

    # --------------------------------------------------------
    # Build records
    # --------------------------------------------------------

    rows: list[
        dict[str, Any]
    ] = []

    for route_number, (
        origin,
        destination,
    ) in enumerate(
        selected_pairs,
        start=1,
    ):

        distance_km = (
            _calculate_route_distance(
                origin_city=
                    origin.city_name,

                destination_city=
                    destination.city_name,

                origin_region=
                    origin.region_name,

                destination_region=
                    destination.region_name,
            )
        )

        transit_hours = (
            _calculate_transit_hours(
                distance_km
            )
        )

        sla_hours = (
            _calculate_sla_hours(
                transit_hours
            )
        )

        baseline_cost = (
            _calculate_route_cost(
                distance_km
            )
        )

        baseline_risk = (
            _calculate_route_risk(
                distance_km=
                    distance_km,

                origin_region=
                    origin.region_name,

                destination_region=
                    destination.region_name,
            )
        )

        route_type = (
            "INTRA_REGION"
            if origin.region_id
            == destination.region_id
            else "INTER_REGION"
        )

        rows.append(
            {
                "route_id":
                    make_entity_id(
                        "route",
                        route_number,
                        width=3,
                    ),

                # --------------------------------------------
                # Origin
                # --------------------------------------------

                "origin_warehouse_id":
                    origin.warehouse_id,

                "origin_warehouse_name":
                    origin.warehouse_name,

                "origin_city_id":
                    origin.city_id,

                "origin_city_name":
                    origin.city_name,

                "origin_region_id":
                    origin.region_id,

                "origin_region_name":
                    origin.region_name,

                # --------------------------------------------
                # Destination
                # --------------------------------------------

                "destination_warehouse_id":
                    destination.warehouse_id,

                "destination_warehouse_name":
                    destination.warehouse_name,

                "destination_city_id":
                    destination.city_id,

                "destination_city_name":
                    destination.city_name,

                "destination_region_id":
                    destination.region_id,

                "destination_region_name":
                    destination.region_name,

                # --------------------------------------------
                # Route properties
                # --------------------------------------------

                "route_type":
                    route_type,

                "transport_mode":
                    "ROAD",

                "distance_km":
                    distance_km,

                "typical_transit_hours":
                    transit_hours,

                "sla_hours":
                    sla_hours,

                "baseline_cost_inr":
                    baseline_cost,

                "baseline_risk_score":
                    baseline_risk,

                "active":
                    True,

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    routes = pd.DataFrame(
        rows,
        columns=[
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
        ],
    )

    validate_routes(
        routes=routes,
        warehouses=warehouses,
        expected_count=route_count,
    )

    return routes


# ============================================================
# ROUTE VALIDATION
# ============================================================


def validate_routes(
    routes: pd.DataFrame,
    warehouses: pd.DataFrame,
    expected_count: int | None = None,
) -> None:
    """
    Validate logistics route master records.
    """

    required_columns = {
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

    missing_columns = (
        required_columns
        .difference(
            routes.columns
        )
    )

    if missing_columns:

        raise ValueError(
            "Routes DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if routes.empty:

        raise ValueError(
            "Routes DataFrame cannot be empty"
        )

    # --------------------------------------------------------
    # Count validation
    # --------------------------------------------------------

    if (
        expected_count is not None
        and len(
            routes
        )
        != expected_count
    ):

        raise ValueError(
            f"Expected {expected_count} routes "
            f"but generated {len(routes)}."
        )

    # --------------------------------------------------------
    # Route ID uniqueness
    # --------------------------------------------------------

    if routes[
        "route_id"
    ].duplicated().any():

        duplicates = (
            routes.loc[
                routes[
                    "route_id"
                ].duplicated(
                    keep=False
                ),
                "route_id",
            ]
            .tolist()
        )

        raise ValueError(
            "Duplicate route_id values found: "
            f"{duplicates}"
        )

    # --------------------------------------------------------
    # Valid warehouse foreign keys
    # --------------------------------------------------------

    valid_warehouse_ids = set(
        warehouses[
            "warehouse_id"
        ]
    )

    invalid_origins = sorted(
        set(
            routes[
                "origin_warehouse_id"
            ]
        )
        .difference(
            valid_warehouse_ids
        )
    )

    if invalid_origins:

        raise ValueError(
            "Routes reference invalid origin "
            "warehouse IDs: "
            + ", ".join(
                invalid_origins
            )
        )

    invalid_destinations = sorted(
        set(
            routes[
                "destination_warehouse_id"
            ]
        )
        .difference(
            valid_warehouse_ids
        )
    )

    if invalid_destinations:

        raise ValueError(
            "Routes reference invalid destination "
            "warehouse IDs: "
            + ", ".join(
                invalid_destinations
            )
        )

    # --------------------------------------------------------
    # No route can go warehouse -> same warehouse
    # --------------------------------------------------------

    same_origin_destination = (
        routes[
            "origin_warehouse_id"
        ]
        ==
        routes[
            "destination_warehouse_id"
        ]
    )

    if (
        same_origin_destination.any()
    ):

        raise ValueError(
            "A logistics route cannot have "
            "the same origin and destination "
            "warehouse."
        )

    # --------------------------------------------------------
    # No duplicate lane combinations
    # --------------------------------------------------------

    duplicate_pairs = (
        routes.duplicated(
            subset=[
                "origin_warehouse_id",
                "destination_warehouse_id",
            ],
            keep=False,
        )
    )

    if duplicate_pairs.any():

        duplicates = (
            routes.loc[
                duplicate_pairs,
                [
                    "origin_warehouse_id",
                    "destination_warehouse_id",
                ],
            ]
            .to_dict(
                orient="records"
            )
        )

        raise ValueError(
            "Duplicate origin/destination "
            f"routes found: {duplicates}"
        )

    # --------------------------------------------------------
    # Distances
    # --------------------------------------------------------

    distances = pd.to_numeric(
        routes[
            "distance_km"
        ],
        errors="raise",
    )

    if (
        distances <= 0
    ).any():

        raise ValueError(
            "All route distances must be > 0"
        )

    # --------------------------------------------------------
    # Transit time
    # --------------------------------------------------------

    transit = pd.to_numeric(
        routes[
            "typical_transit_hours"
        ],
        errors="raise",
    )

    if (
        transit <= 0
    ).any():

        raise ValueError(
            "All typical_transit_hours "
            "values must be > 0"
        )

    # --------------------------------------------------------
    # SLA
    # --------------------------------------------------------

    sla = pd.to_numeric(
        routes[
            "sla_hours"
        ],
        errors="raise",
    )

    if (
        sla <= 0
    ).any():

        raise ValueError(
            "All SLA values must be > 0"
        )

    if (
        sla
        < transit
    ).any():

        raise ValueError(
            "sla_hours cannot be less than "
            "typical_transit_hours"
        )

    # --------------------------------------------------------
    # Cost
    # --------------------------------------------------------

    costs = pd.to_numeric(
        routes[
            "baseline_cost_inr"
        ],
        errors="raise",
    )

    if (
        costs <= 0
    ).any():

        raise ValueError(
            "All baseline route costs "
            "must be > 0"
        )

    # --------------------------------------------------------
    # Risk
    # --------------------------------------------------------

    risks = pd.to_numeric(
        routes[
            "baseline_risk_score"
        ],
        errors="raise",
    )

    if (
        (risks < 0)
        | (risks > 1)
    ).any():

        raise ValueError(
            "baseline_risk_score must "
            "be between 0 and 1"
        )

    # --------------------------------------------------------
    # Verify warehouse metadata hasn't been corrupted
    # --------------------------------------------------------

    warehouse_lookup = {
        row.warehouse_id: {
            "warehouse_name":
                row.warehouse_name,

            "city_id":
                row.city_id,

            "city_name":
                row.city_name,

            "region_id":
                row.region_id,

            "region_name":
                row.region_name,
        }

        for row
        in warehouses.itertuples(
            index=False
        )
    }

    for route in routes.itertuples(
        index=False
    ):

        origin = warehouse_lookup[
            route.origin_warehouse_id
        ]

        destination = warehouse_lookup[
            route.destination_warehouse_id
        ]

        if (
            route.origin_warehouse_name
            != origin[
                "warehouse_name"
            ]
        ):
            raise ValueError(
                f"Origin warehouse-name mismatch "
                f"for {route.route_id}"
            )

        if (
            route.origin_city_id
            != origin[
                "city_id"
            ]
        ):
            raise ValueError(
                f"Origin city-id mismatch "
                f"for {route.route_id}"
            )

        if (
            route.origin_region_id
            != origin[
                "region_id"
            ]
        ):
            raise ValueError(
                f"Origin region-id mismatch "
                f"for {route.route_id}"
            )

        if (
            route.destination_warehouse_name
            != destination[
                "warehouse_name"
            ]
        ):
            raise ValueError(
                f"Destination warehouse-name "
                f"mismatch for {route.route_id}"
            )

        if (
            route.destination_city_id
            != destination[
                "city_id"
            ]
        ):
            raise ValueError(
                f"Destination city-id mismatch "
                f"for {route.route_id}"
            )

        if (
            route.destination_region_id
            != destination[
                "region_id"
            ]
        ):
            raise ValueError(
                f"Destination region-id mismatch "
                f"for {route.route_id}"
            )


# ============================================================
# PUBLIC MASTER GENERATOR
# ============================================================


def generate_route_master(
    warehouses: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Public entry point used later by generate_all.py.

    Returns:
        logistics_routes_df
    """

    return generate_routes(
        warehouses=warehouses,
        generation=generation,
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

    # --------------------------------------------------------
    # Geography
    #     ↓
    # Warehouses
    #     ↓
    # Routes
    # --------------------------------------------------------

    _, cities_df = (
        generate_geography()
    )

    warehouses_df = (
        generate_warehouse_master(
            geography_cities=cities_df
        )
    )

    routes_df = (
        generate_route_master(
            warehouses=warehouses_df
        )
    )

    print(
        "\n=== LOGISTICS ROUTES ===\n"
    )

    display_columns = [
        "route_id",
        "origin_city_name",
        "destination_city_name",
        "route_type",
        "distance_km",
        "typical_transit_hours",
        "sla_hours",
        "baseline_cost_inr",
        "baseline_risk_score",
    ]

    print(
        routes_df[
            display_columns
        ].to_string(
            index=False
        )
    )

    print(
        "\n=== ROUTES BY TYPE ===\n"
    )

    route_type_counts = (
        routes_df
        .groupby(
            "route_type"
        )
        .size()
        .reset_index(
            name="route_count"
        )
    )

    print(
        route_type_counts.to_string(
            index=False
        )
    )

    print(
        "\nGenerated "
        f"{len(routes_df)} "
        "logistics routes successfully."
    )