"""
Dealer master-data generator for Mahindra AI Nexus.

Generates:
- Dealer master records

Every dealer is linked to a valid:
- city
- region

This module DOES NOT write CSV files.

Later:
    data/scripts/generate_all.py

will save the returned DataFrame as:

    data/synthetic/master/dealers.csv

IMPORTANT:
Dealer capacities, staffing, service-bay counts and SLA values
are synthetic engineering assumptions for the PoC.
They are NOT actual Mahindra dealer-network data.
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
# SYNTHETIC DEALER OPERATING PROFILES
#
# Tier determines approximate synthetic dealer scale.
# ============================================================

DEALER_TIER_PROFILES: dict[str, dict[str, Any]] = {

    "TIER_1": {
        "monthly_lead_capacity": 650,
        "monthly_test_drive_capacity": 330,
        "monthly_booking_capacity": 140,
        "sales_consultants": 24,
        "service_bays": 18,
        "followup_sla_hours": 4,
    },

    "TIER_2": {
        "monthly_lead_capacity": 450,
        "monthly_test_drive_capacity": 220,
        "monthly_booking_capacity": 95,
        "sales_consultants": 16,
        "service_bays": 12,
        "followup_sla_hours": 6,
    },

    "TIER_3": {
        "monthly_lead_capacity": 280,
        "monthly_test_drive_capacity": 135,
        "monthly_booking_capacity": 60,
        "sales_consultants": 10,
        "service_bays": 8,
        "followup_sla_hours": 8,
    },
}


# ============================================================
# INTERNAL HELPERS
# ============================================================


def _as_positive_int(
    value: Any,
    name: str,
) -> int:
    """
    Convert configuration value to positive integer.
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


def _validate_geography_inputs(
    regions: pd.DataFrame,
    cities: pd.DataFrame,
) -> None:
    """
    Validate geography DataFrames required by dealer generator.
    """

    region_columns = {
        "region_id",
        "region_name",
        "generation_weight",
    }

    city_columns = {
        "city_id",
        "city_name",
        "region_id",
        "region_name",
        "generation_weight_within_region",
    }

    missing_region_columns = (
        region_columns
        .difference(
            regions.columns
        )
    )

    if missing_region_columns:
        raise ValueError(
            "Regions DataFrame is missing columns "
            "required by dealers.py: "
            + ", ".join(
                sorted(
                    missing_region_columns
                )
            )
        )

    missing_city_columns = (
        city_columns
        .difference(
            cities.columns
        )
    )

    if missing_city_columns:
        raise ValueError(
            "Cities DataFrame is missing columns "
            "required by dealers.py: "
            + ", ".join(
                sorted(
                    missing_city_columns
                )
            )
        )

    if regions.empty:
        raise ValueError(
            "Regions DataFrame cannot be empty"
        )

    if cities.empty:
        raise ValueError(
            "Cities DataFrame cannot be empty"
        )

    if regions[
        "region_id"
    ].duplicated().any():
        raise ValueError(
            "Duplicate region_id values "
            "found in geography master"
        )

    if cities[
        "city_id"
    ].duplicated().any():
        raise ValueError(
            "Duplicate city_id values "
            "found in geography master"
        )

    # --------------------------------------------------------
    # Every city's region must exist.
    # --------------------------------------------------------

    valid_region_ids = set(
        regions[
            "region_id"
        ]
    )

    invalid_regions = sorted(
        set(
            cities[
                "region_id"
            ]
        )
        .difference(
            valid_region_ids
        )
    )

    if invalid_regions:
        raise ValueError(
            "Cities reference invalid region IDs: "
            + ", ".join(
                invalid_regions
            )
        )


def _build_city_priority(
    regions: pd.DataFrame,
    cities: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate a deterministic synthetic demand priority
    for each city.

    Priority =
        region generation weight
        *
        city generation weight within region

    Example:

        West weight = 0.30
        Pune within West = 0.30

        priority = 0.30 * 0.30 = 0.09

    This is used only to decide where additional dealers
    should be located.
    """

    region_weights = dict(
        zip(
            regions[
                "region_id"
            ],
            regions[
                "generation_weight"
            ],
        )
    )

    city_priority = (
        cities.copy()
    )

    city_priority[
        "region_generation_weight"
    ] = city_priority[
        "region_id"
    ].map(
        region_weights
    )

    if city_priority[
        "region_generation_weight"
    ].isna().any():

        raise ValueError(
            "Unable to map region generation "
            "weights to all cities"
        )

    city_priority[
        "dealer_location_weight"
    ] = (
        city_priority[
            "region_generation_weight"
        ].astype(float)
        *
        city_priority[
            "generation_weight_within_region"
        ].astype(float)
    )

    return (
        city_priority
        .sort_values(
            by=[
                "dealer_location_weight",
                "city_name",
            ],
            ascending=[
                False,
                True,
            ],
        )
        .reset_index(
            drop=True
        )
    )


def _assign_dealer_tier(
    location_weight: float,
    max_location_weight: float,
) -> str:
    """
    Assign a synthetic dealer tier based on
    relative city demand weight.

    This does NOT represent real dealer classification.
    """

    if max_location_weight <= 0:
        return "TIER_3"

    relative_score = (
        location_weight
        / max_location_weight
    )

    if relative_score >= 0.70:
        return "TIER_1"

    if relative_score >= 0.40:
        return "TIER_2"

    return "TIER_3"


# ============================================================
# GENERATOR
# ============================================================


def generate_dealers(
    regions: pd.DataFrame,
    cities: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate dealer master records.

    Output columns:

        dealer_id
        dealer_name

        city_id
        city_name

        region_id
        region_name

        dealer_tier

        monthly_lead_capacity
        monthly_test_drive_capacity
        monthly_booking_capacity

        sales_consultants
        service_bays
        followup_sla_hours

        active
        data_origin
        generator_version
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    # --------------------------------------------------------
    # Validate upstream geography
    # --------------------------------------------------------

    _validate_geography_inputs(
        regions=regions,
        cities=cities,
    )

    # --------------------------------------------------------
    # EXACT CONFIG KEY:
    #
    # master:
    #   dealers:
    #     count: 30
    # --------------------------------------------------------

    try:
        dealer_count = (
            _as_positive_int(
                generation[
                    "master"
                ][
                    "dealers"
                ][
                    "count"
                ],
                "generation.master.dealers.count",
            )
        )

    except KeyError as exc:
        raise KeyError(
            "Missing configuration key: "
            "generation.master.dealers.count"
        ) from exc

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
    # City priority
    # --------------------------------------------------------

    city_priority = (
        _build_city_priority(
            regions=regions,
            cities=cities,
        )
    )

    if city_priority.empty:
        raise ValueError(
            "No cities available for dealer generation"
        )

    max_location_weight = float(
        city_priority[
            "dealer_location_weight"
        ].max()
    )

    # --------------------------------------------------------
    # Dealer location assignment
    #
    # First:
    #   give every configured city one dealer
    #
    # Then:
    #   remaining dealers go to higher-demand cities,
    #   cycling deterministically through city priority.
    #
    # With:
    #
    #   cities  = 20
    #   dealers = 30
    #
    # all 20 cities receive at least one dealer,
    # then 10 additional dealers are assigned to
    # higher-priority cities.
    # --------------------------------------------------------

    city_assignments: list[
        pd.Series
    ] = []

    # First pass:
    # one dealer per city where possible.
    initial_count = min(
        dealer_count,
        len(
            city_priority
        ),
    )

    for index in range(
        initial_count
    ):
        city_assignments.append(
            city_priority.iloc[
                index
            ]
        )

    # Additional dealers.
    remaining = (
        dealer_count
        - initial_count
    )

    for index in range(
        remaining
    ):

        city_index = (
            index
            % len(
                city_priority
            )
        )

        city_assignments.append(
            city_priority.iloc[
                city_index
            ]
        )

    # --------------------------------------------------------
    # Track dealer sequence inside each city.
    #
    # Example:
    #
    # Pune Synthetic Dealer 01
    # Pune Synthetic Dealer 02
    # --------------------------------------------------------

    city_dealer_counter: dict[
        str,
        int
    ] = {}

    rows: list[
        dict[str, Any]
    ] = []

    # --------------------------------------------------------
    # Build dealer records
    # --------------------------------------------------------

    for dealer_number, city in enumerate(
        city_assignments,
        start=1,
    ):

        city_id = str(
            city[
                "city_id"
            ]
        )

        city_dealer_counter[
            city_id
        ] = (
            city_dealer_counter.get(
                city_id,
                0,
            )
            + 1
        )

        local_dealer_number = (
            city_dealer_counter[
                city_id
            ]
        )

        location_weight = float(
            city[
                "dealer_location_weight"
            ]
        )

        dealer_tier = (
            _assign_dealer_tier(
                location_weight=
                    location_weight,

                max_location_weight=
                    max_location_weight,
            )
        )

        profile = (
            DEALER_TIER_PROFILES[
                dealer_tier
            ]
        )

        # ----------------------------------------------------
        # Small deterministic variation for multiple dealers
        # within the same city.
        #
        # Dealer 1 -> multiplier 1.00
        # Dealer 2 -> multiplier 0.95
        # Dealer 3 -> multiplier 0.90
        #
        # Minimum multiplier = 0.80
        # ----------------------------------------------------

        capacity_multiplier = max(
            0.80,
            (
                1.0
                - (
                    0.05
                    * (
                        local_dealer_number
                        - 1
                    )
                )
            ),
        )

        rows.append(
            {
                "dealer_id":
                    make_entity_id(
                        "dealer",
                        dealer_number,
                        width=6,
                    ),

                "dealer_name":
                    (
                        f"{city['city_name']} "
                        "Synthetic Dealer "
                        f"{local_dealer_number:02d}"
                    ),

                "city_id":
                    city_id,

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

                "dealer_tier":
                    dealer_tier,

                "monthly_lead_capacity":
                    int(
                        round(
                            profile[
                                "monthly_lead_capacity"
                            ]
                            * capacity_multiplier
                        )
                    ),

                "monthly_test_drive_capacity":
                    int(
                        round(
                            profile[
                                "monthly_test_drive_capacity"
                            ]
                            * capacity_multiplier
                        )
                    ),

                "monthly_booking_capacity":
                    int(
                        round(
                            profile[
                                "monthly_booking_capacity"
                            ]
                            * capacity_multiplier
                        )
                    ),

                "sales_consultants":
                    max(
                        1,
                        int(
                            round(
                                profile[
                                    "sales_consultants"
                                ]
                                * capacity_multiplier
                            )
                        ),
                    ),

                "service_bays":
                    max(
                        1,
                        int(
                            round(
                                profile[
                                    "service_bays"
                                ]
                                * capacity_multiplier
                            )
                        ),
                    ),

                "followup_sla_hours":
                    int(
                        profile[
                            "followup_sla_hours"
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

    dealers = pd.DataFrame(
        rows,
        columns=[
            "dealer_id",
            "dealer_name",

            "city_id",
            "city_name",

            "region_id",
            "region_name",

            "dealer_tier",

            "monthly_lead_capacity",
            "monthly_test_drive_capacity",
            "monthly_booking_capacity",

            "sales_consultants",
            "service_bays",
            "followup_sla_hours",

            "active",

            "data_origin",
            "generator_version",
        ],
    )

    validate_dealers(
        dealers=dealers,
        regions=regions,
        cities=cities,
        expected_count=dealer_count,
    )

    return dealers


# ============================================================
# VALIDATION
# ============================================================


def validate_dealers(
    dealers: pd.DataFrame,
    regions: pd.DataFrame,
    cities: pd.DataFrame,
    expected_count: int | None = None,
) -> None:
    """
    Validate dealer master records.
    """

    required_columns = {
        "dealer_id",
        "dealer_name",

        "city_id",
        "city_name",

        "region_id",
        "region_name",

        "dealer_tier",

        "monthly_lead_capacity",
        "monthly_test_drive_capacity",
        "monthly_booking_capacity",

        "sales_consultants",
        "service_bays",
        "followup_sla_hours",

        "active",

        "data_origin",
        "generator_version",
    }

    missing_columns = (
        required_columns
        .difference(
            dealers.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "Dealers DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if dealers.empty:
        raise ValueError(
            "Dealers DataFrame cannot be empty"
        )

    # --------------------------------------------------------
    # Count
    # --------------------------------------------------------

    if (
        expected_count is not None
        and len(
            dealers
        )
        != expected_count
    ):
        raise ValueError(
            f"Expected {expected_count} dealers "
            f"but generated {len(dealers)}."
        )

    # --------------------------------------------------------
    # Required non-null fields
    # --------------------------------------------------------

    required_non_null = [
        "dealer_id",
        "dealer_name",
        "city_id",
        "city_name",
        "region_id",
        "region_name",
        "dealer_tier",
    ]

    for column in required_non_null:

        if dealers[
            column
        ].isna().any():

            raise ValueError(
                f"Dealers contains missing "
                f"values in {column}"
            )

    # --------------------------------------------------------
    # Unique dealer IDs
    # --------------------------------------------------------

    if dealers[
        "dealer_id"
    ].duplicated().any():

        duplicates = (
            dealers.loc[
                dealers[
                    "dealer_id"
                ].duplicated(
                    keep=False
                ),
                "dealer_id",
            ]
            .tolist()
        )

        raise ValueError(
            "Duplicate dealer_id values found: "
            f"{duplicates}"
        )

    # --------------------------------------------------------
    # Unique dealer names
    # --------------------------------------------------------

    if dealers[
        "dealer_name"
    ].duplicated().any():

        duplicates = (
            dealers.loc[
                dealers[
                    "dealer_name"
                ].duplicated(
                    keep=False
                ),
                "dealer_name",
            ]
            .tolist()
        )

        raise ValueError(
            "Duplicate dealer names found: "
            f"{duplicates}"
        )

    # --------------------------------------------------------
    # City FK
    # --------------------------------------------------------

    valid_city_ids = set(
        cities[
            "city_id"
        ]
    )

    invalid_city_ids = sorted(
        set(
            dealers[
                "city_id"
            ]
        )
        .difference(
            valid_city_ids
        )
    )

    if invalid_city_ids:
        raise ValueError(
            "Dealers reference invalid city IDs: "
            + ", ".join(
                invalid_city_ids
            )
        )

    # --------------------------------------------------------
    # Region FK
    # --------------------------------------------------------

    valid_region_ids = set(
        regions[
            "region_id"
        ]
    )

    invalid_region_ids = sorted(
        set(
            dealers[
                "region_id"
            ]
        )
        .difference(
            valid_region_ids
        )
    )

    if invalid_region_ids:
        raise ValueError(
            "Dealers reference invalid region IDs: "
            + ", ".join(
                invalid_region_ids
            )
        )

    # --------------------------------------------------------
    # Exact city -> region validation
    # --------------------------------------------------------

    city_lookup = {
        row.city_id: {
            "city_name":
                row.city_name,

            "region_id":
                row.region_id,

            "region_name":
                row.region_name,
        }

        for row
        in cities.itertuples(
            index=False
        )
    }

    for dealer in dealers.itertuples(
        index=False
    ):

        geography = city_lookup[
            dealer.city_id
        ]

        if (
            dealer.city_name
            != geography[
                "city_name"
            ]
        ):
            raise ValueError(
                f"city_name mismatch for "
                f"{dealer.dealer_id}"
            )

        if (
            dealer.region_id
            != geography[
                "region_id"
            ]
        ):
            raise ValueError(
                f"region_id mismatch for "
                f"{dealer.dealer_id}"
            )

        if (
            dealer.region_name
            != geography[
                "region_name"
            ]
        ):
            raise ValueError(
                f"region_name mismatch for "
                f"{dealer.dealer_id}"
            )

    # --------------------------------------------------------
    # Dealer tier
    # --------------------------------------------------------

    valid_tiers = set(
        DEALER_TIER_PROFILES.keys()
    )

    invalid_tiers = sorted(
        set(
            dealers[
                "dealer_tier"
            ]
        )
        .difference(
            valid_tiers
        )
    )

    if invalid_tiers:
        raise ValueError(
            "Invalid dealer tiers found: "
            + ", ".join(
                invalid_tiers
            )
        )

    # --------------------------------------------------------
    # Capacity fields
    # --------------------------------------------------------

    positive_columns = [
        "monthly_lead_capacity",
        "monthly_test_drive_capacity",
        "monthly_booking_capacity",
        "sales_consultants",
        "service_bays",
        "followup_sla_hours",
    ]

    for column in positive_columns:

        values = pd.to_numeric(
            dealers[
                column
            ],
            errors="raise",
        )

        if (
            values <= 0
        ).any():

            raise ValueError(
                f"{column} must contain "
                "values greater than 0"
            )

    # --------------------------------------------------------
    # Logical funnel-capacity relationship
    #
    # Leads >= Test Drives >= Bookings
    # --------------------------------------------------------

    invalid_funnel_capacity = (
        (
            dealers[
                "monthly_test_drive_capacity"
            ]
            >
            dealers[
                "monthly_lead_capacity"
            ]
        )
        |
        (
            dealers[
                "monthly_booking_capacity"
            ]
            >
            dealers[
                "monthly_test_drive_capacity"
            ]
        )
    )

    if invalid_funnel_capacity.any():

        raise ValueError(
            "Dealer capacity relationship invalid. "
            "Expected: "
            "lead capacity >= test-drive capacity "
            ">= booking capacity."
        )


# ============================================================
# PUBLIC MASTER GENERATOR
# ============================================================


def generate_dealer_master(
    regions: pd.DataFrame,
    cities: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Public entry point used later by generate_all.py.

    Returns:
        dealers_df
    """

    return generate_dealers(
        regions=regions,
        cities=cities,
        generation=generation,
    )


# ============================================================
# LOCAL TEST
# ============================================================


if __name__ == "__main__":

    from data.generators.master.geography import (
        generate_geography,
    )

    # --------------------------------------------------------
    # Geography
    #      ↓
    # Dealers
    # --------------------------------------------------------

    (
        regions_df,
        cities_df,
    ) = generate_geography()

    dealers_df = (
        generate_dealer_master(
            regions=regions_df,
            cities=cities_df,
        )
    )

    print(
        "\n=== DEALERS ===\n"
    )

    display_columns = [
        "dealer_id",
        "dealer_name",
        "city_name",
        "region_name",
        "dealer_tier",
        "monthly_lead_capacity",
        "monthly_test_drive_capacity",
        "monthly_booking_capacity",
        "sales_consultants",
        "service_bays",
        "followup_sla_hours",
    ]

    print(
        dealers_df[
            display_columns
        ].to_string(
            index=False
        )
    )

    print(
        "\n=== DEALERS BY REGION ===\n"
    )

    region_counts = (
        dealers_df
        .groupby(
            "region_name"
        )
        .size()
        .reset_index(
            name="dealer_count"
        )
        .sort_values(
            "region_name"
        )
    )

    print(
        region_counts.to_string(
            index=False
        )
    )

    print(
        "\n=== DEALERS BY TIER ===\n"
    )

    tier_counts = (
        dealers_df
        .groupby(
            "dealer_tier"
        )
        .size()
        .reset_index(
            name="dealer_count"
        )
        .sort_values(
            "dealer_tier"
        )
    )

    print(
        tier_counts.to_string(
            index=False
        )
    )

    print(
        "\nGenerated "
        f"{len(dealers_df)} "
        "dealers successfully."
    )