"""
Synthetic Vehicle Allocation generator for Mahindra AI Nexus.

Purpose
-------
Connect surviving customer bookings with released production inventory.

Inputs:
    bookings
    cancellations
    production_batches
    dealers
    finance_applications

Outputs:
    allocations DataFrame

Each surviving booking gets exactly one allocation record.

Possible statuses:
    ALLOCATED
    WAITLISTED

An ALLOCATED record links:

    Booking
        ↓
    Dealer
        ↓
    Vehicle Unit
        ↓
    Production Batch
        ↓
    Plant
        ↓
    Production Line
        ↓
    Machine
        ↓
    Supplier
        ↓
    Supplier Lot

This module DOES NOT save CSV files.

Later generate_all.py will save:

    data/synthetic/auto/allocations.csv

All values are synthetic PoC data.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.helpers import (
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
# SYNTHETIC PROCESS ASSUMPTIONS
# ============================================================

MIN_ALLOCATION_PROCESSING_HOURS = 2.0

MAX_ALLOCATION_PROCESSING_HOURS = 36.0

RECENT_BATCH_PREFERENCE_DAYS = 45.0


VALID_ALLOCATION_STATUSES = {
    "ALLOCATED",
    "WAITLISTED",
}


VALID_PRIORITIES = {
    "HIGH",
    "MEDIUM",
    "NORMAL",
}


# ============================================================
# SMALL HELPERS
# ============================================================


def _has_value(
    value: Any,
) -> bool:
    """
    Safely check whether a value exists.
    """

    return (
        value is not None
        and not pd.isna(
            value
        )
    )


# ============================================================
# GENERATION END
# ============================================================


def _get_generation_end(
    generation: Mapping[
        str,
        Any,
    ],
) -> pd.Timestamp:
    """
    Get configured synthetic generation end time.
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

    end_value = time_config.get(
        "end",
        time_config.get(
            "end_date"
        ),
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

    timestamp = pd.Timestamp(
        end_value
    )

    if timestamp.tzinfo is None:

        timestamp = timestamp.tz_localize(
            timezone
        )

    else:

        timestamp = timestamp.tz_convert(
            timezone
        )

    return timestamp


# ============================================================
# INPUT VALIDATION
# ============================================================


def _validate_inputs(
    bookings: pd.DataFrame,
    cancellations: pd.DataFrame,
    production_batches: pd.DataFrame,
    dealers: pd.DataFrame,
    finance_applications: pd.DataFrame,
) -> None:
    """
    Validate upstream datasets.
    """

    # --------------------------------------------------------
    # BOOKINGS
    # --------------------------------------------------------

    booking_required = {
        "booking_id",
        "lead_id",
        "customer_id",

        "dealer_id",
        "dealer_name",

        "region_id",
        "region_name",

        "city_id",
        "city_name",

        "vehicle_model_id",
        "vehicle_model_name",

        "booking_timestamp",
        "promised_delivery_date",

        "finance_assisted",

        "booking_status",
    }

    missing = (
        booking_required
        .difference(
            bookings.columns
        )
    )

    if missing:

        raise ValueError(
            "Bookings DataFrame is missing "
            "columns required by allocations.py: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if bookings.empty:

        raise ValueError(
            "Bookings DataFrame cannot be empty"
        )

    if bookings[
        "booking_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate booking_id values found"
        )

    # --------------------------------------------------------
    # PRODUCTION
    # --------------------------------------------------------

    production_required = {
        "production_batch_id",

        "plant_id",
        "plant_name",

        "production_line_id",
        "production_line_name",

        "representative_machine_id",
        "representative_machine_name",

        "vehicle_model_id",
        "vehicle_model_name",

        "variant",

        "primary_supplier_id",
        "primary_supplier_name",
        "primary_supplier_lot_id",

        "supplier_lot_quality_score",
        "quality_score",

        "production_end",

        "batch_status",

        "available_for_allocation_units",
    }

    missing = (
        production_required
        .difference(
            production_batches.columns
        )
    )

    if missing:

        raise ValueError(
            "Production batches DataFrame is missing "
            "columns required by allocations.py: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if production_batches.empty:

        raise ValueError(
            "Production batches DataFrame cannot be empty"
        )

    if production_batches[
        "production_batch_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate production_batch_id values found"
        )

    # --------------------------------------------------------
    # DEALERS
    # --------------------------------------------------------

    dealer_required = {
        "dealer_id",
        "dealer_name",

        "region_id",
        "city_id",
    }

    missing = (
        dealer_required
        .difference(
            dealers.columns
        )
    )

    if missing:

        raise ValueError(
            "Dealers DataFrame is missing "
            "columns required by allocations.py: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if dealers.empty:

        raise ValueError(
            "Dealers DataFrame cannot be empty"
        )

    if dealers[
        "dealer_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate dealer_id values found"
        )

    # --------------------------------------------------------
    # CANCELLATIONS
    # --------------------------------------------------------

    if not cancellations.empty:

        cancellation_required = {
            "cancellation_id",
            "booking_id",
            "cancelled_at",
        }

        missing = (
            cancellation_required
            .difference(
                cancellations.columns
            )
        )

        if missing:

            raise ValueError(
                "Cancellations DataFrame is missing "
                "columns required by allocations.py: "
                + ", ".join(
                    sorted(
                        missing
                    )
                )
            )

        if cancellations[
            "cancellation_id"
        ].duplicated().any():

            raise ValueError(
                "Duplicate cancellation_id values found"
            )

        if cancellations[
            "booking_id"
        ].duplicated().any():

            raise ValueError(
                "A booking has more than "
                "one cancellation"
            )

        invalid_booking_ids = (
            set(
                cancellations[
                    "booking_id"
                ]
            )
            -
            set(
                bookings[
                    "booking_id"
                ]
            )
        )

        if invalid_booking_ids:

            raise ValueError(
                "Cancellations reference "
                "invalid booking IDs"
            )

    # --------------------------------------------------------
    # FINANCE
    # --------------------------------------------------------

    if not finance_applications.empty:

        finance_required = {
            "finance_application_id",
            "booking_id",
            "status",
        }

        missing = (
            finance_required
            .difference(
                finance_applications.columns
            )
        )

        if missing:

            raise ValueError(
                "Finance applications DataFrame "
                "is missing columns required "
                "by allocations.py: "
                + ", ".join(
                    sorted(
                        missing
                    )
                )
            )

        if finance_applications[
            "finance_application_id"
        ].duplicated().any():

            raise ValueError(
                "Duplicate finance_application_id "
                "values found"
            )

        if finance_applications[
            "booking_id"
        ].duplicated().any():

            raise ValueError(
                "A booking has more than "
                "one finance application"
            )


# ============================================================
# SURVIVING BOOKINGS
# ============================================================


def _build_surviving_bookings(
    bookings: pd.DataFrame,
    cancellations: pd.DataFrame,
) -> pd.DataFrame:
    """
    Remove confirmed cancellations from booking demand.
    """

    cancelled_booking_ids: set[str] = set()

    if not cancellations.empty:

        cancelled_booking_ids = set(
            cancellations[
                "booking_id"
            ]
            .astype(str)
        )

    work = (
        bookings[
            bookings[
                "booking_status"
            ]
            .astype(str)
            .str.upper()
            ==
            "ACTIVE"
        ]
        .copy()
    )

    work = (
        work[
            ~work[
                "booking_id"
            ]
            .astype(str)
            .isin(
                cancelled_booking_ids
            )
        ]
        .copy()
    )

    work[
        "booking_timestamp"
    ] = pd.to_datetime(
        work[
            "booking_timestamp"
        ]
    )

    work[
        "promised_delivery_date"
    ] = pd.to_datetime(
        work[
            "promised_delivery_date"
        ]
    )

    return work.reset_index(
        drop=True
    )


# ============================================================
# REGIONAL DEMAND
# ============================================================


def _add_regional_demand_index(
    bookings: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate regional demand from surviving bookings.

    This is derived evidence rather than a random KPI.

    More surviving bookings in a region:
        ↓
    higher regional demand index.
    """

    work = bookings.copy()

    region_counts = (
        work
        .groupby(
            "region_id"
        )
        .size()
    )

    min_count = float(
        region_counts.min()
    )

    max_count = float(
        region_counts.max()
    )

    demand_lookup: dict[
        str,
        float,
    ] = {}

    for (
        region_id,
        count,
    ) in region_counts.items():

        if max_count == min_count:

            normalized = 0.50

        else:

            normalized = (
                float(
                    count
                )
                -
                min_count
            ) / (
                max_count
                -
                min_count
            )

        # Keep index in a business-friendly range.
        demand_index = (
            0.55
            +
            0.40
            * normalized
        )

        demand_lookup[
            str(
                region_id
            )
        ] = float(
            np.clip(
                demand_index,
                0.0,
                1.0,
            )
        )

    work[
        "regional_demand_index"
    ] = (
        work[
            "region_id"
        ]
        .astype(str)
        .map(
            demand_lookup
        )
        .astype(float)
    )

    return work


# ============================================================
# DEALER CAPACITY
# ============================================================


def _build_dealer_capacity_lookup(
    dealers: pd.DataFrame,
) -> tuple[
    dict[str, int],
    dict[str, str],
]:
    """
    Use existing dealer capacity fields if available.

    We do NOT change dealers.py.

    Preference order:

        inventory_capacity
        dealer_capacity
        capacity_per_day
        daily_capacity
        monthly_lead_capacity
        sales_consultants
        fallback = 100
    """

    capacities: dict[
        str,
        int,
    ] = {}

    sources: dict[
        str,
        str,
    ] = {}

    for dealer in dealers.itertuples(
        index=False
    ):

        row = dealer._asdict()

        dealer_id = str(
            row[
                "dealer_id"
            ]
        )

        capacity = None

        source = None

        # ----------------------------------------------------
        # Direct capacity fields
        # ----------------------------------------------------

        for column in (
            "inventory_capacity",
            "dealer_capacity",
            "capacity_per_day",
            "daily_capacity",
        ):

            if (
                column in row
                and
                _has_value(
                    row[
                        column
                    ]
                )
            ):

                value = int(
                    round(
                        float(
                            row[
                                column
                            ]
                        )
                    )
                )

                if value > 0:

                    capacity = value

                    source = column

                    break

        # ----------------------------------------------------
        # Monthly lead capacity as proxy
        # ----------------------------------------------------

        if (
            capacity is None
            and
            "monthly_lead_capacity"
            in row
        ):

            value = row.get(
                "monthly_lead_capacity"
            )

            if _has_value(
                value
            ):

                value = int(
                    round(
                        float(
                            value
                        )
                    )
                )

                if value > 0:

                    capacity = value

                    source = (
                        "monthly_lead_capacity_proxy"
                    )

        # ----------------------------------------------------
        # Sales consultant proxy
        # ----------------------------------------------------

        if (
            capacity is None
            and
            "sales_consultants"
            in row
        ):

            value = row.get(
                "sales_consultants"
            )

            if _has_value(
                value
            ):

                value = int(
                    round(
                        float(
                            value
                        )
                    )
                )

                if value > 0:

                    capacity = (
                        value
                        * 10
                    )

                    source = (
                        "sales_consultants_proxy"
                    )

        # ----------------------------------------------------
        # Last-resort synthetic fallback
        # ----------------------------------------------------

        if capacity is None:

            capacity = 100

            source = (
                "synthetic_default"
            )

        capacities[
            dealer_id
        ] = int(
            capacity
        )

        sources[
            dealer_id
        ] = str(
            source
        )

    return (
        capacities,
        sources,
    )


# ============================================================
# FINANCE LOOKUP
# ============================================================


def _build_finance_lookup(
    finance_applications: pd.DataFrame,
) -> dict[
    str,
    Any,
]:
    """
    Create booking -> finance application lookup.
    """

    if finance_applications.empty:

        return {}

    return {
        str(
            row.booking_id
        ):
            row

        for row
        in finance_applications.itertuples(
            index=False
        )
    }


# ============================================================
# ALLOCATION PRIORITY
# ============================================================


def _calculate_allocation_priority(
    regional_demand_index: float,
    promised_wait_days: float,
    finance_assisted: bool,
    finance_status: str | None,
) -> tuple[
    float,
    str,
]:
    """
    Calculate allocation priority from evidence.

    Components:

        regional demand
        promised-delivery urgency
        finance readiness
    """

    demand_component = float(
        np.clip(
            regional_demand_index,
            0.0,
            1.0,
        )
    )

    # --------------------------------------------------------
    # Longer promised wait means more urgency.
    # --------------------------------------------------------

    urgency_component = float(
        np.clip(
            promised_wait_days
            / 60.0,
            0.0,
            1.0,
        )
    )

    # --------------------------------------------------------
    # Finance readiness
    # --------------------------------------------------------

    if not finance_assisted:

        finance_component = 1.0

    elif finance_status == "APPROVED":

        finance_component = 1.0

    elif finance_status == "MANUAL_REVIEW":

        finance_component = 0.65

    elif finance_status == "PENDING":

        finance_component = 0.45

    elif finance_status == "REJECTED":

        finance_component = 0.25

    else:

        finance_component = 0.50

    score = (
        0.50
        * demand_component

        +
        0.30
        * urgency_component

        +
        0.20
        * finance_component
    )

    score = float(
        np.clip(
            score,
            0.0,
            1.0,
        )
    )

    if score >= 0.75:

        priority = "HIGH"

    elif score >= 0.55:

        priority = "MEDIUM"

    else:

        priority = "NORMAL"

    return (
        score,
        priority,
    )


# ============================================================
# PRODUCTION INVENTORY
# ============================================================


def _prepare_production_inventory(
    production_batches: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    dict[str, int],
]:
    """
    Keep only RELEASED production inventory.
    """

    inventory = (
        production_batches[
            (
                production_batches[
                    "batch_status"
                ]
                .astype(str)
                .str.upper()
                ==
                "RELEASED"
            )
            &
            (
                pd.to_numeric(
                    production_batches[
                        "available_for_allocation_units"
                    ],
                    errors="raise",
                )
                >
                0
            )
        ]
        .copy()
    )

    if inventory.empty:

        raise ValueError(
            "No RELEASED production inventory "
            "available for allocation"
        )

    inventory[
        "production_end"
    ] = pd.to_datetime(
        inventory[
            "production_end"
        ]
    )

    inventory = (
        inventory
        .sort_values(
            [
                "vehicle_model_id",
                "production_end",
                "production_batch_id",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    remaining_units = {
        str(
            row.production_batch_id
        ):
            int(
                row.
                available_for_allocation_units
            )

        for row
        in inventory.itertuples(
            index=False
        )
    }

    return (
        inventory,
        remaining_units,
    )


# ============================================================
# PRODUCTION BATCH SELECTION
# ============================================================


def _select_production_batch(
    inventory: pd.DataFrame,
    remaining_units: dict[
        str,
        int,
    ],
    vehicle_model_id: str,
    desired_ready_at: pd.Timestamp,
) -> pd.Series | None:
    """
    Find production inventory for requested model.

    Preference:

    1. recent already-produced inventory
    2. older already-produced inventory
    3. earliest future released batch
    """

    candidates = (
        inventory[
            inventory[
                "vehicle_model_id"
            ]
            .astype(str)
            ==
            str(
                vehicle_model_id
            )
        ]
        .copy()
    )

    if candidates.empty:

        return None

    candidates[
        "_remaining"
    ] = (
        candidates[
            "production_batch_id"
        ]
        .astype(str)
        .map(
            remaining_units
        )
        .fillna(
            0
        )
        .astype(int)
    )

    candidates = (
        candidates[
            candidates[
                "_remaining"
            ]
            >
            0
        ]
        .copy()
    )

    if candidates.empty:

        return None

    # --------------------------------------------------------
    # Already produced
    # --------------------------------------------------------

    already_produced = (
        candidates[
            candidates[
                "production_end"
            ]
            <=
            desired_ready_at
        ]
        .copy()
    )

    if not already_produced.empty:

        ages = (
            (
                desired_ready_at
                -
                already_produced[
                    "production_end"
                ]
            )
            .dt
            .total_seconds()
            /
            86400.0
        )

        recent = (
            already_produced[
                ages
                <=
                RECENT_BATCH_PREFERENCE_DAYS
            ]
            .copy()
        )

        if not recent.empty:

            already_produced = (
                recent
            )

        # Most recent compatible inventory.
        return (
            already_produced
            .sort_values(
                [
                    "production_end",
                    "production_batch_id",
                ],
                ascending=[
                    False,
                    True,
                ],
            )
            .iloc[
                0
            ]
        )

    # --------------------------------------------------------
    # Future production
    # --------------------------------------------------------

    return (
        candidates
        .sort_values(
            [
                "production_end",
                "production_batch_id",
            ]
        )
        .iloc[
            0
        ]
    )


# ============================================================
# GENERATOR
# ============================================================


def generate_allocations(
    bookings: pd.DataFrame,
    cancellations: pd.DataFrame,
    production_batches: pd.DataFrame,
    dealers: pd.DataFrame,
    finance_applications: pd.DataFrame,
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
) -> pd.DataFrame:
    """
    Generate one allocation record for every surviving booking.
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    # ========================================================
    # VALIDATION
    # ========================================================

    _validate_inputs(
        bookings=bookings,

        cancellations=
            cancellations,

        production_batches=
            production_batches,

        dealers=dealers,

        finance_applications=
            finance_applications,
    )

    # ========================================================
    # GENERATION SETTINGS
    # ========================================================

    generation_end = (
        _get_generation_end(
            generation
        )
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
            "auto.allocations",
        )
    )

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
    # SURVIVING BOOKINGS
    # ========================================================

    surviving = (
        _build_surviving_bookings(
            bookings=bookings,
            cancellations=
                cancellations,
        )
    )

    if surviving.empty:

        raise ValueError(
            "No surviving bookings available "
            "for allocation"
        )

    surviving = (
        _add_regional_demand_index(
            surviving
        )
    )

    # ========================================================
    # FINANCE
    # ========================================================

    finance_lookup = (
        _build_finance_lookup(
            finance_applications
        )
    )

    priority_scores: list[
        float
    ] = []

    priority_labels: list[
        str
    ] = []

    finance_statuses: list[
        str | None
    ] = []

    finance_application_ids: list[
        str | None
    ] = []

    for booking in surviving.itertuples(
        index=False
    ):

        finance = (
            finance_lookup.get(
                str(
                    booking.booking_id
                )
            )
        )

        finance_status = None

        finance_application_id = None

        if finance is not None:

            finance_status = str(
                finance.status
            )

            finance_application_id = str(
                finance.
                finance_application_id
            )

        promised_wait_days = max(
            0.0,
            (
                pd.Timestamp(
                    booking.
                    promised_delivery_date
                )
                -
                pd.Timestamp(
                    booking.
                    booking_timestamp
                )
            ).total_seconds()
            /
            86400.0,
        )

        (
            priority_score,
            priority,
        ) = (
            _calculate_allocation_priority(
                regional_demand_index=
                    float(
                        booking.
                        regional_demand_index
                    ),

                promised_wait_days=
                    promised_wait_days,

                finance_assisted=
                    bool(
                        booking.
                        finance_assisted
                    ),

                finance_status=
                    finance_status,
            )
        )

        priority_scores.append(
            priority_score
        )

        priority_labels.append(
            priority
        )

        finance_statuses.append(
            finance_status
        )

        finance_application_ids.append(
            finance_application_id
        )

    surviving[
        "allocation_priority_score"
    ] = priority_scores

    surviving[
        "allocation_priority"
    ] = priority_labels

    surviving[
        "finance_status"
    ] = finance_statuses

    surviving[
        "finance_application_id"
    ] = finance_application_ids

    # ========================================================
    # PROCESS BOOKINGS IN ORDER
    # ========================================================

    surviving[
        "_booking_day"
    ] = (
        surviving[
            "booking_timestamp"
        ]
        .dt
        .floor(
            "D"
        )
    )

    surviving = (
        surviving
        .sort_values(
            [
                "_booking_day",
                "allocation_priority_score",
                "booking_timestamp",
                "booking_id",
            ],
            ascending=[
                True,
                False,
                True,
                True,
            ],
        )
        .reset_index(
            drop=True
        )
    )

    # ========================================================
    # PRODUCTION INVENTORY
    # ========================================================

    (
        inventory,
        remaining_units,
    ) = (
        _prepare_production_inventory(
            production_batches
        )
    )

    # ========================================================
    # DEALER CAPACITY
    # ========================================================

    (
        dealer_capacity_lookup,
        dealer_capacity_source_lookup,
    ) = (
        _build_dealer_capacity_lookup(
            dealers
        )
    )

    # Current allocated stock by dealer/model.
    dealer_inventory: dict[
        tuple[
            str,
            str,
        ],
        int,
    ] = {}

    # ========================================================
    # GENERATION
    # ========================================================

    rows: list[
        dict[str, Any]
    ] = []

    allocation_counter = 1

    vehicle_counter = 1

    for booking in surviving.itertuples(
        index=False
    ):

        booking_time = pd.Timestamp(
            booking.booking_timestamp
        )

        dealer_id = str(
            booking.dealer_id
        )

        model_id = str(
            booking.vehicle_model_id
        )

        dealer_key = (
            dealer_id,
            model_id,
        )

        dealer_capacity = int(
            dealer_capacity_lookup[
                dealer_id
            ]
        )

        dealer_capacity_source = str(
            dealer_capacity_source_lookup[
                dealer_id
            ]
        )

        inventory_before = int(
            dealer_inventory.get(
                dealer_key,
                0,
            )
        )

        # ====================================================
        # INITIAL DESIRED ALLOCATION TIME
        # ====================================================

        available_hours = max(
            0.0,
            (
                generation_end
                -
                booking_time
            ).total_seconds()
            /
            3600.0,
        )

        if available_hours <= 0:

            desired_ready_at = (
                booking_time
            )

        else:

            max_delay = min(
                MAX_ALLOCATION_PROCESSING_HOURS,
                available_hours,
            )

            min_delay = min(
                MIN_ALLOCATION_PROCESSING_HOURS,
                max_delay,
            )

            processing_delay_hours = float(
                rng.uniform(
                    min_delay,
                    max_delay,
                )
            )

            desired_ready_at = (
                booking_time
                +
                timedelta(
                    hours=
                        processing_delay_hours
                )
            )

        # ====================================================
        # FIND PRODUCTION BATCH
        # ====================================================

        selected_batch = (
            _select_production_batch(
                inventory=
                    inventory,

                remaining_units=
                    remaining_units,

                vehicle_model_id=
                    model_id,

                desired_ready_at=
                    desired_ready_at,
            )
        )

        # ====================================================
        # WAITLISTED
        # ====================================================

        if selected_batch is None:

            rows.append(
                {
                    "allocation_id":
                        make_entity_id(
                            "allocation",
                            allocation_counter,
                            width=6,
                        ),

                    "booking_id":
                        booking.booking_id,

                    "lead_id":
                        booking.lead_id,

                    "customer_id":
                        booking.customer_id,

                    "dealer_id":
                        booking.dealer_id,

                    "dealer_name":
                        booking.dealer_name,

                    "region_id":
                        booking.region_id,

                    "region_name":
                        booking.region_name,

                    "city_id":
                        booking.city_id,

                    "city_name":
                        booking.city_name,

                    "vehicle_model_id":
                        booking.vehicle_model_id,

                    "vehicle_model_name":
                        booking.vehicle_model_name,

                    "vehicle_id":
                        None,

                    "production_batch_id":
                        None,

                    "plant_id":
                        None,

                    "plant_name":
                        None,

                    "production_line_id":
                        None,

                    "production_line_name":
                        None,

                    "representative_machine_id":
                        None,

                    "representative_machine_name":
                        None,

                    "variant":
                        None,

                    "primary_supplier_id":
                        None,

                    "primary_supplier_name":
                        None,

                    "primary_supplier_lot_id":
                        None,

                    "supplier_lot_quality_score":
                        None,

                    "production_quality_score":
                        None,

                    "finance_application_id":
                        booking.
                        finance_application_id,

                    "finance_status":
                        booking.finance_status,

                    "allocation_date":
                        desired_ready_at,

                    "requested_units":
                        1,

                    "allocated_units":
                        0,

                    "waiting_list":
                        1,

                    "dealer_capacity":
                        dealer_capacity,

                    "dealer_capacity_source":
                        dealer_capacity_source,

                    "regional_demand_index":
                        round(
                            float(
                                booking.
                                regional_demand_index
                            ),
                            6,
                        ),

                    "allocation_priority_score":
                        round(
                            float(
                                booking.
                                allocation_priority_score
                            ),
                            6,
                        ),

                    "allocation_priority":
                        booking.
                        allocation_priority,

                    "inventory_before":
                        inventory_before,

                    "inventory_after":
                        inventory_before,

                    "production_batch_inventory_before":
                        0,

                    "production_batch_inventory_after":
                        0,

                    "allocation_wait_hours":
                        round(
                            max(
                                0.0,
                                (
                                    desired_ready_at
                                    -
                                    booking_time
                                ).total_seconds()
                                /
                                3600.0,
                            ),
                            3,
                        ),

                    "allocation_status":
                        "WAITLISTED",

                    "data_origin":
                        data_origin,

                    "generator_version":
                        generator_version,
                }
            )

            allocation_counter += 1

            continue

        # ====================================================
        # SELECTED BATCH
        # ====================================================

        batch_id = str(
            selected_batch[
                "production_batch_id"
            ]
        )

        batch_production_end = pd.Timestamp(
            selected_batch[
                "production_end"
            ]
        )

        # Cannot allocate before vehicle is produced.
        allocation_date = max(
            desired_ready_at,
            batch_production_end,
        )

        # If future production is beyond synthetic window,
        # keep booking waitlisted.
        if allocation_date > generation_end:

            rows.append(
                {
                    "allocation_id":
                        make_entity_id(
                            "allocation",
                            allocation_counter,
                            width=6,
                        ),

                    "booking_id":
                        booking.booking_id,

                    "lead_id":
                        booking.lead_id,

                    "customer_id":
                        booking.customer_id,

                    "dealer_id":
                        booking.dealer_id,

                    "dealer_name":
                        booking.dealer_name,

                    "region_id":
                        booking.region_id,

                    "region_name":
                        booking.region_name,

                    "city_id":
                        booking.city_id,

                    "city_name":
                        booking.city_name,

                    "vehicle_model_id":
                        booking.vehicle_model_id,

                    "vehicle_model_name":
                        booking.vehicle_model_name,

                    "vehicle_id":
                        None,

                    "production_batch_id":
                        None,

                    "plant_id":
                        None,

                    "plant_name":
                        None,

                    "production_line_id":
                        None,

                    "production_line_name":
                        None,

                    "representative_machine_id":
                        None,

                    "representative_machine_name":
                        None,

                    "variant":
                        None,

                    "primary_supplier_id":
                        None,

                    "primary_supplier_name":
                        None,

                    "primary_supplier_lot_id":
                        None,

                    "supplier_lot_quality_score":
                        None,

                    "production_quality_score":
                        None,

                    "finance_application_id":
                        booking.
                        finance_application_id,

                    "finance_status":
                        booking.finance_status,

                    "allocation_date":
                        generation_end,

                    "requested_units":
                        1,

                    "allocated_units":
                        0,

                    "waiting_list":
                        1,

                    "dealer_capacity":
                        dealer_capacity,

                    "dealer_capacity_source":
                        dealer_capacity_source,

                    "regional_demand_index":
                        round(
                            float(
                                booking.
                                regional_demand_index
                            ),
                            6,
                        ),

                    "allocation_priority_score":
                        round(
                            float(
                                booking.
                                allocation_priority_score
                            ),
                            6,
                        ),

                    "allocation_priority":
                        booking.
                        allocation_priority,

                    "inventory_before":
                        inventory_before,

                    "inventory_after":
                        inventory_before,

                    "production_batch_inventory_before":
                        int(
                            remaining_units[
                                batch_id
                            ]
                        ),

                    "production_batch_inventory_after":
                        int(
                            remaining_units[
                                batch_id
                            ]
                        ),

                    "allocation_wait_hours":
                        round(
                            max(
                                0.0,
                                (
                                    generation_end
                                    -
                                    booking_time
                                ).total_seconds()
                                /
                                3600.0,
                            ),
                            3,
                        ),

                    "allocation_status":
                        "WAITLISTED",

                    "data_origin":
                        data_origin,

                    "generator_version":
                        generator_version,
                }
            )

            allocation_counter += 1

            continue

        # ====================================================
        # RESERVE ONE VEHICLE
        # ====================================================

        batch_inventory_before = int(
            remaining_units[
                batch_id
            ]
        )

        if batch_inventory_before <= 0:

            raise ValueError(
                f"Production batch {batch_id} "
                "has no remaining inventory"
            )

        remaining_units[
            batch_id
        ] -= 1

        batch_inventory_after = int(
            remaining_units[
                batch_id
            ]
        )

        inventory_after = (
            inventory_before
            +
            1
        )

        dealer_inventory[
            dealer_key
        ] = inventory_after

        vehicle_id = (
    f"VEHUNIT_SYN_"
    f"{vehicle_counter:07d}"
      )

        allocation_wait_hours = max(
            0.0,
            (
                allocation_date
                -
                booking_time
            ).total_seconds()
            /
            3600.0,
        )

        # ====================================================
        # RECORD
        # ====================================================

        rows.append(
            {
                "allocation_id":
                    make_entity_id(
                        "allocation",
                        allocation_counter,
                        width=6,
                    ),

                # --------------------------------------------
                # Commercial journey
                # --------------------------------------------

                "booking_id":
                    booking.booking_id,

                "lead_id":
                    booking.lead_id,

                "customer_id":
                    booking.customer_id,

                # --------------------------------------------
                # Dealer
                # --------------------------------------------

                "dealer_id":
                    booking.dealer_id,

                "dealer_name":
                    booking.dealer_name,

                # --------------------------------------------
                # Geography
                # --------------------------------------------

                "region_id":
                    booking.region_id,

                "region_name":
                    booking.region_name,

                "city_id":
                    booking.city_id,

                "city_name":
                    booking.city_name,

                # --------------------------------------------
                # Vehicle
                # --------------------------------------------

                "vehicle_model_id":
                    booking.vehicle_model_id,

                "vehicle_model_name":
                    booking.vehicle_model_name,

                "vehicle_id":
                    vehicle_id,

                # --------------------------------------------
                # Production traceability
                # --------------------------------------------

                "production_batch_id":
                    selected_batch[
                        "production_batch_id"
                    ],

                "plant_id":
                    selected_batch[
                        "plant_id"
                    ],

                "plant_name":
                    selected_batch[
                        "plant_name"
                    ],

                "production_line_id":
                    selected_batch[
                        "production_line_id"
                    ],

                "production_line_name":
                    selected_batch[
                        "production_line_name"
                    ],

                "representative_machine_id":
                    selected_batch[
                        "representative_machine_id"
                    ],

                "representative_machine_name":
                    selected_batch[
                        "representative_machine_name"
                    ],

                "variant":
                    selected_batch[
                        "variant"
                    ],

                # --------------------------------------------
                # Supplier traceability
                # --------------------------------------------

                "primary_supplier_id":
                    selected_batch[
                        "primary_supplier_id"
                    ],

                "primary_supplier_name":
                    selected_batch[
                        "primary_supplier_name"
                    ],

                "primary_supplier_lot_id":
                    selected_batch[
                        "primary_supplier_lot_id"
                    ],

                "supplier_lot_quality_score":
                    float(
                        selected_batch[
                            "supplier_lot_quality_score"
                        ]
                    ),

                "production_quality_score":
                    float(
                        selected_batch[
                            "quality_score"
                        ]
                    ),

                # --------------------------------------------
                # Finance evidence
                # --------------------------------------------

                "finance_application_id":
                    booking.
                    finance_application_id,

                "finance_status":
                    booking.finance_status,

                # --------------------------------------------
                # Allocation event
                # --------------------------------------------

                "allocation_date":
                    allocation_date,

                "requested_units":
                    1,

                "allocated_units":
                    1,

                "waiting_list":
                    0,

                # --------------------------------------------
                # Dealer capacity
                # --------------------------------------------

                "dealer_capacity":
                    dealer_capacity,

                "dealer_capacity_source":
                    dealer_capacity_source,

                # --------------------------------------------
                # Demand / priority
                # --------------------------------------------

                "regional_demand_index":
                    round(
                        float(
                            booking.
                            regional_demand_index
                        ),
                        6,
                    ),

                "allocation_priority_score":
                    round(
                        float(
                            booking.
                            allocation_priority_score
                        ),
                        6,
                    ),

                "allocation_priority":
                    booking.
                    allocation_priority,

                # --------------------------------------------
                # Dealer inventory
                # --------------------------------------------

                "inventory_before":
                    inventory_before,

                "inventory_after":
                    inventory_after,

                # --------------------------------------------
                # Production inventory
                # --------------------------------------------

                "production_batch_inventory_before":
                    batch_inventory_before,

                "production_batch_inventory_after":
                    batch_inventory_after,

                # --------------------------------------------
                # Waiting time
                # --------------------------------------------

                "allocation_wait_hours":
                    round(
                        allocation_wait_hours,
                        3,
                    ),

                "allocation_status":
                    "ALLOCATED",

                # --------------------------------------------
                # Provenance
                # --------------------------------------------

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

        allocation_counter += 1

        vehicle_counter += 1

    # ========================================================
    # DATAFRAME
    # ========================================================

    allocations = pd.DataFrame(
        rows,
        columns=[
            "allocation_id",

            "booking_id",
            "lead_id",
            "customer_id",

            "dealer_id",
            "dealer_name",

            "region_id",
            "region_name",

            "city_id",
            "city_name",

            "vehicle_model_id",
            "vehicle_model_name",

            "vehicle_id",

            "production_batch_id",

            "plant_id",
            "plant_name",

            "production_line_id",
            "production_line_name",

            "representative_machine_id",
            "representative_machine_name",

            "variant",

            "primary_supplier_id",
            "primary_supplier_name",
            "primary_supplier_lot_id",

            "supplier_lot_quality_score",
            "production_quality_score",

            "finance_application_id",
            "finance_status",

            "allocation_date",

            "requested_units",
            "allocated_units",
            "waiting_list",

            "dealer_capacity",
            "dealer_capacity_source",

            "regional_demand_index",

            "allocation_priority_score",
            "allocation_priority",

            "inventory_before",
            "inventory_after",

            "production_batch_inventory_before",
            "production_batch_inventory_after",

            "allocation_wait_hours",

            "allocation_status",

            "data_origin",
            "generator_version",
        ],
    )

    validate_allocations(
        allocations=allocations,

        surviving_bookings=
            surviving,

        production_batches=
            production_batches,

        generation_end=
            generation_end,
    )

    return allocations


# ============================================================
# VALIDATION
# ============================================================


def validate_allocations(
    allocations: pd.DataFrame,
    surviving_bookings: pd.DataFrame,
    production_batches: pd.DataFrame,
    generation_end: pd.Timestamp,
) -> None:
    """
    Validate generated allocation records.
    """

    required_columns = {
        "allocation_id",

        "booking_id",
        "lead_id",
        "customer_id",

        "dealer_id",

        "vehicle_model_id",

        "vehicle_id",

        "production_batch_id",

        "allocation_date",

        "requested_units",
        "allocated_units",
        "waiting_list",

        "dealer_capacity",

        "regional_demand_index",

        "allocation_priority_score",
        "allocation_priority",

        "inventory_before",
        "inventory_after",

        "production_batch_inventory_before",
        "production_batch_inventory_after",

        "allocation_wait_hours",

        "allocation_status",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        .difference(
            allocations.columns
        )
    )

    if missing:

        raise ValueError(
            "Allocations DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if allocations.empty:

        raise ValueError(
            "No allocation records generated"
        )

    # ========================================================
    # UNIQUE IDs
    # ========================================================

    if allocations[
        "allocation_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate allocation_id values found"
        )

    if allocations[
        "booking_id"
    ].duplicated().any():

        raise ValueError(
            "A surviving booking has more "
            "than one allocation record"
        )

    # ========================================================
    # EXACT SURVIVING BOOKING COVERAGE
    # ========================================================

    expected_booking_ids = set(
        surviving_bookings[
            "booking_id"
        ]
        .astype(str)
    )

    actual_booking_ids = set(
        allocations[
            "booking_id"
        ]
        .astype(str)
    )

    if (
        actual_booking_ids
        !=
        expected_booking_ids
    ):

        missing_bookings = (
            expected_booking_ids
            -
            actual_booking_ids
        )

        extra_bookings = (
            actual_booking_ids
            -
            expected_booking_ids
        )

        raise ValueError(
            "Allocation coverage mismatch. "
            f"Missing={len(missing_bookings)}, "
            f"Extra={len(extra_bookings)}"
        )

    # ========================================================
    # STATUS
    # ========================================================

    invalid_statuses = (
        set(
            allocations[
                "allocation_status"
            ]
        )
        -
        VALID_ALLOCATION_STATUSES
    )

    if invalid_statuses:

        raise ValueError(
            "Invalid allocation statuses found"
        )

    invalid_priorities = (
        set(
            allocations[
                "allocation_priority"
            ]
        )
        -
        VALID_PRIORITIES
    )

    if invalid_priorities:

        raise ValueError(
            "Invalid allocation priorities found"
        )

    # ========================================================
    # DEMAND INDEX / PRIORITY
    # ========================================================

    for column in (
        "regional_demand_index",
        "allocation_priority_score",
    ):

        values = pd.to_numeric(
            allocations[
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
                f"{column} must be "
                "between 0 and 1"
            )

    # ========================================================
    # UNIT COUNTS
    # ========================================================

    if not (
        allocations[
            "requested_units"
        ]
        ==
        1
    ).all():

        raise ValueError(
            "Every booking must request exactly 1 unit"
        )

    # ========================================================
    # ALLOCATED ROWS
    # ========================================================

    allocated = (
        allocations[
            "allocation_status"
        ]
        ==
        "ALLOCATED"
    )

    if (
        allocations.loc[
            allocated,
            "vehicle_id",
        ]
        .isna()
        .any()
    ):

        raise ValueError(
            "Allocated records must have vehicle_id"
        )

    if (
        allocations.loc[
            allocated,
            "production_batch_id",
        ]
        .isna()
        .any()
    ):

        raise ValueError(
            "Allocated records must have "
            "production_batch_id"
        )

    if not (
        allocations.loc[
            allocated,
            "allocated_units",
        ]
        ==
        1
    ).all():

        raise ValueError(
            "Allocated records must "
            "have allocated_units=1"
        )

    if not (
        allocations.loc[
            allocated,
            "waiting_list",
        ]
        ==
        0
    ).all():

        raise ValueError(
            "Allocated records cannot "
            "be on waiting list"
        )

    # Vehicle must be unique.
    vehicle_ids = (
        allocations.loc[
            allocated,
            "vehicle_id",
        ]
    )

    if vehicle_ids.duplicated().any():

        raise ValueError(
            "Duplicate vehicle_id values found"
        )

    # ========================================================
    # WAITLISTED ROWS
    # ========================================================

    waitlisted = (
        allocations[
            "allocation_status"
        ]
        ==
        "WAITLISTED"
    )

    if not (
        allocations.loc[
            waitlisted,
            "allocated_units",
        ]
        ==
        0
    ).all():

        raise ValueError(
            "Waitlisted records must "
            "have allocated_units=0"
        )

    if not (
        allocations.loc[
            waitlisted,
            "waiting_list",
        ]
        ==
        1
    ).all():

        raise ValueError(
            "Waitlisted records must "
            "have waiting_list=1"
        )

    if (
        allocations.loc[
            waitlisted,
            "vehicle_id",
        ]
        .notna()
        .any()
    ):

        raise ValueError(
            "Waitlisted bookings cannot "
            "have vehicle_id"
        )

    # ========================================================
    # TIME
    # ========================================================

    allocation_dates = pd.to_datetime(
        allocations[
            "allocation_date"
        ]
    )

    if (
        allocation_dates
        >
        generation_end
    ).any():

        raise ValueError(
            "Allocation occurs after generation end"
        )

    if (
        pd.to_numeric(
            allocations[
                "allocation_wait_hours"
            ],
            errors="raise",
        )
        <
        0
    ).any():

        raise ValueError(
            "allocation_wait_hours cannot be negative"
        )

    # ========================================================
    # LOOKUPS
    # ========================================================

    booking_lookup = {
        str(
            row.booking_id
        ):
            row

        for row
        in surviving_bookings.itertuples(
            index=False
        )
    }

    batch_lookup = {
        str(
            row.production_batch_id
        ):
            row

        for row
        in production_batches.itertuples(
            index=False
        )
    }

    # ========================================================
    # ROW CONSISTENCY
    # ========================================================

    for row in allocations.itertuples(
        index=False
    ):

        booking = (
            booking_lookup[
                str(
                    row.booking_id
                )
            ]
        )

        allocation_date = pd.Timestamp(
            row.allocation_date
        )

        booking_time = pd.Timestamp(
            booking.
            booking_timestamp
        )

        if allocation_date < booking_time:

            raise ValueError(
                f"{row.allocation_id}: "
                "allocation occurs before booking"
            )

        if (
            str(
                row.customer_id
            )
            !=
            str(
                booking.customer_id
            )
        ):

            raise ValueError(
                f"{row.allocation_id}: "
                "customer mismatch"
            )

        if (
            str(
                row.dealer_id
            )
            !=
            str(
                booking.dealer_id
            )
        ):

            raise ValueError(
                f"{row.allocation_id}: "
                "dealer mismatch"
            )

        if (
            str(
                row.vehicle_model_id
            )
            !=
            str(
                booking.
                vehicle_model_id
            )
        ):

            raise ValueError(
                f"{row.allocation_id}: "
                "vehicle model mismatch "
                "with booking"
            )

        if (
            row.allocation_status
            !=
            "ALLOCATED"
        ):

            continue

        batch = (
            batch_lookup[
                str(
                    row.
                    production_batch_id
                )
            ]
        )

        production_end = pd.Timestamp(
            batch.production_end
        )

        if allocation_date < production_end:

            raise ValueError(
                f"{row.allocation_id}: "
                "vehicle allocated before "
                "production completion"
            )

        if (
            str(
                row.vehicle_model_id
            )
            !=
            str(
                batch.
                vehicle_model_id
            )
        ):

            raise ValueError(
                f"{row.allocation_id}: "
                "production batch model "
                "does not match booking model"
            )

        if (
            batch.batch_status
            !=
            "RELEASED"
        ):

            raise ValueError(
                f"{row.allocation_id}: "
                "allocation uses non-released "
                "production batch"
            )

        # ----------------------------------------------------
        # Dealer inventory transition
        # ----------------------------------------------------

        if (
            int(
                row.inventory_after
            )
            !=
            int(
                row.inventory_before
            )
            +
            1
        ):

            raise ValueError(
                f"{row.allocation_id}: "
                "dealer inventory transition invalid"
            )

        # ----------------------------------------------------
        # Production inventory transition
        # ----------------------------------------------------

        if (
            int(
                row.
                production_batch_inventory_after
            )
            !=
            int(
                row.
                production_batch_inventory_before
            )
            -
            1
        ):

            raise ValueError(
                f"{row.allocation_id}: "
                "production inventory transition invalid"
            )

    # ========================================================
    # PRODUCTION INVENTORY CANNOT BE OVER-ALLOCATED
    # ========================================================

    allocated_rows = (
        allocations[
            allocations[
                "allocation_status"
            ]
            ==
            "ALLOCATED"
        ]
        .copy()
    )

    if not allocated_rows.empty:

        usage = (
            allocated_rows
            .groupby(
                "production_batch_id"
            )
            .size()
        )

        available_lookup = (
            production_batches
            .set_index(
                "production_batch_id"
            )[
                "available_for_allocation_units"
            ]
        )

        for (
            batch_id,
            allocated_count,
        ) in usage.items():

            available_units = int(
                available_lookup[
                    batch_id
                ]
            )

            if (
                int(
                    allocated_count
                )
                >
                available_units
            ):

                raise ValueError(
                    f"Production batch {batch_id} "
                    "allocated beyond available inventory"
                )


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_allocation_master(
    bookings: pd.DataFrame,
    cancellations: pd.DataFrame,
    production_batches: pd.DataFrame,
    dealers: pd.DataFrame,
    finance_applications: pd.DataFrame,
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
) -> pd.DataFrame:
    """
    Public entry point later used by generate_all.py.
    """

    return generate_allocations(
        bookings=bookings,

        cancellations=
            cancellations,

        production_batches=
            production_batches,

        dealers=dealers,

        finance_applications=
            finance_applications,

        generation=generation,
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

    from data.generators.master.dealers import (
        generate_dealer_master,
    )

    from data.generators.master.plants import (
        generate_plant_master,
    )

    from data.generators.master.machines import (
        generate_machine_master,
    )

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

    dealers_df = (
        generate_dealer_master(
            regions=regions_df,
            cities=cities_df,
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
    # COMMERCIAL JOURNEY
    # ========================================================

    customers_df = (
        generate_customer_master(
            regions=regions_df,

            cities=cities_df,

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
    # SUPPLY / MANUFACTURING
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
    # ALLOCATIONS
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
    # SAMPLE
    # ========================================================

    print(
        "\n=== ALLOCATION SAMPLE ===\n"
    )

    display_columns = [
        "allocation_id",
        "booking_id",

        "dealer_name",
        "region_name",

        "vehicle_model_name",
        "vehicle_id",

        "production_batch_id",
        "variant",

        "plant_name",

        "primary_supplier_name",

        "allocation_priority",

        "regional_demand_index",

        "allocation_wait_hours",

        "allocation_status",
    ]

    print(
        allocations_df[
            display_columns
        ]
        .head(
            30
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # STATUS
    # ========================================================

    print(
        "\n=== ALLOCATION STATUS ===\n"
    )

    print(
        allocations_df
        .groupby(
            "allocation_status"
        )
        .size()
        .reset_index(
            name="allocation_count"
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # PRIORITY
    # ========================================================

    print(
        "\n=== ALLOCATION PRIORITY ===\n"
    )

    print(
        allocations_df
        .groupby(
            "allocation_priority"
        )
        .size()
        .reset_index(
            name="allocation_count"
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # KPI CHECK
    # ========================================================

    cancelled_booking_ids = set(
        cancellations_df[
            "booking_id"
        ]
    )

    surviving_count = int(
        (
            ~bookings_df[
                "booking_id"
            ]
            .isin(
                cancelled_booking_ids
            )
        )
        .sum()
    )

    allocated_df = (
        allocations_df[
            allocations_df[
                "allocation_status"
            ]
            ==
            "ALLOCATED"
        ]
    )

    waitlisted_df = (
        allocations_df[
            allocations_df[
                "allocation_status"
            ]
            ==
            "WAITLISTED"
        ]
    )

    print(
        "\n=== ALLOCATION KPI CHECK ===\n"
    )

    print(
        "Bookings:",
        len(
            bookings_df
        ),
    )

    print(
        "Cancellations:",
        len(
            cancellations_df
        ),
    )

    print(
        "Surviving bookings:",
        surviving_count,
    )

    print(
        "Allocation records:",
        len(
            allocations_df
        ),
    )

    print(
        "Successfully allocated:",
        len(
            allocated_df
        ),
    )

    print(
        "Waitlisted:",
        len(
            waitlisted_df
        ),
    )

    if not allocated_df.empty:

        print(
            "Unique vehicle units:",
            allocated_df[
                "vehicle_id"
            ]
            .nunique(),
        )

        print(
            "Average allocation wait:",
            round(
                allocated_df[
                    "allocation_wait_hours"
                ]
                .mean(),
                2,
            ),
            "hours",
        )

        print(
            "Average regional demand index:",
            round(
                allocated_df[
                    "regional_demand_index"
                ]
                .mean(),
                3,
            ),
        )

    print(
        "\nGenerated "
        f"{len(allocations_df)} "
        "synthetic allocation records from "
        f"{surviving_count} surviving bookings "
        "successfully."
    )