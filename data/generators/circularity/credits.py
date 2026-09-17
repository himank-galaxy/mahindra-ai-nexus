"""
Synthetic Carbon Credit Marketplace Listing Generator
for Mahindra AI Nexus.

============================================================
PURPOSE
============================================================

Generate operational sustainability / carbon-credit marketplace
listing records from the validated Circularity evidence chain:

    ELV Assessment
        ↓
    RVSF Operations
        ↓
    dMRV Evidence
        ↓
    Carbon Credit Marketplace Listing


============================================================
CURRENT GENERATION MODEL
============================================================

One marketplace listing is generated per ELV vehicle.

Configured upstream:

    750 ELV assessments
    1,500 RVSF job cards
    3,000 dMRV evidence records

Configured output:

    750 carbon-credit listings


Each ELV therefore contributes:

    1 ELV assessment
    2 RVSF jobs
    4 dMRV evidence records
    1 marketplace listing


============================================================
CRITICAL ARCHITECTURAL RULE
============================================================

This generator creates MARKETPLACE / OPERATIONAL EVIDENCE.

It may contain:

    seller-entered claimed carbon quantity
    seller asking price
    observed market reference price
    buyer inquiry count
    buyer bid count
    highest observed bid
    RVSF recovery quantities
    raw dMRV evidence counts
    listing timestamps

It MUST NOT contain:

    predicted price band
    recommended price
    buyer match
    buyer-match score
    closure probability
    predicted closure
    true closure outcome
    true closure price
    final traceability score
    verification readiness score
    dMRV completeness score
    AI recommendation
    AI confidence

Those belong to either:

    Runtime Application Data

or:

    Ground Truth / Evaluation Data


============================================================
SELLER CLAIM VS MODEL ESTIMATE
============================================================

seller_claimed_quantity_tco2e is an operational marketplace
field.

It represents a synthetic seller-entered claim based on the
facility's recovery records.

It is NOT:

    verified carbon quantity
    true avoided emissions
    AI-estimated carbon credits
    ground truth

The runtime application can independently estimate the
supported quantity from RVSF + dMRV evidence and compare it
with the seller claim.


============================================================
ENGINEERING ASSUMPTIONS
============================================================

The carbon conversion factors and market prices in this file
are synthetic engineering parameters created only to form an
internally consistent test world.

They are NOT:

    Mahindra statistics
    statutory carbon-credit factors
    certified methodology factors
    market forecasts
    regulatory guidance


============================================================
OUTPUT
============================================================

Returns a pandas DataFrame.

No CSV writes occur inside this module.
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
# CREDIT TYPES
#
# Synthetic marketplace product categories.
# These are NOT names of regulatory methodologies.
# ============================================================

REUSE_AVOIDANCE = "REUSE_AVOIDANCE"

RECYCLING_AVOIDANCE = "RECYCLING_AVOIDANCE"

MIXED_CIRCULARITY = "MIXED_CIRCULARITY"

VALID_CREDIT_TYPES = {
    REUSE_AVOIDANCE,
    RECYCLING_AVOIDANCE,
    MIXED_CIRCULARITY,
}


# ============================================================
# LISTING STATUS
#
# Actual credit closure is deliberately NOT generated here.
# All records represent marketplace listings that are open at
# their observation point.
# ============================================================

LISTING_STATUS_OPEN = "OPEN"

VALID_LISTING_STATUSES = {
    LISTING_STATUS_OPEN,
}


# ============================================================
# CREDIT UNIT
# ============================================================

CREDIT_UNIT = "TCO2E"


# ============================================================
# SELLER CLAIM BASIS
# ============================================================

CLAIM_BASIS = (
    "RVSF_RECOVERY_MASS_AND_PROCESS_ENERGY"
)

CLAIM_BASIS_VERSION = (
    "SYNTHETIC_CARBON_CLAIM_V1"
)


# ============================================================
# SYNTHETIC CARBON CONVERSION FACTORS
#
# kg CO2e claimed benefit per kg of recovered material.
#
# Development assumptions only.
# ============================================================

REUSABLE_PARTS_FACTOR_KGCO2E_PER_KG = 1.10

RECYCLABLE_MATERIAL_FACTOR_KGCO2E_PER_KG = 0.65

BATTERY_RECOVERY_FACTOR_KGCO2E_PER_KG = 1.60

TYRE_RECOVERY_FACTOR_KGCO2E_PER_KG = 0.45

CATALYTIC_RECOVERY_FACTOR_KGCO2E_PER_KG = 2.00


# ============================================================
# PROCESS-BURDEN FACTORS
#
# Synthetic engineering assumptions.
# ============================================================

ELECTRICITY_FACTOR_KGCO2E_PER_KWH = 0.70

WATER_FACTOR_KGCO2E_PER_LITER = 0.0004


# ============================================================
# SYNTHETIC MARKET REFERENCE PRICES
#
# INR / tCO2e
#
# Engineering assumptions only.
# ============================================================

BASE_MARKET_PRICE_INR = {
    REUSE_AVOIDANCE: 2200.0,
    RECYCLING_AVOIDANCE: 1600.0,
    MIXED_CIRCULARITY: 1900.0,
}


# ============================================================
# REQUIRED UPSTREAM CARDINALITIES
# ============================================================

RVSF_JOBS_PER_ELV = 2

DMRV_RECORDS_PER_RVSF_JOB = 2

DMRV_RECORDS_PER_ELV = (
    RVSF_JOBS_PER_ELV
    *
    DMRV_RECORDS_PER_RVSF_JOB
)


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

    "condition_score",

    "document_completeness",
    "traceability_score",

    "estimated_vehicle_mass_kg",

    "assessed_reusable_parts_pct",
    "assessed_recyclable_material_pct",

    "data_origin",
    "generator_version",
}


# ============================================================
# REQUIRED RVSF SCHEMA
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

    "rvsf_facility_id",
    "rvsf_facility_name",

    "city_id",
    "city_name",

    "region_id",
    "region_name",

    "processing_started_at",
    "processing_completed_at",

    "stage_input_mass_kg",

    "battery_recovered_mass_kg",
    "tyre_recovered_mass_kg",
    "catalytic_converter_mass_kg",

    "hazardous_fluid_mass_kg",

    "removed_component_mass_kg",

    "reusable_parts_mass_kg",
    "recyclable_material_mass_kg",
    "residual_waste_mass_kg",

    "transferred_to_next_stage_kg",

    "energy_consumed_kwh",
    "water_consumed_liters",

    "quality_check_passed",

    "job_status",

    "data_origin",
    "generator_version",
}


# ============================================================
# REQUIRED dMRV SCHEMA
# ============================================================

DMRV_REQUIRED_COLUMNS: set[str] = {
    "dmrv_record_id",

    "rvsf_job_card_id",
    "elv_assessment_id",
    "elv_vehicle_id",

    "evidence_sequence",
    "evidence_type",

    "dmrv_recorded_at",

    "evidence_available",
    "evidence_status",

    "source_reference_present",
    "evidence_attachment_present",
    "timestamp_verified",
    "digital_signature_present",
    "operator_identity_present",
    "chain_of_custody_present",
    "measurement_calibration_present",

    "source_job_quality_check_passed",

    "data_origin",
    "generator_version",
}


# ============================================================
# FORBIDDEN RUNTIME / GROUND-TRUTH OUTPUTS
# ============================================================

HIDDEN_RUNTIME_COLUMNS = {
    # --------------------------------------------
    # UI / predictive pricing
    # --------------------------------------------

    "price_band",
    "predicted_price_band",

    "recommended_price",
    "recommended_price_inr",

    "predicted_price",
    "predicted_price_inr",

    "fair_value",
    "fair_value_inr",

    # --------------------------------------------
    # Buyer matching
    # --------------------------------------------

    "buyer_match",
    "buyer_match_score",

    "recommended_buyer",

    "matched_buyer_id",
    "matched_buyer_name",

    # --------------------------------------------
    # Closure prediction
    # --------------------------------------------

    "closure_probability",
    "predicted_closure_probability",

    "predicted_credit_closed",
    "predicted_closure",

    # --------------------------------------------
    # Actual / ground-truth closure outcome
    # --------------------------------------------

    "credit_closed",
    "closure_outcome",

    "credit_closure_price",
    "credit_closure_price_inr",

    "closed_at",
    "closure_at",

    "true_credit_closed",
    "true_closure_price",
    "true_closure_price_inr",

    # --------------------------------------------
    # Final evidence-derived scores
    # --------------------------------------------

    "traceability_score",
    "final_traceability_score",

    "dmrv_completeness",
    "dmrv_completeness_score",

    "evidence_sufficiency",
    "evidence_sufficiency_score",

    "verification_readiness",
    "verification_readiness_score",

    "verification_ready",

    # --------------------------------------------
    # AI outputs
    # --------------------------------------------

    "recommended_action",

    "confidence",
    "confidence_score",

    "model_score",
    "model_probability",

    "risk_score",
    "risk_band",

    # --------------------------------------------
    # Carbon truth / AI estimate
    # --------------------------------------------

    "estimated_carbon_credits",
    "predicted_carbon_credits",

    "verified_carbon_quantity_tco2e",
    "true_carbon_quantity_tco2e",
}


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
    Return configured generation-window boundaries.
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
# CONFIGURED TARGET COUNT
# ============================================================


def _get_credit_listing_target_count(
    generation: Mapping[str, Any],
) -> int:
    """
    Read:

        circularity:
            carbon_credit_listings:
                count: 750
    """

    try:
        target_count = int(
            generation[
                "circularity"
            ][
                "carbon_credit_listings"
            ][
                "count"
            ]
        )

    except KeyError as exc:
        raise KeyError(
            "Missing generation.circularity."
            "carbon_credit_listings.count"
        ) from exc

    if target_count <= 0:
        raise ValueError(
            "carbon_credit_listings.count must be > 0"
        )

    return target_count


# ============================================================
# BOOLEAN NORMALIZATION
# ============================================================


def _to_bool_series(
    series: pd.Series,
) -> pd.Series:
    """
    Normalize boolean-like source columns.
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
# PREPARE ELV
# ============================================================


def _prepare_elv_assessments(
    elv_assessments: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate frozen ELV input.
    """

    if elv_assessments.empty:
        raise ValueError(
            "ELV assessments DataFrame cannot be empty"
        )

    missing = (
        ELV_REQUIRED_COLUMNS
        -
        set(
            elv_assessments.columns
        )
    )

    if missing:
        raise ValueError(
            "ELV assessments missing columns: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    result = (
        elv_assessments
        .copy(
            deep=True
        )
    )

    if (
        result[
            "elv_assessment_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "ELV assessments contain missing IDs"
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
            "Credit listing generation requires "
            "completed ELV assessments"
        )

    numeric_columns = (
        "condition_score",
        "document_completeness",
        "traceability_score",
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
# PREPARE RVSF
# ============================================================


def _prepare_rvsf_job_cards(
    rvsf_job_cards: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate frozen RVSF input.
    """

    if rvsf_job_cards.empty:
        raise ValueError(
            "RVSF job cards DataFrame cannot be empty"
        )

    missing = (
        RVSF_REQUIRED_COLUMNS
        -
        set(
            rvsf_job_cards.columns
        )
    )

    if missing:
        raise ValueError(
            "RVSF job cards missing columns: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    result = (
        rvsf_job_cards
        .copy(
            deep=True
        )
    )

    if (
        result[
            "rvsf_job_card_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "RVSF job cards contain missing IDs"
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
            "Credit listing generation requires "
            "completed RVSF jobs"
        )

    timestamp_columns = (
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

    numeric_columns = (
        "stage_input_mass_kg",

        "battery_recovered_mass_kg",
        "tyre_recovered_mass_kg",
        "catalytic_converter_mass_kg",

        "hazardous_fluid_mass_kg",

        "removed_component_mass_kg",

        "reusable_parts_mass_kg",
        "recyclable_material_mass_kg",
        "residual_waste_mass_kg",

        "transferred_to_next_stage_kg",

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
                f"RVSF {column} cannot be negative"
            )

    result[
        "quality_check_passed"
    ] = (
        _to_bool_series(
            result[
                "quality_check_passed"
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
# PREPARE dMRV
# ============================================================


def _prepare_dmrv_records(
    dmrv_records: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate frozen dMRV input.
    """

    if dmrv_records.empty:
        raise ValueError(
            "dMRV records DataFrame cannot be empty"
        )

    missing = (
        DMRV_REQUIRED_COLUMNS
        -
        set(
            dmrv_records.columns
        )
    )

    if missing:
        raise ValueError(
            "dMRV records missing columns: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    result = (
        dmrv_records
        .copy(
            deep=True
        )
    )

    if (
        result[
            "dmrv_record_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "dMRV records contain missing IDs"
        )

    if (
        result[
            "dmrv_record_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate dmrv_record_id values found"
        )

    result[
        "dmrv_recorded_at"
    ] = pd.to_datetime(
        result[
            "dmrv_recorded_at"
        ],
        utc=True,
    )

    boolean_columns = (
        "evidence_available",
        "source_reference_present",
        "evidence_attachment_present",
        "timestamp_verified",
        "digital_signature_present",
        "operator_identity_present",
        "chain_of_custody_present",
        "measurement_calibration_present",
        "source_job_quality_check_passed",
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
                "dmrv_recorded_at",
                "dmrv_record_id",
            ]
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# CREDIT TYPE
# ============================================================


def _derive_credit_type(
    reusable_parts_mass_kg: float,
    recyclable_material_mass_kg: float,
    stage_input_mass_kg: float,
) -> str:
    """
    Derive marketplace claim category from actual RVSF mass
    flows.

    This is product categorization, not an AI prediction.
    """

    if stage_input_mass_kg <= 0:
        raise ValueError(
            "stage_input_mass_kg must be positive"
        )

    reusable_fraction = (
        reusable_parts_mass_kg
        /
        stage_input_mass_kg
    )

    recyclable_fraction = (
        recyclable_material_mass_kg
        /
        stage_input_mass_kg
    )

    if reusable_fraction >= 0.40:
        return REUSE_AVOIDANCE

    if recyclable_fraction >= 0.53:
        return RECYCLING_AVOIDANCE

    return MIXED_CIRCULARITY


# ============================================================
# SELLER-CLAIMED CARBON QUANTITY
# ============================================================


def _seller_claimed_quantity_tco2e(
    rng: np.random.Generator,
    reusable_parts_mass_kg: float,
    recyclable_material_mass_kg: float,
    battery_mass_kg: float,
    tyre_mass_kg: float,
    catalytic_mass_kg: float,
    total_energy_kwh: float,
    total_water_liters: float,
) -> float:
    """
    Create the seller-entered marketplace carbon claim.

    This is NOT verified quantity or ground truth.
    """

    gross_claim_kgco2e = (
        reusable_parts_mass_kg
        *
        REUSABLE_PARTS_FACTOR_KGCO2E_PER_KG

        +
        recyclable_material_mass_kg
        *
        RECYCLABLE_MATERIAL_FACTOR_KGCO2E_PER_KG

        +
        battery_mass_kg
        *
        BATTERY_RECOVERY_FACTOR_KGCO2E_PER_KG

        +
        tyre_mass_kg
        *
        TYRE_RECOVERY_FACTOR_KGCO2E_PER_KG

        +
        catalytic_mass_kg
        *
        CATALYTIC_RECOVERY_FACTOR_KGCO2E_PER_KG
    )

    process_burden_kgco2e = (
        total_energy_kwh
        *
        ELECTRICITY_FACTOR_KGCO2E_PER_KWH

        +
        total_water_liters
        *
        WATER_FACTOR_KGCO2E_PER_LITER
    )

    net_claim_kgco2e = max(
        50.0,
        gross_claim_kgco2e
        -
        process_burden_kgco2e,
    )

    # Seller reporting / measurement variation.
    claim_reporting_factor = float(
        np.clip(
            rng.normal(
                loc=1.0,
                scale=0.035,
            ),
            0.90,
            1.10,
        )
    )

    claimed_quantity_tco2e = (
        net_claim_kgco2e
        /
        1000.0
        *
        claim_reporting_factor
    )

    return round(
        max(
            0.05,
            claimed_quantity_tco2e,
        ),
        4,
    )


# ============================================================
# LISTING TIME
# ============================================================


def _build_listing_at(
    rng: np.random.Generator,
    latest_dmrv_at: pd.Timestamp,
    generation_end_utc: pd.Timestamp,
) -> pd.Timestamp:
    """
    Place marketplace listing after latest dMRV record and
    before generation cutoff.
    """

    latest = pd.Timestamp(
        latest_dmrv_at
    )

    end = pd.Timestamp(
        generation_end_utc
    )

    remaining_seconds = (
        end
        -
        latest
    ).total_seconds()

    if remaining_seconds <= 0:
        raise ValueError(
            "Latest dMRV record must occur before "
            "generation end"
        )

    preferred_delay_seconds = float(
        rng.uniform(
            1.0,
            36.0,
        )
        *
        3600.0
    )

    listing_delay_seconds = min(
        preferred_delay_seconds,
        remaining_seconds
        *
        0.50,
    )

    if listing_delay_seconds <= 0:
        listing_delay_seconds = (
            remaining_seconds
            *
            0.25
        )

    listing_at = (
        latest
        +
        pd.Timedelta(
            seconds=
                listing_delay_seconds
        )
    )

    if not (
        latest
        <
        listing_at
        <
        end
    ):
        raise ValueError(
            "Generated invalid credit-listing timestamp"
        )

    return listing_at


# ============================================================
# MARKET REFERENCE
# ============================================================


def _market_reference_price(
    rng: np.random.Generator,
    credit_type: str,
    listing_at: pd.Timestamp,
    generation_start: pd.Timestamp,
) -> float:
    """
    Generate an observed marketplace benchmark price.

    This is synthetic market data, not a prediction.
    """

    base_price = float(
        BASE_MARKET_PRICE_INR[
            credit_type
        ]
    )

    elapsed_days = (
        pd.Timestamp(
            listing_at
        )
        -
        pd.Timestamp(
            generation_start
        )
    ).total_seconds() / 86400.0

    # Slow synthetic market cycle.
    cycle_factor = (
        1.0
        +
        0.06
        *
        np.sin(
            elapsed_days
            /
            26.0
        )
    )

    market_noise = float(
        np.clip(
            rng.normal(
                loc=1.0,
                scale=0.055,
            ),
            0.82,
            1.18,
        )
    )

    value = (
        base_price
        *
        cycle_factor
        *
        market_noise
    )

    return round(
        float(
            np.clip(
                value,
                700.0,
                5000.0,
            )
        ),
        2,
    )


# ============================================================
# SELLER ASKING PRICE
# ============================================================


def _seller_asking_price(
    rng: np.random.Generator,
    market_reference_price: float,
    dmrv_available_fraction: float,
    source_traceability_score: float,
) -> float:
    """
    Generate operational asking price.

    Better evidence / traceability can support modest seller
    pricing premiums.

    This remains a seller-entered price, not recommended price.
    """

    evidence_premium = (
        0.055
        *
        dmrv_available_fraction
    )

    traceability_premium = (
        0.045
        *
        source_traceability_score
    )

    negotiation_markup = float(
        np.clip(
            rng.normal(
                loc=0.035,
                scale=0.065,
            ),
            -0.12,
            0.22,
        )
    )

    ask_factor = (
        0.94
        +
        evidence_premium
        +
        traceability_premium
        +
        negotiation_markup
    )

    asking_price = (
        market_reference_price
        *
        ask_factor
    )

    return round(
        float(
            np.clip(
                asking_price,
                600.0,
                6000.0,
            )
        ),
        2,
    )


# ============================================================
# MARKET ENGAGEMENT
# ============================================================


def _generate_market_engagement(
    rng: np.random.Generator,
    listing_at: pd.Timestamp,
    generation_end_utc: pd.Timestamp,
    seller_ask_price: float,
    market_reference_price: float,
    dmrv_available_fraction: float,
    source_traceability_score: float,
    claimed_quantity_tco2e: float,
) -> tuple[
    int,
    int,
    float,
]:
    """
    Generate observed marketplace activity.

    Returns:

        buyer_inquiry_count
        buyer_bid_count
        highest_bid_price_per_tco2e_inr

    Highest bid is NaN when no bid exists.

    These are observed market events, not buyer-match or
    closure predictions.
    """

    remaining_days = max(
        0.0,
        (
            pd.Timestamp(
                generation_end_utc
            )
            -
            pd.Timestamp(
                listing_at
            )
        ).total_seconds()
        /
        86400.0,
    )

    exposure_factor = float(
        np.clip(
            remaining_days
            /
            30.0,
            0.08,
            1.0,
        )
    )

    ask_reference_ratio = (
        seller_ask_price
        /
        market_reference_price
    )

    overpricing = max(
        0.0,
        ask_reference_ratio
        -
        1.0,
    )

    underpricing = max(
        0.0,
        1.0
        -
        ask_reference_ratio,
    )

    quantity_factor = float(
        np.clip(
            claimed_quantity_tco2e
            /
            1.25,
            0.50,
            1.60,
        )
    )

    inquiry_lambda = (
        0.65
        +
        2.10
        *
        dmrv_available_fraction

        +
        1.25
        *
        source_traceability_score

        +
        1.00
        *
        underpricing

        -
        2.30
        *
        overpricing
    )

    inquiry_lambda *= (
        exposure_factor
        *
        quantity_factor
    )

    inquiry_lambda = float(
        np.clip(
            inquiry_lambda,
            0.08,
            8.0,
        )
    )

    buyer_inquiry_count = int(
        np.clip(
            rng.poisson(
                inquiry_lambda
            ),
            0,
            18,
        )
    )

    if buyer_inquiry_count == 0:
        return (
            0,
            0,
            np.nan,
        )

    bid_probability = (
        0.12
        +
        0.30
        *
        dmrv_available_fraction

        +
        0.14
        *
        source_traceability_score

        +
        0.16
        *
        underpricing

        -
        0.30
        *
        overpricing
    )

    bid_probability = float(
        np.clip(
            bid_probability,
            0.04,
            0.72,
        )
    )

    buyer_bid_count = int(
        rng.binomial(
            n=
                buyer_inquiry_count,

            p=
                bid_probability,
        )
    )

    if buyer_bid_count == 0:
        return (
            buyer_inquiry_count,
            0,
            np.nan,
        )

    bid_center_factor = (
        0.98
        -
        0.08
        *
        overpricing
        +
        0.04
        *
        underpricing
    )

    bid_prices = (
        market_reference_price
        *
        rng.normal(
            loc=
                bid_center_factor,

            scale=
                0.055,

            size=
                buyer_bid_count,
        )
    )

    bid_prices = np.clip(
        bid_prices,
        market_reference_price
        *
        0.72,

        market_reference_price
        *
        1.20,
    )

    highest_bid = round(
        float(
            np.max(
                bid_prices
            )
        ),
        2,
    )

    return (
        buyer_inquiry_count,
        buyer_bid_count,
        highest_bid,
    )


# ============================================================
# MAIN GENERATOR
# ============================================================


def generate_carbon_credit_listings(
    elv_assessments: pd.DataFrame,
    rvsf_job_cards: pd.DataFrame,
    dmrv_records: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate synthetic marketplace carbon-credit listings.
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

    target_count = (
        _get_credit_listing_target_count(
            generation
        )
    )

    # ========================================================
    # PREPARE UPSTREAM INPUTS
    # ========================================================

    elv = (
        _prepare_elv_assessments(
            elv_assessments
        )
    )

    rvsf = (
        _prepare_rvsf_job_cards(
            rvsf_job_cards
        )
    )

    dmrv = (
        _prepare_dmrv_records(
            dmrv_records
        )
    )

    # ========================================================
    # ONE LISTING PER ELV
    # ========================================================

    if (
        target_count
        !=
        len(
            elv
        )
    ):
        raise ValueError(
            "Configured carbon-credit listing count "
            "must equal ELV assessment count for the "
            "one-listing-per-ELV model. "
            f"ELVs={len(elv)}, "
            f"configured_listings={target_count}"
        )

    # ========================================================
    # UPSTREAM CARDINALITY
    # ========================================================

    rvsf_counts = (
        rvsf
        .groupby(
            "elv_assessment_id"
        )
        .size()
    )

    if (
        set(
            rvsf_counts.index.astype(str)
        )
        !=
        set(
            elv[
                "elv_assessment_id"
            ]
            .astype(str)
        )
    ):
        raise ValueError(
            "RVSF ELV coverage does not match ELV master"
        )

    if (
        rvsf_counts
        !=
        RVSF_JOBS_PER_ELV
    ).any():
        raise ValueError(
            "Each ELV must have exactly "
            f"{RVSF_JOBS_PER_ELV} RVSF jobs"
        )

    dmrv_counts = (
        dmrv
        .groupby(
            "elv_assessment_id"
        )
        .size()
    )

    if (
        set(
            dmrv_counts.index.astype(str)
        )
        !=
        set(
            elv[
                "elv_assessment_id"
            ]
            .astype(str)
        )
    ):
        raise ValueError(
            "dMRV ELV coverage does not match ELV master"
        )

    if (
        dmrv_counts
        !=
        DMRV_RECORDS_PER_ELV
    ).any():
        raise ValueError(
            "Each ELV must have exactly "
            f"{DMRV_RECORDS_PER_ELV} dMRV records"
        )

    # ========================================================
    # RVSF JOB FK CHECK INSIDE dMRV
    # ========================================================

    valid_rvsf_ids = set(
        rvsf[
            "rvsf_job_card_id"
        ]
        .astype(str)
    )

    invalid_dmrv_rvsf_ids = (
        set(
            dmrv[
                "rvsf_job_card_id"
            ]
            .astype(str)
        )
        -
        valid_rvsf_ids
    )

    if invalid_dmrv_rvsf_ids:
        raise ValueError(
            "dMRV records reference invalid RVSF jobs"
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
            "circularity.credits",
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
    # GROUP UPSTREAM DATA
    # ========================================================

    rvsf_by_elv = {
        str(
            elv_id
        ):
            group.copy()

        for (
            elv_id,
            group,
        ) in rvsf.groupby(
            "elv_assessment_id",
            sort=False,
        )
    }

    dmrv_by_elv = {
        str(
            elv_id
        ):
            group.copy()

        for (
            elv_id,
            group,
        ) in dmrv.groupby(
            "elv_assessment_id",
            sort=False,
        )
    }

    rows: list[
        dict[str, Any]
    ] = []

    # ========================================================
    # GENERATE LISTINGS
    # ========================================================

    for (
        position,
        elv_record,
    ) in enumerate(
        elv.itertuples(
            index=False
        ),
        start=1,
    ):
        elv_id = str(
            elv_record.elv_assessment_id
        )

        elv_rvsf = (
            rvsf_by_elv[
                elv_id
            ]
            .copy()
        )

        elv_dmrv = (
            dmrv_by_elv[
                elv_id
            ]
            .copy()
        )

        # ====================================================
        # RVSF FACILITY CONSISTENCY
        # ====================================================

        facility_ids = (
            elv_rvsf[
                "rvsf_facility_id"
            ]
            .astype(str)
            .unique()
        )

        if len(
            facility_ids
        ) != 1:
            raise ValueError(
                f"{elv_id}: expected exactly one "
                "RVSF facility"
            )

        facility_names = (
            elv_rvsf[
                "rvsf_facility_name"
            ]
            .astype(str)
            .unique()
        )

        if len(
            facility_names
        ) != 1:
            raise ValueError(
                f"{elv_id}: inconsistent RVSF "
                "facility names"
            )

        rvsf_facility_id = str(
            facility_ids[
                0
            ]
        )

        rvsf_facility_name = str(
            facility_names[
                0
            ]
        )

        # ====================================================
        # RVSF JOB TYPES
        # ====================================================

        depollution = (
            elv_rvsf.loc[
                elv_rvsf[
                    "job_type"
                ]
                ==
                "DEPOLLUTION_AND_SAFETY"
            ]
        )

        dismantling = (
            elv_rvsf.loc[
                elv_rvsf[
                    "job_type"
                ]
                ==
                "DISMANTLING_AND_RECOVERY"
            ]
        )

        if len(
            depollution
        ) != 1:
            raise ValueError(
                f"{elv_id}: expected exactly one "
                "depollution job"
            )

        if len(
            dismantling
        ) != 1:
            raise ValueError(
                f"{elv_id}: expected exactly one "
                "dismantling job"
            )

        dep = depollution.iloc[
            0
        ]

        dis = dismantling.iloc[
            0
        ]

        # ====================================================
        # RECOVERY MASS SNAPSHOT
        # ====================================================

        reusable_parts_mass_kg = float(
            dis[
                "reusable_parts_mass_kg"
            ]
        )

        recyclable_material_mass_kg = float(
            dis[
                "recyclable_material_mass_kg"
            ]
        )

        residual_waste_mass_kg = float(
            dis[
                "residual_waste_mass_kg"
            ]
        )

        stage2_input_mass_kg = float(
            dis[
                "stage_input_mass_kg"
            ]
        )

        battery_mass_kg = float(
            dep[
                "battery_recovered_mass_kg"
            ]
        )

        tyre_mass_kg = float(
            dep[
                "tyre_recovered_mass_kg"
            ]
        )

        catalytic_mass_kg = float(
            dep[
                "catalytic_converter_mass_kg"
            ]
        )

        recovered_component_mass_kg = (
            battery_mass_kg
            +
            tyre_mass_kg
            +
            catalytic_mass_kg
        )

        total_process_energy_kwh = float(
            elv_rvsf[
                "energy_consumed_kwh"
            ]
            .sum()
        )

        total_process_water_liters = float(
            elv_rvsf[
                "water_consumed_liters"
            ]
            .sum()
        )

        source_rvsf_quality_pass_count = int(
            elv_rvsf[
                "quality_check_passed"
            ]
            .astype(bool)
            .sum()
        )

        # ====================================================
        # CREDIT TYPE
        # ====================================================

        credit_type = (
            _derive_credit_type(
                reusable_parts_mass_kg=
                    reusable_parts_mass_kg,

                recyclable_material_mass_kg=
                    recyclable_material_mass_kg,

                stage_input_mass_kg=
                    stage2_input_mass_kg,
            )
        )

        # ====================================================
        # SELLER-CLAIMED QUANTITY
        # ====================================================

        seller_claimed_quantity = (
            _seller_claimed_quantity_tco2e(
                rng=rng,

                reusable_parts_mass_kg=
                    reusable_parts_mass_kg,

                recyclable_material_mass_kg=
                    recyclable_material_mass_kg,

                battery_mass_kg=
                    battery_mass_kg,

                tyre_mass_kg=
                    tyre_mass_kg,

                catalytic_mass_kg=
                    catalytic_mass_kg,

                total_energy_kwh=
                    total_process_energy_kwh,

                total_water_liters=
                    total_process_water_liters,
            )
        )

        # ====================================================
        # dMRV SNAPSHOT
        #
        # Counts only.
        #
        # No completeness/readiness score is generated.
        # ====================================================

        dmrv_expected_records = int(
            DMRV_RECORDS_PER_ELV
        )

        dmrv_available_records = int(
            elv_dmrv[
                "evidence_available"
            ]
            .astype(bool)
            .sum()
        )

        dmrv_missing_records = int(
            dmrv_expected_records
            -
            dmrv_available_records
        )

        dmrv_source_reference_records = int(
            elv_dmrv[
                "source_reference_present"
            ]
            .astype(bool)
            .sum()
        )

        dmrv_attachment_records = int(
            elv_dmrv[
                "evidence_attachment_present"
            ]
            .astype(bool)
            .sum()
        )

        dmrv_timestamp_verified_records = int(
            elv_dmrv[
                "timestamp_verified"
            ]
            .astype(bool)
            .sum()
        )

        dmrv_signature_records = int(
            elv_dmrv[
                "digital_signature_present"
            ]
            .astype(bool)
            .sum()
        )

        dmrv_operator_identity_records = int(
            elv_dmrv[
                "operator_identity_present"
            ]
            .astype(bool)
            .sum()
        )

        dmrv_chain_of_custody_records = int(
            elv_dmrv[
                "chain_of_custody_present"
            ]
            .astype(bool)
            .sum()
        )

        dmrv_calibration_records = int(
            elv_dmrv[
                "measurement_calibration_present"
            ]
            .astype(bool)
            .sum()
        )

        dmrv_available_fraction = (
            dmrv_available_records
            /
            dmrv_expected_records
        )

        # ====================================================
        # CREDIT VINTAGE
        # ====================================================

        credit_vintage_start_at = pd.Timestamp(
            elv_rvsf[
                "processing_started_at"
            ]
            .min()
        )

        credit_vintage_end_at = pd.Timestamp(
            elv_rvsf[
                "processing_completed_at"
            ]
            .max()
        )

        if not (
            credit_vintage_start_at
            <
            credit_vintage_end_at
        ):
            raise ValueError(
                f"{elv_id}: invalid credit vintage"
            )

        # ====================================================
        # LISTING TIME AFTER dMRV
        # ====================================================

        latest_dmrv_at = pd.Timestamp(
            elv_dmrv[
                "dmrv_recorded_at"
            ]
            .max()
        )

        listing_at = (
            _build_listing_at(
                rng=rng,

                latest_dmrv_at=
                    latest_dmrv_at,

                generation_end_utc=
                    generation_end_utc,
            )
        )

        # ====================================================
        # OBSERVED MARKET REFERENCE PRICE
        # ====================================================

        market_reference_price = (
            _market_reference_price(
                rng=rng,

                credit_type=
                    credit_type,

                listing_at=
                    listing_at,

                generation_start=
                    generation_start_utc,
            )
        )

        # ====================================================
        # SELLER ASK
        # ====================================================

        source_traceability_score = float(
            elv_record.traceability_score
        )

        seller_ask_price = (
            _seller_asking_price(
                rng=rng,

                market_reference_price=
                    market_reference_price,

                dmrv_available_fraction=
                    dmrv_available_fraction,

                source_traceability_score=
                    source_traceability_score,
            )
        )

        # ====================================================
        # MINIMUM TRADE LOT
        # ====================================================

        minimum_trade_fraction = float(
            np.clip(
                rng.normal(
                    loc=0.45,
                    scale=0.14,
                ),
                0.20,
                1.00,
            )
        )

        minimum_trade_quantity = round(
            min(
                seller_claimed_quantity,
                max(
                    0.01,
                    seller_claimed_quantity
                    *
                    minimum_trade_fraction,
                ),
            ),
            4,
        )

        # ====================================================
        # OBSERVED MARKET ACTIVITY
        # ====================================================

        (
            buyer_inquiry_count,
            buyer_bid_count,
            highest_bid_price,
        ) = (
            _generate_market_engagement(
                rng=rng,

                listing_at=
                    listing_at,

                generation_end_utc=
                    generation_end_utc,

                seller_ask_price=
                    seller_ask_price,

                market_reference_price=
                    market_reference_price,

                dmrv_available_fraction=
                    dmrv_available_fraction,

                source_traceability_score=
                    source_traceability_score,

                claimed_quantity_tco2e=
                    seller_claimed_quantity,
            )
        )

        # ====================================================
        # OUTPUT ROW
        # ====================================================

        rows.append(
            {
                # --------------------------------------------
                # Listing identity
                # --------------------------------------------

                "carbon_credit_listing_id":
                    generate_id(
                        "CCLIST_SYN",
                        position,
                        width=6,
                    ),

                "elv_assessment_id":
                    elv_id,

                "elv_vehicle_id":
                    str(
                        elv_record.elv_vehicle_id
                    ),

                # --------------------------------------------
                # Vehicle
                # --------------------------------------------

                "vehicle_model_id":
                    str(
                        elv_record.vehicle_model_id
                    ),

                "model_name":
                    str(
                        elv_record.model_name
                    ),

                "segment":
                    str(
                        elv_record.segment
                    ),

                # --------------------------------------------
                # RVSF facility / geography
                # --------------------------------------------

                "rvsf_facility_id":
                    rvsf_facility_id,

                "rvsf_facility_name":
                    rvsf_facility_name,

                "city_id":
                    str(
                        elv_record.city_id
                    ),

                "city_name":
                    str(
                        elv_record.city_name
                    ),

                "region_id":
                    str(
                        elv_record.region_id
                    ),

                "region_name":
                    str(
                        elv_record.region_name
                    ),

                # --------------------------------------------
                # Credit identity
                # --------------------------------------------

                "credit_type":
                    credit_type,

                "credit_unit":
                    CREDIT_UNIT,

                "claim_basis":
                    CLAIM_BASIS,

                "claim_basis_version":
                    CLAIM_BASIS_VERSION,

                # --------------------------------------------
                # Vintage / listing
                # --------------------------------------------

                "credit_vintage_start_at":
                    credit_vintage_start_at
                    .tz_convert(
                        timezone
                    ),

                "credit_vintage_end_at":
                    credit_vintage_end_at
                    .tz_convert(
                        timezone
                    ),

                "listing_at":
                    listing_at
                    .tz_convert(
                        timezone
                    ),

                "listing_status":
                    LISTING_STATUS_OPEN,

                # --------------------------------------------
                # Seller-entered marketplace quantity
                # --------------------------------------------

                "seller_claimed_quantity_tco2e":
                    seller_claimed_quantity,

                "minimum_trade_quantity_tco2e":
                    minimum_trade_quantity,

                # --------------------------------------------
                # Observed marketplace price evidence
                # --------------------------------------------

                "market_reference_price_per_tco2e_inr":
                    market_reference_price,

                "seller_ask_price_per_tco2e_inr":
                    seller_ask_price,

                # --------------------------------------------
                # Actual observed marketplace activity
                # --------------------------------------------

                "buyer_inquiry_count":
                    buyer_inquiry_count,

                "buyer_bid_count":
                    buyer_bid_count,

                "highest_bid_price_per_tco2e_inr":
                    highest_bid_price,

                # --------------------------------------------
                # RVSF recovery evidence snapshot
                # --------------------------------------------

                "source_rvsf_job_count":
                    int(
                        len(
                            elv_rvsf
                        )
                    ),

                "source_rvsf_quality_pass_count":
                    source_rvsf_quality_pass_count,

                "reusable_parts_mass_kg":
                    round(
                        reusable_parts_mass_kg,
                        2,
                    ),

                "recyclable_material_mass_kg":
                    round(
                        recyclable_material_mass_kg,
                        2,
                    ),

                "residual_waste_mass_kg":
                    round(
                        residual_waste_mass_kg,
                        2,
                    ),

                "recovered_component_mass_kg":
                    round(
                        recovered_component_mass_kg,
                        2,
                    ),

                "total_process_energy_kwh":
                    round(
                        total_process_energy_kwh,
                        3,
                    ),

                "total_process_water_liters":
                    round(
                        total_process_water_liters,
                        3,
                    ),

                # --------------------------------------------
                # Raw dMRV evidence snapshot
                #
                # Counts, NOT readiness/completeness scores.
                # --------------------------------------------

                "source_dmrv_record_count":
                    int(
                        len(
                            elv_dmrv
                        )
                    ),

                "dmrv_expected_records":
                    dmrv_expected_records,

                "dmrv_available_records":
                    dmrv_available_records,

                "dmrv_missing_records":
                    dmrv_missing_records,

                "dmrv_source_reference_records":
                    dmrv_source_reference_records,

                "dmrv_attachment_records":
                    dmrv_attachment_records,

                "dmrv_timestamp_verified_records":
                    dmrv_timestamp_verified_records,

                "dmrv_signature_records":
                    dmrv_signature_records,

                "dmrv_operator_identity_records":
                    dmrv_operator_identity_records,

                "dmrv_chain_of_custody_records":
                    dmrv_chain_of_custody_records,

                "dmrv_calibration_records":
                    dmrv_calibration_records,

                # --------------------------------------------
                # Provenance
                # --------------------------------------------

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    listings = pd.DataFrame(
        rows
    )

    # ========================================================
    # FINAL COLUMN ORDER
    # ========================================================

    output_columns = [
        "carbon_credit_listing_id",

        "elv_assessment_id",
        "elv_vehicle_id",

        "vehicle_model_id",
        "model_name",
        "segment",

        "rvsf_facility_id",
        "rvsf_facility_name",

        "city_id",
        "city_name",

        "region_id",
        "region_name",

        "credit_type",
        "credit_unit",

        "claim_basis",
        "claim_basis_version",

        "credit_vintage_start_at",
        "credit_vintage_end_at",

        "listing_at",
        "listing_status",

        "seller_claimed_quantity_tco2e",
        "minimum_trade_quantity_tco2e",

        "market_reference_price_per_tco2e_inr",
        "seller_ask_price_per_tco2e_inr",

        "buyer_inquiry_count",
        "buyer_bid_count",

        "highest_bid_price_per_tco2e_inr",

        "source_rvsf_job_count",
        "source_rvsf_quality_pass_count",

        "reusable_parts_mass_kg",
        "recyclable_material_mass_kg",
        "residual_waste_mass_kg",

        "recovered_component_mass_kg",

        "total_process_energy_kwh",
        "total_process_water_liters",

        "source_dmrv_record_count",

        "dmrv_expected_records",
        "dmrv_available_records",
        "dmrv_missing_records",

        "dmrv_source_reference_records",
        "dmrv_attachment_records",
        "dmrv_timestamp_verified_records",
        "dmrv_signature_records",
        "dmrv_operator_identity_records",
        "dmrv_chain_of_custody_records",
        "dmrv_calibration_records",

        "data_origin",
        "generator_version",
    ]

    listings = (
        listings[
            output_columns
        ]
        .copy()
    )

    # ========================================================
    # VALIDATE
    # ========================================================

    validate_carbon_credit_listings(
        listings=listings,

        elv_assessments=elv,
        rvsf_job_cards=rvsf,
        dmrv_records=dmrv,

        generation_start=
            generation_start,

        generation_end=
            generation_end,

        expected_count=
            target_count,
    )

    return listings


# ============================================================
# VALIDATION
# ============================================================


def validate_carbon_credit_listings(
    listings: pd.DataFrame,
    elv_assessments: pd.DataFrame,
    rvsf_job_cards: pd.DataFrame,
    dmrv_records: pd.DataFrame,
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
    expected_count: int,
) -> None:
    """
    Validate marketplace listing integrity.
    """

    required_columns = {
        "carbon_credit_listing_id",

        "elv_assessment_id",
        "elv_vehicle_id",

        "vehicle_model_id",
        "model_name",
        "segment",

        "rvsf_facility_id",
        "rvsf_facility_name",

        "city_id",
        "city_name",

        "region_id",
        "region_name",

        "credit_type",
        "credit_unit",

        "claim_basis",
        "claim_basis_version",

        "credit_vintage_start_at",
        "credit_vintage_end_at",

        "listing_at",
        "listing_status",

        "seller_claimed_quantity_tco2e",
        "minimum_trade_quantity_tco2e",

        "market_reference_price_per_tco2e_inr",
        "seller_ask_price_per_tco2e_inr",

        "buyer_inquiry_count",
        "buyer_bid_count",

        "highest_bid_price_per_tco2e_inr",

        "source_rvsf_job_count",
        "source_rvsf_quality_pass_count",

        "reusable_parts_mass_kg",
        "recyclable_material_mass_kg",
        "residual_waste_mass_kg",

        "recovered_component_mass_kg",

        "total_process_energy_kwh",
        "total_process_water_liters",

        "source_dmrv_record_count",

        "dmrv_expected_records",
        "dmrv_available_records",
        "dmrv_missing_records",

        "dmrv_source_reference_records",
        "dmrv_attachment_records",
        "dmrv_timestamp_verified_records",
        "dmrv_signature_records",
        "dmrv_operator_identity_records",
        "dmrv_chain_of_custody_records",
        "dmrv_calibration_records",

        "data_origin",
        "generator_version",
    }

    missing_columns = (
        required_columns
        -
        set(
            listings.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "Credit listings missing columns: "
            +
            ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if listings.empty:
        raise ValueError(
            "Credit-listing generator produced zero rows"
        )

    # ========================================================
    # EXACT COUNT
    # ========================================================

    if (
        len(
            listings
        )
        !=
        expected_count
    ):
        raise ValueError(
            "Unexpected carbon-credit listing count. "
            f"Expected={expected_count}, "
            f"actual={len(listings)}"
        )

    # ========================================================
    # PRIMARY KEY
    # ========================================================

    if (
        listings[
            "carbon_credit_listing_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Credit listings contain missing IDs"
        )

    if (
        listings[
            "carbon_credit_listing_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate carbon_credit_listing_id "
            "values found"
        )

    # ========================================================
    # ONE LISTING PER ELV
    # ========================================================

    if (
        listings[
            "elv_assessment_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Each ELV may have only one "
            "credit listing"
        )

    valid_elv_ids = set(
        elv_assessments[
            "elv_assessment_id"
        ]
        .astype(str)
    )

    listing_elv_ids = set(
        listings[
            "elv_assessment_id"
        ]
        .astype(str)
    )

    if (
        listing_elv_ids
        !=
        valid_elv_ids
    ):
        raise ValueError(
            "Credit listings do not provide exact "
            "ELV coverage"
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

    for record in listings.itertuples(
        index=False
    ):
        source_elv = (
            elv_lookup.loc[
                str(
                    record.elv_assessment_id
                )
            ]
        )

        consistency = {
            "elv_vehicle_id":
                source_elv[
                    "elv_vehicle_id"
                ],

            "vehicle_model_id":
                source_elv[
                    "vehicle_model_id"
                ],

            "model_name":
                source_elv[
                    "model_name"
                ],

            "segment":
                source_elv[
                    "segment"
                ],

            "city_id":
                source_elv[
                    "city_id"
                ],

            "city_name":
                source_elv[
                    "city_name"
                ],

            "region_id":
                source_elv[
                    "region_id"
                ],

            "region_name":
                source_elv[
                    "region_name"
                ],
        }

        for (
            column,
            expected_value,
        ) in consistency.items():

            if (
                str(
                    getattr(
                        record,
                        column,
                    )
                )
                !=
                str(
                    expected_value
                )
            ):
                raise ValueError(
                    f"{record.carbon_credit_listing_id}: "
                    f"{column} inconsistent with ELV"
                )

    # ========================================================
    # CREDIT TYPE / UNIT / STATUS
    # ========================================================

    invalid_credit_types = (
        set(
            listings[
                "credit_type"
            ]
            .astype(str)
        )
        -
        VALID_CREDIT_TYPES
    )

    if invalid_credit_types:
        raise ValueError(
            "Invalid credit_type values"
        )

    if (
        set(
            listings[
                "credit_unit"
            ]
            .astype(str)
        )
        !=
        {
            CREDIT_UNIT
        }
    ):
        raise ValueError(
            "All carbon-credit listings must use TCO2E"
        )

    invalid_statuses = (
        set(
            listings[
                "listing_status"
            ]
            .astype(str)
        )
        -
        VALID_LISTING_STATUSES
    )

    if invalid_statuses:
        raise ValueError(
            "Invalid listing_status values"
        )

    if (
        set(
            listings[
                "claim_basis"
            ]
            .astype(str)
        )
        !=
        {
            CLAIM_BASIS
        }
    ):
        raise ValueError(
            "Invalid claim_basis"
        )

    # ========================================================
    # TIMESTAMPS
    # ========================================================

    vintage_start = pd.to_datetime(
        listings[
            "credit_vintage_start_at"
        ],
        utc=True,
    )

    vintage_end = pd.to_datetime(
        listings[
            "credit_vintage_end_at"
        ],
        utc=True,
    )

    listing_at = pd.to_datetime(
        listings[
            "listing_at"
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
        vintage_end
        <=
        vintage_start
    ).any():
        raise ValueError(
            "Credit vintage end must be after "
            "vintage start"
        )

    if (
        listing_at
        <=
        vintage_end
    ).any():
        raise ValueError(
            "Marketplace listing must occur after "
            "RVSF vintage completion"
        )

    if (
        listing_at
        <
        generation_start_utc
    ).any():
        raise ValueError(
            "Credit listing occurs before "
            "generation start"
        )

    if (
        listing_at
        >=
        generation_end_utc
    ).any():
        raise ValueError(
            "Credit listing occurs on/after "
            "generation end"
        )

    # ========================================================
    # LISTING MUST OCCUR AFTER LATEST dMRV RECORD
    # ========================================================

    latest_dmrv_by_elv = (
        dmrv_records
        .groupby(
            "elv_assessment_id"
        )[
            "dmrv_recorded_at"
        ]
        .max()
    )

    listing_latest_dmrv = (
        listings[
            "elv_assessment_id"
        ]
        .map(
            latest_dmrv_by_elv
        )
    )

    listing_latest_dmrv = pd.to_datetime(
        listing_latest_dmrv,
        utc=True,
    )

    if (
        listing_at
        <=
        listing_latest_dmrv
    ).any():
        raise ValueError(
            "Credit listing must occur after latest "
            "dMRV record"
        )

    # ========================================================
    # POSITIVE QUANTITY / PRICE
    # ========================================================

    positive_columns = (
        "seller_claimed_quantity_tco2e",
        "minimum_trade_quantity_tco2e",

        "market_reference_price_per_tco2e_inr",
        "seller_ask_price_per_tco2e_inr",
    )

    for column in positive_columns:
        values = pd.to_numeric(
            listings[
                column
            ],
            errors="raise",
        )

        if (
            values
            <=
            0
        ).any():
            raise ValueError(
                f"{column} must be positive"
            )

    if (
        listings[
            "minimum_trade_quantity_tco2e"
        ]
        >
        listings[
            "seller_claimed_quantity_tco2e"
        ]
    ).any():
        raise ValueError(
            "Minimum trade quantity cannot exceed "
            "seller claimed quantity"
        )

    # ========================================================
    # MARKET ENGAGEMENT
    # ========================================================

    for column in (
        "buyer_inquiry_count",
        "buyer_bid_count",
    ):
        values = pd.to_numeric(
            listings[
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
        listings[
            "buyer_bid_count"
        ]
        >
        listings[
            "buyer_inquiry_count"
        ]
    ).any():
        raise ValueError(
            "buyer_bid_count cannot exceed "
            "buyer_inquiry_count"
        )

    bid_exists_mask = (
        listings[
            "buyer_bid_count"
        ]
        >
        0
    )

    no_bid_mask = (
        ~bid_exists_mask
    )

    if (
        listings.loc[
            bid_exists_mask,
            "highest_bid_price_per_tco2e_inr",
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Listings with bids require "
            "highest_bid_price"
        )

    if (
        listings.loc[
            no_bid_mask,
            "highest_bid_price_per_tco2e_inr",
        ]
        .notna()
        .any()
    ):
        raise ValueError(
            "Listings without bids cannot have "
            "highest_bid_price"
        )

    if (
        pd.to_numeric(
            listings.loc[
                bid_exists_mask,
                "highest_bid_price_per_tco2e_inr",
            ],
            errors="raise",
        )
        <=
        0
    ).any():
        raise ValueError(
            "Highest bid price must be positive"
        )

    # ========================================================
    # RVSF SOURCE COUNTS
    # ========================================================

    if (
        listings[
            "source_rvsf_job_count"
        ]
        !=
        RVSF_JOBS_PER_ELV
    ).any():
        raise ValueError(
            "Each credit listing must reference "
            "exactly two RVSF jobs"
        )

    if (
        (
            listings[
                "source_rvsf_quality_pass_count"
            ]
            <
            0
        )
        |
        (
            listings[
                "source_rvsf_quality_pass_count"
            ]
            >
            RVSF_JOBS_PER_ELV
        )
    ).any():
        raise ValueError(
            "Invalid source RVSF quality-pass count"
        )

    # ========================================================
    # RVSF SNAPSHOT VALIDATION
    # ========================================================

    rvsf_grouped = (
        rvsf_job_cards
        .groupby(
            "elv_assessment_id"
        )
    )

    for record in listings.itertuples(
        index=False
    ):
        elv_id = str(
            record.elv_assessment_id
        )

        source_jobs = (
            rvsf_grouped
            .get_group(
                elv_id
            )
        )

        dep = source_jobs.loc[
            source_jobs[
                "job_type"
            ]
            ==
            "DEPOLLUTION_AND_SAFETY"
        ]

        dis = source_jobs.loc[
            source_jobs[
                "job_type"
            ]
            ==
            "DISMANTLING_AND_RECOVERY"
        ]

        if (
            len(dep) != 1
            or
            len(dis) != 1
        ):
            raise ValueError(
                f"{elv_id}: invalid RVSF job pair"
            )

        dep_row = dep.iloc[
            0
        ]

        dis_row = dis.iloc[
            0
        ]

        expected_values = {
            "reusable_parts_mass_kg":
                float(
                    dis_row[
                        "reusable_parts_mass_kg"
                    ]
                ),

            "recyclable_material_mass_kg":
                float(
                    dis_row[
                        "recyclable_material_mass_kg"
                    ]
                ),

            "residual_waste_mass_kg":
                float(
                    dis_row[
                        "residual_waste_mass_kg"
                    ]
                ),

            "recovered_component_mass_kg":
                (
                    float(
                        dep_row[
                            "battery_recovered_mass_kg"
                        ]
                    )
                    +
                    float(
                        dep_row[
                            "tyre_recovered_mass_kg"
                        ]
                    )
                    +
                    float(
                        dep_row[
                            "catalytic_converter_mass_kg"
                        ]
                    )
                ),

            "total_process_energy_kwh":
                float(
                    source_jobs[
                        "energy_consumed_kwh"
                    ]
                    .sum()
                ),

            "total_process_water_liters":
                float(
                    source_jobs[
                        "water_consumed_liters"
                    ]
                    .sum()
                ),
        }

        for (
            column,
            expected_value,
        ) in expected_values.items():

            actual_value = float(
                getattr(
                    record,
                    column,
                )
            )

            if not np.isclose(
                actual_value,
                expected_value,
                atol=0.02,
            ):
                raise ValueError(
                    f"{record.carbon_credit_listing_id}: "
                    f"{column} inconsistent with RVSF"
                )

        source_facilities = (
            source_jobs[
                "rvsf_facility_id"
            ]
            .astype(str)
            .unique()
        )

        if (
            len(
                source_facilities
            )
            !=
            1
        ):
            raise ValueError(
                f"{elv_id}: RVSF facility mismatch"
            )

        if (
            str(
                record.rvsf_facility_id
            )
            !=
            str(
                source_facilities[
                    0
                ]
            )
        ):
            raise ValueError(
                f"{record.carbon_credit_listing_id}: "
                "RVSF facility inconsistent with source"
            )

    # ========================================================
    # dMRV SNAPSHOT COUNTS
    # ========================================================

    dmrv_grouped = (
        dmrv_records
        .groupby(
            "elv_assessment_id"
        )
    )

    support_count_columns = {
        "dmrv_source_reference_records":
            "source_reference_present",

        "dmrv_attachment_records":
            "evidence_attachment_present",

        "dmrv_timestamp_verified_records":
            "timestamp_verified",

        "dmrv_signature_records":
            "digital_signature_present",

        "dmrv_operator_identity_records":
            "operator_identity_present",

        "dmrv_chain_of_custody_records":
            "chain_of_custody_present",

        "dmrv_calibration_records":
            "measurement_calibration_present",
    }

    for record in listings.itertuples(
        index=False
    ):
        elv_id = str(
            record.elv_assessment_id
        )

        source_dmrv = (
            dmrv_grouped
            .get_group(
                elv_id
            )
        )

        expected_total = int(
            len(
                source_dmrv
            )
        )

        expected_available = int(
            source_dmrv[
                "evidence_available"
            ]
            .astype(bool)
            .sum()
        )

        expected_missing = int(
            expected_total
            -
            expected_available
        )

        if (
            int(
                record.source_dmrv_record_count
            )
            !=
            expected_total
        ):
            raise ValueError(
                f"{record.carbon_credit_listing_id}: "
                "source_dmrv_record_count mismatch"
            )

        if (
            int(
                record.dmrv_expected_records
            )
            !=
            DMRV_RECORDS_PER_ELV
        ):
            raise ValueError(
                f"{record.carbon_credit_listing_id}: "
                "dmrv_expected_records mismatch"
            )

        if (
            int(
                record.dmrv_available_records
            )
            !=
            expected_available
        ):
            raise ValueError(
                f"{record.carbon_credit_listing_id}: "
                "dmrv_available_records mismatch"
            )

        if (
            int(
                record.dmrv_missing_records
            )
            !=
            expected_missing
        ):
            raise ValueError(
                f"{record.carbon_credit_listing_id}: "
                "dmrv_missing_records mismatch"
            )

        for (
            listing_column,
            dmrv_column,
        ) in support_count_columns.items():

            expected_count_value = int(
                source_dmrv[
                    dmrv_column
                ]
                .astype(bool)
                .sum()
            )

            actual_count_value = int(
                getattr(
                    record,
                    listing_column,
                )
            )

            if (
                actual_count_value
                !=
                expected_count_value
            ):
                raise ValueError(
                    f"{record.carbon_credit_listing_id}: "
                    f"{listing_column} mismatch"
                )

    # ========================================================
    # dMRV COUNT BOUNDS
    # ========================================================

    if (
        listings[
            "source_dmrv_record_count"
        ]
        !=
        DMRV_RECORDS_PER_ELV
    ).any():
        raise ValueError(
            "Each listing must reference exactly "
            f"{DMRV_RECORDS_PER_ELV} dMRV records"
        )

    if (
        listings[
            "dmrv_expected_records"
        ]
        !=
        DMRV_RECORDS_PER_ELV
    ).any():
        raise ValueError(
            "Invalid dmrv_expected_records"
        )

    if not np.array_equal(
        (
            listings[
                "dmrv_available_records"
            ]
            +
            listings[
                "dmrv_missing_records"
            ]
        ).to_numpy(),
        listings[
            "dmrv_expected_records"
        ].to_numpy(),
    ):
        raise ValueError(
            "Available + missing dMRV records "
            "must equal expected records"
        )

    dmrv_count_columns = (
        "dmrv_available_records",
        "dmrv_missing_records",

        "dmrv_source_reference_records",
        "dmrv_attachment_records",
        "dmrv_timestamp_verified_records",
        "dmrv_signature_records",
        "dmrv_operator_identity_records",
        "dmrv_chain_of_custody_records",
        "dmrv_calibration_records",
    )

    for column in dmrv_count_columns:
        if (
            (
                listings[
                    column
                ]
                <
                0
            )
            |
            (
                listings[
                    column
                ]
                >
                DMRV_RECORDS_PER_ELV
            )
        ).any():
            raise ValueError(
                f"{column} outside valid dMRV bounds"
            )

    # ========================================================
    # RECOVERY / RESOURCE METRICS
    # ========================================================

    nonnegative_columns = (
        "reusable_parts_mass_kg",
        "recyclable_material_mass_kg",
        "residual_waste_mass_kg",

        "recovered_component_mass_kg",

        "total_process_energy_kwh",
        "total_process_water_liters",
    )

    for column in nonnegative_columns:
        values = pd.to_numeric(
            listings[
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

    # ========================================================
    # PROVENANCE
    # ========================================================

    if (
        listings[
            "data_origin"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Credit listings contain missing data_origin"
        )

    if (
        listings[
            "generator_version"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Credit listings contain missing "
            "generator_version"
        )

    # ========================================================
    # HIDDEN RUNTIME / GROUND-TRUTH LEAKAGE
    # ========================================================

    leaked_columns = (
        HIDDEN_RUNTIME_COLUMNS
        &
        set(
            listings.columns
        )
    )

    if leaked_columns:
        raise ValueError(
            "Runtime / ground-truth fields leaked "
            "into carbon-credit listings: "
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


def generate_credits(
    elv_assessments: pd.DataFrame,
    rvsf_job_cards: pd.DataFrame,
    dmrv_records: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Convenience alias.
    """

    return generate_carbon_credit_listings(
        elv_assessments=
            elv_assessments,

        rvsf_job_cards=
            rvsf_job_cards,

        dmrv_records=
            dmrv_records,

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

    from data.generators.circularity.dmrv import (
        generate_dmrv_records,
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

    rvsf_df = (
        generate_rvsf_job_cards(
            elv_assessments=
                elv_df,

            generation=
                generation_config,
        )
    )

    dmrv_df = (
        generate_dmrv_records(
            rvsf_job_cards=
                rvsf_df,

            generation=
                generation_config,
        )
    )

    # ========================================================
    # DEPENDENCY CHECK
    # ========================================================

    print(
        "\n=== CREDIT LISTING DEPENDENCY CHECK ===\n"
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
        "dMRV records:",
        len(
            dmrv_df
        ),
    )

    print(
        "Configured carbon-credit listings:",
        _get_credit_listing_target_count(
            generation_config
        ),
    )

    # ========================================================
    # GENERATE
    # ========================================================

    credits_df = (
        generate_carbon_credit_listings(
            elv_assessments=
                elv_df,

            rvsf_job_cards=
                rvsf_df,

            dmrv_records=
                dmrv_df,

            generation=
                generation_config,
        )
    )

    # ========================================================
    # SAMPLE
    # ========================================================

    print(
        "\n=== CREDIT LISTING SAMPLE ===\n"
    )

    sample_columns = [
        "carbon_credit_listing_id",

        "elv_assessment_id",
        "model_name",

        "city_name",
        "region_name",

        "credit_type",

        "listing_at",

        "seller_claimed_quantity_tco2e",

        "market_reference_price_per_tco2e_inr",
        "seller_ask_price_per_tco2e_inr",

        "buyer_inquiry_count",
        "buyer_bid_count",

        "highest_bid_price_per_tco2e_inr",

        "reusable_parts_mass_kg",
        "recyclable_material_mass_kg",

        "dmrv_available_records",
        "dmrv_missing_records",

        "dmrv_attachment_records",
        "dmrv_signature_records",
        "dmrv_chain_of_custody_records",
    ]

    print(
        credits_df[
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
    # CREDIT TYPE MIX
    # ========================================================

    print(
        "\n=== CREDIT TYPE MIX ===\n"
    )

    credit_type_summary = (
        credits_df[
            "credit_type"
        ]
        .value_counts()
        .rename_axis(
            "credit_type"
        )
        .reset_index(
            name="listings"
        )
    )

    credit_type_summary[
        "rate"
    ] = (
        credit_type_summary[
            "listings"
        ]
        /
        len(
            credits_df
        )
    ).round(
        4
    )

    print(
        credit_type_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # MARKETPLACE SUMMARY
    # ========================================================

    print(
        "\n=== CREDIT MARKETPLACE SUMMARY ===\n"
    )

    print(
        "Average seller claimed quantity tCO2e:",
        round(
            float(
                credits_df[
                    "seller_claimed_quantity_tco2e"
                ]
                .mean()
            ),
            4,
        ),
    )

    print(
        "Minimum seller claimed quantity tCO2e:",
        round(
            float(
                credits_df[
                    "seller_claimed_quantity_tco2e"
                ]
                .min()
            ),
            4,
        ),
    )

    print(
        "Maximum seller claimed quantity tCO2e:",
        round(
            float(
                credits_df[
                    "seller_claimed_quantity_tco2e"
                ]
                .max()
            ),
            4,
        ),
    )

    print(
        "Average market reference price INR/tCO2e:",
        round(
            float(
                credits_df[
                    "market_reference_price_per_tco2e_inr"
                ]
                .mean()
            ),
            2,
        ),
    )

    print(
        "Average seller ask price INR/tCO2e:",
        round(
            float(
                credits_df[
                    "seller_ask_price_per_tco2e_inr"
                ]
                .mean()
            ),
            2,
        ),
    )

    ask_reference_ratio = (
        credits_df[
            "seller_ask_price_per_tco2e_inr"
        ]
        /
        credits_df[
            "market_reference_price_per_tco2e_inr"
        ]
    )

    print(
        "Average ask/reference ratio:",
        round(
            float(
                ask_reference_ratio.mean()
            ),
            4,
        ),
    )

    # ========================================================
    # BUYER ACTIVITY
    # ========================================================

    print(
        "\n=== CREDIT BUYER ACTIVITY ===\n"
    )

    print(
        "Average buyer inquiries/listing:",
        round(
            float(
                credits_df[
                    "buyer_inquiry_count"
                ]
                .mean()
            ),
            3,
        ),
    )

    print(
        "Listings with at least one inquiry:",
        int(
            (
                credits_df[
                    "buyer_inquiry_count"
                ]
                >
                0
            ).sum()
        ),
    )

    print(
        "Average bids/listing:",
        round(
            float(
                credits_df[
                    "buyer_bid_count"
                ]
                .mean()
            ),
            3,
        ),
    )

    print(
        "Listings with at least one bid:",
        int(
            (
                credits_df[
                    "buyer_bid_count"
                ]
                >
                0
            ).sum()
        ),
    )

    print(
        "Listings without bids:",
        int(
            (
                credits_df[
                    "buyer_bid_count"
                ]
                ==
                0
            ).sum()
        ),
    )

    bid_rows = (
        credits_df.loc[
            credits_df[
                "buyer_bid_count"
            ]
            >
            0
        ]
    )

    if not bid_rows.empty:
        print(
            "Average highest bid INR/tCO2e:",
            round(
                float(
                    bid_rows[
                        "highest_bid_price_per_tco2e_inr"
                    ]
                    .mean()
                ),
                2,
            ),
        )

    # ========================================================
    # dMRV COVERAGE SNAPSHOT
    # ========================================================

    print(
        "\n=== CREDIT dMRV EVIDENCE SNAPSHOT ===\n"
    )

    dmrv_coverage_summary = (
        credits_df[
            "dmrv_available_records"
        ]
        .value_counts()
        .sort_index(
            ascending=False
        )
        .rename_axis(
            "dmrv_available_records"
        )
        .reset_index(
            name="listings"
        )
    )

    dmrv_coverage_summary[
        "rate"
    ] = (
        dmrv_coverage_summary[
            "listings"
        ]
        /
        len(
            credits_df
        )
    ).round(
        4
    )

    print(
        dmrv_coverage_summary
        .to_string(
            index=False
        )
    )

    print(
        "\nListings with all 4 dMRV records available:",
        int(
            (
                credits_df[
                    "dmrv_available_records"
                ]
                ==
                4
            ).sum()
        ),
    )

    print(
        "Listings with at least one dMRV record missing:",
        int(
            (
                credits_df[
                    "dmrv_missing_records"
                ]
                >
                0
            ).sum()
        ),
    )

    # ========================================================
    # RVSF RECOVERY EVIDENCE
    # ========================================================

    print(
        "\n=== CREDIT RECOVERY EVIDENCE ===\n"
    )

    print(
        "Average reusable parts mass kg:",
        round(
            float(
                credits_df[
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
                credits_df[
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
                credits_df[
                    "residual_waste_mass_kg"
                ]
                .mean()
            ),
            2,
        ),
    )

    print(
        "Average recovered component mass kg:",
        round(
            float(
                credits_df[
                    "recovered_component_mass_kg"
                ]
                .mean()
            ),
            2,
        ),
    )

    # ========================================================
    # RELATIONSHIP CHECKS
    # ========================================================

    relationship_df = (
        credits_df.merge(
            elv_df[
                [
                    "elv_assessment_id",
                    "traceability_score",
                ]
            ],
            on="elv_assessment_id",
            how="left",
            validate="one_to_one",
        )
    )

    relationship_df[
        "total_recovered_mass_kg"
    ] = (
        relationship_df[
            "reusable_parts_mass_kg"
        ]
        +
        relationship_df[
            "recyclable_material_mass_kg"
        ]
        +
        relationship_df[
            "recovered_component_mass_kg"
        ]
    )

    relationship_df[
        "dmrv_available_fraction"
    ] = (
        relationship_df[
            "dmrv_available_records"
        ]
        /
        relationship_df[
            "dmrv_expected_records"
        ]
    )

    relationship_df[
        "ask_reference_ratio"
    ] = (
        relationship_df[
            "seller_ask_price_per_tco2e_inr"
        ]
        /
        relationship_df[
            "market_reference_price_per_tco2e_inr"
        ]
    )

    print(
        "\n=== CREDIT RELATIONSHIP CHECKS ===\n"
    )

    print(
        "Correlation recovered mass vs claimed quantity:",
        round(
            float(
                relationship_df[
                    [
                        "total_recovered_mass_kg",
                        "seller_claimed_quantity_tco2e",
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
        "Correlation dMRV availability vs buyer inquiries:",
        round(
            float(
                relationship_df[
                    [
                        "dmrv_available_fraction",
                        "buyer_inquiry_count",
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
        "Correlation traceability vs buyer inquiries:",
        round(
            float(
                relationship_df[
                    [
                        "traceability_score",
                        "buyer_inquiry_count",
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
        "Correlation ask/reference ratio vs buyer bids:",
        round(
            float(
                relationship_df[
                    [
                        "ask_reference_ratio",
                        "buyer_bid_count",
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
        "\n=== CREDIT LISTING VALIDATION ===\n"
    )

    print(
        "Rows:",
        len(
            credits_df
        ),
    )

    print(
        "Unique credit listing IDs:",
        credits_df[
            "carbon_credit_listing_id"
        ]
        .nunique(),
    )

    print(
        "ELV assessments represented:",
        credits_df[
            "elv_assessment_id"
        ]
        .nunique(),
    )

    print(
        "Unique ELV vehicles:",
        credits_df[
            "elv_vehicle_id"
        ]
        .nunique(),
    )

    print(
        "Facilities represented:",
        credits_df[
            "rvsf_facility_id"
        ]
        .nunique(),
    )

    print(
        "Regions represented:",
        credits_df[
            "region_id"
        ]
        .nunique(),
    )

    print(
        "Credit types represented:",
        credits_df[
            "credit_type"
        ]
        .nunique(),
    )

    print(
        "Duplicate listing IDs:",
        int(
            credits_df[
                "carbon_credit_listing_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Duplicate ELV listings:",
        int(
            credits_df[
                "elv_assessment_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Missing ELV assessment IDs:",
        int(
            credits_df[
                "elv_assessment_id"
            ]
            .isna()
            .sum()
        ),
    )

    print(
        "Listings with invalid bid count:",
        int(
            (
                credits_df[
                    "buyer_bid_count"
                ]
                >
                credits_df[
                    "buyer_inquiry_count"
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
                credits_df.columns
            )
        ),
    )

    print(
        "\nGenerated "
        f"{len(credits_df)} "
        "synthetic carbon-credit marketplace "
        "listings successfully."
    )