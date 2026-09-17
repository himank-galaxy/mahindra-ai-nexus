"""
Mobility Business Time-Series Generator
for Mahindra AI Nexus.

Purpose
-------
Convert existing Auto transactional records into an ordered
regional business time series.

No dashboard KPI is randomly generated here.

Operational flow:

    Leads
        ↓
    Follow-ups scheduled
        ↓
    Follow-ups completed
        ↓
    Customer responses
        ↓
    Test Drives
        ↓
    Bookings
        ↓
    Finance Applications
        ↓
    Cancellations
        ↓
    Allocations
        ↓
    Deliveries
        ↓
    Service
        ↓
    Warranty

Output
------
One rolling 12-hour business observation per minute for each region.

CRITICAL RULE
-------------

Each region remains an independent time-series context.

Never concatenate:

    East → North → South → West

and treat that as one continuous PCMCI history.


GROUND-TRUTH RULE
-----------------

Runtime mobility data MUST NOT contain:

    latent_purchase_intent
    booking_probability
    cancellation_probability
    claim_probability
    root_cause_domain

    scenario_name
    scenario_event_id
    is_anomaly
    anomaly_type

    expected_warning
    true causal edges
    causal coefficients

Ground truth remains separately stored under:

    data/ground_truth/


This generator returns a DataFrame only.

It DOES NOT save CSV files.
"""

from __future__ import annotations

import importlib
import inspect

from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from data.generators.common.helpers import (
    load_generation_config,
)


# ============================================================
# TIME WINDOW
# ============================================================

BUSINESS_WINDOW_HOURS = 12


# ============================================================
# PRIMARY PCMCI VARIABLES
# ============================================================

MOBILITY_PCMCI_PRIMARY_VARIABLES: tuple[str, ...] = (
    "lead_count",
    "followup_completed_count",
    "test_drive_completed_count",
    "booking_count",
    "finance_approved_count",
    "cancellation_count",
    "allocated_vehicle_count",
    "delivered_vehicle_count",
    "delayed_delivery_count",
)


# ============================================================
# AUXILIARY OBSERVABLE BUSINESS VARIABLES
# ============================================================

MOBILITY_AUXILIARY_VARIABLES: tuple[str, ...] = (
    "avg_lead_engagement_score",

    "followup_count",
    "customer_response_count",
    "avg_followup_response_minutes",

    "test_drive_requested_count",
    "test_drive_no_show_count",

    "booking_value_inr",

    "finance_application_count",
    "finance_rejected_count",
    "finance_manual_review_count",
    "avg_finance_approval_tat_hours",

    "waitlisted_booking_count",
    "avg_allocation_wait_hours",

    "avg_delivery_delay_days",

    "service_event_count",
    "unscheduled_repair_count",

    "warranty_claim_count",
    "warranty_approved_count",
    "warranty_claim_amount_inr",
)


# ============================================================
# OUTPUT METRIC TYPES
# ============================================================

COUNT_COLUMNS: tuple[str, ...] = (
    "lead_count",

    "followup_count",
    "followup_completed_count",
    "customer_response_count",

    "test_drive_requested_count",
    "test_drive_completed_count",
    "test_drive_no_show_count",

    "booking_count",

    "finance_application_count",
    "finance_approved_count",
    "finance_rejected_count",
    "finance_manual_review_count",

    "cancellation_count",

    "allocated_vehicle_count",
    "waitlisted_booking_count",

    "delivered_vehicle_count",
    "delayed_delivery_count",

    "service_event_count",
    "unscheduled_repair_count",

    "warranty_claim_count",
    "warranty_approved_count",
)


SUM_COLUMNS: tuple[str, ...] = (
    "booking_value_inr",
    "warranty_claim_amount_inr",
)


MEAN_COLUMNS: tuple[str, ...] = (
    "avg_lead_engagement_score",
    "avg_followup_response_minutes",
    "avg_finance_approval_tat_hours",
    "avg_allocation_wait_hours",
    "avg_delivery_delay_days",
)


ALL_METRIC_COLUMNS: tuple[str, ...] = (
    COUNT_COLUMNS
    +
    SUM_COLUMNS
    +
    MEAN_COLUMNS
)


# ============================================================
# FORBIDDEN RUNTIME / GENERATOR-TRUTH COLUMNS
# ============================================================

FORBIDDEN_RUNTIME_COLUMNS: set[str] = {
    # Auto generator truth

    "latent_purchase_intent",

    "request_probability",
    "completion_probability",

    "booking_probability",

    "cancellation_probability",

    "claim_probability",

    "root_cause",
    "root_cause_domain",
    "true_root_cause",

    # Scenario truth

    "scenario_event_id",
    "scenario_id",
    "scenario_name",

    "scenario_type",
    "scenario_severity",

    "is_anomaly",
    "anomaly_type",

    "expected_warning",
    "expected_primary_signal",
    "expected_direction",

    # Causal ground truth

    "true_causal_parent",
    "true_causal_child",

    "causal_coefficient",

    "ground_truth_edge",
    "ground_truth_edge_id",

    "expectation_id",

    "true_root_signal",

    "expected_change",
    "expected_lag_hours",

    "generator_effect",

    "ground_truth_version",
}


# ============================================================
# GROUPING KEYS
# ============================================================

GROUP_KEYS = [
    "_region_id",
    "_region_name",
    "_window_start",
]


# ============================================================
# COLUMN HELPERS
# ============================================================


def _find_column(
    dataframe: pd.DataFrame,
    candidates: Sequence[str],
    dataset_name: str,
    logical_name: str,
) -> str:
    """
    Resolve one required column from supported aliases.
    """

    for candidate in candidates:

        if candidate in dataframe.columns:

            return candidate

    available_columns = sorted(
        str(column)
        for column in dataframe.columns
    )

    raise ValueError(
        f"{dataset_name} is missing the column required "
        f"for {logical_name}.\n"
        f"Expected one of: {', '.join(candidates)}\n"
        f"Available columns: {', '.join(available_columns)}"
    )


def _find_optional_column(
    dataframe: pd.DataFrame,
    candidates: Sequence[str],
) -> str | None:
    """
    Resolve one optional column.
    """

    for candidate in candidates:

        if candidate in dataframe.columns:

            return candidate

    return None


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
    Read synthetic generation window.
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

    start_value = time_config.get(
        "start",
        time_config.get(
            "start_date"
        ),
    )

    end_value = time_config.get(
        "end",
        time_config.get(
            "end_date"
        ),
    )

    if start_value is None:

        raise KeyError(
            "Missing generation start/start_date"
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
            "Generation end must be later than start"
        )

    return (
        start,
        end,
        timezone,
    )


# ============================================================
# TIMESTAMP NORMALIZATION
# ============================================================


def _normalize_timestamp_series(
    series: pd.Series,
    timezone: str,
) -> pd.Series:
    """
    Normalize event timestamps to configured timezone.
    """

    result = pd.to_datetime(
        series,
        errors="coerce",
    )

    try:

        current_timezone = result.dt.tz

    except AttributeError as exc:

        raise ValueError(
            "Timestamp column could not be converted "
            "to pandas datetime"
        ) from exc

    if current_timezone is None:

        result = result.dt.tz_localize(
            timezone
        )

    else:

        result = result.dt.tz_convert(
            timezone
        )

    return result


# ============================================================
# BOOLEAN NORMALIZATION
# ============================================================


def _to_bool_series(
    series: pd.Series,
) -> pd.Series:
    """
    Normalize bool / 0 / 1 / common text representations.
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
        "1",
        "YES",
        "Y",

        "COMPLETED",

        "RESPONDED",
        "CUSTOMER_RESPONDED",
        "RESPONSE_RECEIVED",

        "APPROVED",

        "DELAYED",
    }

    false_values = {
        "FALSE",
        "0",
        "NO",
        "N",

        "NOT_COMPLETED",

        "NO_RESPONSE",
        "NOT_RESPONDED",

        "REJECTED",
    }

    def convert(
        value: Any,
    ) -> bool:

        if pd.isna(
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
                np.integer,
                float,
                np.floating,
            ),
        ):

            return bool(
                value
            )

        text = (
            str(
                value
            )
            .strip()
            .upper()
        )

        if text in true_values:

            return True

        if text in false_values:

            return False

        return False

    return (
        series
        .map(
            convert
        )
        .astype(bool)
    )


# ============================================================
# REGION MASTER
# ============================================================


def _canonicalize_regions(
    regions: pd.DataFrame,
) -> pd.DataFrame:
    """
    Canonical region lookup.
    """

    if regions.empty:

        raise ValueError(
            "regions DataFrame cannot be empty"
        )

    region_id_col = _find_column(
        regions,
        (
            "region_id",
            "id",
        ),
        "regions",
        "region ID",
    )

    region_name_col = _find_column(
        regions,
        (
            "region_name",
            "region",
            "name",
        ),
        "regions",
        "region name",
    )

    result = (
        regions[
            [
                region_id_col,
                region_name_col,
            ]
        ]
        .copy()
        .rename(
            columns={
                region_id_col:
                    "region_id",

                region_name_col:
                    "region_name",
            }
        )
    )

    result[
        "region_id"
    ] = (
        result[
            "region_id"
        ]
        .astype(str)
    )

    result[
        "region_name"
    ] = (
        result[
            "region_name"
        ]
        .astype(str)
    )

    if result[
        "region_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate region_id found"
        )

    if result[
        "region_name"
    ].duplicated().any():

        raise ValueError(
            "Duplicate region_name found"
        )

    return (
        result
        .sort_values(
            "region_id"
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# EVENT PREPARATION
# ============================================================


def _prepare_event_frame(
    dataframe: pd.DataFrame,
    dataset_name: str,
    timestamp_candidates: Sequence[str],
    regions: pd.DataFrame,
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
    timezone: str,
    window_frequency: str,
) -> pd.DataFrame:
    """
    Canonicalize region and event timestamp and create
    a minute-level aggregation bucket.
    """

    work = dataframe.copy()

    if work.empty:

        work[
            "_region_id"
        ] = pd.Series(
            dtype="object"
        )

        work[
            "_region_name"
        ] = pd.Series(
            dtype="object"
        )

        work[
            "_event_timestamp"
        ] = pd.Series(
            dtype="object"
        )

        work[
            "_window_start"
        ] = pd.Series(
            dtype="object"
        )

        return work

    timestamp_col = _find_column(
        work,
        timestamp_candidates,
        dataset_name,
        "event timestamp",
    )

    region_id_col = _find_optional_column(
        work,
        (
            "region_id",
            "dealer_region_id",
            "service_region_id",
            "delivery_region_id",
            "customer_region_id",
        ),
    )

    region_name_col = _find_optional_column(
        work,
        (
            "region_name",
            "region",
            "dealer_region",
            "service_region",
            "delivery_region",
            "customer_region",
        ),
    )

    if (
        region_id_col is None
        and
        region_name_col is None
    ):

        available_columns = ", ".join(
            sorted(
                str(column)
                for column in work.columns
            )
        )

        raise ValueError(
            f"{dataset_name} has neither a region ID "
            "nor region-name column.\n"
            f"Available columns: {available_columns}"
        )

    id_to_name = dict(
        zip(
            regions[
                "region_id"
            ],
            regions[
                "region_name"
            ],
        )
    )

    name_to_id = dict(
        zip(
            regions[
                "region_name"
            ],
            regions[
                "region_id"
            ],
        )
    )

    # --------------------------------------------------------
    # REGION ID
    # --------------------------------------------------------

    if region_id_col is not None:

        work[
            "_region_id"
        ] = (
            work[
                region_id_col
            ]
            .astype(str)
        )

    else:

        work[
            "_region_id"
        ] = (
            work[
                region_name_col
            ]
            .astype(str)
            .map(
                name_to_id
            )
        )

    # --------------------------------------------------------
    # REGION NAME
    # --------------------------------------------------------

    if region_name_col is not None:

        work[
            "_region_name"
        ] = (
            work[
                region_name_col
            ]
            .astype(str)
        )

    else:

        work[
            "_region_name"
        ] = (
            work[
                "_region_id"
            ]
            .map(
                id_to_name
            )
        )

    if work[
        "_region_id"
    ].isna().any():

        raise ValueError(
            f"{dataset_name} contains unknown region names"
        )

    if work[
        "_region_name"
    ].isna().any():

        raise ValueError(
            f"{dataset_name} contains unknown region IDs"
        )

    expected_region_names = (
        work[
            "_region_id"
        ]
        .map(
            id_to_name
        )
    )

    mismatch = (
        expected_region_names
        !=
        work[
            "_region_name"
        ]
    )

    if mismatch.any():

        bad = (
            work.loc[
                mismatch,
                [
                    "_region_id",
                    "_region_name",
                ],
            ]
            .drop_duplicates()
            .head(
                10
            )
        )

        raise ValueError(
            f"{dataset_name} contains region ID/name "
            "mismatches:\n"
            +
            bad.to_string(
                index=False
            )
        )

    # --------------------------------------------------------
    # EVENT TIMESTAMP
    # --------------------------------------------------------

    work[
        "_event_timestamp"
    ] = (
        _normalize_timestamp_series(
            work[
                timestamp_col
            ],
            timezone,
        )
    )

    work = (
        work[
            work[
                "_event_timestamp"
            ].notna()
        ]
        .copy()
    )

    # Only runtime observation window.

    work = (
        work[
            (
                work[
                    "_event_timestamp"
                ]
                >=
                generation_start
            )
            &
            (
                work[
                    "_event_timestamp"
                ]
                <
                generation_end
            )
        ]
        .copy()
    )

    work[
        "_window_start"
    ] = (
        work[
            "_event_timestamp"
        ]
        .dt.floor(
            window_frequency
        )
    )

    return work


# ============================================================
# STATUS
# ============================================================


def _status_series(
    dataframe: pd.DataFrame,
    candidates: Sequence[str],
    dataset_name: str,
) -> pd.Series:
    """
    Resolve normalized status.
    """

    column = _find_column(
        dataframe,
        candidates,
        dataset_name,
        "status",
    )

    return (
        dataframe[
            column
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )


# ============================================================
# COUNT AGGREGATION
# ============================================================


def _count_metric(
    work: pd.DataFrame,
    metric_name: str,
    mask: pd.Series | None = None,
) -> pd.DataFrame:
    """
    Count events by region/window.
    """

    output_columns = (
        GROUP_KEYS
        +
        [
            metric_name
        ]
    )

    if work.empty:

        return pd.DataFrame(
            columns=
                output_columns
        )

    selected = work

    if mask is not None:

        aligned_mask = (
            mask.reindex(
                work.index,
                fill_value=False,
            )
        )

        selected = (
            work.loc[
                aligned_mask
            ]
            .copy()
        )

    if selected.empty:

        return pd.DataFrame(
            columns=
                output_columns
        )

    return (
        selected
        .groupby(
            GROUP_KEYS,
            dropna=False,
        )
        .size()
        .reset_index(
            name=
                metric_name
        )
    )


# ============================================================
# SUM AGGREGATION
# ============================================================


def _sum_metric(
    work: pd.DataFrame,
    source_column: str,
    metric_name: str,
    mask: pd.Series | None = None,
) -> pd.DataFrame:
    """
    Sum numeric business values.
    """

    output_columns = (
        GROUP_KEYS
        +
        [
            metric_name
        ]
    )

    if work.empty:

        return pd.DataFrame(
            columns=
                output_columns
        )

    selected = work

    if mask is not None:

        aligned_mask = (
            mask.reindex(
                work.index,
                fill_value=False,
            )
        )

        selected = (
            work.loc[
                aligned_mask
            ]
            .copy()
        )

    if selected.empty:

        return pd.DataFrame(
            columns=
                output_columns
        )

    selected = selected.copy()

    selected[
        "_numeric_value"
    ] = (
        pd.to_numeric(
            selected[
                source_column
            ],
            errors="coerce",
        )
        .fillna(0.0)
    )

    return (
        selected
        .groupby(
            GROUP_KEYS,
            dropna=False,
        )[
            "_numeric_value"
        ]
        .sum()
        .reset_index(
            name=
                metric_name
        )
    )


# ============================================================
# MEAN AGGREGATION
# ============================================================


def _mean_metric(
    work: pd.DataFrame,
    source_column: str,
    metric_name: str,
    mask: pd.Series | None = None,
) -> pd.DataFrame:
    """
    Average numeric business values.
    """

    output_columns = (
        GROUP_KEYS
        +
        [
            metric_name
        ]
    )

    if work.empty:

        return pd.DataFrame(
            columns=
                output_columns
        )

    selected = work

    if mask is not None:

        aligned_mask = (
            mask.reindex(
                work.index,
                fill_value=False,
            )
        )

        selected = (
            work.loc[
                aligned_mask
            ]
            .copy()
        )

    if selected.empty:

        return pd.DataFrame(
            columns=
                output_columns
        )

    selected = selected.copy()

    selected[
        "_numeric_value"
    ] = pd.to_numeric(
        selected[
            source_column
        ],
        errors="coerce",
    )

    selected = (
        selected[
            selected[
                "_numeric_value"
            ].notna()
        ]
        .copy()
    )

    if selected.empty:

        return pd.DataFrame(
            columns=
                output_columns
        )

    return (
        selected
        .groupby(
            GROUP_KEYS,
            dropna=False,
        )[
            "_numeric_value"
        ]
        .mean()
        .reset_index(
            name=
                metric_name
        )
    )


# ============================================================
# REGION × TIME GRID
# ============================================================


def _build_base_grid(
    regions: pd.DataFrame,
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
    window_frequency: str,
) -> pd.DataFrame:
    """
    Generate every region/window combination.
    """

    windows = pd.date_range(
        start=
            generation_start,

        end=
            generation_end,

        freq=
            window_frequency,

        inclusive=
            "left",
    )

    if len(
        windows
    ) == 0:

        raise ValueError(
            "No mobility windows generated"
        )

    rows: list[
        dict[str, Any]
    ] = []

    for region in regions.itertuples(
        index=False
    ):

        for window_start in windows:

            rows.append(
                {
                    "region_id":
                        str(
                            region.region_id
                        ),

                    "region_name":
                        str(
                            region.region_name
                        ),

                    "window_start":
                        window_start,

                    "window_end":
                        (
                            window_start
                            +
                            pd.Timedelta(window_frequency)
                        ),
                }
            )

    return pd.DataFrame(
        rows
    )


# ============================================================
# MERGE METRICS
# ============================================================


def _merge_metric_frame(
    result: pd.DataFrame,
    metric_frame: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge aggregated metric into complete region/time grid.
    """

    if metric_frame.empty:

        return result

    work = (
        metric_frame
        .rename(
            columns={
                "_region_id":
                    "region_id",

                "_region_name":
                    "region_name",

                "_window_start":
                    "window_start",
            }
        )
    )

    return result.merge(
        work,
        on=[
            "region_id",
            "region_name",
            "window_start",
        ],
        how=
            "left",
        validate=
            "one_to_one",
    )


# ============================================================
# MAIN GENERATOR
# ============================================================


def generate_mobility_timeseries(
    regions: pd.DataFrame,

    leads: pd.DataFrame,
    followups: pd.DataFrame,
    test_drives: pd.DataFrame,
    bookings: pd.DataFrame,

    finance_applications: pd.DataFrame,
    cancellations: pd.DataFrame,

    allocations: pd.DataFrame,
    deliveries: pd.DataFrame,

    service_events: pd.DataFrame,
    warranty_claims: pd.DataFrame,

    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate region-level rolling 12-hour measures at one-minute cadence.
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    (
        generation_start,
        generation_end,
        timezone,
    ) = _get_generation_window(
        generation
    )

    mobility_config = generation.get("mobility", {})
    window_frequency = str(mobility_config.get("frequency", "1min"))
    history_days = int(mobility_config.get("history_days", 30))
    rolling_hours = int(
        mobility_config.get("rolling_business_window_hours", 12)
    )

    if history_days <= 0 or rolling_hours <= 0:
        raise ValueError("mobility history and rolling window must be positive")

    if pd.Timedelta(window_frequency) != pd.Timedelta(minutes=1):
        raise ValueError("mobility.frequency must be exactly 1min")

    generation_start = max(
        generation_start,
        generation_end - pd.Timedelta(days=history_days),
    )

    regions = (
        _canonicalize_regions(
            regions
        )
    )

    result = (
        _build_base_grid(
            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            window_frequency=
                window_frequency,
        )
    )

    metric_frames: list[
        pd.DataFrame
    ] = []

    # ========================================================
    # 1. LEADS
    # ========================================================

    lead_work = (
        _prepare_event_frame(
            dataframe=
                leads,

            dataset_name=
                "leads",

            timestamp_candidates=(
                "lead_created_at",
                "lead_timestamp",
                "created_at",
                "generated_at",
                "timestamp",
            ),

            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            timezone=
                timezone,

            window_frequency=
                window_frequency,
        )
    )

    metric_frames.append(
        _count_metric(
            lead_work,
            "lead_count",
        )
    )

    lead_engagement_col = (
        _find_column(
            lead_work,
            (
                "engagement_score",
            ),
            "leads",
            "engagement score",
        )
    )

    metric_frames.append(
        _mean_metric(
            lead_work,
            lead_engagement_col,
            "avg_lead_engagement_score",
        )
    )

    # ========================================================
    # 2. FOLLOW-UPS
    #
    # scheduled_at
    #     -> followup_count
    #
    # completed_at
    #     -> followup_completed_count
    #
    # response_at
    #     -> customer_response_count
    #     -> avg_followup_response_minutes
    # ========================================================

    # --------------------------------------------------------
    # 2A. SCHEDULED FOLLOW-UPS
    # --------------------------------------------------------

    followup_scheduled_work = (
        _prepare_event_frame(
            dataframe=
                followups,

            dataset_name=
                "followups.scheduled",

            timestamp_candidates=(
                "scheduled_at",
            ),

            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            timezone=
                timezone,

            window_frequency=
                window_frequency,
        )
    )

    metric_frames.append(
        _count_metric(
            followup_scheduled_work,
            "followup_count",
        )
    )

    # --------------------------------------------------------
    # 2B. COMPLETED FOLLOW-UPS
    # --------------------------------------------------------

    completed_col = (
        _find_column(
            followups,
            (
                "completed",
                "is_completed",
                "followup_completed",
            ),
            "followups",
            "completion flag",
        )
    )

    completed_source_mask = (
        _to_bool_series(
            followups[
                completed_col
            ]
        )
    )

    completed_followups_source = (
        followups.loc[
            completed_source_mask
        ]
        .copy()
    )

    completed_at_col = (
        _find_column(
            completed_followups_source,
            (
                "completed_at",
            ),
            "followups.completed",
            "completion timestamp",
        )
    )

    if (
        completed_followups_source[
            completed_at_col
        ]
        .isna()
        .any()
    ):

        raise ValueError(
            "Completed follow-ups contain missing "
            "completed_at timestamps"
        )

    followup_completed_work = (
        _prepare_event_frame(
            dataframe=
                completed_followups_source,

            dataset_name=
                "followups.completed",

            timestamp_candidates=(
                "completed_at",
            ),

            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            timezone=
                timezone,

            window_frequency=
                window_frequency,
        )
    )

    metric_frames.append(
        _count_metric(
            followup_completed_work,
            "followup_completed_count",
        )
    )

    # --------------------------------------------------------
    # 2C. CUSTOMER RESPONSES
    # --------------------------------------------------------

    customer_response_col = (
        _find_column(
            followups,
            (
                "customer_responded",
                "customer_response",
                "responded",
                "response_received",
                "has_customer_response",
            ),
            "followups",
            "customer response",
        )
    )

    response_source_mask = (
        _to_bool_series(
            followups[
                customer_response_col
            ]
        )
    )

    responded_followups_source = (
        followups.loc[
            response_source_mask
        ]
        .copy()
    )

    response_at_col = (
        _find_column(
            responded_followups_source,
            (
                "response_at",
            ),
            "followups.response",
            "response timestamp",
        )
    )

    if (
        responded_followups_source[
            response_at_col
        ]
        .isna()
        .any()
    ):

        raise ValueError(
            "Responded follow-ups contain missing "
            "response_at timestamps"
        )

    followup_response_work = (
        _prepare_event_frame(
            dataframe=
                responded_followups_source,

            dataset_name=
                "followups.response",

            timestamp_candidates=(
                "response_at",
            ),

            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            timezone=
                timezone,

            window_frequency=
                window_frequency,
        )
    )

    metric_frames.append(
        _count_metric(
            followup_response_work,
            "customer_response_count",
        )
    )

    response_time_col = (
        _find_column(
            followup_response_work,
            (
                "response_time_minutes",
                "customer_response_time_minutes",
                "response_minutes",
            ),
            "followups.response",
            "response time minutes",
        )
    )

    metric_frames.append(
        _mean_metric(
            followup_response_work,
            response_time_col,
            "avg_followup_response_minutes",
        )
    )

    # ========================================================
    # 3. TEST DRIVE REQUESTS
    # ========================================================

    test_drive_request_work = (
        _prepare_event_frame(
            dataframe=
                test_drives,

            dataset_name=
                "test_drives.request",

            timestamp_candidates=(
                "requested_at",
                "request_timestamp",
                "test_drive_requested_at",
                "created_at",
                "scheduled_at",
                "timestamp",
            ),

            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            timezone=
                timezone,

            window_frequency=
                window_frequency,
        )
    )

    metric_frames.append(
        _count_metric(
            test_drive_request_work,
            "test_drive_requested_count",
        )
    )

    if not test_drives.empty:

        test_drive_status = (
            _status_series(
                test_drives,
                (
                    "status",
                    "test_drive_status",
                ),
                "test_drives",
            )
        )

    else:

        test_drive_status = pd.Series(
            dtype="object"
        )

    # --------------------------------------------------------
    # COMPLETED TEST DRIVES
    # --------------------------------------------------------

    completed_test_drive_source = (
        test_drives.loc[
            test_drive_status
            ==
            "COMPLETED"
        ]
        .copy()
        if not test_drives.empty
        else
        test_drives.copy()
    )

    test_drive_complete_work = (
        _prepare_event_frame(
            dataframe=
                completed_test_drive_source,

            dataset_name=
                "test_drives.completed",

            timestamp_candidates=(
                "completed_at",
                "completion_timestamp",
                "test_drive_completed_at",
                "actual_completion_at",
                "scheduled_at",
                "requested_at",
            ),

            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            timezone=
                timezone,

            window_frequency=
                window_frequency,
        )
    )

    metric_frames.append(
        _count_metric(
            test_drive_complete_work,
            "test_drive_completed_count",
        )
    )

    # --------------------------------------------------------
    # TEST DRIVE NO-SHOWS
    # --------------------------------------------------------

    no_show_source = (
        test_drives.loc[
            test_drive_status
            ==
            "NO_SHOW"
        ]
        .copy()
        if not test_drives.empty
        else
        test_drives.copy()
    )

    no_show_work = (
        _prepare_event_frame(
            dataframe=
                no_show_source,

            dataset_name=
                "test_drives.no_show",

            timestamp_candidates=(
                "scheduled_at",
                "requested_at",
                "request_timestamp",
                "created_at",
            ),

            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            timezone=
                timezone,

            window_frequency=
                window_frequency,
        )
    )

    metric_frames.append(
        _count_metric(
            no_show_work,
            "test_drive_no_show_count",
        )
    )

    # ========================================================
    # 4. BOOKINGS
    # ========================================================

    booking_work = (
        _prepare_event_frame(
            dataframe=
                bookings,

            dataset_name=
                "bookings",

            timestamp_candidates=(
                "booking_timestamp",
                "booked_at",
                "booking_date",
                "created_at",
                "timestamp",
            ),

            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            timezone=
                timezone,

            window_frequency=
                window_frequency,
        )
    )

    metric_frames.append(
        _count_metric(
            booking_work,
            "booking_count",
        )
    )

    booking_amount_col = (
        _find_column(
            booking_work,
            (
                "booking_amount_inr",
                "booking_amount",
                "amount_inr",
            ),
            "bookings",
            "booking amount",
        )
    )

    metric_frames.append(
        _sum_metric(
            booking_work,
            booking_amount_col,
            "booking_value_inr",
        )
    )

    # ========================================================
    # 5. FINANCE APPLICATIONS
    # ========================================================

    finance_submission_work = (
        _prepare_event_frame(
            dataframe=
                finance_applications,

            dataset_name=
                "finance_applications.submitted",

            timestamp_candidates=(
                "submitted_at",
                "application_timestamp",
                "application_date",
                "created_at",
                "timestamp",
            ),

            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            timezone=
                timezone,

            window_frequency=
                window_frequency,
        )
    )

    metric_frames.append(
        _count_metric(
            finance_submission_work,
            "finance_application_count",
        )
    )

    # --------------------------------------------------------
    # FINANCE DECISIONS
    # --------------------------------------------------------

    finance_decision_work = (
        _prepare_event_frame(
            dataframe=
                finance_applications,

            dataset_name=
                "finance_applications.decision",

            timestamp_candidates=(
                "decision_at",
                "decided_at",
                "decision_timestamp",
                "updated_at",
                "submitted_at",
            ),

            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            timezone=
                timezone,

            window_frequency=
                window_frequency,
        )
    )

    finance_status = (
        _status_series(
            finance_decision_work,
            (
                "status",
                "finance_status",
                "application_status",
            ),
            "finance_applications",
        )
    )

    finance_approved_mask = (
        finance_status
        ==
        "APPROVED"
    )

    finance_rejected_mask = (
        finance_status
        ==
        "REJECTED"
    )

    finance_manual_review_mask = (
        finance_status
        ==
        "MANUAL_REVIEW"
    )

    metric_frames.append(
        _count_metric(
            finance_decision_work,
            "finance_approved_count",
            mask=
                finance_approved_mask,
        )
    )

    metric_frames.append(
        _count_metric(
            finance_decision_work,
            "finance_rejected_count",
            mask=
                finance_rejected_mask,
        )
    )

    metric_frames.append(
        _count_metric(
            finance_decision_work,
            "finance_manual_review_count",
            mask=
                finance_manual_review_mask,
        )
    )

    finance_tat_col = (
        _find_column(
            finance_decision_work,
            (
                "approval_tat_hours",
                "decision_tat_hours",
                "tat_hours",
            ),
            "finance_applications",
            "approval TAT",
        )
    )

    metric_frames.append(
        _mean_metric(
            finance_decision_work,
            finance_tat_col,
            "avg_finance_approval_tat_hours",
        )
    )

    # ========================================================
    # 6. CANCELLATIONS
    # ========================================================

    cancellation_work = (
        _prepare_event_frame(
            dataframe=
                cancellations,

            dataset_name=
                "cancellations",

            timestamp_candidates=(
                "cancelled_at",
                "cancellation_timestamp",
                "cancelled_timestamp",
                "cancellation_date",
                "created_at",
                "timestamp",
            ),

            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            timezone=
                timezone,

            window_frequency=
                window_frequency,
        )
    )

    metric_frames.append(
        _count_metric(
            cancellation_work,
            "cancellation_count",
        )
    )

    # ========================================================
    # 7. ALLOCATIONS
    # ========================================================

    allocation_work = (
        _prepare_event_frame(
            dataframe=
                allocations,

            dataset_name=
                "allocations",

            timestamp_candidates=(
                "allocation_date",
                "allocated_at",
                "allocation_timestamp",
                "created_at",
                "timestamp",
            ),

            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            timezone=
                timezone,

            window_frequency=
                window_frequency,
        )
    )

    allocation_status = (
        _status_series(
            allocation_work,
            (
                "allocation_status",
                "status",
            ),
            "allocations",
        )
    )

    allocated_mask = (
        allocation_status
        ==
        "ALLOCATED"
    )

    waitlisted_mask = (
        allocation_status
        ==
        "WAITLISTED"
    )

    allocated_units_col = (
        _find_optional_column(
            allocation_work,
            (
                "allocated_units",
                "allocated_vehicle_units",
            ),
        )
    )

    if allocated_units_col is not None:

        metric_frames.append(
            _sum_metric(
                allocation_work,
                allocated_units_col,
                "allocated_vehicle_count",
                mask=
                    allocated_mask,
            )
        )

    else:

        metric_frames.append(
            _count_metric(
                allocation_work,
                "allocated_vehicle_count",
                mask=
                    allocated_mask,
            )
        )

    metric_frames.append(
        _count_metric(
            allocation_work,
            "waitlisted_booking_count",
            mask=
                waitlisted_mask,
        )
    )

    allocation_wait_col = (
        _find_column(
            allocation_work,
            (
                "allocation_wait_hours",
                "wait_hours",
                "allocation_latency_hours",
            ),
            "allocations",
            "allocation wait hours",
        )
    )

    metric_frames.append(
        _mean_metric(
            allocation_work,
            allocation_wait_col,
            "avg_allocation_wait_hours",
            mask=
                allocated_mask,
        )
    )

    # ========================================================
    # 8. DELIVERIES
    # ========================================================

    delivery_work = (
        _prepare_event_frame(
            dataframe=
                deliveries,

            dataset_name=
                "deliveries",

            timestamp_candidates=(
                "actual_delivery_date",
                "actual_delivery_at",
                "delivered_at",
                "handover_at",
                "actual_handover_at",
                "actual_date",
            ),

            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            timezone=
                timezone,

            window_frequency=
                window_frequency,
        )
    )

    delivery_status_col = (
        _find_optional_column(
            delivery_work,
            (
                "delivery_status",
                "handover_status",
                "status",
            ),
        )
    )

    if delivery_status_col is not None:

        delivery_status = (
            delivery_work[
                delivery_status_col
            ]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        delivered_mask = (
            delivery_status
            ==
            "DELIVERED"
        )

    else:

        delivered_mask = pd.Series(
            True,
            index=
                delivery_work.index,
        )

    metric_frames.append(
        _count_metric(
            delivery_work,
            "delivered_vehicle_count",
            mask=
                delivered_mask,
        )
    )

    delayed_col = (
        _find_optional_column(
            delivery_work,
            (
                "delayed",
                "is_delayed",
            ),
        )
    )

    delay_days_col = (
        _find_column(
            delivery_work,
            (
                "delay_days",
                "delivery_delay_days",
                "delay_in_days",
            ),
            "deliveries",
            "delivery delay days",
        )
    )

    if delayed_col is not None:

        delayed_mask = (
            delivered_mask
            &
            _to_bool_series(
                delivery_work[
                    delayed_col
                ]
            )
        )

    else:

        delay_values = (
            pd.to_numeric(
                delivery_work[
                    delay_days_col
                ],
                errors="coerce",
            )
            .fillna(0.0)
        )

        delayed_mask = (
            delivered_mask
            &
            (
                delay_values
                >
                0
            )
        )

    metric_frames.append(
        _count_metric(
            delivery_work,
            "delayed_delivery_count",
            mask=
                delayed_mask,
        )
    )

    metric_frames.append(
        _mean_metric(
            delivery_work,
            delay_days_col,
            "avg_delivery_delay_days",
            mask=
                delayed_mask,
        )
    )

    # ========================================================
    # 9. SERVICE
    # ========================================================

    service_work = (
        _prepare_event_frame(
            dataframe=
                service_events,

            dataset_name=
                "service_events",

            timestamp_candidates=(
                "service_started_at",
                "service_start",
                "service_start_at",
                "started_at",
                "start_at",
                "service_timestamp",
                "service_event_timestamp",
                "service_date",
                "event_timestamp",
                "created_at",
                "timestamp",
            ),

            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            timezone=
                timezone,

            window_frequency=
                window_frequency,
        )
    )

    metric_frames.append(
        _count_metric(
            service_work,
            "service_event_count",
        )
    )

    service_type_col = (
        _find_column(
            service_work,
            (
                "service_type",
                "event_type",
                "service_event_type",
            ),
            "service_events",
            "service type",
        )
    )

    service_type = (
        service_work[
            service_type_col
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    unscheduled_repair_mask = (
        service_type
        ==
        "UNSCHEDULED_REPAIR"
    )

    metric_frames.append(
        _count_metric(
            service_work,
            "unscheduled_repair_count",
            mask=
                unscheduled_repair_mask,
        )
    )

    # ========================================================
    # 10. WARRANTY
    # ========================================================

    warranty_work = (
        _prepare_event_frame(
            dataframe=
                warranty_claims,

            dataset_name=
                "warranty_claims",

            timestamp_candidates=(
                "claim_submitted_at",
                "submitted_at",
                "claim_timestamp",
                "claim_date",
                "created_at",
                "timestamp",
            ),

            regions=
                regions,

            generation_start=
                generation_start,

            generation_end=
                generation_end,

            timezone=
                timezone,

            window_frequency=
                window_frequency,
        )
    )

    metric_frames.append(
        _count_metric(
            warranty_work,
            "warranty_claim_count",
        )
    )

    warranty_status = (
        _status_series(
            warranty_work,
            (
                "claim_status",
                "status",
                "warranty_status",
            ),
            "warranty_claims",
        )
    )

    warranty_approved_mask = (
        warranty_status
        ==
        "APPROVED"
    )

    metric_frames.append(
        _count_metric(
            warranty_work,
            "warranty_approved_count",
            mask=
                warranty_approved_mask,
        )
    )

    warranty_amount_col = (
        _find_column(
            warranty_work,
            (
                "claim_amount_inr",
                "claim_amount",
                "amount_inr",
            ),
            "warranty_claims",
            "claim amount",
        )
    )

    metric_frames.append(
        _sum_metric(
            warranty_work,
            warranty_amount_col,
            "warranty_claim_amount_inr",
        )
    )

    # ========================================================
    # MERGE ALL METRICS
    # ========================================================

    for metric_frame in metric_frames:

        result = (
            _merge_metric_frame(
                result,
                metric_frame,
            )
        )

    # ========================================================
    # COMPLETE OUTPUT SCHEMA
    # ========================================================

    for column in ALL_METRIC_COLUMNS:

        if column not in result.columns:

            result[
                column
            ] = 0.0

    # ========================================================
    # ROLLING BUSINESS MEASURES
    # ========================================================

    rolling_steps = rolling_hours * 60

    for column in (*COUNT_COLUMNS, *SUM_COLUMNS):
        result[column] = (
            result.groupby("region_id", sort=False)[column]
            .transform(lambda values: values.rolling(rolling_steps, min_periods=1).sum())
        )

    for column in MEAN_COLUMNS:
        result[column] = (
            result[column].where(result[column] > 0.0)
            .groupby(result["region_id"], sort=False)
            .transform(lambda values: values.rolling(rolling_steps, min_periods=1).mean())
            .fillna(0.0)
        )

    # ========================================================
    # COUNT TYPES
    # ========================================================

    for column in COUNT_COLUMNS:

        result[
            column
        ] = (
            pd.to_numeric(
                result[
                    column
                ],
                errors="coerce",
            )
            .fillna(0)
            .round()
            .astype(int)
        )

    # ========================================================
    # SUM TYPES
    # ========================================================

    for column in SUM_COLUMNS:

        result[
            column
        ] = (
            pd.to_numeric(
                result[
                    column
                ],
                errors="coerce",
            )
            .fillna(0.0)
            .astype(float)
        )

    # ========================================================
    # MEAN TYPES
    # ========================================================

    for column in MEAN_COLUMNS:

        result[
            column
        ] = (
            pd.to_numeric(
                result[
                    column
                ],
                errors="coerce",
            )
            .fillna(0.0)
            .astype(float)
        )

    # ========================================================
    # ROUNDING
    # ========================================================

    result[
        "avg_lead_engagement_score"
    ] = result[
        "avg_lead_engagement_score"
    ].round(
        6
    )

    result[
        "avg_followup_response_minutes"
    ] = result[
        "avg_followup_response_minutes"
    ].round(
        3
    )

    result[
        "booking_value_inr"
    ] = result[
        "booking_value_inr"
    ].round(
        2
    )

    result[
        "avg_finance_approval_tat_hours"
    ] = result[
        "avg_finance_approval_tat_hours"
    ].round(
        3
    )

    result[
        "avg_allocation_wait_hours"
    ] = result[
        "avg_allocation_wait_hours"
    ].round(
        3
    )

    result[
        "avg_delivery_delay_days"
    ] = result[
        "avg_delivery_delay_days"
    ].round(
        3
    )

    result[
        "warranty_claim_amount_inr"
    ] = result[
        "warranty_claim_amount_inr"
    ].round(
        2
    )

    # ========================================================
    # PROVENANCE
    # ========================================================

    provenance = generation.get(
        "provenance",
        {},
    )

    result[
        "data_origin"
    ] = str(
        provenance.get(
            "data_origin",
            "SYNTHETIC",
        )
    )

    result[
        "generator_version"
    ] = str(
        generation.get(
            "generator_version",
            "1.0.0",
        )
    )

    # ========================================================
    # ORDER
    # ========================================================

    result = (
        result
        .sort_values(
            [
                "region_id",
                "window_start",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    validate_mobility_timeseries(
        mobility_timeseries=
            result,

        regions=
            regions,

        generation_start=
            generation_start,

        generation_end=
            generation_end,

        window_frequency=
            window_frequency,
    )

    return result


# ============================================================
# VALIDATION
# ============================================================


def validate_mobility_timeseries(
    mobility_timeseries: pd.DataFrame,
    regions: pd.DataFrame,
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
    window_frequency: str = "1min",
) -> None:
    """
    Validate mobility runtime time-series.
    """

    required_columns = {
        "region_id",
        "region_name",

        "window_start",
        "window_end",

        *ALL_METRIC_COLUMNS,

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        -
        set(
            mobility_timeseries.columns
        )
    )

    if missing:

        raise ValueError(
            "Mobility time series is missing: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    if mobility_timeseries.empty:

        raise ValueError(
            "Mobility time series cannot be empty"
        )

    # ========================================================
    # GROUND-TRUTH LEAKAGE
    # ========================================================

    leaked = (
        FORBIDDEN_RUNTIME_COLUMNS
        &
        set(
            mobility_timeseries.columns
        )
    )

    if leaked:

        raise ValueError(
            "Generator truth leaked into runtime "
            "mobility time series: "
            +
            ", ".join(
                sorted(
                    leaked
                )
            )
        )

    # ========================================================
    # DUPLICATE REGION/WINDOW
    # ========================================================

    if (
        mobility_timeseries
        .duplicated(
            subset=[
                "region_id",
                "window_start",
            ]
        )
        .any()
    ):

        raise ValueError(
            "Duplicate region/window observations found"
        )

    # ========================================================
    # EXPECTED GRID
    # ========================================================

    expected_windows = (
        pd.date_range(
            start=
                generation_start,

            end=
                generation_end,

            freq=
                window_frequency,

            inclusive=
                "left",
        )
    )

    expected_rows = (
        len(
            regions
        )
        *
        len(
            expected_windows
        )
    )

    if (
        len(
            mobility_timeseries
        )
        !=
        expected_rows
    ):

        raise ValueError(
            "Mobility row-count mismatch. "
            f"Expected {expected_rows}, "
            f"found {len(mobility_timeseries)}"
        )

    observations_per_region = (
        mobility_timeseries
        .groupby(
            "region_id"
        )
        .size()
    )

    if (
        observations_per_region
        !=
        len(
            expected_windows
        )
    ).any():

        raise ValueError(
            "One or more regions have missing windows"
        )

    # ========================================================
    # REGION SET
    # ========================================================

    expected_region_ids = set(
        regions[
            "region_id"
        ].astype(str)
    )

    actual_region_ids = set(
        mobility_timeseries[
            "region_id"
        ].astype(str)
    )

    if (
        expected_region_ids
        !=
        actual_region_ids
    ):

        raise ValueError(
            "Mobility regions do not match region master"
        )

    # ========================================================
    # WINDOW VALIDITY
    # ========================================================

    starts = pd.to_datetime(
        mobility_timeseries[
            "window_start"
        ]
    )

    ends = pd.to_datetime(
        mobility_timeseries[
            "window_end"
        ]
    )

    if (
        starts
        <
        generation_start
    ).any():

        raise ValueError(
            "Mobility window starts before generation start"
        )

    if (
        ends
        >
        generation_end
    ).any():

        raise ValueError(
            "Mobility window ends after generation end"
        )

    durations = (
        (
            ends
            -
            starts
        )
        .dt.total_seconds()
        /
        3600.0
    )

    if not np.allclose(
        durations,
        pd.Timedelta(window_frequency).total_seconds() / 3600.0,
    ):

        raise ValueError(
            "Mobility window duration is not "
            f"{pd.Timedelta(window_frequency).total_seconds() / 3600.0} hours"
        )

    # ========================================================
    # COUNT VALIDATION
    # ========================================================

    for column in COUNT_COLUMNS:

        values = pd.to_numeric(
            mobility_timeseries[
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

        if not np.allclose(
            values,
            np.round(
                values
            ),
        ):

            raise ValueError(
                f"{column} must contain integer counts"
            )

    # ========================================================
    # OTHER NUMERIC METRICS
    # ========================================================

    for column in (
        *SUM_COLUMNS,
        *MEAN_COLUMNS,
    ):

        values = pd.to_numeric(
            mobility_timeseries[
                column
            ],
            errors="raise",
        )

        if values.isna().any():

            raise ValueError(
                f"{column} contains missing values"
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
    # FOLLOW-UP LIFECYCLE VALIDATION
    #
    # IMPORTANT:
    #
    # We intentionally DO NOT validate:
    #
    # completed <= scheduled
    #
    # inside every individual 12-hour window.
    #
    # scheduled_at and completed_at can naturally belong to
    # different windows.
    #
    # Validate aggregate lifecycle totals instead.
    # ========================================================

    total_followups = int(
        mobility_timeseries[
            "followup_count"
        ].sum()
    )

    total_completed_followups = int(
        mobility_timeseries[
            "followup_completed_count"
        ].sum()
    )

    total_customer_responses = int(
        mobility_timeseries[
            "customer_response_count"
        ].sum()
    )

    if (
        total_completed_followups
        >
        total_followups
    ):

        raise ValueError(
            "Completed follow-up total exceeds "
            "scheduled follow-up total"
        )

    if (
        total_customer_responses
        >
        total_completed_followups
    ):

        raise ValueError(
            "Customer-response total exceeds "
            "completed follow-up total"
        )

    # ========================================================
    # DELIVERY CONSISTENCY
    # ========================================================

    if (
        mobility_timeseries[
            "delayed_delivery_count"
        ]
        >
        mobility_timeseries[
            "delivered_vehicle_count"
        ]
    ).any():

        raise ValueError(
            "Delayed deliveries exceed delivered vehicles "
            "inside the same time window"
        )

    # ========================================================
    # DO NOT ENFORCE THESE PER-WINDOW
    #
    # Test drive request -> no-show
    #
    # Warranty submission -> approval
    #
    # may happen in different windows.
    # ========================================================

    total_test_drive_requests = int(
        mobility_timeseries[
            "test_drive_requested_count"
        ].sum()
    )

    total_test_drive_no_shows = int(
        mobility_timeseries[
            "test_drive_no_show_count"
        ].sum()
    )

    if (
        total_test_drive_no_shows
        >
        total_test_drive_requests
    ):

        raise ValueError(
            "Total test-drive no-shows exceed "
            "total test-drive requests"
        )

    total_warranty_claims = int(
        mobility_timeseries[
            "warranty_claim_count"
        ].sum()
    )

    total_warranty_approvals = int(
        mobility_timeseries[
            "warranty_approved_count"
        ].sum()
    )

    if (
        total_warranty_approvals
        >
        total_warranty_claims
    ):

        raise ValueError(
            "Total warranty approvals exceed "
            "total warranty claims"
        )

    # ========================================================
    # PRIMARY SIGNAL VARIATION
    # ========================================================

    for variable in (
        MOBILITY_PCMCI_PRIMARY_VARIABLES
    ):

        values = pd.to_numeric(
            mobility_timeseries[
                variable
            ],
            errors="raise",
        )

        if values.nunique() <= 1:

            raise ValueError(
                "Primary mobility causal variable "
                f"{variable} is constant"
            )

    # ========================================================
    # REGION-SPECIFIC BUSINESS VARIATION
    # ========================================================

    essential_variables = (
        "lead_count",
        "booking_count",
        "cancellation_count",
    )

    for (
        region_id,
        region_rows,
    ) in (
        mobility_timeseries
        .groupby(
            "region_id"
        )
    ):

        for variable in essential_variables:

            if (
                region_rows[
                    variable
                ].nunique()
                <=
                1
            ):

                raise ValueError(
                    f"{variable} is constant for "
                    f"region {region_id}"
                )


# ============================================================
# PUBLIC ENTRY POINT
# ============================================================


def generate_mobility_timeseries_master(
    regions: pd.DataFrame,

    leads: pd.DataFrame,
    followups: pd.DataFrame,
    test_drives: pd.DataFrame,
    bookings: pd.DataFrame,

    finance_applications: pd.DataFrame,
    cancellations: pd.DataFrame,

    allocations: pd.DataFrame,
    deliveries: pd.DataFrame,

    service_events: pd.DataFrame,
    warranty_claims: pd.DataFrame,

    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Public entry point for generate_all.py.
    """

    return generate_mobility_timeseries(
        regions=
            regions,

        leads=
            leads,

        followups=
            followups,

        test_drives=
            test_drives,

        bookings=
            bookings,

        finance_applications=
            finance_applications,

        cancellations=
            cancellations,

        allocations=
            allocations,

        deliveries=
            deliveries,

        service_events=
            service_events,

        warranty_claims=
            warranty_claims,

        generation=
            generation,
    )


# ============================================================
# LOCAL INTEGRATION HELPERS
# ============================================================


def _load_generator_callable(
    module_name: str,
    candidate_names: Sequence[str],
) -> Callable[..., Any]:
    """
    Locate existing public generator function.
    """

    module = importlib.import_module(
        module_name
    )

    for candidate_name in candidate_names:

        function = getattr(
            module,
            candidate_name,
            None,
        )

        if callable(
            function
        ):

            return function

    raise AttributeError(
        f"No supported generator found in "
        f"{module_name}. Expected one of: "
        +
        ", ".join(
            candidate_names
        )
    )


def _invoke_generator(
    function: Callable[..., Any],
    available_inputs: Mapping[str, Any],
) -> Any:
    """
    Invoke generator using its actual signature.

    Used only for local integration testing.
    """

    signature = inspect.signature(
        function
    )

    kwargs: dict[
        str,
        Any
    ] = {}

    for (
        parameter_name,
        parameter,
    ) in signature.parameters.items():

        if parameter_name in available_inputs:

            kwargs[
                parameter_name
            ] = available_inputs[
                parameter_name
            ]

            continue

        if (
            parameter.default
            is
            inspect.Parameter.empty
        ):

            raise TypeError(
                f"Cannot run {function.__name__}: "
                f"required argument "
                f"'{parameter_name}' is unavailable"
            )

    return function(
        **kwargs
    )


# ============================================================
# LOCAL INTEGRATION TEST
# ============================================================


if __name__ == "__main__":

    # ========================================================
    # LOAD EXISTING GENERATORS
    # ========================================================

    generate_geography = (
        _load_generator_callable(
            "data.generators.master.geography",
            (
                "generate_geography",
            ),
        )
    )

    generate_vehicle_models = (
        _load_generator_callable(
            "data.generators.master.vehicle_models",
            (
                "generate_vehicle_models",
            ),
        )
    )

    generate_dealers = (
        _load_generator_callable(
            "data.generators.master.dealers",
            (
                "generate_dealer_master",
                "generate_dealers_master",
                "generate_dealers",
            ),
        )
    )

    generate_plants = (
        _load_generator_callable(
            "data.generators.master.plants",
            (
                "generate_plant_master",
                "generate_plants_master",
            ),
        )
    )

    generate_machines = (
        _load_generator_callable(
            "data.generators.master.machines",
            (
                "generate_machine_master",
                "generate_machines_master",
            ),
        )
    )

    generate_customers = (
        _load_generator_callable(
            "data.generators.auto.customers",
            (
                "generate_customer_master",
                "generate_customers_master",
            ),
        )
    )

    generate_leads = (
        _load_generator_callable(
            "data.generators.auto.leads",
            (
                "generate_lead_master",
                "generate_leads_master",
            ),
        )
    )

    generate_followups = (
        _load_generator_callable(
            "data.generators.auto.followups",
            (
                "generate_followup_master",
                "generate_followups_master",
            ),
        )
    )

    generate_test_drives = (
        _load_generator_callable(
            "data.generators.auto.test_drives",
            (
                "generate_test_drive_master",
                "generate_test_drives_master",
            ),
        )
    )

    generate_bookings = (
        _load_generator_callable(
            "data.generators.auto.bookings",
            (
                "generate_booking_master",
                "generate_bookings_master",
            ),
        )
    )

    generate_finance_applications = (
        _load_generator_callable(
            "data.generators.auto.finance_applications",
            (
                "generate_finance_application_master",
                "generate_finance_applications_master",
            ),
        )
    )

    generate_cancellations = (
        _load_generator_callable(
            "data.generators.auto.cancellations",
            (
                "generate_cancellation_master",
                "generate_cancellations_master",
            ),
        )
    )

    generate_suppliers = (
        _load_generator_callable(
            "data.generators.auto.suppliers",
            (
                "generate_supplier_master",
                "generate_suppliers_master",
            ),
        )
    )

    generate_production = (
        _load_generator_callable(
            "data.generators.auto.production",
            (
                "generate_production_batch_master",
                "generate_production_master",
            ),
        )
    )

    generate_allocations = (
        _load_generator_callable(
            "data.generators.auto.allocations",
            (
                "generate_allocation_master",
                "generate_allocations_master",
            ),
        )
    )

    generate_deliveries = (
        _load_generator_callable(
            "data.generators.auto.deliveries",
            (
                "generate_delivery_master",
                "generate_deliveries_master",
            ),
        )
    )

    generate_service = (
        _load_generator_callable(
            "data.generators.auto.service",
            (
                "generate_service_master",
                "generate_service_event_master",
                "generate_service_events_master",
            ),
        )
    )

    generate_warranty = (
        _load_generator_callable(
            "data.generators.auto.warranty",
            (
                "generate_warranty_master",
                "generate_warranty_claim_master",
                "generate_warranty_claims_master",
            ),
        )
    )

    # ========================================================
    # MASTER DATA
    # ========================================================

    (
        regions_df,
        cities_df,
    ) = generate_geography()

    vehicle_models_df = (
        generate_vehicle_models()
    )

    available: dict[
        str,
        Any
    ] = {
        "regions":
            regions_df,

        "cities":
            cities_df,

        "vehicle_models":
            vehicle_models_df,
    }

    dealers_df = (
        _invoke_generator(
            generate_dealers,
            available,
        )
    )

    available[
        "dealers"
    ] = dealers_df

    plant_result = (
        _invoke_generator(
            generate_plants,
            available,
        )
    )

    if (
        not isinstance(
            plant_result,
            tuple,
        )
        or
        len(
            plant_result
        )
        !=
        2
    ):

        raise ValueError(
            "plants.py must return "
            "(plants_df, production_lines_df)"
        )

    (
        plants_df,
        production_lines_df,
    ) = plant_result

    available[
        "plants"
    ] = plants_df

    available[
        "production_lines"
    ] = production_lines_df

    machines_df = (
        _invoke_generator(
            generate_machines,
            available,
        )
    )

    available[
        "machines"
    ] = machines_df

    # ========================================================
    # AUTO JOURNEY
    # ========================================================

    customers_df = (
        _invoke_generator(
            generate_customers,
            available,
        )
    )

    available[
        "customers"
    ] = customers_df

    leads_df = (
        _invoke_generator(
            generate_leads,
            available,
        )
    )

    available[
        "leads"
    ] = leads_df

    followups_df = (
        _invoke_generator(
            generate_followups,
            available,
        )
    )

    available[
        "followups"
    ] = followups_df

    test_drives_df = (
        _invoke_generator(
            generate_test_drives,
            available,
        )
    )

    available[
        "test_drives"
    ] = test_drives_df

    bookings_df = (
        _invoke_generator(
            generate_bookings,
            available,
        )
    )

    available[
        "bookings"
    ] = bookings_df

    finance_applications_df = (
        _invoke_generator(
            generate_finance_applications,
            available,
        )
    )

    available[
        "finance_applications"
    ] = finance_applications_df

    cancellations_df = (
        _invoke_generator(
            generate_cancellations,
            available,
        )
    )

    available[
        "cancellations"
    ] = cancellations_df

    # ========================================================
    # SUPPLIER / PRODUCTION
    # ========================================================

    supplier_result = (
        _invoke_generator(
            generate_suppliers,
            available,
        )
    )

    if (
        not isinstance(
            supplier_result,
            tuple,
        )
        or
        len(
            supplier_result
        )
        !=
        2
    ):

        raise ValueError(
            "suppliers.py must return "
            "(suppliers_df, supplier_lots_df)"
        )

    (
        suppliers_df,
        supplier_lots_df,
    ) = supplier_result

    available[
        "suppliers"
    ] = suppliers_df

    available[
        "supplier_lots"
    ] = supplier_lots_df

    production_batches_df = (
        _invoke_generator(
            generate_production,
            available,
        )
    )

    available[
        "production_batches"
    ] = production_batches_df

    # ========================================================
    # ALLOCATION
    # ========================================================

    allocations_df = (
        _invoke_generator(
            generate_allocations,
            available,
        )
    )

    available[
        "allocations"
    ] = allocations_df

    # ========================================================
    # DELIVERY
    # ========================================================

    deliveries_df = (
        _invoke_generator(
            generate_deliveries,
            available,
        )
    )

    available[
        "deliveries"
    ] = deliveries_df

    # ========================================================
    # SERVICE
    # ========================================================

    service_events_df = (
        _invoke_generator(
            generate_service,
            available,
        )
    )

    available[
        "service_events"
    ] = service_events_df

    available[
        "services"
    ] = service_events_df

    # ========================================================
    # WARRANTY
    # ========================================================

    warranty_claims_df = (
        _invoke_generator(
            generate_warranty,
            available,
        )
    )

    available[
        "warranty_claims"
    ] = warranty_claims_df

    # ========================================================
    # MOBILITY TIME SERIES
    # ========================================================

    mobility_df = (
        generate_mobility_timeseries_master(
            regions=
                regions_df,

            leads=
                leads_df,

            followups=
                followups_df,

            test_drives=
                test_drives_df,

            bookings=
                bookings_df,

            finance_applications=
                finance_applications_df,

            cancellations=
                cancellations_df,

            allocations=
                allocations_df,

            deliveries=
                deliveries_df,

            service_events=
                service_events_df,

            warranty_claims=
                warranty_claims_df,
        )
    )

    # ========================================================
    # INFO
    # ========================================================

    print(
        "\n=== MOBILITY TIME-SERIES INFO ===\n"
    )

    print(
        "Rows:",
        len(
            mobility_df
        ),
    )

    print(
        "Regions:",
        mobility_df[
            "region_id"
        ].nunique(),
    )

    print(
        "Window hours:",
        WINDOW_HOURS,
    )

    print(
        "Start:",
        mobility_df[
            "window_start"
        ].min(),
    )

    print(
        "End:",
        mobility_df[
            "window_end"
        ].max(),
    )

    # ========================================================
    # OBSERVATIONS PER REGION
    # ========================================================

    print(
        "\n=== OBSERVATIONS PER REGION ===\n"
    )

    print(
        mobility_df
        .groupby(
            [
                "region_id",
                "region_name",
            ]
        )
        .size()
        .reset_index(
            name=
                "observations"
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # EVENT TOTALS
    # ========================================================

    print(
        "\n=== MOBILITY EVENT TOTALS ===\n"
    )

    total_metrics = [
        (
            "Leads",
            "lead_count",
        ),

        (
            "Followups",
            "followup_count",
        ),

        (
            "Completed followups",
            "followup_completed_count",
        ),

        (
            "Customer responses",
            "customer_response_count",
        ),

        (
            "Test-drive requests",
            "test_drive_requested_count",
        ),

        (
            "Test-drive completions",
            "test_drive_completed_count",
        ),

        (
            "Test-drive no-shows",
            "test_drive_no_show_count",
        ),

        (
            "Bookings",
            "booking_count",
        ),

        (
            "Finance applications",
            "finance_application_count",
        ),

        (
            "Finance approvals",
            "finance_approved_count",
        ),

        (
            "Finance rejections",
            "finance_rejected_count",
        ),

        (
            "Finance manual reviews",
            "finance_manual_review_count",
        ),

        (
            "Cancellations",
            "cancellation_count",
        ),

        (
            "Allocated vehicles",
            "allocated_vehicle_count",
        ),

        (
            "Waitlisted bookings",
            "waitlisted_booking_count",
        ),

        (
            "Delivered vehicles",
            "delivered_vehicle_count",
        ),

        (
            "Delayed deliveries",
            "delayed_delivery_count",
        ),

        (
            "Service events",
            "service_event_count",
        ),

        (
            "Unscheduled repairs",
            "unscheduled_repair_count",
        ),

        (
            "Warranty claims",
            "warranty_claim_count",
        ),

        (
            "Warranty approvals",
            "warranty_approved_count",
        ),
    ]

    for (
        label,
        column,
    ) in total_metrics:

        print(
            f"{label}:",
            int(
                mobility_df[
                    column
                ].sum()
            ),
        )

    # ========================================================
    # FOLLOW-UP RECONCILIATION
    # ========================================================

    print(
        "\n=== FOLLOW-UP LIFECYCLE CHECK ===\n"
    )

    print(
        "Scheduled followups:",
        int(
            mobility_df[
                "followup_count"
            ].sum()
        ),
    )

    print(
        "Completed followups:",
        int(
            mobility_df[
                "followup_completed_count"
            ].sum()
        ),
    )

    print(
        "Customer responses:",
        int(
            mobility_df[
                "customer_response_count"
            ].sum()
        ),
    )

    # ========================================================
    # SAMPLE
    # ========================================================

    print(
        "\n=== MOBILITY TIME-SERIES SAMPLE ===\n"
    )

    sample_columns = [
        "window_start",

        "region_name",

        "lead_count",

        "followup_count",
        "followup_completed_count",
        "customer_response_count",

        "test_drive_requested_count",
        "test_drive_completed_count",

        "booking_count",

        "finance_approved_count",

        "cancellation_count",

        "allocated_vehicle_count",

        "avg_allocation_wait_hours",

        "delivered_vehicle_count",

        "delayed_delivery_count",

        "avg_delivery_delay_days",

        "service_event_count",

        "unscheduled_repair_count",

        "warranty_claim_count",
    ]

    print(
        mobility_df[
            sample_columns
        ]
        .head(
            40
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # SIGNAL CHECK
    # ========================================================

    print(
        "\n=== MOBILITY SIGNAL CHECK ===\n"
    )

    for variable in (
        MOBILITY_PCMCI_PRIMARY_VARIABLES
    ):

        values = pd.to_numeric(
            mobility_df[
                variable
            ],
            errors="raise",
        )

        zero_percentage = (
            100.0
            *
            (
                values
                ==
                0
            )
            .mean()
        )

        print(
            f"{variable}: "
            f"mean={values.mean():.4f}, "
            f"std={values.std():.4f}, "
            f"zero_pct={zero_percentage:.2f}%"
        )

    # ========================================================
    # REGION BUSINESS TOTALS
    # ========================================================

    print(
        "\n=== REGION BUSINESS TOTALS ===\n"
    )

    region_summary = (
        mobility_df
        .groupby(
            "region_name"
        )
        .agg(
            leads=(
                "lead_count",
                "sum",
            ),

            followups_scheduled=(
                "followup_count",
                "sum",
            ),

            followups_completed=(
                "followup_completed_count",
                "sum",
            ),

            customer_responses=(
                "customer_response_count",
                "sum",
            ),

            test_drives=(
                "test_drive_completed_count",
                "sum",
            ),

            bookings=(
                "booking_count",
                "sum",
            ),

            finance_approved=(
                "finance_approved_count",
                "sum",
            ),

            cancellations=(
                "cancellation_count",
                "sum",
            ),

            allocations=(
                "allocated_vehicle_count",
                "sum",
            ),

            delivered=(
                "delivered_vehicle_count",
                "sum",
            ),

            delayed=(
                "delayed_delivery_count",
                "sum",
            ),

            service_events=(
                "service_event_count",
                "sum",
            ),

            warranty_claims=(
                "warranty_claim_count",
                "sum",
            ),
        )
        .reset_index()
    )

    print(
        region_summary
        .to_string(
            index=False
        )
    )

    # ========================================================
    # PRIMARY PCMCI ALLOWLIST
    # ========================================================

    print(
        "\n=== PRIMARY MOBILITY PCMCI VARIABLES ===\n"
    )

    for variable in (
        MOBILITY_PCMCI_PRIMARY_VARIABLES
    ):

        print(
            "-",
            variable,
        )

    # ========================================================
    # GROUND-TRUTH LEAKAGE
    # ========================================================

    leaked = (
        FORBIDDEN_RUNTIME_COLUMNS
        &
        set(
            mobility_df.columns
        )
    )

    print(
        "\n=== RUNTIME GROUND-TRUTH LEAKAGE CHECK ===\n"
    )

    print(
        "Leaked columns:",
        sorted(
            leaked
        ),
    )

    # ========================================================
    # FINAL
    # ========================================================

    print(
        "\nGenerated "
        f"{len(mobility_df)} "
        "regional mobility business observations "
        "successfully."
    )