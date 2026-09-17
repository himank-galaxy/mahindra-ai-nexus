"""
Synthetic Booking generator for Mahindra AI Nexus.

Dependency chain:

    Customers
        ↓
    Leads
        ↓
    Follow-ups
        ↓
    Test Drives
        ↓
    Bookings

The generator creates actual booking events from the evidence already
generated in the customer journey.

This module DOES NOT write CSV files.

Later generate_all.py will save:

    data/synthetic/auto/bookings.csv

All values are synthetic.
"""

from __future__ import annotations

import math
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
# SYNTHETIC PROCESS ASSUMPTIONS
# ============================================================

# A finance preapproval here means a synthetic pre-booking
# eligibility signal.
#
# It is NOT the final finance decision.
#
# Formal finance applications are generated later in:
#
#     finance_applications.py

FINANCE_PREAPPROVAL_BUDGET_FIT_THRESHOLD = 0.60

MIN_BOOKING_DELAY_HOURS = 1.0
MAX_BOOKING_DELAY_HOURS = 72.0

MIN_PROMISED_DELIVERY_DAYS = 14
MAX_PROMISED_DELIVERY_DAYS = 60


# ============================================================
# BASIC HELPERS
# ============================================================


def _validate_probability(
    value: Any,
    name: str,
) -> float:
    """
    Validate a probability in [0, 1].
    """

    try:
        result = float(value)

    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"{name} must be numeric"
        ) from exc

    if not 0.0 <= result <= 1.0:
        raise ValueError(
            f"{name} must be between 0 and 1"
        )

    return result


def _logit(
    probability: float,
) -> float:
    """
    Convert probability to log-odds.
    """

    p = float(
        np.clip(
            probability,
            1e-8,
            1.0 - 1e-8,
        )
    )

    return math.log(
        p / (1.0 - p)
    )


def _sigmoid(
    value: float,
) -> float:
    """
    Convert log-odds back to probability.
    """

    return (
        1.0
        /
        (
            1.0
            + math.exp(
                -value
            )
        )
    )


# ============================================================
# GENERATION END TIME
# ============================================================


def _get_generation_end(
    generation: Mapping[str, Any],
) -> pd.Timestamp:
    """
    Load synthetic generation end time.
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
            "Missing end/end_date in generation time configuration"
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
    customers: pd.DataFrame,
    leads: pd.DataFrame,
    followups: pd.DataFrame,
    test_drives: pd.DataFrame,
    vehicle_models: pd.DataFrame,
) -> None:
    """
    Validate all upstream datasets required by bookings.py.
    """

    customer_required = {
        "customer_id",
        "finance_required",
        "exchange_vehicle",
    }

    lead_required = {
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

        "source_channel",

        "budget_fit",
        "latent_purchase_intent",

        "lead_created_at",
    }

    followup_required = {
        "followup_id",
        "lead_id",

        "completed",
        "within_sla",
        "customer_responded",

        "scheduled_at",
        "completed_at",
        "response_at",
    }

    test_drive_required = {
        "test_drive_id",
        "lead_id",

        "completed",
        "long_wait",

        "requested_at",
        "scheduled_at",
        "completed_at",
    }

    vehicle_required = {
        "vehicle_model_id",
        "model_name",

        "base_price",
        "production_complexity",
    }

    datasets = [
        (
            "customers",
            customers,
            customer_required,
        ),
        (
            "leads",
            leads,
            lead_required,
        ),
        (
            "followups",
            followups,
            followup_required,
        ),
        (
            "test_drives",
            test_drives,
            test_drive_required,
        ),
        (
            "vehicle_models",
            vehicle_models,
            vehicle_required,
        ),
    ]

    for (
        name,
        dataframe,
        required,
    ) in datasets:

        missing = (
            required
            .difference(
                dataframe.columns
            )
        )

        if missing:

            raise ValueError(
                f"{name} DataFrame is missing required columns: "
                + ", ".join(
                    sorted(
                        missing
                    )
                )
            )

    if customers.empty:
        raise ValueError(
            "Customers DataFrame cannot be empty"
        )

    if leads.empty:
        raise ValueError(
            "Leads DataFrame cannot be empty"
        )

    if followups.empty:
        raise ValueError(
            "Followups DataFrame cannot be empty"
        )

    if vehicle_models.empty:
        raise ValueError(
            "Vehicle-model DataFrame cannot be empty"
        )

    if customers[
        "customer_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate customer_id values found"
        )

    if leads[
        "lead_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate lead_id values found"
        )

    if followups[
        "followup_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate followup_id values found"
        )

    if (
        not test_drives.empty
        and test_drives[
            "test_drive_id"
        ].duplicated().any()
    ):

        raise ValueError(
            "Duplicate test_drive_id values found"
        )

    if (
        not test_drives.empty
        and test_drives[
            "lead_id"
        ].duplicated().any()
    ):

        raise ValueError(
            "More than one test-drive record found for a lead"
        )


# ============================================================
# FOLLOW-UP EVIDENCE
# ============================================================


def _build_followup_summary(
    followups: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convert multiple follow-up attempts into one evidence row
    for each lead.
    """

    work = followups.copy()

    for column in (
        "scheduled_at",
        "completed_at",
        "response_at",
    ):

        work[
            column
        ] = pd.to_datetime(
            work[
                column
            ]
        )

    work[
        "latest_activity"
    ] = (
        work[
            "response_at"
        ]
        .combine_first(
            work[
                "completed_at"
            ]
        )
        .combine_first(
            work[
                "scheduled_at"
            ]
        )
    )

    summary = (
        work
        .groupby(
            "lead_id",
            as_index=False,
        )
        .agg(
            followup_attempt_count=(
                "followup_id",
                "count",
            ),

            completed_followup_count=(
                "completed",
                "sum",
            ),

            within_sla_followup_count=(
                "within_sla",
                "sum",
            ),

            responded_followup_count=(
                "customer_responded",
                "sum",
            ),

            latest_followup_activity=(
                "latest_activity",
                "max",
            ),
        )
    )

    # --------------------------------------------------------
    # A "good follow-up" means:
    #
    # at least one dealer follow-up was completed
    # AND
    # at least one follow-up happened within SLA.
    # --------------------------------------------------------

    summary[
        "good_followup"
    ] = (
        (
            summary[
                "completed_followup_count"
            ]
            > 0
        )
        &
        (
            summary[
                "within_sla_followup_count"
            ]
            > 0
        )
    )

    return summary


# ============================================================
# BOOKING PROBABILITY
# ============================================================


def _calculate_booking_probability(
    base_probability: float,
    effects: Mapping[str, float],
    latent_intent: float,
    completed_test_drive: bool,
    good_followup: bool,
    finance_preapproval: bool,
    exchange_offer: bool,
    long_wait: bool,
) -> float:
    """
    Calculate booking probability using log-odds adjustments.

    Config values are interpreted as effect coefficients.

    This avoids raw additive probability inflation.
    """

    score = _logit(
        base_probability
    )

    score += (
        effects[
            "latent_intent"
        ]
        *
        latent_intent
    )

    score += (
        effects[
            "completed_test_drive"
        ]
        *
        int(
            completed_test_drive
        )
    )

    score += (
        effects[
            "good_followup"
        ]
        *
        int(
            good_followup
        )
    )

    score += (
        effects[
            "finance_preapproval"
        ]
        *
        int(
            finance_preapproval
        )
    )

    score += (
        effects[
            "exchange_offer"
        ]
        *
        int(
            exchange_offer
        )
    )

    score += (
        effects[
            "long_wait_penalty"
        ]
        *
        int(
            long_wait
        )
    )

    return float(
        np.clip(
            _sigmoid(
                score
            ),
            0.01,
            0.95,
        )
    )


# ============================================================
# BOOKING TIMESTAMP
# ============================================================


def _generate_booking_time(
    rng: np.random.Generator,
    anchor_time: pd.Timestamp,
    generation_end: pd.Timestamp,
) -> pd.Timestamp | None:
    """
    Generate booking time after the latest relevant journey event.

    Returns None when no future time is available.
    """

    anchor_time = pd.Timestamp(
        anchor_time
    )

    if anchor_time >= generation_end:
        return None

    available_hours = (
        generation_end
        - anchor_time
    ).total_seconds() / 3600.0

    if available_hours <= 0:
        return None

    max_delay = min(
        MAX_BOOKING_DELAY_HOURS,
        available_hours,
    )

    min_delay = min(
        MIN_BOOKING_DELAY_HOURS,
        max_delay,
    )

    delay_hours = float(
        rng.uniform(
            min_delay,
            max_delay,
        )
    )

    return (
        anchor_time
        + timedelta(
            hours=delay_hours
        )
    )


# ============================================================
# PROMISED DELIVERY DATE
# ============================================================


def _generate_promised_delivery_date(
    rng: np.random.Generator,
    booking_timestamp: pd.Timestamp,
    production_complexity: float,
) -> pd.Timestamp:
    """
    Create a synthetic customer promise date.

    More complex models receive somewhat longer expected
    delivery windows.

    Actual delivery is generated later in deliveries.py.
    """

    complexity = float(
        np.clip(
            production_complexity,
            0.0,
            1.0,
        )
    )

    base_days = (
        18
        + (
            24
            * complexity
        )
    )

    variation = float(
        rng.normal(
            0.0,
            4.0,
        )
    )

    delivery_days = int(
        round(
            base_days
            + variation
        )
    )

    delivery_days = int(
        np.clip(
            delivery_days,
            MIN_PROMISED_DELIVERY_DAYS,
            MAX_PROMISED_DELIVERY_DAYS,
        )
    )

    return (
        booking_timestamp
        + timedelta(
            days=delivery_days
        )
    )


# ============================================================
# GENERATOR
# ============================================================


def generate_bookings(
    customers: pd.DataFrame,
    leads: pd.DataFrame,
    followups: pd.DataFrame,
    test_drives: pd.DataFrame,
    vehicle_models: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate synthetic bookings.

    Only leads that actually convert create booking records.
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
    # INPUT VALIDATION
    # ========================================================

    _validate_inputs(
        customers=customers,
        leads=leads,
        followups=followups,
        test_drives=test_drives,
        vehicle_models=vehicle_models,
    )

    # ========================================================
    # EXACT BOOKING CONFIG
    # ========================================================

    booking_config = (
        distributions.get(
            "bookings"
        )
    )

    if not isinstance(
        booking_config,
        Mapping,
    ):

        raise KeyError(
            "Missing distributions.bookings configuration"
        )

    required_keys = {
        "booking_probability_base",
        "effects",
        "booking_amount",
    }

    missing = (
        required_keys
        .difference(
            booking_config.keys()
        )
    )

    if missing:

        raise KeyError(
            "distributions.bookings is missing: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    base_probability = (
        _validate_probability(
            booking_config[
                "booking_probability_base"
            ],
            (
                "bookings."
                "booking_probability_base"
            ),
        )
    )

    raw_effects = (
        booking_config[
            "effects"
        ]
    )

    if not isinstance(
        raw_effects,
        Mapping,
    ):

        raise TypeError(
            "bookings.effects must be a mapping"
        )

    required_effects = {
        "latent_intent",
        "completed_test_drive",
        "good_followup",
        "finance_preapproval",
        "exchange_offer",
        "long_wait_penalty",
    }

    missing_effects = (
        required_effects
        .difference(
            raw_effects.keys()
        )
    )

    if missing_effects:

        raise KeyError(
            "bookings.effects is missing: "
            + ", ".join(
                sorted(
                    missing_effects
                )
            )
        )

    effects = {
        key: float(
            raw_effects[
                key
            ]
        )
        for key in required_effects
    }

    booking_amount_spec = (
        booking_config[
            "booking_amount"
        ]
    )

    if not isinstance(
        booking_amount_spec,
        Mapping,
    ):

        raise TypeError(
            "bookings.booking_amount must "
            "be a distribution mapping"
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
            "auto.bookings",
        )
    )

    generation_end = (
        _get_generation_end(
            generation
        )
    )

    # ========================================================
    # LOOKUPS
    # ========================================================

    customer_lookup = {
        row.customer_id: row
        for row
        in customers.itertuples(
            index=False
        )
    }

    vehicle_lookup = {
        row.vehicle_model_id: row
        for row
        in vehicle_models.itertuples(
            index=False
        )
    }

    # --------------------------------------------------------
    # Follow-up summary
    # --------------------------------------------------------

    followup_summary = (
        _build_followup_summary(
            followups
        )
    )

    followup_lookup = {
        row.lead_id: row
        for row
        in followup_summary.itertuples(
            index=False
        )
    }

    # --------------------------------------------------------
    # Test-drive lookup
    #
    # Leads without a test-drive request simply do not appear.
    # --------------------------------------------------------

    test_drive_lookup = {
        row.lead_id: row
        for row
        in test_drives.itertuples(
            index=False
        )
    }

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
    # GENERATE BOOKINGS
    # ========================================================

    rows: list[
        dict[str, Any]
    ] = []

    booking_counter = 1

    for lead in leads.itertuples(
        index=False
    ):

        # ----------------------------------------------------
        # Customer
        # ----------------------------------------------------

        customer = customer_lookup.get(
            lead.customer_id
        )

        if customer is None:

            raise ValueError(
                f"Lead {lead.lead_id} references "
                f"unknown customer {lead.customer_id}"
            )

        # ----------------------------------------------------
        # Follow-up evidence
        # ----------------------------------------------------

        followup = followup_lookup.get(
            lead.lead_id
        )

        if followup is None:

            raise ValueError(
                f"No follow-up evidence for "
                f"lead {lead.lead_id}"
            )

        good_followup = bool(
            followup.good_followup
        )

        # ----------------------------------------------------
        # Test-drive evidence
        # ----------------------------------------------------

        test_drive = test_drive_lookup.get(
            lead.lead_id
        )

        completed_test_drive = False
        long_wait = False
        test_drive_id = None

        if test_drive is not None:

            test_drive_id = (
                test_drive.
                test_drive_id
            )

            completed_test_drive = bool(
                test_drive.completed
            )

            long_wait = bool(
                test_drive.long_wait
            )

        # ----------------------------------------------------
        # Finance preapproval signal
        #
        # This is only a PRE-BOOKING synthetic eligibility
        # signal.
        #
        # The actual finance application is generated later.
        # ----------------------------------------------------

        finance_required = bool(
            customer.finance_required
        )

        finance_preapproval = bool(
            finance_required
            and
            float(
                lead.budget_fit
            )
            >=
            FINANCE_PREAPPROVAL_BUDGET_FIT_THRESHOLD
        )

        # ----------------------------------------------------
        # Exchange offer
        #
        # Customer declared an existing vehicle for exchange.
        # ----------------------------------------------------

        exchange_offer = bool(
            customer.exchange_vehicle
        )

        latent_intent = float(
            lead.latent_purchase_intent
        )

        # ====================================================
        # BOOKING PROBABILITY
        # ====================================================

        booking_probability = (
            _calculate_booking_probability(
                base_probability=
                    base_probability,

                effects=
                    effects,

                latent_intent=
                    latent_intent,

                completed_test_drive=
                    completed_test_drive,

                good_followup=
                    good_followup,

                finance_preapproval=
                    finance_preapproval,

                exchange_offer=
                    exchange_offer,

                long_wait=
                    long_wait,
            )
        )

        converted = bool(
            float(
                rng.random()
            )
            <
            booking_probability
        )

        if not converted:
            continue

        # ====================================================
        # JOURNEY ANCHOR TIME
        # ====================================================

        journey_times = [
            pd.Timestamp(
                lead.lead_created_at
            ),

            pd.Timestamp(
                followup.
                latest_followup_activity
            ),
        ]

        if test_drive is not None:

            if (
                test_drive.completed_at
                is not None
                and not pd.isna(
                    test_drive.completed_at
                )
            ):

                journey_times.append(
                    pd.Timestamp(
                        test_drive.completed_at
                    )
                )

            elif (
                test_drive.scheduled_at
                is not None
                and not pd.isna(
                    test_drive.scheduled_at
                )
            ):

                journey_times.append(
                    pd.Timestamp(
                        test_drive.scheduled_at
                    )
                )

        anchor_time = max(
            journey_times
        )

        booking_timestamp = (
            _generate_booking_time(
                rng=rng,
                anchor_time=anchor_time,
                generation_end=
                    generation_end,
            )
        )

        # No room left in synthetic clock.
        if booking_timestamp is None:
            continue

        # ====================================================
        # BOOKING AMOUNT
        # ====================================================

        booking_amount = float(
            sample_distribution(
                booking_amount_spec,
                rng=rng,
            )
        )

        amount_min = float(
            booking_amount_spec.get(
                "min",
                0,
            )
        )

        amount_max = float(
            booking_amount_spec.get(
                "max",
                booking_amount,
            )
        )

        booking_amount = float(
            np.clip(
                booking_amount,
                amount_min,
                amount_max,
            )
        )

        booking_amount = int(
            round(
                booking_amount
            )
        )

        # ====================================================
        # VEHICLE MASTER
        # ====================================================

        vehicle = vehicle_lookup.get(
            lead.vehicle_model_id
        )

        if vehicle is None:

            raise ValueError(
                f"Lead {lead.lead_id} references "
                "unknown vehicle model "
                f"{lead.vehicle_model_id}"
            )

        promised_delivery_date = (
            _generate_promised_delivery_date(
                rng=rng,

                booking_timestamp=
                    booking_timestamp,

                production_complexity=
                    float(
                        vehicle.
                        production_complexity
                    ),
            )
        )

        # ====================================================
        # RECORD
        # ====================================================

        rows.append(
            {
                "booking_id":
                    make_entity_id(
                        "booking",
                        booking_counter,
                        width=6,
                    ),

                # --------------------------------------------
                # Journey
                # --------------------------------------------

                "lead_id":
                    lead.lead_id,

                "customer_id":
                    lead.customer_id,

                "test_drive_id":
                    test_drive_id,

                # --------------------------------------------
                # Dealer
                # --------------------------------------------

                "dealer_id":
                    lead.dealer_id,

                "dealer_name":
                    lead.dealer_name,

                # --------------------------------------------
                # Geography
                # --------------------------------------------

                "region_id":
                    lead.region_id,

                "region_name":
                    lead.region_name,

                "city_id":
                    lead.city_id,

                "city_name":
                    lead.city_name,

                # --------------------------------------------
                # Vehicle
                # --------------------------------------------

                "vehicle_model_id":
                    lead.vehicle_model_id,

                "vehicle_model_name":
                    lead.vehicle_model_name,

                "vehicle_base_price_inr":
                    int(
                        vehicle.base_price
                    ),

                # --------------------------------------------
                # Lead source
                # --------------------------------------------

                "source_channel":
                    lead.source_channel,

                # --------------------------------------------
                # Booking evidence
                # --------------------------------------------

                "latent_purchase_intent":
                    round(
                        latent_intent,
                        6,
                    ),

                "completed_test_drive":
                    completed_test_drive,

                "good_followup":
                    good_followup,

                "finance_assisted":
                    finance_required,

                "finance_preapproval_signal":
                    finance_preapproval,

                "exchange_assisted":
                    exchange_offer,

                "long_test_drive_wait":
                    long_wait,

                "booking_probability":
                    round(
                        booking_probability,
                        6,
                    ),

                # --------------------------------------------
                # Commercial
                # --------------------------------------------

                "booking_amount_inr":
                    booking_amount,

                # --------------------------------------------
                # Time
                # --------------------------------------------

                "booking_timestamp":
                    booking_timestamp,

                "promised_delivery_date":
                    promised_delivery_date,

                # --------------------------------------------
                # Status
                #
                # Cancellation is generated later in
                # cancellations.py.
                # --------------------------------------------

                "booking_status":
                    "ACTIVE",

                # --------------------------------------------
                # Provenance
                # --------------------------------------------

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

        booking_counter += 1

    # ========================================================
    # DATAFRAME
    # ========================================================

    bookings = pd.DataFrame(
        rows,
        columns=[
            "booking_id",

            "lead_id",
            "customer_id",
            "test_drive_id",

            "dealer_id",
            "dealer_name",

            "region_id",
            "region_name",

            "city_id",
            "city_name",

            "vehicle_model_id",
            "vehicle_model_name",
            "vehicle_base_price_inr",

            "source_channel",

            "latent_purchase_intent",

            "completed_test_drive",
            "good_followup",

            "finance_assisted",
            "finance_preapproval_signal",

            "exchange_assisted",
            "long_test_drive_wait",

            "booking_probability",

            "booking_amount_inr",

            "booking_timestamp",
            "promised_delivery_date",

            "booking_status",

            "data_origin",
            "generator_version",
        ],
    )

    validate_bookings(
        bookings=bookings,
        leads=leads,
        customers=customers,
        test_drives=test_drives,
        vehicle_models=vehicle_models,
        booking_amount_spec=
            booking_amount_spec,
        generation_end=
            generation_end,
    )

    return bookings


# ============================================================
# VALIDATION
# ============================================================


def validate_bookings(
    bookings: pd.DataFrame,
    leads: pd.DataFrame,
    customers: pd.DataFrame,
    test_drives: pd.DataFrame,
    vehicle_models: pd.DataFrame,
    booking_amount_spec: Mapping[str, Any],
    generation_end: pd.Timestamp,
) -> None:
    """
    Validate generated booking events.
    """

    required_columns = {
        "booking_id",

        "lead_id",
        "customer_id",
        "test_drive_id",

        "dealer_id",
        "dealer_name",

        "region_id",
        "region_name",

        "city_id",
        "city_name",

        "vehicle_model_id",
        "vehicle_model_name",
        "vehicle_base_price_inr",

        "source_channel",

        "latent_purchase_intent",

        "completed_test_drive",
        "good_followup",

        "finance_assisted",
        "finance_preapproval_signal",

        "exchange_assisted",
        "long_test_drive_wait",

        "booking_probability",

        "booking_amount_inr",

        "booking_timestamp",
        "promised_delivery_date",

        "booking_status",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        .difference(
            bookings.columns
        )
    )

    if missing:

        raise ValueError(
            "Bookings DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if bookings.empty:

        raise ValueError(
            "No bookings were generated"
        )

    # ========================================================
    # UNIQUE IDs
    # ========================================================

    if bookings[
        "booking_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate booking_id values found"
        )

    # One booking event per lead in this generation model.
    if bookings[
        "lead_id"
    ].duplicated().any():

        raise ValueError(
            "A lead has more than one booking"
        )

    # ========================================================
    # FOREIGN KEYS
    # ========================================================

    valid_lead_ids = set(
        leads[
            "lead_id"
        ]
    )

    invalid_leads = (
        set(
            bookings[
                "lead_id"
            ]
        )
        .difference(
            valid_lead_ids
        )
    )

    if invalid_leads:

        raise ValueError(
            "Bookings reference invalid lead IDs"
        )

    valid_customer_ids = set(
        customers[
            "customer_id"
        ]
    )

    invalid_customers = (
        set(
            bookings[
                "customer_id"
            ]
        )
        .difference(
            valid_customer_ids
        )
    )

    if invalid_customers:

        raise ValueError(
            "Bookings reference invalid customer IDs"
        )

    valid_model_ids = set(
        vehicle_models[
            "vehicle_model_id"
        ]
    )

    invalid_models = (
        set(
            bookings[
                "vehicle_model_id"
            ]
        )
        .difference(
            valid_model_ids
        )
    )

    if invalid_models:

        raise ValueError(
            "Bookings reference invalid vehicle models"
        )

    # ========================================================
    # OPTIONAL TEST-DRIVE FK
    # ========================================================

    valid_test_drive_ids = set(
        test_drives[
            "test_drive_id"
        ]
    )

    booking_test_drive_ids = set(
        bookings.loc[
            bookings[
                "test_drive_id"
            ].notna(),
            "test_drive_id",
        ]
    )

    invalid_test_drives = (
        booking_test_drive_ids
        .difference(
            valid_test_drive_ids
        )
    )

    if invalid_test_drives:

        raise ValueError(
            "Bookings reference invalid test-drive IDs"
        )

    # ========================================================
    # PROBABILITY
    # ========================================================

    probabilities = pd.to_numeric(
        bookings[
            "booking_probability"
        ],
        errors="raise",
    )

    if (
        (
            probabilities < 0
        )
        |
        (
            probabilities > 1
        )
    ).any():

        raise ValueError(
            "booking_probability must "
            "be between 0 and 1"
        )

    # ========================================================
    # BOOKING AMOUNT
    # ========================================================

    amounts = pd.to_numeric(
        bookings[
            "booking_amount_inr"
        ],
        errors="raise",
    )

    minimum_amount = float(
        booking_amount_spec.get(
            "min",
            0,
        )
    )

    maximum_amount = float(
        booking_amount_spec.get(
            "max",
            float("inf"),
        )
    )

    if (
        amounts
        < minimum_amount
    ).any():

        raise ValueError(
            "Booking amount below configured minimum"
        )

    if (
        amounts
        > maximum_amount
    ).any():

        raise ValueError(
            "Booking amount above configured maximum"
        )

    # ========================================================
    # STATUS
    # ========================================================

    if not (
        bookings[
            "booking_status"
        ]
        ==
        "ACTIVE"
    ).all():

        raise ValueError(
            "Newly generated bookings must "
            "start with ACTIVE status"
        )

    # ========================================================
    # TIME VALIDATION
    # ========================================================

    lead_time_lookup = dict(
        zip(
            leads[
                "lead_id"
            ],
            pd.to_datetime(
                leads[
                    "lead_created_at"
                ]
            ),
        )
    )

    for booking in bookings.itertuples(
        index=False
    ):

        booking_time = pd.Timestamp(
            booking.booking_timestamp
        )

        promised_date = pd.Timestamp(
            booking.promised_delivery_date
        )

        lead_time = (
            lead_time_lookup[
                booking.lead_id
            ]
        )

        if booking_time < lead_time:

            raise ValueError(
                f"{booking.booking_id}: "
                "booking occurs before lead creation"
            )

        if booking_time > generation_end:

            raise ValueError(
                f"{booking.booking_id}: "
                "booking occurs after generation end"
            )

        if promised_date <= booking_time:

            raise ValueError(
                f"{booking.booking_id}: "
                "promised delivery must occur "
                "after booking"
            )

    # ========================================================
    # LEAD -> BOOKING CONSISTENCY
    # ========================================================

    lead_lookup = {
        row.lead_id: row
        for row
        in leads.itertuples(
            index=False
        )
    }

    for booking in bookings.itertuples(
        index=False
    ):

        lead = (
            lead_lookup[
                booking.lead_id
            ]
        )

        if (
            booking.customer_id
            != lead.customer_id
        ):

            raise ValueError(
                f"customer_id mismatch for "
                f"{booking.booking_id}"
            )

        if (
            booking.dealer_id
            != lead.dealer_id
        ):

            raise ValueError(
                f"dealer_id mismatch for "
                f"{booking.booking_id}"
            )

        if (
            booking.region_id
            != lead.region_id
        ):

            raise ValueError(
                f"region_id mismatch for "
                f"{booking.booking_id}"
            )

        if (
            booking.city_id
            != lead.city_id
        ):

            raise ValueError(
                f"city_id mismatch for "
                f"{booking.booking_id}"
            )

        if (
            booking.vehicle_model_id
            != lead.vehicle_model_id
        ):

            raise ValueError(
                f"vehicle_model_id mismatch for "
                f"{booking.booking_id}"
            )

    # ========================================================
    # TEST-DRIVE CONSISTENCY
    # ========================================================

    if not test_drives.empty:

        test_drive_lookup = {
            row.test_drive_id: row
            for row
            in test_drives.itertuples(
                index=False
            )
        }

        for booking in bookings.itertuples(
            index=False
        ):

            if booking.test_drive_id is None:
                continue

            if pd.isna(
                booking.test_drive_id
            ):
                continue

            test_drive = (
                test_drive_lookup[
                    booking.test_drive_id
                ]
            )

            if (
                test_drive.lead_id
                != booking.lead_id
            ):

                raise ValueError(
                    f"Test-drive lead mismatch for "
                    f"{booking.booking_id}"
                )

            if (
                bool(
                    test_drive.completed
                )
                !=
                bool(
                    booking.
                    completed_test_drive
                )
            ):

                raise ValueError(
                    f"Test-drive completion mismatch "
                    f"for {booking.booking_id}"
                )


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_booking_master(
    customers: pd.DataFrame,
    leads: pd.DataFrame,
    followups: pd.DataFrame,
    test_drives: pd.DataFrame,
    vehicle_models: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Public entry point later used by generate_all.py.
    """

    return generate_bookings(
        customers=customers,
        leads=leads,
        followups=followups,
        test_drives=test_drives,
        vehicle_models=vehicle_models,
        generation=generation,
        distributions=distributions,
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

    # --------------------------------------------------------
    # MASTER
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # CUSTOMERS
    # --------------------------------------------------------

    customers_df = (
        generate_customer_master(
            regions=regions_df,
            cities=cities_df,
            vehicle_models=
                vehicle_models_df,
        )
    )

    # --------------------------------------------------------
    # LEADS
    # --------------------------------------------------------

    leads_df = (
        generate_lead_master(
            customers=customers_df,
            dealers=dealers_df,
            vehicle_models=
                vehicle_models_df,
        )
    )

    # --------------------------------------------------------
    # FOLLOW-UPS
    # --------------------------------------------------------

    followups_df = (
        generate_followup_master(
            leads=leads_df,
            dealers=dealers_df,
        )
    )

    # --------------------------------------------------------
    # TEST DRIVES
    # --------------------------------------------------------

    test_drives_df = (
        generate_test_drive_master(
            leads=leads_df,
            followups=followups_df,
        )
    )

    # --------------------------------------------------------
    # BOOKINGS
    # --------------------------------------------------------

    bookings_df = (
        generate_booking_master(
            customers=customers_df,
            leads=leads_df,
            followups=followups_df,
            test_drives=test_drives_df,
            vehicle_models=
                vehicle_models_df,
        )
    )

    print(
        "\n=== BOOKING SAMPLE ===\n"
    )

    display_columns = [
        "booking_id",
        "lead_id",
        "city_name",
        "vehicle_model_name",

        "completed_test_drive",
        "good_followup",

        "finance_preapproval_signal",
        "exchange_assisted",
        "long_test_drive_wait",

        "booking_probability",
        "booking_amount_inr",

        "booking_status",
    ]

    print(
        bookings_df[
            display_columns
        ]
        .head(25)
        .to_string(
            index=False
        )
    )

    print(
        "\n=== BOOKING KPI CHECK ===\n"
    )

    booking_rate = (
        len(
            bookings_df
        )
        /
        len(
            leads_df
        )
    )

    print(
        "Lead-to-booking rate:",
        round(
            booking_rate,
            4,
        ),
    )

    print(
        "Total bookings:",
        len(
            bookings_df
        ),
    )

    print(
        "Average booking amount:",
        round(
            bookings_df[
                "booking_amount_inr"
            ].mean(),
            2,
        ),
    )

    print(
        "Completed test-drive share:",
        round(
            bookings_df[
                "completed_test_drive"
            ].mean(),
            4,
        ),
    )

    print(
        "Good follow-up share:",
        round(
            bookings_df[
                "good_followup"
            ].mean(),
            4,
        ),
    )

    print(
        "Finance-assisted share:",
        round(
            bookings_df[
                "finance_assisted"
            ].mean(),
            4,
        ),
    )

    print(
        "Exchange-assisted share:",
        round(
            bookings_df[
                "exchange_assisted"
            ].mean(),
            4,
        ),
    )

    print(
        "\n=== BOOKINGS BY MODEL ===\n"
    )

    print(
        bookings_df
        .groupby(
            "vehicle_model_name"
        )
        .size()
        .reset_index(
            name="booking_count"
        )
        .sort_values(
            "booking_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== BOOKINGS BY REGION ===\n"
    )

    print(
        bookings_df
        .groupby(
            "region_name"
        )
        .size()
        .reset_index(
            name="booking_count"
        )
        .to_string(
            index=False
        )
    )

    print(
        "\nGenerated "
        f"{len(bookings_df)} "
        "synthetic bookings from "
        f"{len(leads_df)} leads "
        "successfully."
    )