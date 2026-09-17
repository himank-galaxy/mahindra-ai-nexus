"""
Geography master-data generator for Mahindra AI Nexus.

Generates:
- Regions
- Cities

This module DOES NOT write CSV files.
It only generates and validates pandas DataFrames.

CSV writing will later be handled centrally by:
    data/scripts/generate_all.py
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from data.generators.common.helpers import (
    load_generation_config,
    load_distribution_config,
)

from data.generators.common.ids import (
    make_city_id,
    make_region_id,
)


# ============================================================
# INTERNAL HELPERS
# ============================================================


def _as_positive_int(
    value: Any,
    name: str,
) -> int:
    """
    Convert a config value to a positive integer.
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


def _normalize_weight_mapping(
    mapping: Mapping[str, Any],
    name: str,
) -> dict[str, float]:
    """
    Validate and normalize weights.

    Example input:

        {
            "West": 0.30,
            "North": 0.25,
            "South": 0.25,
            "East": 0.20
        }

    Output will always sum to 1.0.
    """

    if not mapping:
        raise ValueError(
            f"{name} cannot be empty"
        )

    parsed: dict[str, float] = {}

    for key, value in mapping.items():

        if (
            not isinstance(key, str)
            or not key.strip()
        ):
            raise ValueError(
                f"{name} contains an invalid key: "
                f"{key!r}"
            )

        try:
            weight = float(value)

        except (TypeError, ValueError) as exc:

            raise TypeError(
                f"Weight for {key!r} in {name} "
                f"must be numeric"
            ) from exc

        if weight < 0:
            raise ValueError(
                f"Weight for {key!r} in {name} "
                f"cannot be negative"
            )

        parsed[key.strip()] = weight

    total = sum(
        parsed.values()
    )

    if total <= 0:
        raise ValueError(
            f"Weights in {name} "
            f"must have a positive sum"
        )

    return {
        key: weight / total
        for key, weight in parsed.items()
    }


# ============================================================
# REGIONS
# ============================================================


def generate_regions(
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate the region master DataFrame.

    Expected output:

        region_id
        region_name
        generation_weight
    """

    if generation is None:
        generation = load_generation_config()

    if distributions is None:
        distributions = load_distribution_config()

    # --------------------------------------------------------
    # Expected number of regions
    # --------------------------------------------------------

    expected_count = _as_positive_int(
        generation["master"]["regions"]["count"],
        "generation.master.regions.count",
    )

    # --------------------------------------------------------
    # Read geography distribution
    # --------------------------------------------------------

    geography_config = distributions.get(
        "geography"
    )

    if not isinstance(
        geography_config,
        Mapping,
    ):
        raise KeyError(
            "Missing distributions.geography "
            "configuration"
        )

    region_weights_raw = geography_config.get(
        "region_weights"
    )

    if not isinstance(
        region_weights_raw,
        Mapping,
    ):
        raise KeyError(
            "Missing "
            "distributions.geography.region_weights "
            "configuration"
        )

    # --------------------------------------------------------
    # Normalize weights
    # --------------------------------------------------------

    region_weights = _normalize_weight_mapping(
        region_weights_raw,
        "distributions.geography.region_weights",
    )

    # --------------------------------------------------------
    # Check count
    # --------------------------------------------------------

    if len(region_weights) != expected_count:

        raise ValueError(
            "Region count mismatch: "
            f"generation.yaml expects "
            f"{expected_count} regions, "
            f"but distributions.yaml defines "
            f"{len(region_weights)}."
        )

    # --------------------------------------------------------
    # Build records
    # --------------------------------------------------------

    rows = []

    for region_name, weight in region_weights.items():

        rows.append(
            {
                "region_id":
                    make_region_id(
                        region_name
                    ),

                "region_name":
                    region_name,

                "generation_weight":
                    weight,
            }
        )

    regions = pd.DataFrame(
        rows,
        columns=[
            "region_id",
            "region_name",
            "generation_weight",
        ],
    )

    validate_regions(
        regions
    )

    return regions


# ============================================================
# CITIES
# ============================================================


def generate_cities(
    regions: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate city master data.

    Every city is connected to a valid region.

    Expected output:

        city_id
        city_name
        region_id
        region_name
        generation_weight_within_region
    """

    if generation is None:
        generation = load_generation_config()

    if distributions is None:
        distributions = load_distribution_config()

    # Make sure supplied regions are valid first.
    validate_regions(
        regions
    )

    # --------------------------------------------------------
    # Target number of cities
    # --------------------------------------------------------

    target_count = _as_positive_int(
        generation["master"]["cities"][
            "target_count"
        ],
        "generation.master.cities.target_count",
    )

    # --------------------------------------------------------
    # Read city configuration
    # --------------------------------------------------------

    geography_config = distributions.get(
        "geography"
    )

    if not isinstance(
        geography_config,
        Mapping,
    ):
        raise KeyError(
            "Missing distributions.geography "
            "configuration"
        )

    cities_by_region_raw = geography_config.get(
        "cities_by_region"
    )

    if not isinstance(
        cities_by_region_raw,
        Mapping,
    ):
        raise KeyError(
            "Missing "
            "distributions.geography."
            "cities_by_region configuration"
        )

    # --------------------------------------------------------
    # Build region lookup
    #
    # Example:
    #
    # {
    #     "West": "REG_WEST",
    #     "North": "REG_NORTH"
    # }
    # --------------------------------------------------------

    valid_regions = {
        row.region_name: row.region_id
        for row
        in regions.itertuples(
            index=False
        )
    }

    candidates: list[
        dict[str, Any]
    ] = []

    # --------------------------------------------------------
    # Create city records
    # --------------------------------------------------------

    for (
        region_name,
        city_weights_raw,
    ) in cities_by_region_raw.items():

        # Ensure city config uses a valid region.
        if region_name not in valid_regions:

            raise ValueError(
                "City configuration references "
                f"unknown region: "
                f"{region_name!r}"
            )

        if not isinstance(
            city_weights_raw,
            Mapping,
        ):

            raise TypeError(
                "City configuration for region "
                f"{region_name!r} "
                "must be a mapping."
            )

        city_weights = (
            _normalize_weight_mapping(
                city_weights_raw,
                (
                    "distributions.geography."
                    "cities_by_region."
                    f"{region_name}"
                ),
            )
        )

        for (
            city_name,
            city_weight,
        ) in city_weights.items():

            candidates.append(
                {
                    "city_id":
                        make_city_id(
                            city_name
                        ),

                    "city_name":
                        city_name,

                    "region_id":
                        valid_regions[
                            region_name
                        ],

                    "region_name":
                        region_name,

                    "generation_weight_within_region":
                        city_weight,
                }
            )

    # --------------------------------------------------------
    # Validate requested city count
    # --------------------------------------------------------

    if target_count > len(candidates):

        raise ValueError(
            "City target count exceeds "
            "configured city inventory: "
            f"target_count={target_count}, "
            f"available={len(candidates)}"
        )

    # --------------------------------------------------------
    # In our current config:
    #
    # target_count = 20
    # configured cities = 20
    #
    # Therefore all cities will normally be selected.
    #
    # This block also makes the generator safe if the target
    # count is reduced later.
    # --------------------------------------------------------

    if target_count < len(candidates):

        region_order = list(
            valid_regions.keys()
        )

        region_rank = {
            name: index
            for index, name
            in enumerate(
                region_order
            )
        }

        # Prefer cities with higher configured weights.
        candidates = sorted(
            candidates,
            key=lambda row: (
                -row[
                    "generation_weight_within_region"
                ],
                region_rank[
                    row["region_name"]
                ],
                row["city_name"],
            ),
        )[:target_count]

        # Restore a predictable ordering.
        candidates = sorted(
            candidates,
            key=lambda row: (
                region_rank[
                    row["region_name"]
                ],
                row["city_name"],
            ),
        )

    # --------------------------------------------------------
    # Create DataFrame
    # --------------------------------------------------------

    cities = pd.DataFrame(
        candidates,
        columns=[
            "city_id",
            "city_name",
            "region_id",
            "region_name",
            "generation_weight_within_region",
        ],
    )

    validate_cities(
        cities=cities,
        regions=regions,
        expected_count=target_count,
    )

    return cities


# ============================================================
# VALIDATION
# ============================================================


def validate_regions(
    regions: pd.DataFrame,
) -> None:
    """
    Validate generated regions.
    """

    required_columns = {
        "region_id",
        "region_name",
        "generation_weight",
    }

    missing_columns = (
        required_columns
        .difference(
            regions.columns
        )
    )

    if missing_columns:

        raise ValueError(
            "Regions DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if regions.empty:
        raise ValueError(
            "Regions DataFrame cannot be empty"
        )

    # --------------------------------------------------------
    # Missing values
    # --------------------------------------------------------

    if regions[
        "region_id"
    ].isna().any():

        raise ValueError(
            "Regions contains missing "
            "region_id values"
        )

    if regions[
        "region_name"
    ].isna().any():

        raise ValueError(
            "Regions contains missing "
            "region_name values"
        )

    # --------------------------------------------------------
    # Duplicate IDs
    # --------------------------------------------------------

    if regions[
        "region_id"
    ].duplicated().any():

        duplicates = regions.loc[
            regions[
                "region_id"
            ].duplicated(
                keep=False
            ),
            "region_id",
        ].tolist()

        raise ValueError(
            "Duplicate region_id values "
            f"found: {duplicates}"
        )

    # --------------------------------------------------------
    # Duplicate names
    # --------------------------------------------------------

    if regions[
        "region_name"
    ].duplicated().any():

        duplicates = regions.loc[
            regions[
                "region_name"
            ].duplicated(
                keep=False
            ),
            "region_name",
        ].tolist()

        raise ValueError(
            "Duplicate region_name values "
            f"found: {duplicates}"
        )

    # --------------------------------------------------------
    # Weight validation
    # --------------------------------------------------------

    weights = pd.to_numeric(
        regions[
            "generation_weight"
        ],
        errors="raise",
    )

    if (
        weights < 0
    ).any():

        raise ValueError(
            "Region generation weights "
            "cannot be negative"
        )

    total_weight = float(
        weights.sum()
    )

    if abs(
        total_weight - 1.0
    ) > 1e-9:

        raise ValueError(
            "Region generation weights "
            "must sum to 1.0. "
            f"Received {total_weight}."
        )


def validate_cities(
    cities: pd.DataFrame,
    regions: pd.DataFrame,
    expected_count: int | None = None,
) -> None:
    """
    Validate generated cities and their
    relationship with regions.
    """

    required_columns = {
        "city_id",
        "city_name",
        "region_id",
        "region_name",
        "generation_weight_within_region",
    }

    missing_columns = (
        required_columns
        .difference(
            cities.columns
        )
    )

    if missing_columns:

        raise ValueError(
            "Cities DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if cities.empty:
        raise ValueError(
            "Cities DataFrame cannot be empty"
        )

    # --------------------------------------------------------
    # Count
    # --------------------------------------------------------

    if (
        expected_count is not None
        and len(cities)
        != expected_count
    ):

        raise ValueError(
            f"Expected {expected_count} "
            f"cities but generated "
            f"{len(cities)}."
        )

    # --------------------------------------------------------
    # Missing IDs / names
    # --------------------------------------------------------

    if cities[
        "city_id"
    ].isna().any():

        raise ValueError(
            "Cities contains missing "
            "city_id values"
        )

    if cities[
        "city_name"
    ].isna().any():

        raise ValueError(
            "Cities contains missing "
            "city_name values"
        )

    # --------------------------------------------------------
    # Duplicate city IDs
    # --------------------------------------------------------

    if cities[
        "city_id"
    ].duplicated().any():

        duplicates = cities.loc[
            cities[
                "city_id"
            ].duplicated(
                keep=False
            ),
            "city_id",
        ].tolist()

        raise ValueError(
            "Duplicate city_id values "
            f"found: {duplicates}"
        )

    # --------------------------------------------------------
    # Foreign-key validation
    #
    # Every city.region_id must exist
    # inside regions.region_id.
    # --------------------------------------------------------

    valid_region_ids = set(
        regions[
            "region_id"
        ]
    )

    invalid_region_ids = sorted(
        set(
            cities[
                "region_id"
            ]
        ).difference(
            valid_region_ids
        )
    )

    if invalid_region_ids:

        raise ValueError(
            "Cities references invalid "
            "region_id values: "
            + ", ".join(
                invalid_region_ids
            )
        )

    # --------------------------------------------------------
    # Check region name matches region ID
    # --------------------------------------------------------

    region_lookup = dict(
        zip(
            regions[
                "region_id"
            ],
            regions[
                "region_name"
            ],
        )
    )

    mismatched_rows = cities[
        cities.apply(
            lambda row:
                region_lookup[
                    row["region_id"]
                ]
                != row[
                    "region_name"
                ],
            axis=1,
        )
    ]

    if not mismatched_rows.empty:

        raise ValueError(
            "Some city records contain "
            "inconsistent region_id / "
            "region_name combinations."
        )

    # --------------------------------------------------------
    # Validate city weights
    # --------------------------------------------------------

    weights = pd.to_numeric(
        cities[
            "generation_weight_within_region"
        ],
        errors="raise",
    )

    if (
        weights < 0
    ).any():

        raise ValueError(
            "City generation weights "
            "cannot be negative"
        )


# ============================================================
# MAIN GENERATOR
# ============================================================


def generate_geography(
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Generate complete geography master data.

    Returns:

        regions_df, cities_df

    This is the function that generate_all.py will
    eventually call.
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    if distributions is None:
        distributions = (
            load_distribution_config()
        )

    regions = generate_regions(
        generation=generation,
        distributions=distributions,
    )

    cities = generate_cities(
        regions=regions,
        generation=generation,
        distributions=distributions,
    )

    return regions, cities


# ============================================================
# LOCAL TEST
# ============================================================

if __name__ == "__main__":

    regions_df, cities_df = (
        generate_geography()
    )

    print(
        "\n=== REGIONS ==="
    )

    print(
        regions_df.to_string(
            index=False
        )
    )

    print(
        "\n=== CITIES ==="
    )

    print(
        cities_df.to_string(
            index=False
        )
    )

    print(
        f"\nGenerated "
        f"{len(regions_df)} regions "
        f"and "
        f"{len(cities_df)} cities "
        f"successfully."
    )