"""
Synthetic dealer follow-up generator for Mahindra AI Nexus.

Generates follow-up interaction records from synthetic Auto leads.

Dependencies:
    customers.py
        ↓
    leads.py
        ↓
    followups.py

Every follow-up is linked to:
- a valid lead
- a valid customer
- a valid dealer
- a valid city/region
- the lead's vehicle model

This module DOES NOT write CSV files.

Later:
    data/scripts/generate_all.py

will save:

    data/synthetic/auto/followups.csv

IMPORTANT:
The records are entirely synthetic and contain no real customer PII.
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
# BASIC HELPERS
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


def _validate_probability(
    value: Any,
    name: str,
) -> float:
    """
    Validate probability in [0, 1].
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


def _normalize_weights(
    weights: Mapping[str, Any],
    name: str,
) -> dict[str, float]:
    """
    Validate and normalize categorical weights.
    """

    if (
        not isinstance(weights, Mapping)
        or not weights
    ):
        raise ValueError(
            f"{name} must be a non-empty mapping"
        )

    parsed: dict[str, float] = {}

    for label, raw_value in weights.items():

        try:
            value = float(raw_value)

        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"Weight for {label!r} "
                f"in {name} must be numeric"
            ) from exc

        if value < 0:
            raise ValueError(
                f"Weight for {label!r} "
                f"in {name} cannot be negative"
            )

        parsed[
            str(label)
        ] = value

    total = sum(
        parsed.values()
    )

    if total <= 0:
        raise ValueError(
            f"Weights in {name} must sum to > 0"
        )

    return {
        label: value / total
        for label, value
        in parsed.items()
    }


# ============================================================
# FOLLOW-UP CONFIG
# ============================================================


def _get_max_followups_per_lead(
    generation: Mapping[str, Any],
) -> int:
    """
    Read maximum number of follow-ups per lead.

    Supports these config styles:

        auto:
          followups:
            max_per_lead: 5

    OR:

        auto:
          followups:
            max_followups_per_lead: 5

    OR:

        auto:
          followups:
            max: 5

    This compatibility is intentional because only the field
    naming may vary; the generator still reads generation.yaml.
    """

    try:
        followup_config = (
            generation[
                "auto"
            ][
                "followups"
            ]
        )

    except KeyError as exc:
        raise KeyError(
            "Missing generation.auto.followups "
            "configuration"
        ) from exc

    if isinstance(
        followup_config,
        Mapping,
    ):

        value = None

        for key in (
            "max_per_lead",
            "max_followups_per_lead",
            "max",
        ):

            if key in followup_config:

                value = (
                    followup_config[
                        key
                    ]
                )

                break

    else:
        value = followup_config

    if value is None:
        raise KeyError(
            "Unable to find maximum follow-ups "
            "per lead. Expected one of: "
            "generation.auto.followups.max_per_lead, "
            "max_followups_per_lead, or max."
        )

    return _as_positive_int(
        value,
        (
            "generation.auto."
            "followups.max_per_lead"
        ),
    )


# ============================================================
# GENERATION END TIME
# ============================================================


def _get_generation_end(
    generation: Mapping[str, Any],
) -> pd.Timestamp:
    """
    Read configured generation end timestamp.
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
            "Missing end/end_date in "
            "generation time configuration"
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
    leads: pd.DataFrame,
    dealers: pd.DataFrame,
) -> None:
    """
    Validate upstream datasets.
    """

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

        "latent_purchase_intent",

        "lead_created_at",
    }

    dealer_required = {
        "dealer_id",
        "dealer_name",

        "city_id",
        "region_id",

        "followup_sla_hours",

        "active",
    }

    missing_lead = (
        lead_required
        .difference(
            leads.columns
        )
    )

    if missing_lead:

        raise ValueError(
            "Leads DataFrame is missing columns "
            "required by followups.py: "
            + ", ".join(
                sorted(
                    missing_lead
                )
            )
        )

    missing_dealer = (
        dealer_required
        .difference(
            dealers.columns
        )
    )

    if missing_dealer:

        raise ValueError(
            "Dealers DataFrame is missing columns "
            "required by followups.py: "
            + ", ".join(
                sorted(
                    missing_dealer
                )
            )
        )

    if leads.empty:
        raise ValueError(
            "Leads DataFrame cannot be empty"
        )

    if dealers.empty:
        raise ValueError(
            "Dealers DataFrame cannot be empty"
        )

    if leads[
        "lead_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate lead_id values found"
        )

    if dealers[
        "dealer_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate dealer_id values found"
        )


# ============================================================
# NUMBER OF FOLLOW-UPS
# ============================================================


def _calculate_followup_count(
    rng: np.random.Generator,
    latent_purchase_intent: float,
    max_followups: int,
) -> int:
    """
    Determine how many follow-up attempts a lead receives.

    Every lead receives at least one attempt.

    Additional attempts are generated probabilistically.

    Logic:
        high-intent leads generally require fewer repeated attempts
        low/medium-intent leads may require more persistence

    This is process logic, not a final business outcome.
    """

    if max_followups <= 1:
        return 1

    intent = float(
        np.clip(
            latent_purchase_intent,
            0.0,
            1.0,
        )
    )

    count = 1

    # Lower intent -> somewhat higher chance of needing
    # another follow-up attempt.
    continuation_probability = (
        0.35
        + (
            0.35
            * (
                1.0
                - intent
            )
        )
    )

    while (
        count < max_followups
        and float(
            rng.random()
        )
        < continuation_probability
    ):

        count += 1

        # Each subsequent attempt is less likely.
        continuation_probability *= 0.72

    return count


# ============================================================
# FOLLOW-UP TIMING
# ============================================================


def _schedule_followup(
    rng: np.random.Generator,
    previous_time: pd.Timestamp,
    attempt_number: int,
    generation_end: pd.Timestamp,
) -> pd.Timestamp:
    """
    Schedule a follow-up after the previous journey event.

    Attempt 1:
        typically within several hours

    Later attempts:
        progressively later

    Timestamp cannot exceed generation end.
    """

    previous_time = pd.Timestamp(
        previous_time
    )

    if (
        previous_time.tzinfo is None
        and generation_end.tzinfo is not None
    ):

        previous_time = (
            previous_time.tz_localize(
                generation_end.tzinfo
            )
        )

    elif (
        previous_time.tzinfo is not None
        and generation_end.tzinfo is not None
    ):

        previous_time = (
            previous_time.tz_convert(
                generation_end.tzinfo
            )
        )

    if previous_time >= generation_end:
        return previous_time

    # --------------------------------------------------------
    # Minimum/maximum delay by attempt
    # --------------------------------------------------------

    if attempt_number == 1:

        min_hours = 1.0
        max_hours = 12.0

    elif attempt_number == 2:

        min_hours = 6.0
        max_hours = 24.0

    else:

        min_hours = 12.0
        max_hours = 48.0

    available_hours = (
        generation_end
        - previous_time
    ).total_seconds() / 3600.0

    if available_hours <= 0:
        return previous_time

    actual_max = min(
        max_hours,
        available_hours,
    )

    actual_min = min(
        min_hours,
        actual_max,
    )

    delay_hours = float(
        rng.uniform(
            actual_min,
            actual_max,
        )
    )

    return (
        previous_time
        + timedelta(
            hours=delay_hours
        )
    )


# ============================================================
# GENERATOR
# ============================================================


def generate_followups(
    leads: pd.DataFrame,
    dealers: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate dealer follow-up interaction records.

    Output includes:

        followup_id
        lead_id
        customer_id

        dealer_id

        attempt_number
        channel

        scheduled_at
        completed_at

        completed
        within_sla

        customer_responded
        response_time_minutes
        response_at

        followup_status
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
        leads=leads,
        dealers=dealers,
    )

    # ========================================================
    # CONFIG
    # ========================================================

    max_followups = (
        _get_max_followups_per_lead(
            generation
        )
    )

    followup_config = (
        distributions.get(
            "followups"
        )
    )

    if not isinstance(
        followup_config,
        Mapping,
    ):

        raise KeyError(
            "Missing distributions.followups "
            "configuration"
        )

    required_keys = {
        "channel_weights",
        "completion_probability",
        "customer_response_probability",
        "response_time_minutes",
    }

    missing = (
        required_keys
        .difference(
            followup_config.keys()
        )
    )

    if missing:

        raise KeyError(
            "distributions.followups is missing: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    # ========================================================
    # CHANNEL WEIGHTS
    # ========================================================

    channel_weights = (
        _normalize_weights(
            followup_config[
                "channel_weights"
            ],
            (
                "distributions.followups."
                "channel_weights"
            ),
        )
    )

    channel_names = list(
        channel_weights.keys()
    )

    channel_probabilities = (
        np.asarray(
            list(
                channel_weights.values()
            ),
            dtype=float,
        )
    )

    # ========================================================
    # PROBABILITIES
    # ========================================================

    completion_probability = (
        _validate_probability(
            followup_config[
                "completion_probability"
            ],
            (
                "followups."
                "completion_probability"
            ),
        )
    )

    response_probability = (
        _validate_probability(
            followup_config[
                "customer_response_probability"
            ],
            (
                "followups."
                "customer_response_probability"
            ),
        )
    )

    response_time_spec = (
        followup_config[
            "response_time_minutes"
        ]
    )

    if not isinstance(
        response_time_spec,
        Mapping,
    ):

        raise TypeError(
            "followups.response_time_minutes "
            "must be a distribution mapping"
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

    followup_seed = (
        derive_seed(
            base_seed,
            "auto.followups",
        )
    )

    rng = make_rng(
        followup_seed
    )

    # ========================================================
    # GENERATION END
    # ========================================================

    generation_end = (
        _get_generation_end(
            generation
        )
    )

    # ========================================================
    # DEALER LOOKUP
    # ========================================================

    dealer_lookup = {

        row.dealer_id: {
            "dealer_name":
                row.dealer_name,

            "city_id":
                row.city_id,

            "region_id":
                row.region_id,

            "followup_sla_hours":
                float(
                    row.followup_sla_hours
                ),

            "active":
                bool(
                    row.active
                ),
        }

        for row
        in dealers.itertuples(
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
    # GENERATE FOLLOW-UPS
    # ========================================================

    rows: list[
        dict[str, Any]
    ] = []

    followup_counter = 1

    for lead in leads.itertuples(
        index=False
    ):

        dealer = (
            dealer_lookup.get(
                lead.dealer_id
            )
        )

        if dealer is None:

            raise ValueError(
                f"Lead {lead.lead_id} references "
                f"unknown dealer {lead.dealer_id}"
            )

        if not dealer[
            "active"
        ]:

            raise ValueError(
                f"Lead {lead.lead_id} references "
                "an inactive dealer"
            )

        # ----------------------------------------------------
        # Number of follow-up attempts
        # ----------------------------------------------------

        followup_count = (
            _calculate_followup_count(
                rng=rng,

                latent_purchase_intent=
                    float(
                        lead.
                        latent_purchase_intent
                    ),

                max_followups=
                    max_followups,
            )
        )

        previous_event_time = (
            pd.Timestamp(
                lead.lead_created_at
            )
        )

        for attempt_number in range(
            1,
            followup_count + 1,
        ):

            # =================================================
            # CHANNEL
            # =================================================

            channel = str(
                rng.choice(
                    channel_names,
                    p=channel_probabilities,
                )
            )

            # =================================================
            # SCHEDULE
            # =================================================

            scheduled_at = (
                _schedule_followup(
                    rng=rng,

                    previous_time=
                        previous_event_time,

                    attempt_number=
                        attempt_number,

                    generation_end=
                        generation_end,
                )
            )

            # =================================================
            # COMPLETION
            # =================================================

            completed = bool(
                float(
                    rng.random()
                )
                <
                completion_probability
            )

            completed_at = None

            if completed:

                execution_delay_minutes = float(
                    rng.uniform(
                        5.0,
                        180.0,
                    )
                )

                candidate_completed_at = (
                    scheduled_at
                    + timedelta(
                        minutes=
                            execution_delay_minutes
                    )
                )

                completed_at = min(
                    candidate_completed_at,
                    generation_end,
                )

            # =================================================
            # SLA
            # =================================================

            sla_hours = float(
                dealer[
                    "followup_sla_hours"
                ]
            )

            lead_time = pd.Timestamp(
                lead.lead_created_at
            )

            if completed_at is not None:

                actual_followup_hours = (
                    completed_at
                    - lead_time
                ).total_seconds() / 3600.0

                within_sla = bool(
                    actual_followup_hours
                    <= sla_hours
                )

            else:

                within_sla = False

            # =================================================
            # CUSTOMER RESPONSE
            #
            # Customer can respond only if follow-up was
            # actually completed.
            # =================================================

            customer_responded = False

            response_time_minutes = None

            response_at = None

            if completed:

                customer_responded = bool(
                    float(
                        rng.random()
                    )
                    <
                    response_probability
                )

            if customer_responded:

                sampled_response_time = (
                    sample_distribution(
                        response_time_spec,
                        rng=rng,
                    )
                )

                response_time_minutes = int(
                    round(
                        float(
                            sampled_response_time
                        )
                    )
                )

                minimum = int(
                    response_time_spec.get(
                        "min",
                        5,
                    )
                )

                maximum = int(
                    response_time_spec.get(
                        "max",
                        1440,
                    )
                )

                response_time_minutes = int(
                    np.clip(
                        response_time_minutes,
                        minimum,
                        maximum,
                    )
                )

                response_at_candidate = (
                    completed_at
                    + timedelta(
                        minutes=
                            response_time_minutes
                    )
                )

                response_at = min(
                    response_at_candidate,
                    generation_end,
                )

            # =================================================
            # STATUS
            # =================================================

            if not completed:

                followup_status = (
                    "NOT_COMPLETED"
                )

            elif customer_responded:

                followup_status = (
                    "CUSTOMER_RESPONDED"
                )

            else:

                followup_status = (
                    "NO_RESPONSE"
                )

            # =================================================
            # RECORD
            # =================================================

            rows.append(
                {
                    "followup_id":
                        make_entity_id(
                            "followup",
                            followup_counter,
                            width=6,
                        ),

                    "lead_id":
                        lead.lead_id,

                    "customer_id":
                        lead.customer_id,

                    # -----------------------------------------
                    # Dealer
                    # -----------------------------------------

                    "dealer_id":
                        lead.dealer_id,

                    "dealer_name":
                        lead.dealer_name,

                    # -----------------------------------------
                    # Geography
                    # -----------------------------------------

                    "region_id":
                        lead.region_id,

                    "region_name":
                        lead.region_name,

                    "city_id":
                        lead.city_id,

                    "city_name":
                        lead.city_name,

                    # -----------------------------------------
                    # Vehicle
                    # -----------------------------------------

                    "vehicle_model_id":
                        lead.vehicle_model_id,

                    "vehicle_model_name":
                        lead.vehicle_model_name,

                    # -----------------------------------------
                    # Follow-up
                    # -----------------------------------------

                    "attempt_number":
                        attempt_number,

                    "channel":
                        channel,

                    "scheduled_at":
                        scheduled_at,

                    "completed":
                        completed,

                    "completed_at":
                        completed_at,

                    "dealer_sla_hours":
                        sla_hours,

                    "within_sla":
                        within_sla,

                    # -----------------------------------------
                    # Customer response
                    # -----------------------------------------

                    "customer_responded":
                        customer_responded,

                    "response_time_minutes":
                        response_time_minutes,

                    "response_at":
                        response_at,

                    "followup_status":
                        followup_status,

                    # -----------------------------------------
                    # Provenance
                    # -----------------------------------------

                    "data_origin":
                        data_origin,

                    "generator_version":
                        generator_version,
                }
            )

            followup_counter += 1

            # ------------------------------------------------
            # Next attempt starts after latest event
            # ------------------------------------------------

            if response_at is not None:

                previous_event_time = (
                    response_at
                )

            elif completed_at is not None:

                previous_event_time = (
                    completed_at
                )

            else:

                previous_event_time = (
                    scheduled_at
                )

    # ========================================================
    # DATAFRAME
    # ========================================================

    followups = pd.DataFrame(
        rows,
        columns=[
            "followup_id",

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

            "attempt_number",
            "channel",

            "scheduled_at",

            "completed",
            "completed_at",

            "dealer_sla_hours",
            "within_sla",

            "customer_responded",

            "response_time_minutes",
            "response_at",

            "followup_status",

            "data_origin",
            "generator_version",
        ],
    )

    validate_followups(
        followups=followups,
        leads=leads,
        dealers=dealers,
        max_followups=
            max_followups,
    )

    return followups


# ============================================================
# VALIDATION
# ============================================================


def validate_followups(
    followups: pd.DataFrame,
    leads: pd.DataFrame,
    dealers: pd.DataFrame,
    max_followups: int,
) -> None:
    """
    Validate generated follow-up records.
    """

    required_columns = {
        "followup_id",

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

        "attempt_number",
        "channel",

        "scheduled_at",

        "completed",
        "completed_at",

        "dealer_sla_hours",
        "within_sla",

        "customer_responded",

        "response_time_minutes",
        "response_at",

        "followup_status",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        .difference(
            followups.columns
        )
    )

    if missing:

        raise ValueError(
            "Followups DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if followups.empty:

        raise ValueError(
            "Followups DataFrame cannot be empty"
        )

    # ========================================================
    # UNIQUE FOLLOWUP IDS
    # ========================================================

    if followups[
        "followup_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate followup_id values found"
        )

    # ========================================================
    # FOREIGN KEYS
    # ========================================================

    valid_leads = set(
        leads[
            "lead_id"
        ]
    )

    invalid_leads = (
        set(
            followups[
                "lead_id"
            ]
        )
        .difference(
            valid_leads
        )
    )

    if invalid_leads:

        raise ValueError(
            "Followups reference invalid "
            "lead IDs"
        )

    valid_dealers = set(
        dealers[
            "dealer_id"
        ]
    )

    invalid_dealers = (
        set(
            followups[
                "dealer_id"
            ]
        )
        .difference(
            valid_dealers
        )
    )

    if invalid_dealers:

        raise ValueError(
            "Followups reference invalid "
            "dealer IDs"
        )

    # ========================================================
    # ATTEMPT NUMBER
    # ========================================================

    attempts = pd.to_numeric(
        followups[
            "attempt_number"
        ],
        errors="raise",
    )

    if (
        attempts < 1
    ).any():

        raise ValueError(
            "attempt_number must be >= 1"
        )

    if (
        attempts
        > max_followups
    ).any():

        raise ValueError(
            "attempt_number exceeds configured "
            "maximum follow-ups per lead"
        )

    # ========================================================
    # AT LEAST ONE FOLLOWUP PER LEAD
    # ========================================================

    followup_leads = set(
        followups[
            "lead_id"
        ]
    )

    missing_leads = (
        valid_leads
        - followup_leads
    )

    if missing_leads:

        raise ValueError(
            "Some leads have no follow-up records"
        )

    # ========================================================
    # MAX COUNT PER LEAD
    # ========================================================

    counts = (
        followups
        .groupby(
            "lead_id"
        )
        .size()
    )

    if (
        counts
        > max_followups
    ).any():

        raise ValueError(
            "A lead has more follow-ups "
            "than configured maximum"
        )

    # ========================================================
    # COMPLETION LOGIC
    # ========================================================

    invalid_completed = (
        followups[
            "completed"
        ]
        &
        followups[
            "completed_at"
        ].isna()
    )

    if invalid_completed.any():

        raise ValueError(
            "Completed follow-ups must have "
            "completed_at"
        )

    invalid_not_completed = (
        ~followups[
            "completed"
        ]
        &
        followups[
            "completed_at"
        ].notna()
    )

    if invalid_not_completed.any():

        raise ValueError(
            "Incomplete follow-ups cannot "
            "have completed_at"
        )

    # ========================================================
    # RESPONSE LOGIC
    # ========================================================

    invalid_response = (
        followups[
            "customer_responded"
        ]
        &
        ~followups[
            "completed"
        ]
    )

    if invalid_response.any():

        raise ValueError(
            "Customer cannot respond to "
            "an uncompleted follow-up"
        )

    responded = (
        followups[
            "customer_responded"
        ]
    )

    if (
        followups.loc[
            responded,
            "response_time_minutes",
        ].isna().any()
    ):

        raise ValueError(
            "Responded follow-ups must have "
            "response_time_minutes"
        )

    if (
        followups.loc[
            responded,
            "response_at",
        ].isna().any()
    ):

        raise ValueError(
            "Responded follow-ups must have "
            "response_at"
        )

    # ========================================================
    # TIME ORDERING
    # ========================================================

    lead_time_lookup = dict(
        zip(
            leads[
                "lead_id"
            ],
            pd.to_datetime(
                leads[
                    "lead_created_at"
                ],
            ),
        )
    )

    for row in followups.itertuples(
        index=False
    ):

        lead_created_at = (
            lead_time_lookup[
                row.lead_id
            ]
        )

        scheduled_at = pd.Timestamp(
            row.scheduled_at
        )

        if (
            scheduled_at
            < lead_created_at
        ):

            raise ValueError(
                f"Follow-up {row.followup_id} "
                "occurs before lead creation"
            )

        if row.completed_at is not None:

            completed_at = pd.Timestamp(
                row.completed_at
            )

            if (
                completed_at
                < scheduled_at
            ):

                raise ValueError(
                    f"Follow-up {row.followup_id} "
                    "completed before it was scheduled"
                )

        if row.response_at is not None:

            response_at = pd.Timestamp(
                row.response_at
            )

            completed_at = pd.Timestamp(
                row.completed_at
            )

            if (
                response_at
                < completed_at
            ):

                raise ValueError(
                    f"Follow-up {row.followup_id} "
                    "has response before completion"
                )

    # ========================================================
    # ATTEMPT ORDER PER LEAD
    # ========================================================

    grouped = (
        followups
        .sort_values(
            [
                "lead_id",
                "attempt_number",
            ]
        )
        .groupby(
            "lead_id"
        )
    )

    for (
        lead_id,
        group,
    ) in grouped:

        expected_attempts = list(
            range(
                1,
                len(group) + 1,
            )
        )

        actual_attempts = (
            group[
                "attempt_number"
            ]
            .astype(int)
            .tolist()
        )

        if (
            actual_attempts
            != expected_attempts
        ):

            raise ValueError(
                "Invalid follow-up attempt sequence "
                f"for lead {lead_id}"
            )


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_followup_master(
    leads: pd.DataFrame,
    dealers: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Public entry point later used by generate_all.py.
    """

    return generate_followups(
        leads=leads,
        dealers=dealers,
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

    # --------------------------------------------------------
    # Geography
    # --------------------------------------------------------

    (
        regions_df,
        cities_df,
    ) = generate_geography()

    # --------------------------------------------------------
    # Vehicle Models
    # --------------------------------------------------------

    vehicle_models_df = (
        generate_vehicle_models()
    )

    # --------------------------------------------------------
    # Dealers
    # --------------------------------------------------------

    dealers_df = (
        generate_dealer_master(
            regions=regions_df,
            cities=cities_df,
        )
    )

    # --------------------------------------------------------
    # Customers
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
    # Leads
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
    # Follow-ups
    # --------------------------------------------------------

    followups_df = (
        generate_followup_master(
            leads=leads_df,
            dealers=dealers_df,
        )
    )

    print(
        "\n=== FOLLOW-UP SAMPLE ===\n"
    )

    print(
        followups_df
        .head(25)
        .to_string(
            index=False
        )
    )

    print(
        "\n=== FOLLOW-UPS BY CHANNEL ===\n"
    )

    print(
        followups_df
        .groupby(
            "channel"
        )
        .size()
        .reset_index(
            name="followup_count"
        )
        .sort_values(
            "followup_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== FOLLOW-UP STATUS ===\n"
    )

    print(
        followups_df
        .groupby(
            "followup_status"
        )
        .size()
        .reset_index(
            name="followup_count"
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== FOLLOW-UP KPI CHECK ===\n"
    )

    print(
        "Completion rate:",
        round(
            followups_df[
                "completed"
            ].mean(),
            4,
        ),
    )

    completed_df = (
        followups_df[
            followups_df[
                "completed"
            ]
        ]
    )

    if not completed_df.empty:

        print(
            "Customer response rate "
            "among completed:",
            round(
                completed_df[
                    "customer_responded"
                ].mean(),
                4,
            ),
        )

    print(
        "Within SLA rate:",
        round(
            followups_df[
                "within_sla"
            ].mean(),
            4,
        ),
    )

    print(
        "Average attempts per lead:",
        round(
            len(
                followups_df
            )
            /
            len(
                leads_df
            ),
            3,
        ),
    )

    print(
        "\nGenerated "
        f"{len(followups_df)} "
        "synthetic follow-up records "
        f"for {len(leads_df)} leads "
        "successfully."
    )