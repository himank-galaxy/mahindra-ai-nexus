"""
Synthetic Test Drive generator for Mahindra AI Nexus.

Generates test-drive records from:
- leads
- dealer follow-up history
- distributions.yaml

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

This module DOES NOT write CSV files.

Later generate_all.py will save:

    data/synthetic/auto/test_drives.csv

All records are synthetic.
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
# SYNTHETIC PROCESS ASSUMPTIONS
#
# These are orchestration assumptions, not real Mahindra data.
# Core probabilities still come from distributions.yaml.
# ============================================================

HIGH_INTENT_THRESHOLD = 0.70

REMINDER_THRESHOLD_HOURS = 18.0

LONG_WAIT_THRESHOLD_HOURS = 48.0

MIN_SCHEDULING_DELAY_HOURS = 4.0

MAX_SCHEDULING_DELAY_HOURS = 96.0


# ============================================================
# BASIC HELPERS
# ============================================================


def _validate_probability(
    value: Any,
    name: str,
) -> float:
    """
    Validate numeric probability in [0, 1].
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
                f"{name}.{label} must be numeric"
            ) from exc

        if value < 0:
            raise ValueError(
                f"{name}.{label} cannot be negative"
            )

        parsed[
            str(label)
        ] = value

    total = sum(
        parsed.values()
    )

    if total <= 0:
        raise ValueError(
            f"{name} must sum to > 0"
        )

    return {
        key: value / total
        for key, value
        in parsed.items()
    }


# ============================================================
# GENERATION END TIME
# ============================================================


def _get_generation_end(
    generation: Mapping[str, Any],
) -> pd.Timestamp:
    """
    Read generation end timestamp.
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
    followups: pd.DataFrame,
) -> None:
    """
    Validate upstream lead and follow-up data.
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

    followup_required = {
        "followup_id",

        "lead_id",

        "scheduled_at",

        "completed",
        "completed_at",

        "within_sla",

        "customer_responded",
        "response_at",
    }

    missing_leads = (
        lead_required
        .difference(
            leads.columns
        )
    )

    if missing_leads:
        raise ValueError(
            "Leads DataFrame is missing "
            "columns required by test_drives.py: "
            + ", ".join(
                sorted(
                    missing_leads
                )
            )
        )

    missing_followups = (
        followup_required
        .difference(
            followups.columns
        )
    )

    if missing_followups:
        raise ValueError(
            "Followups DataFrame is missing "
            "columns required by test_drives.py: "
            + ", ".join(
                sorted(
                    missing_followups
                )
            )
        )

    if leads.empty:
        raise ValueError(
            "Leads DataFrame cannot be empty"
        )

    if followups.empty:
        raise ValueError(
            "Followups DataFrame cannot be empty"
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

    # --------------------------------------------------------
    # Every follow-up must reference a valid lead.
    # --------------------------------------------------------

    invalid_lead_ids = (
        set(
            followups[
                "lead_id"
            ]
        )
        .difference(
            set(
                leads[
                    "lead_id"
                ]
            )
        )
    )

    if invalid_lead_ids:
        raise ValueError(
            "Followups reference invalid lead IDs"
        )


# ============================================================
# FOLLOW-UP SUMMARY
# ============================================================


def _build_followup_summary(
    followups: pd.DataFrame,
) -> pd.DataFrame:
    """
    Reduce 1-N follow-up records into one evidence row per lead.

    Produces:

        followup_attempt_count
        completed_followup_count
        responded_followup_count
        within_sla_followup_count
        any_completed_followup
        any_customer_response
        any_within_sla
        latest_followup_activity_at
    """

    work = followups.copy()

    work[
        "scheduled_at"
    ] = pd.to_datetime(
        work[
            "scheduled_at"
        ]
    )

    work[
        "completed_at"
    ] = pd.to_datetime(
        work[
            "completed_at"
        ]
    )

    work[
        "response_at"
    ] = pd.to_datetime(
        work[
            "response_at"
        ]
    )

    # Most advanced event time on each follow-up.
    work[
        "followup_activity_at"
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

            responded_followup_count=(
                "customer_responded",
                "sum",
            ),

            within_sla_followup_count=(
                "within_sla",
                "sum",
            ),

            latest_followup_activity_at=(
                "followup_activity_at",
                "max",
            ),
        )
    )

    summary[
        "any_completed_followup"
    ] = (
        summary[
            "completed_followup_count"
        ]
        > 0
    )

    summary[
        "any_customer_response"
    ] = (
        summary[
            "responded_followup_count"
        ]
        > 0
    )

    summary[
        "any_within_sla"
    ] = (
        summary[
            "within_sla_followup_count"
        ]
        > 0
    )

    return summary


# ============================================================
# TEST-DRIVE REQUEST PROBABILITY
# ============================================================


def _calculate_request_probability(
    base_probability: float,
    latent_purchase_intent: float,
    any_completed_followup: bool,
    any_customer_response: bool,
) -> float:
    """
    Calculate test-drive request probability.

    The configured request_probability_base remains
    the main driver.

    Small evidence-based adjustments make the customer
    journey coherent:

    - high latent intent slightly increases propensity
    - customer response slightly increases propensity
    - no completed follow-up slightly decreases propensity

    These small adjustments are synthetic process logic.
    """

    intent = float(
        np.clip(
            latent_purchase_intent,
            0.0,
            1.0,
        )
    )

    probability = (
        base_probability
        +
        (
            0.08
            * (
                intent
                - 0.50
            )
        )
    )

    if any_customer_response:
        probability += 0.03

    if not any_completed_followup:
        probability -= 0.03

    return float(
        np.clip(
            probability,
            0.05,
            0.95,
        )
    )


# ============================================================
# REQUEST TIMESTAMP
# ============================================================


def _generate_request_time(
    rng: np.random.Generator,
    latest_activity_at: pd.Timestamp,
    generation_end: pd.Timestamp,
) -> pd.Timestamp:
    """
    Generate request timestamp after the latest follow-up activity.
    """

    latest_activity_at = pd.Timestamp(
        latest_activity_at
    )

    if latest_activity_at >= generation_end:
        return generation_end

    available_hours = (
        generation_end
        - latest_activity_at
    ).total_seconds() / 3600.0

    max_delay_hours = min(
        24.0,
        available_hours,
    )

    if max_delay_hours <= 0:
        return latest_activity_at

    min_delay_hours = min(
        0.5,
        max_delay_hours,
    )

    delay_hours = float(
        rng.uniform(
            min_delay_hours,
            max_delay_hours,
        )
    )

    return (
        latest_activity_at
        + timedelta(
            hours=delay_hours
        )
    )


# ============================================================
# SCHEDULING
# ============================================================


def _generate_scheduled_time(
    rng: np.random.Generator,
    requested_at: pd.Timestamp,
    generation_end: pd.Timestamp,
) -> pd.Timestamp:
    """
    Schedule test drive after request.
    """

    if requested_at >= generation_end:
        return generation_end

    available_hours = (
        generation_end
        - requested_at
    ).total_seconds() / 3600.0

    if available_hours <= 0:
        return requested_at

    max_delay = min(
        MAX_SCHEDULING_DELAY_HOURS,
        available_hours,
    )

    min_delay = min(
        MIN_SCHEDULING_DELAY_HOURS,
        max_delay,
    )

    delay_hours = float(
        rng.uniform(
            min_delay,
            max_delay,
        )
    )

    return (
        requested_at
        + timedelta(
            hours=delay_hours
        )
    )


# ============================================================
# COMPLETION PROBABILITY
# ============================================================


def _calculate_completion_probability(
    base_probability: float,
    reminder_sent: bool,
    high_intent: bool,
    long_wait: bool,
    reminder_boost: float,
    high_intent_boost: float,
    long_wait_penalty: float,
) -> float:
    """
    Calculate test-drive completion probability directly
    from the configured test-drive effects.
    """

    probability = base_probability

    if reminder_sent:
        probability += reminder_boost

    if high_intent:
        probability += high_intent_boost

    if long_wait:
        probability += long_wait_penalty

    return float(
        np.clip(
            probability,
            0.05,
            0.98,
        )
    )


# ============================================================
# GENERATOR
# ============================================================


def generate_test_drives(
    leads: pd.DataFrame,
    followups: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate synthetic test-drive records.

    Only leads that request a test drive create a row.

    Therefore:

        len(test_drives)

    represents actual requested test drives rather than
    all leads.
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
        followups=followups,
    )

    # ========================================================
    # EXACT TEST-DRIVE CONFIG
    # ========================================================

    test_drive_config = (
        distributions.get(
            "test_drives"
        )
    )

    if not isinstance(
        test_drive_config,
        Mapping,
    ):
        raise KeyError(
            "Missing distributions.test_drives "
            "configuration"
        )

    required_keys = {
        "request_probability_base",
        "completion_probability_base",
        "reminder_completion_boost",
        "high_intent_completion_boost",
        "long_wait_penalty",
        "status_weights",
        "feedback_score",
    }

    missing = (
        required_keys
        .difference(
            test_drive_config.keys()
        )
    )

    if missing:
        raise KeyError(
            "distributions.test_drives "
            "is missing required keys: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    request_probability_base = (
        _validate_probability(
            test_drive_config[
                "request_probability_base"
            ],
            (
                "test_drives."
                "request_probability_base"
            ),
        )
    )

    completion_probability_base = (
        _validate_probability(
            test_drive_config[
                "completion_probability_base"
            ],
            (
                "test_drives."
                "completion_probability_base"
            ),
        )
    )

    reminder_boost = float(
        test_drive_config[
            "reminder_completion_boost"
        ]
    )

    high_intent_boost = float(
        test_drive_config[
            "high_intent_completion_boost"
        ]
    )

    long_wait_penalty = float(
        test_drive_config[
            "long_wait_penalty"
        ]
    )

    status_weights = (
        _normalize_weights(
            test_drive_config[
                "status_weights"
            ],
            "test_drives.status_weights",
        )
    )

    feedback_spec = (
        test_drive_config[
            "feedback_score"
        ]
    )

    if not isinstance(
        feedback_spec,
        Mapping,
    ):
        raise TypeError(
            "test_drives.feedback_score "
            "must be a distribution mapping"
        )

    # ========================================================
    # STATUS CONFIG VALIDATION
    # ========================================================

    if (
        "COMPLETED"
        not in status_weights
    ):
        raise ValueError(
            "test_drives.status_weights "
            "must contain COMPLETED"
        )

    non_completed_weights = {
        status: weight
        for status, weight
        in status_weights.items()
        if status != "COMPLETED"
    }

    if not non_completed_weights:
        raise ValueError(
            "At least one non-COMPLETED "
            "test-drive status is required"
        )

    non_completed_weights = (
        _normalize_weights(
            non_completed_weights,
            "non-completed test-drive statuses",
        )
    )

    non_completed_statuses = list(
        non_completed_weights.keys()
    )

    non_completed_probabilities = (
        np.asarray(
            list(
                non_completed_weights.values()
            ),
            dtype=float,
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
            "auto.test_drives",
        )
    )

    # ========================================================
    # END TIME
    # ========================================================

    generation_end = (
        _get_generation_end(
            generation
        )
    )

    # ========================================================
    # FOLLOW-UP EVIDENCE
    # ========================================================

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
    # GENERATE
    # ========================================================

    rows: list[
        dict[str, Any]
    ] = []

    test_drive_counter = 1

    for lead in leads.itertuples(
        index=False
    ):

        followup = (
            followup_lookup.get(
                lead.lead_id
            )
        )

        if followup is None:
            raise ValueError(
                f"No follow-up evidence found "
                f"for lead {lead.lead_id}"
            )

        # ====================================================
        # REQUEST PROBABILITY
        # ====================================================

        request_probability = (
            _calculate_request_probability(
                base_probability=
                    request_probability_base,

                latent_purchase_intent=
                    float(
                        lead.
                        latent_purchase_intent
                    ),

                any_completed_followup=
                    bool(
                        followup.
                        any_completed_followup
                    ),

                any_customer_response=
                    bool(
                        followup.
                        any_customer_response
                    ),
            )
        )

        requested = bool(
            float(
                rng.random()
            )
            <
            request_probability
        )

        # No test-drive event is created.
        if not requested:
            continue

        # ====================================================
        # REQUEST TIME
        # ====================================================

        requested_at = (
            _generate_request_time(
                rng=rng,

                latest_activity_at=
                    pd.Timestamp(
                        followup.
                        latest_followup_activity_at
                    ),

                generation_end=
                    generation_end,
            )
        )

        # ====================================================
        # SCHEDULE TIME
        # ====================================================

        scheduled_at = (
            _generate_scheduled_time(
                rng=rng,

                requested_at=
                    requested_at,

                generation_end=
                    generation_end,
            )
        )

        wait_hours = max(
            0.0,
            (
                scheduled_at
                - requested_at
            ).total_seconds()
            / 3600.0,
        )

        # ====================================================
        # REMINDER
        #
        # Reminder requires:
        # - at least one completed dealer follow-up
        # - sufficiently long scheduling wait
        # ====================================================

        reminder_sent = bool(
            followup.
            any_completed_followup
            and
            wait_hours
            >= REMINDER_THRESHOLD_HOURS
        )

        # ====================================================
        # HIGH INTENT
        # ====================================================

        high_intent = bool(
            float(
                lead.
                latent_purchase_intent
            )
            >= HIGH_INTENT_THRESHOLD
        )

        # ====================================================
        # LONG WAIT
        # ====================================================

        long_wait = bool(
            wait_hours
            >= LONG_WAIT_THRESHOLD_HOURS
        )

        # ====================================================
        # COMPLETION PROBABILITY
        # ====================================================

        completion_probability = (
            _calculate_completion_probability(
                base_probability=
                    completion_probability_base,

                reminder_sent=
                    reminder_sent,

                high_intent=
                    high_intent,

                long_wait=
                    long_wait,

                reminder_boost=
                    reminder_boost,

                high_intent_boost=
                    high_intent_boost,

                long_wait_penalty=
                    long_wait_penalty,
            )
        )

        completed_at = None

        feedback_score = None

        rescheduled_for = None

        # ====================================================
        # If scheduled at generation boundary, it remains
        # pending rather than pretending completion happened.
        # ====================================================

        if scheduled_at >= generation_end:

            completed = False

            status = "SCHEDULED"

        else:

            completed = bool(
                float(
                    rng.random()
                )
                <
                completion_probability
            )

            if completed:

                status = "COMPLETED"

                duration_minutes = float(
                    rng.uniform(
                        20.0,
                        90.0,
                    )
                )

                completed_at = min(
                    (
                        scheduled_at
                        + timedelta(
                            minutes=
                                duration_minutes
                        )
                    ),
                    generation_end,
                )

                feedback_score = float(
                    sample_distribution(
                        feedback_spec,
                        rng=rng,
                    )
                )

                feedback_score = round(
                    feedback_score,
                    2,
                )

            else:

                status = str(
                    rng.choice(
                        non_completed_statuses,
                        p=
                            non_completed_probabilities,
                    )
                )

                # --------------------------------------------
                # Rescheduled test drive
                # --------------------------------------------

                if status == "RESCHEDULED":

                    available_hours = max(
                        0.0,
                        (
                            generation_end
                            - scheduled_at
                        ).total_seconds()
                        / 3600.0,
                    )

                    if available_hours > 0:

                        delay = float(
                            rng.uniform(
                                min(
                                    12.0,
                                    available_hours,
                                ),
                                min(
                                    72.0,
                                    available_hours,
                                ),
                            )
                        )

                        rescheduled_for = min(
                            (
                                scheduled_at
                                + timedelta(
                                    hours=delay
                                )
                            ),
                            generation_end,
                        )

        # ====================================================
        # RECORD
        # ====================================================

        rows.append(
            {
                "test_drive_id":
                    make_entity_id(
                        "test_drive",
                        test_drive_counter,
                        width=6,
                    ),

                # --------------------------------------------
                # Journey FKs
                # --------------------------------------------

                "lead_id":
                    lead.lead_id,

                "customer_id":
                    lead.customer_id,

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

                # --------------------------------------------
                # Lead evidence
                # --------------------------------------------

                "latent_purchase_intent":
                    float(
                        lead.
                        latent_purchase_intent
                    ),

                "request_probability":
                    round(
                        request_probability,
                        6,
                    ),

                # --------------------------------------------
                # Follow-up evidence
                # --------------------------------------------

                "followup_attempt_count":
                    int(
                        followup.
                        followup_attempt_count
                    ),

                "completed_followup_count":
                    int(
                        followup.
                        completed_followup_count
                    ),

                "responded_followup_count":
                    int(
                        followup.
                        responded_followup_count
                    ),

                "any_within_sla_followup":
                    bool(
                        followup.
                        any_within_sla
                    ),

                # --------------------------------------------
                # Test-drive journey
                # --------------------------------------------

                "requested_at":
                    requested_at,

                "scheduled_at":
                    scheduled_at,

                "wait_hours":
                    round(
                        wait_hours,
                        3,
                    ),

                "reminder_sent":
                    reminder_sent,

                "high_intent":
                    high_intent,

                "long_wait":
                    long_wait,

                "completion_probability":
                    round(
                        completion_probability,
                        6,
                    ),

                "status":
                    status,

                "completed":
                    completed,

                "completed_at":
                    completed_at,

                "feedback_score":
                    feedback_score,

                "rescheduled_for":
                    rescheduled_for,

                # --------------------------------------------
                # Provenance
                # --------------------------------------------

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

        test_drive_counter += 1

    # ========================================================
    # DATAFRAME
    # ========================================================

    test_drives = pd.DataFrame(
        rows,
        columns=[
            "test_drive_id",

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
            "request_probability",

            "followup_attempt_count",
            "completed_followup_count",
            "responded_followup_count",
            "any_within_sla_followup",

            "requested_at",
            "scheduled_at",
            "wait_hours",

            "reminder_sent",
            "high_intent",
            "long_wait",

            "completion_probability",

            "status",
            "completed",

            "completed_at",
            "feedback_score",

            "rescheduled_for",

            "data_origin",
            "generator_version",
        ],
    )

    validate_test_drives(
        test_drives=
            test_drives,

        leads=
            leads,

        generation_end=
            generation_end,
    )

    return test_drives


# ============================================================
# VALIDATION
# ============================================================


def validate_test_drives(
    test_drives: pd.DataFrame,
    leads: pd.DataFrame,
    generation_end: pd.Timestamp,
) -> None:
    """
    Validate test-drive records.
    """

    required_columns = {
        "test_drive_id",

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
        "request_probability",

        "followup_attempt_count",
        "completed_followup_count",
        "responded_followup_count",
        "any_within_sla_followup",

        "requested_at",
        "scheduled_at",
        "wait_hours",

        "reminder_sent",
        "high_intent",
        "long_wait",

        "completion_probability",

        "status",
        "completed",

        "completed_at",
        "feedback_score",

        "rescheduled_for",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        .difference(
            test_drives.columns
        )
    )

    if missing:
        raise ValueError(
            "Test-drives DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if test_drives.empty:
        raise ValueError(
            "No test-drive records were generated"
        )

    # ========================================================
    # IDS
    # ========================================================

    if test_drives[
        "test_drive_id"
    ].duplicated().any():
        raise ValueError(
            "Duplicate test_drive_id values found"
        )

    # One test-drive record per lead for this PoC model.
    if test_drives[
        "lead_id"
    ].duplicated().any():
        raise ValueError(
            "A lead has multiple test-drive records"
        )

    # ========================================================
    # LEAD FOREIGN KEY
    # ========================================================

    valid_leads = set(
        leads[
            "lead_id"
        ]
    )

    invalid_leads = (
        set(
            test_drives[
                "lead_id"
            ]
        )
        .difference(
            valid_leads
        )
    )

    if invalid_leads:
        raise ValueError(
            "Test drives reference invalid lead IDs"
        )

    # ========================================================
    # PROBABILITY RANGES
    # ========================================================

    for column in (
        "request_probability",
        "completion_probability",
        "latent_purchase_intent",
    ):

        values = pd.to_numeric(
            test_drives[
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
                f"{column} must be between 0 and 1"
            )

    # ========================================================
    # WAIT HOURS
    # ========================================================

    wait_hours = pd.to_numeric(
        test_drives[
            "wait_hours"
        ],
        errors="raise",
    )

    if (
        wait_hours < 0
    ).any():
        raise ValueError(
            "wait_hours cannot be negative"
        )

    # ========================================================
    # COMPLETION CONSISTENCY
    # ========================================================

    completed_rows = (
        test_drives[
            "completed"
        ].astype(bool)
    )

    if (
        test_drives.loc[
            completed_rows,
            "completed_at",
        ].isna().any()
    ):
        raise ValueError(
            "Completed test drives must "
            "have completed_at"
        )

    if (
        test_drives.loc[
            completed_rows,
            "feedback_score",
        ].isna().any()
    ):
        raise ValueError(
            "Completed test drives must "
            "have feedback_score"
        )

    if (
        test_drives.loc[
            completed_rows,
            "status",
        ]
        != "COMPLETED"
    ).any():
        raise ValueError(
            "Completed test drives must "
            "have status COMPLETED"
        )

    non_completed_rows = (
        ~completed_rows
    )

    if (
        test_drives.loc[
            non_completed_rows,
            "completed_at",
        ].notna().any()
    ):
        raise ValueError(
            "Non-completed test drives cannot "
            "have completed_at"
        )

    # ========================================================
    # FEEDBACK RANGE
    # ========================================================

    feedback = (
        test_drives.loc[
            completed_rows,
            "feedback_score",
        ]
    )

    feedback = pd.to_numeric(
        feedback,
        errors="raise",
    )

    if (
        (
            feedback < 1.0
        )
        |
        (
            feedback > 5.0
        )
    ).any():

        raise ValueError(
            "feedback_score must be "
            "between 1 and 5"
        )

    # ========================================================
    # LEAD TIME LOOKUP
    # ========================================================

    lead_lookup = {

        row.lead_id: row

        for row
        in leads.itertuples(
            index=False
        )
    }

    # ========================================================
    # TEMPORAL CONSISTENCY
    # ========================================================

    for row in test_drives.itertuples(
        index=False
    ):

        lead = (
            lead_lookup[
                row.lead_id
            ]
        )

        lead_created_at = pd.Timestamp(
            lead.lead_created_at
        )

        requested_at = pd.Timestamp(
            row.requested_at
        )

        scheduled_at = pd.Timestamp(
            row.scheduled_at
        )

        if requested_at < lead_created_at:
            raise ValueError(
                f"{row.test_drive_id}: "
                "request occurs before lead creation"
            )

        if scheduled_at < requested_at:
            raise ValueError(
                f"{row.test_drive_id}: "
                "scheduled_at occurs before requested_at"
            )

        if scheduled_at > generation_end:
            raise ValueError(
                f"{row.test_drive_id}: "
                "scheduled_at exceeds generation end"
            )

        if row.completed_at is not None:

            completed_at = pd.Timestamp(
                row.completed_at
            )

            if completed_at < scheduled_at:
                raise ValueError(
                    f"{row.test_drive_id}: "
                    "completed before scheduled time"
                )

            if completed_at > generation_end:
                raise ValueError(
                    f"{row.test_drive_id}: "
                    "completed_at exceeds generation end"
                )

        if row.rescheduled_for is not None:

            rescheduled_for = pd.Timestamp(
                row.rescheduled_for
            )

            if rescheduled_for < scheduled_at:
                raise ValueError(
                    f"{row.test_drive_id}: "
                    "rescheduled time occurs before "
                    "original schedule"
                )

    # ========================================================
    # JOURNEY ID CONSISTENCY
    # ========================================================

    for row in test_drives.itertuples(
        index=False
    ):

        lead = (
            lead_lookup[
                row.lead_id
            ]
        )

        if (
            row.customer_id
            != lead.customer_id
        ):
            raise ValueError(
                f"customer_id mismatch for "
                f"{row.test_drive_id}"
            )

        if (
            row.dealer_id
            != lead.dealer_id
        ):
            raise ValueError(
                f"dealer_id mismatch for "
                f"{row.test_drive_id}"
            )

        if (
            row.vehicle_model_id
            != lead.vehicle_model_id
        ):
            raise ValueError(
                f"vehicle_model_id mismatch for "
                f"{row.test_drive_id}"
            )

        if (
            row.city_id
            != lead.city_id
        ):
            raise ValueError(
                f"city_id mismatch for "
                f"{row.test_drive_id}"
            )

        if (
            row.region_id
            != lead.region_id
        ):
            raise ValueError(
                f"region_id mismatch for "
                f"{row.test_drive_id}"
            )


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_test_drive_master(
    leads: pd.DataFrame,
    followups: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Public entry point later used by generate_all.py.
    """

    return generate_test_drives(
        leads=leads,
        followups=followups,
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

    # --------------------------------------------------------
    # Master
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

    # --------------------------------------------------------
    # Test Drives
    # --------------------------------------------------------

    test_drives_df = (
        generate_test_drive_master(
            leads=leads_df,
            followups=followups_df,
        )
    )

    print(
        "\n=== TEST DRIVE SAMPLE ===\n"
    )

    display_columns = [
        "test_drive_id",
        "lead_id",
        "city_name",
        "vehicle_model_name",
        "request_probability",
        "wait_hours",
        "reminder_sent",
        "completion_probability",
        "status",
        "feedback_score",
    ]

    print(
        test_drives_df[
            display_columns
        ]
        .head(25)
        .to_string(
            index=False
        )
    )

    print(
        "\n=== TEST DRIVE STATUS ===\n"
    )

    print(
        test_drives_df
        .groupby(
            "status"
        )
        .size()
        .reset_index(
            name="test_drive_count"
        )
        .sort_values(
            "test_drive_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== TEST DRIVE KPI CHECK ===\n"
    )

    request_rate = (
        len(
            test_drives_df
        )
        /
        len(
            leads_df
        )
    )

    print(
        "Test-drive request rate:",
        round(
            request_rate,
            4,
        ),
    )

    completion_rate = (
        test_drives_df[
            "completed"
        ].mean()
    )

    print(
        "Test-drive completion rate:",
        round(
            completion_rate,
            4,
        ),
    )

    completed_df = (
        test_drives_df[
            test_drives_df[
                "completed"
            ]
        ]
    )

    if not completed_df.empty:

        print(
            "Average feedback score:",
            round(
                completed_df[
                    "feedback_score"
                ].mean(),
                3,
            ),
        )

    print(
        "Reminder rate:",
        round(
            test_drives_df[
                "reminder_sent"
            ].mean(),
            4,
        ),
    )

    print(
        "Long-wait rate:",
        round(
            test_drives_df[
                "long_wait"
            ].mean(),
            4,
        ),
    )

    print(
        "\nGenerated "
        f"{len(test_drives_df)} "
        "synthetic test-drive records "
        f"from {len(leads_df)} leads "
        "successfully."
    )