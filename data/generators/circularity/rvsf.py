"""
Synthetic RVSF Job Card Generator
for Mahindra AI Nexus.

============================================================
PURPOSE
============================================================

Generate Registered Vehicle Scrapping Facility (RVSF)
operational job-card records from validated ELV assessments.

Dependency chain:

    Geography
        +
    Vehicle Model Master
        ↓
    ELV Assessments
        ↓
    RVSF Job Cards
        ↓
    DMRV Records
        ↓
    Carbon Credit Listings


============================================================
CURRENT GENERATION MODEL
============================================================

Every ELV creates exactly two RVSF job cards:

    1. DEPOLLUTION_AND_SAFETY

       - intake / weighing
       - fluid draining
       - battery removal
       - tyre removal
       - catalytic-converter removal
       - safety preparation

    2. DISMANTLING_AND_RECOVERY

       - reusable component recovery
       - recyclable material recovery
       - residual waste separation


With:

    750 ELV assessments

the configured target is:

    1,500 RVSF job cards


============================================================
IMPORTANT ARCHITECTURAL RULE
============================================================

This generator creates OBSERVED OPERATIONAL RECORDS.

Allowed:

    recovered battery
    recovered tyres
    fluid quantity removed
    reusable-parts mass
    recyclable-material mass
    residual-waste mass
    energy consumed
    water consumed
    labor hours
    observed process timestamps
    mass balance

Not allowed:

    predicted recoverable value
    recommended disposition
    recovery probability
    carbon-credit prediction
    AI recommendation
    confidence score
    model score
    hidden synthetic truth


============================================================
ACTUAL generation.yaml STRUCTURE
============================================================

circularity:

    elv_assessments:
        count: 750

    rvsf_job_cards:
        count: 1500

    dmrv_records:
        count: 3000

    carbon_credit_listings:
        count: 750


============================================================
OUTPUT
============================================================

This module returns a DataFrame.

It DOES NOT write CSV files.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.helpers import (
    load_distribution_config,
    load_generation_config,
)

from data.generators.common.ids import generate_id

from data.generators.common.seed import (
    derive_seed,
    make_rng,
)


# ============================================================
# JOB TYPES
# ============================================================

DEPOLLUTION_JOB = "DEPOLLUTION_AND_SAFETY"

DISMANTLING_JOB = "DISMANTLING_AND_RECOVERY"

VALID_JOB_TYPES = {
    DEPOLLUTION_JOB,
    DISMANTLING_JOB,
}


# ============================================================
# STATUS
# ============================================================

JOB_STATUS_COMPLETED = "COMPLETED"

VALID_JOB_STATUSES = {
    JOB_STATUS_COMPLETED,
}


# ============================================================
# SYNTHETIC ENGINEERING ASSUMPTIONS
#
# NOT Mahindra operating statistics.
# ============================================================

BATTERY_MASS_KG_MEAN = 22.0
BATTERY_MASS_KG_STD = 3.5

TYRE_SET_MASS_KG_MEAN = 62.0
TYRE_SET_MASS_KG_STD = 7.0

CATALYTIC_CONVERTER_MASS_KG_MEAN = 6.0
CATALYTIC_CONVERTER_MASS_KG_STD = 1.2

FLUID_LITERS_PER_VEHICLE_MASS_KG = 0.0145

FLUID_DENSITY_KG_PER_LITER = 0.88


# ============================================================
# COMPONENT RECOVERY PROBABILITIES
#
# These represent observed RVSF process completion.
# ============================================================

BATTERY_RECOVERY_PROBABILITY = 0.975

TYRE_RECOVERY_PROBABILITY = 0.985

CATALYTIC_RECOVERY_PROBABILITY = 0.955

FLUID_DRAIN_PROBABILITY = 0.990


# ============================================================
# FORBIDDEN AI / GROUND-TRUTH COLUMNS
# ============================================================

HIDDEN_RUNTIME_COLUMNS = {
    "predicted_recoverable_value",
    "predicted_recoverable_value_inr",

    "recoverable_value",
    "recoverable_value_inr",

    "true_recoverable_value",
    "true_recoverable_value_inr",

    "predicted_recovery_probability",
    "recovery_probability",

    "recommended_action",
    "recommended_disposition",
    "recommended_channel",
    "recommended_dismantling_route",

    "carbon_credit_estimate",
    "estimated_carbon_credits",
    "predicted_carbon_credits",

    "credit_value",
    "credit_value_inr",

    "confidence",
    "confidence_score",

    "model_score",
    "model_probability",

    "risk_score",
    "risk_band",

    "true_recovery_rate",
    "true_disposition",
    "target_recoverable_value",
}


# ============================================================
# REQUIRED ELV SCHEMA
# ============================================================

ELV_REQUIRED_COLUMNS: set[str] = {
    "elv_assessment_id",
    "elv_vehicle_id",

    "vehicle_model_id",
    "model_name",
    "segment",

    "city_id",
    "city_name",

    "region_id",
    "region_name",

    "assessment_at",
    "assessment_status",

    "source_channel",

    "vehicle_age_years",
    "odometer_km",

    "condition_score",
    "chassis_integrity_score",
    "powertrain_condition_score",

    "engine_operable",

    "document_completeness",
    "traceability_score",
    "buyer_demand_index",

    "estimated_vehicle_mass_kg",

    "assessed_reusable_parts_pct",
    "assessed_recyclable_material_pct",

    "battery_present",
    "tyre_set_present",
    "catalytic_converter_present",
    "hazardous_fluids_present",

    "data_origin",
    "generator_version",
}


# ============================================================
# CONFIG
# ============================================================


def _get_generation_window(
    generation: Mapping[str, Any],
) -> tuple[
    pd.Timestamp,
    pd.Timestamp,
    str,
]:
    """
    Return configured timezone-aware generation boundaries.
    """

    try:
        time_config = generation["time"]

        start_value = time_config["start_date"]
        end_value = time_config["end_date"]

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
            "generation.time.end_date must be after "
            "generation.time.start_date"
        )

    return (
        start,
        end,
        timezone,
    )


def _get_rvsf_target_count(
    generation: Mapping[str, Any],
) -> int:
    """
    Read:

        circularity:
            rvsf_job_cards:
                count: 1500
    """

    try:
        target_count = int(
            generation[
                "circularity"
            ][
                "rvsf_job_cards"
            ][
                "count"
            ]
        )

    except KeyError as exc:
        raise KeyError(
            "Missing "
            "generation.circularity."
            "rvsf_job_cards.count"
        ) from exc

    if target_count <= 0:
        raise ValueError(
            "generation.circularity."
            "rvsf_job_cards.count must be > 0"
        )

    return target_count


# ============================================================
# BOOLEAN NORMALIZATION
# ============================================================


def _to_bool_series(
    series: pd.Series,
) -> pd.Series:
    """
    Normalize boolean-like input safely.
    """

    if pd.api.types.is_bool_dtype(
        series
    ):
        return (
            series
            .fillna(False)
            .astype(bool)
        )

    true_values = {
        "TRUE",
        "YES",
        "Y",
        "1",
    }

    false_values = {
        "FALSE",
        "NO",
        "N",
        "0",
    }

    def convert(
        value: Any,
    ) -> bool:
        if pd.isna(value):
            return False

        if isinstance(
            value,
            (
                bool,
                np.bool_,
            ),
        ):
            return bool(
                value
            )

        normalized = (
            str(value)
            .strip()
            .upper()
        )

        if normalized in true_values:
            return True

        if normalized in false_values:
            return False

        raise ValueError(
            "Unable to interpret boolean value: "
            f"{value!r}"
        )

    return (
        series
        .map(convert)
        .astype(bool)
    )


# ============================================================
# PREPARE ELV
# ============================================================


def _prepare_elv_assessments(
    elv_assessments: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate the frozen ELV dataset before RVSF generation.
    """

    if elv_assessments.empty:
        raise ValueError(
            "ELV assessments DataFrame cannot be empty"
        )

    missing_columns = (
        ELV_REQUIRED_COLUMNS
        -
        set(
            elv_assessments.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "ELV assessments missing columns: "
            +
            ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    result = (
        elv_assessments
        .copy(
            deep=True
        )
    )

    # ========================================================
    # PRIMARY IDENTIFIERS
    # ========================================================

    for column in (
        "elv_assessment_id",
        "elv_vehicle_id",
        "vehicle_model_id",
        "city_id",
        "region_id",
    ):
        if (
            result[
                column
            ]
            .isna()
            .any()
        ):
            raise ValueError(
                f"ELV assessments contain missing {column}"
            )

    if (
        result[
            "elv_assessment_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate elv_assessment_id values found"
        )

    if (
        result[
            "elv_vehicle_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate elv_vehicle_id values found"
        )

    # ========================================================
    # COMPLETED ELV ASSESSMENTS ONLY
    # ========================================================

    if (
        set(
            result[
                "assessment_status"
            ]
            .astype(str)
        )
        !=
        {
            "COMPLETED"
        }
    ):
        raise ValueError(
            "RVSF generation requires completed "
            "ELV assessments"
        )

    # ========================================================
    # NUMERIC FIELDS
    # ========================================================

    numeric_columns = (
        "vehicle_age_years",
        "odometer_km",

        "condition_score",
        "chassis_integrity_score",
        "powertrain_condition_score",

        "document_completeness",
        "traceability_score",
        "buyer_demand_index",

        "estimated_vehicle_mass_kg",

        "assessed_reusable_parts_pct",
        "assessed_recyclable_material_pct",
    )

    for column in numeric_columns:
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
            "estimated_vehicle_mass_kg"
        ]
        <= 0
    ).any():
        raise ValueError(
            "estimated_vehicle_mass_kg must be positive"
        )

    for column in (
        "document_completeness",
        "traceability_score",
        "buyer_demand_index",
        "assessed_reusable_parts_pct",
        "assessed_recyclable_material_pct",
    ):
        values = result[
            column
        ]

        if (
            (values < 0)
            |
            (values > 1)
        ).any():
            raise ValueError(
                f"{column} must be between 0 and 1"
            )

    # ========================================================
    # BOOLEAN FIELDS
    # ========================================================

    boolean_columns = (
        "engine_operable",

        "battery_present",
        "tyre_set_present",
        "catalytic_converter_present",
        "hazardous_fluids_present",
    )

    for column in boolean_columns:
        result[
            column
        ] = (
            _to_bool_series(
                result[
                    column
                ]
            )
        )

    # ========================================================
    # ASSESSMENT TIMESTAMP
    # ========================================================

    result[
        "assessment_at"
    ] = pd.to_datetime(
        result[
            "assessment_at"
        ],
        utc=True,
    )

    return (
        result
        .sort_values(
            [
                "assessment_at",
                "elv_assessment_id",
            ]
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# FACILITY ID
# ============================================================


def _facility_id(
    city_id: str,
) -> str:
    """
    Deterministic synthetic RVSF site identifier.

    The fixed project structure has no separate RVSF-facility
    master generator, so facility identity is derived from the
    existing city master identifier.
    """

    suffix = (
        str(city_id)
        .replace(
            "CITY_",
            "",
        )
        .replace(
            " ",
            "_",
        )
        .upper()
    )

    return (
        f"RVSF_SYN_{suffix}"
    )


def _facility_name(
    city_name: str,
) -> str:
    """
    Deterministic synthetic facility display name.
    """

    return (
        f"{city_name} RVSF Facility"
    )


# ============================================================
# TWO-JOB TIMELINE
# ============================================================


def _build_job_timeline(
    rng: np.random.Generator,
    assessment_at: pd.Timestamp,
    generation_end: pd.Timestamp,
) -> tuple[
    pd.Timestamp,
    pd.Timestamp,
    pd.Timestamp,
    pd.Timestamp,
    pd.Timestamp,
    pd.Timestamp,
]:
    """
    Create sequential RVSF timestamps:

        assessment
            <
        job1_open
            <=
        job1_start
            <
        job1_complete
            <
        job2_open
            <=
        job2_start
            <
        job2_complete
            <
        generation_end


    Near the generation cutoff, normal process durations are
    proportionally compressed so historical records remain
    temporally valid instead of being dropped.
    """

    assessment_utc = pd.Timestamp(
        assessment_at
    )

    end_utc = pd.Timestamp(
        generation_end
    )

    remaining_seconds = (
        end_utc
        -
        assessment_utc
    ).total_seconds()

    if remaining_seconds <= 0:
        raise ValueError(
            "ELV assessment must occur before generation end"
        )

    # Preferred operating gaps in hours:
    #
    # assessment -> job1 opened
    # job1 opened -> job1 start
    # job1 processing duration
    # job1 complete -> job2 opened
    # job2 opened -> job2 start
    # job2 processing duration

    preferred_hours = np.asarray(
        [
            rng.uniform(
                2.0,
                30.0,
            ),

            rng.uniform(
                0.25,
                5.0,
            ),

            rng.uniform(
                1.5,
                5.5,
            ),

            rng.uniform(
                1.0,
                18.0,
            ),

            rng.uniform(
                0.25,
                6.0,
            ),

            rng.uniform(
                3.0,
                11.0,
            ),
        ],
        dtype=float,
    )

    preferred_seconds = (
        preferred_hours
        *
        3600.0
    )

    total_preferred_seconds = float(
        preferred_seconds.sum()
    )

    # Leave at least 10% of remaining historical window after
    # the second job whenever compression is needed.
    usable_seconds = (
        remaining_seconds
        *
        0.90
    )

    if (
        total_preferred_seconds
        >
        usable_seconds
    ):
        scale = (
            usable_seconds
            /
            total_preferred_seconds
        )

        preferred_seconds = (
            preferred_seconds
            *
            scale
        )

    timestamps: list[
        pd.Timestamp
    ] = []

    current = assessment_utc

    for seconds in preferred_seconds:
        current = (
            current
            +
            pd.Timedelta(
                seconds=float(
                    seconds
                )
            )
        )

        timestamps.append(
            current
        )

    (
        job1_opened_at,
        job1_started_at,
        job1_completed_at,

        job2_opened_at,
        job2_started_at,
        job2_completed_at,
    ) = timestamps

    if not (
        assessment_utc
        <
        job1_opened_at
        <=
        job1_started_at
        <
        job1_completed_at
        <
        job2_opened_at
        <=
        job2_started_at
        <
        job2_completed_at
        <
        end_utc
    ):
        raise ValueError(
            "Generated invalid RVSF job timeline"
        )

    return (
        job1_opened_at,
        job1_started_at,
        job1_completed_at,

        job2_opened_at,
        job2_started_at,
        job2_completed_at,
    )


# ============================================================
# COMPONENT MASS
# ============================================================


def _sample_positive_mass(
    rng: np.random.Generator,
    mean: float,
    std: float,
    minimum: float,
    maximum: float,
) -> float:
    """
    Sample bounded positive component mass.
    """

    value = float(
        rng.normal(
            loc=mean,
            scale=std,
        )
    )

    return float(
        np.clip(
            value,
            minimum,
            maximum,
        )
    )


# ============================================================
# ROUNDING / MASS BALANCE
# ============================================================


def _round_mass(
    value: float,
) -> float:
    return round(
        max(
            0.0,
            float(value),
        ),
        2,
    )


# ============================================================
# GENERATOR
# ============================================================


def generate_rvsf_job_cards(
    elv_assessments: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate RVSF operational job cards from ELV assessments.
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    # ========================================================
    # CONFIG
    # ========================================================

    (
        generation_start,
        generation_end,
        timezone,
    ) = (
        _get_generation_window(
            generation
        )
    )

    target_count = (
        _get_rvsf_target_count(
            generation
        )
    )

    # ========================================================
    # PREPARE ELV
    # ========================================================

    elv = (
        _prepare_elv_assessments(
            elv_assessments
        )
    )

    # ========================================================
    # TWO JOBS PER ELV
    # ========================================================

    expected_count = (
        len(elv)
        *
        2
    )

    if (
        target_count
        !=
        expected_count
    ):
        raise ValueError(
            "RVSF configured target does not match "
            "the two-job ELV processing model. "
            f"ELVs={len(elv)}, "
            f"required_job_cards={expected_count}, "
            f"configured_target={target_count}"
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
            "circularity.rvsf",
        )
    )

    # ========================================================
    # PROVENANCE
    # ========================================================

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

    rows: list[
        dict[str, Any]
    ] = []

    # ========================================================
    # GENERATE TWO JOBS PER ELV
    # ========================================================

    job_counter = 0

    for record in elv.itertuples(
        index=False
    ):
        vehicle_mass_kg = float(
            record.estimated_vehicle_mass_kg
        )

        facility_id = (
            _facility_id(
                record.city_id
            )
        )

        facility_name = (
            _facility_name(
                record.city_name
            )
        )

        # ====================================================
        # TIMELINE
        # ====================================================

        (
            job1_opened_at,
            job1_started_at,
            job1_completed_at,

            job2_opened_at,
            job2_started_at,
            job2_completed_at,
        ) = (
            _build_job_timeline(
                rng=rng,

                assessment_at=
                    pd.Timestamp(
                        record.assessment_at
                    ),

                generation_end=
                    generation_end
                    .tz_convert(
                        "UTC"
                    ),
            )
        )

        # ====================================================
        # JOB 1:
        # DEPOLLUTION AND SAFETY
        # ====================================================

        battery_recovered = bool(
            record.battery_present
            and
            (
                rng.random()
                <
                BATTERY_RECOVERY_PROBABILITY
            )
        )

        tyre_set_recovered = bool(
            record.tyre_set_present
            and
            (
                rng.random()
                <
                TYRE_RECOVERY_PROBABILITY
            )
        )

        catalytic_converter_recovered = bool(
            record.catalytic_converter_present
            and
            (
                rng.random()
                <
                CATALYTIC_RECOVERY_PROBABILITY
            )
        )

        fluid_drain_completed = bool(
            record.hazardous_fluids_present
            and
            (
                rng.random()
                <
                FLUID_DRAIN_PROBABILITY
            )
        )

        # ----------------------------------------------------
        # Component masses
        # ----------------------------------------------------

        battery_mass_kg = (
            _sample_positive_mass(
                rng=rng,

                mean=
                    BATTERY_MASS_KG_MEAN,

                std=
                    BATTERY_MASS_KG_STD,

                minimum=
                    12.0,

                maximum=
                    35.0,
            )

            if battery_recovered

            else 0.0
        )

        tyre_mass_kg = (
            _sample_positive_mass(
                rng=rng,

                mean=
                    TYRE_SET_MASS_KG_MEAN,

                std=
                    TYRE_SET_MASS_KG_STD,

                minimum=
                    40.0,

                maximum=
                    85.0,
            )

            if tyre_set_recovered

            else 0.0
        )

        catalytic_mass_kg = (
            _sample_positive_mass(
                rng=rng,

                mean=
                    CATALYTIC_CONVERTER_MASS_KG_MEAN,

                std=
                    CATALYTIC_CONVERTER_MASS_KG_STD,

                minimum=
                    2.5,

                maximum=
                    10.0,
            )

            if catalytic_converter_recovered

            else 0.0
        )

        # ----------------------------------------------------
        # Hazardous fluids
        # ----------------------------------------------------

        expected_fluid_liters = (
            vehicle_mass_kg
            *
            FLUID_LITERS_PER_VEHICLE_MASS_KG
        )

        hazardous_fluid_liters = (
            float(
                np.clip(
                    rng.normal(
                        loc=
                            expected_fluid_liters,

                        scale=
                            max(
                                2.0,
                                expected_fluid_liters
                                *
                                0.12,
                            ),
                    ),
                    8.0,
                    45.0,
                )
            )

            if fluid_drain_completed

            else 0.0
        )

        hazardous_fluid_mass_kg = (
            hazardous_fluid_liters
            *
            FLUID_DENSITY_KG_PER_LITER
        )

        # ----------------------------------------------------
        # Rounded depollution mass
        # ----------------------------------------------------

        battery_mass_kg = (
            _round_mass(
                battery_mass_kg
            )
        )

        tyre_mass_kg = (
            _round_mass(
                tyre_mass_kg
            )
        )

        catalytic_mass_kg = (
            _round_mass(
                catalytic_mass_kg
            )
        )

        hazardous_fluid_liters = round(
            hazardous_fluid_liters,
            2,
        )

        hazardous_fluid_mass_kg = (
            _round_mass(
                hazardous_fluid_mass_kg
            )
        )

        removed_component_mass_kg = (
            _round_mass(
                battery_mass_kg
                +
                tyre_mass_kg
                +
                catalytic_mass_kg
            )
        )

        stage1_input_mass_kg = (
            _round_mass(
                vehicle_mass_kg
            )
        )

        transferred_mass_kg = (
            _round_mass(
                stage1_input_mass_kg
                -
                removed_component_mass_kg
                -
                hazardous_fluid_mass_kg
            )
        )

        if transferred_mass_kg <= 0:
            raise ValueError(
                f"{record.elv_assessment_id}: "
                "depollution removed more mass "
                "than vehicle input mass"
            )

        # ----------------------------------------------------
        # Process resource consumption
        # ----------------------------------------------------

        job1_duration_minutes = (
            (
                job1_completed_at
                -
                job1_started_at
            )
            .total_seconds()
            /
            60.0
        )

        labor_hours_job1 = float(
            np.clip(
                (
                    1.1
                    +
                    stage1_input_mass_kg
                    /
                    1800.0
                    *
                    1.5
                    +
                    float(
                        rng.normal(
                            0.0,
                            0.35,
                        )
                    )
                ),
                1.0,
                5.5,
            )
        )

        energy_kwh_job1 = float(
            np.clip(
                7.0
                +
                stage1_input_mass_kg
                *
                0.006
                +
                float(
                    rng.normal(
                        0.0,
                        2.0,
                    )
                ),
                6.0,
                35.0,
            )
        )

        water_liters_job1 = float(
            np.clip(
                12.0
                +
                stage1_input_mass_kg
                *
                0.012
                +
                float(
                    rng.normal(
                        0.0,
                        7.0,
                    )
                ),
                5.0,
                80.0,
            )
        )

        qc_probability_job1 = float(
            np.clip(
                0.88
                +
                0.07
                *
                float(
                    record.traceability_score
                )
                +
                0.04
                *
                float(
                    record.document_completeness
                ),
                0.88,
                0.995,
            )
        )

        quality_check_job1 = bool(
            rng.random()
            <
            qc_probability_job1
        )

        job_counter += 1

        rows.append(
            {
                "rvsf_job_card_id":
                    generate_id(
                        "RVSFJOB_SYN",
                        job_counter,
                        width=7,
                    ),

                "elv_assessment_id":
                    str(
                        record.elv_assessment_id
                    ),

                "elv_vehicle_id":
                    str(
                        record.elv_vehicle_id
                    ),

                "job_sequence":
                    1,

                "job_type":
                    DEPOLLUTION_JOB,

                # --------------------------------------------
                # Vehicle
                # --------------------------------------------

                "vehicle_model_id":
                    str(
                        record.vehicle_model_id
                    ),

                "model_name":
                    str(
                        record.model_name
                    ),

                "segment":
                    str(
                        record.segment
                    ),

                "vehicle_age_years":
                    int(
                        record.vehicle_age_years
                    ),

                "condition_score":
                    round(
                        float(
                            record.condition_score
                        ),
                        2,
                    ),

                # --------------------------------------------
                # Facility / geography
                # --------------------------------------------

                "rvsf_facility_id":
                    facility_id,

                "rvsf_facility_name":
                    facility_name,

                "city_id":
                    str(
                        record.city_id
                    ),

                "city_name":
                    str(
                        record.city_name
                    ),

                "region_id":
                    str(
                        record.region_id
                    ),

                "region_name":
                    str(
                        record.region_name
                    ),

                "intake_source_channel":
                    str(
                        record.source_channel
                    ),

                # --------------------------------------------
                # Timeline
                # --------------------------------------------

                "job_opened_at":
                    job1_opened_at
                    .tz_convert(
                        timezone
                    ),

                "processing_started_at":
                    job1_started_at
                    .tz_convert(
                        timezone
                    ),

                "processing_completed_at":
                    job1_completed_at
                    .tz_convert(
                        timezone
                    ),

                "processing_duration_minutes":
                    round(
                        job1_duration_minutes,
                        3,
                    ),

                # --------------------------------------------
                # Mass flow
                # --------------------------------------------

                "stage_input_mass_kg":
                    stage1_input_mass_kg,

                "battery_recovered":
                    battery_recovered,

                "battery_recovered_mass_kg":
                    battery_mass_kg,

                "tyre_set_recovered":
                    tyre_set_recovered,

                "tyre_recovered_mass_kg":
                    tyre_mass_kg,

                "catalytic_converter_recovered":
                    catalytic_converter_recovered,

                "catalytic_converter_mass_kg":
                    catalytic_mass_kg,

                "fluid_drain_completed":
                    fluid_drain_completed,

                "hazardous_fluid_liters":
                    hazardous_fluid_liters,

                "hazardous_fluid_mass_kg":
                    hazardous_fluid_mass_kg,

                "removed_component_mass_kg":
                    removed_component_mass_kg,

                "reusable_parts_mass_kg":
                    0.0,

                "recyclable_material_mass_kg":
                    0.0,

                "residual_waste_mass_kg":
                    0.0,

                "transferred_to_next_stage_kg":
                    transferred_mass_kg,

                # --------------------------------------------
                # Operating evidence
                # --------------------------------------------

                "labor_hours":
                    round(
                        labor_hours_job1,
                        3,
                    ),

                "energy_consumed_kwh":
                    round(
                        energy_kwh_job1,
                        3,
                    ),

                "water_consumed_liters":
                    round(
                        water_liters_job1,
                        3,
                    ),

                "quality_check_passed":
                    quality_check_job1,

                "weighbridge_ticket_id":
                    generate_id(
                        "WB_SYN",
                        job_counter,
                        width=8,
                    ),

                "job_status":
                    JOB_STATUS_COMPLETED,

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

        # ====================================================
        # JOB 2:
        # DISMANTLING / MATERIAL RECOVERY
        # ====================================================

        stage2_input_mass_kg = (
            transferred_mass_kg
        )

        # ----------------------------------------------------
        # Reusable component recovery
        #
        # Based on observed ELV inspection evidence with
        # process-efficiency noise.
        # ----------------------------------------------------

        reusable_efficiency = float(
            np.clip(
                rng.normal(
                    loc=0.96,
                    scale=0.045,
                ),
                0.82,
                1.05,
            )
        )

        reusable_fraction = float(
            np.clip(
                float(
                    record.assessed_reusable_parts_pct
                )
                *
                reusable_efficiency,
                0.02,
                0.72,
            )
        )

        # Better-operating powertrains modestly improve usable
        # component recovery.
        if bool(
            record.engine_operable
        ):
            reusable_fraction = float(
                np.clip(
                    reusable_fraction
                    +
                    0.025,
                    0.02,
                    0.72,
                )
            )

        reusable_parts_mass_kg = (
            _round_mass(
                stage2_input_mass_kg
                *
                reusable_fraction
            )
        )

        remaining_after_reuse_kg = max(
            0.0,
            stage2_input_mass_kg
            -
            reusable_parts_mass_kg,
        )

        # ----------------------------------------------------
        # Recycling recovery
        #
        # ELV recyclable-material percentage represents
        # recyclable share AFTER reusable parts are removed.
        # ----------------------------------------------------

        recycling_efficiency = float(
            np.clip(
                rng.normal(
                    loc=0.965,
                    scale=0.025,
                ),
                0.86,
                1.00,
            )
        )

        recyclable_fraction = float(
            np.clip(
                float(
                    record.assessed_recyclable_material_pct
                )
                *
                recycling_efficiency,
                0.55,
                0.95,
            )
        )

        recyclable_material_mass_kg = (
            _round_mass(
                remaining_after_reuse_kg
                *
                recyclable_fraction
            )
        )

        residual_waste_mass_kg = (
            _round_mass(
                stage2_input_mass_kg
                -
                reusable_parts_mass_kg
                -
                recyclable_material_mass_kg
            )
        )

        # Correct rounding edge case explicitly.
        stage2_mass_difference = round(
            stage2_input_mass_kg
            -
            (
                reusable_parts_mass_kg
                +
                recyclable_material_mass_kg
                +
                residual_waste_mass_kg
            ),
            2,
        )

        if (
            abs(
                stage2_mass_difference
            )
            >=
            0.01
        ):
            residual_waste_mass_kg = (
                _round_mass(
                    residual_waste_mass_kg
                    +
                    stage2_mass_difference
                )
            )

        # ----------------------------------------------------
        # Resource usage
        # ----------------------------------------------------

        job2_duration_minutes = (
            (
                job2_completed_at
                -
                job2_started_at
            )
            .total_seconds()
            /
            60.0
        )

        condition_pressure = (
            1.0
            -
            float(
                record.condition_score
            )
            /
            100.0
        )

        labor_hours_job2 = float(
            np.clip(
                3.0
                +
                stage2_input_mass_kg
                /
                500.0
                +
                2.0
                *
                condition_pressure
                +
                float(
                    rng.normal(
                        0.0,
                        0.6,
                    )
                ),
                3.0,
                13.0,
            )
        )

        energy_kwh_job2 = float(
            np.clip(
                18.0
                +
                stage2_input_mass_kg
                *
                0.022
                +
                6.0
                *
                condition_pressure
                +
                float(
                    rng.normal(
                        0.0,
                        4.0,
                    )
                ),
                20.0,
                90.0,
            )
        )

        water_liters_job2 = float(
            np.clip(
                10.0
                +
                stage2_input_mass_kg
                *
                0.008
                +
                float(
                    rng.normal(
                        0.0,
                        6.0,
                    )
                ),
                5.0,
                65.0,
            )
        )

        qc_probability_job2 = float(
            np.clip(
                0.90
                +
                0.055
                *
                float(
                    record.traceability_score
                )
                +
                0.025
                *
                float(
                    record.document_completeness
                ),
                0.90,
                0.995,
            )
        )

        quality_check_job2 = bool(
            rng.random()
            <
            qc_probability_job2
        )

        job_counter += 1

        rows.append(
            {
                "rvsf_job_card_id":
                    generate_id(
                        "RVSFJOB_SYN",
                        job_counter,
                        width=7,
                    ),

                "elv_assessment_id":
                    str(
                        record.elv_assessment_id
                    ),

                "elv_vehicle_id":
                    str(
                        record.elv_vehicle_id
                    ),

                "job_sequence":
                    2,

                "job_type":
                    DISMANTLING_JOB,

                # --------------------------------------------
                # Vehicle
                # --------------------------------------------

                "vehicle_model_id":
                    str(
                        record.vehicle_model_id
                    ),

                "model_name":
                    str(
                        record.model_name
                    ),

                "segment":
                    str(
                        record.segment
                    ),

                "vehicle_age_years":
                    int(
                        record.vehicle_age_years
                    ),

                "condition_score":
                    round(
                        float(
                            record.condition_score
                        ),
                        2,
                    ),

                # --------------------------------------------
                # Facility
                # --------------------------------------------

                "rvsf_facility_id":
                    facility_id,

                "rvsf_facility_name":
                    facility_name,

                "city_id":
                    str(
                        record.city_id
                    ),

                "city_name":
                    str(
                        record.city_name
                    ),

                "region_id":
                    str(
                        record.region_id
                    ),

                "region_name":
                    str(
                        record.region_name
                    ),

                "intake_source_channel":
                    str(
                        record.source_channel
                    ),

                # --------------------------------------------
                # Timeline
                # --------------------------------------------

                "job_opened_at":
                    job2_opened_at
                    .tz_convert(
                        timezone
                    ),

                "processing_started_at":
                    job2_started_at
                    .tz_convert(
                        timezone
                    ),

                "processing_completed_at":
                    job2_completed_at
                    .tz_convert(
                        timezone
                    ),

                "processing_duration_minutes":
                    round(
                        job2_duration_minutes,
                        3,
                    ),

                # --------------------------------------------
                # Mass flow
                # --------------------------------------------

                "stage_input_mass_kg":
                    stage2_input_mass_kg,

                "battery_recovered":
                    False,

                "battery_recovered_mass_kg":
                    0.0,

                "tyre_set_recovered":
                    False,

                "tyre_recovered_mass_kg":
                    0.0,

                "catalytic_converter_recovered":
                    False,

                "catalytic_converter_mass_kg":
                    0.0,

                "fluid_drain_completed":
                    False,

                "hazardous_fluid_liters":
                    0.0,

                "hazardous_fluid_mass_kg":
                    0.0,

                "removed_component_mass_kg":
                    0.0,

                "reusable_parts_mass_kg":
                    reusable_parts_mass_kg,

                "recyclable_material_mass_kg":
                    recyclable_material_mass_kg,

                "residual_waste_mass_kg":
                    residual_waste_mass_kg,

                "transferred_to_next_stage_kg":
                    0.0,

                # --------------------------------------------
                # Operating evidence
                # --------------------------------------------

                "labor_hours":
                    round(
                        labor_hours_job2,
                        3,
                    ),

                "energy_consumed_kwh":
                    round(
                        energy_kwh_job2,
                        3,
                    ),

                "water_consumed_liters":
                    round(
                        water_liters_job2,
                        3,
                    ),

                "quality_check_passed":
                    quality_check_job2,

                "weighbridge_ticket_id":
                    generate_id(
                        "WB_SYN",
                        job_counter,
                        width=8,
                    ),

                "job_status":
                    JOB_STATUS_COMPLETED,

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    rvsf = pd.DataFrame(
        rows
    )

    # ========================================================
    # FINAL COLUMN ORDER
    # ========================================================

    output_columns = [
        "rvsf_job_card_id",

        "elv_assessment_id",
        "elv_vehicle_id",

        "job_sequence",
        "job_type",

        "vehicle_model_id",
        "model_name",
        "segment",

        "vehicle_age_years",
        "condition_score",

        "rvsf_facility_id",
        "rvsf_facility_name",

        "city_id",
        "city_name",

        "region_id",
        "region_name",

        "intake_source_channel",

        "job_opened_at",
        "processing_started_at",
        "processing_completed_at",

        "processing_duration_minutes",

        "stage_input_mass_kg",

        "battery_recovered",
        "battery_recovered_mass_kg",

        "tyre_set_recovered",
        "tyre_recovered_mass_kg",

        "catalytic_converter_recovered",
        "catalytic_converter_mass_kg",

        "fluid_drain_completed",

        "hazardous_fluid_liters",
        "hazardous_fluid_mass_kg",

        "removed_component_mass_kg",

        "reusable_parts_mass_kg",
        "recyclable_material_mass_kg",
        "residual_waste_mass_kg",

        "transferred_to_next_stage_kg",

        "labor_hours",
        "energy_consumed_kwh",
        "water_consumed_liters",

        "quality_check_passed",

        "weighbridge_ticket_id",

        "job_status",

        "data_origin",
        "generator_version",
    ]

    rvsf = (
        rvsf[
            output_columns
        ]
        .copy()
    )

    # ========================================================
    # VALIDATE
    # ========================================================

    validate_rvsf_job_cards(
        rvsf=rvsf,

        elv_assessments=elv,

        generation_start=generation_start,

        generation_end=generation_end,

        expected_count=target_count,
    )

    return rvsf


# ============================================================
# VALIDATION
# ============================================================


def validate_rvsf_job_cards(
    rvsf: pd.DataFrame,
    elv_assessments: pd.DataFrame,
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
    expected_count: int,
) -> None:
    """
    Validate RVSF operational integrity.
    """

    required_columns = {
        "rvsf_job_card_id",

        "elv_assessment_id",
        "elv_vehicle_id",

        "job_sequence",
        "job_type",

        "vehicle_model_id",
        "model_name",
        "segment",

        "vehicle_age_years",
        "condition_score",

        "rvsf_facility_id",
        "rvsf_facility_name",

        "city_id",
        "city_name",

        "region_id",
        "region_name",

        "intake_source_channel",

        "job_opened_at",
        "processing_started_at",
        "processing_completed_at",

        "processing_duration_minutes",

        "stage_input_mass_kg",

        "battery_recovered",
        "battery_recovered_mass_kg",

        "tyre_set_recovered",
        "tyre_recovered_mass_kg",

        "catalytic_converter_recovered",
        "catalytic_converter_mass_kg",

        "fluid_drain_completed",

        "hazardous_fluid_liters",
        "hazardous_fluid_mass_kg",

        "removed_component_mass_kg",

        "reusable_parts_mass_kg",
        "recyclable_material_mass_kg",
        "residual_waste_mass_kg",

        "transferred_to_next_stage_kg",

        "labor_hours",
        "energy_consumed_kwh",
        "water_consumed_liters",

        "quality_check_passed",

        "weighbridge_ticket_id",

        "job_status",

        "data_origin",
        "generator_version",
    }

    missing_columns = (
        required_columns
        -
        set(
            rvsf.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "RVSF job cards missing columns: "
            +
            ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if rvsf.empty:
        raise ValueError(
            "RVSF generator produced zero rows"
        )

    # ========================================================
    # EXACT COUNT
    # ========================================================

    if (
        len(rvsf)
        !=
        expected_count
    ):
        raise ValueError(
            "Unexpected RVSF job-card count. "
            f"Expected={expected_count}, "
            f"actual={len(rvsf)}"
        )

    # ========================================================
    # PK
    # ========================================================

    if (
        rvsf[
            "rvsf_job_card_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "RVSF job cards contain missing IDs"
        )

    if (
        rvsf[
            "rvsf_job_card_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate rvsf_job_card_id values found"
        )

    if (
        rvsf[
            "weighbridge_ticket_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate weighbridge_ticket_id values found"
        )

    # ========================================================
    # ELV FK
    # ========================================================

    valid_elv_ids = set(
        elv_assessments[
            "elv_assessment_id"
        ]
        .astype(str)
    )

    job_elv_ids = set(
        rvsf[
            "elv_assessment_id"
        ]
        .astype(str)
    )

    invalid_elv_ids = (
        job_elv_ids
        -
        valid_elv_ids
    )

    if invalid_elv_ids:
        raise ValueError(
            "RVSF job cards reference invalid ELV assessments"
        )

    if (
        job_elv_ids
        !=
        valid_elv_ids
    ):
        raise ValueError(
            "Not every ELV assessment is represented "
            "in RVSF job cards"
        )

    # ========================================================
    # EXACTLY TWO JOBS PER ELV
    # ========================================================

    jobs_per_elv = (
        rvsf
        .groupby(
            "elv_assessment_id"
        )
        .size()
    )

    if (
        jobs_per_elv
        !=
        2
    ).any():
        raise ValueError(
            "Every ELV must have exactly two RVSF job cards"
        )

    # ========================================================
    # EXACT JOB PAIR
    # ========================================================

    job_type_counts = (
        rvsf
        .groupby(
            [
                "elv_assessment_id",
                "job_type",
            ]
        )
        .size()
        .unstack(
            fill_value=0
        )
    )

    for job_type in VALID_JOB_TYPES:
        if (
            job_type
            not in job_type_counts.columns
        ):
            raise ValueError(
                "RVSF dataset missing job type: "
                f"{job_type}"
            )

        if (
            job_type_counts[
                job_type
            ]
            !=
            1
        ).any():
            raise ValueError(
                "Every ELV must have exactly one "
                f"{job_type}"
            )

    # ========================================================
    # SEQUENCE
    # ========================================================

    depollution_mask = (
        rvsf[
            "job_type"
        ]
        ==
        DEPOLLUTION_JOB
    )

    dismantling_mask = (
        rvsf[
            "job_type"
        ]
        ==
        DISMANTLING_JOB
    )

    if (
        rvsf.loc[
            depollution_mask,
            "job_sequence",
        ]
        !=
        1
    ).any():
        raise ValueError(
            "DEPOLLUTION_AND_SAFETY must have job_sequence=1"
        )

    if (
        rvsf.loc[
            dismantling_mask,
            "job_sequence",
        ]
        !=
        2
    ).any():
        raise ValueError(
            "DISMANTLING_AND_RECOVERY must have "
            "job_sequence=2"
        )

    # ========================================================
    # ELV METADATA CONSISTENCY
    # ========================================================

    elv_lookup = (
        elv_assessments
        .set_index(
            "elv_assessment_id"
        )
    )

    for job in rvsf.itertuples(
        index=False
    ):
        elv_record = elv_lookup.loc[
            str(
                job.elv_assessment_id
            )
        ]

        consistency_checks = {
            "elv_vehicle_id":
                elv_record[
                    "elv_vehicle_id"
                ],

            "vehicle_model_id":
                elv_record[
                    "vehicle_model_id"
                ],

            "model_name":
                elv_record[
                    "model_name"
                ],

            "segment":
                elv_record[
                    "segment"
                ],

            "city_id":
                elv_record[
                    "city_id"
                ],

            "city_name":
                elv_record[
                    "city_name"
                ],

            "region_id":
                elv_record[
                    "region_id"
                ],

            "region_name":
                elv_record[
                    "region_name"
                ],

            "intake_source_channel":
                elv_record[
                    "source_channel"
                ],
        }

        for (
            column,
            expected_value,
        ) in consistency_checks.items():

            actual_value = getattr(
                job,
                column,
            )

            if (
                str(
                    actual_value
                )
                !=
                str(
                    expected_value
                )
            ):
                raise ValueError(
                    f"{job.rvsf_job_card_id}: "
                    f"{column} inconsistent with ELV"
                )

    # ========================================================
    # TIMELINE
    # ========================================================

    opened = pd.to_datetime(
        rvsf[
            "job_opened_at"
        ],
        utc=True,
    )

    started = pd.to_datetime(
        rvsf[
            "processing_started_at"
        ],
        utc=True,
    )

    completed = pd.to_datetime(
        rvsf[
            "processing_completed_at"
        ],
        utc=True,
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

    if (
        opened
        <
        generation_start_utc
    ).any():
        raise ValueError(
            "RVSF job opened before generation start"
        )

    if (
        started
        <
        opened
    ).any():
        raise ValueError(
            "RVSF processing cannot start before job opening"
        )

    if (
        completed
        <=
        started
    ).any():
        raise ValueError(
            "RVSF completion must occur after process start"
        )

    if (
        completed
        >=
        generation_end_utc
    ).any():
        raise ValueError(
            "RVSF job completed on/after generation cutoff"
        )

    # ========================================================
    # ASSESSMENT MUST PRECEDE JOB 1
    # ========================================================

    assessment_lookup = (
        elv_assessments
        .set_index(
            "elv_assessment_id"
        )[
            "assessment_at"
        ]
    )

    depollution_jobs = (
        rvsf.loc[
            depollution_mask
        ]
        .copy()
    )

    depollution_assessment_times = (
        depollution_jobs[
            "elv_assessment_id"
        ]
        .map(
            assessment_lookup
        )
    )

    depollution_assessment_times = pd.to_datetime(
        depollution_assessment_times,
        utc=True,
    )

    depollution_opened = pd.to_datetime(
        depollution_jobs[
            "job_opened_at"
        ],
        utc=True,
    )

    if (
        depollution_opened
        <=
        depollution_assessment_times
    ).any():
        raise ValueError(
            "RVSF job must open after ELV assessment"
        )

    # ========================================================
    # JOB 1 MUST PRECEDE JOB 2
    # ========================================================

    job_times = (
        rvsf
        .pivot(
            index="elv_assessment_id",
            columns="job_sequence",
            values=[
                "job_opened_at",
                "processing_completed_at",
            ],
        )
    )

    job1_completed = pd.to_datetime(
        job_times[
            "processing_completed_at"
        ][
            1
        ],
        utc=True,
    )

    job2_opened = pd.to_datetime(
        job_times[
            "job_opened_at"
        ][
            2
        ],
        utc=True,
    )

    if (
        job2_opened
        <=
        job1_completed
    ).any():
        raise ValueError(
            "RVSF job 2 must open after job 1 completes"
        )

    # ========================================================
    # PROCESSING DURATION
    # ========================================================

    calculated_duration = (
        (
            completed
            -
            started
        )
        .dt
        .total_seconds()
        /
        60.0
    )

    stored_duration = pd.to_numeric(
        rvsf[
            "processing_duration_minutes"
        ],
        errors="raise",
    )

    if not np.allclose(
        calculated_duration.to_numpy(
            dtype=float
        ),
        stored_duration.to_numpy(
            dtype=float
        ),
        atol=0.02,
    ):
        raise ValueError(
            "processing_duration_minutes inconsistent "
            "with timestamps"
        )

    # ========================================================
    # NONNEGATIVE OPERATIONAL METRICS
    # ========================================================

    nonnegative_columns = (
        "stage_input_mass_kg",

        "battery_recovered_mass_kg",
        "tyre_recovered_mass_kg",
        "catalytic_converter_mass_kg",

        "hazardous_fluid_liters",
        "hazardous_fluid_mass_kg",

        "removed_component_mass_kg",

        "reusable_parts_mass_kg",
        "recyclable_material_mass_kg",
        "residual_waste_mass_kg",

        "transferred_to_next_stage_kg",

        "labor_hours",
        "energy_consumed_kwh",
        "water_consumed_liters",
    )

    for column in nonnegative_columns:
        values = pd.to_numeric(
            rvsf[
                column
            ],
            errors="raise",
        )

        if (
            values
            <
            0
        ).any():
            raise ValueError(
                f"{column} cannot be negative"
            )

    if (
        rvsf[
            "stage_input_mass_kg"
        ]
        <=
        0
    ).any():
        raise ValueError(
            "stage_input_mass_kg must be positive"
        )

    # ========================================================
    # JOB 1 MASS BALANCE
    # ========================================================

    depollution = (
        rvsf.loc[
            depollution_mask
        ]
        .copy()
    )

    depollution_accounted_mass = (
        depollution[
            "removed_component_mass_kg"
        ]
        +
        depollution[
            "hazardous_fluid_mass_kg"
        ]
        +
        depollution[
            "transferred_to_next_stage_kg"
        ]
    )

    depollution_balance_error = (
        depollution[
            "stage_input_mass_kg"
        ]
        -
        depollution_accounted_mass
    ).abs()

    if (
        depollution_balance_error
        >
        0.05
    ).any():
        raise ValueError(
            "Depollution job mass balance exceeds tolerance"
        )

    # ========================================================
    # JOB 2 MASS BALANCE
    # ========================================================

    dismantling = (
        rvsf.loc[
            dismantling_mask
        ]
        .copy()
    )

    dismantling_accounted_mass = (
        dismantling[
            "reusable_parts_mass_kg"
        ]
        +
        dismantling[
            "recyclable_material_mass_kg"
        ]
        +
        dismantling[
            "residual_waste_mass_kg"
        ]
    )

    dismantling_balance_error = (
        dismantling[
            "stage_input_mass_kg"
        ]
        -
        dismantling_accounted_mass
    ).abs()

    if (
        dismantling_balance_error
        >
        0.05
    ).any():
        raise ValueError(
            "Dismantling job mass balance exceeds tolerance"
        )

    # ========================================================
    # STAGE 1 → STAGE 2 MASS CONTINUITY
    # ========================================================

    stage1_transfer = (
        depollution
        .set_index(
            "elv_assessment_id"
        )[
            "transferred_to_next_stage_kg"
        ]
        .sort_index()
    )

    stage2_input = (
        dismantling
        .set_index(
            "elv_assessment_id"
        )[
            "stage_input_mass_kg"
        ]
        .sort_index()
    )

    if not np.allclose(
        stage1_transfer.to_numpy(
            dtype=float
        ),
        stage2_input.to_numpy(
            dtype=float
        ),
        atol=0.01,
    ):
        raise ValueError(
            "RVSF stage-1 transfer mass does not "
            "equal stage-2 input mass"
        )

    # ========================================================
    # JOB-TYPE-SPECIFIC FIELDS
    # ========================================================

    if (
        depollution[
            "reusable_parts_mass_kg"
        ]
        !=
        0
    ).any():
        raise ValueError(
            "Depollution job cannot contain reusable-parts mass"
        )

    if (
        depollution[
            "recyclable_material_mass_kg"
        ]
        !=
        0
    ).any():
        raise ValueError(
            "Depollution job cannot contain recyclable mass"
        )

    if (
        depollution[
            "residual_waste_mass_kg"
        ]
        !=
        0
    ).any():
        raise ValueError(
            "Depollution job cannot contain final residual mass"
        )

    stage2_zero_columns = (
        "battery_recovered_mass_kg",
        "tyre_recovered_mass_kg",
        "catalytic_converter_mass_kg",

        "hazardous_fluid_liters",
        "hazardous_fluid_mass_kg",

        "removed_component_mass_kg",
        "transferred_to_next_stage_kg",
    )

    for column in stage2_zero_columns:
        if (
            dismantling[
                column
            ]
            !=
            0
        ).any():
            raise ValueError(
                f"Dismantling job must have {column}=0"
            )

    # ========================================================
    # RECOVERY FLAGS ↔ MASS
    # ========================================================

    flag_mass_pairs = (
        (
            "battery_recovered",
            "battery_recovered_mass_kg",
        ),

        (
            "tyre_set_recovered",
            "tyre_recovered_mass_kg",
        ),

        (
            "catalytic_converter_recovered",
            "catalytic_converter_mass_kg",
        ),
    )

    for (
        flag_column,
        mass_column,
    ) in flag_mass_pairs:

        invalid_positive_mass = (
            ~depollution[
                flag_column
            ]
            .astype(bool)
        ) & (
            depollution[
                mass_column
            ]
            >
            0
        )

        if invalid_positive_mass.any():
            raise ValueError(
                f"{mass_column} positive while "
                f"{flag_column}=False"
            )

        invalid_zero_mass = (
            depollution[
                flag_column
            ]
            .astype(bool)
        ) & (
            depollution[
                mass_column
            ]
            <=
            0
        )

        if invalid_zero_mass.any():
            raise ValueError(
                f"{flag_column}=True but "
                f"{mass_column} is not positive"
            )

    invalid_fluid_mass = (
        ~depollution[
            "fluid_drain_completed"
        ]
        .astype(bool)
    ) & (
        (
            depollution[
                "hazardous_fluid_liters"
            ]
            >
            0
        )
        |
        (
            depollution[
                "hazardous_fluid_mass_kg"
            ]
            >
            0
        )
    )

    if invalid_fluid_mass.any():
        raise ValueError(
            "Fluid mass exists when fluid_drain_completed=False"
        )

    # ========================================================
    # STATUS
    # ========================================================

    invalid_statuses = (
        set(
            rvsf[
                "job_status"
            ]
            .astype(str)
        )
        -
        VALID_JOB_STATUSES
    )

    if invalid_statuses:
        raise ValueError(
            "Invalid RVSF job statuses"
        )

    # ========================================================
    # BOOLEAN FIELDS
    # ========================================================

    boolean_columns = (
        "battery_recovered",
        "tyre_set_recovered",
        "catalytic_converter_recovered",

        "fluid_drain_completed",

        "quality_check_passed",
    )

    for column in boolean_columns:
        if (
            ~rvsf[
                column
            ]
            .isin(
                [
                    True,
                    False,
                ]
            )
        ).any():
            raise ValueError(
                f"{column} must contain boolean values only"
            )

    # ========================================================
    # FACILITY CONSISTENCY
    # ========================================================

    facility_location_count = (
        rvsf
        .groupby(
            "rvsf_facility_id"
        )[
            "city_id"
        ]
        .nunique()
    )

    if (
        facility_location_count
        >
        1
    ).any():
        raise ValueError(
            "An RVSF facility ID maps to multiple cities"
        )

    # ========================================================
    # PROVENANCE
    # ========================================================

    if (
        rvsf[
            "data_origin"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "RVSF jobs contain missing data_origin"
        )

    if (
        rvsf[
            "generator_version"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "RVSF jobs contain missing generator_version"
        )

    # ========================================================
    # HIDDEN RUNTIME / TRUTH LEAKAGE
    # ========================================================

    leaked_columns = (
        HIDDEN_RUNTIME_COLUMNS
        &
        set(
            rvsf.columns
        )
    )

    if leaked_columns:
        raise ValueError(
            "Hidden runtime / ground-truth fields leaked "
            "into RVSF jobs: "
            +
            ", ".join(
                sorted(
                    leaked_columns
                )
            )
        )


# ============================================================
# CONVENIENCE ALIAS
# ============================================================


def generate_rvsf(
    elv_assessments: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Convenience alias.
    """

    return generate_rvsf_job_cards(
        elv_assessments=
            elv_assessments,

        generation=
            generation,
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

    from data.generators.circularity.elv import (
        generate_elv_assessments,
    )

    # ========================================================
    # CONFIG
    # ========================================================

    generation_config = (
        load_generation_config()
    )

    distribution_config = (
        load_distribution_config()
    )

    # ========================================================
    # UPSTREAM CHAIN
    # ========================================================

    (
        regions_df,
        cities_df,
    ) = generate_geography()

    vehicle_models_df = (
        generate_vehicle_models(
            generation=
                generation_config,

            distributions=
                distribution_config,
        )
    )

    elv_df = (
        generate_elv_assessments(
            vehicle_models=
                vehicle_models_df,

            cities=
                cities_df,

            regions=
                regions_df,

            generation=
                generation_config,

            distributions=
                distribution_config,
        )
    )

    # ========================================================
    # DEPENDENCY CHECK
    # ========================================================

    print(
        "\n=== RVSF DEPENDENCY CHECK ===\n"
    )

    print(
        "ELV assessments:",
        len(
            elv_df
        ),
    )

    print(
        "Configured RVSF job cards:",
        _get_rvsf_target_count(
            generation_config
        ),
    )

    # ========================================================
    # GENERATE
    # ========================================================

    rvsf_df = (
        generate_rvsf_job_cards(
            elv_assessments=
                elv_df,

            generation=
                generation_config,
        )
    )

    # ========================================================
    # SAMPLE
    # ========================================================

    print(
        "\n=== RVSF SAMPLE ===\n"
    )

    sample_columns = [
        "rvsf_job_card_id",

        "elv_assessment_id",
        "elv_vehicle_id",

        "job_sequence",
        "job_type",

        "model_name",
        "city_name",

        "rvsf_facility_id",

        "job_opened_at",
        "processing_started_at",
        "processing_completed_at",

        "stage_input_mass_kg",

        "battery_recovered",
        "tyre_set_recovered",

        "fluid_drain_completed",

        "reusable_parts_mass_kg",
        "recyclable_material_mass_kg",
        "residual_waste_mass_kg",

        "transferred_to_next_stage_kg",

        "labor_hours",
        "energy_consumed_kwh",

        "quality_check_passed",
    ]

    print(
        rvsf_df[
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
    # JOB TYPE MIX
    # ========================================================

    print(
        "\n=== RVSF JOB TYPE MIX ===\n"
    )

    job_type_summary = (
        rvsf_df[
            "job_type"
        ]
        .value_counts()
        .rename_axis(
            "job_type"
        )
        .reset_index(
            name="jobs"
        )
    )

    job_type_summary[
        "rate"
    ] = (
        job_type_summary[
            "jobs"
        ]
        /
        len(
            rvsf_df
        )
    ).round(
        4
    )

    print(
        job_type_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # FACILITY SUMMARY
    # ========================================================

    print(
        "\n=== RVSF FACILITY SUMMARY ===\n"
    )

    facility_summary = (
        rvsf_df
        .groupby(
            [
                "rvsf_facility_id",
                "rvsf_facility_name",
                "city_name",
                "region_name",
            ],
            as_index=False,
        )
        .agg(
            jobs=(
                "rvsf_job_card_id",
                "size",
            ),

            vehicles=(
                "elv_vehicle_id",
                "nunique",
            ),

            average_input_mass_kg=(
                "stage_input_mass_kg",
                "mean",
            ),

            average_labor_hours=(
                "labor_hours",
                "mean",
            ),

            average_energy_kwh=(
                "energy_consumed_kwh",
                "mean",
            ),

            quality_pass_rate=(
                "quality_check_passed",
                "mean",
            ),
        )
        .sort_values(
            "jobs",
            ascending=False,
        )
    )

    for column in (
        "average_input_mass_kg",
        "average_labor_hours",
        "average_energy_kwh",
        "quality_pass_rate",
    ):
        facility_summary[
            column
        ] = (
            facility_summary[
                column
            ]
            .round(
                3
            )
        )

    print(
        facility_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # DEPOLLUTION
    # ========================================================

    depollution_df = (
        rvsf_df.loc[
            rvsf_df[
                "job_type"
            ]
            ==
            DEPOLLUTION_JOB
        ]
        .copy()
    )

    print(
        "\n=== RVSF DEPOLLUTION RECOVERY ===\n"
    )

    print(
        "Depollution jobs:",
        len(
            depollution_df
        ),
    )

    print(
        "Battery recovered rate:",
        round(
            float(
                depollution_df[
                    "battery_recovered"
                ]
                .mean()
            ),
            4,
        ),
    )

    print(
        "Tyre set recovered rate:",
        round(
            float(
                depollution_df[
                    "tyre_set_recovered"
                ]
                .mean()
            ),
            4,
        ),
    )

    print(
        "Catalytic converter recovered rate:",
        round(
            float(
                depollution_df[
                    "catalytic_converter_recovered"
                ]
                .mean()
            ),
            4,
        ),
    )

    print(
        "Fluid drain completed rate:",
        round(
            float(
                depollution_df[
                    "fluid_drain_completed"
                ]
                .mean()
            ),
            4,
        ),
    )

    print(
        "Average hazardous fluid liters:",
        round(
            float(
                depollution_df[
                    "hazardous_fluid_liters"
                ]
                .mean()
            ),
            2,
        ),
    )

    print(
        "Average transferred mass kg:",
        round(
            float(
                depollution_df[
                    "transferred_to_next_stage_kg"
                ]
                .mean()
            ),
            2,
        ),
    )

    # ========================================================
    # DISMANTLING
    # ========================================================

    dismantling_df = (
        rvsf_df.loc[
            rvsf_df[
                "job_type"
            ]
            ==
            DISMANTLING_JOB
        ]
        .copy()
    )

    print(
        "\n=== RVSF DISMANTLING / RECOVERY ===\n"
    )

    print(
        "Dismantling jobs:",
        len(
            dismantling_df
        ),
    )

    print(
        "Average reusable parts mass kg:",
        round(
            float(
                dismantling_df[
                    "reusable_parts_mass_kg"
                ]
                .mean()
            ),
            2,
        ),
    )

    print(
        "Average recyclable material mass kg:",
        round(
            float(
                dismantling_df[
                    "recyclable_material_mass_kg"
                ]
                .mean()
            ),
            2,
        ),
    )

    print(
        "Average residual waste mass kg:",
        round(
            float(
                dismantling_df[
                    "residual_waste_mass_kg"
                ]
                .mean()
            ),
            2,
        ),
    )

    reusable_fraction = (
        dismantling_df[
            "reusable_parts_mass_kg"
        ]
        /
        dismantling_df[
            "stage_input_mass_kg"
        ]
    )

    recycling_fraction_after_reuse = (
        dismantling_df[
            "recyclable_material_mass_kg"
        ]
        /
        (
            dismantling_df[
                "stage_input_mass_kg"
            ]
            -
            dismantling_df[
                "reusable_parts_mass_kg"
            ]
        )
        .replace(
            0,
            np.nan,
        )
    )

    print(
        "Average observed reusable fraction:",
        round(
            float(
                reusable_fraction.mean()
            ),
            4,
        ),
    )

    print(
        "Average recycling fraction after reuse:",
        round(
            float(
                recycling_fraction_after_reuse.mean()
            ),
            4,
        ),
    )

    # ========================================================
    # MASS BALANCE
    # ========================================================

    print(
        "\n=== RVSF MASS BALANCE ===\n"
    )

    depollution_balance_error = (
        depollution_df[
            "stage_input_mass_kg"
        ]
        -
        (
            depollution_df[
                "removed_component_mass_kg"
            ]
            +
            depollution_df[
                "hazardous_fluid_mass_kg"
            ]
            +
            depollution_df[
                "transferred_to_next_stage_kg"
            ]
        )
    ).abs()

    dismantling_balance_error = (
        dismantling_df[
            "stage_input_mass_kg"
        ]
        -
        (
            dismantling_df[
                "reusable_parts_mass_kg"
            ]
            +
            dismantling_df[
                "recyclable_material_mass_kg"
            ]
            +
            dismantling_df[
                "residual_waste_mass_kg"
            ]
        )
    ).abs()

    print(
        "Max depollution mass-balance error kg:",
        round(
            float(
                depollution_balance_error.max()
            ),
            4,
        ),
    )

    print(
        "Max dismantling mass-balance error kg:",
        round(
            float(
                dismantling_balance_error.max()
            ),
            4,
        ),
    )

    # ========================================================
    # RELATIONSHIP CHECKS
    # ========================================================

    relationship_df = (
        dismantling_df.merge(
            elv_df[
                [
                    "elv_assessment_id",
                    "assessed_reusable_parts_pct",
                    "assessed_recyclable_material_pct",
                ]
            ],
            on="elv_assessment_id",
            how="left",
            validate="one_to_one",
        )
    )

    relationship_df[
        "observed_reusable_fraction"
    ] = (
        relationship_df[
            "reusable_parts_mass_kg"
        ]
        /
        relationship_df[
            "stage_input_mass_kg"
        ]
    )

    print(
        "\n=== RVSF RELATIONSHIP CHECKS ===\n"
    )

    print(
        "Correlation ELV condition vs reusable mass fraction:",
        round(
            float(
                relationship_df[
                    [
                        "condition_score",
                        "observed_reusable_fraction",
                    ]
                ]
                .corr()
                .iloc[
                    0,
                    1
                ]
            ),
            4,
        ),
    )

    print(
        "Correlation assessed reusable pct "
        "vs observed reusable fraction:",
        round(
            float(
                relationship_df[
                    [
                        "assessed_reusable_parts_pct",
                        "observed_reusable_fraction",
                    ]
                ]
                .corr()
                .iloc[
                    0,
                    1
                ]
            ),
            4,
        ),
    )

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    print(
        "\n=== RVSF VALIDATION ===\n"
    )

    print(
        "Rows:",
        len(
            rvsf_df
        ),
    )

    print(
        "Unique job-card IDs:",
        rvsf_df[
            "rvsf_job_card_id"
        ]
        .nunique(),
    )

    print(
        "ELV assessments represented:",
        rvsf_df[
            "elv_assessment_id"
        ]
        .nunique(),
    )

    jobs_per_elv = (
        rvsf_df
        .groupby(
            "elv_assessment_id"
        )
        .size()
    )

    print(
        "Minimum jobs/ELV:",
        int(
            jobs_per_elv.min()
        ),
    )

    print(
        "Maximum jobs/ELV:",
        int(
            jobs_per_elv.max()
        ),
    )

    print(
        "Facilities represented:",
        rvsf_df[
            "rvsf_facility_id"
        ]
        .nunique(),
    )

    print(
        "Regions represented:",
        rvsf_df[
            "region_id"
        ]
        .nunique(),
    )

    print(
        "Duplicate job-card IDs:",
        int(
            rvsf_df[
                "rvsf_job_card_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Duplicate weighbridge tickets:",
        int(
            rvsf_df[
                "weighbridge_ticket_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Missing ELV assessment IDs:",
        int(
            rvsf_df[
                "elv_assessment_id"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Quality-check pass rate:",
        round(
            float(
                rvsf_df[
                    "quality_check_passed"
                ]
                .mean()
            ),
            4,
        ),
    )

    print(
        "Hidden truth/runtime leakage:",
        sorted(
            HIDDEN_RUNTIME_COLUMNS
            &
            set(
                rvsf_df.columns
            )
        ),
    )

    print(
        "\nGenerated "
        f"{len(rvsf_df)} "
        "synthetic RVSF job cards successfully."
    )