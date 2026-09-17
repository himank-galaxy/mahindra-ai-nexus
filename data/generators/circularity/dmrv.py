"""
Synthetic dMRV Evidence Generator
for Mahindra AI Nexus.

============================================================
PURPOSE
============================================================

Generate digital Measurement / Reporting / Verification
(dMRV) evidence records from validated RVSF operational
job cards.

Dependency chain:

    ELV Assessments
        ↓
    RVSF Job Cards
        ↓
    dMRV Evidence Records
        ↓
    Carbon Credit Listings


============================================================
CURRENT GENERATION MODEL
============================================================

Each RVSF job card creates exactly two dMRV records:

    1. PROCESS_EXECUTION_EVIDENCE

       Evidence covering:
       - processing duration
       - labor
       - electricity use
       - water use
       - process timestamps

    2. MATERIAL_MASS_BALANCE_EVIDENCE

       Evidence covering:
       - stage input mass
       - removed components
       - hazardous fluids
       - reusable parts
       - recyclable material
       - residual waste
       - next-stage transfer


With:

    1,500 RVSF job cards

the configured target is:

    3,000 dMRV records


============================================================
CRITICAL ARCHITECTURAL RULE
============================================================

This generator creates RAW / OBSERVED dMRV evidence.

It intentionally DOES NOT create:

    dMRV completeness score
    evidence sufficiency score
    verification readiness
    verification-ready flag
    compliance risk score
    carbon-credit estimate
    predicted credits
    recommended action
    AI confidence
    model score

Those are runtime application outputs that must later be
derived from the evidence created here.

Missing evidence is represented explicitly through:

    evidence_available
    evidence_status
    missing_reason_code

and through supporting evidence flags such as:

    source_reference_present
    evidence_attachment_present
    timestamp_verified
    digital_signature_present
    operator_identity_present
    chain_of_custody_present
    measurement_calibration_present

The backend can therefore independently calculate:

    dMRV completeness
    evidence sufficiency
    verification readiness
    compliance risk


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

Returns one pandas DataFrame.

No CSV writes occur in this module.
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
# dMRV EVIDENCE TYPES
# ============================================================

PROCESS_EXECUTION_EVIDENCE = (
    "PROCESS_EXECUTION_EVIDENCE"
)

MATERIAL_MASS_BALANCE_EVIDENCE = (
    "MATERIAL_MASS_BALANCE_EVIDENCE"
)

VALID_EVIDENCE_TYPES = {
    PROCESS_EXECUTION_EVIDENCE,
    MATERIAL_MASS_BALANCE_EVIDENCE,
}


# ============================================================
# EVIDENCE STATUS
# ============================================================

EVIDENCE_STATUS_CAPTURED = "CAPTURED"
EVIDENCE_STATUS_MISSING = "MISSING"

VALID_EVIDENCE_STATUSES = {
    EVIDENCE_STATUS_CAPTURED,
    EVIDENCE_STATUS_MISSING,
}


# ============================================================
# EXPECTED SOURCE SYSTEMS
# ============================================================

PROCESS_SOURCE_SYSTEM = "RVSF_PROCESS_LOG"

MASS_SOURCE_SYSTEM = "RVSF_WEIGHBRIDGE"


# ============================================================
# MEASUREMENT BASIS
# ============================================================

PROCESS_MEASUREMENT_BASIS = (
    "PROCESS_LOG_AND_RESOURCE_METERS"
)

MASS_MEASUREMENT_BASIS = (
    "WEIGHBRIDGE_AND_MASS_FLOW_LOG"
)


# ============================================================
# SYNTHETIC ENGINEERING PARAMETERS
#
# These are development assumptions only.
# They are NOT Mahindra operational statistics.
# ============================================================

PROCESS_EVIDENCE_AVAILABILITY = 0.94

MASS_EVIDENCE_AVAILABILITY = 0.955

FAILED_QC_AVAILABILITY_PENALTY = 0.16


# ============================================================
# SUPPORTING EVIDENCE CAPTURE PROBABILITIES
#
# Applied only when the main evidence record is available.
# ============================================================

PROCESS_SUPPORT_PROBABILITIES = {
    "source_reference_present": 0.985,
    "evidence_attachment_present": 0.930,
    "timestamp_verified": 0.985,
    "digital_signature_present": 0.880,
    "operator_identity_present": 0.950,
    "chain_of_custody_present": 0.900,
    "measurement_calibration_present": 0.940,
}

MASS_SUPPORT_PROBABILITIES = {
    "source_reference_present": 0.995,
    "evidence_attachment_present": 0.970,
    "timestamp_verified": 0.990,
    "digital_signature_present": 0.920,
    "operator_identity_present": 0.960,
    "chain_of_custody_present": 0.960,
    "measurement_calibration_present": 0.985,
}


# ============================================================
# MISSING-EVIDENCE REASON CODES
# ============================================================

PROCESS_MISSING_REASONS = [
    "PROCESS_LOG_EXPORT_MISSING",
    "RESOURCE_METER_CAPTURE_MISSING",
    "EVIDENCE_ATTACHMENT_NOT_AVAILABLE",
]

PROCESS_MISSING_REASON_WEIGHTS = np.asarray(
    [
        0.45,
        0.35,
        0.20,
    ],
    dtype=float,
)

MASS_MISSING_REASONS = [
    "WEIGHBRIDGE_EVIDENCE_MISSING",
    "MASS_FLOW_RECORD_MISSING",
    "EVIDENCE_ATTACHMENT_NOT_AVAILABLE",
]

MASS_MISSING_REASON_WEIGHTS = np.asarray(
    [
        0.45,
        0.35,
        0.20,
    ],
    dtype=float,
)

VALID_MISSING_REASON_CODES = (
    set(PROCESS_MISSING_REASONS)
    |
    set(MASS_MISSING_REASONS)
)


# ============================================================
# FORBIDDEN RUNTIME / AI / GROUND-TRUTH FIELDS
# ============================================================

HIDDEN_RUNTIME_COLUMNS = {
    "dmrv_completeness",
    "dmrv_completeness_score",

    "evidence_sufficiency",
    "evidence_sufficiency_score",

    "verification_readiness",
    "verification_readiness_score",
    "verification_ready",

    "compliance_risk",
    "compliance_risk_score",

    "carbon_credit_estimate",
    "estimated_carbon_credits",
    "predicted_carbon_credits",

    "credit_value",
    "credit_value_inr",

    "recommended_action",
    "recommended_disposition",

    "confidence",
    "confidence_score",

    "model_score",
    "model_probability",

    "risk_score",
    "risk_band",

    "true_verification_status",
    "true_credit_value",
    "true_carbon_credit_quantity",

    "target_verification_ready",
    "target_credit_value",
}


# ============================================================
# REQUIRED RVSF INPUT SCHEMA
# ============================================================

RVSF_REQUIRED_COLUMNS: set[str] = {
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


# ============================================================
# TYPE-SPECIFIC MEASUREMENT COLUMNS
# ============================================================

PROCESS_MEASUREMENT_COLUMNS = [
    "observed_processing_duration_minutes",
    "observed_labor_hours",
    "observed_energy_consumed_kwh",
    "observed_water_consumed_liters",
]

MASS_MEASUREMENT_COLUMNS = [
    "observed_stage_input_mass_kg",

    "observed_battery_recovered_mass_kg",
    "observed_tyre_recovered_mass_kg",
    "observed_catalytic_converter_mass_kg",

    "observed_hazardous_fluid_liters",
    "observed_hazardous_fluid_mass_kg",

    "observed_removed_component_mass_kg",

    "observed_reusable_parts_mass_kg",
    "observed_recyclable_material_mass_kg",
    "observed_residual_waste_mass_kg",

    "observed_transferred_to_next_stage_kg",
]


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
    Return configured timezone-aware generation boundaries.
    """

    try:
        time_config = generation["time"]

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
# TARGET COUNT
# ============================================================


def _get_dmrv_target_count(
    generation: Mapping[str, Any],
) -> int:
    """
    Read:

        circularity:
            dmrv_records:
                count: 3000
    """

    try:
        target_count = int(
            generation[
                "circularity"
            ][
                "dmrv_records"
            ][
                "count"
            ]
        )

    except KeyError as exc:
        raise KeyError(
            "Missing "
            "generation.circularity."
            "dmrv_records.count"
        ) from exc

    if target_count <= 0:
        raise ValueError(
            "generation.circularity."
            "dmrv_records.count must be > 0"
        )

    return target_count


# ============================================================
# BOOLEAN NORMALIZATION
# ============================================================


def _to_bool_series(
    series: pd.Series,
) -> pd.Series:
    """
    Normalize boolean-like values.
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
        .map(
            convert
        )
        .astype(bool)
    )


# ============================================================
# PREPARE RVSF INPUT
# ============================================================


def _prepare_rvsf_job_cards(
    rvsf_job_cards: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate frozen RVSF operational job cards.
    """

    if rvsf_job_cards.empty:
        raise ValueError(
            "RVSF job cards DataFrame cannot be empty"
        )

    missing_columns = (
        RVSF_REQUIRED_COLUMNS
        -
        set(
            rvsf_job_cards.columns
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

    result = (
        rvsf_job_cards
        .copy(
            deep=True
        )
    )

    # ========================================================
    # IDENTIFIERS
    # ========================================================

    required_identifier_columns = (
        "rvsf_job_card_id",
        "elv_assessment_id",
        "elv_vehicle_id",
        "vehicle_model_id",
        "rvsf_facility_id",
        "city_id",
        "region_id",
        "weighbridge_ticket_id",
    )

    for column in required_identifier_columns:
        if (
            result[
                column
            ]
            .isna()
            .any()
        ):
            raise ValueError(
                "RVSF job cards contain missing "
                f"{column}"
            )

    if (
        result[
            "rvsf_job_card_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate rvsf_job_card_id values found"
        )

    if (
        result[
            "weighbridge_ticket_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate weighbridge_ticket_id values found"
        )

    # ========================================================
    # COMPLETED HISTORICAL JOBS
    # ========================================================

    if (
        set(
            result[
                "job_status"
            ]
            .astype(str)
        )
        !=
        {
            "COMPLETED"
        }
    ):
        raise ValueError(
            "dMRV generation requires completed "
            "RVSF job cards"
        )

    # ========================================================
    # TIMESTAMPS
    # ========================================================

    timestamp_columns = (
        "job_opened_at",
        "processing_started_at",
        "processing_completed_at",
    )

    for column in timestamp_columns:
        result[
            column
        ] = pd.to_datetime(
            result[
                column
            ],
            utc=True,
        )

    if (
        result[
            "processing_started_at"
        ]
        <
        result[
            "job_opened_at"
        ]
    ).any():
        raise ValueError(
            "RVSF processing starts before job opening"
        )

    if (
        result[
            "processing_completed_at"
        ]
        <=
        result[
            "processing_started_at"
        ]
    ).any():
        raise ValueError(
            "RVSF processing completion must occur "
            "after processing start"
        )

    # ========================================================
    # NUMERIC OPERATIONAL FIELDS
    # ========================================================

    numeric_columns = (
        "processing_duration_minutes",

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
                column
            ]
            <
            0
        ).any():
            raise ValueError(
                f"{column} cannot be negative"
            )

    if (
        result[
            "stage_input_mass_kg"
        ]
        <=
        0
    ).any():
        raise ValueError(
            "stage_input_mass_kg must be positive"
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
        result[
            column
        ] = (
            _to_bool_series(
                result[
                    column
                ]
            )
        )

    return (
        result
        .sort_values(
            [
                "processing_completed_at",
                "rvsf_job_card_id",
            ]
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# EVIDENCE AVAILABILITY
# ============================================================


def _evidence_availability_probability(
    evidence_type: str,
    quality_check_passed: bool,
) -> float:
    """
    Raw source-evidence availability probability.

    Failed RVSF QC increases the chance that the evidence
    package is incomplete or unavailable.

    This is NOT a verification-readiness score.
    """

    if (
        evidence_type
        ==
        PROCESS_EXECUTION_EVIDENCE
    ):
        probability = (
            PROCESS_EVIDENCE_AVAILABILITY
        )

    elif (
        evidence_type
        ==
        MATERIAL_MASS_BALANCE_EVIDENCE
    ):
        probability = (
            MASS_EVIDENCE_AVAILABILITY
        )

    else:
        raise ValueError(
            "Unexpected dMRV evidence type: "
            f"{evidence_type}"
        )

    if not quality_check_passed:
        probability -= (
            FAILED_QC_AVAILABILITY_PENALTY
        )

    return float(
        np.clip(
            probability,
            0.50,
            0.995,
        )
    )


# ============================================================
# SUPPORTING EVIDENCE FLAGS
# ============================================================


def _generate_support_flags(
    rng: np.random.Generator,
    evidence_type: str,
    evidence_available: bool,
) -> dict[str, bool]:
    """
    Generate atomic evidence-support observations.

    These are intentionally raw booleans rather than a single
    fake completeness/readiness score.
    """

    keys = (
        "source_reference_present",
        "evidence_attachment_present",
        "timestamp_verified",
        "digital_signature_present",
        "operator_identity_present",
        "chain_of_custody_present",
        "measurement_calibration_present",
    )

    if not evidence_available:
        return {
            key: False
            for key in keys
        }

    if (
        evidence_type
        ==
        PROCESS_EXECUTION_EVIDENCE
    ):
        probabilities = (
            PROCESS_SUPPORT_PROBABILITIES
        )

    elif (
        evidence_type
        ==
        MATERIAL_MASS_BALANCE_EVIDENCE
    ):
        probabilities = (
            MASS_SUPPORT_PROBABILITIES
        )

    else:
        raise ValueError(
            "Unexpected evidence type: "
            f"{evidence_type}"
        )

    return {
        key:
            bool(
                rng.random()
                <
                probabilities[
                    key
                ]
            )

        for key in keys
    }


# ============================================================
# MISSING REASON
# ============================================================


def _sample_missing_reason(
    rng: np.random.Generator,
    evidence_type: str,
) -> str:
    """
    Generate an operational missing-evidence reason.
    """

    if (
        evidence_type
        ==
        PROCESS_EXECUTION_EVIDENCE
    ):
        reasons = (
            PROCESS_MISSING_REASONS
        )

        weights = (
            PROCESS_MISSING_REASON_WEIGHTS
        )

    elif (
        evidence_type
        ==
        MATERIAL_MASS_BALANCE_EVIDENCE
    ):
        reasons = (
            MASS_MISSING_REASONS
        )

        weights = (
            MASS_MISSING_REASON_WEIGHTS
        )

    else:
        raise ValueError(
            "Unexpected evidence type: "
            f"{evidence_type}"
        )

    return str(
        rng.choice(
            reasons,
            p=weights,
        )
    )


# ============================================================
# dMRV RECORD TIMELINE
# ============================================================


def _build_dmrv_record_times(
    rng: np.random.Generator,
    processing_completed_at: pd.Timestamp,
    generation_end_utc: pd.Timestamp,
) -> tuple[
    pd.Timestamp,
    pd.Timestamp,
]:
    """
    Create two sequential dMRV registration timestamps after
    RVSF processing completes.

    Near the generation cutoff the delays are compressed so
    both dMRV records still remain inside the historical
    generation window.
    """

    completed_at = pd.Timestamp(
        processing_completed_at
    )

    generation_end = pd.Timestamp(
        generation_end_utc
    )

    remaining_seconds = (
        generation_end
        -
        completed_at
    ).total_seconds()

    if remaining_seconds <= 0:
        raise ValueError(
            "RVSF completion must occur before "
            "generation end"
        )

    preferred_process_delay_seconds = float(
        rng.uniform(
            0.25,
            4.0,
        )
        *
        3600.0
    )

    process_delay_seconds = min(
        preferred_process_delay_seconds,
        remaining_seconds
        *
        0.30,
    )

    process_delay_seconds = max(
        process_delay_seconds,
        min(
            0.001,
            remaining_seconds
            *
            0.10,
        ),
    )

    process_recorded_at = (
        completed_at
        +
        pd.Timedelta(
            seconds=
                process_delay_seconds
        )
    )

    remaining_after_process = (
        generation_end
        -
        process_recorded_at
    ).total_seconds()

    if remaining_after_process <= 0:
        raise ValueError(
            "Unable to place second dMRV record "
            "before generation end"
        )

    preferred_mass_delay_seconds = float(
        rng.uniform(
            0.25,
            5.0,
        )
        *
        3600.0
    )

    mass_delay_seconds = min(
        preferred_mass_delay_seconds,
        remaining_after_process
        *
        0.50,
    )

    mass_delay_seconds = max(
        mass_delay_seconds,
        min(
            0.001,
            remaining_after_process
            *
            0.10,
        ),
    )

    mass_recorded_at = (
        process_recorded_at
        +
        pd.Timedelta(
            seconds=
                mass_delay_seconds
        )
    )

    if not (
        completed_at
        <
        process_recorded_at
        <
        mass_recorded_at
        <
        generation_end
    ):
        raise ValueError(
            "Generated invalid dMRV record timeline"
        )

    return (
        process_recorded_at,
        mass_recorded_at,
    )


# ============================================================
# COMMON dMRV RECORD
# ============================================================


def _common_record_fields(
    job: Any,
    dmrv_record_id: str,
    evidence_sequence: int,
    evidence_type: str,
    dmrv_recorded_at: pd.Timestamp,
    evidence_available: bool,
    support_flags: Mapping[str, bool],
    missing_reason_code: str | None,
    data_origin: str,
    generator_version: str,
) -> dict[str, Any]:
    """
    Build shared dMRV fields.
    """

    if (
        evidence_type
        ==
        PROCESS_EXECUTION_EVIDENCE
    ):
        source_system = (
            PROCESS_SOURCE_SYSTEM
        )

        measurement_basis = (
            PROCESS_MEASUREMENT_BASIS
        )

        expected_source_reference = str(
            job.rvsf_job_card_id
        )

    elif (
        evidence_type
        ==
        MATERIAL_MASS_BALANCE_EVIDENCE
    ):
        source_system = (
            MASS_SOURCE_SYSTEM
        )

        measurement_basis = (
            MASS_MEASUREMENT_BASIS
        )

        expected_source_reference = str(
            job.weighbridge_ticket_id
        )

    else:
        raise ValueError(
            "Unexpected evidence type: "
            f"{evidence_type}"
        )

    source_reference_present = bool(
        support_flags[
            "source_reference_present"
        ]
    )

    if source_reference_present:
        source_reference_id: Any = (
            expected_source_reference
        )

    else:
        source_reference_id = pd.NA

    if evidence_available:
        evidence_status = (
            EVIDENCE_STATUS_CAPTURED
        )

        evidence_observed_at: Any = (
            dmrv_recorded_at
        )

    else:
        evidence_status = (
            EVIDENCE_STATUS_MISSING
        )

        evidence_observed_at = pd.NaT

    return {
        "dmrv_record_id":
            dmrv_record_id,

        "rvsf_job_card_id":
            str(
                job.rvsf_job_card_id
            ),

        "elv_assessment_id":
            str(
                job.elv_assessment_id
            ),

        "elv_vehicle_id":
            str(
                job.elv_vehicle_id
            ),

        "evidence_sequence":
            int(
                evidence_sequence
            ),

        "evidence_type":
            evidence_type,

        # ----------------------------------------------------
        # RVSF context
        # ----------------------------------------------------

        "job_type":
            str(
                job.job_type
            ),

        "vehicle_model_id":
            str(
                job.vehicle_model_id
            ),

        "model_name":
            str(
                job.model_name
            ),

        "segment":
            str(
                job.segment
            ),

        "rvsf_facility_id":
            str(
                job.rvsf_facility_id
            ),

        "rvsf_facility_name":
            str(
                job.rvsf_facility_name
            ),

        "city_id":
            str(
                job.city_id
            ),

        "city_name":
            str(
                job.city_name
            ),

        "region_id":
            str(
                job.region_id
            ),

        "region_name":
            str(
                job.region_name
            ),

        # ----------------------------------------------------
        # Measurement period
        # ----------------------------------------------------

        "measurement_period_start":
            pd.Timestamp(
                job.processing_started_at
            ),

        "measurement_period_end":
            pd.Timestamp(
                job.processing_completed_at
            ),

        # ----------------------------------------------------
        # dMRV recording
        # ----------------------------------------------------

        "dmrv_recorded_at":
            dmrv_recorded_at,

        "evidence_observed_at":
            evidence_observed_at,

        "evidence_source_system":
            source_system,

        "measurement_basis":
            measurement_basis,

        "source_reference_id":
            source_reference_id,

        # ----------------------------------------------------
        # Evidence availability
        # ----------------------------------------------------

        "evidence_available":
            bool(
                evidence_available
            ),

        "evidence_status":
            evidence_status,

        "missing_reason_code":
            (
                missing_reason_code
                if not evidence_available
                else pd.NA
            ),

        # ----------------------------------------------------
        # Atomic supporting evidence
        # ----------------------------------------------------

        "source_reference_present":
            source_reference_present,

        "evidence_attachment_present":
            bool(
                support_flags[
                    "evidence_attachment_present"
                ]
            ),

        "timestamp_verified":
            bool(
                support_flags[
                    "timestamp_verified"
                ]
            ),

        "digital_signature_present":
            bool(
                support_flags[
                    "digital_signature_present"
                ]
            ),

        "operator_identity_present":
            bool(
                support_flags[
                    "operator_identity_present"
                ]
            ),

        "chain_of_custody_present":
            bool(
                support_flags[
                    "chain_of_custody_present"
                ]
            ),

        "measurement_calibration_present":
            bool(
                support_flags[
                    "measurement_calibration_present"
                ]
            ),

        # ----------------------------------------------------
        # Source-job evidence
        # ----------------------------------------------------

        "source_job_quality_check_passed":
            bool(
                job.quality_check_passed
            ),

        # ----------------------------------------------------
        # Provenance
        # ----------------------------------------------------

        "data_origin":
            data_origin,

        "generator_version":
            generator_version,
    }


# ============================================================
# PROCESS EVIDENCE MEASUREMENTS
# ============================================================


def _add_process_measurements(
    record: dict[str, Any],
    job: Any,
    evidence_available: bool,
) -> None:
    """
    Add process-execution measurements.

    Mass-balance fields are explicitly non-applicable and
    represented as NaN rather than zero.
    """

    if evidence_available:
        record[
            "observed_processing_duration_minutes"
        ] = float(
            job.processing_duration_minutes
        )

        record[
            "observed_labor_hours"
        ] = float(
            job.labor_hours
        )

        record[
            "observed_energy_consumed_kwh"
        ] = float(
            job.energy_consumed_kwh
        )

        record[
            "observed_water_consumed_liters"
        ] = float(
            job.water_consumed_liters
        )

    else:
        for column in (
            PROCESS_MEASUREMENT_COLUMNS
        ):
            record[
                column
            ] = np.nan

    for column in (
        MASS_MEASUREMENT_COLUMNS
    ):
        record[
            column
        ] = np.nan


# ============================================================
# MASS EVIDENCE MEASUREMENTS
# ============================================================


def _add_mass_measurements(
    record: dict[str, Any],
    job: Any,
    evidence_available: bool,
) -> None:
    """
    Add material / mass-balance observations.

    Process resource fields are non-applicable for this
    evidence record and therefore represented as NaN.
    """

    for column in (
        PROCESS_MEASUREMENT_COLUMNS
    ):
        record[
            column
        ] = np.nan

    if evidence_available:
        record[
            "observed_stage_input_mass_kg"
        ] = float(
            job.stage_input_mass_kg
        )

        record[
            "observed_battery_recovered_mass_kg"
        ] = float(
            job.battery_recovered_mass_kg
        )

        record[
            "observed_tyre_recovered_mass_kg"
        ] = float(
            job.tyre_recovered_mass_kg
        )

        record[
            "observed_catalytic_converter_mass_kg"
        ] = float(
            job.catalytic_converter_mass_kg
        )

        record[
            "observed_hazardous_fluid_liters"
        ] = float(
            job.hazardous_fluid_liters
        )

        record[
            "observed_hazardous_fluid_mass_kg"
        ] = float(
            job.hazardous_fluid_mass_kg
        )

        record[
            "observed_removed_component_mass_kg"
        ] = float(
            job.removed_component_mass_kg
        )

        record[
            "observed_reusable_parts_mass_kg"
        ] = float(
            job.reusable_parts_mass_kg
        )

        record[
            "observed_recyclable_material_mass_kg"
        ] = float(
            job.recyclable_material_mass_kg
        )

        record[
            "observed_residual_waste_mass_kg"
        ] = float(
            job.residual_waste_mass_kg
        )

        record[
            "observed_transferred_to_next_stage_kg"
        ] = float(
            job.transferred_to_next_stage_kg
        )

    else:
        for column in (
            MASS_MEASUREMENT_COLUMNS
        ):
            record[
                column
            ] = np.nan


# ============================================================
# MAIN GENERATOR
# ============================================================


def generate_dmrv_records(
    rvsf_job_cards: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate structured dMRV evidence from RVSF job cards.
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
        _get_dmrv_target_count(
            generation
        )
    )

    generation_end_utc = (
        generation_end
        .tz_convert(
            "UTC"
        )
    )

    # ========================================================
    # UPSTREAM DATA
    # ========================================================

    rvsf = (
        _prepare_rvsf_job_cards(
            rvsf_job_cards
        )
    )

    # ========================================================
    # TWO dMRV RECORDS PER RVSF JOB
    # ========================================================

    expected_count = (
        len(
            rvsf
        )
        *
        2
    )

    if (
        target_count
        !=
        expected_count
    ):
        raise ValueError(
            "Configured dMRV target does not match "
            "the two-evidence-record RVSF model. "
            f"RVSF jobs={len(rvsf)}, "
            f"required_dmrv_records={expected_count}, "
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
            "circularity.dmrv",
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

    # ========================================================
    # GENERATE
    # ========================================================

    rows: list[
        dict[str, Any]
    ] = []

    record_counter = 0

    for job in rvsf.itertuples(
        index=False
    ):
        quality_check_passed = bool(
            job.quality_check_passed
        )

        # ----------------------------------------------------
        # Two sequential dMRV registration timestamps
        # ----------------------------------------------------

        (
            process_recorded_at,
            mass_recorded_at,
        ) = (
            _build_dmrv_record_times(
                rng=rng,

                processing_completed_at=
                    pd.Timestamp(
                        job.processing_completed_at
                    ),

                generation_end_utc=
                    generation_end_utc,
            )
        )

        # ====================================================
        # RECORD 1 — PROCESS EXECUTION
        # ====================================================

        process_availability_probability = (
            _evidence_availability_probability(
                evidence_type=
                    PROCESS_EXECUTION_EVIDENCE,

                quality_check_passed=
                    quality_check_passed,
            )
        )

        process_available = bool(
            rng.random()
            <
            process_availability_probability
        )

        process_support_flags = (
            _generate_support_flags(
                rng=rng,

                evidence_type=
                    PROCESS_EXECUTION_EVIDENCE,

                evidence_available=
                    process_available,
            )
        )

        process_missing_reason = (
            None

            if process_available

            else _sample_missing_reason(
                rng=rng,

                evidence_type=
                    PROCESS_EXECUTION_EVIDENCE,
            )
        )

        record_counter += 1

        process_record = (
            _common_record_fields(
                job=job,

                dmrv_record_id=
                    generate_id(
                        "DMRV_SYN",
                        record_counter,
                        width=8,
                    ),

                evidence_sequence=1,

                evidence_type=
                    PROCESS_EXECUTION_EVIDENCE,

                dmrv_recorded_at=
                    process_recorded_at
                    .tz_convert(
                        timezone
                    ),

                evidence_available=
                    process_available,

                support_flags=
                    process_support_flags,

                missing_reason_code=
                    process_missing_reason,

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

        _add_process_measurements(
            record=
                process_record,

            job=
                job,

            evidence_available=
                process_available,
        )

        rows.append(
            process_record
        )

        # ====================================================
        # RECORD 2 — MATERIAL MASS BALANCE
        # ====================================================

        mass_availability_probability = (
            _evidence_availability_probability(
                evidence_type=
                    MATERIAL_MASS_BALANCE_EVIDENCE,

                quality_check_passed=
                    quality_check_passed,
            )
        )

        mass_available = bool(
            rng.random()
            <
            mass_availability_probability
        )

        mass_support_flags = (
            _generate_support_flags(
                rng=rng,

                evidence_type=
                    MATERIAL_MASS_BALANCE_EVIDENCE,

                evidence_available=
                    mass_available,
            )
        )

        mass_missing_reason = (
            None

            if mass_available

            else _sample_missing_reason(
                rng=rng,

                evidence_type=
                    MATERIAL_MASS_BALANCE_EVIDENCE,
            )
        )

        record_counter += 1

        mass_record = (
            _common_record_fields(
                job=job,

                dmrv_record_id=
                    generate_id(
                        "DMRV_SYN",
                        record_counter,
                        width=8,
                    ),

                evidence_sequence=2,

                evidence_type=
                    MATERIAL_MASS_BALANCE_EVIDENCE,

                dmrv_recorded_at=
                    mass_recorded_at
                    .tz_convert(
                        timezone
                    ),

                evidence_available=
                    mass_available,

                support_flags=
                    mass_support_flags,

                missing_reason_code=
                    mass_missing_reason,

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

        _add_mass_measurements(
            record=
                mass_record,

            job=
                job,

            evidence_available=
                mass_available,
        )

        rows.append(
            mass_record
        )

    dmrv = pd.DataFrame(
        rows
    )

    # ========================================================
    # FINAL COLUMN ORDER
    # ========================================================

    output_columns = [
        "dmrv_record_id",

        "rvsf_job_card_id",
        "elv_assessment_id",
        "elv_vehicle_id",

        "evidence_sequence",
        "evidence_type",

        "job_type",

        "vehicle_model_id",
        "model_name",
        "segment",

        "rvsf_facility_id",
        "rvsf_facility_name",

        "city_id",
        "city_name",

        "region_id",
        "region_name",

        "measurement_period_start",
        "measurement_period_end",

        "dmrv_recorded_at",
        "evidence_observed_at",

        "evidence_source_system",
        "measurement_basis",

        "source_reference_id",

        "evidence_available",
        "evidence_status",
        "missing_reason_code",

        "source_reference_present",
        "evidence_attachment_present",
        "timestamp_verified",
        "digital_signature_present",
        "operator_identity_present",
        "chain_of_custody_present",
        "measurement_calibration_present",

        "source_job_quality_check_passed",

        # Process observations
        "observed_processing_duration_minutes",
        "observed_labor_hours",
        "observed_energy_consumed_kwh",
        "observed_water_consumed_liters",

        # Mass observations
        "observed_stage_input_mass_kg",

        "observed_battery_recovered_mass_kg",
        "observed_tyre_recovered_mass_kg",
        "observed_catalytic_converter_mass_kg",

        "observed_hazardous_fluid_liters",
        "observed_hazardous_fluid_mass_kg",

        "observed_removed_component_mass_kg",

        "observed_reusable_parts_mass_kg",
        "observed_recyclable_material_mass_kg",
        "observed_residual_waste_mass_kg",

        "observed_transferred_to_next_stage_kg",

        "data_origin",
        "generator_version",
    ]

    dmrv = (
        dmrv[
            output_columns
        ]
        .copy()
    )

    # ========================================================
    # VALIDATE
    # ========================================================

    validate_dmrv_records(
        dmrv=dmrv,

        rvsf_job_cards=rvsf,

        generation_start=
            generation_start,

        generation_end=
            generation_end,

        expected_count=
            target_count,
    )

    return dmrv


# ============================================================
# VALIDATION
# ============================================================


def validate_dmrv_records(
    dmrv: pd.DataFrame,
    rvsf_job_cards: pd.DataFrame,
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
    expected_count: int,
) -> None:
    """
    Validate dMRV evidence integrity.
    """

    required_columns = {
        "dmrv_record_id",

        "rvsf_job_card_id",
        "elv_assessment_id",
        "elv_vehicle_id",

        "evidence_sequence",
        "evidence_type",

        "job_type",

        "vehicle_model_id",
        "model_name",
        "segment",

        "rvsf_facility_id",
        "rvsf_facility_name",

        "city_id",
        "city_name",

        "region_id",
        "region_name",

        "measurement_period_start",
        "measurement_period_end",

        "dmrv_recorded_at",
        "evidence_observed_at",

        "evidence_source_system",
        "measurement_basis",

        "source_reference_id",

        "evidence_available",
        "evidence_status",
        "missing_reason_code",

        "source_reference_present",
        "evidence_attachment_present",
        "timestamp_verified",
        "digital_signature_present",
        "operator_identity_present",
        "chain_of_custody_present",
        "measurement_calibration_present",

        "source_job_quality_check_passed",

        *PROCESS_MEASUREMENT_COLUMNS,
        *MASS_MEASUREMENT_COLUMNS,

        "data_origin",
        "generator_version",
    }

    missing_columns = (
        required_columns
        -
        set(
            dmrv.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "dMRV records missing columns: "
            +
            ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if dmrv.empty:
        raise ValueError(
            "dMRV generator produced zero rows"
        )

    # ========================================================
    # EXACT COUNT
    # ========================================================

    if (
        len(
            dmrv
        )
        !=
        expected_count
    ):
        raise ValueError(
            "Unexpected dMRV record count. "
            f"Expected={expected_count}, "
            f"actual={len(dmrv)}"
        )

    # ========================================================
    # PRIMARY KEY
    # ========================================================

    if (
        dmrv[
            "dmrv_record_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "dMRV records contain missing IDs"
        )

    if (
        dmrv[
            "dmrv_record_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate dmrv_record_id values found"
        )

    # ========================================================
    # RVSF FK
    # ========================================================

    valid_job_ids = set(
        rvsf_job_cards[
            "rvsf_job_card_id"
        ]
        .astype(str)
    )

    dmrv_job_ids = set(
        dmrv[
            "rvsf_job_card_id"
        ]
        .astype(str)
    )

    invalid_job_ids = (
        dmrv_job_ids
        -
        valid_job_ids
    )

    if invalid_job_ids:
        raise ValueError(
            "dMRV records reference invalid "
            "RVSF job cards"
        )

    if (
        dmrv_job_ids
        !=
        valid_job_ids
    ):
        raise ValueError(
            "Not every RVSF job card is represented "
            "in dMRV records"
        )

    # ========================================================
    # EXACTLY TWO RECORDS PER RVSF JOB
    # ========================================================

    records_per_job = (
        dmrv
        .groupby(
            "rvsf_job_card_id"
        )
        .size()
    )

    if (
        records_per_job
        !=
        2
    ).any():
        raise ValueError(
            "Every RVSF job must have exactly "
            "two dMRV records"
        )

    # ========================================================
    # EXACT EVIDENCE PAIR
    # ========================================================

    evidence_type_counts = (
        dmrv
        .groupby(
            [
                "rvsf_job_card_id",
                "evidence_type",
            ]
        )
        .size()
        .unstack(
            fill_value=0
        )
    )

    for evidence_type in (
        VALID_EVIDENCE_TYPES
    ):
        if (
            evidence_type
            not in evidence_type_counts.columns
        ):
            raise ValueError(
                "Missing dMRV evidence type: "
                f"{evidence_type}"
            )

        if (
            evidence_type_counts[
                evidence_type
            ]
            !=
            1
        ).any():
            raise ValueError(
                "Every RVSF job must have exactly "
                f"one {evidence_type}"
            )

    # ========================================================
    # TYPE MASKS
    # ========================================================

    process_mask = (
        dmrv[
            "evidence_type"
        ]
        ==
        PROCESS_EXECUTION_EVIDENCE
    )

    mass_mask = (
        dmrv[
            "evidence_type"
        ]
        ==
        MATERIAL_MASS_BALANCE_EVIDENCE
    )

    # ========================================================
    # SEQUENCE
    # ========================================================

    if (
        dmrv.loc[
            process_mask,
            "evidence_sequence",
        ]
        !=
        1
    ).any():
        raise ValueError(
            "PROCESS_EXECUTION_EVIDENCE must have "
            "evidence_sequence=1"
        )

    if (
        dmrv.loc[
            mass_mask,
            "evidence_sequence",
        ]
        !=
        2
    ).any():
        raise ValueError(
            "MATERIAL_MASS_BALANCE_EVIDENCE must "
            "have evidence_sequence=2"
        )

    # ========================================================
    # VALID EVIDENCE TYPES
    # ========================================================

    invalid_evidence_types = (
        set(
            dmrv[
                "evidence_type"
            ]
            .astype(str)
        )
        -
        VALID_EVIDENCE_TYPES
    )

    if invalid_evidence_types:
        raise ValueError(
            "Invalid dMRV evidence types"
        )

    # ========================================================
    # SOURCE JOB LOOKUP
    # ========================================================

    job_lookup = (
        rvsf_job_cards
        .set_index(
            "rvsf_job_card_id"
        )
    )

    # ========================================================
    # METADATA / SOURCE CONSISTENCY
    # ========================================================

    for record in dmrv.itertuples(
        index=False
    ):
        source_job = (
            job_lookup.loc[
                str(
                    record.rvsf_job_card_id
                )
            ]
        )

        consistency_checks = {
            "elv_assessment_id":
                source_job[
                    "elv_assessment_id"
                ],

            "elv_vehicle_id":
                source_job[
                    "elv_vehicle_id"
                ],

            "job_type":
                source_job[
                    "job_type"
                ],

            "vehicle_model_id":
                source_job[
                    "vehicle_model_id"
                ],

            "model_name":
                source_job[
                    "model_name"
                ],

            "segment":
                source_job[
                    "segment"
                ],

            "rvsf_facility_id":
                source_job[
                    "rvsf_facility_id"
                ],

            "rvsf_facility_name":
                source_job[
                    "rvsf_facility_name"
                ],

            "city_id":
                source_job[
                    "city_id"
                ],

            "city_name":
                source_job[
                    "city_name"
                ],

            "region_id":
                source_job[
                    "region_id"
                ],

            "region_name":
                source_job[
                    "region_name"
                ],
        }

        for (
            column,
            expected_value,
        ) in consistency_checks.items():

            actual_value = getattr(
                record,
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
                    f"{record.dmrv_record_id}: "
                    f"{column} inconsistent with "
                    "source RVSF job"
                )

        if (
            bool(
                record.source_job_quality_check_passed
            )
            !=
            bool(
                source_job[
                    "quality_check_passed"
                ]
            )
        ):
            raise ValueError(
                f"{record.dmrv_record_id}: "
                "source_job_quality_check_passed "
                "does not match RVSF source"
            )

    # ========================================================
    # MEASUREMENT PERIOD
    # ========================================================

    measurement_start = (
        pd.to_datetime(
            dmrv[
                "measurement_period_start"
            ],
            utc=True,
        )
    )

    measurement_end = (
        pd.to_datetime(
            dmrv[
                "measurement_period_end"
            ],
            utc=True,
        )
    )

    if (
        measurement_end
        <=
        measurement_start
    ).any():
        raise ValueError(
            "dMRV measurement period end must occur "
            "after measurement period start"
        )

    for record in dmrv.itertuples(
        index=False
    ):
        source_job = (
            job_lookup.loc[
                str(
                    record.rvsf_job_card_id
                )
            ]
        )

        expected_start = pd.Timestamp(
            source_job[
                "processing_started_at"
            ]
        )

        expected_end = pd.Timestamp(
            source_job[
                "processing_completed_at"
            ]
        )

        if (
            pd.Timestamp(
                record.measurement_period_start
            )
            !=
            expected_start
        ):
            raise ValueError(
                f"{record.dmrv_record_id}: "
                "measurement_period_start mismatch"
            )

        if (
            pd.Timestamp(
                record.measurement_period_end
            )
            !=
            expected_end
        ):
            raise ValueError(
                f"{record.dmrv_record_id}: "
                "measurement_period_end mismatch"
            )

    # ========================================================
    # RECORD TIMELINE
    # ========================================================

    recorded_at = pd.to_datetime(
        dmrv[
            "dmrv_recorded_at"
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
        recorded_at
        <
        generation_start_utc
    ).any():
        raise ValueError(
            "dMRV record occurs before generation start"
        )

    if (
        recorded_at
        >=
        generation_end_utc
    ).any():
        raise ValueError(
            "dMRV record occurs on/after generation end"
        )

    if (
        recorded_at
        <=
        measurement_end
    ).any():
        raise ValueError(
            "dMRV record must be registered after "
            "RVSF processing completes"
        )

    # ========================================================
    # PROCESS EVIDENCE PRECEDES MASS EVIDENCE
    # ========================================================

    record_time_table = (
        dmrv
        .pivot(
            index="rvsf_job_card_id",
            columns="evidence_sequence",
            values="dmrv_recorded_at",
        )
    )

    process_record_time = pd.to_datetime(
        record_time_table[
            1
        ],
        utc=True,
    )

    mass_record_time = pd.to_datetime(
        record_time_table[
            2
        ],
        utc=True,
    )

    if (
        mass_record_time
        <=
        process_record_time
    ).any():
        raise ValueError(
            "Mass-balance evidence must be registered "
            "after process evidence"
        )

    # ========================================================
    # EVIDENCE AVAILABLE / STATUS
    # ========================================================

    if (
        ~dmrv[
            "evidence_available"
        ]
        .isin(
            [
                True,
                False,
            ]
        )
    ).any():
        raise ValueError(
            "evidence_available must contain "
            "booleans only"
        )

    available_mask = (
        dmrv[
            "evidence_available"
        ]
        .astype(bool)
    )

    missing_mask = (
        ~available_mask
    )

    if (
        dmrv.loc[
            available_mask,
            "evidence_status",
        ]
        !=
        EVIDENCE_STATUS_CAPTURED
    ).any():
        raise ValueError(
            "Available evidence must have "
            "evidence_status=CAPTURED"
        )

    if (
        dmrv.loc[
            missing_mask,
            "evidence_status",
        ]
        !=
        EVIDENCE_STATUS_MISSING
    ).any():
        raise ValueError(
            "Unavailable evidence must have "
            "evidence_status=MISSING"
        )

    invalid_statuses = (
        set(
            dmrv[
                "evidence_status"
            ]
            .astype(str)
        )
        -
        VALID_EVIDENCE_STATUSES
    )

    if invalid_statuses:
        raise ValueError(
            "Invalid dMRV evidence statuses"
        )

    # ========================================================
    # MISSING REASON
    # ========================================================

    if (
        dmrv.loc[
            available_mask,
            "missing_reason_code",
        ]
        .notna()
        .any()
    ):
        raise ValueError(
            "Captured evidence cannot have "
            "missing_reason_code"
        )

    if (
        dmrv.loc[
            missing_mask,
            "missing_reason_code",
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Missing evidence requires "
            "missing_reason_code"
        )

    observed_missing_reason_codes = set(
        dmrv.loc[
            missing_mask,
            "missing_reason_code",
        ]
        .dropna()
        .astype(str)
    )

    invalid_missing_reasons = (
        observed_missing_reason_codes
        -
        VALID_MISSING_REASON_CODES
    )

    if invalid_missing_reasons:
        raise ValueError(
            "Invalid dMRV missing-reason codes"
        )

    # ========================================================
    # EVIDENCE OBSERVED TIMESTAMP
    # ========================================================

    if (
        dmrv.loc[
            available_mask,
            "evidence_observed_at",
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Captured evidence requires "
            "evidence_observed_at"
        )

    if (
        dmrv.loc[
            missing_mask,
            "evidence_observed_at",
        ]
        .notna()
        .any()
    ):
        raise ValueError(
            "Missing evidence cannot have "
            "evidence_observed_at"
        )

    # ========================================================
    # SUPPORT FLAG VALIDATION
    # ========================================================

    support_columns = (
        "source_reference_present",
        "evidence_attachment_present",
        "timestamp_verified",
        "digital_signature_present",
        "operator_identity_present",
        "chain_of_custody_present",
        "measurement_calibration_present",
    )

    for column in support_columns:
        if (
            ~dmrv[
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
                f"{column} must contain "
                "booleans only"
            )

    # When the primary evidence is completely missing,
    # no support artifacts should magically exist.

    for column in support_columns:
        if (
            dmrv.loc[
                missing_mask,
                column,
            ]
            .astype(bool)
            .any()
        ):
            raise ValueError(
                "Missing evidence cannot contain "
                f"support flag {column}=True"
            )

    # ========================================================
    # SOURCE SYSTEM / BASIS
    # ========================================================

    if (
        dmrv.loc[
            process_mask,
            "evidence_source_system",
        ]
        !=
        PROCESS_SOURCE_SYSTEM
    ).any():
        raise ValueError(
            "Process dMRV evidence must use "
            "RVSF_PROCESS_LOG"
        )

    if (
        dmrv.loc[
            mass_mask,
            "evidence_source_system",
        ]
        !=
        MASS_SOURCE_SYSTEM
    ).any():
        raise ValueError(
            "Mass dMRV evidence must use "
            "RVSF_WEIGHBRIDGE"
        )

    if (
        dmrv.loc[
            process_mask,
            "measurement_basis",
        ]
        !=
        PROCESS_MEASUREMENT_BASIS
    ).any():
        raise ValueError(
            "Invalid process measurement basis"
        )

    if (
        dmrv.loc[
            mass_mask,
            "measurement_basis",
        ]
        !=
        MASS_MEASUREMENT_BASIS
    ).any():
        raise ValueError(
            "Invalid mass measurement basis"
        )

    # ========================================================
    # SOURCE REFERENCE
    # ========================================================

    for record in dmrv.itertuples(
        index=False
    ):
        source_job = (
            job_lookup.loc[
                str(
                    record.rvsf_job_card_id
                )
            ]
        )

        if (
            record.evidence_type
            ==
            PROCESS_EXECUTION_EVIDENCE
        ):
            expected_reference = str(
                record.rvsf_job_card_id
            )

        else:
            expected_reference = str(
                source_job[
                    "weighbridge_ticket_id"
                ]
            )

        if bool(
            record.source_reference_present
        ):
            if pd.isna(
                record.source_reference_id
            ):
                raise ValueError(
                    f"{record.dmrv_record_id}: "
                    "source reference flagged present "
                    "but ID is missing"
                )

            if (
                str(
                    record.source_reference_id
                )
                !=
                expected_reference
            ):
                raise ValueError(
                    f"{record.dmrv_record_id}: "
                    "source_reference_id mismatch"
                )

        else:
            if not pd.isna(
                record.source_reference_id
            ):
                raise ValueError(
                    f"{record.dmrv_record_id}: "
                    "source_reference_id exists while "
                    "source_reference_present=False"
                )

    # ========================================================
    # TYPE-SPECIFIC NULLABILITY
    # ========================================================

    # Process evidence must never carry mass measurements.

    if (
        dmrv.loc[
            process_mask,
            MASS_MEASUREMENT_COLUMNS,
        ]
        .notna()
        .any()
        .any()
    ):
        raise ValueError(
            "Process evidence contains non-applicable "
            "mass measurements"
        )

    # Mass evidence must never carry process measurements.

    if (
        dmrv.loc[
            mass_mask,
            PROCESS_MEASUREMENT_COLUMNS,
        ]
        .notna()
        .any()
        .any()
    ):
        raise ValueError(
            "Mass evidence contains non-applicable "
            "process measurements"
        )

    # ========================================================
    # AVAILABLE PROCESS EVIDENCE MUST MATCH SOURCE JOB
    # ========================================================

    available_process = (
        dmrv.loc[
            process_mask
            &
            available_mask
        ]
    )

    process_source_map = {
        "observed_processing_duration_minutes":
            "processing_duration_minutes",

        "observed_labor_hours":
            "labor_hours",

        "observed_energy_consumed_kwh":
            "energy_consumed_kwh",

        "observed_water_consumed_liters":
            "water_consumed_liters",
    }

    for record in (
        available_process
        .itertuples(
            index=False
        )
    ):
        source_job = (
            job_lookup.loc[
                str(
                    record.rvsf_job_card_id
                )
            ]
        )

        for (
            dmrv_column,
            source_column,
        ) in process_source_map.items():

            actual_value = float(
                getattr(
                    record,
                    dmrv_column,
                )
            )

            expected_value = float(
                source_job[
                    source_column
                ]
            )

            if not np.isclose(
                actual_value,
                expected_value,
                atol=0.001,
            ):
                raise ValueError(
                    f"{record.dmrv_record_id}: "
                    f"{dmrv_column} does not match "
                    "RVSF source"
                )

    # ========================================================
    # MISSING PROCESS EVIDENCE MUST HAVE NO VALUES
    # ========================================================

    if (
        dmrv.loc[
            process_mask
            &
            missing_mask,
            PROCESS_MEASUREMENT_COLUMNS,
        ]
        .notna()
        .any()
        .any()
    ):
        raise ValueError(
            "Missing process evidence contains "
            "measurement values"
        )

    # ========================================================
    # AVAILABLE MASS EVIDENCE MUST MATCH SOURCE JOB
    # ========================================================

    available_mass = (
        dmrv.loc[
            mass_mask
            &
            available_mask
        ]
    )

    mass_source_map = {
        "observed_stage_input_mass_kg":
            "stage_input_mass_kg",

        "observed_battery_recovered_mass_kg":
            "battery_recovered_mass_kg",

        "observed_tyre_recovered_mass_kg":
            "tyre_recovered_mass_kg",

        "observed_catalytic_converter_mass_kg":
            "catalytic_converter_mass_kg",

        "observed_hazardous_fluid_liters":
            "hazardous_fluid_liters",

        "observed_hazardous_fluid_mass_kg":
            "hazardous_fluid_mass_kg",

        "observed_removed_component_mass_kg":
            "removed_component_mass_kg",

        "observed_reusable_parts_mass_kg":
            "reusable_parts_mass_kg",

        "observed_recyclable_material_mass_kg":
            "recyclable_material_mass_kg",

        "observed_residual_waste_mass_kg":
            "residual_waste_mass_kg",

        "observed_transferred_to_next_stage_kg":
            "transferred_to_next_stage_kg",
    }

    for record in (
        available_mass
        .itertuples(
            index=False
        )
    ):
        source_job = (
            job_lookup.loc[
                str(
                    record.rvsf_job_card_id
                )
            ]
        )

        for (
            dmrv_column,
            source_column,
        ) in mass_source_map.items():

            actual_value = float(
                getattr(
                    record,
                    dmrv_column,
                )
            )

            expected_value = float(
                source_job[
                    source_column
                ]
            )

            if not np.isclose(
                actual_value,
                expected_value,
                atol=0.001,
            ):
                raise ValueError(
                    f"{record.dmrv_record_id}: "
                    f"{dmrv_column} does not match "
                    "RVSF source"
                )

    # ========================================================
    # MISSING MASS EVIDENCE MUST HAVE NO VALUES
    # ========================================================

    if (
        dmrv.loc[
            mass_mask
            &
            missing_mask,
            MASS_MEASUREMENT_COLUMNS,
        ]
        .notna()
        .any()
        .any()
    ):
        raise ValueError(
            "Missing mass evidence contains "
            "measurement values"
        )

    # ========================================================
    # NONNEGATIVE AVAILABLE MEASUREMENTS
    # ========================================================

    all_measurement_columns = (
        PROCESS_MEASUREMENT_COLUMNS
        +
        MASS_MEASUREMENT_COLUMNS
    )

    for column in (
        all_measurement_columns
    ):
        values = pd.to_numeric(
            dmrv[
                column
            ],
            errors="coerce",
        )

        if (
            values
            .dropna()
            .lt(0)
            .any()
        ):
            raise ValueError(
                f"{column} cannot be negative"
            )

    # ========================================================
    # AVAILABLE MASS-BALANCE EVIDENCE
    # ========================================================

    available_dep_mass = (
        available_mass.loc[
            available_mass[
                "job_type"
            ]
            ==
            "DEPOLLUTION_AND_SAFETY"
        ]
    )

    if not available_dep_mass.empty:
        depollution_accounted = (
            available_dep_mass[
                "observed_removed_component_mass_kg"
            ]
            +
            available_dep_mass[
                "observed_hazardous_fluid_mass_kg"
            ]
            +
            available_dep_mass[
                "observed_transferred_to_next_stage_kg"
            ]
        )

        depollution_error = (
            available_dep_mass[
                "observed_stage_input_mass_kg"
            ]
            -
            depollution_accounted
        ).abs()

        if (
            depollution_error
            >
            0.05
        ).any():
            raise ValueError(
                "dMRV depollution mass evidence "
                "fails mass balance"
            )

    available_dis_mass = (
        available_mass.loc[
            available_mass[
                "job_type"
            ]
            ==
            "DISMANTLING_AND_RECOVERY"
        ]
    )

    if not available_dis_mass.empty:
        dismantling_accounted = (
            available_dis_mass[
                "observed_reusable_parts_mass_kg"
            ]
            +
            available_dis_mass[
                "observed_recyclable_material_mass_kg"
            ]
            +
            available_dis_mass[
                "observed_residual_waste_mass_kg"
            ]
        )

        dismantling_error = (
            available_dis_mass[
                "observed_stage_input_mass_kg"
            ]
            -
            dismantling_accounted
        ).abs()

        if (
            dismantling_error
            >
            0.05
        ).any():
            raise ValueError(
                "dMRV dismantling mass evidence "
                "fails mass balance"
            )

    # ========================================================
    # PROVENANCE
    # ========================================================

    if (
        dmrv[
            "data_origin"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "dMRV records contain missing data_origin"
        )

    if (
        dmrv[
            "generator_version"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "dMRV records contain missing "
            "generator_version"
        )

    # ========================================================
    # HIDDEN RUNTIME / TRUTH LEAKAGE
    # ========================================================

    leaked_columns = (
        HIDDEN_RUNTIME_COLUMNS
        &
        set(
            dmrv.columns
        )
    )

    if leaked_columns:
        raise ValueError(
            "Hidden runtime / ground-truth fields "
            "leaked into dMRV records: "
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


def generate_dmrv(
    rvsf_job_cards: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Convenience alias.
    """

    return generate_dmrv_records(
        rvsf_job_cards=
            rvsf_job_cards,

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

    from data.generators.circularity.rvsf import (
        generate_rvsf_job_cards,
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
    # UPSTREAM DEPENDENCY CHAIN
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

    rvsf_df = (
        generate_rvsf_job_cards(
            elv_assessments=
                elv_df,

            generation=
                generation_config,
        )
    )

    # ========================================================
    # DEPENDENCY CHECK
    # ========================================================

    print(
        "\n=== dMRV DEPENDENCY CHECK ===\n"
    )

    print(
        "ELV assessments:",
        len(
            elv_df
        ),
    )

    print(
        "RVSF job cards:",
        len(
            rvsf_df
        ),
    )

    print(
        "Configured dMRV records:",
        _get_dmrv_target_count(
            generation_config
        ),
    )

    # ========================================================
    # GENERATE
    # ========================================================

    dmrv_df = (
        generate_dmrv_records(
            rvsf_job_cards=
                rvsf_df,

            generation=
                generation_config,
        )
    )

    # ========================================================
    # SAMPLE
    # ========================================================

    print(
        "\n=== dMRV SAMPLE ===\n"
    )

    sample_columns = [
        "dmrv_record_id",

        "rvsf_job_card_id",
        "elv_assessment_id",

        "evidence_sequence",
        "evidence_type",

        "job_type",

        "city_name",

        "dmrv_recorded_at",

        "evidence_source_system",

        "evidence_available",
        "evidence_status",

        "source_reference_present",
        "evidence_attachment_present",
        "timestamp_verified",
        "digital_signature_present",
        "operator_identity_present",
        "chain_of_custody_present",
        "measurement_calibration_present",

        "observed_processing_duration_minutes",
        "observed_energy_consumed_kwh",

        "observed_stage_input_mass_kg",
        "observed_reusable_parts_mass_kg",
        "observed_recyclable_material_mass_kg",
        "observed_residual_waste_mass_kg",

        "missing_reason_code",
    ]

    print(
        dmrv_df[
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
    # EVIDENCE TYPE MIX
    # ========================================================

    print(
        "\n=== dMRV EVIDENCE TYPE MIX ===\n"
    )

    evidence_type_summary = (
        dmrv_df[
            "evidence_type"
        ]
        .value_counts()
        .rename_axis(
            "evidence_type"
        )
        .reset_index(
            name="records"
        )
    )

    evidence_type_summary[
        "rate"
    ] = (
        evidence_type_summary[
            "records"
        ]
        /
        len(
            dmrv_df
        )
    ).round(
        4
    )

    print(
        evidence_type_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # EVIDENCE AVAILABILITY
    # ========================================================

    print(
        "\n=== dMRV EVIDENCE AVAILABILITY ===\n"
    )

    availability_summary = (
        dmrv_df
        .groupby(
            "evidence_type",
            as_index=False,
        )
        .agg(
            records=(
                "dmrv_record_id",
                "size",
            ),

            evidence_available_rate=(
                "evidence_available",
                "mean",
            ),

            source_reference_rate=(
                "source_reference_present",
                "mean",
            ),

            attachment_rate=(
                "evidence_attachment_present",
                "mean",
            ),

            timestamp_verified_rate=(
                "timestamp_verified",
                "mean",
            ),

            digital_signature_rate=(
                "digital_signature_present",
                "mean",
            ),

            operator_identity_rate=(
                "operator_identity_present",
                "mean",
            ),

            chain_of_custody_rate=(
                "chain_of_custody_present",
                "mean",
            ),

            calibration_evidence_rate=(
                "measurement_calibration_present",
                "mean",
            ),
        )
    )

    rate_columns = [
        column
        for column in (
            availability_summary.columns
        )
        if (
            column.endswith(
                "_rate"
            )
        )
    ]

    for column in rate_columns:
        availability_summary[
            column
        ] = (
            availability_summary[
                column
            ]
            .round(
                4
            )
        )

    print(
        availability_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # MISSING REASONS
    # ========================================================

    print(
        "\n=== dMRV MISSING EVIDENCE REASONS ===\n"
    )

    missing_records = (
        dmrv_df.loc[
            ~dmrv_df[
                "evidence_available"
            ]
        ]
    )

    if missing_records.empty:
        print(
            "No missing evidence records generated."
        )

    else:
        missing_summary = (
            missing_records[
                "missing_reason_code"
            ]
            .value_counts()
            .rename_axis(
                "missing_reason_code"
            )
            .reset_index(
                name="records"
            )
        )

        print(
            missing_summary
            .to_string(
                index=False
            )
        )

    # ========================================================
    # SOURCE QC RELATIONSHIP
    # ========================================================

    print(
        "\n=== dMRV AVAILABILITY BY SOURCE QC ===\n"
    )

    qc_summary = (
        dmrv_df
        .groupby(
            [
                "source_job_quality_check_passed",
                "evidence_type",
            ],
            as_index=False,
        )
        .agg(
            records=(
                "dmrv_record_id",
                "size",
            ),

            evidence_available_rate=(
                "evidence_available",
                "mean",
            ),
        )
    )

    qc_summary[
        "evidence_available_rate"
    ] = (
        qc_summary[
            "evidence_available_rate"
        ]
        .round(
            4
        )
    )

    print(
        qc_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # PROCESS EVIDENCE
    # ========================================================

    process_evidence = (
        dmrv_df.loc[
            (
                dmrv_df[
                    "evidence_type"
                ]
                ==
                PROCESS_EXECUTION_EVIDENCE
            )
            &
            (
                dmrv_df[
                    "evidence_available"
                ]
            )
        ]
        .copy()
    )

    print(
        "\n=== dMRV PROCESS EVIDENCE ===\n"
    )

    print(
        "Available process records:",
        len(
            process_evidence
        ),
    )

    if not process_evidence.empty:
        print(
            "Average processing duration minutes:",
            round(
                float(
                    process_evidence[
                        "observed_processing_duration_minutes"
                    ]
                    .mean()
                ),
                2,
            ),
        )

        print(
            "Average labor hours:",
            round(
                float(
                    process_evidence[
                        "observed_labor_hours"
                    ]
                    .mean()
                ),
                2,
            ),
        )

        print(
            "Average energy consumed kWh:",
            round(
                float(
                    process_evidence[
                        "observed_energy_consumed_kwh"
                    ]
                    .mean()
                ),
                2,
            ),
        )

        print(
            "Average water consumed liters:",
            round(
                float(
                    process_evidence[
                        "observed_water_consumed_liters"
                    ]
                    .mean()
                ),
                2,
            ),
        )

    # ========================================================
    # MASS EVIDENCE
    # ========================================================

    mass_evidence = (
        dmrv_df.loc[
            (
                dmrv_df[
                    "evidence_type"
                ]
                ==
                MATERIAL_MASS_BALANCE_EVIDENCE
            )
            &
            (
                dmrv_df[
                    "evidence_available"
                ]
            )
        ]
        .copy()
    )

    print(
        "\n=== dMRV MASS EVIDENCE ===\n"
    )

    print(
        "Available mass records:",
        len(
            mass_evidence
        ),
    )

    if not mass_evidence.empty:
        print(
            "Average stage input mass kg:",
            round(
                float(
                    mass_evidence[
                        "observed_stage_input_mass_kg"
                    ]
                    .mean()
                ),
                2,
            ),
        )

        print(
            "Average reusable-parts mass kg:",
            round(
                float(
                    mass_evidence[
                        "observed_reusable_parts_mass_kg"
                    ]
                    .mean()
                ),
                2,
            ),
        )

        print(
            "Average recyclable-material mass kg:",
            round(
                float(
                    mass_evidence[
                        "observed_recyclable_material_mass_kg"
                    ]
                    .mean()
                ),
                2,
            ),
        )

        print(
            "Average residual-waste mass kg:",
            round(
                float(
                    mass_evidence[
                        "observed_residual_waste_mass_kg"
                    ]
                    .mean()
                ),
                2,
            ),
        )

    # ========================================================
    # EVIDENCE COVERAGE BY JOB
    #
    # This is raw evidence coverage only.
    # It is NOT verification readiness.
    # ========================================================

    print(
        "\n=== dMRV JOB EVIDENCE COVERAGE ===\n"
    )

    job_evidence_coverage = (
        dmrv_df
        .groupby(
            "rvsf_job_card_id"
        )[
            "evidence_available"
        ]
        .agg(
            [
                "sum",
                "count",
            ]
        )
    )

    complete_evidence_jobs = int(
        (
            job_evidence_coverage[
                "sum"
            ]
            ==
            2
        ).sum()
    )

    one_missing_jobs = int(
        (
            job_evidence_coverage[
                "sum"
            ]
            ==
            1
        ).sum()
    )

    both_missing_jobs = int(
        (
            job_evidence_coverage[
                "sum"
            ]
            ==
            0
        ).sum()
    )

    print(
        "Jobs with both evidence records available:",
        complete_evidence_jobs,
    )

    print(
        "Jobs with one evidence record missing:",
        one_missing_jobs,
    )

    print(
        "Jobs with both evidence records missing:",
        both_missing_jobs,
    )

    print(
        "Jobs with at least one missing evidence record:",
        one_missing_jobs
        +
        both_missing_jobs,
    )

    # ========================================================
    # SUPPORTING EVIDENCE DISTRIBUTION
    # ========================================================

    print(
        "\n=== dMRV SUPPORTING EVIDENCE ===\n"
    )

    for column in (
        "source_reference_present",
        "evidence_attachment_present",
        "timestamp_verified",
        "digital_signature_present",
        "operator_identity_present",
        "chain_of_custody_present",
        "measurement_calibration_present",
    ):
        print(
            f"{column}:",
            round(
                float(
                    dmrv_df[
                        column
                    ]
                    .mean()
                ),
                4,
            ),
        )

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    print(
        "\n=== dMRV VALIDATION ===\n"
    )

    print(
        "Rows:",
        len(
            dmrv_df
        ),
    )

    print(
        "Unique dMRV record IDs:",
        dmrv_df[
            "dmrv_record_id"
        ]
        .nunique(),
    )

    print(
        "RVSF job cards represented:",
        dmrv_df[
            "rvsf_job_card_id"
        ]
        .nunique(),
    )

    records_per_job = (
        dmrv_df
        .groupby(
            "rvsf_job_card_id"
        )
        .size()
    )

    print(
        "Minimum dMRV records/job:",
        int(
            records_per_job.min()
        ),
    )

    print(
        "Maximum dMRV records/job:",
        int(
            records_per_job.max()
        ),
    )

    print(
        "ELV assessments represented:",
        dmrv_df[
            "elv_assessment_id"
        ]
        .nunique(),
    )

    print(
        "Facilities represented:",
        dmrv_df[
            "rvsf_facility_id"
        ]
        .nunique(),
    )

    print(
        "Regions represented:",
        dmrv_df[
            "region_id"
        ]
        .nunique(),
    )

    print(
        "Duplicate dMRV record IDs:",
        int(
            dmrv_df[
                "dmrv_record_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Missing RVSF job-card IDs:",
        int(
            dmrv_df[
                "rvsf_job_card_id"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Evidence missing records:",
        int(
            (
                ~dmrv_df[
                    "evidence_available"
                ]
            ).sum()
        ),
    )

    print(
        "Hidden truth/runtime leakage:",
        sorted(
            HIDDEN_RUNTIME_COLUMNS
            &
            set(
                dmrv_df.columns
            )
        ),
    )

    print(
        "\nGenerated "
        f"{len(dmrv_df)} "
        "synthetic dMRV evidence records successfully."
    )