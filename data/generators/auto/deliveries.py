"""
Synthetic Vehicle Delivery generator for Mahindra AI Nexus.

Dependency chain:

Booking
    ↓
Allocation
    ↓
Vehicle Unit
    ↓
Delivery
    ↓
Service
    ↓
Warranty

Inputs:
    bookings
    allocations

Outputs:
    deliveries DataFrame

Important distinction:

    dispatch_at
        ↓
    physical_ready_date
        ↓
    projected_delivery_date
        ↓
    actual_delivery_date

physical_ready_date:
    Vehicle has physically reached / become ready at the dealer.

actual_delivery_date:
    Customer actually receives the vehicle.

This distinction is important because a vehicle can reach the
dealer before the customer's promised delivery date.

Delivery delay is derived from:

    promised_delivery_date
                vs
    actual/projected delivery date

This module DOES NOT write CSV files.

Later generate_all.py will save:

    data/synthetic/auto/deliveries.csv

All values are synthetic PoC assumptions.
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
# DELIVERY PROCESS ASSUMPTIONS
# ============================================================

MIN_DISPATCH_DELAY_HOURS = 6.0
MAX_DISPATCH_DELAY_HOURS = 48.0

MIN_TRANSIT_DAYS = 1.5
MAX_TRANSIT_DAYS = 8.0


# ============================================================
# DEMAND / QUALITY PRESSURE
# ============================================================

DEMAND_PRESSURE_THRESHOLD = 0.70

QUALITY_HOLD_THRESHOLD = 0.94


# ============================================================
# TRANSPORT DISRUPTION
# ============================================================

DELIVERY_DISRUPTION_PROBABILITY = 0.12

MIN_DISRUPTION_DAYS = 1.0
MAX_DISRUPTION_DAYS = 8.0


# ============================================================
# CUSTOMER HANDOVER BEHAVIOUR
#
# Most vehicles are handed over slightly before their
# committed date.
#
# Some experience normal operational delay.
# ============================================================

MIN_EARLY_HANDOVER_DAYS = 0.5
MAX_EARLY_HANDOVER_DAYS = 6.0

NORMAL_DELAY_PROBABILITY = 0.18

MIN_NORMAL_DELAY_DAYS = 0.5
MAX_NORMAL_DELAY_DAYS = 5.0


# ============================================================
# DEMAND-RELATED HANDOVER DELAY
# ============================================================

DEMAND_DELAY_DAYS_MIN = 1.0
DEMAND_DELAY_DAYS_MAX = 5.0


# ============================================================
# QUALITY-HOLD DELAY
# ============================================================

QUALITY_DELAY_DAYS_MIN = 1.0
QUALITY_DELAY_DAYS_MAX = 4.0


# ============================================================
# VALID VALUES
# ============================================================

VALID_DELIVERY_STATUSES = {
    "DELIVERED",
    "IN_TRANSIT",
}


VALID_DELAY_REASONS = {
    "NONE",

    "ALLOCATION_DELAY",

    "HANDOVER_DELAY",

    "DEMAND_PRESSURE",

    "QUALITY_HOLD",

    "TRANSPORT_DELAY",

    "MULTIPLE_FACTORS",
}


# ============================================================
# GENERATION END
# ============================================================


def _get_generation_end(
    generation: Mapping[str, Any],
) -> pd.Timestamp:
    """
    Return configured synthetic generation end timestamp.
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

    iot_config = generation.get("iot", {})
    end_value = iot_config.get(
        "end_date",
        time_config.get(
            "end",
            time_config.get(
                "end_date"
            ),
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
    allocations: pd.DataFrame,
) -> None:
    """
    Validate booking and allocation inputs.
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
    }

    missing_booking = (
        booking_required
        .difference(
            bookings.columns
        )
    )

    if missing_booking:

        raise ValueError(
            "Bookings DataFrame is missing "
            "columns required by deliveries.py: "
            + ", ".join(
                sorted(
                    missing_booking
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
    # ALLOCATIONS
    # --------------------------------------------------------

    allocation_required = {
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

        "allocation_date",

        "allocation_wait_hours",

        "regional_demand_index",

        "allocation_priority",

        "allocation_status",
    }

    missing_allocation = (
        allocation_required
        .difference(
            allocations.columns
        )
    )

    if missing_allocation:

        raise ValueError(
            "Allocations DataFrame is missing "
            "columns required by deliveries.py: "
            + ", ".join(
                sorted(
                    missing_allocation
                )
            )
        )

    if allocations.empty:

        raise ValueError(
            "Allocations DataFrame cannot be empty"
        )

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
            "A booking has multiple "
            "allocation records"
        )

    # --------------------------------------------------------
    # ALLOCATION -> BOOKING FK
    # --------------------------------------------------------

    invalid_booking_ids = (
        set(
            allocations[
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
            "Allocations reference invalid booking IDs"
        )


# ============================================================
# DISPATCH DELAY
# ============================================================


def _calculate_dispatch_delay_hours(
    rng: np.random.Generator,
    regional_demand_index: float,
    allocation_priority: str,
) -> float:
    """
    Generate dispatch preparation time.

    Higher demand:
        slightly slower processing.

    Higher allocation priority:
        slightly faster processing.
    """

    delay = float(
        rng.uniform(
            MIN_DISPATCH_DELAY_HOURS,
            MAX_DISPATCH_DELAY_HOURS,
        )
    )

    demand = float(
        np.clip(
            regional_demand_index,
            0.0,
            1.0,
        )
    )

    # --------------------------------------------------------
    # HIGH DEMAND
    # --------------------------------------------------------

    if (
        demand
        >
        DEMAND_PRESSURE_THRESHOLD
    ):

        delay += (
            (
                demand
                -
                DEMAND_PRESSURE_THRESHOLD
            )
            *
            36.0
        )

    # --------------------------------------------------------
    # ALLOCATION PRIORITY
    # --------------------------------------------------------

    priority = (
        str(
            allocation_priority
        )
        .strip()
        .upper()
    )

    if priority == "HIGH":

        delay *= 0.78

    elif priority == "MEDIUM":

        delay *= 0.90

    return max(
        2.0,
        float(
            delay
        ),
    )


# ============================================================
# TRANSIT
# ============================================================


def _calculate_transit_days(
    rng: np.random.Generator,
    regional_demand_index: float,
    production_quality_score: float,
) -> tuple[
    float,
    bool,
    bool,
]:
    """
    Generate physical logistics time.

    Returns:

        transit_days
        demand_pressure
        quality_hold
    """

    transit_days = float(
        rng.uniform(
            MIN_TRANSIT_DAYS,
            MAX_TRANSIT_DAYS,
        )
    )

    demand = float(
        np.clip(
            regional_demand_index,
            0.0,
            1.0,
        )
    )

    production_quality = float(
        np.clip(
            production_quality_score,
            0.0,
            1.0,
        )
    )

    # ========================================================
    # DEMAND PRESSURE
    # ========================================================

    demand_pressure = bool(
        demand
        >
        DEMAND_PRESSURE_THRESHOLD
    )

    if demand_pressure:

        transit_days += (
            (
                demand
                -
                DEMAND_PRESSURE_THRESHOLD
            )
            *
            7.0
        )

    # ========================================================
    # QUALITY HOLD
    # ========================================================

    quality_hold = bool(
        production_quality
        <
        QUALITY_HOLD_THRESHOLD
    )

    if quality_hold:

        quality_gap = (
            QUALITY_HOLD_THRESHOLD
            -
            production_quality
        )

        transit_days += (
            1.0
            +
            quality_gap
            * 12.0
        )

    return (
        max(
            1.0,
            transit_days,
        ),
        demand_pressure,
        quality_hold,
    )


# ============================================================
# TRANSPORT DISRUPTION
# ============================================================


def _generate_transport_disruption(
    rng: np.random.Generator,
) -> tuple[
    bool,
    float,
]:
    """
    Generate occasional transport disruption.
    """

    disrupted = bool(
        float(
            rng.random()
        )
        <
        DELIVERY_DISRUPTION_PROBABILITY
    )

    if not disrupted:

        return (
            False,
            0.0,
        )

    disruption_days = float(
        rng.uniform(
            MIN_DISRUPTION_DAYS,
            MAX_DISRUPTION_DAYS,
        )
    )

    return (
        True,
        disruption_days,
    )


# ============================================================
# CUSTOMER HANDOVER
# ============================================================


def _generate_customer_handover_date(
    rng: np.random.Generator,

    physical_ready_date: pd.Timestamp,

    promised_delivery_date: pd.Timestamp,

    demand_pressure: bool,

    quality_hold: bool,

    transport_disruption: bool,

    disruption_days: float,
) -> tuple[
    pd.Timestamp,
    bool,
]:
    """
    Generate the projected customer handover date.

    Most customers receive vehicles slightly before the
    promised date.

    Some receive them after the promised date because of:

        normal operational delay
        demand pressure
        quality hold
        transport disruption

    The vehicle can NEVER be delivered before it is
    physically ready.

    Returns:

        projected_handover_date
        normal_handover_delay
    """

    physical_ready_date = pd.Timestamp(
        physical_ready_date
    )

    promised_delivery_date = pd.Timestamp(
        promised_delivery_date
    )

    # ========================================================
    # NORMAL LATE HANDOVER?
    # ========================================================

    normal_handover_delay = bool(
        float(
            rng.random()
        )
        <
        NORMAL_DELAY_PROBABILITY
    )

    if normal_handover_delay:

        # ----------------------------------------------------
        # Deliberately after promised date.
        # ----------------------------------------------------

        normal_delay_days = float(
            rng.uniform(
                MIN_NORMAL_DELAY_DAYS,
                MAX_NORMAL_DELAY_DAYS,
            )
        )

        planned_handover = (
            promised_delivery_date
            +
            timedelta(
                days=
                    normal_delay_days
            )
        )

    else:

        # ----------------------------------------------------
        # Usually delivered a little early.
        # ----------------------------------------------------

        early_days = float(
            rng.uniform(
                MIN_EARLY_HANDOVER_DAYS,
                MAX_EARLY_HANDOVER_DAYS,
            )
        )

        planned_handover = (
            promised_delivery_date
            -
            timedelta(
                days=
                    early_days
            )
        )

    # ========================================================
    # CANNOT DELIVER BEFORE VEHICLE IS PHYSICALLY READY
    # ========================================================

    handover_date = max(
        planned_handover,
        physical_ready_date,
    )

    # ========================================================
    # DEMAND PRESSURE
    # ========================================================

    if demand_pressure:

        demand_delay = float(
            rng.uniform(
                DEMAND_DELAY_DAYS_MIN,
                DEMAND_DELAY_DAYS_MAX,
            )
        )

        handover_date += timedelta(
            days=
                demand_delay
        )

    # ========================================================
    # QUALITY HOLD
    # ========================================================

    if quality_hold:

        quality_delay = float(
            rng.uniform(
                QUALITY_DELAY_DAYS_MIN,
                QUALITY_DELAY_DAYS_MAX,
            )
        )

        handover_date += timedelta(
            days=
                quality_delay
        )

    # ========================================================
    # ADDITIONAL DISRUPTION IMPACT
    #
    # Most disruption time is already included in physical
    # transit.
    #
    # A smaller handover impact remains possible.
    # ========================================================

    if transport_disruption:

        additional_effect = min(
            float(
                disruption_days
            )
            * 0.25,
            2.0,
        )

        handover_date += timedelta(
            days=
                additional_effect
        )

    return (
        handover_date,
        normal_handover_delay,
    )


# ============================================================
# DELAY REASON
# ============================================================


def _derive_delay_reason(
    delayed: bool,

    allocation_date: pd.Timestamp,

    promised_delivery_date: pd.Timestamp,

    normal_handover_delay: bool,

    demand_pressure: bool,

    quality_hold: bool,

    transport_disruption: bool,

    physical_ready_date: pd.Timestamp,
) -> str:
    """
    Derive delivery delay explanation from generated evidence.
    """

    if not delayed:

        return "NONE"

    reasons: list[str] = []

    # ========================================================
    # ALLOCATION ITSELF OCCURRED TOO LATE
    # ========================================================

    if (
        allocation_date
        >
        promised_delivery_date
    ):

        reasons.append(
            "ALLOCATION_DELAY"
        )

    # ========================================================
    # NORMAL DEALER / CUSTOMER HANDOVER SLIPPAGE
    # ========================================================

    if normal_handover_delay:

        reasons.append(
            "HANDOVER_DELAY"
        )

    # ========================================================
    # HIGH REGIONAL DEMAND
    # ========================================================

    if demand_pressure:

        reasons.append(
            "DEMAND_PRESSURE"
        )

    # ========================================================
    # QUALITY HOLD
    # ========================================================

    if quality_hold:

        reasons.append(
            "QUALITY_HOLD"
        )

    # ========================================================
    # TRANSPORT
    # ========================================================

    if transport_disruption:

        reasons.append(
            "TRANSPORT_DELAY"
        )

    # Vehicle physically became ready after commitment,
    # even without an explicit disruption flag.
    if (
        physical_ready_date
        >
        promised_delivery_date
        and
        "TRANSPORT_DELAY"
        not in reasons
        and
        "ALLOCATION_DELAY"
        not in reasons
    ):

        reasons.append(
            "TRANSPORT_DELAY"
        )

    # ========================================================
    # FALLBACK
    # ========================================================

    if not reasons:

        return "HANDOVER_DELAY"

    # Remove accidental duplicates.
    reasons = list(
        dict.fromkeys(
            reasons
        )
    )

    if len(
        reasons
    ) == 1:

        return reasons[
            0
        ]

    return "MULTIPLE_FACTORS"


# ============================================================
# HANDOVER SCORE
# ============================================================


def _generate_handover_score(
    rng: np.random.Generator,

    delay_days: float,

    production_quality_score: float,
) -> float:
    """
    Generate synthetic customer handover score.

    Range:
        1 → 5

    Delay decreases satisfaction.

    Better production quality slightly improves satisfaction.
    """

    quality = float(
        np.clip(
            production_quality_score,
            0.0,
            1.0,
        )
    )

    base_score = float(
        rng.normal(
            4.35,
            0.35,
        )
    )

    # --------------------------------------------------------
    # DELAY PENALTY
    # --------------------------------------------------------

    delay_penalty = min(
        float(
            delay_days
        )
        * 0.08,
        1.7,
    )

    # --------------------------------------------------------
    # QUALITY ADJUSTMENT
    # --------------------------------------------------------

    quality_adjustment = (
        (
            quality
            -
            0.90
        )
        *
        1.5
    )

    score = (
        base_score
        -
        delay_penalty
        +
        quality_adjustment
    )

    return round(
        float(
            np.clip(
                score,
                1.0,
                5.0,
            )
        ),
        2,
    )


# ============================================================
# GENERATOR
# ============================================================


def generate_deliveries(
    bookings: pd.DataFrame,

    allocations: pd.DataFrame,

    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate one delivery lifecycle record for every
    successfully allocated vehicle.
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    # ========================================================
    # INPUTS
    # ========================================================

    _validate_inputs(
        bookings=bookings,
        allocations=allocations,
    )

    # ========================================================
    # TIME
    # ========================================================

    generation_end = (
        _get_generation_end(
            generation
        )
    )

    # ========================================================
    # RNG
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

    rng = make_rng(
        derive_seed(
            base_seed,
            "auto.deliveries",
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
    # BOOKING LOOKUP
    # ========================================================

    booking_lookup = {
        str(
            row.booking_id
        ):
            row

        for row
        in bookings.itertuples(
            index=False
        )
    }

    # ========================================================
    # ALLOCATED VEHICLES ONLY
    # ========================================================

    allocated = (
        allocations[
            allocations[
                "allocation_status"
            ]
            .astype(str)
            .str.upper()
            ==
            "ALLOCATED"
        ]
        .copy()
    )

    if allocated.empty:

        raise ValueError(
            "No ALLOCATED vehicles available "
            "for delivery generation"
        )

    # ========================================================
    # GENERATE
    # ========================================================

    rows: list[
        dict[str, Any]
    ] = []

    delivery_counter = 1

    for allocation in allocated.itertuples(
        index=False
    ):

        booking = booking_lookup.get(
            str(
                allocation.booking_id
            )
        )

        if booking is None:

            raise ValueError(
                f"Allocation "
                f"{allocation.allocation_id} "
                "references unknown booking "
                f"{allocation.booking_id}"
            )

        # ====================================================
        # JOURNEY TIMES
        # ====================================================

        booking_timestamp = pd.Timestamp(
            booking.booking_timestamp
        )

        promised_delivery_date = pd.Timestamp(
            booking.promised_delivery_date
        )

        allocation_date = pd.Timestamp(
            allocation.allocation_date
        )

        # ====================================================
        # DISPATCH
        # ====================================================

        dispatch_delay_hours = (
            _calculate_dispatch_delay_hours(
                rng=rng,

                regional_demand_index=
                    float(
                        allocation.
                        regional_demand_index
                    ),

                allocation_priority=
                    str(
                        allocation.
                        allocation_priority
                    ),
            )
        )

        dispatch_at = (
            allocation_date
            +
            timedelta(
                hours=
                    dispatch_delay_hours
            )
        )

        # ====================================================
        # PHYSICAL TRANSIT
        # ====================================================

        (
            base_transit_days,
            demand_pressure,
            quality_hold,
        ) = (
            _calculate_transit_days(
                rng=rng,

                regional_demand_index=
                    float(
                        allocation.
                        regional_demand_index
                    ),

                production_quality_score=
                    float(
                        allocation.
                        production_quality_score
                    ),
            )
        )

        # ====================================================
        # TRANSPORT DISRUPTION
        # ====================================================

        (
            transport_disruption,
            disruption_days,
        ) = (
            _generate_transport_disruption(
                rng
            )
        )

        total_transit_days = (
            base_transit_days
            +
            disruption_days
        )

        # ====================================================
        # PHYSICAL READY DATE
        #
        # This is when the vehicle becomes physically
        # available at/near the dealer.
        # ====================================================

        physical_ready_date = (
            dispatch_at
            +
            timedelta(
                days=
                    total_transit_days
            )
        )

        # ====================================================
        # CUSTOMER HANDOVER DATE
        # ====================================================

        (
            projected_delivery_date,
            normal_handover_delay,
        ) = (
            _generate_customer_handover_date(
                rng=rng,

                physical_ready_date=
                    physical_ready_date,

                promised_delivery_date=
                    promised_delivery_date,

                demand_pressure=
                    demand_pressure,

                quality_hold=
                    quality_hold,

                transport_disruption=
                    transport_disruption,

                disruption_days=
                    disruption_days,
            )
        )

        # ====================================================
        # DELIVERY STATUS
        # ====================================================

        if (
            projected_delivery_date
            <=
            generation_end
        ):

            delivery_status = (
                "DELIVERED"
            )

            actual_delivery_date = (
                projected_delivery_date
            )

            customer_handover_completed = (
                True
            )

        else:

            delivery_status = (
                "IN_TRANSIT"
            )

            actual_delivery_date = None

            customer_handover_completed = (
                False
            )

        # ====================================================
        # DELIVERY VARIANCE
        #
        # < 0 = early
        # = 0 = on time
        # > 0 = delayed
        # ====================================================

        delivery_variance_days = (
            (
                projected_delivery_date
                -
                promised_delivery_date
            ).total_seconds()
            /
            86400.0
        )

        delay_days = max(
            0.0,
            delivery_variance_days,
        )

        early_days = max(
            0.0,
            -delivery_variance_days,
        )

        delayed = bool(
            delay_days
            >
            0
        )

        # ====================================================
        # DELAY REASON
        # ====================================================

        delay_reason = (
            _derive_delay_reason(
                delayed=
                    delayed,

                allocation_date=
                    allocation_date,

                promised_delivery_date=
                    promised_delivery_date,

                normal_handover_delay=
                    normal_handover_delay,

                demand_pressure=
                    demand_pressure,

                quality_hold=
                    quality_hold,

                transport_disruption=
                    transport_disruption,

                physical_ready_date=
                    physical_ready_date,
            )
        )

        # ====================================================
        # HANDOVER SCORE
        # ====================================================

        if (
            delivery_status
            ==
            "DELIVERED"
        ):

            handover_score = (
                _generate_handover_score(
                    rng=rng,

                    delay_days=
                        delay_days,

                    production_quality_score=
                        float(
                            allocation.
                            production_quality_score
                        ),
                )
            )

        else:

            handover_score = None

        # ====================================================
        # RECORD
        # ====================================================

        rows.append(
            {
                # --------------------------------------------
                # DELIVERY ID
                # --------------------------------------------

                "delivery_id":
                    make_entity_id(
                        "delivery",
                        delivery_counter,
                        width=6,
                    ),

                # --------------------------------------------
                # JOURNEY
                # --------------------------------------------

                "allocation_id":
                    allocation.allocation_id,

                "booking_id":
                    allocation.booking_id,

                "lead_id":
                    allocation.lead_id,

                "customer_id":
                    allocation.customer_id,

                # --------------------------------------------
                # VEHICLE
                # --------------------------------------------

                "vehicle_id":
                    allocation.vehicle_id,

                "vehicle_model_id":
                    allocation.vehicle_model_id,

                "vehicle_model_name":
                    allocation.vehicle_model_name,

                "variant":
                    allocation.variant,

                # --------------------------------------------
                # DEALER
                # --------------------------------------------

                "dealer_id":
                    allocation.dealer_id,

                "dealer_name":
                    allocation.dealer_name,

                # --------------------------------------------
                # GEOGRAPHY
                # --------------------------------------------

                "region_id":
                    allocation.region_id,

                "region_name":
                    allocation.region_name,

                "city_id":
                    allocation.city_id,

                "city_name":
                    allocation.city_name,

                # --------------------------------------------
                # PRODUCTION TRACEABILITY
                # --------------------------------------------

                "production_batch_id":
                    allocation.production_batch_id,

                "plant_id":
                    allocation.plant_id,

                "plant_name":
                    allocation.plant_name,

                "production_line_id":
                    allocation.production_line_id,

                "production_line_name":
                    allocation.production_line_name,

                "representative_machine_id":
                    allocation.
                    representative_machine_id,

                "representative_machine_name":
                    allocation.
                    representative_machine_name,

                # --------------------------------------------
                # SUPPLIER TRACEABILITY
                # --------------------------------------------

                "primary_supplier_id":
                    allocation.primary_supplier_id,

                "primary_supplier_name":
                    allocation.primary_supplier_name,

                "primary_supplier_lot_id":
                    allocation.
                    primary_supplier_lot_id,

                "supplier_lot_quality_score":
                    round(
                        float(
                            allocation.
                            supplier_lot_quality_score
                        ),
                        6,
                    ),

                "production_quality_score":
                    round(
                        float(
                            allocation.
                            production_quality_score
                        ),
                        6,
                    ),

                # --------------------------------------------
                # JOURNEY DATES
                # --------------------------------------------

                "booking_timestamp":
                    booking_timestamp,

                "allocation_date":
                    allocation_date,

                "promised_delivery_date":
                    promised_delivery_date,

                "dispatch_at":
                    dispatch_at,

                # --------------------------------------------
                # IMPORTANT NEW FIELD
                # --------------------------------------------

                "physical_ready_date":
                    physical_ready_date,

                "projected_delivery_date":
                    projected_delivery_date,

                "actual_delivery_date":
                    actual_delivery_date,

                # --------------------------------------------
                # DISPATCH / TRANSIT
                # --------------------------------------------

                "dispatch_delay_hours":
                    round(
                        dispatch_delay_hours,
                        3,
                    ),

                "base_transit_days":
                    round(
                        base_transit_days,
                        3,
                    ),

                "transport_disruption":
                    transport_disruption,

                "disruption_days":
                    round(
                        disruption_days,
                        3,
                    ),

                "total_transit_days":
                    round(
                        total_transit_days,
                        3,
                    ),

                # --------------------------------------------
                # UPSTREAM EVIDENCE
                # --------------------------------------------

                "regional_demand_index":
                    round(
                        float(
                            allocation.
                            regional_demand_index
                        ),
                        6,
                    ),

                "allocation_priority":
                    allocation.
                    allocation_priority,

                "allocation_wait_hours":
                    round(
                        float(
                            allocation.
                            allocation_wait_hours
                        ),
                        3,
                    ),

                "demand_pressure":
                    demand_pressure,

                "quality_hold":
                    quality_hold,

                "normal_handover_delay":
                    normal_handover_delay,

                # --------------------------------------------
                # DELIVERY VARIANCE
                # --------------------------------------------

                "delivery_variance_days":
                    round(
                        delivery_variance_days,
                        3,
                    ),

                "delay_days":
                    round(
                        delay_days,
                        3,
                    ),

                "early_days":
                    round(
                        early_days,
                        3,
                    ),

                "delayed":
                    delayed,

                "delay_reason":
                    delay_reason,

                # --------------------------------------------
                # CUSTOMER HANDOVER
                # --------------------------------------------

                "customer_handover_completed":
                    customer_handover_completed,

                "handover_score":
                    handover_score,

                "delivery_status":
                    delivery_status,

                # --------------------------------------------
                # PROVENANCE
                # --------------------------------------------

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

        delivery_counter += 1

    # ========================================================
    # DATAFRAME
    # ========================================================

    deliveries = pd.DataFrame(
        rows,
        columns=[
            "delivery_id",

            "allocation_id",
            "booking_id",
            "lead_id",
            "customer_id",

            "vehicle_id",
            "vehicle_model_id",
            "vehicle_model_name",
            "variant",

            "dealer_id",
            "dealer_name",

            "region_id",
            "region_name",

            "city_id",
            "city_name",

            "production_batch_id",

            "plant_id",
            "plant_name",

            "production_line_id",
            "production_line_name",

            "representative_machine_id",
            "representative_machine_name",

            "primary_supplier_id",
            "primary_supplier_name",
            "primary_supplier_lot_id",

            "supplier_lot_quality_score",
            "production_quality_score",

            "booking_timestamp",
            "allocation_date",

            "promised_delivery_date",

            "dispatch_at",

            "physical_ready_date",

            "projected_delivery_date",
            "actual_delivery_date",

            "dispatch_delay_hours",

            "base_transit_days",

            "transport_disruption",
            "disruption_days",

            "total_transit_days",

            "regional_demand_index",

            "allocation_priority",
            "allocation_wait_hours",

            "demand_pressure",
            "quality_hold",

            "normal_handover_delay",

            "delivery_variance_days",

            "delay_days",
            "early_days",

            "delayed",
            "delay_reason",

            "customer_handover_completed",
            "handover_score",

            "delivery_status",

            "data_origin",
            "generator_version",
        ],
    )

    validate_deliveries(
        deliveries=
            deliveries,

        allocations=
            allocated,

        bookings=
            bookings,

        generation_end=
            generation_end,
    )

    return deliveries


# ============================================================
# VALIDATION
# ============================================================


def validate_deliveries(
    deliveries: pd.DataFrame,

    allocations: pd.DataFrame,

    bookings: pd.DataFrame,

    generation_end: pd.Timestamp,
) -> None:
    """
    Validate generated delivery records.
    """

    required_columns = {
        "delivery_id",

        "allocation_id",
        "booking_id",
        "customer_id",

        "vehicle_id",
        "vehicle_model_id",

        "production_batch_id",

        "dealer_id",

        "booking_timestamp",
        "allocation_date",

        "promised_delivery_date",

        "dispatch_at",

        "physical_ready_date",

        "projected_delivery_date",
        "actual_delivery_date",

        "delivery_variance_days",

        "delay_days",
        "early_days",

        "delayed",
        "delay_reason",

        "customer_handover_completed",

        "delivery_status",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        .difference(
            deliveries.columns
        )
    )

    if missing:

        raise ValueError(
            "Deliveries DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if deliveries.empty:

        raise ValueError(
            "No delivery records generated"
        )

    # ========================================================
    # UNIQUE IDS
    # ========================================================

    if deliveries[
        "delivery_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate delivery_id values found"
        )

    if deliveries[
        "allocation_id"
    ].duplicated().any():

        raise ValueError(
            "An allocation has multiple "
            "delivery records"
        )

    if deliveries[
        "vehicle_id"
    ].duplicated().any():

        raise ValueError(
            "A vehicle has multiple "
            "delivery records"
        )

    # ========================================================
    # EXACT ALLOCATION COVERAGE
    # ========================================================

    expected_allocation_ids = set(
        allocations[
            "allocation_id"
        ]
        .astype(str)
    )

    actual_allocation_ids = set(
        deliveries[
            "allocation_id"
        ]
        .astype(str)
    )

    if (
        expected_allocation_ids
        !=
        actual_allocation_ids
    ):

        missing_allocations = (
            expected_allocation_ids
            -
            actual_allocation_ids
        )

        extra_allocations = (
            actual_allocation_ids
            -
            expected_allocation_ids
        )

        raise ValueError(
            "Delivery coverage mismatch. "
            f"Missing={len(missing_allocations)}, "
            f"Extra={len(extra_allocations)}"
        )

    # ========================================================
    # STATUS
    # ========================================================

    invalid_statuses = (
        set(
            deliveries[
                "delivery_status"
            ]
        )
        -
        VALID_DELIVERY_STATUSES
    )

    if invalid_statuses:

        raise ValueError(
            "Invalid delivery statuses: "
            + ", ".join(
                sorted(
                    invalid_statuses
                )
            )
        )

    # ========================================================
    # DELAY REASONS
    # ========================================================

    invalid_reasons = (
        set(
            deliveries[
                "delay_reason"
            ]
        )
        -
        VALID_DELAY_REASONS
    )

    if invalid_reasons:

        raise ValueError(
            "Invalid delivery delay reasons: "
            + ", ".join(
                sorted(
                    invalid_reasons
                )
            )
        )

    # ========================================================
    # DELAY METRICS
    # ========================================================

    delay_days = pd.to_numeric(
        deliveries[
            "delay_days"
        ],
        errors="raise",
    )

    early_days = pd.to_numeric(
        deliveries[
            "early_days"
        ],
        errors="raise",
    )

    if (
        delay_days
        <
        0
    ).any():

        raise ValueError(
            "delay_days cannot be negative"
        )

    if (
        early_days
        <
        0
    ).any():

        raise ValueError(
            "early_days cannot be negative"
        )

    # Cannot be both early and late.
    if (
        (
            delay_days > 0
        )
        &
        (
            early_days > 0
        )
    ).any():

        raise ValueError(
            "A delivery cannot be both "
            "early and delayed"
        )

    # ========================================================
    # DELAY BOOLEAN CONSISTENCY
    # ========================================================

    expected_delayed = (
        delay_days
        >
        0
    )

    actual_delayed = (
        deliveries[
            "delayed"
        ]
        .astype(bool)
    )

    if not (
        expected_delayed
        ==
        actual_delayed
    ).all():

        raise ValueError(
            "delayed flag does not "
            "match delay_days"
        )

    # ========================================================
    # NO DELAY -> NONE
    # ========================================================

    non_delayed = (
        ~actual_delayed
    )

    if not (
        deliveries.loc[
            non_delayed,
            "delay_reason",
        ]
        ==
        "NONE"
    ).all():

        raise ValueError(
            "Non-delayed deliveries must "
            "have delay_reason=NONE"
        )

    # ========================================================
    # DELIVERED
    # ========================================================

    delivered = (
        deliveries[
            "delivery_status"
        ]
        ==
        "DELIVERED"
    )

    if (
        deliveries.loc[
            delivered,
            "actual_delivery_date",
        ]
        .isna()
        .any()
    ):

        raise ValueError(
            "DELIVERED rows require "
            "actual_delivery_date"
        )

    if not (
        deliveries.loc[
            delivered,
            "customer_handover_completed",
        ]
        .astype(bool)
    ).all():

        raise ValueError(
            "Delivered vehicles must have "
            "customer_handover_completed=True"
        )

    if (
        deliveries.loc[
            delivered,
            "handover_score",
        ]
        .isna()
        .any()
    ):

        raise ValueError(
            "Delivered vehicles must "
            "have handover_score"
        )

    # ========================================================
    # HANDOVER SCORE RANGE
    # ========================================================

    handover_scores = pd.to_numeric(
        deliveries.loc[
            delivered,
            "handover_score",
        ],
        errors="raise",
    )

    if (
        (
            handover_scores < 1.0
        )
        |
        (
            handover_scores > 5.0
        )
    ).any():

        raise ValueError(
            "handover_score must be "
            "between 1 and 5"
        )

    # ========================================================
    # IN TRANSIT
    # ========================================================

    in_transit = (
        deliveries[
            "delivery_status"
        ]
        ==
        "IN_TRANSIT"
    )

    if (
        deliveries.loc[
            in_transit,
            "actual_delivery_date",
        ]
        .notna()
        .any()
    ):

        raise ValueError(
            "IN_TRANSIT rows cannot "
            "have actual_delivery_date"
        )

    if (
        deliveries.loc[
            in_transit,
            "customer_handover_completed",
        ]
        .astype(bool)
        .any()
    ):

        raise ValueError(
            "IN_TRANSIT vehicles cannot "
            "have completed customer handover"
        )

    # ========================================================
    # LOOKUPS
    # ========================================================

    allocation_lookup = {
        str(
            row.allocation_id
        ):
            row

        for row
        in allocations.itertuples(
            index=False
        )
    }

    booking_lookup = {
        str(
            row.booking_id
        ):
            row

        for row
        in bookings.itertuples(
            index=False
        )
    }

    # ========================================================
    # ROW CONSISTENCY
    # ========================================================

    for delivery in deliveries.itertuples(
        index=False
    ):

        allocation = (
            allocation_lookup[
                str(
                    delivery.allocation_id
                )
            ]
        )

        booking = (
            booking_lookup[
                str(
                    delivery.booking_id
                )
            ]
        )

        # ----------------------------------------------------
        # IDS
        # ----------------------------------------------------

        if (
            str(
                delivery.booking_id
            )
            !=
            str(
                allocation.booking_id
            )
        ):

            raise ValueError(
                f"{delivery.delivery_id}: "
                "booking mismatch"
            )

        if (
            str(
                delivery.customer_id
            )
            !=
            str(
                allocation.customer_id
            )
        ):

            raise ValueError(
                f"{delivery.delivery_id}: "
                "customer mismatch"
            )

        if (
            str(
                delivery.vehicle_id
            )
            !=
            str(
                allocation.vehicle_id
            )
        ):

            raise ValueError(
                f"{delivery.delivery_id}: "
                "vehicle mismatch"
            )

        if (
            str(
                delivery.production_batch_id
            )
            !=
            str(
                allocation.production_batch_id
            )
        ):

            raise ValueError(
                f"{delivery.delivery_id}: "
                "production batch mismatch"
            )

        # ====================================================
        # TIMES
        # ====================================================

        booking_time = pd.Timestamp(
            delivery.booking_timestamp
        )

        allocation_date = pd.Timestamp(
            delivery.allocation_date
        )

        promised_date = pd.Timestamp(
            delivery.promised_delivery_date
        )

        dispatch_at = pd.Timestamp(
            delivery.dispatch_at
        )

        physical_ready_date = pd.Timestamp(
            delivery.physical_ready_date
        )

        projected_date = pd.Timestamp(
            delivery.projected_delivery_date
        )

        # ----------------------------------------------------
        # BOOKING -> ALLOCATION
        # ----------------------------------------------------

        if allocation_date < booking_time:

            raise ValueError(
                f"{delivery.delivery_id}: "
                "allocation occurs before booking"
            )

        # ----------------------------------------------------
        # ALLOCATION -> DISPATCH
        # ----------------------------------------------------

        if dispatch_at < allocation_date:

            raise ValueError(
                f"{delivery.delivery_id}: "
                "dispatch occurs before allocation"
            )

        # ----------------------------------------------------
        # DISPATCH -> PHYSICAL READY
        # ----------------------------------------------------

        if physical_ready_date < dispatch_at:

            raise ValueError(
                f"{delivery.delivery_id}: "
                "physical_ready_date occurs "
                "before dispatch"
            )

        # ----------------------------------------------------
        # PHYSICAL READY -> CUSTOMER HANDOVER
        # ----------------------------------------------------

        if projected_date < physical_ready_date:

            raise ValueError(
                f"{delivery.delivery_id}: "
                "customer delivery occurs before "
                "vehicle is physically ready"
            )

        # ----------------------------------------------------
        # PROMISED DATE MUST MATCH BOOKING
        # ----------------------------------------------------

        if (
            promised_date
            !=
            pd.Timestamp(
                booking.promised_delivery_date
            )
        ):

            raise ValueError(
                f"{delivery.delivery_id}: "
                "promised delivery date mismatch"
            )

        # ====================================================
        # DELIVERY VARIANCE CONSISTENCY
        # ====================================================

        expected_variance = (
            (
                projected_date
                -
                promised_date
            ).total_seconds()
            /
            86400.0
        )

        if not np.isclose(
            float(
                delivery.
                delivery_variance_days
            ),
            expected_variance,
            atol=0.01,
        ):

            raise ValueError(
                f"{delivery.delivery_id}: "
                "delivery_variance_days "
                "is inconsistent"
            )

        # ====================================================
        # DELIVERED
        # ====================================================

        if (
            delivery.delivery_status
            ==
            "DELIVERED"
        ):

            actual_date = pd.Timestamp(
                delivery.actual_delivery_date
            )

            if actual_date < physical_ready_date:

                raise ValueError(
                    f"{delivery.delivery_id}: "
                    "actual delivery occurs "
                    "before physical readiness"
                )

            if actual_date > generation_end:

                raise ValueError(
                    f"{delivery.delivery_id}: "
                    "actual delivery exceeds "
                    "generation end"
                )

            if actual_date != projected_date:

                raise ValueError(
                    f"{delivery.delivery_id}: "
                    "actual/projected delivery "
                    "date mismatch"
                )


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_delivery_master(
    bookings: pd.DataFrame,

    allocations: pd.DataFrame,

    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Public entry point later used by generate_all.py.
    """

    return generate_deliveries(
        bookings=bookings,
        allocations=allocations,
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

    from data.generators.auto.allocations import (
        generate_allocation_master,
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
    # MANUFACTURING
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
    # DELIVERY
    # ========================================================

    deliveries_df = (
        generate_delivery_master(
            bookings=
                bookings_df,

            allocations=
                allocations_df,
        )
    )

    # ========================================================
    # SAMPLE
    # ========================================================

    print(
        "\n=== DELIVERY SAMPLE ===\n"
    )

    display_columns = [
        "delivery_id",

        "booking_id",
        "vehicle_id",

        "dealer_name",
        "region_name",

        "vehicle_model_name",

        "plant_name",

        "promised_delivery_date",

        "physical_ready_date",

        "actual_delivery_date",

        "delay_days",
        "early_days",

        "delay_reason",

        "handover_score",

        "delivery_status",
    ]

    print(
        deliveries_df[
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
    # DELIVERY STATUS
    # ========================================================

    print(
        "\n=== DELIVERY STATUS ===\n"
    )

    print(
        deliveries_df
        .groupby(
            "delivery_status"
        )
        .size()
        .reset_index(
            name="delivery_count"
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # DELAY REASONS
    # ========================================================

    delayed_df = (
        deliveries_df[
            deliveries_df[
                "delayed"
            ]
        ]
    )

    print(
        "\n=== DELIVERY DELAY REASONS ===\n"
    )

    if delayed_df.empty:

        print(
            "No delayed deliveries."
        )

    else:

        print(
            delayed_df
            .groupby(
                "delay_reason"
            )
            .size()
            .reset_index(
                name="delivery_count"
            )
            .sort_values(
                "delivery_count",
                ascending=False,
            )
            .to_string(
                index=False
            )
        )

    # ========================================================
    # KPI CHECK
    # ========================================================

    allocated_count = int(
        (
            allocations_df[
                "allocation_status"
            ]
            ==
            "ALLOCATED"
        )
        .sum()
    )

    delivered_count = int(
        (
            deliveries_df[
                "delivery_status"
            ]
            ==
            "DELIVERED"
        )
        .sum()
    )

    in_transit_count = int(
        (
            deliveries_df[
                "delivery_status"
            ]
            ==
            "IN_TRANSIT"
        )
        .sum()
    )

    delayed_count = int(
        deliveries_df[
            "delayed"
        ].sum()
    )

    early_count = int(
        (
            deliveries_df[
                "early_days"
            ]
            >
            0
        )
        .sum()
    )

    print(
        "\n=== DELIVERY KPI CHECK ===\n"
    )

    print(
        "Allocated vehicles:",
        allocated_count,
    )

    print(
        "Delivery records:",
        len(
            deliveries_df
        ),
    )

    print(
        "Delivered:",
        delivered_count,
    )

    print(
        "In transit:",
        in_transit_count,
    )

    print(
        "Delayed deliveries:",
        delayed_count,
    )

    print(
        "Early deliveries:",
        early_count,
    )

    print(
        "Delayed delivery rate:",
        round(
            deliveries_df[
                "delayed"
            ].mean(),
            4,
        ),
    )

    delivered_only = (
        deliveries_df[
            deliveries_df[
                "delivery_status"
            ]
            ==
            "DELIVERED"
        ]
    )

    if not delivered_only.empty:

        delayed_delivered = (
            delivered_only[
                delivered_only[
                    "delayed"
                ]
            ]
        )

        early_delivered = (
            delivered_only[
                delivered_only[
                    "early_days"
                ]
                >
                0
            ]
        )

        if not delayed_delivered.empty:

            print(
                "Average delay days "
                "(delayed only):",
                round(
                    delayed_delivered[
                        "delay_days"
                    ].mean(),
                    3,
                ),
            )

        if not early_delivered.empty:

            print(
                "Average early days "
                "(early only):",
                round(
                    early_delivered[
                        "early_days"
                    ].mean(),
                    3,
                ),
            )

        print(
            "Average handover score:",
            round(
                delivered_only[
                    "handover_score"
                ].mean(),
                3,
            ),
        )

    print(
        "\nGenerated "
        f"{len(deliveries_df)} "
        "synthetic delivery records from "
        f"{allocated_count} allocated vehicles "
        "successfully."
    )