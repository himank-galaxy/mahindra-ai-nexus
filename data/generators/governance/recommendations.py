"""
Synthetic evidence-derived recommendation generator
for Mahindra AI Nexus.

============================================================
PURPOSE
============================================================

Generate governance recommendation records from already-created
operational evidence across:

    AUTO
    FINANCE
    COLLECTIONS
    LOGISTICS
    CIRCULARITY

Recommendations are created in PROPOSED state only.

Approval, rejection, modification, escalation, human review,
compliance checks and audit history belong to downstream:

    governance/trust.py
    governance/audit.py


============================================================
SYNTHETIC DATA FACTORY ALIGNMENT
============================================================

Rules preserved:

1. Recommendations are derived from operational evidence.
2. Confidence is derived from evidence strength/completeness.
3. Risk is derived from observed operational evidence.
4. No hidden ground-truth fields are exposed.
5. No future outcome is injected into recommendation records.
6. No APPROVED recommendation is created here.
7. Evidence lineage is retained as JSON.
8. Individual generators return DataFrames only.
9. No CSV writes occur in this module.
10. Recommendation generation is deterministic.


============================================================
IMPORTANT AUTO DESIGN
============================================================

The real frozen allocation schema contains:

    allocation_status
    requested_units
    allocated_units
    waiting_list
    dealer_capacity
    regional_demand_index
    allocation_priority_score
    allocation_priority
    inventory_before
    inventory_after
    production_batch_inventory_before
    production_batch_inventory_after
    allocation_wait_hours

It does NOT contain:

    inventory_shortage_flag
    promised_delivery_wait_days

Therefore Auto recommendations derive inventory/capacity pressure
from actual observed inventory, demand, wait and priority evidence.

The current synthetic world also has:

    allocation_status = ALLOCATED for all rows
    waiting_list = 0 for all rows

Therefore those fields are retained as evidence but are not used as
the main discriminating recommendation signals.


============================================================
OUTPUT
============================================================

Public functions:

    generate_recommendations(...)
        -> recommendations DataFrame

    generate_recommendation_master(...)
        -> alias for generate_recommendations(...)
"""

from __future__ import annotations

import json
from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.helpers import (
    load_generation_config,
)

from data.generators.common.ids import (
    generate_id,
)


# ============================================================
# DOMAINS
# ============================================================

DOMAIN_AUTO = "AUTO"
DOMAIN_FINANCE = "FINANCE"
DOMAIN_COLLECTIONS = "COLLECTIONS"
DOMAIN_LOGISTICS = "LOGISTICS"
DOMAIN_CIRCULARITY = "CIRCULARITY"


SUPPORTED_DOMAINS = (
    DOMAIN_AUTO,
    DOMAIN_FINANCE,
    DOMAIN_COLLECTIONS,
    DOMAIN_LOGISTICS,
    DOMAIN_CIRCULARITY,
)


DOMAIN_USE_CASES = {
    DOMAIN_AUTO:
        "DEALER_ALLOCATION_OPTIMIZATION",

    DOMAIN_FINANCE:
        "FINANCIAL_CROSS_SELL_FOLLOWUP",

    DOMAIN_COLLECTIONS:
        "COLLECTIONS_RECOVERY",

    DOMAIN_LOGISTICS:
        "ROUTE_SLA_MITIGATION",

    DOMAIN_CIRCULARITY:
        "CREDIT_AND_DMRV_OPTIMIZATION",
}


DOMAIN_TARGET_ENTITY_TYPES = {
    DOMAIN_AUTO:
        "ALLOCATION",

    DOMAIN_FINANCE:
        "CROSS_SELL_EVENT",

    DOMAIN_COLLECTIONS:
        "COLLECTION_CASE",

    DOMAIN_LOGISTICS:
        "SHIPMENT",

    DOMAIN_CIRCULARITY:
        "CARBON_CREDIT_LISTING",
}


VALID_RISK_LEVELS = {
    "LOW",
    "MEDIUM",
    "HIGH",
}


VALID_RECOMMENDATION_STATUSES = {
    "PROPOSED",
}


# ============================================================
# LEAKAGE PROTECTION
# ============================================================

FORBIDDEN_OUTPUT_COLUMN_FRAGMENTS = (
    "true_",
    "ground_truth",
    "actual_future",
    "future_outcome",
    "predicted_",
    "prediction_",
    "model_score",
    "calibrated_probability",
    "closure_outcome",
)


FORBIDDEN_PAYLOAD_KEY_FRAGMENTS = (
    "true_",
    "ground_truth",
    "actual_future",
    "future_outcome",
    "predicted_",
    "prediction_",
    "model_score",
    "calibrated_probability",
    "closure_outcome",
)


# ============================================================
# BASIC HELPERS
# ============================================================


def _is_missing(
    value: Any,
) -> bool:
    """
    Safe scalar missing-value check.
    """

    if value is None:
        return True

    if isinstance(
        value,
        (
            dict,
            list,
            tuple,
            set,
        ),
    ):
        return False

    try:
        result = pd.isna(
            value
        )

        if isinstance(
            result,
            (
                bool,
                np.bool_,
            ),
        ):
            return bool(
                result
            )

    except (
        TypeError,
        ValueError,
    ):
        pass

    return False


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    """
    Convert scalar to finite float.
    """

    if _is_missing(
        value
    ):
        return float(
            default
        )

    try:
        number = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return float(
            default
        )

    if not np.isfinite(
        number
    ):
        return float(
            default
        )

    return float(
        number
    )


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    """
    Convert scalar to integer.
    """

    if _is_missing(
        value
    ):
        return int(
            default
        )

    try:
        return int(
            round(
                float(
                    value
                )
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return int(
            default
        )


def _to_bool(
    value: Any,
) -> bool:
    """
    Normalize common boolean representations.
    """

    if _is_missing(
        value
    ):
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

    if isinstance(
        value,
        (
            int,
            float,
            np.integer,
            np.floating,
        ),
    ):
        return bool(
            value
        )

    text = str(
        value
    ).strip().upper()

    if text in {
        "TRUE",
        "1",
        "YES",
        "Y",
    }:
        return True

    if text in {
        "FALSE",
        "0",
        "NO",
        "N",
    }:
        return False

    return bool(
        text
    )


def _clip01(
    value: float,
) -> float:
    """
    Clip numeric value into [0, 1].
    """

    return float(
        np.clip(
            float(
                value
            ),
            0.0,
            1.0,
        )
    )


def _quantile_scale(
    series: pd.Series,
    quantile: float = 0.95,
    minimum: float = 1.0,
) -> float:
    """
    Robust positive normalization scale.
    """

    numeric = pd.to_numeric(
        series,
        errors="coerce",
    )

    numeric = numeric[
        numeric.notna()
        &
        np.isfinite(
            numeric
        )
        &
        (
            numeric
            >= 0
        )
    ]

    if numeric.empty:
        return float(
            minimum
        )

    value = float(
        numeric.quantile(
            quantile
        )
    )

    return max(
        value,
        float(
            minimum
        ),
    )


def _min_max_bounds(
    series: pd.Series,
) -> tuple[
    float,
    float,
]:
    """
    Return finite min/max bounds for deterministic normalization.
    """

    numeric = pd.to_numeric(
        series,
        errors="coerce",
    )

    numeric = numeric[
        numeric.notna()
        &
        np.isfinite(
            numeric
        )
    ]

    if numeric.empty:
        return (
            0.0,
            1.0,
        )

    minimum = float(
        numeric.min()
    )

    maximum = float(
        numeric.max()
    )

    if maximum <= minimum:
        maximum = (
            minimum
            + 1.0
        )

    return (
        minimum,
        maximum,
    )


def _normalize_min_max(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    """
    Normalize into [0,1].
    """

    denominator = (
        float(
            maximum
        )
        -
        float(
            minimum
        )
    )

    if denominator <= 0:
        return 0.0

    return _clip01(
        (
            float(
                value
            )
            -
            float(
                minimum
            )
        )
        /
        denominator
    )


def _evidence_completeness(
    row: Mapping[str, Any],
    columns: tuple[str, ...],
) -> float:
    """
    Fraction of evidence fields populated.
    """

    if not columns:
        return 1.0

    populated = sum(
        0
        if _is_missing(
            row.get(
                column
            )
        )
        else 1

        for column
        in columns
    )

    return float(
        populated
        /
        len(
            columns
        )
    )


# ============================================================
# JSON HELPERS
# ============================================================


def _json_ready(
    value: Any,
) -> Any:
    """
    Convert pandas/numpy values into JSON-safe values.
    """

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(
                key
            ):
            _json_ready(
                item
            )

            for key,
            item
            in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            _json_ready(
                item
            )
            for item
            in value
        ]

    if isinstance(
        value,
        pd.Timestamp,
    ):
        if pd.isna(
            value
        ):
            return None

        return value.isoformat()

    if isinstance(
        value,
        np.datetime64,
    ):
        timestamp = pd.Timestamp(
            value
        )

        if pd.isna(
            timestamp
        ):
            return None

        return timestamp.isoformat()

    if isinstance(
        value,
        np.integer,
    ):
        return int(
            value
        )

    if isinstance(
        value,
        np.floating,
    ):
        if not np.isfinite(
            value
        ):
            return None

        return float(
            value
        )

    if isinstance(
        value,
        np.bool_,
    ):
        return bool(
            value
        )

    if _is_missing(
        value
    ):
        return None

    return value


def _canonical_json(
    payload: Mapping[str, Any],
) -> str:
    """
    Deterministic JSON serialization.
    """

    return json.dumps(
        _json_ready(
            payload
        ),
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=False,
    )


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
    Read synthetic generation window.
    """

    time_config = generation.get(
        "time"
    )

    if not isinstance(
        time_config,
        Mapping,
    ):
        raise KeyError(
            "Missing generation.time configuration"
        )

    start_value = time_config.get(
        "start_date",
        time_config.get(
            "start"
        ),
    )

    end_value = time_config.get(
        "end_date",
        time_config.get(
            "end"
        ),
    )

    timezone = str(
        time_config.get(
            "timezone",
            "Asia/Kolkata",
        )
    )

    if start_value is None:
        raise KeyError(
            "Missing generation.time.start_date"
        )

    if end_value is None:
        raise KeyError(
            "Missing generation.time.end_date"
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
            "Generation end must be after generation start"
        )

    return (
        start,
        end,
        timezone,
    )


def _get_recommendation_target_count(
    generation: Mapping[str, Any],
) -> int:
    """
    Read governance.recommendation_target_count.
    """

    governance = generation.get(
        "governance"
    )

    if not isinstance(
        governance,
        Mapping,
    ):
        raise KeyError(
            "Missing generation.governance configuration"
        )

    value = governance.get(
        "recommendation_target_count"
    )

    if value is None:
        raise KeyError(
            "Missing governance.recommendation_target_count"
        )

    count = int(
        value
    )

    if count <= 0:
        raise ValueError(
            "recommendation_target_count must be > 0"
        )

    return count


# ============================================================
# INPUT VALIDATION
# ============================================================


def _require_columns(
    name: str,
    dataframe: pd.DataFrame,
    required: set[str],
    primary_key: str,
) -> None:
    """
    Validate one upstream evidence DataFrame.
    """

    if dataframe.empty:
        raise ValueError(
            f"{name} DataFrame cannot be empty"
        )

    missing = (
        required
        -
        set(
            dataframe.columns
        )
    )

    if missing:
        raise ValueError(
            f"{name} DataFrame is missing required columns: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    if (
        dataframe[
            primary_key
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            f"{name}.{primary_key} cannot contain null values"
        )

    if (
        dataframe[
            primary_key
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            f"Duplicate {primary_key} values found in {name}"
        )


def _validate_inputs(
    allocations: pd.DataFrame,
    cross_sell_events: pd.DataFrame,
    collection_cases: pd.DataFrame,
    shipments: pd.DataFrame,
    credit_listings: pd.DataFrame,
) -> None:
    """
    Validate real upstream schemas.
    """

    # ========================================================
    # AUTO - exact live evidence used by governance
    # ========================================================

    _require_columns(
        name="allocations",
        dataframe=allocations,
        primary_key="allocation_id",
        required={
            "allocation_id",
            "booking_id",

            "dealer_id",
            "dealer_name",

            "region_id",
            "region_name",

            "city_id",
            "city_name",

            "vehicle_model_id",
            "vehicle_model_name",

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
        },
    )

    # ========================================================
    # FINANCE
    # ========================================================

    _require_columns(
        name="cross_sell_events",
        dataframe=cross_sell_events,
        primary_key="cross_sell_event_id",
        required={
            "cross_sell_event_id",
            "finance_customer_id",

            "source_product_code",

            "offered_product_code",
            "offered_product_name",

            "offered_at",
            "offer_channel",

            "offer_amount_inr",
            "offer_interest_rate_pct",
            "offer_tenure_months",
            "estimated_offer_emi_inr",

            "customer_response",
            "responded_at",
        },
    )

    # ========================================================
    # COLLECTIONS
    # ========================================================

    _require_columns(
        name="collection_cases",
        dataframe=collection_cases,
        primary_key="collection_case_id",
        required={
            "collection_case_id",

            "loan_account_id",
            "finance_customer_id",

            "product_name",

            "case_created_at",

            "observed_dpd_at_trigger_event",
            "dpd_at_case_creation",

            "arrears_at_trigger_event_inr",

            "priority_at_creation",

            "peak_observed_dpd",

            "case_status",

            "current_dpd",
            "current_arrears_inr",

            "resolved_at",
        },
    )

    # ========================================================
    # LOGISTICS
    # ========================================================

    _require_columns(
        name="shipments",
        dataframe=shipments,
        primary_key="shipment_id",
        required={
            "shipment_id",
            "route_id",

            "origin_city_name",
            "destination_city_name",

            "vehicle_id",

            "priority",
            "units",

            "dispatch_time",
            "expected_arrival",
            "actual_arrival",

            "delay_minutes",
            "sla_breach",

            "weather_disruption",
            "vehicle_breakdown",
            "warehouse_delay",
            "port_delay",
            "customs_delay",
        },
    )

    # ========================================================
    # CIRCULARITY
    # ========================================================

    _require_columns(
        name="credit_listings",
        dataframe=credit_listings,
        primary_key="carbon_credit_listing_id",
        required={
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
        },
    )


# ============================================================
# INTERNAL CANDIDATE
# ============================================================


def _candidate(
    domain: str,
    target_entity_id: str,
    recommendation_type: str,
    evidence: Mapping[str, Any],
    expected_impact: Mapping[str, Any],
    confidence: float,
    risk_level: str,
    candidate_score: float,
) -> dict[str, Any]:
    """
    Build internal recommendation candidate.
    """

    return {
        "domain":
            domain,

        "use_case":
            DOMAIN_USE_CASES[
                domain
            ],

        "target_entity_type":
            DOMAIN_TARGET_ENTITY_TYPES[
                domain
            ],

        "target_entity_id":
            str(
                target_entity_id
            ),

        "recommendation_type":
            str(
                recommendation_type
            ),

        "_evidence":
            dict(
                evidence
            ),

        "_expected_impact":
            dict(
                expected_impact
            ),

        "_confidence":
            _clip01(
                confidence
            ),

        "_risk_level":
            str(
                risk_level
            ),

        "_candidate_score":
            _clip01(
                candidate_score
            ),
    }


# ============================================================
# AUTO RECOMMENDATIONS
# ============================================================


def _build_auto_candidates(
    allocations: pd.DataFrame,
    snapshot_at: pd.Timestamp,
) -> pd.DataFrame:
    """
    Build dealer-allocation recommendations from the actual
    frozen allocation evidence.

    Important:
        waiting_list currently has no variation.
        allocation_status currently has no variation.

    Therefore the main ranking signals are:

        regional demand
        allocation wait
        allocation priority
        dealer inventory remaining
        production-batch inventory remaining
    """

    work = allocations.copy()

    work[
        "_allocation_date_utc"
    ] = pd.to_datetime(
        work[
            "allocation_date"
        ],
        errors="coerce",
        utc=True,
    )

    snapshot_utc = (
        snapshot_at
        .tz_convert(
            "UTC"
        )
    )

    work = work[
        work[
            "_allocation_date_utc"
        ].isna()
        |
        (
            work[
                "_allocation_date_utc"
            ]
            <= snapshot_utc
        )
    ].copy()

    if work.empty:
        return pd.DataFrame()

    # ========================================================
    # DATASET-RELATIVE NORMALIZATION
    # ========================================================

    wait_scale = _quantile_scale(
        work[
            "allocation_wait_hours"
        ],
        quantile=0.95,
        minimum=1.0,
    )

    dealer_inventory_scale = _quantile_scale(
        work[
            "inventory_after"
        ],
        quantile=0.95,
        minimum=1.0,
    )

    batch_inventory_scale = _quantile_scale(
        work[
            "production_batch_inventory_after"
        ],
        quantile=0.95,
        minimum=1.0,
    )

    queue_scale = _quantile_scale(
        work[
            "waiting_list"
        ],
        quantile=0.95,
        minimum=1.0,
    )

    (
        demand_min,
        demand_max,
    ) = _min_max_bounds(
        work[
            "regional_demand_index"
        ]
    )

    candidates: list[
        dict[str, Any]
    ] = []

    for row in work.to_dict(
        orient="records"
    ):

        requested_units = max(
            0,
            _safe_int(
                row[
                    "requested_units"
                ]
            ),
        )

        allocated_units = max(
            0,
            _safe_int(
                row[
                    "allocated_units"
                ]
            ),
        )

        fulfillment_ratio = _clip01(
            allocated_units
            /
            max(
                requested_units,
                1,
            )
        )

        waiting_list = max(
            0,
            _safe_int(
                row[
                    "waiting_list"
                ]
            ),
        )

        dealer_capacity = max(
            1,
            _safe_int(
                row[
                    "dealer_capacity"
                ],
                default=1,
            ),
        )

        demand = max(
            0.0,
            _safe_float(
                row[
                    "regional_demand_index"
                ]
            ),
        )

        priority_score = _clip01(
            _safe_float(
                row[
                    "allocation_priority_score"
                ]
            )
        )

        allocation_priority = str(
            row[
                "allocation_priority"
            ]
        ).upper()

        allocation_status = str(
            row[
                "allocation_status"
            ]
        ).upper()

        wait_hours = max(
            0.0,
            _safe_float(
                row[
                    "allocation_wait_hours"
                ]
            ),
        )

        inventory_before = max(
            0.0,
            _safe_float(
                row[
                    "inventory_before"
                ]
            ),
        )

        inventory_after = max(
            0.0,
            _safe_float(
                row[
                    "inventory_after"
                ]
            ),
        )

        batch_inventory_before = max(
            0.0,
            _safe_float(
                row[
                    "production_batch_inventory_before"
                ]
            ),
        )

        batch_inventory_after = max(
            0.0,
            _safe_float(
                row[
                    "production_batch_inventory_after"
                ]
            ),
        )

        # ----------------------------------------------------
        # Derived transparent rule inputs
        # ----------------------------------------------------

        demand_component = (
            _normalize_min_max(
                value=demand,
                minimum=demand_min,
                maximum=demand_max,
            )
        )

        wait_component = _clip01(
            wait_hours
            /
            wait_scale
        )

        queue_component = _clip01(
            waiting_list
            /
            queue_scale
        )

        # Low remaining inventory means stronger pressure.
        dealer_inventory_pressure = (
            1.0
            -
            _clip01(
                inventory_after
                /
                dealer_inventory_scale
            )
        )

        batch_inventory_pressure = (
            1.0
            -
            _clip01(
                batch_inventory_after
                /
                batch_inventory_scale
            )
        )

        dealer_depletion_ratio = _clip01(
            (
                inventory_before
                -
                inventory_after
            )
            /
            max(
                inventory_before,
                1.0,
            )
        )

        batch_depletion_ratio = _clip01(
            (
                batch_inventory_before
                -
                batch_inventory_after
            )
            /
            max(
                batch_inventory_before,
                1.0,
            )
        )

        # ----------------------------------------------------
        # Candidate score
        #
        # waiting_list contributes only 3% because the current
        # generated world has waiting_list == 0 for all records.
        # ----------------------------------------------------

        candidate_score = _clip01(
            0.28
            * demand_component
            +
            0.24
            * wait_component
            +
            0.18
            * priority_score
            +
            0.16
            * dealer_inventory_pressure
            +
            0.07
            * batch_inventory_pressure
            +
            0.04
            * dealer_depletion_ratio
            +
            0.03
            * queue_component
        )

        # ----------------------------------------------------
        # Recommendation type
        # ----------------------------------------------------

        if (
            dealer_inventory_pressure
            >= 0.65
            and
            demand_component
            >= 0.60
        ):
            recommendation_type = (
                "RECOMMEND_DEALER_INVENTORY_REBALANCE"
            )

        elif (
            wait_component
            >= 0.70
            and
            priority_score
            >= 0.70
        ):
            recommendation_type = (
                "RECOMMEND_ALLOCATION_CYCLE_REVIEW"
            )

        elif (
            batch_inventory_pressure
            >= 0.70
            and
            demand_component
            >= 0.60
        ):
            recommendation_type = (
                "RECOMMEND_SOURCE_BATCH_CAPACITY_REVIEW"
            )

        else:
            recommendation_type = (
                "RECOMMEND_DEALER_ALLOCATION_REBALANCE"
            )

        # ----------------------------------------------------
        # Risk
        # ----------------------------------------------------

        if (
            candidate_score
            >= 0.72
            and
            (
                allocation_priority
                == "HIGH"
                or
                demand_component
                >= 0.75
            )
        ):
            risk_level = (
                "HIGH"
            )

        elif (
            candidate_score
            >= 0.45
        ):
            risk_level = (
                "MEDIUM"
            )

        else:
            risk_level = (
                "LOW"
            )

        # ----------------------------------------------------
        # Confidence
        #
        # Maximum by construction is below 1.0.
        # ----------------------------------------------------

        completeness = _evidence_completeness(
            row,
            (
                "dealer_id",
                "region_id",
                "vehicle_model_id",

                "allocation_date",

                "requested_units",
                "allocated_units",

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
            ),
        )

        signal_agreement = _clip01(
            (
                demand_component
                +
                wait_component
                +
                priority_score
                +
                dealer_inventory_pressure
                +
                batch_inventory_pressure
            )
            /
            5.0
        )

        confidence = _clip01(
            0.38
            +
            0.22
            * completeness
            +
            0.18
            * signal_agreement
            +
            0.12
            * fulfillment_ratio
            +
            0.08
            * (
                1.0
                if allocation_status
                == "ALLOCATED"
                else 0.0
            )
        )

        # ----------------------------------------------------
        # Evidence payload
        # ----------------------------------------------------

        evidence = {
            "source_record_type":
                "ALLOCATION",

            "source_record_id":
                row[
                    "allocation_id"
                ],

            "booking_id":
                row[
                    "booking_id"
                ],

            "dealer_id":
                row[
                    "dealer_id"
                ],

            "dealer_name":
                row[
                    "dealer_name"
                ],

            "region_id":
                row[
                    "region_id"
                ],

            "region_name":
                row[
                    "region_name"
                ],

            "city_id":
                row[
                    "city_id"
                ],

            "city_name":
                row[
                    "city_name"
                ],

            "vehicle_model_id":
                row[
                    "vehicle_model_id"
                ],

            "vehicle_model_name":
                row[
                    "vehicle_model_name"
                ],

            "allocation_date":
                row[
                    "allocation_date"
                ],

            "requested_units":
                requested_units,

            "allocated_units":
                allocated_units,

            "fulfillment_ratio":
                round(
                    fulfillment_ratio,
                    6,
                ),

            "waiting_list":
                waiting_list,

            "dealer_capacity":
                dealer_capacity,

            "dealer_capacity_source":
                row[
                    "dealer_capacity_source"
                ],

            "regional_demand_index":
                round(
                    demand,
                    6,
                ),

            "allocation_wait_hours":
                round(
                    wait_hours,
                    3,
                ),

            "allocation_priority_score":
                round(
                    priority_score,
                    6,
                ),

            "allocation_priority":
                allocation_priority,

            "allocation_status":
                allocation_status,

            "inventory_before":
                round(
                    inventory_before,
                    3,
                ),

            "inventory_after":
                round(
                    inventory_after,
                    3,
                ),

            "production_batch_inventory_before":
                round(
                    batch_inventory_before,
                    3,
                ),

            "production_batch_inventory_after":
                round(
                    batch_inventory_after,
                    3,
                ),

            "derived_demand_component":
                round(
                    demand_component,
                    6,
                ),

            "derived_wait_component":
                round(
                    wait_component,
                    6,
                ),

            "derived_dealer_inventory_pressure":
                round(
                    dealer_inventory_pressure,
                    6,
                ),

            "derived_batch_inventory_pressure":
                round(
                    batch_inventory_pressure,
                    6,
                ),

            "derived_dealer_depletion_ratio":
                round(
                    dealer_depletion_ratio,
                    6,
                ),

            "derived_batch_depletion_ratio":
                round(
                    batch_depletion_ratio,
                    6,
                ),
        }

        expected_impact = {
            "metric":
                "allocation_flow_efficiency",

            "direction":
                "IMPROVE",

            "booking_exposure":
                1,

            "basis":
                (
                    "observed_demand_wait_priority_"
                    "and_inventory_evidence"
                ),
        }

        candidates.append(
            _candidate(
                domain=DOMAIN_AUTO,

                target_entity_id=
                    row[
                        "allocation_id"
                    ],

                recommendation_type=
                    recommendation_type,

                evidence=
                    evidence,

                expected_impact=
                    expected_impact,

                confidence=
                    confidence,

                risk_level=
                    risk_level,

                candidate_score=
                    candidate_score,
            )
        )

    return pd.DataFrame(
        candidates
    )


# ============================================================
# FINANCE RECOMMENDATIONS
# ============================================================


def _build_finance_candidates(
    cross_sell_events: pd.DataFrame,
    snapshot_at: pd.Timestamp,
) -> pd.DataFrame:
    """
    Build cross-sell follow-up recommendations.

    No underwriting decision is created here.
    """

    work = cross_sell_events.copy()

    work[
        "_offered_at_utc"
    ] = pd.to_datetime(
        work[
            "offered_at"
        ],
        errors="coerce",
        utc=True,
    )

    work[
        "_responded_at_utc"
    ] = pd.to_datetime(
        work[
            "responded_at"
        ],
        errors="coerce",
        utc=True,
    )

    snapshot_utc = (
        snapshot_at
        .tz_convert(
            "UTC"
        )
    )

    work = work[
        work[
            "_offered_at_utc"
        ].notna()
        &
        (
            work[
                "_offered_at_utc"
            ]
            <= snapshot_utc
        )
    ].copy()

    if work.empty:
        return pd.DataFrame()

    amount_scale = _quantile_scale(
        work[
            "offer_amount_inr"
        ],
        quantile=0.95,
        minimum=1.0,
    )

    candidates: list[
        dict[str, Any]
    ] = []

    for row in work.to_dict(
        orient="records"
    ):

        raw_response = str(
            row[
                "customer_response"
            ]
        ).upper()

        responded_at_utc = row[
            "_responded_at_utc"
        ]

        response_available = (
            not _is_missing(
                responded_at_utc
            )
            and
            pd.Timestamp(
                responded_at_utc
            )
            <= snapshot_utc
        )

        if response_available:
            response = (
                raw_response
            )
        else:
            response = (
                "NO_RESPONSE"
            )

        if response == "INTERESTED":

            response_component = (
                1.0
            )

            recommendation_type = (
                "RECOMMEND_RELATIONSHIP_MANAGER_FOLLOWUP"
            )

        elif response == "NO_RESPONSE":

            response_component = (
                0.60
            )

            recommendation_type = (
                "RECOMMEND_CROSS_SELL_OFFER_FOLLOWUP"
            )

        elif response == "DECLINED":

            response_component = (
                0.20
            )

            recommendation_type = (
                "RECOMMEND_SUPPRESS_REPEAT_OFFER"
            )

        else:

            response_component = (
                0.35
            )

            recommendation_type = (
                "RECOMMEND_CROSS_SELL_REVIEW"
            )

        offer_amount = max(
            0.0,
            _safe_float(
                row[
                    "offer_amount_inr"
                ]
            ),
        )

        amount_component = _clip01(
            offer_amount
            /
            amount_scale
        )

        candidate_score = _clip01(
            0.70
            * response_component
            +
            0.20
            * amount_component
            +
            0.10
            * (
                1.0
                if response_available
                else 0.0
            )
        )

        if (
            response
            == "INTERESTED"
            and
            amount_component
            >= 0.75
        ):
            risk_level = (
                "MEDIUM"
            )

        elif response == "DECLINED":
            risk_level = (
                "MEDIUM"
            )

        else:
            risk_level = (
                "LOW"
            )

        completeness = _evidence_completeness(
            row,
            (
                "finance_customer_id",
                "source_product_code",
                "offered_product_code",
                "offered_at",
                "offer_channel",
                "offer_amount_inr",
                "offer_interest_rate_pct",
                "offer_tenure_months",
            ),
        )

        # Maximum < 1.0.
        confidence = _clip01(
            0.38
            +
            0.22
            * completeness
            +
            0.22
            * response_component
            +
            0.08
            * (
                1.0
                if response_available
                else 0.0
            )
            +
            0.06
            * amount_component
        )

        evidence = {
            "source_record_type":
                "CROSS_SELL_EVENT",

            "source_record_id":
                row[
                    "cross_sell_event_id"
                ],

            "finance_customer_id":
                row[
                    "finance_customer_id"
                ],

            "source_product_code":
                row[
                    "source_product_code"
                ],

            "offered_product_code":
                row[
                    "offered_product_code"
                ],

            "offered_product_name":
                row[
                    "offered_product_name"
                ],

            "offered_at":
                row[
                    "offered_at"
                ],

            "offer_channel":
                row[
                    "offer_channel"
                ],

            "offer_amount_inr":
                round(
                    offer_amount,
                    2,
                ),

            "offer_interest_rate_pct":
                round(
                    _safe_float(
                        row[
                            "offer_interest_rate_pct"
                        ]
                    ),
                    4,
                ),

            "offer_tenure_months":
                _safe_int(
                    row[
                        "offer_tenure_months"
                    ]
                ),

            "estimated_offer_emi_inr":
                round(
                    _safe_float(
                        row[
                            "estimated_offer_emi_inr"
                        ]
                    ),
                    2,
                ),

            "customer_response_as_of_snapshot":
                response,

            "responded_at":
                (
                    row[
                        "responded_at"
                    ]
                    if response_available
                    else None
                ),
        }

        expected_impact = {
            "metric":
                "cross_sell_followup_opportunity",

            "direction":
                (
                    "PRESERVE_CUSTOMER_INTENT"
                    if response
                    == "INTERESTED"
                    else (
                        "IMPROVE_FOLLOWUP_DISCIPLINE"
                        if response
                        == "NO_RESPONSE"
                        else
                        "REDUCE_UNWANTED_REPEAT_CONTACT"
                    )
                ),

            "offer_exposure_inr":
                round(
                    offer_amount,
                    2,
                ),

            "basis":
                (
                    "observed_cross_sell_offer_"
                    "and_response_history"
                ),
        }

        candidates.append(
            _candidate(
                domain=
                    DOMAIN_FINANCE,

                target_entity_id=
                    row[
                        "cross_sell_event_id"
                    ],

                recommendation_type=
                    recommendation_type,

                evidence=
                    evidence,

                expected_impact=
                    expected_impact,

                confidence=
                    confidence,

                risk_level=
                    risk_level,

                candidate_score=
                    candidate_score,
            )
        )

    return pd.DataFrame(
        candidates
    )


# ============================================================
# COLLECTIONS RECOMMENDATIONS
# ============================================================


def _build_collections_candidates(
    collection_cases: pd.DataFrame,
    snapshot_at: pd.Timestamp,
) -> pd.DataFrame:
    """
    Build collections intervention recommendations from
    observed DPD and arrears evidence.
    """

    work = collection_cases.copy()

    work[
        "_case_created_at_utc"
    ] = pd.to_datetime(
        work[
            "case_created_at"
        ],
        errors="coerce",
        utc=True,
    )

    work[
        "_resolved_at_utc"
    ] = pd.to_datetime(
        work[
            "resolved_at"
        ],
        errors="coerce",
        utc=True,
    )

    snapshot_utc = (
        snapshot_at
        .tz_convert(
            "UTC"
        )
    )

    work = work[
        work[
            "_case_created_at_utc"
        ].notna()
        &
        (
            work[
                "_case_created_at_utc"
            ]
            <= snapshot_utc
        )
    ].copy()

    if work.empty:
        return pd.DataFrame()

    arrears_scale = _quantile_scale(
        work[
            "current_arrears_inr"
        ],
        quantile=0.95,
        minimum=1.0,
    )

    candidates: list[
        dict[str, Any]
    ] = []

    for row in work.to_dict(
        orient="records"
    ):

        current_dpd = max(
            0,
            _safe_int(
                row[
                    "current_dpd"
                ]
            ),
        )

        peak_dpd = max(
            current_dpd,
            _safe_int(
                row[
                    "peak_observed_dpd"
                ]
            ),
        )

        current_arrears = max(
            0.0,
            _safe_float(
                row[
                    "current_arrears_inr"
                ]
            ),
        )

        resolved_at_utc = row[
            "_resolved_at_utc"
        ]

        resolved_before_snapshot = (
            not _is_missing(
                resolved_at_utc
            )
            and
            pd.Timestamp(
                resolved_at_utc
            )
            <= snapshot_utc
        )

        source_status = str(
            row[
                "case_status"
            ]
        ).upper()

        case_open = (
            source_status
            == "OPEN"
            or
            not resolved_before_snapshot
        )

        dpd_component = _clip01(
            current_dpd
            /
            360.0
        )

        peak_component = _clip01(
            peak_dpd
            /
            360.0
        )

        arrears_component = _clip01(
            current_arrears
            /
            arrears_scale
        )

        open_component = (
            1.0
            if case_open
            else 0.0
        )

        candidate_score = _clip01(
            0.45
            * dpd_component
            +
            0.20
            * peak_component
            +
            0.25
            * arrears_component
            +
            0.10
            * open_component
        )

        if case_open:

            if (
                current_dpd
                >= 180
                or
                (
                    current_dpd
                    >= 90
                    and
                    arrears_component
                    >= 0.50
                )
            ):
                recommendation_type = (
                    "RECOMMEND_RESTRUCTURING_REVIEW"
                )

            elif current_dpd >= 60:
                recommendation_type = (
                    "RECOMMEND_PRIORITY_COLLECTIONS_REVIEW"
                )

            else:
                recommendation_type = (
                    "RECOMMEND_EARLY_DELINQUENCY_OUTREACH"
                )

        else:
            recommendation_type = (
                "RECOMMEND_COLLECTIONS_CASE_LEARNING_REVIEW"
            )

        if (
            current_dpd
            >= 180
            or
            current_arrears
            >= arrears_scale
        ):
            risk_level = (
                "HIGH"
            )

        elif (
            current_dpd
            >= 60
            or
            arrears_component
            >= 0.50
        ):
            risk_level = (
                "MEDIUM"
            )

        else:
            risk_level = (
                "LOW"
            )

        completeness = _evidence_completeness(
            row,
            (
                "loan_account_id",
                "finance_customer_id",
                "case_created_at",
                "dpd_at_case_creation",
                "peak_observed_dpd",
                "current_dpd",
                "current_arrears_inr",
                "case_status",
            ),
        )

        signal_agreement = _clip01(
            (
                dpd_component
                +
                peak_component
                +
                arrears_component
            )
            /
            3.0
        )

        # Maximum < 1.0.
        confidence = _clip01(
            0.38
            +
            0.22
            * completeness
            +
            0.20
            * signal_agreement
            +
            0.12
            * open_component
            +
            0.06
            * peak_component
        )

        evidence = {
            "source_record_type":
                "COLLECTION_CASE",

            "source_record_id":
                row[
                    "collection_case_id"
                ],

            "loan_account_id":
                row[
                    "loan_account_id"
                ],

            "finance_customer_id":
                row[
                    "finance_customer_id"
                ],

            "product_name":
                row[
                    "product_name"
                ],

            "case_created_at":
                row[
                    "case_created_at"
                ],

            "observed_dpd_at_trigger_event":
                _safe_int(
                    row[
                        "observed_dpd_at_trigger_event"
                    ]
                ),

            "dpd_at_case_creation":
                _safe_int(
                    row[
                        "dpd_at_case_creation"
                    ]
                ),

            "arrears_at_trigger_event_inr":
                round(
                    _safe_float(
                        row[
                            "arrears_at_trigger_event_inr"
                        ]
                    ),
                    2,
                ),

            "priority_at_creation":
                row[
                    "priority_at_creation"
                ],

            "peak_observed_dpd":
                peak_dpd,

            "case_status_as_of_snapshot":
                (
                    "OPEN"
                    if case_open
                    else
                    "RESOLVED"
                ),

            "current_dpd":
                current_dpd,

            "current_arrears_inr":
                round(
                    current_arrears,
                    2,
                ),

            "resolved_at":
                (
                    row[
                        "resolved_at"
                    ]
                    if resolved_before_snapshot
                    else None
                ),
        }

        expected_impact = {
            "metric":
                "collections_arrears_exposure",

            "direction":
                (
                    "REDUCE"
                    if case_open
                    else
                    "LEARN_FROM_RESOLVED_CASE"
                ),

            "arrears_exposure_inr":
                round(
                    current_arrears,
                    2,
                ),

            "basis":
                (
                    "observed_dpd_and_"
                    "arrears_history"
                ),
        }

        candidates.append(
            _candidate(
                domain=
                    DOMAIN_COLLECTIONS,

                target_entity_id=
                    row[
                        "collection_case_id"
                    ],

                recommendation_type=
                    recommendation_type,

                evidence=
                    evidence,

                expected_impact=
                    expected_impact,

                confidence=
                    confidence,

                risk_level=
                    risk_level,

                candidate_score=
                    candidate_score,
            )
        )

    return pd.DataFrame(
        candidates
    )


# ============================================================
# LOGISTICS RECOMMENDATIONS
# ============================================================


def _build_logistics_candidates(
    shipments: pd.DataFrame,
    snapshot_at: pd.Timestamp,
) -> pd.DataFrame:
    """
    Generate route/SLA mitigation recommendations from completed
    historical shipment evidence.

    Historical completed shipments are not treated as if they can
    still be rerouted.
    """

    work = shipments.copy()

    work[
        "_dispatch_time_utc"
    ] = pd.to_datetime(
        work[
            "dispatch_time"
        ],
        errors="coerce",
        utc=True,
    )

    work[
        "_expected_arrival_utc"
    ] = pd.to_datetime(
        work[
            "expected_arrival"
        ],
        errors="coerce",
        utc=True,
    )

    work[
        "_actual_arrival_utc"
    ] = pd.to_datetime(
        work[
            "actual_arrival"
        ],
        errors="coerce",
        utc=True,
    )

    snapshot_utc = (
        snapshot_at
        .tz_convert(
            "UTC"
        )
    )

    work = work[
        work[
            "_actual_arrival_utc"
        ].notna()
        &
        (
            work[
                "_actual_arrival_utc"
            ]
            <= snapshot_utc
        )
    ].copy()

    if work.empty:
        return pd.DataFrame()

    delay_scale = _quantile_scale(
        work[
            "delay_minutes"
        ],
        quantile=0.95,
        minimum=60.0,
    )

    candidates: list[
        dict[str, Any]
    ] = []

    for row in work.to_dict(
        orient="records"
    ):

        delay_minutes = max(
            0.0,
            _safe_float(
                row[
                    "delay_minutes"
                ]
            ),
        )

        sla_breach = _to_bool(
            row[
                "sla_breach"
            ]
        )

        disruption_flags = {
            "weather_disruption":
                _to_bool(
                    row[
                        "weather_disruption"
                    ]
                ),

            "vehicle_breakdown":
                _to_bool(
                    row[
                        "vehicle_breakdown"
                    ]
                ),

            "warehouse_delay":
                _to_bool(
                    row[
                        "warehouse_delay"
                    ]
                ),

            "port_delay":
                _to_bool(
                    row[
                        "port_delay"
                    ]
                ),

            "customs_delay":
                _to_bool(
                    row[
                        "customs_delay"
                    ]
                ),
        }

        disruption_count = int(
            sum(
                1
                for value
                in disruption_flags.values()
                if value
            )
        )

        priority = str(
            row[
                "priority"
            ]
        ).upper()

        priority_component = {
            "LOW":
                0.20,

            "NORMAL":
                0.40,

            "HIGH":
                0.75,

            "CRITICAL":
                1.00,
        }.get(
            priority,
            0.40,
        )

        delay_component = _clip01(
            delay_minutes
            /
            delay_scale
        )

        disruption_component = _clip01(
            disruption_count
            /
            3.0
        )

        breach_component = (
            1.0
            if sla_breach
            else 0.0
        )

        candidate_score = _clip01(
            0.35
            * breach_component
            +
            0.25
            * delay_component
            +
            0.20
            * disruption_component
            +
            0.20
            * priority_component
        )

        if sla_breach:
            recommendation_type = (
                "RECOMMEND_ROUTE_SLA_MITIGATION"
            )

        elif disruption_count > 0:
            recommendation_type = (
                "RECOMMEND_ROUTE_DISRUPTION_CONTINGENCY"
            )

        elif (
            priority
            in {
                "HIGH",
                "CRITICAL",
            }
            and
            delay_minutes
            >= 60.0
        ):
            recommendation_type = (
                "RECOMMEND_PRIORITY_ROUTE_REVIEW"
            )

        else:
            recommendation_type = (
                "RECOMMEND_ROUTE_PERFORMANCE_REVIEW"
            )

        if (
            sla_breach
            or
            (
                priority
                == "CRITICAL"
                and
                disruption_count
                > 0
            )
        ):
            risk_level = (
                "HIGH"
            )

        elif (
            disruption_count
            > 0
            or
            delay_minutes
            >= 120.0
        ):
            risk_level = (
                "MEDIUM"
            )

        else:
            risk_level = (
                "LOW"
            )

        completeness = _evidence_completeness(
            row,
            (
                "route_id",
                "priority",
                "dispatch_time",
                "expected_arrival",
                "actual_arrival",
                "delay_minutes",
                "sla_breach",
            ),
        )

        signal_strength = _clip01(
            (
                breach_component
                +
                delay_component
                +
                disruption_component
            )
            /
            3.0
        )

        # Maximum < 1.0.
        confidence = _clip01(
            0.42
            +
            0.22
            * completeness
            +
            0.24
            * signal_strength
            +
            0.08
            * priority_component
        )

        evidence = {
            "source_record_type":
                "SHIPMENT",

            "source_record_id":
                row[
                    "shipment_id"
                ],

            "route_id":
                row[
                    "route_id"
                ],

            "origin_city_name":
                row[
                    "origin_city_name"
                ],

            "destination_city_name":
                row[
                    "destination_city_name"
                ],

            "vehicle_id":
                row[
                    "vehicle_id"
                ],

            "priority":
                priority,

            "units":
                _safe_int(
                    row[
                        "units"
                    ]
                ),

            "dispatch_time":
                row[
                    "dispatch_time"
                ],

            "expected_arrival":
                row[
                    "expected_arrival"
                ],

            "actual_arrival":
                row[
                    "actual_arrival"
                ],

            "delay_minutes":
                round(
                    delay_minutes,
                    3,
                ),

            "sla_breach":
                sla_breach,

            "disruption_count":
                disruption_count,

            **disruption_flags,
        }

        expected_impact = {
            "metric":
                "future_route_sla_exposure",

            "direction":
                "REDUCE",

            "route_id":
                row[
                    "route_id"
                ],

            "historical_delay_minutes":
                round(
                    delay_minutes,
                    3,
                ),

            "basis":
                (
                    "observed_completed_shipment_"
                    "exception_history"
                ),
        }

        candidates.append(
            _candidate(
                domain=
                    DOMAIN_LOGISTICS,

                target_entity_id=
                    row[
                        "shipment_id"
                    ],

                recommendation_type=
                    recommendation_type,

                evidence=
                    evidence,

                expected_impact=
                    expected_impact,

                confidence=
                    confidence,

                risk_level=
                    risk_level,

                candidate_score=
                    candidate_score,
            )
        )

    return pd.DataFrame(
        candidates
    )


# ============================================================
# CIRCULARITY RECOMMENDATIONS
# ============================================================


def _build_circularity_candidates(
    credit_listings: pd.DataFrame,
    snapshot_at: pd.Timestamp,
) -> pd.DataFrame:
    """
    Generate dMRV and marketplace recommendations from the
    observed carbon-credit listing evidence.
    """

    work = credit_listings.copy()

    work[
        "_listing_at_utc"
    ] = pd.to_datetime(
        work[
            "listing_at"
        ],
        errors="coerce",
        utc=True,
    )

    snapshot_utc = (
        snapshot_at
        .tz_convert(
            "UTC"
        )
    )

    work = work[
        work[
            "_listing_at_utc"
        ].notna()
        &
        (
            work[
                "_listing_at_utc"
            ]
            <= snapshot_utc
        )
    ].copy()

    if work.empty:
        return pd.DataFrame()

    candidates: list[
        dict[str, Any]
    ] = []

    for row in work.to_dict(
        orient="records"
    ):

        reference_price = max(
            0.0,
            _safe_float(
                row[
                    "market_reference_price_per_tco2e_inr"
                ]
            ),
        )

        ask_price = max(
            0.0,
            _safe_float(
                row[
                    "seller_ask_price_per_tco2e_inr"
                ]
            ),
        )

        inquiry_count = max(
            0,
            _safe_int(
                row[
                    "buyer_inquiry_count"
                ]
            ),
        )

        bid_count = max(
            0,
            _safe_int(
                row[
                    "buyer_bid_count"
                ]
            ),
        )

        if _is_missing(
            row[
                "highest_bid_price_per_tco2e_inr"
            ]
        ):
            highest_bid = (
                None
            )

        else:
            highest_bid = max(
                0.0,
                _safe_float(
                    row[
                        "highest_bid_price_per_tco2e_inr"
                    ]
                ),
            )

        available_dmrv = max(
            0,
            _safe_int(
                row[
                    "dmrv_available_records"
                ]
            ),
        )

        missing_dmrv = max(
            0,
            _safe_int(
                row[
                    "dmrv_missing_records"
                ]
            ),
        )

        total_dmrv = (
            available_dmrv
            +
            missing_dmrv
        )

        missing_ratio = (
            missing_dmrv
            /
            total_dmrv
            if total_dmrv
            > 0
            else 1.0
        )

        if reference_price > 0:

            price_gap_ratio = (
                ask_price
                -
                reference_price
            ) / reference_price

        else:

            price_gap_ratio = (
                0.0
            )

        price_gap_component = _clip01(
            abs(
                price_gap_ratio
            )
            /
            0.25
        )

        missing_component = _clip01(
            missing_ratio
        )

        market_activity_component = _clip01(
            (
                inquiry_count
                +
                2
                * bid_count
            )
            /
            10.0
        )

        weak_bid_component = (
            0.0
        )

        if (
            highest_bid
            is not None
            and
            ask_price
            > 0
        ):

            weak_bid_component = _clip01(
                max(
                    ask_price
                    -
                    highest_bid,
                    0.0,
                )
                /
                ask_price
                /
                0.20
            )

        elif bid_count == 0:

            weak_bid_component = (
                0.50
            )

        candidate_score = _clip01(
            0.35
            * missing_component
            +
            0.30
            * price_gap_component
            +
            0.20
            * market_activity_component
            +
            0.15
            * weak_bid_component
        )

        if missing_dmrv > 0:

            recommendation_type = (
                "RECOMMEND_DMRV_EVIDENCE_REMEDIATION"
            )

        elif (
            price_gap_ratio
            >= 0.10
            and
            bid_count
            <= 1
        ):

            recommendation_type = (
                "RECOMMEND_CREDIT_REPRICE"
            )

        elif (
            bid_count
            > 0
            or
            inquiry_count
            >= 3
        ):

            recommendation_type = (
                "RECOMMEND_BUYER_ENGAGEMENT_FOLLOWUP"
            )

        else:

            recommendation_type = (
                "RECOMMEND_MARKETPLACE_PRICE_REVIEW"
            )

        if missing_dmrv >= 2:

            risk_level = (
                "HIGH"
            )

        elif (
            missing_dmrv
            == 1
            or
            abs(
                price_gap_ratio
            )
            >= 0.12
        ):

            risk_level = (
                "MEDIUM"
            )

        else:

            risk_level = (
                "LOW"
            )

        support_record_count = (
            _safe_int(
                row[
                    "dmrv_attachment_records"
                ]
            )
            +
            _safe_int(
                row[
                    "dmrv_signature_records"
                ]
            )
            +
            _safe_int(
                row[
                    "dmrv_chain_of_custody_records"
                ]
            )
        )

        support_denominator = max(
            total_dmrv
            * 3,
            1,
        )

        support_ratio = _clip01(
            support_record_count
            /
            support_denominator
        )

        price_evidence_complete = (
            1.0
            if (
                reference_price
                > 0
                and
                ask_price
                > 0
            )
            else 0.0
        )

        # Maximum < 1.0.
        confidence = _clip01(
            0.40
            +
            0.18
            * price_evidence_complete
            +
            0.16
            * support_ratio
            +
            0.12
            * (
                1.0
                if total_dmrv
                > 0
                else 0.0
            )
            +
            0.10
            * market_activity_component
        )

        evidence = {
            "source_record_type":
                "CARBON_CREDIT_LISTING",

            "source_record_id":
                row[
                    "carbon_credit_listing_id"
                ],

            "elv_assessment_id":
                row[
                    "elv_assessment_id"
                ],

            "model_name":
                row[
                    "model_name"
                ],

            "city_name":
                row[
                    "city_name"
                ],

            "region_name":
                row[
                    "region_name"
                ],

            "credit_type":
                row[
                    "credit_type"
                ],

            "listing_at":
                row[
                    "listing_at"
                ],

            "seller_claimed_quantity_tco2e":
                round(
                    _safe_float(
                        row[
                            "seller_claimed_quantity_tco2e"
                        ]
                    ),
                    4,
                ),

            "market_reference_price_per_tco2e_inr":
                round(
                    reference_price,
                    2,
                ),

            "seller_ask_price_per_tco2e_inr":
                round(
                    ask_price,
                    2,
                ),

            "ask_vs_reference_gap_ratio":
                round(
                    price_gap_ratio,
                    6,
                ),

            "buyer_inquiry_count":
                inquiry_count,

            "buyer_bid_count":
                bid_count,

            "highest_bid_price_per_tco2e_inr":
                (
                    round(
                        highest_bid,
                        2,
                    )
                    if highest_bid
                    is not None
                    else None
                ),

            "reusable_parts_mass_kg":
                round(
                    _safe_float(
                        row[
                            "reusable_parts_mass_kg"
                        ]
                    ),
                    2,
                ),

            "recyclable_material_mass_kg":
                round(
                    _safe_float(
                        row[
                            "recyclable_material_mass_kg"
                        ]
                    ),
                    2,
                ),

            "dmrv_available_records":
                available_dmrv,

            "dmrv_missing_records":
                missing_dmrv,

            "dmrv_attachment_records":
                _safe_int(
                    row[
                        "dmrv_attachment_records"
                    ]
                ),

            "dmrv_signature_records":
                _safe_int(
                    row[
                        "dmrv_signature_records"
                    ]
                ),

            "dmrv_chain_of_custody_records":
                _safe_int(
                    row[
                        "dmrv_chain_of_custody_records"
                    ]
                ),
        }

        if missing_dmrv > 0:

            impact_metric = (
                "dmrv_evidence_sufficiency_input"
            )

        elif recommendation_type == (
            "RECOMMEND_CREDIT_REPRICE"
        ):

            impact_metric = (
                "credit_market_price_alignment"
            )

        else:

            impact_metric = (
                "credit_marketplace_engagement"
            )

        expected_impact = {
            "metric":
                impact_metric,

            "direction":
                "IMPROVE",

            "listing_quantity_tco2e":
                round(
                    _safe_float(
                        row[
                            "seller_claimed_quantity_tco2e"
                        ]
                    ),
                    4,
                ),

            "basis":
                (
                    "observed_dmrv_evidence_"
                    "and_marketplace_activity"
                ),
        }

        candidates.append(
            _candidate(
                domain=
                    DOMAIN_CIRCULARITY,

                target_entity_id=
                    row[
                        "carbon_credit_listing_id"
                    ],

                recommendation_type=
                    recommendation_type,

                evidence=
                    evidence,

                expected_impact=
                    expected_impact,

                confidence=
                    confidence,

                risk_level=
                    risk_level,

                candidate_score=
                    candidate_score,
            )
        )

    return pd.DataFrame(
        candidates
    )


# ============================================================
# DOMAIN QUOTAS
# ============================================================


def _build_domain_quotas(
    target_count: int,
) -> dict[str, int]:
    """
    Balanced synthetic development/test coverage.

    This is NOT a claim about real Mahindra recommendation
    frequency.
    """

    base = (
        target_count
        //
        len(
            SUPPORTED_DOMAINS
        )
    )

    remainder = (
        target_count
        %
        len(
            SUPPORTED_DOMAINS
        )
    )

    quotas = {
        domain:
            base
        for domain
        in SUPPORTED_DOMAINS
    }

    for domain in (
        SUPPORTED_DOMAINS[
            :remainder
        ]
    ):
        quotas[
            domain
        ] += 1

    return quotas


# ============================================================
# CANDIDATE SELECTION
# ============================================================


def _select_candidates(
    candidate_frames: list[pd.DataFrame],
    target_count: int,
) -> pd.DataFrame:
    """
    Deterministically select strongest candidates while maintaining
    broad domain coverage.
    """

    populated = [
        frame
        for frame
        in candidate_frames
        if not frame.empty
    ]

    if not populated:
        raise ValueError(
            "No recommendation candidates generated"
        )

    pool = pd.concat(
        populated,
        ignore_index=True,
    )

    if len(
        pool
    ) < target_count:
        raise ValueError(
            "Not enough recommendation candidates. "
            f"Required={target_count}, available={len(pool)}"
        )

    if (
        pool[
            [
                "domain",
                "target_entity_id",
            ]
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate domain/target candidates found"
        )

    pool = (
        pool
        .sort_values(
            [
                "domain",
                "_candidate_score",
                "_confidence",
                "target_entity_id",
            ],
            ascending=[
                True,
                False,
                False,
                True,
            ],
        )
        .reset_index(
            drop=True
        )
    )

    quotas = _build_domain_quotas(
        target_count
    )

    selected_indices: list[int] = []

    for domain in (
        SUPPORTED_DOMAINS
    ):

        domain_rows = pool[
            pool[
                "domain"
            ]
            ==
            domain
        ]

        quota = quotas[
            domain
        ]

        take_count = min(
            quota,
            len(
                domain_rows
            ),
        )

        selected_indices.extend(
            domain_rows.index[
                :take_count
            ].tolist()
        )

    selected_index_set = set(
        selected_indices
    )

    shortfall = (
        target_count
        -
        len(
            selected_indices
        )
    )

    if shortfall > 0:

        remaining = pool[
            ~pool.index.isin(
                selected_index_set
            )
        ].copy()

        remaining = remaining.sort_values(
            [
                "_candidate_score",
                "_confidence",
                "domain",
                "target_entity_id",
            ],
            ascending=[
                False,
                False,
                True,
                True,
            ],
        )

        selected_indices.extend(
            remaining.index[
                :shortfall
            ].tolist()
        )

    selected = (
        pool.loc[
            selected_indices
        ]
        .copy()
        .sort_values(
            [
                "domain",
                "_candidate_score",
                "_confidence",
                "target_entity_id",
            ],
            ascending=[
                True,
                False,
                False,
                True,
            ],
        )
        .reset_index(
            drop=True
        )
    )

    if len(
        selected
    ) != target_count:
        raise ValueError(
            "Recommendation selection failed exact target count"
        )

    return selected


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_recommendations(
    allocations: pd.DataFrame,
    cross_sell_events: pd.DataFrame,
    collection_cases: pd.DataFrame,
    shipments: pd.DataFrame,
    credit_listings: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate evidence-backed PROPOSED governance recommendations.
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    _validate_inputs(
        allocations=
            allocations,

        cross_sell_events=
            cross_sell_events,

        collection_cases=
            collection_cases,

        shipments=
            shipments,

        credit_listings=
            credit_listings,
    )

    (
        generation_start,
        generation_end,
        _,
    ) = _get_generation_window(
        generation
    )

    target_count = (
        _get_recommendation_target_count(
            generation
        )
    )

    snapshot_at = (
        generation_end
        -
        pd.Timedelta(
            minutes=1
        )
    )

    if snapshot_at <= generation_start:
        raise ValueError(
            "Generation window too small for governance snapshot"
        )

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

    # Deterministic evidence-derived candidate generation.
    # No recommendation RNG is intentionally used.

    auto_candidates = (
        _build_auto_candidates(
            allocations=
                allocations,

            snapshot_at=
                snapshot_at,
        )
    )

    finance_candidates = (
        _build_finance_candidates(
            cross_sell_events=
                cross_sell_events,

            snapshot_at=
                snapshot_at,
        )
    )

    collections_candidates = (
        _build_collections_candidates(
            collection_cases=
                collection_cases,

            snapshot_at=
                snapshot_at,
        )
    )

    logistics_candidates = (
        _build_logistics_candidates(
            shipments=
                shipments,

            snapshot_at=
                snapshot_at,
        )
    )

    circularity_candidates = (
        _build_circularity_candidates(
            credit_listings=
                credit_listings,

            snapshot_at=
                snapshot_at,
        )
    )

    selected = _select_candidates(
        candidate_frames=[
            auto_candidates,
            finance_candidates,
            collections_candidates,
            logistics_candidates,
            circularity_candidates,
        ],

        target_count=
            target_count,
    )

    rows: list[
        dict[str, Any]
    ] = []

    for sequence, candidate in enumerate(
        selected.to_dict(
            orient="records"
        ),
        start=1,
    ):

        rows.append(
            {
                "recommendation_id":
                    generate_id(
                        "REC_SYN",
                        sequence,
                        width=7,
                    ),

                "domain":
                    candidate[
                        "domain"
                    ],

                "use_case":
                    candidate[
                        "use_case"
                    ],

                "target_entity_type":
                    candidate[
                        "target_entity_type"
                    ],

                "target_entity_id":
                    candidate[
                        "target_entity_id"
                    ],

                "recommendation_type":
                    candidate[
                        "recommendation_type"
                    ],

                "generated_at":
                    snapshot_at,

                "evidence_json":
                    _canonical_json(
                        candidate[
                            "_evidence"
                        ]
                    ),

                "expected_impact":
                    _canonical_json(
                        candidate[
                            "_expected_impact"
                        ]
                    ),

                "confidence":
                    round(
                        float(
                            candidate[
                                "_confidence"
                            ]
                        ),
                        6,
                    ),

                "risk_level":
                    candidate[
                        "_risk_level"
                    ],

                "status":
                    "PROPOSED",

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    recommendations = pd.DataFrame(
        rows
    )

    validate_recommendations(
        recommendations=
            recommendations,

        allocations=
            allocations,

        cross_sell_events=
            cross_sell_events,

        collection_cases=
            collection_cases,

        shipments=
            shipments,

        credit_listings=
            credit_listings,

        generation_start=
            generation_start,

        generation_end=
            generation_end,

        expected_count=
            target_count,

        expected_data_origin=
            data_origin,

        expected_generator_version=
            generator_version,
    )

    return recommendations


# ============================================================
# PAYLOAD LEAKAGE SCAN
# ============================================================


def _scan_payload_keys(
    value: Any,
    path: str = "",
) -> list[str]:
    """
    Recursively detect forbidden hidden truth/runtime payload keys.
    """

    violations: list[
        str
    ] = []

    if isinstance(
        value,
        Mapping,
    ):

        for key, item in (
            value.items()
        ):

            key_text = str(
                key
            ).lower()

            current_path = (
                f"{path}.{key}"
                if path
                else str(
                    key
                )
            )

            for fragment in (
                FORBIDDEN_PAYLOAD_KEY_FRAGMENTS
            ):

                if fragment in key_text:
                    violations.append(
                        current_path
                    )

            violations.extend(
                _scan_payload_keys(
                    item,
                    current_path,
                )
            )

    elif isinstance(
        value,
        list,
    ):

        for index, item in enumerate(
            value
        ):

            violations.extend(
                _scan_payload_keys(
                    item,
                    f"{path}[{index}]",
                )
            )

    return violations


# ============================================================
# VALIDATION
# ============================================================


def validate_recommendations(
    recommendations: pd.DataFrame,
    allocations: pd.DataFrame,
    cross_sell_events: pd.DataFrame,
    collection_cases: pd.DataFrame,
    shipments: pd.DataFrame,
    credit_listings: pd.DataFrame,
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
    expected_count: int,
    expected_data_origin: str,
    expected_generator_version: str,
) -> None:
    """
    Validate recommendation integrity and governance boundaries.
    """

    if recommendations.empty:
        raise ValueError(
            "No governance recommendations generated"
        )

    required_columns = {
        "recommendation_id",

        "domain",
        "use_case",

        "target_entity_type",
        "target_entity_id",

        "recommendation_type",

        "generated_at",

        "evidence_json",
        "expected_impact",

        "confidence",
        "risk_level",

        "status",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        -
        set(
            recommendations.columns
        )
    )

    if missing:
        raise ValueError(
            "Recommendations missing columns: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    # ========================================================
    # COUNT
    # ========================================================

    if len(
        recommendations
    ) != int(
        expected_count
    ):
        raise ValueError(
            "Recommendation count does not match configured target"
        )

    # ========================================================
    # PRIMARY KEY
    # ========================================================

    if (
        recommendations[
            "recommendation_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "recommendation_id cannot be null"
        )

    if (
        recommendations[
            "recommendation_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate recommendation_id values found"
        )

    # ========================================================
    # LOGICAL DUPLICATES
    # ========================================================

    if (
        recommendations[
            [
                "domain",
                "target_entity_type",
                "target_entity_id",
            ]
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate recommendation target found"
        )

    # ========================================================
    # DOMAIN COVERAGE
    # ========================================================

    invalid_domains = (
        set(
            recommendations[
                "domain"
            ]
        )
        -
        set(
            SUPPORTED_DOMAINS
        )
    )

    if invalid_domains:
        raise ValueError(
            "Invalid recommendation domains: "
            +
            ", ".join(
                sorted(
                    invalid_domains
                )
            )
        )

    missing_domains = (
        set(
            SUPPORTED_DOMAINS
        )
        -
        set(
            recommendations[
                "domain"
            ]
        )
    )

    if missing_domains:
        raise ValueError(
            "Missing governance recommendation domains: "
            +
            ", ".join(
                sorted(
                    missing_domains
                )
            )
        )

    # ========================================================
    # STATUS
    # ========================================================

    invalid_statuses = (
        set(
            recommendations[
                "status"
            ]
        )
        -
        VALID_RECOMMENDATION_STATUSES
    )

    if invalid_statuses:
        raise ValueError(
            "recommendations.py may generate PROPOSED records only"
        )

    # ========================================================
    # RISK
    # ========================================================

    invalid_risks = (
        set(
            recommendations[
                "risk_level"
            ]
        )
        -
        VALID_RISK_LEVELS
    )

    if invalid_risks:
        raise ValueError(
            "Invalid recommendation risk levels found"
        )

    # ========================================================
    # CONFIDENCE
    # ========================================================

    confidence = pd.to_numeric(
        recommendations[
            "confidence"
        ],
        errors="raise",
    )

    if confidence.isna().any():
        raise ValueError(
            "Recommendation confidence cannot be null"
        )

    if (
        (
            confidence
            < 0
        )
        |
        (
            confidence
            > 1
        )
    ).any():
        raise ValueError(
            "Recommendation confidence must lie in [0,1]"
        )

    # ========================================================
    # TIMESTAMPS
    # ========================================================

    generated_at = pd.to_datetime(
        recommendations[
            "generated_at"
        ],
        errors="raise",
        utc=True,
    )

    start_utc = (
        generation_start
        .tz_convert(
            "UTC"
        )
    )

    end_utc = (
        generation_end
        .tz_convert(
            "UTC"
        )
    )

    if (
        generated_at
        < start_utc
    ).any():
        raise ValueError(
            "Recommendation generated before synthetic window"
        )

    if (
        generated_at
        >= end_utc
    ).any():
        raise ValueError(
            "Recommendation generated outside synthetic window"
        )

    # ========================================================
    # UPSTREAM FK SETS
    # ========================================================

    source_ids = {
        DOMAIN_AUTO:
            set(
                allocations[
                    "allocation_id"
                ]
                .astype(
                    str
                )
            ),

        DOMAIN_FINANCE:
            set(
                cross_sell_events[
                    "cross_sell_event_id"
                ]
                .astype(
                    str
                )
            ),

        DOMAIN_COLLECTIONS:
            set(
                collection_cases[
                    "collection_case_id"
                ]
                .astype(
                    str
                )
            ),

        DOMAIN_LOGISTICS:
            set(
                shipments[
                    "shipment_id"
                ]
                .astype(
                    str
                )
            ),

        DOMAIN_CIRCULARITY:
            set(
                credit_listings[
                    "carbon_credit_listing_id"
                ]
                .astype(
                    str
                )
            ),
    }

    for domain in (
        SUPPORTED_DOMAINS
    ):

        domain_rows = recommendations[
            recommendations[
                "domain"
            ]
            ==
            domain
        ]

        expected_type = (
            DOMAIN_TARGET_ENTITY_TYPES[
                domain
            ]
        )

        if not (
            domain_rows[
                "target_entity_type"
            ]
            ==
            expected_type
        ).all():
            raise ValueError(
                f"{domain}: incorrect target_entity_type"
            )

        invalid_ids = (
            set(
                domain_rows[
                    "target_entity_id"
                ]
                .astype(
                    str
                )
            )
            -
            source_ids[
                domain
            ]
        )

        if invalid_ids:
            raise ValueError(
                f"{domain}: recommendation references "
                "invalid upstream entity IDs"
            )

    # ========================================================
    # JSON / LINEAGE / LEAKAGE
    # ========================================================

    for row in recommendations.itertuples(
        index=False
    ):

        try:

            evidence = json.loads(
                row.evidence_json
            )

        except json.JSONDecodeError as exc:

            raise ValueError(
                f"{row.recommendation_id}: invalid evidence_json"
            ) from exc

        try:

            expected_impact = json.loads(
                row.expected_impact
            )

        except json.JSONDecodeError as exc:

            raise ValueError(
                f"{row.recommendation_id}: invalid expected_impact"
            ) from exc

        if not isinstance(
            evidence,
            dict,
        ):
            raise ValueError(
                f"{row.recommendation_id}: evidence_json must be object"
            )

        if not isinstance(
            expected_impact,
            dict,
        ):
            raise ValueError(
                f"{row.recommendation_id}: expected_impact must be object"
            )

        if str(
            evidence.get(
                "source_record_id"
            )
        ) != str(
            row.target_entity_id
        ):
            raise ValueError(
                f"{row.recommendation_id}: evidence lineage mismatch"
            )

        payload_violations = (
            _scan_payload_keys(
                evidence,
                "evidence_json",
            )
            +
            _scan_payload_keys(
                expected_impact,
                "expected_impact",
            )
        )

        if payload_violations:
            raise ValueError(
                f"{row.recommendation_id}: "
                "hidden truth/runtime payload leakage: "
                +
                ", ".join(
                    payload_violations
                )
            )

    # ========================================================
    # PROVENANCE
    # ========================================================

    if not (
        recommendations[
            "data_origin"
        ]
        ==
        expected_data_origin
    ).all():
        raise ValueError(
            "Recommendation data_origin mismatch"
        )

    if not (
        recommendations[
            "generator_version"
        ]
        ==
        expected_generator_version
    ).all():
        raise ValueError(
            "Recommendation generator_version mismatch"
        )

    # ========================================================
    # COLUMN LEAKAGE
    # ========================================================

    leakage_columns = [
        column

        for column
        in recommendations.columns

        if any(
            fragment
            in column.lower()

            for fragment
            in FORBIDDEN_OUTPUT_COLUMN_FRAGMENTS
        )
    ]

    if leakage_columns:
        raise ValueError(
            "Hidden truth/runtime output leakage found: "
            +
            ", ".join(
                leakage_columns
            )
        )


# ============================================================
# PUBLIC ALIAS
# ============================================================


def generate_recommendation_master(
    allocations: pd.DataFrame,
    cross_sell_events: pd.DataFrame,
    collection_cases: pd.DataFrame,
    shipments: pd.DataFrame,
    credit_listings: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Alias for later generate_all.py orchestration.
    """

    return generate_recommendations(
        allocations=
            allocations,

        cross_sell_events=
            cross_sell_events,

        collection_cases=
            collection_cases,

        shipments=
            shipments,

        credit_listings=
            credit_listings,

        generation=
            generation,
    )


# ============================================================
# LOCAL VALIDATION FIXTURE
# ============================================================


def _build_local_validation_fixture(
    generation: Mapping[str, Any],
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Build deterministic schema-compatible smoke-test evidence.

    This fixture is not a substitute for the real integration test.
    """

    (
        generation_start,
        generation_end,
        _,
    ) = _get_generation_window(
        generation
    )

    base_time = (
        generation_start
        +
        pd.Timedelta(
            days=30
        )
    )

    n = 500

    # ========================================================
    # AUTO FIXTURE - aligned with real allocation schema
    # ========================================================

    allocation_rows: list[
        dict[str, Any]
    ] = []

    demand_levels = [
        0.55,
        0.691844,
        0.725887,
        0.95,
    ]

    capacities = [
        280,
        428,
        450,
        618,
        650,
    ]

    for i in range(
        1,
        n + 1,
    ):

        demand = float(
            demand_levels[
                i
                %
                len(
                    demand_levels
                )
            ]
        )

        capacity = int(
            capacities[
                i
                %
                len(
                    capacities
                )
            ]
        )

        wait_hours = float(
            0.5
            +
            (
                i
                * 1.73
            )
            %
            35.5
        )

        inventory_before = float(
            3
            +
            (
                i
                % 28
            )
        )

        requested_units = (
            1
        )

        allocated_units = (
            1
        )

        inventory_after = max(
            0.0,
            inventory_before
            -
            allocated_units,
        )

        batch_inventory_before = float(
            20
            +
            (
                i
                % 80
            )
        )

        batch_inventory_after = max(
            0.0,
            batch_inventory_before
            -
            allocated_units,
        )

        priority_score = _clip01(
            0.46
            +
            0.30
            * (
                (
                    demand
                    -
                    0.55
                )
                /
                0.40
            )
            +
            0.15
            * (
                wait_hours
                /
                36.0
            )
        )

        if priority_score >= 0.75:

            priority = (
                "HIGH"
            )

        elif priority_score >= 0.60:

            priority = (
                "MEDIUM"
            )

        else:

            priority = (
                "NORMAL"
            )

        allocation_rows.append(
            {
                "allocation_id":
                    f"ALLOCATION_FIX_{i:06d}",

                "booking_id":
                    f"BOOKING_FIX_{i:06d}",

                "dealer_id":
                    f"DEALER_FIX_{(i % 30) + 1:03d}",

                "dealer_name":
                    f"Dealer {(i % 30) + 1}",

                "region_id":
                    f"REGION_FIX_{(i % 4) + 1:02d}",

                "region_name":
                    (
                        "West",
                        "North",
                        "South",
                        "East",
                    )[
                        i % 4
                    ],

                "city_id":
                    f"CITY_FIX_{(i % 20) + 1:03d}",

                "city_name":
                    f"City {(i % 20) + 1}",

                "vehicle_model_id":
                    f"VEH_FIX_{(i % 5) + 1:02d}",

                "vehicle_model_name":
                    f"Vehicle {(i % 5) + 1}",

                "allocation_date":
                    base_time
                    +
                    pd.Timedelta(
                        hours=i
                    ),

                "requested_units":
                    requested_units,

                "allocated_units":
                    allocated_units,

                # Mirror the current real generator:
                "waiting_list":
                    0,

                "dealer_capacity":
                    capacity,

                "dealer_capacity_source":
                    "DEALER_MASTER",

                "regional_demand_index":
                    demand,

                "allocation_priority_score":
                    round(
                        priority_score,
                        6,
                    ),

                "allocation_priority":
                    priority,

                "inventory_before":
                    inventory_before,

                "inventory_after":
                    inventory_after,

                "production_batch_inventory_before":
                    batch_inventory_before,

                "production_batch_inventory_after":
                    batch_inventory_after,

                "allocation_wait_hours":
                    round(
                        wait_hours,
                        3,
                    ),

                "allocation_status":
                    "ALLOCATED",
            }
        )

    allocations = pd.DataFrame(
        allocation_rows
    )

    # ========================================================
    # FINANCE FIXTURE
    # ========================================================

    finance_rows: list[
        dict[str, Any]
    ] = []

    for i in range(
        1,
        n + 1,
    ):

        if i % 3 == 0:

            response = (
                "INTERESTED"
            )

        elif i % 3 == 1:

            response = (
                "NO_RESPONSE"
            )

        else:

            response = (
                "DECLINED"
            )

        offered_at = (
            base_time
            +
            pd.Timedelta(
                hours=i
            )
        )

        finance_rows.append(
            {
                "cross_sell_event_id":
                    f"FINXSELL_FIX_{i:06d}",

                "finance_customer_id":
                    f"FINCUST_FIX_{i:06d}",

                "source_product_code":
                    "AUTO_LOAN_NEW",

                "offered_product_code":
                    "SME_LOAN",

                "offered_product_name":
                    "SME Business Loan",

                "offered_at":
                    offered_at,

                "offer_channel":
                    (
                        "WHATSAPP"
                        if i % 2 == 0
                        else "CALL"
                    ),

                "offer_amount_inr":
                    float(
                        100000
                        +
                        (
                            i % 25
                        )
                        * 25000
                    ),

                "offer_interest_rate_pct":
                    11.0
                    +
                    (
                        i % 10
                    )
                    * 0.2,

                "offer_tenure_months":
                    12
                    +
                    (
                        i % 5
                    )
                    * 12,

                "estimated_offer_emi_inr":
                    5000.0
                    +
                    (
                        i % 20
                    )
                    * 500.0,

                "customer_response":
                    response,

                "responded_at":
                    (
                        offered_at
                        +
                        pd.Timedelta(
                            hours=12
                        )
                        if response
                        != "NO_RESPONSE"
                        else pd.NaT
                    ),
            }
        )

    cross_sell_events = pd.DataFrame(
        finance_rows
    )

    # ========================================================
    # COLLECTIONS FIXTURE
    # ========================================================

    collection_rows: list[
        dict[str, Any]
    ] = []

    for i in range(
        1,
        n + 1,
    ):

        created_at = (
            base_time
            +
            pd.Timedelta(
                hours=i
            )
        )

        open_case = (
            i % 4
            != 0
        )

        current_dpd = (
            (
                15
                +
                (
                    i
                    * 7
                )
                % 420
            )
            if open_case
            else 0
        )

        arrears = (
            float(
                5000
                +
                (
                    i
                    * 1700
                )
                % 90000
            )
            if open_case
            else 0.0
        )

        peak_dpd = max(
            current_dpd,
            30
            +
            (
                i
                * 9
            )
            % 500,
        )

        collection_rows.append(
            {
                "collection_case_id":
                    f"COLCASE_FIX_{i:06d}",

                "loan_account_id":
                    f"FINLOAN_FIX_{i:06d}",

                "finance_customer_id":
                    f"FINCUST_FIX_{i:06d}",

                "product_name":
                    "New Vehicle Loan",

                "case_created_at":
                    created_at,

                "observed_dpd_at_trigger_event":
                    max(
                        15,
                        current_dpd,
                    ),

                "dpd_at_case_creation":
                    15,

                "arrears_at_trigger_event_inr":
                    max(
                        2500.0,
                        arrears
                        * 0.60,
                    ),

                "priority_at_creation":
                    (
                        "HIGH"
                        if current_dpd
                        >= 180
                        else "LOW"
                    ),

                "peak_observed_dpd":
                    peak_dpd,

                "case_status":
                    (
                        "OPEN"
                        if open_case
                        else "RESOLVED"
                    ),

                "current_dpd":
                    current_dpd,

                "current_arrears_inr":
                    arrears,

                "resolved_at":
                    (
                        pd.NaT
                        if open_case
                        else
                        created_at
                        +
                        pd.Timedelta(
                            days=30
                        )
                    ),
            }
        )

    collection_cases = pd.DataFrame(
        collection_rows
    )

    # ========================================================
    # LOGISTICS FIXTURE
    # ========================================================

    shipment_rows: list[
        dict[str, Any]
    ] = []

    for i in range(
        1,
        n + 1,
    ):

        dispatch = (
            base_time
            +
            pd.Timedelta(
                hours=i
            )
        )

        expected = (
            dispatch
            +
            pd.Timedelta(
                hours=24
            )
        )

        delay_minutes = float(
            (
                i
                * 37
            )
            % 720
        )

        actual = (
            expected
            +
            pd.Timedelta(
                minutes=
                    delay_minutes
            )
        )

        shipment_rows.append(
            {
                "shipment_id":
                    f"SHIP_FIX_{i:06d}",

                "route_id":
                    f"ROUTE_FIX_{(i % 15) + 1:03d}",

                "origin_city_name":
                    f"Origin {(i % 8) + 1}",

                "destination_city_name":
                    f"Destination {(i % 8) + 1}",

                "vehicle_id":
                    f"LOGVEH_FIX_{(i % 300) + 1:04d}",

                "priority":
                    (
                        "CRITICAL"
                        if i % 11 == 0
                        else (
                            "HIGH"
                            if i % 4 == 0
                            else "NORMAL"
                        )
                    ),

                "units":
                    1
                    +
                    (
                        i % 12
                    ),

                "dispatch_time":
                    dispatch,

                "expected_arrival":
                    expected,

                "actual_arrival":
                    actual,

                "delay_minutes":
                    delay_minutes,

                "sla_breach":
                    delay_minutes
                    >= 360.0,

                "weather_disruption":
                    i % 9 == 0,

                "vehicle_breakdown":
                    i % 17 == 0,

                "warehouse_delay":
                    i % 13 == 0,

                "port_delay":
                    i % 19 == 0,

                "customs_delay":
                    i % 23 == 0,
            }
        )

    shipments = pd.DataFrame(
        shipment_rows
    )

    # ========================================================
    # CIRCULARITY FIXTURE
    # ========================================================

    credit_rows: list[
        dict[str, Any]
    ] = []

    for i in range(
        1,
        n + 1,
    ):

        reference_price = (
            1700.0
            +
            (
                i % 20
            )
            * 25.0
        )

        ask_multiplier = (
            0.92
            +
            (
                i % 15
            )
            * 0.02
        )

        ask_price = (
            reference_price
            *
            ask_multiplier
        )

        missing_dmrv = (
            2
            if i % 29 == 0
            else (
                1
                if i % 7 == 0
                else 0
            )
        )

        available_dmrv = (
            4
            -
            missing_dmrv
        )

        inquiry_count = (
            i % 7
        )

        bid_count = min(
            inquiry_count,
            i % 4,
        )

        credit_rows.append(
            {
                "carbon_credit_listing_id":
                    f"CCLIST_FIX_{i:06d}",

                "elv_assessment_id":
                    f"ELV_FIX_{i:06d}",

                "model_name":
                    f"Vehicle {(i % 5) + 1}",

                "city_name":
                    f"City {(i % 20) + 1}",

                "region_name":
                    (
                        "West",
                        "North",
                        "South",
                        "East",
                    )[
                        i % 4
                    ],

                "credit_type":
                    (
                        "REUSE_AVOIDANCE"
                        if i % 3 == 0
                        else (
                            "RECYCLING_AVOIDANCE"
                            if i % 3 == 1
                            else
                            "MIXED_CIRCULARITY"
                        )
                    ),

                "listing_at":
                    base_time
                    +
                    pd.Timedelta(
                        hours=i
                    ),

                "seller_claimed_quantity_tco2e":
                    0.8
                    +
                    (
                        i % 10
                    )
                    * 0.07,

                "market_reference_price_per_tco2e_inr":
                    reference_price,

                "seller_ask_price_per_tco2e_inr":
                    ask_price,

                "buyer_inquiry_count":
                    inquiry_count,

                "buyer_bid_count":
                    bid_count,

                "highest_bid_price_per_tco2e_inr":
                    (
                        ask_price
                        * 0.95
                        if bid_count
                        > 0
                        else np.nan
                    ),

                "reusable_parts_mass_kg":
                    300.0
                    +
                    (
                        i % 20
                    )
                    * 20.0,

                "recyclable_material_mass_kg":
                    650.0
                    +
                    (
                        i % 20
                    )
                    * 25.0,

                "dmrv_available_records":
                    available_dmrv,

                "dmrv_missing_records":
                    missing_dmrv,

                "dmrv_attachment_records":
                    max(
                        0,
                        available_dmrv
                        -
                        (
                            1
                            if i % 8 == 0
                            else 0
                        ),
                    ),

                "dmrv_signature_records":
                    max(
                        0,
                        available_dmrv
                        -
                        (
                            1
                            if i % 6 == 0
                            else 0
                        ),
                    ),

                "dmrv_chain_of_custody_records":
                    max(
                        0,
                        available_dmrv
                        -
                        (
                            1
                            if i % 9 == 0
                            else 0
                        ),
                    ),
            }
        )

    credit_listings = pd.DataFrame(
        credit_rows
    )

    # ========================================================
    # FIXTURE WINDOW PROTECTION
    # ========================================================

    for dataframe, columns in (
        (
            allocations,
            (
                "allocation_date",
            ),
        ),
        (
            cross_sell_events,
            (
                "offered_at",
                "responded_at",
            ),
        ),
        (
            collection_cases,
            (
                "case_created_at",
                "resolved_at",
            ),
        ),
        (
            shipments,
            (
                "dispatch_time",
                "expected_arrival",
                "actual_arrival",
            ),
        ),
        (
            credit_listings,
            (
                "listing_at",
            ),
        ),
    ):

        for column in columns:

            values = pd.to_datetime(
                dataframe[
                    column
                ],
                errors="coerce",
                utc=True,
            )

            end_utc = (
                generation_end
                .tz_convert(
                    "UTC"
                )
            )

            too_late = (
                values
                >= end_utc
            )

            dataframe.loc[
                too_late,
                column,
            ] = (
                generation_end
                -
                pd.Timedelta(
                    hours=2
                )
            )

    return (
        allocations,
        cross_sell_events,
        collection_cases,
        shipments,
        credit_listings,
    )


# ============================================================
# LOCAL TEST
# ============================================================


if __name__ == "__main__":

    generation_config = (
        load_generation_config()
    )

    (
        allocations_df,
        cross_sell_events_df,
        collection_cases_df,
        shipments_df,
        credit_listings_df,
    ) = _build_local_validation_fixture(
        generation_config
    )

    print(
        "\n=== GOVERNANCE RECOMMENDATION CONFIG ===\n"
    )

    print(
        "Configured recommendations:",
        _get_recommendation_target_count(
            generation_config
        ),
    )

    print(
        "\n=== LOCAL EVIDENCE FIXTURE ===\n"
    )

    print(
        "Allocation evidence:",
        len(
            allocations_df
        ),
    )

    print(
        "Finance cross-sell evidence:",
        len(
            cross_sell_events_df
        ),
    )

    print(
        "Collections evidence:",
        len(
            collection_cases_df
        ),
    )

    print(
        "Shipment evidence:",
        len(
            shipments_df
        ),
    )

    print(
        "Circularity credit evidence:",
        len(
            credit_listings_df
        ),
    )

    recommendations_df = (
        generate_recommendation_master(
            allocations=
                allocations_df,

            cross_sell_events=
                cross_sell_events_df,

            collection_cases=
                collection_cases_df,

            shipments=
                shipments_df,

            credit_listings=
                credit_listings_df,

            generation=
                generation_config,
        )
    )

    # ========================================================
    # DETERMINISM
    # ========================================================

    recommendations_repeat_df = (
        generate_recommendation_master(
            allocations=
                allocations_df,

            cross_sell_events=
                cross_sell_events_df,

            collection_cases=
                collection_cases_df,

            shipments=
                shipments_df,

            credit_listings=
                credit_listings_df,

            generation=
                generation_config,
        )
    )

    pd.testing.assert_frame_equal(
        recommendations_df,
        recommendations_repeat_df,
        check_dtype=True,
        check_exact=True,
    )

    # ========================================================
    # SAMPLE
    # ========================================================

    print(
        "\n=== RECOMMENDATION SAMPLE ===\n"
    )

    display_columns = [
        "recommendation_id",
        "domain",
        "use_case",
        "target_entity_type",
        "target_entity_id",
        "recommendation_type",
        "confidence",
        "risk_level",
        "status",
    ]

    print(
        recommendations_df[
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
    # DOMAIN SUMMARY
    # ========================================================

    print(
        "\n=== RECOMMENDATIONS BY DOMAIN ===\n"
    )

    domain_summary = (
        recommendations_df
        .groupby(
            "domain",
            as_index=False,
        )
        .agg(
            recommendations=(
                "recommendation_id",
                "count",
            ),

            average_confidence=(
                "confidence",
                "mean",
            ),

            minimum_confidence=(
                "confidence",
                "min",
            ),

            maximum_confidence=(
                "confidence",
                "max",
            ),
        )
        .sort_values(
            "domain"
        )
    )

    for column in (
        "average_confidence",
        "minimum_confidence",
        "maximum_confidence",
    ):

        domain_summary[
            column
        ] = (
            domain_summary[
                column
            ]
            .round(
                4
            )
        )

    print(
        domain_summary.to_string(
            index=False
        )
    )

    # ========================================================
    # TYPE MIX
    # ========================================================

    print(
        "\n=== RECOMMENDATION TYPE MIX ===\n"
    )

    print(
        recommendations_df
        .groupby(
            [
                "domain",
                "recommendation_type",
            ],
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "recommendations"
            }
        )
        .sort_values(
            [
                "domain",
                "recommendations",
                "recommendation_type",
            ],
            ascending=[
                True,
                False,
                True,
            ],
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # RISK
    # ========================================================

    print(
        "\n=== RISK MIX ===\n"
    )

    print(
        recommendations_df
        .groupby(
            [
                "domain",
                "risk_level",
            ],
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "recommendations"
            }
        )
        .sort_values(
            [
                "domain",
                "risk_level",
            ]
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # CONFIDENCE
    # ========================================================

    print(
        "\n=== CONFIDENCE SUMMARY ===\n"
    )

    print(
        recommendations_df[
            "confidence"
        ]
        .describe()
        .round(
            4
        )
        .to_string()
    )

    confidence_at_one = int(
        (
            recommendations_df[
                "confidence"
            ]
            >=
            0.999999
        )
        .sum()
    )

    print(
        "\nRecommendations at confidence 1.0:",
        confidence_at_one,
    )

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    leakage_columns = [
        column

        for column
        in recommendations_df.columns

        if any(
            fragment
            in column.lower()

            for fragment
            in FORBIDDEN_OUTPUT_COLUMN_FRAGMENTS
        )
    ]

    print(
        "\n=== GOVERNANCE RECOMMENDATION VALIDATION ===\n"
    )

    print(
        "Rows:",
        len(
            recommendations_df
        ),
    )

    print(
        "Unique recommendation IDs:",
        recommendations_df[
            "recommendation_id"
        ]
        .nunique(),
    )

    print(
        "Domains represented:",
        recommendations_df[
            "domain"
        ]
        .nunique(),
    )

    print(
        "Duplicate recommendation IDs:",
        int(
            recommendations_df[
                "recommendation_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Duplicate domain/target entities:",
        int(
            recommendations_df[
                [
                    "domain",
                    "target_entity_type",
                    "target_entity_id",
                ]
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Non-PROPOSED recommendations:",
        int(
            (
                recommendations_df[
                    "status"
                ]
                !=
                "PROPOSED"
            )
            .sum()
        ),
    )

    print(
        "Confidence outside [0,1]:",
        int(
            (
                (
                    recommendations_df[
                        "confidence"
                    ]
                    <
                    0
                )
                |
                (
                    recommendations_df[
                        "confidence"
                    ]
                    >
                    1
                )
            )
            .sum()
        ),
    )

    print(
        "Hidden truth/runtime leakage:",
        leakage_columns,
    )

    print(
        "Deterministic rerun:",
        "PASS",
    )

    print(
        "\nGenerated "
        f"{len(recommendations_df)} "
        "synthetic evidence-derived governance "
        "recommendations successfully."
    )