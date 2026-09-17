"""
Synthetic AR / VR / XR Experience and Session Generator
for Mahindra AI Nexus.

============================================================
PURPOSE
============================================================

Generate operational XR reference data and session history for:

    AI Virtual Showroom
    3D Vehicle Configurator
    AR Technician Repair Guide
    VR Dealer Sales Training


============================================================
SYNTHETIC DATA FACTORY ALIGNMENT
============================================================

The Mahindra AI Nexus Synthetic Data Factory requires:

    xr_experiences
    xr_sessions

Operational session fields include:

    experience_id
    experience_type
    vehicle_model
    persona
    session_id
    started_at
    completed_at
    engagement_seconds
    configuration_selected
    assistant_interactions
    training_score
    repair_steps_completed
    conversion_or_completion_outcome

Business impact must later be DERIVED from session statistics.

Therefore this generator DOES NOT create:

    engagement uplift %
    training-cost reduction
    technician productivity uplift
    conversion probability
    recommended configuration
    AI confidence
    model score
    predicted outcome
    dashboard KPI values


============================================================
ACTUAL generation.yaml
============================================================

xr:

    experiences:
        - AI Virtual Showroom
        - 3D Vehicle Configurator
        - AR Technician Repair Guide
        - VR Dealer Sales Training

    sessions:
        count: 2000


============================================================
EXPERIENCE ALLOCATION
============================================================

No experience weights currently exist in configuration.

Therefore sessions are distributed as evenly as possible
across the configured experiences.

For the current configuration:

    2,000 sessions
    4 experiences

    = 500 sessions per experience


============================================================
ENGINEERING ASSUMPTIONS
============================================================

Session duration, persona distribution, assistant usage,
configuration-selection behavior, repair-step completion,
training scores and session outcomes are synthetic engineering
parameters.

They are NOT Mahindra operating statistics.


============================================================
OUTPUT
============================================================

This module returns DataFrames.

It DOES NOT write CSV files.

Public functions:

    generate_xr_experiences(...)
        -> xr_experiences DataFrame

    generate_xr_sessions(...)
        -> xr_sessions DataFrame

    generate_xr(...)
        -> (xr_experiences, xr_sessions)
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.helpers import (
    load_generation_config,
)

from data.generators.common.ids import (
    generate_id,
)

from data.generators.common.seed import (
    derive_seed,
    make_rng,
)


# ============================================================
# CONFIGURED EXPERIENCE NAMES
# ============================================================

AI_VIRTUAL_SHOWROOM = (
    "AI Virtual Showroom"
)

VEHICLE_CONFIGURATOR = (
    "3D Vehicle Configurator"
)

AR_TECHNICIAN_REPAIR_GUIDE = (
    "AR Technician Repair Guide"
)

VR_DEALER_SALES_TRAINING = (
    "VR Dealer Sales Training"
)


SUPPORTED_EXPERIENCES = {
    AI_VIRTUAL_SHOWROOM,
    VEHICLE_CONFIGURATOR,
    AR_TECHNICIAN_REPAIR_GUIDE,
    VR_DEALER_SALES_TRAINING,
}


# ============================================================
# EXPERIENCE CATEGORIES
# ============================================================

CUSTOMER_SALES_EXPERIENCE = (
    "CUSTOMER_SALES"
)

TECHNICIAN_SUPPORT_EXPERIENCE = (
    "TECHNICIAN_SUPPORT"
)

DEALER_TRAINING_EXPERIENCE = (
    "DEALER_TRAINING"
)


# ============================================================
# DEVICE MODES
#
# Generic synthetic categories.
# Not hardware-brand assumptions.
# ============================================================

IMMERSIVE_WEB = "IMMERSIVE_WEB"

INTERACTIVE_3D = "INTERACTIVE_3D"

AR_MOBILE_OR_HEADSET = (
    "AR_MOBILE_OR_HEADSET"
)

VR_HEADSET = "VR_HEADSET"


# ============================================================
# PERSONAS
# ============================================================

PROSPECT_CUSTOMER = (
    "PROSPECT_CUSTOMER"
)

EXISTING_OWNER = (
    "EXISTING_OWNER"
)

FAMILY_BUYER = (
    "FAMILY_BUYER"
)

ENTHUSIAST = (
    "ENTHUSIAST"
)

SERVICE_TECHNICIAN = (
    "SERVICE_TECHNICIAN"
)

SENIOR_TECHNICIAN = (
    "SENIOR_TECHNICIAN"
)

APPRENTICE_TECHNICIAN = (
    "APPRENTICE_TECHNICIAN"
)

SALES_CONSULTANT = (
    "SALES_CONSULTANT"
)

SALES_MANAGER = (
    "SALES_MANAGER"
)

NEW_JOINER = (
    "NEW_JOINER"
)


# ============================================================
# SYNTHETIC CONFIGURATION CODES
#
# These are deliberately generic.
#
# They are NOT actual Mahindra trim / variant names.
# ============================================================

CONFIGURATION_LEVELS = [
    "BASE",
    "PLUS",
    "PREMIUM",
]

CONFIGURATION_LEVEL_WEIGHTS = np.asarray(
    [
        0.25,
        0.45,
        0.30,
    ],
    dtype=float,
)


# ============================================================
# OUTCOMES
#
# These are observed operational session outcomes.
#
# They are NOT predictions.
# ============================================================

OUTCOME_ABANDONED = (
    "ABANDONED"
)

OUTCOME_EXPERIENCE_COMPLETED = (
    "EXPERIENCE_COMPLETED"
)

OUTCOME_TEST_DRIVE_INTENT = (
    "TEST_DRIVE_INTENT"
)

OUTCOME_BOOKING_INTENT = (
    "BOOKING_INTENT"
)

OUTCOME_CONFIGURATION_SAVED = (
    "CONFIGURATION_SAVED"
)

OUTCOME_REPAIR_COMPLETED = (
    "REPAIR_COMPLETED"
)

OUTCOME_REPAIR_PARTIAL = (
    "REPAIR_PARTIAL"
)

OUTCOME_TECHNICIAN_ESCALATED = (
    "ESCALATED_TO_SENIOR_TECHNICIAN"
)

OUTCOME_TRAINING_PASSED = (
    "TRAINING_PASSED"
)

OUTCOME_TRAINING_FAILED = (
    "TRAINING_FAILED"
)

OUTCOME_TRAINING_INCOMPLETE = (
    "TRAINING_INCOMPLETE"
)


VALID_OUTCOMES_BY_EXPERIENCE = {

    AI_VIRTUAL_SHOWROOM: {
        OUTCOME_ABANDONED,
        OUTCOME_EXPERIENCE_COMPLETED,
        OUTCOME_TEST_DRIVE_INTENT,
        OUTCOME_BOOKING_INTENT,
    },

    VEHICLE_CONFIGURATOR: {
        OUTCOME_ABANDONED,
        OUTCOME_EXPERIENCE_COMPLETED,
        OUTCOME_CONFIGURATION_SAVED,
        OUTCOME_TEST_DRIVE_INTENT,
        OUTCOME_BOOKING_INTENT,
    },

    AR_TECHNICIAN_REPAIR_GUIDE: {
        OUTCOME_REPAIR_COMPLETED,
        OUTCOME_REPAIR_PARTIAL,
        OUTCOME_TECHNICIAN_ESCALATED,
    },

    VR_DEALER_SALES_TRAINING: {
        OUTCOME_TRAINING_PASSED,
        OUTCOME_TRAINING_FAILED,
        OUTCOME_TRAINING_INCOMPLETE,
    },
}


# ============================================================
# EXPERIENCE ENGINEERING SPECIFICATION
#
# Synthetic assumptions only.
# ============================================================

EXPERIENCE_SPECS: dict[
    str,
    dict[str, Any],
] = {

    AI_VIRTUAL_SHOWROOM: {
        "experience_category":
            CUSTOMER_SALES_EXPERIENCE,

        "device_mode":
            IMMERSIVE_WEB,

        "primary_persona_group":
            "CUSTOMER",

        "supports_configuration":
            True,

        "supports_training_score":
            False,

        "supports_repair_steps":
            False,

        "supports_ai_assistant":
            True,

        "personas": [
            PROSPECT_CUSTOMER,
            EXISTING_OWNER,
            FAMILY_BUYER,
            ENTHUSIAST,
        ],

        "persona_weights": np.asarray(
            [
                0.55,
                0.18,
                0.17,
                0.10,
            ],
            dtype=float,
        ),

        "engagement_mean_seconds":
            720.0,

        "engagement_std_seconds":
            300.0,

        "engagement_min_seconds":
            120,

        "engagement_max_seconds":
            1800,

        "assistant_base_lambda":
            1.20,

        "assistant_per_10_minutes":
            1.15,
    },


    VEHICLE_CONFIGURATOR: {
        "experience_category":
            CUSTOMER_SALES_EXPERIENCE,

        "device_mode":
            INTERACTIVE_3D,

        "primary_persona_group":
            "CUSTOMER",

        "supports_configuration":
            True,

        "supports_training_score":
            False,

        "supports_repair_steps":
            False,

        "supports_ai_assistant":
            True,

        "personas": [
            PROSPECT_CUSTOMER,
            EXISTING_OWNER,
            FAMILY_BUYER,
            ENTHUSIAST,
        ],

        "persona_weights": np.asarray(
            [
                0.60,
                0.15,
                0.15,
                0.10,
            ],
            dtype=float,
        ),

        "engagement_mean_seconds":
            900.0,

        "engagement_std_seconds":
            380.0,

        "engagement_min_seconds":
            180,

        "engagement_max_seconds":
            2400,

        "assistant_base_lambda":
            1.40,

        "assistant_per_10_minutes":
            1.30,
    },


    AR_TECHNICIAN_REPAIR_GUIDE: {
        "experience_category":
            TECHNICIAN_SUPPORT_EXPERIENCE,

        "device_mode":
            AR_MOBILE_OR_HEADSET,

        "primary_persona_group":
            "TECHNICIAN",

        "supports_configuration":
            False,

        "supports_training_score":
            False,

        "supports_repair_steps":
            True,

        "supports_ai_assistant":
            True,

        "personas": [
            SERVICE_TECHNICIAN,
            SENIOR_TECHNICIAN,
            APPRENTICE_TECHNICIAN,
        ],

        "persona_weights": np.asarray(
            [
                0.58,
                0.20,
                0.22,
            ],
            dtype=float,
        ),

        "engagement_mean_seconds":
            1500.0,

        "engagement_std_seconds":
            650.0,

        "engagement_min_seconds":
            300,

        "engagement_max_seconds":
            3600,

        "assistant_base_lambda":
            2.00,

        "assistant_per_10_minutes":
            1.50,
    },


    VR_DEALER_SALES_TRAINING: {
        "experience_category":
            DEALER_TRAINING_EXPERIENCE,

        "device_mode":
            VR_HEADSET,

        "primary_persona_group":
            "DEALER_SALES",

        "supports_configuration":
            False,

        "supports_training_score":
            True,

        "supports_repair_steps":
            False,

        "supports_ai_assistant":
            True,

        "personas": [
            SALES_CONSULTANT,
            SALES_MANAGER,
            NEW_JOINER,
        ],

        "persona_weights": np.asarray(
            [
                0.58,
                0.15,
                0.27,
            ],
            dtype=float,
        ),

        "engagement_mean_seconds":
            2400.0,

        "engagement_std_seconds":
            800.0,

        "engagement_min_seconds":
            600,

        "engagement_max_seconds":
            5400,

        "assistant_base_lambda":
            1.00,

        "assistant_per_10_minutes":
            0.80,
    },
}


# ============================================================
# REQUIRED VEHICLE-MODEL SCHEMA
# ============================================================

VEHICLE_MODEL_REQUIRED_COLUMNS: set[str] = {
    "vehicle_model_id",
    "model_name",
    "segment",

    "production_complexity",
    "generation_weight",

    "data_origin",
    "generator_version",
}


# ============================================================
# FORBIDDEN RUNTIME / AI / DASHBOARD OUTPUTS
# ============================================================

HIDDEN_RUNTIME_COLUMNS = {
    "predicted_conversion",
    "predicted_conversion_probability",

    "conversion_probability",

    "predicted_configuration",
    "recommended_configuration",
    "recommended_variant",

    "recommended_next_action",

    "engagement_uplift",
    "engagement_uplift_pct",

    "training_cost_reduction",
    "training_cost_reduction_pct",

    "technician_productivity_uplift",
    "technician_productivity_uplift_pct",

    "sales_conversion_uplift",
    "sales_conversion_uplift_pct",

    "confidence",
    "confidence_score",

    "model_score",
    "model_probability",

    "risk_score",
    "risk_band",

    "true_conversion_probability",
    "true_training_effectiveness",

    "target_conversion",
    "target_outcome",
}


# ============================================================
# CONFIG HELPERS
# ============================================================


def _get_xr_experience_names(
    generation: Mapping[str, Any],
) -> list[str]:
    """
    Read configured XR experience names.
    """

    try:
        experiences = list(
            generation[
                "xr"
            ][
                "experiences"
            ]
        )

    except KeyError as exc:
        raise KeyError(
            "Missing generation.xr.experiences"
        ) from exc

    if not experiences:
        raise ValueError(
            "generation.xr.experiences cannot be empty"
        )

    experiences = [
        str(
            value
        )
        for value in experiences
    ]

    if (
        len(
            experiences
        )
        !=
        len(
            set(
                experiences
            )
        )
    ):
        raise ValueError(
            "generation.xr.experiences contains duplicates"
        )

    unsupported = (
        set(
            experiences
        )
        -
        SUPPORTED_EXPERIENCES
    )

    if unsupported:
        raise ValueError(
            "Unsupported configured XR experiences: "
            +
            ", ".join(
                sorted(
                    unsupported
                )
            )
        )

    missing_required = (
        SUPPORTED_EXPERIENCES
        -
        set(
            experiences
        )
    )

    if missing_required:
        raise ValueError(
            "Configured XR experiences are missing "
            "required Mahindra AI Nexus use cases: "
            +
            ", ".join(
                sorted(
                    missing_required
                )
            )
        )

    return experiences


def _get_xr_session_count(
    generation: Mapping[str, Any],
) -> int:
    """
    Read:

        xr:
            sessions:
                count: 2000
    """

    try:
        count = int(
            generation[
                "xr"
            ][
                "sessions"
            ][
                "count"
            ]
        )

    except KeyError as exc:
        raise KeyError(
            "Missing generation.xr.sessions.count"
        ) from exc

    if count <= 0:
        raise ValueError(
            "generation.xr.sessions.count must be > 0"
        )

    return count


def _get_generation_window(
    generation: Mapping[str, Any],
) -> tuple[
    pd.Timestamp,
    pd.Timestamp,
    str,
]:
    """
    Return timezone-aware generation boundaries.
    """

    try:
        time_config = (
            generation[
                "time"
            ]
        )

        start_value = (
            time_config[
                "start_date"
            ]
        )

        end_value = (
            time_config[
                "end_date"
            ]
        )

        timezone = str(
            time_config.get(
                "timezone",
                "Asia/Kolkata",
            )
        )

    except KeyError as exc:
        raise KeyError(
            "Missing generation.time configuration"
        ) from exc

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
            "generation.time.end_date must be "
            "after generation.time.start_date"
        )

    return (
        start,
        end,
        timezone,
    )


# ============================================================
# PROVENANCE
# ============================================================


def _get_provenance(
    generation: Mapping[str, Any],
) -> tuple[
    str,
    str,
]:
    """
    Return configured provenance fields.
    """

    data_origin = str(
        generation.get(
            "provenance",
            {},
        ).get(
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

    return (
        data_origin,
        generator_version,
    )


# ============================================================
# NUMERIC HELPERS
# ============================================================


def _sigmoid(
    value: float,
) -> float:
    """
    Stable scalar logistic transform.
    """

    value = float(
        np.clip(
            value,
            -30.0,
            30.0,
        )
    )

    return float(
        1.0
        /
        (
            1.0
            +
            np.exp(
                -value
            )
        )
    )


# ============================================================
# VEHICLE MODELS
# ============================================================


def _prepare_vehicle_models(
    vehicle_models: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate canonical vehicle-model master input.
    """

    if vehicle_models.empty:
        raise ValueError(
            "Vehicle-model DataFrame cannot be empty"
        )

    missing_columns = (
        VEHICLE_MODEL_REQUIRED_COLUMNS
        -
        set(
            vehicle_models.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "Vehicle models missing columns: "
            +
            ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    result = (
        vehicle_models
        .copy(
            deep=True
        )
    )

    if (
        result[
            "vehicle_model_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Vehicle models contain missing IDs"
        )

    if (
        result[
            "vehicle_model_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate vehicle_model_id values found"
        )

    for column in (
        "production_complexity",
        "generation_weight",
    ):
        result[
            column
        ] = pd.to_numeric(
            result[
                column
            ],
            errors="raise",
        )

    if (
        result[
            "production_complexity"
        ]
        <
        0
    ).any():
        raise ValueError(
            "production_complexity cannot be negative"
        )

    if (
        result[
            "generation_weight"
        ]
        <
        0
    ).any():
        raise ValueError(
            "generation_weight cannot be negative"
        )

    if (
        float(
            result[
                "generation_weight"
            ]
            .sum()
        )
        <=
        0
    ):
        raise ValueError(
            "Vehicle-model generation weights must "
            "have positive total"
        )

    return (
        result
        .reset_index(
            drop=True
        )
    )


# ============================================================
# XR EXPERIENCE REFERENCE DATA
# ============================================================


def generate_xr_experiences(
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate XR experience reference/configuration rows.
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    experience_names = (
        _get_xr_experience_names(
            generation
        )
    )

    (
        data_origin,
        generator_version,
    ) = (
        _get_provenance(
            generation
        )
    )

    rows: list[
        dict[str, Any]
    ] = []

    for (
        sequence,
        experience_type,
    ) in enumerate(
        experience_names,
        start=1,
    ):
        spec = (
            EXPERIENCE_SPECS[
                experience_type
            ]
        )

        rows.append(
            {
                "experience_id":
                    generate_id(
                        "XR_EXP",
                        sequence,
                        width=2,
                    ),

                "experience_type":
                    experience_type,

                "experience_category":
                    str(
                        spec[
                            "experience_category"
                        ]
                    ),

                "primary_persona_group":
                    str(
                        spec[
                            "primary_persona_group"
                        ]
                    ),

                "device_mode":
                    str(
                        spec[
                            "device_mode"
                        ]
                    ),

                "supports_ai_assistant":
                    bool(
                        spec[
                            "supports_ai_assistant"
                        ]
                    ),

                "supports_configuration":
                    bool(
                        spec[
                            "supports_configuration"
                        ]
                    ),

                "supports_training_score":
                    bool(
                        spec[
                            "supports_training_score"
                        ]
                    ),

                "supports_repair_steps":
                    bool(
                        spec[
                            "supports_repair_steps"
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

    experiences = pd.DataFrame(
        rows
    )

    validate_xr_experiences(
        experiences=
            experiences,

        generation=
            generation,
    )

    return experiences


# ============================================================
# EXPERIENCE REFERENCE VALIDATION
# ============================================================


def validate_xr_experiences(
    experiences: pd.DataFrame,
    generation: Mapping[str, Any],
) -> None:
    """
    Validate XR experience reference rows.
    """

    required_columns = {
        "experience_id",
        "experience_type",
        "experience_category",
        "primary_persona_group",
        "device_mode",

        "supports_ai_assistant",
        "supports_configuration",
        "supports_training_score",
        "supports_repair_steps",

        "active",

        "data_origin",
        "generator_version",
    }

    missing_columns = (
        required_columns
        -
        set(
            experiences.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "XR experiences missing columns: "
            +
            ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    configured_experiences = (
        _get_xr_experience_names(
            generation
        )
    )

    if (
        len(
            experiences
        )
        !=
        len(
            configured_experiences
        )
    ):
        raise ValueError(
            "Unexpected XR experience count"
        )

    if (
        experiences[
            "experience_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate XR experience IDs found"
        )

    if (
        experiences[
            "experience_type"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate XR experience types found"
        )

    if (
        set(
            experiences[
                "experience_type"
            ]
            .astype(str)
        )
        !=
        set(
            configured_experiences
        )
    ):
        raise ValueError(
            "XR experience rows do not match "
            "generation configuration"
        )

    if (
        ~experiences[
            "active"
        ]
        .isin(
            [
                True,
                False,
            ]
        )
    ).any():
        raise ValueError(
            "XR experience active flag must be boolean"
        )

    if (
        ~experiences[
            "active"
        ]
        .astype(bool)
    ).any():
        raise ValueError(
            "All configured XR experiences must be active"
        )


# ============================================================
# BALANCED EXPERIENCE ASSIGNMENT
# ============================================================


def _balanced_experience_assignments(
    rng: np.random.Generator,
    session_count: int,
    experience_count: int,
) -> np.ndarray:
    """
    Allocate sessions as evenly as possible across configured
    experiences.

    No XR experience weights exist in current configuration,
    so equal allocation is the least-assumptive choice.
    """

    if experience_count <= 0:
        raise ValueError(
            "experience_count must be positive"
        )

    base_count = (
        session_count
        //
        experience_count
    )

    remainder = (
        session_count
        %
        experience_count
    )

    assignments: list[int] = []

    for experience_index in range(
        experience_count
    ):
        count = (
            base_count
            +
            (
                1
                if experience_index < remainder
                else 0
            )
        )

        assignments.extend(
            [
                experience_index
            ]
            *
            count
        )

    assignment_array = np.asarray(
        assignments,
        dtype=int,
    )

    rng.shuffle(
        assignment_array
    )

    return assignment_array


# ============================================================
# PERSONA
# ============================================================


def _sample_persona(
    rng: np.random.Generator,
    experience_type: str,
) -> str:
    """
    Sample persona appropriate to the experience.
    """

    spec = (
        EXPERIENCE_SPECS[
            experience_type
        ]
    )

    personas = (
        spec[
            "personas"
        ]
    )

    weights = np.asarray(
        spec[
            "persona_weights"
        ],
        dtype=float,
    )

    weights = (
        weights
        /
        weights.sum()
    )

    return str(
        rng.choice(
            personas,
            p=weights,
        )
    )


# ============================================================
# ENGAGEMENT
# ============================================================


def _sample_engagement_seconds(
    rng: np.random.Generator,
    experience_type: str,
) -> int:
    """
    Generate bounded observed engagement duration.
    """

    spec = (
        EXPERIENCE_SPECS[
            experience_type
        ]
    )

    engagement = float(
        rng.normal(
            loc=float(
                spec[
                    "engagement_mean_seconds"
                ]
            ),

            scale=float(
                spec[
                    "engagement_std_seconds"
                ]
            ),
        )
    )

    engagement = float(
        np.clip(
            engagement,

            int(
                spec[
                    "engagement_min_seconds"
                ]
            ),

            int(
                spec[
                    "engagement_max_seconds"
                ]
            ),
        )
    )

    return int(
        round(
            engagement
        )
    )


# ============================================================
# ASSISTANT INTERACTIONS
# ============================================================


def _sample_assistant_interactions(
    rng: np.random.Generator,
    experience_type: str,
    engagement_seconds: int,
) -> int:
    """
    Generate observed assistant-interaction count.

    Longer sessions have more opportunity for interaction.
    """

    spec = (
        EXPERIENCE_SPECS[
            experience_type
        ]
    )

    ten_minute_blocks = (
        float(
            engagement_seconds
        )
        /
        600.0
    )

    interaction_lambda = (
        float(
            spec[
                "assistant_base_lambda"
            ]
        )
        +
        float(
            spec[
                "assistant_per_10_minutes"
            ]
        )
        *
        ten_minute_blocks
    )

    interaction_lambda = float(
        np.clip(
            interaction_lambda,
            0.10,
            15.0,
        )
    )

    interactions = int(
        rng.poisson(
            interaction_lambda
        )
    )

    return int(
        np.clip(
            interactions,
            0,
            25,
        )
    )


# ============================================================
# SYNTHETIC CONFIGURATION SELECTION
# ============================================================


def _sample_configuration_selected(
    rng: np.random.Generator,
    experience_type: str,
    vehicle_model_id: str,
    engagement_seconds: int,
    assistant_interactions: int,
) -> str | None:
    """
    Generate an observed configuration-selection event.

    Generic synthetic codes are used instead of actual trims.
    """

    if experience_type not in {
        AI_VIRTUAL_SHOWROOM,
        VEHICLE_CONFIGURATOR,
    }:
        return None

    if (
        experience_type
        ==
        AI_VIRTUAL_SHOWROOM
    ):
        logit = (
            -0.70
            +
            0.0012
            *
            (
                engagement_seconds
                -
                600
            )
            +
            0.11
            *
            assistant_interactions
        )

    else:
        logit = (
            0.10
            +
            0.0014
            *
            (
                engagement_seconds
                -
                800
            )
            +
            0.10
            *
            assistant_interactions
        )

    selection_probability = (
        _sigmoid(
            logit
        )
    )

    if (
        rng.random()
        >=
        selection_probability
    ):
        return None

    configuration_level = str(
        rng.choice(
            CONFIGURATION_LEVELS,
            p=
                CONFIGURATION_LEVEL_WEIGHTS,
        )
    )

    return (
        f"{vehicle_model_id}"
        f"_CONFIG_"
        f"{configuration_level}"
    )


# ============================================================
# CUSTOMER SESSION OUTCOME
# ============================================================


def _generate_customer_outcome(
    rng: np.random.Generator,
    experience_type: str,
    engagement_seconds: int,
    assistant_interactions: int,
    configuration_selected: str | None,
) -> str:
    """
    Generate observed customer session outcome.

    This is not a predicted conversion probability.
    """

    selected_flag = (
        1.0
        if configuration_selected is not None
        else 0.0
    )

    engagement_signal = (
        float(
            engagement_seconds
        )
        /
        1200.0
    )

    interaction_signal = (
        min(
            float(
                assistant_interactions
            )
            /
            8.0,
            1.5,
        )
    )

    intent_strength = (
        _sigmoid(
            -1.25
            +
            1.10
            *
            engagement_signal
            +
            0.55
            *
            interaction_signal
            +
            0.80
            *
            selected_flag
        )
    )

    abandonment_probability = float(
        np.clip(
            0.30
            -
            0.24
            *
            intent_strength,
            0.04,
            0.30,
        )
    )

    if (
        rng.random()
        <
        abandonment_probability
    ):
        return OUTCOME_ABANDONED

    random_value = float(
        rng.random()
    )

    if (
        experience_type
        ==
        AI_VIRTUAL_SHOWROOM
    ):
        booking_probability = (
            0.05
            +
            0.15
            *
            intent_strength
        )

        test_drive_probability = (
            0.10
            +
            0.22
            *
            intent_strength
        )

        if (
            random_value
            <
            booking_probability
        ):
            return (
                OUTCOME_BOOKING_INTENT
            )

        if (
            random_value
            <
            booking_probability
            +
            test_drive_probability
        ):
            return (
                OUTCOME_TEST_DRIVE_INTENT
            )

        return (
            OUTCOME_EXPERIENCE_COMPLETED
        )

    booking_probability = (
        0.06
        +
        0.17
        *
        intent_strength
    )

    test_drive_probability = (
        0.08
        +
        0.18
        *
        intent_strength
    )

    configuration_save_probability = (
        (
            0.10
            +
            0.24
            *
            intent_strength
        )
        if configuration_selected is not None
        else
        0.04
    )

    if (
        random_value
        <
        booking_probability
    ):
        return (
            OUTCOME_BOOKING_INTENT
        )

    if (
        random_value
        <
        booking_probability
        +
        test_drive_probability
    ):
        return (
            OUTCOME_TEST_DRIVE_INTENT
        )

    if (
        random_value
        <
        booking_probability
        +
        test_drive_probability
        +
        configuration_save_probability
    ):
        return (
            OUTCOME_CONFIGURATION_SAVED
        )

    return (
        OUTCOME_EXPERIENCE_COMPLETED
    )


# ============================================================
# AR REPAIR SESSION
# ============================================================


def _generate_repair_activity(
    rng: np.random.Generator,
    production_complexity: float,
    engagement_seconds: int,
    assistant_interactions: int,
) -> tuple[
    int,
    int,
    str,
]:
    """
    Generate observed AR repair-guide progression.

    Repair completion is influenced by:

        engagement duration
        assistant usage
        vehicle production complexity
        unobserved session variation

    Full repair completion is modeled explicitly rather than
    relying on rounding a continuous completion fraction.

    This prevents the synthetic world from unrealistically
    producing zero completed repair sessions while preserving
    meaningful partial and escalation outcomes.

    This creates operational outcomes only. It does NOT create:

        technician productivity uplift
        repair-success prediction
        recommendation confidence
        predicted escalation
    """

    # ========================================================
    # TOTAL PROCEDURAL STEPS
    # ========================================================

    total_steps = int(
        round(
            6.0
            +
            8.0
            *
            float(
                production_complexity
            )
            +
            int(
                rng.integers(
                    -1,
                    2,
                )
            )
        )
    )

    total_steps = int(
        np.clip(
            total_steps,
            7,
            16,
        )
    )

    # ========================================================
    # NORMALIZED OPERATIONAL SIGNALS
    # ========================================================

    engagement_signal = float(
        np.clip(
            (
                float(
                    engagement_seconds
                )
                -
                300.0
            )
            /
            (
                3600.0
                -
                300.0
            ),
            0.0,
            1.0,
        )
    )

    assistant_signal = float(
        np.clip(
            float(
                assistant_interactions
            )
            /
            10.0,
            0.0,
            1.5,
        )
    )

    complexity_signal = float(
        np.clip(
            production_complexity,
            0.0,
            1.0,
        )
    )

    # ========================================================
    # PARTIAL COMPLETION FRACTION
    #
    # Engagement matters, but the relationship includes enough
    # noise that engagement does not deterministically explain
    # nearly all variation.
    # ========================================================

    completion_fraction = (
        0.46
        +
        0.34
        *
        engagement_signal
        +
        0.10
        *
        assistant_signal
        -
        0.08
        *
        complexity_signal
        +
        float(
            rng.normal(
                0.0,
                0.11,
            )
        )
    )

    completion_fraction = float(
        np.clip(
            completion_fraction,
            0.15,
            0.95,
        )
    )

    # ========================================================
    # EXPLICIT FULL-COMPLETION EVENT
    #
    # Longer engagement and useful assistant interaction
    # improve the probability.
    #
    # Higher production complexity reduces it.
    # ========================================================

    full_completion_logit = (
        -2.15
        +
        2.20
        *
        engagement_signal
        +
        0.55
        *
        assistant_signal
        -
        0.55
        *
        complexity_signal
    )

    full_completion_probability = (
        _sigmoid(
            full_completion_logit
        )
    )

    full_completion = bool(
        rng.random()
        <
        full_completion_probability
    )

    # ========================================================
    # COMPLETED STEP COUNT
    # ========================================================

    if full_completion:

        completed_steps = (
            total_steps
        )

    else:

        completed_steps = int(
            round(
                total_steps
                *
                completion_fraction
            )
        )

        completed_steps = int(
            np.clip(
                completed_steps,
                1,
                total_steps
                -
                1,
            )
        )

    observed_fraction = (
        completed_steps
        /
        total_steps
    )

    # ========================================================
    # OBSERVED SESSION OUTCOME
    # ========================================================

    if (
        completed_steps
        ==
        total_steps
    ):

        outcome = (
            OUTCOME_REPAIR_COMPLETED
        )

    elif (
        observed_fraction
        <
        0.60
        and
        assistant_interactions
        >=
        4
        and
        rng.random()
        <
        0.50
    ):

        outcome = (
            OUTCOME_TECHNICIAN_ESCALATED
        )

    else:

        outcome = (
            OUTCOME_REPAIR_PARTIAL
        )

    return (
        completed_steps,
        total_steps,
        outcome,
    )


# ============================================================
# VR TRAINING SESSION
# ============================================================


def _generate_training_activity(
    rng: np.random.Generator,
    persona: str,
    production_complexity: float,
    engagement_seconds: int,
    assistant_interactions: int,
) -> tuple[
    float,
    str,
]:
    """
    Generate observed dealer-training score and completion
    outcome.
    """

    persona_adjustment = {
        SALES_CONSULTANT: 3.0,
        SALES_MANAGER: 6.0,
        NEW_JOINER: -4.0,
    }[
        persona
    ]

    engagement_effect = (
        0.010
        *
        (
            engagement_seconds
            -
            1800
        )
    )

    assistant_effect = (
        1.00
        *
        assistant_interactions
    )

    complexity_effect = (
        -10.0
        *
        (
            production_complexity
            -
            0.65
        )
    )

    raw_score = (
        65.0
        +
        persona_adjustment
        +
        engagement_effect
        +
        assistant_effect
        +
        complexity_effect
        +
        float(
            rng.normal(
                0.0,
                8.5,
            )
        )
    )

    training_score = round(
        float(
            np.clip(
                raw_score,
                25.0,
                100.0,
            )
        ),
        2,
    )

    incomplete_probability = float(
        np.clip(
            0.28
            -
            0.00008
            *
            engagement_seconds,
            0.03,
            0.25,
        )
    )

    if (
        rng.random()
        <
        incomplete_probability
    ):
        outcome = (
            OUTCOME_TRAINING_INCOMPLETE
        )

    elif training_score >= 70.0:
        outcome = (
            OUTCOME_TRAINING_PASSED
        )

    else:
        outcome = (
            OUTCOME_TRAINING_FAILED
        )

    return (
        training_score,
        outcome,
    )


# ============================================================
# SESSION START
# ============================================================


def _sample_session_start(
    rng: np.random.Generator,
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
    maximum_session_seconds: int,
) -> pd.Timestamp:
    """
    Generate session start while reserving enough time for the
    longest allowed session.
    """

    available_seconds = (
        (
            generation_end
            -
            generation_start
        )
        .total_seconds()
        -
        maximum_session_seconds
    )

    if available_seconds <= 0:
        raise ValueError(
            "Generation window too short for XR sessions"
        )

    offset_seconds = float(
        rng.uniform(
            0.0,
            available_seconds,
        )
    )

    return (
        generation_start
        +
        pd.Timedelta(
            seconds=
                offset_seconds
        )
    )


# ============================================================
# MAIN XR SESSION GENERATOR
# ============================================================


def generate_xr_sessions(
    vehicle_models: pd.DataFrame,
    xr_experiences: pd.DataFrame | None = None,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate operational XR session history.
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    # ========================================================
    # CONFIG
    # ========================================================

    session_count = (
        _get_xr_session_count(
            generation
        )
    )

    (
        generation_start,
        generation_end,
        timezone,
    ) = (
        _get_generation_window(
            generation
        )
    )

    (
        data_origin,
        generator_version,
    ) = (
        _get_provenance(
            generation
        )
    )

    # ========================================================
    # INPUT DATA
    # ========================================================

    models = (
        _prepare_vehicle_models(
            vehicle_models
        )
    )

    if xr_experiences is None:

        experiences = (
            generate_xr_experiences(
                generation=
                    generation
            )
        )

    else:

        experiences = (
            xr_experiences
            .copy(
                deep=True
            )
        )

        validate_xr_experiences(
            experiences=
                experiences,

            generation=
                generation,
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
            "xr.sessions",
        )
    )

    # ========================================================
    # EXPERIENCE ASSIGNMENTS
    # ========================================================

    experience_assignments = (
        _balanced_experience_assignments(
            rng=rng,

            session_count=
                session_count,

            experience_count=
                len(
                    experiences
                ),
        )
    )

    # ========================================================
    # VEHICLE MODEL WEIGHTS
    # ========================================================

    model_weights = (
        models[
            "generation_weight"
        ]
        .to_numpy(
            dtype=float
        )
    )

    model_weights = (
        model_weights
        /
        model_weights.sum()
    )

    # ========================================================
    # GLOBAL MAX SESSION LENGTH
    # ========================================================

    maximum_session_seconds = int(
        max(
            int(
                spec[
                    "engagement_max_seconds"
                ]
            )

            for spec in (
                EXPERIENCE_SPECS.values()
            )
        )
    )

    rows: list[
        dict[str, Any]
    ] = []

    # ========================================================
    # GENERATE SESSIONS
    # ========================================================

    for session_index in range(
        session_count
    ):

        # ----------------------------------------------------
        # Experience
        # ----------------------------------------------------

        experience_row = (
            experiences.iloc[
                int(
                    experience_assignments[
                        session_index
                    ]
                )
            ]
        )

        experience_id = str(
            experience_row[
                "experience_id"
            ]
        )

        experience_type = str(
            experience_row[
                "experience_type"
            ]
        )

        # ----------------------------------------------------
        # Vehicle model
        # ----------------------------------------------------

        model_position = int(
            rng.choice(
                len(
                    models
                ),
                p=
                    model_weights,
            )
        )

        model = (
            models.iloc[
                model_position
            ]
        )

        vehicle_model_id = str(
            model[
                "vehicle_model_id"
            ]
        )

        production_complexity = float(
            model[
                "production_complexity"
            ]
        )

        # ----------------------------------------------------
        # Persona
        # ----------------------------------------------------

        persona = (
            _sample_persona(
                rng=rng,

                experience_type=
                    experience_type,
            )
        )

        # ----------------------------------------------------
        # Engagement
        # ----------------------------------------------------

        engagement_seconds = (
            _sample_engagement_seconds(
                rng=rng,

                experience_type=
                    experience_type,
            )
        )

        # ----------------------------------------------------
        # Timestamp
        # ----------------------------------------------------

        started_at = (
            _sample_session_start(
                rng=rng,

                generation_start=
                    generation_start,

                generation_end=
                    generation_end,

                maximum_session_seconds=
                    maximum_session_seconds,
            )
        )

        completed_at = (
            started_at
            +
            pd.Timedelta(
                seconds=
                    engagement_seconds
            )
        )

        # ----------------------------------------------------
        # Assistant usage
        # ----------------------------------------------------

        assistant_interactions = (
            _sample_assistant_interactions(
                rng=rng,

                experience_type=
                    experience_type,

                engagement_seconds=
                    engagement_seconds,
            )
        )

        # ----------------------------------------------------
        # Experience-specific outputs
        # ----------------------------------------------------

        configuration_selected: Any = None

        training_score: Any = np.nan

        repair_steps_completed: Any = np.nan

        repair_steps_total: Any = np.nan

        # ----------------------------------------------------
        # Customer-facing XR
        # ----------------------------------------------------

        if experience_type in {
            AI_VIRTUAL_SHOWROOM,
            VEHICLE_CONFIGURATOR,
        }:

            configuration_selected = (
                _sample_configuration_selected(
                    rng=rng,

                    experience_type=
                        experience_type,

                    vehicle_model_id=
                        vehicle_model_id,

                    engagement_seconds=
                        engagement_seconds,

                    assistant_interactions=
                        assistant_interactions,
                )
            )

            outcome = (
                _generate_customer_outcome(
                    rng=rng,

                    experience_type=
                        experience_type,

                    engagement_seconds=
                        engagement_seconds,

                    assistant_interactions=
                        assistant_interactions,

                    configuration_selected=
                        configuration_selected,
                )
            )

        # ----------------------------------------------------
        # AR technician guide
        # ----------------------------------------------------

        elif (
            experience_type
            ==
            AR_TECHNICIAN_REPAIR_GUIDE
        ):

            (
                repair_steps_completed,
                repair_steps_total,
                outcome,
            ) = (
                _generate_repair_activity(
                    rng=rng,

                    production_complexity=
                        production_complexity,

                    engagement_seconds=
                        engagement_seconds,

                    assistant_interactions=
                        assistant_interactions,
                )
            )

        # ----------------------------------------------------
        # VR dealer training
        # ----------------------------------------------------

        elif (
            experience_type
            ==
            VR_DEALER_SALES_TRAINING
        ):

            (
                training_score,
                outcome,
            ) = (
                _generate_training_activity(
                    rng=rng,

                    persona=
                        persona,

                    production_complexity=
                        production_complexity,

                    engagement_seconds=
                        engagement_seconds,

                    assistant_interactions=
                        assistant_interactions,
                )
            )

        else:
            raise ValueError(
                "Unexpected XR experience type: "
                f"{experience_type}"
            )

        # ----------------------------------------------------
        # Session row
        # ----------------------------------------------------

        rows.append(
            {
                "session_id":
                    generate_id(
                        "XR_SESSION",
                        session_index
                        +
                        1,
                        width=7,
                    ),

                "experience_id":
                    experience_id,

                "experience_type":
                    experience_type,

                "experience_category":
                    str(
                        experience_row[
                            "experience_category"
                        ]
                    ),

                "device_mode":
                    str(
                        experience_row[
                            "device_mode"
                        ]
                    ),

                "vehicle_model_id":
                    vehicle_model_id,

                "model_name":
                    str(
                        model[
                            "model_name"
                        ]
                    ),

                "segment":
                    str(
                        model[
                            "segment"
                        ]
                    ),

                "persona":
                    persona,

                "started_at":
                    started_at
                    .tz_convert(
                        timezone
                    ),

                "completed_at":
                    completed_at
                    .tz_convert(
                        timezone
                    ),

                "engagement_seconds":
                    int(
                        engagement_seconds
                    ),

                "configuration_selected":
                    configuration_selected,

                "assistant_interactions":
                    int(
                        assistant_interactions
                    ),

                "training_score":
                    training_score,

                "repair_steps_completed":
                    repair_steps_completed,

                "repair_steps_total":
                    repair_steps_total,

                "conversion_or_completion_outcome":
                    str(
                        outcome
                    ),

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    sessions = pd.DataFrame(
        rows
    )

    # ========================================================
    # FINAL COLUMN ORDER
    # ========================================================

    output_columns = [
        "session_id",

        "experience_id",
        "experience_type",
        "experience_category",
        "device_mode",

        "vehicle_model_id",
        "model_name",
        "segment",

        "persona",

        "started_at",
        "completed_at",

        "engagement_seconds",

        "configuration_selected",

        "assistant_interactions",

        "training_score",

        "repair_steps_completed",
        "repair_steps_total",

        "conversion_or_completion_outcome",

        "data_origin",
        "generator_version",
    ]

    sessions = (
        sessions[
            output_columns
        ]
        .copy()
    )

    # ========================================================
    # VALIDATE
    # ========================================================

    validate_xr_sessions(
        sessions=
            sessions,

        experiences=
            experiences,

        vehicle_models=
            models,

        generation=
            generation,
    )

    return sessions


# ============================================================
# XR SESSION VALIDATION
# ============================================================


def validate_xr_sessions(
    sessions: pd.DataFrame,
    experiences: pd.DataFrame,
    vehicle_models: pd.DataFrame,
    generation: Mapping[str, Any],
) -> None:
    """
    Validate XR session operational integrity.
    """

    required_columns = {
        "session_id",

        "experience_id",
        "experience_type",
        "experience_category",
        "device_mode",

        "vehicle_model_id",
        "model_name",
        "segment",

        "persona",

        "started_at",
        "completed_at",

        "engagement_seconds",

        "configuration_selected",

        "assistant_interactions",

        "training_score",

        "repair_steps_completed",
        "repair_steps_total",

        "conversion_or_completion_outcome",

        "data_origin",
        "generator_version",
    }

    missing_columns = (
        required_columns
        -
        set(
            sessions.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "XR sessions missing columns: "
            +
            ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if sessions.empty:
        raise ValueError(
            "XR session generator produced zero rows"
        )

    # ========================================================
    # EXACT COUNT
    # ========================================================

    expected_count = (
        _get_xr_session_count(
            generation
        )
    )

    if (
        len(
            sessions
        )
        !=
        expected_count
    ):
        raise ValueError(
            "Unexpected XR session count. "
            f"Expected={expected_count}, "
            f"actual={len(sessions)}"
        )

    # ========================================================
    # SESSION IDs
    # ========================================================

    if (
        sessions[
            "session_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "XR sessions contain missing session IDs"
        )

    if (
        sessions[
            "session_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate XR session IDs found"
        )

    # ========================================================
    # EXPERIENCE FK
    # ========================================================

    valid_experience_ids = set(
        experiences[
            "experience_id"
        ]
        .astype(str)
    )

    invalid_experience_ids = (
        set(
            sessions[
                "experience_id"
            ]
            .astype(str)
        )
        -
        valid_experience_ids
    )

    if invalid_experience_ids:
        raise ValueError(
            "XR sessions reference invalid experiences"
        )

    if (
        set(
            sessions[
                "experience_id"
            ]
            .astype(str)
        )
        !=
        valid_experience_ids
    ):
        raise ValueError(
            "Not every configured XR experience "
            "is represented in sessions"
        )

    # ========================================================
    # EXPERIENCE METADATA CONSISTENCY
    # ========================================================

    experience_lookup = (
        experiences
        .set_index(
            "experience_id"
        )
    )

    for record in sessions.itertuples(
        index=False
    ):

        experience = (
            experience_lookup.loc[
                str(
                    record.experience_id
                )
            ]
        )

        if (
            str(
                record.experience_type
            )
            !=
            str(
                experience[
                    "experience_type"
                ]
            )
        ):
            raise ValueError(
                f"{record.session_id}: "
                "experience_type does not match "
                "experience_id"
            )

        if (
            str(
                record.experience_category
            )
            !=
            str(
                experience[
                    "experience_category"
                ]
            )
        ):
            raise ValueError(
                f"{record.session_id}: "
                "experience_category mismatch"
            )

        if (
            str(
                record.device_mode
            )
            !=
            str(
                experience[
                    "device_mode"
                ]
            )
        ):
            raise ValueError(
                f"{record.session_id}: "
                "device_mode mismatch"
            )

    # ========================================================
    # VEHICLE-MODEL FK
    # ========================================================

    valid_vehicle_ids = set(
        vehicle_models[
            "vehicle_model_id"
        ]
        .astype(str)
    )

    invalid_vehicle_ids = (
        set(
            sessions[
                "vehicle_model_id"
            ]
            .astype(str)
        )
        -
        valid_vehicle_ids
    )

    if invalid_vehicle_ids:
        raise ValueError(
            "XR sessions reference invalid "
            "vehicle-model IDs"
        )

    vehicle_lookup = (
        vehicle_models
        .set_index(
            "vehicle_model_id"
        )
    )

    for record in sessions.itertuples(
        index=False
    ):

        vehicle = (
            vehicle_lookup.loc[
                str(
                    record.vehicle_model_id
                )
            ]
        )

        if (
            str(
                record.model_name
            )
            !=
            str(
                vehicle[
                    "model_name"
                ]
            )
        ):
            raise ValueError(
                f"{record.session_id}: "
                "model_name inconsistent with "
                "vehicle_model_id"
            )

        if (
            str(
                record.segment
            )
            !=
            str(
                vehicle[
                    "segment"
                ]
            )
        ):
            raise ValueError(
                f"{record.session_id}: "
                "segment inconsistent with "
                "vehicle_model_id"
            )

    # ========================================================
    # TIMESTAMPS
    # ========================================================

    (
        generation_start,
        generation_end,
        _,
    ) = (
        _get_generation_window(
            generation
        )
    )

    generation_start_utc = (
        generation_start
        .tz_convert(
            "UTC"
        )
    )

    generation_end_utc = (
        generation_end
        .tz_convert(
            "UTC"
        )
    )

    started_at = pd.to_datetime(
        sessions[
            "started_at"
        ],
        utc=True,
    )

    completed_at = pd.to_datetime(
        sessions[
            "completed_at"
        ],
        utc=True,
    )

    if (
        started_at
        <
        generation_start_utc
    ).any():
        raise ValueError(
            "XR session begins before "
            "generation start"
        )

    if (
        completed_at
        >=
        generation_end_utc
    ).any():
        raise ValueError(
            "XR session completes on/after "
            "generation end"
        )

    if (
        completed_at
        <=
        started_at
    ).any():
        raise ValueError(
            "XR session completion must be "
            "after start"
        )

    # ========================================================
    # ENGAGEMENT DURATION
    # ========================================================

    engagement = pd.to_numeric(
        sessions[
            "engagement_seconds"
        ],
        errors="raise",
    )

    if (
        engagement
        <=
        0
    ).any():
        raise ValueError(
            "XR engagement_seconds must be positive"
        )

    calculated_engagement = (
        (
            completed_at
            -
            started_at
        )
        .dt
        .total_seconds()
    )

    if not np.allclose(
        calculated_engagement.to_numpy(
            dtype=float
        ),
        engagement.to_numpy(
            dtype=float
        ),
        atol=0.01,
    ):
        raise ValueError(
            "engagement_seconds inconsistent "
            "with timestamps"
        )

    # ========================================================
    # EXPERIENCE-SPECIFIC ENGAGEMENT BOUNDS
    # ========================================================

    for experience_type in (
        SUPPORTED_EXPERIENCES
    ):

        mask = (
            sessions[
                "experience_type"
            ]
            ==
            experience_type
        )

        spec = (
            EXPERIENCE_SPECS[
                experience_type
            ]
        )

        minimum = int(
            spec[
                "engagement_min_seconds"
            ]
        )

        maximum = int(
            spec[
                "engagement_max_seconds"
            ]
        )

        values = (
            sessions.loc[
                mask,
                "engagement_seconds",
            ]
        )

        if (
            (
                values
                <
                minimum
            )
            |
            (
                values
                >
                maximum
            )
        ).any():
            raise ValueError(
                f"{experience_type}: "
                "engagement outside configured "
                "engineering bounds"
            )

    # ========================================================
    # ASSISTANT INTERACTIONS
    # ========================================================

    assistant_interactions = (
        pd.to_numeric(
            sessions[
                "assistant_interactions"
            ],
            errors="raise",
        )
    )

    if (
        assistant_interactions
        <
        0
    ).any():
        raise ValueError(
            "assistant_interactions cannot be negative"
        )

    if not np.all(
        np.equal(
            assistant_interactions,
            np.floor(
                assistant_interactions
            ),
        )
    ):
        raise ValueError(
            "assistant_interactions must be integral"
        )

    # ========================================================
    # CUSTOMER EXPERIENCE CONFIGURATION
    # ========================================================

    customer_mask = (
        sessions[
            "experience_type"
        ]
        .isin(
            [
                AI_VIRTUAL_SHOWROOM,
                VEHICLE_CONFIGURATOR,
            ]
        )
    )

    non_customer_mask = (
        ~customer_mask
    )

    if (
        sessions.loc[
            non_customer_mask,
            "configuration_selected",
        ]
        .notna()
        .any()
    ):
        raise ValueError(
            "Non-customer XR sessions cannot contain "
            "configuration selections"
        )

    selected_configurations = (
        sessions.loc[
            customer_mask
            &
            sessions[
                "configuration_selected"
            ]
            .notna(),

            [
                "vehicle_model_id",
                "configuration_selected",
            ],
        ]
    )

    for record in (
        selected_configurations
        .itertuples(
            index=False
        )
    ):

        expected_prefix = (
            f"{record.vehicle_model_id}"
            "_CONFIG_"
        )

        if not str(
            record.configuration_selected
        ).startswith(
            expected_prefix
        ):
            raise ValueError(
                "configuration_selected is inconsistent "
                "with vehicle model"
            )

    # ========================================================
    # TRAINING SCORE
    # ========================================================

    training_mask = (
        sessions[
            "experience_type"
        ]
        ==
        VR_DEALER_SALES_TRAINING
    )

    non_training_mask = (
        ~training_mask
    )

    if (
        sessions.loc[
            training_mask,
            "training_score",
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "VR training sessions require training_score"
        )

    if (
        sessions.loc[
            non_training_mask,
            "training_score",
        ]
        .notna()
        .any()
    ):
        raise ValueError(
            "Non-training sessions cannot contain "
            "training_score"
        )

    training_scores = pd.to_numeric(
        sessions.loc[
            training_mask,
            "training_score",
        ],
        errors="raise",
    )

    if (
        (
            training_scores
            <
            0
        )
        |
        (
            training_scores
            >
            100
        )
    ).any():
        raise ValueError(
            "training_score must be between 0 and 100"
        )

    # ========================================================
    # REPAIR STEPS
    # ========================================================

    repair_mask = (
        sessions[
            "experience_type"
        ]
        ==
        AR_TECHNICIAN_REPAIR_GUIDE
    )

    non_repair_mask = (
        ~repair_mask
    )

    if (
        sessions.loc[
            repair_mask,

            [
                "repair_steps_completed",
                "repair_steps_total",
            ],
        ]
        .isna()
        .any()
        .any()
    ):
        raise ValueError(
            "AR technician sessions require "
            "repair-step data"
        )

    if (
        sessions.loc[
            non_repair_mask,

            [
                "repair_steps_completed",
                "repair_steps_total",
            ],
        ]
        .notna()
        .any()
        .any()
    ):
        raise ValueError(
            "Non-repair XR sessions cannot contain "
            "repair-step values"
        )

    repair_completed = pd.to_numeric(
        sessions.loc[
            repair_mask,
            "repair_steps_completed",
        ],
        errors="raise",
    )

    repair_total = pd.to_numeric(
        sessions.loc[
            repair_mask,
            "repair_steps_total",
        ],
        errors="raise",
    )

    if (
        repair_total
        <=
        0
    ).any():
        raise ValueError(
            "repair_steps_total must be positive"
        )

    if (
        repair_completed
        <=
        0
    ).any():
        raise ValueError(
            "repair_steps_completed must be positive"
        )

    if (
        repair_completed
        >
        repair_total
    ).any():
        raise ValueError(
            "repair_steps_completed cannot exceed "
            "repair_steps_total"
        )

    # ========================================================
    # REPAIR OUTCOME ↔ STEP CONSISTENCY
    # ========================================================

    repair_rows = (
        sessions.loc[
            repair_mask
        ]
        .copy()
    )

    completed_repair_mask = (
        repair_rows[
            "conversion_or_completion_outcome"
        ]
        ==
        OUTCOME_REPAIR_COMPLETED
    )

    incomplete_repair_mask = (
        ~completed_repair_mask
    )

    if (
        repair_rows.loc[
            completed_repair_mask,
            "repair_steps_completed",
        ]
        !=
        repair_rows.loc[
            completed_repair_mask,
            "repair_steps_total",
        ]
    ).any():
        raise ValueError(
            "REPAIR_COMPLETED requires all repair "
            "steps to be completed"
        )

    if (
        repair_rows.loc[
            incomplete_repair_mask,
            "repair_steps_completed",
        ]
        >=
        repair_rows.loc[
            incomplete_repair_mask,
            "repair_steps_total",
        ]
    ).any():
        raise ValueError(
            "Partial/escalated repair outcomes must "
            "remain below total repair steps"
        )

    # ========================================================
    # PERSONA VALIDATION
    # ========================================================

    for experience_type in (
        SUPPORTED_EXPERIENCES
    ):

        mask = (
            sessions[
                "experience_type"
            ]
            ==
            experience_type
        )

        valid_personas = set(
            EXPERIENCE_SPECS[
                experience_type
            ][
                "personas"
            ]
        )

        observed_personas = set(
            sessions.loc[
                mask,
                "persona",
            ]
            .astype(str)
        )

        if not observed_personas.issubset(
            valid_personas
        ):
            raise ValueError(
                f"{experience_type}: "
                "invalid persona found"
            )

    # ========================================================
    # OUTCOME VALIDATION
    # ========================================================

    for experience_type in (
        SUPPORTED_EXPERIENCES
    ):

        mask = (
            sessions[
                "experience_type"
            ]
            ==
            experience_type
        )

        observed_outcomes = set(
            sessions.loc[
                mask,
                "conversion_or_completion_outcome",
            ]
            .astype(str)
        )

        allowed_outcomes = (
            VALID_OUTCOMES_BY_EXPERIENCE[
                experience_type
            ]
        )

        if not observed_outcomes.issubset(
            allowed_outcomes
        ):
            raise ValueError(
                f"{experience_type}: "
                "invalid session outcome found"
            )

    # ========================================================
    # PROVENANCE
    # ========================================================

    if (
        sessions[
            "data_origin"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "XR sessions contain missing data_origin"
        )

    if (
        sessions[
            "generator_version"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "XR sessions contain missing "
            "generator_version"
        )

    # ========================================================
    # HIDDEN RUNTIME / AI / TRUTH LEAKAGE
    # ========================================================

    leaked_columns = (
        HIDDEN_RUNTIME_COLUMNS
        &
        set(
            sessions.columns
        )
    )

    if leaked_columns:
        raise ValueError(
            "Runtime / AI / truth fields leaked "
            "into XR sessions: "
            +
            ", ".join(
                sorted(
                    leaked_columns
                )
            )
        )


# ============================================================
# COMBINED GENERATOR
# ============================================================


def generate_xr(
    vehicle_models: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Generate both XR DataFrames.

    Returns:

        xr_experiences
        xr_sessions
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    experiences = (
        generate_xr_experiences(
            generation=
                generation
        )
    )

    sessions = (
        generate_xr_sessions(
            vehicle_models=
                vehicle_models,

            xr_experiences=
                experiences,

            generation=
                generation,
        )
    )

    return (
        experiences,
        sessions,
    )


# ============================================================
# LOCAL TEST
# ============================================================


if __name__ == "__main__":

    from data.generators.master.vehicle_models import (
        generate_vehicle_models,
    )

    # ========================================================
    # CONFIG / MASTER
    # ========================================================

    generation_config = (
        load_generation_config()
    )

    vehicle_models_df = (
        generate_vehicle_models()
    )

    # ========================================================
    # GENERATE
    # ========================================================

    (
        xr_experiences_df,
        xr_sessions_df,
    ) = (
        generate_xr(
            vehicle_models=
                vehicle_models_df,

            generation=
                generation_config,
        )
    )

    # ========================================================
    # DEPENDENCY CHECK
    # ========================================================

    print(
        "\n=== XR DEPENDENCY CHECK ===\n"
    )

    print(
        "Vehicle models:",
        len(
            vehicle_models_df
        ),
    )

    print(
        "Configured experiences:",
        len(
            _get_xr_experience_names(
                generation_config
            )
        ),
    )

    print(
        "Configured sessions:",
        _get_xr_session_count(
            generation_config
        ),
    )

    # ========================================================
    # EXPERIENCE REFERENCE DATA
    # ========================================================

    print(
        "\n=== XR EXPERIENCES ===\n"
    )

    print(
        xr_experiences_df
        .to_string(
            index=False
        )
    )

    # ========================================================
    # SESSION SAMPLE
    # ========================================================

    print(
        "\n=== XR SESSION SAMPLE ===\n"
    )

    sample_columns = [
        "session_id",

        "experience_type",

        "model_name",
        "segment",

        "persona",

        "started_at",
        "completed_at",

        "engagement_seconds",

        "configuration_selected",

        "assistant_interactions",

        "training_score",

        "repair_steps_completed",
        "repair_steps_total",

        "conversion_or_completion_outcome",
    ]

    print(
        xr_sessions_df[
            sample_columns
        ]
        .head(
            50
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # EXPERIENCE MIX
    # ========================================================

    print(
        "\n=== XR EXPERIENCE MIX ===\n"
    )

    experience_mix = (
        xr_sessions_df
        .groupby(
            "experience_type",
            as_index=False,
        )
        .agg(
            sessions=(
                "session_id",
                "size",
            ),

            average_engagement_seconds=(
                "engagement_seconds",
                "mean",
            ),

            average_assistant_interactions=(
                "assistant_interactions",
                "mean",
            ),
        )
    )

    experience_mix[
        "rate"
    ] = (
        experience_mix[
            "sessions"
        ]
        /
        len(
            xr_sessions_df
        )
    ).round(
        4
    )

    experience_mix[
        "average_engagement_seconds"
    ] = (
        experience_mix[
            "average_engagement_seconds"
        ]
        .round(
            2
        )
    )

    experience_mix[
        "average_assistant_interactions"
    ] = (
        experience_mix[
            "average_assistant_interactions"
        ]
        .round(
            3
        )
    )

    print(
        experience_mix
        .to_string(
            index=False
        )
    )

    # ========================================================
    # VEHICLE MODEL MIX
    # ========================================================

    print(
        "\n=== XR VEHICLE MODEL MIX ===\n"
    )

    model_mix = (
        xr_sessions_df
        .groupby(
            [
                "vehicle_model_id",
                "model_name",
                "segment",
            ],
            as_index=False,
        )
        .agg(
            sessions=(
                "session_id",
                "size",
            ),

            average_engagement_seconds=(
                "engagement_seconds",
                "mean",
            ),
        )
        .sort_values(
            "sessions",
            ascending=False,
        )
    )

    model_mix[
        "average_engagement_seconds"
    ] = (
        model_mix[
            "average_engagement_seconds"
        ]
        .round(
            2
        )
    )

    print(
        model_mix
        .to_string(
            index=False
        )
    )

    # ========================================================
    # PERSONA MIX
    # ========================================================

    print(
        "\n=== XR PERSONA MIX ===\n"
    )

    persona_mix = (
        xr_sessions_df
        .groupby(
            [
                "experience_type",
                "persona",
            ],
            as_index=False,
        )
        .agg(
            sessions=(
                "session_id",
                "size",
            )
        )
    )

    print(
        persona_mix
        .to_string(
            index=False
        )
    )

    # ========================================================
    # OUTCOME MIX
    # ========================================================

    print(
        "\n=== XR OUTCOME MIX ===\n"
    )

    outcome_mix = (
        xr_sessions_df
        .groupby(
            [
                "experience_type",
                "conversion_or_completion_outcome",
            ],
            as_index=False,
        )
        .agg(
            sessions=(
                "session_id",
                "size",
            )
        )
    )

    outcome_totals = (
        outcome_mix
        .groupby(
            "experience_type"
        )[
            "sessions"
        ]
        .transform(
            "sum"
        )
    )

    outcome_mix[
        "rate_within_experience"
    ] = (
        outcome_mix[
            "sessions"
        ]
        /
        outcome_totals
    ).round(
        4
    )

    print(
        outcome_mix
        .to_string(
            index=False
        )
    )

    # ========================================================
    # CUSTOMER EXPERIENCE
    # ========================================================

    print(
        "\n=== XR CUSTOMER EXPERIENCE ===\n"
    )

    customer_sessions = (
        xr_sessions_df.loc[
            xr_sessions_df[
                "experience_type"
            ]
            .isin(
                [
                    AI_VIRTUAL_SHOWROOM,
                    VEHICLE_CONFIGURATOR,
                ]
            )
        ]
        .copy()
    )

    configuration_selection_rate = float(
        customer_sessions[
            "configuration_selected"
        ]
        .notna()
        .mean()
    )

    commercial_intent_mask = (
        customer_sessions[
            "conversion_or_completion_outcome"
        ]
        .isin(
            [
                OUTCOME_TEST_DRIVE_INTENT,
                OUTCOME_BOOKING_INTENT,
            ]
        )
    )

    commercial_intent_rate = float(
        commercial_intent_mask.mean()
    )

    print(
        "Customer-facing sessions:",
        len(
            customer_sessions
        ),
    )

    print(
        "Configuration selection rate:",
        round(
            configuration_selection_rate,
            4,
        ),
    )

    print(
        "Test-drive / booking intent rate:",
        round(
            commercial_intent_rate,
            4,
        ),
    )

    # ========================================================
    # AR TECHNICIAN
    # ========================================================

    print(
        "\n=== XR AR TECHNICIAN ACTIVITY ===\n"
    )

    repair_sessions = (
        xr_sessions_df.loc[
            xr_sessions_df[
                "experience_type"
            ]
            ==
            AR_TECHNICIAN_REPAIR_GUIDE
        ]
        .copy()
    )

    repair_sessions[
        "repair_completion_fraction"
    ] = (
        repair_sessions[
            "repair_steps_completed"
        ]
        /
        repair_sessions[
            "repair_steps_total"
        ]
    )

    print(
        "AR repair sessions:",
        len(
            repair_sessions
        ),
    )

    print(
        "Average repair steps:",
        round(
            float(
                repair_sessions[
                    "repair_steps_total"
                ]
                .mean()
            ),
            2,
        ),
    )

    print(
        "Average repair completion fraction:",
        round(
            float(
                repair_sessions[
                    "repair_completion_fraction"
                ]
                .mean()
            ),
            4,
        ),
    )

    print(
        "Fully completed repairs:",
        int(
            (
                repair_sessions[
                    "repair_steps_completed"
                ]
                ==
                repair_sessions[
                    "repair_steps_total"
                ]
            ).sum()
        ),
    )

    print(
        "Repair completed outcomes:",
        int(
            (
                repair_sessions[
                    "conversion_or_completion_outcome"
                ]
                ==
                OUTCOME_REPAIR_COMPLETED
            ).sum()
        ),
    )

    print(
        "Repair partial outcomes:",
        int(
            (
                repair_sessions[
                    "conversion_or_completion_outcome"
                ]
                ==
                OUTCOME_REPAIR_PARTIAL
            ).sum()
        ),
    )

    print(
        "Technician escalation outcomes:",
        int(
            (
                repair_sessions[
                    "conversion_or_completion_outcome"
                ]
                ==
                OUTCOME_TECHNICIAN_ESCALATED
            ).sum()
        ),
    )

    # ========================================================
    # VR TRAINING
    # ========================================================

    print(
        "\n=== XR VR TRAINING ACTIVITY ===\n"
    )

    training_sessions = (
        xr_sessions_df.loc[
            xr_sessions_df[
                "experience_type"
            ]
            ==
            VR_DEALER_SALES_TRAINING
        ]
        .copy()
    )

    print(
        "VR training sessions:",
        len(
            training_sessions
        ),
    )

    print(
        "Average training score:",
        round(
            float(
                training_sessions[
                    "training_score"
                ]
                .mean()
            ),
            2,
        ),
    )

    print(
        "Minimum training score:",
        round(
            float(
                training_sessions[
                    "training_score"
                ]
                .min()
            ),
            2,
        ),
    )

    print(
        "Maximum training score:",
        round(
            float(
                training_sessions[
                    "training_score"
                ]
                .max()
            ),
            2,
        ),
    )

    # ========================================================
    # RELATIONSHIP CHECKS
    # ========================================================

    print(
        "\n=== XR RELATIONSHIP CHECKS ===\n"
    )

    overall_assistant_correlation = (
        xr_sessions_df[
            [
                "engagement_seconds",
                "assistant_interactions",
            ]
        ]
        .corr()
        .iloc[
            0,
            1
        ]
    )

    print(
        "Correlation engagement vs assistant interactions:",
        round(
            float(
                overall_assistant_correlation
            ),
            4,
        ),
    )

    customer_relationship = (
        customer_sessions
        .copy()
    )

    customer_relationship[
        "configuration_selected_flag"
    ] = (
        customer_relationship[
            "configuration_selected"
        ]
        .notna()
        .astype(int)
    )

    customer_configuration_correlation = (
        customer_relationship[
            [
                "engagement_seconds",
                "configuration_selected_flag",
            ]
        ]
        .corr()
        .iloc[
            0,
            1
        ]
    )

    print(
        "Correlation customer engagement "
        "vs configuration selection:",
        round(
            float(
                customer_configuration_correlation
            ),
            4,
        ),
    )

    repair_engagement_correlation = (
        repair_sessions[
            [
                "engagement_seconds",
                "repair_completion_fraction",
            ]
        ]
        .corr()
        .iloc[
            0,
            1
        ]
    )

    print(
        "Correlation AR engagement "
        "vs repair completion:",
        round(
            float(
                repair_engagement_correlation
            ),
            4,
        ),
    )

    training_engagement_correlation = (
        training_sessions[
            [
                "engagement_seconds",
                "training_score",
            ]
        ]
        .corr()
        .iloc[
            0,
            1
        ]
    )

    print(
        "Correlation VR engagement "
        "vs training score:",
        round(
            float(
                training_engagement_correlation
            ),
            4,
        ),
    )

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    print(
        "\n=== XR VALIDATION ===\n"
    )

    print(
        "Experience rows:",
        len(
            xr_experiences_df
        ),
    )

    print(
        "Unique experience IDs:",
        xr_experiences_df[
            "experience_id"
        ]
        .nunique(),
    )

    print(
        "Session rows:",
        len(
            xr_sessions_df
        ),
    )

    print(
        "Unique session IDs:",
        xr_sessions_df[
            "session_id"
        ]
        .nunique(),
    )

    print(
        "Experiences represented:",
        xr_sessions_df[
            "experience_id"
        ]
        .nunique(),
    )

    print(
        "Vehicle models represented:",
        xr_sessions_df[
            "vehicle_model_id"
        ]
        .nunique(),
    )

    print(
        "Duplicate session IDs:",
        int(
            xr_sessions_df[
                "session_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Missing experience IDs:",
        int(
            xr_sessions_df[
                "experience_id"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Missing vehicle-model IDs:",
        int(
            xr_sessions_df[
                "vehicle_model_id"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Sessions completing before/equal start:",
        int(
            (
                pd.to_datetime(
                    xr_sessions_df[
                        "completed_at"
                    ],
                    utc=True,
                )
                <=
                pd.to_datetime(
                    xr_sessions_df[
                        "started_at"
                    ],
                    utc=True,
                )
            ).sum()
        ),
    )

    print(
        "Hidden truth/runtime leakage:",
        sorted(
            HIDDEN_RUNTIME_COLUMNS
            &
            set(
                xr_sessions_df.columns
            )
        ),
    )

    print(
        "\nGenerated "
        f"{len(xr_experiences_df)} "
        "synthetic XR experiences and "
        f"{len(xr_sessions_df)} "
        "synthetic XR sessions successfully."
    )