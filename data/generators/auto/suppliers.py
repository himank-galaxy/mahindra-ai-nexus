"""
Synthetic Supplier + Supplier Lot generator for Mahindra AI Nexus.

Fixed project structure:

    data/generators/auto/suppliers.py

Generates:
    1. suppliers DataFrame
    2. supplier_lots DataFrame

Dependency chain:

    Geography
        ↓
    Suppliers
        ↓
    Supplier Lots
        ↓
    Production
        ↓
    Allocation
        ↓
    Delivery
        ↓
    Warranty

This module DOES NOT write CSV files.

Later generate_all.py will save:

    data/synthetic/auto/suppliers.csv
    data/synthetic/auto/supplier_lots.csv

All values are synthetic engineering assumptions for the PoC.
They are NOT real Mahindra supplier-network data.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.distributions import (
    sample_distribution,
)

from data.generators.common.helpers import (
    load_distribution_config,
    load_generation_config,
)

from data.generators.common.ids import (
    make_entity_id,
)

from data.generators.common.seed import (
    derive_seed,
    make_rng,
)


# ============================================================
# SYNTHETIC SUPPLIER REFERENCE TEMPLATES
# ============================================================

SUPPLIER_TEMPLATES = [
    (
        "BodySteel Systems",
        "STEEL_BODY_PANELS",
        "BODY",
        "HIGH",
    ),
    (
        "CoatPro Materials",
        "PAINT_COATINGS",
        "PAINT",
        "HIGH",
    ),
    (
        "WireLink Systems",
        "ELECTRICAL_WIRING",
        "ELECTRICAL",
        "HIGH",
    ),
    (
        "ECU Logic Components",
        "ECU_ELECTRONICS",
        "ELECTRICAL",
        "HIGH",
    ),
    (
        "BrakeSafe Components",
        "BRAKING_SYSTEM",
        "CHASSIS",
        "HIGH",
    ),
    (
        "RideTech Suspension",
        "SUSPENSION",
        "CHASSIS",
        "HIGH",
    ),
    (
        "SteerRight Systems",
        "STEERING",
        "CHASSIS",
        "HIGH",
    ),
    (
        "RoadGrip Tyres",
        "TYRES",
        "CHASSIS",
        "HIGH",
    ),
    (
        "ComfortSeat Systems",
        "SEATING",
        "INTERIOR",
        "MEDIUM",
    ),
    (
        "ClearView Auto Glass",
        "GLASS",
        "BODY",
        "MEDIUM",
    ),
    (
        "LumaDrive Lighting",
        "LIGHTING",
        "ELECTRICAL",
        "MEDIUM",
    ),
    (
        "ClimateCore HVAC",
        "HVAC",
        "INTERIOR",
        "MEDIUM",
    ),
    (
        "VoltEdge Batteries",
        "BATTERY",
        "ELECTRICAL",
        "HIGH",
    ),
    (
        "FastenPro Industries",
        "FASTENERS",
        "GENERAL",
        "MEDIUM",
    ),
    (
        "TrimForm Plastics",
        "PLASTIC_TRIM",
        "INTERIOR",
        "MEDIUM",
    ),
    (
        "SealFlex Rubber",
        "RUBBER_SEALS",
        "BODY",
        "MEDIUM",
    ),
    (
        "BondTech Adhesives",
        "ADHESIVES",
        "BODY",
        "MEDIUM",
    ),
    (
        "AutoFluid Solutions",
        "FLUIDS",
        "POWERTRAIN",
        "LOW",
    ),
    (
        "CleanFlow Exhaust",
        "EXHAUST",
        "POWERTRAIN",
        "MEDIUM",
    ),
    (
        "DriveCore Components",
        "DRIVETRAIN_COMPONENTS",
        "POWERTRAIN",
        "HIGH",
    ),
]


# ============================================================
# LOT GENERATION CONSTANTS
# ============================================================

LOT_CADENCE_DAYS = 14

ACCEPTED_QUALITY_THRESHOLD = 0.72

CONDITIONAL_QUALITY_THRESHOLD = 0.62


# ============================================================
# BASIC HELPERS
# ============================================================


def _as_positive_int(
    value: Any,
    name: str,
) -> int:
    """
    Convert config value into positive integer.
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
    Read synthetic generation time window.
    """

    time_config = generation.get(
        "time"
    )

    if not isinstance(
        time_config,
        Mapping,
    ):

        time_config = (
            generation.get(
                "time_window"
            )
        )

    if not isinstance(
        time_config,
        Mapping,
    ):

        raise KeyError(
            "Missing generation time configuration. "
            "Expected generation.time "
            "or generation.time_window."
        )

    start_value = (
        time_config.get(
            "start",
            time_config.get(
                "start_date"
            ),
        )
    )

    end_value = (
        time_config.get(
            "end",
            time_config.get(
                "end_date"
            ),
        )
    )

    if start_value is None:

        raise KeyError(
            "Missing start/start_date "
            "in generation time configuration"
        )

    if end_value is None:

        raise KeyError(
            "Missing end/end_date "
            "in generation time configuration"
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
# GEOGRAPHY VALIDATION
# ============================================================


def _validate_geography(
    cities: pd.DataFrame,
) -> None:
    """
    Validate geography input used for supplier locations.
    """

    required = {
        "city_id",
        "city_name",
        "region_id",
        "region_name",
    }

    missing = (
        required
        .difference(
            cities.columns
        )
    )

    if missing:

        raise ValueError(
            "Cities DataFrame is missing columns "
            "required by suppliers.py: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if cities.empty:

        raise ValueError(
            "Cities DataFrame cannot be empty"
        )

    if cities[
        "city_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate city_id values found"
        )


# ============================================================
# SUPPLIER TIER
# ============================================================


def _supplier_tier(
    index: int,
    criticality: str,
) -> str:
    """
    Assign deterministic synthetic supplier tier.
    """

    if criticality == "HIGH":

        if index % 3 == 0:

            return "STRATEGIC"

        return "PREFERRED"

    if criticality == "MEDIUM":

        if index % 2 == 0:

            return "PREFERRED"

        return "STANDARD"

    return "STANDARD"


# ============================================================
# SUPPLIER BASE QUALITY
# ============================================================


def _baseline_quality(
    index: int,
    criticality: str,
) -> float:
    """
    Stable supplier-level baseline quality.
    """

    base = {
        "HIGH": 0.92,
        "MEDIUM": 0.89,
        "LOW": 0.87,
    }[
        criticality
    ]

    deterministic_adjustment = (
        (
            index % 5
        )
        - 2
    ) * 0.008

    return float(
        np.clip(
            (
                base
                + deterministic_adjustment
            ),
            0.82,
            0.97,
        )
    )


# ============================================================
# SUPPLIER MASTER GENERATOR
# ============================================================


def generate_suppliers(
    cities: pd.DataFrame,
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
) -> pd.DataFrame:
    """
    Generate supplier master records.

    Exact config:

        generation["master"]["suppliers"]["count"]
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    _validate_geography(
        cities
    )

    # --------------------------------------------------------
    # EXACT CONFIG KEY
    # --------------------------------------------------------

    try:

        supplier_count = (
            _as_positive_int(
                generation[
                    "master"
                ][
                    "suppliers"
                ][
                    "count"
                ],
                (
                    "generation.master."
                    "suppliers.count"
                ),
            )
        )

    except KeyError as exc:

        raise KeyError(
            "Missing configuration key: "
            "generation.master.suppliers.count"
        ) from exc

    # --------------------------------------------------------
    # Provenance
    # --------------------------------------------------------

    provenance = (
        generation.get(
            "provenance",
            {},
        )
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
    # Stable city ordering
    # --------------------------------------------------------

    city_table = (
        cities
        .sort_values(
            by=[
                "region_name",
                "city_name",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    rows: list[
        dict[str, Any]
    ] = []

    for index in range(
        1,
        supplier_count + 1,
    ):

        template_index = (
            index - 1
        ) % len(
            SUPPLIER_TEMPLATES
        )

        (
            base_name,
            component_category,
            component_group,
            criticality,
        ) = (
            SUPPLIER_TEMPLATES[
                template_index
            ]
        )

        city = (
            city_table.iloc[
                (
                    index - 1
                )
                %
                len(
                    city_table
                )
            ]
        )

        supplier_tier = (
            _supplier_tier(
                index=index,
                criticality=
                    criticality,
            )
        )

        baseline_quality_score = (
            _baseline_quality(
                index=index,
                criticality=
                    criticality,
            )
        )

        # ----------------------------------------------------
        # Synthetic capacity metadata correlated with tier
        # ----------------------------------------------------

        if supplier_tier == "STRATEGIC":

            lead_time_days = (
                4
                + (
                    index % 3
                )
            )

            monthly_capacity_units = (
                26000
                +
                (
                    index % 5
                )
                * 2500
            )

        elif supplier_tier == "PREFERRED":

            lead_time_days = (
                6
                +
                (
                    index % 4
                )
            )

            monthly_capacity_units = (
                18000
                +
                (
                    index % 5
                )
                * 2000
            )

        else:

            lead_time_days = (
                9
                +
                (
                    index % 5
                )
            )

            monthly_capacity_units = (
                12000
                +
                (
                    index % 5
                )
                * 1500
            )

        # ----------------------------------------------------
        # Supplier name
        # ----------------------------------------------------

        if (
            index
            <= len(
                SUPPLIER_TEMPLATES
            )
        ):

            supplier_name = (
                f"{base_name} "
                "Synthetic Supplier"
            )

        else:

            cycle = (
                (
                    index - 1
                )
                //
                len(
                    SUPPLIER_TEMPLATES
                )
            ) + 1

            supplier_name = (
                f"{base_name} "
                "Synthetic Supplier "
                f"{cycle:02d}"
            )

        rows.append(
            {
                "supplier_id":
                    make_entity_id(
                        "supplier",
                        index,
                        width=3,
                    ),

                "supplier_name":
                    supplier_name,

                "component_category":
                    component_category,

                "component_group":
                    component_group,

                "criticality":
                    criticality,

                "supplier_tier":
                    supplier_tier,

                "city_id":
                    str(
                        city[
                            "city_id"
                        ]
                    ),

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

                "baseline_quality_score":
                    round(
                        baseline_quality_score,
                        6,
                    ),

                "lead_time_days":
                    int(
                        lead_time_days
                    ),

                "monthly_capacity_units":
                    int(
                        monthly_capacity_units
                    ),

                "active":
                    True,

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    suppliers = pd.DataFrame(
        rows,
        columns=[
            "supplier_id",
            "supplier_name",

            "component_category",
            "component_group",

            "criticality",
            "supplier_tier",

            "city_id",
            "city_name",

            "region_id",
            "region_name",

            "baseline_quality_score",

            "lead_time_days",
            "monthly_capacity_units",

            "active",

            "data_origin",
            "generator_version",
        ],
    )

    validate_suppliers(
        suppliers=
            suppliers,

        cities=
            cities,

        expected_count=
            supplier_count,
    )

    return suppliers


# ============================================================
# SUPPLIER LOT QUALITY CONFIG
# ============================================================


def _get_supplier_lot_quality_spec(
    distributions: Mapping[
        str,
        Any,
    ],
) -> Mapping[
    str,
    Any,
]:
    """
    Use the exact existing configuration:

    manufacturing:
      sensors:
        supplier_lot_quality:
    """

    try:

        spec = (
            distributions[
                "manufacturing"
            ][
                "sensors"
            ][
                "supplier_lot_quality"
            ]
        )

    except KeyError as exc:

        raise KeyError(
            "Missing distribution key: "
            "distributions.manufacturing."
            "sensors.supplier_lot_quality"
        ) from exc

    if not isinstance(
        spec,
        Mapping,
    ):

        raise TypeError(
            "manufacturing.sensors."
            "supplier_lot_quality "
            "must be a distribution mapping"
        )

    return spec


# ============================================================
# LOT INSPECTION STATUS
# ============================================================


def _derive_lot_status(
    quality_score: float,
) -> tuple[
    str,
    bool,
]:
    """
    Translate lot quality into inspection status.
    """

    if (
        quality_score
        >= ACCEPTED_QUALITY_THRESHOLD
    ):

        return (
            "ACCEPTED",
            True,
        )

    if (
        quality_score
        >= CONDITIONAL_QUALITY_THRESHOLD
    ):

        return (
            "CONDITIONAL",
            True,
        )

    return (
        "REJECTED",
        False,
    )


# ============================================================
# SUPPLIER LOT GENERATOR
# ============================================================


def generate_supplier_lots(
    suppliers: pd.DataFrame,
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
    distributions: Mapping[
        str,
        Any,
    ]
    | None = None,
) -> pd.DataFrame:
    """
    Generate time-ordered supplier lots.

    Lots arrive every 14 days throughout the configured
    synthetic period.
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    if distributions is None:

        distributions = (
            load_distribution_config()
        )

    if suppliers.empty:

        raise ValueError(
            "Suppliers DataFrame cannot be empty"
        )

    required_supplier_columns = {
        "supplier_id",
        "supplier_name",

        "component_category",
        "component_group",

        "criticality",

        "baseline_quality_score",
        "monthly_capacity_units",

        "active",
    }

    missing = (
        required_supplier_columns
        .difference(
            suppliers.columns
        )
    )

    if missing:

        raise ValueError(
            "Suppliers DataFrame is missing "
            "columns required for lot generation: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    # --------------------------------------------------------
    # Generation window
    # --------------------------------------------------------

    (
        start,
        end,
        _,
    ) = _get_generation_window(
        generation
    )

    # --------------------------------------------------------
    # Exact supplier-lot quality distribution
    # --------------------------------------------------------

    quality_spec = (
        _get_supplier_lot_quality_spec(
            distributions
        )
    )

    # --------------------------------------------------------
    # RNG
    # --------------------------------------------------------

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
            "auto.supplier_lots",
        )
    )

    # --------------------------------------------------------
    # Provenance
    # --------------------------------------------------------

    provenance = (
        generation.get(
            "provenance",
            {},
        )
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

    rows: list[
        dict[str, Any]
    ] = []

    lot_counter = 1

    # ========================================================
    # GENERATE LOTS
    # ========================================================

    for supplier in suppliers.itertuples(
        index=False
    ):

        if not bool(
            supplier.active
        ):

            continue

        supplier_baseline = float(
            supplier.
            baseline_quality_score
        )

        supplier_quality_adjustment = (
            supplier_baseline
            - 0.90
        )

        lot_received_at = start

        lot_sequence = 1

        while (
            lot_received_at
            < end
        ):

            # =================================================
            # YAML-driven base quality
            # =================================================

            sampled_quality = float(
                sample_distribution(
                    quality_spec,
                    rng=rng,
                )
            )

            # =================================================
            # Supplier-specific persistence
            #
            # Prevents every supplier lot from being
            # independent of supplier identity.
            # =================================================

            quality_score = (
                0.78
                * sampled_quality
                +
                0.22
                * (
                    0.90
                    +
                    supplier_quality_adjustment
                )
            )

            quality_min = float(
                quality_spec.get(
                    "min",
                    0.5,
                )
            )

            quality_max = float(
                quality_spec.get(
                    "max",
                    1.0,
                )
            )

            quality_score = float(
                np.clip(
                    quality_score,
                    quality_min,
                    quality_max,
                )
            )

            # =================================================
            # INSPECTION
            # =================================================

            (
                inspection_status,
                usable_for_production,
            ) = (
                _derive_lot_status(
                    quality_score
                )
            )

            # =================================================
            # INCOMING DEFECT RATE
            #
            # Lower-quality lot
            #       ↓
            # higher incoming defects
            # =================================================

            inspection_defect_rate = float(
                np.clip(
                    (
                        1.0
                        - quality_score
                    )
                    * 0.09
                    +
                    rng.normal(
                        0.003,
                        0.002,
                    ),
                    0.0005,
                    0.08,
                )
            )

            # =================================================
            # LOT SIZE
            # =================================================

            monthly_capacity = int(
                supplier.
                monthly_capacity_units
            )

            expected_lot_size = (
                monthly_capacity
                *
                (
                    LOT_CADENCE_DAYS
                    / 30.0
                )
            )

            lot_size_units = int(
                round(
                    expected_lot_size
                    *
                    float(
                        rng.uniform(
                            0.85,
                            1.15,
                        )
                    )
                )
            )

            lot_size_units = max(
                lot_size_units,
                100,
            )

            # =================================================
            # ACCEPTED / REJECTED UNITS
            # =================================================

            if (
                inspection_status
                ==
                "REJECTED"
            ):

                accepted_units = 0

            else:

                accepted_units = int(
                    round(
                        lot_size_units
                        *
                        (
                            1.0
                            -
                            inspection_defect_rate
                        )
                    )
                )

            rejected_units = (
                lot_size_units
                -
                accepted_units
            )

            # =================================================
            # RECORD
            # =================================================

            rows.append(
                {
                    "supplier_lot_id":
                        make_entity_id(
                            "supplier_lot",
                            lot_counter,
                            width=6,
                        ),

                    "supplier_id":
                        supplier.supplier_id,

                    "supplier_name":
                        supplier.supplier_name,

                    "component_category":
                        supplier.
                        component_category,

                    "component_group":
                        supplier.component_group,

                    "criticality":
                        supplier.criticality,

                    "lot_sequence":
                        lot_sequence,

                    "received_at":
                        lot_received_at,

                    "lot_size_units":
                        lot_size_units,

                    "accepted_units":
                        accepted_units,

                    "rejected_units":
                        rejected_units,

                    "lot_quality_score":
                        round(
                            quality_score,
                            6,
                        ),

                    "inspection_defect_rate":
                        round(
                            inspection_defect_rate,
                            6,
                        ),

                    "inspection_status":
                        inspection_status,

                    "usable_for_production":
                        usable_for_production,

                    "data_origin":
                        data_origin,

                    "generator_version":
                        generator_version,
                }
            )

            lot_counter += 1

            lot_sequence += 1

            lot_received_at = (
                lot_received_at
                +
                timedelta(
                    days=
                        LOT_CADENCE_DAYS
                )
            )

    supplier_lots = pd.DataFrame(
        rows,
        columns=[
            "supplier_lot_id",

            "supplier_id",
            "supplier_name",

            "component_category",
            "component_group",
            "criticality",

            "lot_sequence",
            "received_at",

            "lot_size_units",
            "accepted_units",
            "rejected_units",

            "lot_quality_score",
            "inspection_defect_rate",

            "inspection_status",
            "usable_for_production",

            "data_origin",
            "generator_version",
        ],
    )

    validate_supplier_lots(
        supplier_lots=
            supplier_lots,

        suppliers=
            suppliers,

        start=
            start,

        end=
            end,

        quality_spec=
            quality_spec,
    )

    return supplier_lots


# ============================================================
# SUPPLIER VALIDATION
# ============================================================


def validate_suppliers(
    suppliers: pd.DataFrame,
    cities: pd.DataFrame,
    expected_count: int,
) -> None:
    """
    Validate supplier master.
    """

    required_columns = {
        "supplier_id",
        "supplier_name",

        "component_category",
        "component_group",

        "criticality",
        "supplier_tier",

        "city_id",
        "city_name",

        "region_id",
        "region_name",

        "baseline_quality_score",

        "lead_time_days",
        "monthly_capacity_units",

        "active",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        .difference(
            suppliers.columns
        )
    )

    if missing:

        raise ValueError(
            "Suppliers DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    # --------------------------------------------------------
    # COUNT
    # --------------------------------------------------------

    if (
        len(
            suppliers
        )
        != expected_count
    ):

        raise ValueError(
            f"Expected {expected_count} suppliers "
            f"but generated {len(suppliers)}"
        )

    # --------------------------------------------------------
    # IDs
    # --------------------------------------------------------

    if suppliers[
        "supplier_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate supplier_id values found"
        )

    if suppliers[
        "supplier_name"
    ].duplicated().any():

        raise ValueError(
            "Duplicate supplier_name values found"
        )

    # --------------------------------------------------------
    # Geography FK
    # --------------------------------------------------------

    invalid_city_ids = (
        set(
            suppliers[
                "city_id"
            ]
        )
        -
        set(
            cities[
                "city_id"
            ]
        )
    )

    if invalid_city_ids:

        raise ValueError(
            "Suppliers reference invalid city IDs"
        )

    # --------------------------------------------------------
    # Quality
    # --------------------------------------------------------

    quality = pd.to_numeric(
        suppliers[
            "baseline_quality_score"
        ],
        errors="raise",
    )

    if (
        (
            quality < 0
        )
        |
        (
            quality > 1
        )
    ).any():

        raise ValueError(
            "baseline_quality_score must "
            "be between 0 and 1"
        )

    # --------------------------------------------------------
    # Lead time
    # --------------------------------------------------------

    if (
        pd.to_numeric(
            suppliers[
                "lead_time_days"
            ],
            errors="raise",
        )
        <= 0
    ).any():

        raise ValueError(
            "lead_time_days must be > 0"
        )

    # --------------------------------------------------------
    # Capacity
    # --------------------------------------------------------

    if (
        pd.to_numeric(
            suppliers[
                "monthly_capacity_units"
            ],
            errors="raise",
        )
        <= 0
    ).any():

        raise ValueError(
            "monthly_capacity_units must be > 0"
        )


# ============================================================
# SUPPLIER LOT VALIDATION
# ============================================================


def validate_supplier_lots(
    supplier_lots: pd.DataFrame,
    suppliers: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    quality_spec: Mapping[
        str,
        Any,
    ],
) -> None:
    """
    Validate supplier lot records.
    """

    required_columns = {
        "supplier_lot_id",

        "supplier_id",
        "supplier_name",

        "component_category",
        "component_group",
        "criticality",

        "lot_sequence",
        "received_at",

        "lot_size_units",
        "accepted_units",
        "rejected_units",

        "lot_quality_score",
        "inspection_defect_rate",

        "inspection_status",
        "usable_for_production",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        .difference(
            supplier_lots.columns
        )
    )

    if missing:

        raise ValueError(
            "Supplier-lots DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if supplier_lots.empty:

        raise ValueError(
            "Supplier-lots DataFrame cannot be empty"
        )

    # --------------------------------------------------------
    # IDs
    # --------------------------------------------------------

    if supplier_lots[
        "supplier_lot_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate supplier_lot_id values found"
        )

    # --------------------------------------------------------
    # Supplier FK
    # --------------------------------------------------------

    invalid_supplier_ids = (
        set(
            supplier_lots[
                "supplier_id"
            ]
        )
        -
        set(
            suppliers[
                "supplier_id"
            ]
        )
    )

    if invalid_supplier_ids:

        raise ValueError(
            "Supplier lots reference "
            "invalid supplier IDs"
        )

    # --------------------------------------------------------
    # Every active supplier needs lots
    # --------------------------------------------------------

    active_supplier_ids = set(
        suppliers.loc[
            suppliers[
                "active"
            ].astype(
                bool
            ),
            "supplier_id",
        ]
    )

    lot_supplier_ids = set(
        supplier_lots[
            "supplier_id"
        ]
    )

    if not (
        active_supplier_ids
        .issubset(
            lot_supplier_ids
        )
    ):

        raise ValueError(
            "At least one active supplier "
            "has no supplier lots"
        )

    # --------------------------------------------------------
    # Quantities
    # --------------------------------------------------------

    lot_sizes = pd.to_numeric(
        supplier_lots[
            "lot_size_units"
        ],
        errors="raise",
    )

    accepted = pd.to_numeric(
        supplier_lots[
            "accepted_units"
        ],
        errors="raise",
    )

    rejected = pd.to_numeric(
        supplier_lots[
            "rejected_units"
        ],
        errors="raise",
    )

    if (
        lot_sizes <= 0
    ).any():

        raise ValueError(
            "lot_size_units must be > 0"
        )

    if (
        accepted < 0
    ).any():

        raise ValueError(
            "accepted_units cannot be negative"
        )

    if (
        rejected < 0
    ).any():

        raise ValueError(
            "rejected_units cannot be negative"
        )

    if not (
        (
            accepted
            + rejected
        )
        ==
        lot_sizes
    ).all():

        raise ValueError(
            "accepted_units + rejected_units "
            "must equal lot_size_units"
        )

    # --------------------------------------------------------
    # Quality
    # --------------------------------------------------------

    quality = pd.to_numeric(
        supplier_lots[
            "lot_quality_score"
        ],
        errors="raise",
    )

    quality_min = float(
        quality_spec.get(
            "min",
            0.5,
        )
    )

    quality_max = float(
        quality_spec.get(
            "max",
            1.0,
        )
    )

    if (
        (
            quality < quality_min
        )
        |
        (
            quality > quality_max
        )
    ).any():

        raise ValueError(
            "lot_quality_score outside configured "
            "supplier_lot_quality range"
        )

    # --------------------------------------------------------
    # Defect rate
    # --------------------------------------------------------

    defect_rate = pd.to_numeric(
        supplier_lots[
            "inspection_defect_rate"
        ],
        errors="raise",
    )

    if (
        (
            defect_rate < 0
        )
        |
        (
            defect_rate > 1
        )
    ).any():

        raise ValueError(
            "inspection_defect_rate must "
            "be between 0 and 1"
        )

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    valid_statuses = {
        "ACCEPTED",
        "CONDITIONAL",
        "REJECTED",
    }

    invalid_statuses = (
        set(
            supplier_lots[
                "inspection_status"
            ]
        )
        -
        valid_statuses
    )

    if invalid_statuses:

        raise ValueError(
            "Invalid inspection statuses found"
        )

    rejected_rows = (
        supplier_lots[
            "inspection_status"
        ]
        ==
        "REJECTED"
    )

    if (
        supplier_lots.loc[
            rejected_rows,
            "usable_for_production",
        ]
        .astype(
            bool
        )
        .any()
    ):

        raise ValueError(
            "Rejected supplier lots cannot "
            "be usable for production"
        )

    if (
        accepted.loc[
            rejected_rows
        ]
        != 0
    ).any():

        raise ValueError(
            "Rejected supplier lots must have "
            "zero accepted_units"
        )

    # --------------------------------------------------------
    # Time
    # --------------------------------------------------------

    received_at = pd.to_datetime(
        supplier_lots[
            "received_at"
        ]
    )

    if (
        received_at
        < start
    ).any():

        raise ValueError(
            "Supplier lot received before "
            "generation start"
        )

    if (
        received_at
        >= end
    ).any():

        raise ValueError(
            "Supplier lot received at/after "
            "generation end"
        )

    # --------------------------------------------------------
    # Sequential lot numbering
    # --------------------------------------------------------

    grouped = (
        supplier_lots
        .sort_values(
            [
                "supplier_id",
                "lot_sequence",
            ]
        )
        .groupby(
            "supplier_id"
        )
    )

    for (
        supplier_id,
        group,
    ) in grouped:

        actual = (
            group[
                "lot_sequence"
            ]
            .astype(
                int
            )
            .tolist()
        )

        expected = list(
            range(
                1,
                len(
                    group
                )
                + 1,
            )
        )

        if actual != expected:

            raise ValueError(
                "Invalid supplier lot sequence "
                f"for supplier {supplier_id}"
            )


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_supplier_master(
    cities: pd.DataFrame,
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
    distributions: Mapping[
        str,
        Any,
    ]
    | None = None,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Public entry point later used by generate_all.py.

    Returns:

        suppliers_df
        supplier_lots_df
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    if distributions is None:

        distributions = (
            load_distribution_config()
        )

    suppliers = (
        generate_suppliers(
            cities=cities,
            generation=generation,
        )
    )

    supplier_lots = (
        generate_supplier_lots(
            suppliers=suppliers,
            generation=generation,
            distributions=
                distributions,
        )
    )

    return (
        suppliers,
        supplier_lots,
    )


# ============================================================
# LOCAL TEST
# ============================================================


if __name__ == "__main__":

    from data.generators.master.geography import (
        generate_geography,
    )

    (
        regions_df,
        cities_df,
    ) = generate_geography()

    (
        suppliers_df,
        supplier_lots_df,
    ) = generate_supplier_master(
        cities=
            cities_df
    )

    print(
        "\n=== SUPPLIERS ===\n"
    )

    print(
        suppliers_df[
            [
                "supplier_id",
                "supplier_name",
                "component_category",
                "component_group",
                "criticality",
                "supplier_tier",
                "city_name",
                "region_name",
                "baseline_quality_score",
                "monthly_capacity_units",
            ]
        ]
        .to_string(
            index=False
        )
    )

    print(
        "\n=== SUPPLIER LOT SAMPLE ===\n"
    )

    print(
        supplier_lots_df[
            [
                "supplier_lot_id",
                "supplier_id",
                "component_category",

                "received_at",

                "lot_size_units",

                "lot_quality_score",
                "inspection_defect_rate",

                "inspection_status",
                "usable_for_production",
            ]
        ]
        .head(
            30
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== LOT STATUS ===\n"
    )

    print(
        supplier_lots_df
        .groupby(
            "inspection_status"
        )
        .size()
        .reset_index(
            name="lot_count"
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== LOT QUALITY ===\n"
    )

    print(
        supplier_lots_df[
            "lot_quality_score"
        ]
        .describe()
        .round(
            4
        )
        .to_string()
    )

    print(
        "\n=== LOTS PER SUPPLIER ===\n"
    )

    print(
        supplier_lots_df
        .groupby(
            "supplier_id"
        )
        .size()
        .describe()
        .round(
            2
        )
        .to_string()
    )

    print(
        "\nGenerated "
        f"{len(suppliers_df)} suppliers and "
        f"{len(supplier_lots_df)} supplier lots "
        "successfully."
    )