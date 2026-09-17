"""
Mahindra manufacturing causal panel construction.

This module converts the long-format records produced by
manufacturing_loader.fetch_raw_records() into the wide, time-aligned
DataFrame required by Tigramite PCMCI/LPCMCI.

Input
-----
Long records:

    timestamp
    entity
    metric
    value

Output
------
Wide panel:

    timestamp
        MACHINE_SYN_001||machine_load
        MACHINE_SYN_001||machine_temperature_c
        MACHINE_SYN_001||vibration_mm_s
        MACHINE_SYN_001||defect_rate
        ...

Current Mahindra baseline
-------------------------
Raw cadence:
    1 minute

Default analytical cadence:
    15 minutes

Default source window:
    72 hours per machine

Important
---------
This module does NOT:

- query PostgreSQL
- run PCMCI
- read causal ground truth
- read warranty claims
- hardcode causal edges

It only constructs and cleans the causal input panel.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller, kpss

from app.ai.causal.manufacturing_loader import (
    MANUFACTURING_METRICS,
)

logger = logging.getLogger(
    __name__
)


# ============================================================================
# CONFIGURATION
# ============================================================================


@dataclass(frozen=True)
class ManufacturingPanelConfig:
    """
    Configuration for Mahindra manufacturing causal panels.
    """

    # Analytical cadence is deliberately separate from the one-minute raw
    # PostgreSQL source cadence.
    analysis_frequency: str = "15min"

    # 96 analytical rows at 15 minutes preserve at least 24 hours of context.
    min_panel_observations: int = 96

    # A metric must contain real observations for at least this
    # fraction of the requested time window.
    min_data_coverage: float = 0.80

    # Limited forward fill for isolated missing measurements.
    #
    # We deliberately do NOT fill long gaps because that would invent
    # artificial temporal persistence.
    ffill_limit: int = 1

    # Require this fraction of variables to be populated at a timestamp.
    min_row_completeness: float = 0.70

    # Absolute variance floor.
    min_variance: float = 1e-8

    # Relative standard-deviation floor.
    relative_std_threshold: float = 1e-6

    # Drop a signal when one exact value dominates essentially the entire
    # observation window.
    #
    # Example from MACHINE_SYN_023:
    #
    # downtime_minutes
    #     dominant value = 499 / 500 observations = 99.8%
    #
    # This produced hundreds of ConstantInputWarning events inside ParCorr
    # even though the full-series variance was technically non-zero.
    #
    # maintenance_overdue_hours
    #     dominant value = 497 / 500 = 99.4%
    #
    # remains below this threshold and therefore stays available.
    max_dominant_value_fraction: float = 0.995

    # Linear partial correlation can behave poorly on extremely skewed
    # non-negative process variables.
    skew_transform_enabled: bool = True

    skew_threshold: float = 2.0

    # Drop one column of any pair whose absolute correlation exceeds this
    # threshold. Defensive against LPCMCI's larger conditioning sets
    # behaving pathologically on near-duplicate columns.
    collinearity_threshold: float = 0.999

    # Z-score normalize surviving columns after skew compression. LPCMCI's
    # ancestral/non-ancestral phases condition on larger, more varied
    # variable sets than PCMCI, so cross-scale conditioning issues compound
    # faster than they do for plain PCMCI.
    normalize_data: bool = True

    # ADF/KPSS stationarity checking and differencing, matching the
    # reference LPCMCI pipeline. LPCMCI/PCMCI's ParCorr conditional-
    # independence test assumes a stable mean/variance; a trending column
    # (e.g. hours_since_maintenance drifting upward across the analysis
    # window) violates that and can manufacture spurious partial
    # correlations. Enabled by default to genuinely match the reference
    # pipeline's behavior; statsmodels is a real, required dependency (see
    # requirements.txt), not a silently-skipped optional one.
    stationarity_differencing_enabled: bool = True

    # Benjamini-Hochberg-unrelated significance threshold for the ADF/KPSS
    # stationarity tests themselves (matches the reference pipeline's
    # hardcoded 0.05).
    stationarity_alpha: float = 0.05

    # Minimum observations required before running ADF/KPSS at all (the
    # tests are unreliable on very short series).
    min_stationarity_observations: int = 10

    # Prevent future multi-machine panels becoming unnecessarily large.
    max_variables: int = 40


DEFAULT_MANUFACTURING_PANEL_CONFIG = (
    ManufacturingPanelConfig()
)


# Explicit semantic aggregation for every runtime causal metric. Lineage and
# identifier fields are intentionally absent and can never become PCMCI
# variables through this map.
MANUFACTURING_METRIC_AGGREGATIONS: dict[str, str] = {
    "ambient_temperature_c": "mean",
    "ambient_humidity_pct": "mean",
    "machine_load": "mean",
    "machine_temperature_c": "mean",
    "vibration_mm_s": "mean",
    "power_kw": "mean",
    "line_speed_units_per_hour": "mean",
    "cycle_time_seconds": "mean",
    "hours_since_maintenance": "last",
    "maintenance_overdue_hours": "last",
    "supplier_lot_quality_score": "last",
    "torque_deviation_nm": "mean",
    "paint_booth_temperature_c": "mean",
    "paint_booth_humidity_pct": "mean",
    "paint_defect_rate": "mean",
    "defect_rate": "mean",
    "rework_rate": "mean",
    "downtime_minutes": "sum",
    "quality_score": "mean",
}

if set(MANUFACTURING_METRIC_AGGREGATIONS) != set(
    MANUFACTURING_METRICS
):
    raise RuntimeError(
        "Every manufacturing causal metric must have exactly one "
        "analytical aggregation rule."
    )


# ============================================================================
# RESULT MODEL
# ============================================================================


@dataclass
class ManufacturingPanelResult:
    """
    Result returned by build_manufacturing_panel().
    """

    panel: pd.DataFrame

    metadata: dict[
        str,
        dict[str, Any],
    ]

    dropped_metrics: dict[
        str,
        str,
    ]

    transformed_metrics: list[str]

    missing_intervals: dict[str, int] = field(
        default_factory=dict
    )

    duplicate_records_removed: int = 0

    raw_records: int = 0

    # Columns ADF/KPSS-differenced for stationarity. Separate from
    # transformed_metrics (which tracks log1p skew compression) since
    # differencing changes a column's semantic meaning (level -> delta) in
    # a way skew compression does not, and callers/UI copy need to
    # distinguish the two.
    differenced_metrics: list[str] = field(
        default_factory=list
    )


# ============================================================================
# HELPERS
# ============================================================================


def _validate_records(
    records: Sequence[
        dict[str, Any]
    ],
) -> None:
    """
    Validate the causal long-record contract.
    """

    required_fields = {
        "timestamp",
        "entity",
        "metric",
        "value",
    }

    for index, record in enumerate(
        records
    ):
        missing = (
            required_fields
            - set(record)
        )

        if missing:
            raise ValueError(
                "Manufacturing causal record "
                f"{index} is missing fields: "
                + ", ".join(
                    sorted(missing)
                )
            )


def _build_metadata(
    dataframe: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    """
    Construct Mahindra metadata for each entity||metric variable.
    """

    metadata: dict[
        str,
        dict[str, Any],
    ] = {}

    for column in sorted(
        dataframe["column"].unique()
    ):
        subset = dataframe[
            dataframe["column"]
            == column
        ]

        first = subset.iloc[
            0
        ]

        entity = str(
            first["entity"]
        )

        metric = str(
            first["metric"]
        )

        metadata[
            column
        ] = {
            "entity": entity,
            "machine_id": entity,
            "metric": metric,
            "aggregation": (
                MANUFACTURING_METRIC_AGGREGATIONS[
                    metric
                ]
            ),

            "plant_id": first.get(
                "plant_id"
            ),
            "plant_name": first.get(
                "plant_name"
            ),

            "production_line_id": first.get(
                "production_line_id"
            ),
            "production_line_name": first.get(
                "production_line_name"
            ),

            "line_type": first.get(
                "line_type"
            ),

            "machine_name": first.get(
                "machine_name"
            ),

            # Batch, vehicle model and supplier lot may change throughout
            # the observation window. They must therefore be enriched later
            # at timestamp level rather than represented here as one static
            # series-level value.
            "role": "manufacturing_process_signal",
        }

    return metadata


def _dominant_value_fraction(
    series: pd.Series,
) -> float:
    """
    Return the fraction occupied by the most common exact finite value.

    This detects extremely sparse/event-like variables that technically
    have non-zero variance but contain too little continuous information
    for stable ParCorr conditioning.

    It is intentionally different from a normal variance test.
    """

    values = pd.to_numeric(
        series,
        errors="coerce",
    )

    finite = values[
        np.isfinite(values)
    ]

    if finite.empty:
        return 1.0

    frequencies = finite.value_counts(
        dropna=False,
        normalize=True,
    )

    if frequencies.empty:
        return 1.0

    return float(
        frequencies.iloc[0]
    )


def _is_near_constant(
    series: pd.Series,
    config: ManufacturingPanelConfig,
) -> bool:
    """
    Detect ordinary constant and near-constant continuous signals.
    """

    values = pd.to_numeric(
        series,
        errors="coerce",
    )

    finite = values[
        np.isfinite(values)
    ]

    if finite.empty:
        return True

    variance = float(
        finite.var()
    )

    if not np.isfinite(
        variance
    ):
        return True

    if variance <= config.min_variance:
        return True

    std = float(
        finite.std()
    )

    mean_abs = max(
        abs(
            float(
                finite.mean()
            )
        ),
        1.0,
    )

    relative_std = (
        std / mean_abs
    )

    return (
        relative_std
        <= config.relative_std_threshold
    )


# ============================================================================
# PUBLIC PANEL BUILDER
# ============================================================================


def build_manufacturing_panel(
    records: Sequence[
        dict[str, Any]
    ],
    config: ManufacturingPanelConfig = (
        DEFAULT_MANUFACTURING_PANEL_CONFIG
    ),
) -> ManufacturingPanelResult:
    """
    Convert minute-level manufacturing records into an analytical panel.

    Pipeline:

        long records
            ->
        entity||metric variables
            ->
        regular analytical temporal grid
            ->
        coverage filtering
            ->
        limited missing-value handling
            ->
        low-information screening
            ->
        constant / near-constant screening
            ->
        optional skew transformation

    Resampling is anchored to the source-series start timestamp.
    """

    if not records:
        return ManufacturingPanelResult(
            panel=pd.DataFrame(),
            metadata={},
            dropped_metrics={},
            transformed_metrics=[],
        )

    _validate_records(
        records
    )

    dataframe = pd.DataFrame(
        records
    ).copy()

    raw_record_count = len(
        dataframe
    )

    dropped_metrics: dict[
        str,
        str,
    ] = {}

    # ------------------------------------------------------------------------
    # Normalise fundamental fields.
    # ------------------------------------------------------------------------

    dataframe["timestamp"] = (
        pd.to_datetime(
            dataframe["timestamp"],
            utc=True,
            errors="coerce",
        )
    )

    dataframe["entity"] = (
        dataframe["entity"]
        .astype(str)
        .str.strip()
    )

    dataframe["metric"] = (
        dataframe["metric"]
        .astype(str)
        .str.strip()
    )

    supported_mask = dataframe[
        "metric"
    ].isin(
        MANUFACTURING_METRICS
    )

    unsupported = dataframe[
        ~supported_mask
    ]

    for entity, metric in unsupported[
        [
            "entity",
            "metric",
        ]
    ].drop_duplicates().itertuples(
        index=False,
        name=None,
    ):
        dropped_metrics[
            f"{entity}||{metric}"
        ] = "not_a_manufacturing_causal_metric"

    dataframe = dataframe[
        supported_mask
    ]

    dataframe["value"] = (
        pd.to_numeric(
            dataframe["value"],
            errors="coerce",
        )
    )

    dataframe = dataframe.dropna(
        subset=[
            "timestamp",
            "value",
        ]
    )

    dataframe = dataframe[
        np.isfinite(
            dataframe["value"]
        )
    ]

    before_deduplication = len(
        dataframe
    )

    dataframe = dataframe.drop_duplicates(
        subset=[
            "timestamp",
            "entity",
            "metric",
            "value",
        ],
        keep="last",
    )

    duplicate_records_removed = (
        before_deduplication
        - len(dataframe)
    )

    if dataframe.empty:
        return ManufacturingPanelResult(
            panel=pd.DataFrame(),
            metadata={},
            dropped_metrics=dropped_metrics,
            transformed_metrics=[],
            duplicate_records_removed=(
                duplicate_records_removed
            ),
            raw_records=raw_record_count,
        )

    # ------------------------------------------------------------------------
    # Variable identifier.
    # ------------------------------------------------------------------------

    dataframe["column"] = (
        dataframe["entity"]
        + "||"
        + dataframe["metric"]
    )

    metadata = _build_metadata(
        dataframe
    )

    # ------------------------------------------------------------------------
    # Build regular analytical series using metric-specific semantics.
    #
    # origin="start" preserves timestamps such as:
    #
    #   22:30
    #   23:30
    #   00:30
    #
    # instead of relabelling them:
    #
    #   22:00
    #   23:00
    #   00:00
    # ------------------------------------------------------------------------

    series_list: list[
        pd.Series
    ] = []

    for column in sorted(
        dataframe["column"].unique()
    ):
        subset = dataframe[
            dataframe["column"]
            == column
        ][
            [
                "timestamp",
                "value",
            ]
        ].copy()

        subset = subset.sort_values(
            "timestamp"
        )

        metric = str(
            dataframe.loc[
                dataframe["column"]
                == column,
                "metric",
            ].iloc[0]
        )

        aggregation = (
            MANUFACTURING_METRIC_AGGREGATIONS[
                metric
            ]
        )

        resampler = (
            subset
            .set_index(
                "timestamp"
            )["value"]
            .resample(
                config.analysis_frequency,
                origin="start",
            )
        )

        if aggregation == "sum":
            series = resampler.sum(
                min_count=1
            )
        elif aggregation == "last":
            series = resampler.last()
        else:
            series = resampler.mean()

        series.name = column

        series_list.append(
            series
        )

    if not series_list:
        return ManufacturingPanelResult(
            panel=pd.DataFrame(),
            metadata={},
            dropped_metrics=dropped_metrics,
            transformed_metrics=[],
            duplicate_records_removed=(
                duplicate_records_removed
            ),
            raw_records=raw_record_count,
        )

    panel = pd.concat(
        series_list,
        axis=1,
    )

    panel = panel.sort_index()

    missing_intervals = {
        str(column): int(
            panel[column].isna().sum()
        )
        for column in panel.columns
    }

    # ------------------------------------------------------------------------
    # Coverage filtering.
    # ------------------------------------------------------------------------

    minimum_observations = int(
        np.ceil(
            len(panel)
            * config.min_data_coverage
        )
    )

    coverage_keep: list[str] = []

    for column in panel.columns:
        available = int(
            panel[column]
            .notna()
            .sum()
        )

        if available >= minimum_observations:
            coverage_keep.append(
                column
            )
        else:
            dropped_metrics[
                column
            ] = (
                "insufficient_coverage:"
                f"{available}/{len(panel)}"
            )

    panel = panel[
        coverage_keep
    ]

    if panel.empty:
        return ManufacturingPanelResult(
            panel=panel,
            metadata={},
            dropped_metrics=dropped_metrics,
            transformed_metrics=[],
            missing_intervals=missing_intervals,
            duplicate_records_removed=(
                duplicate_records_removed
            ),
            raw_records=raw_record_count,
        )

    # ------------------------------------------------------------------------
    # Limited forward fill.
    # ------------------------------------------------------------------------

    if config.ffill_limit > 0:
        panel = panel.ffill(
            limit=config.ffill_limit
        )

    # ------------------------------------------------------------------------
    # Row completeness.
    # ------------------------------------------------------------------------

    minimum_valid_columns = max(
        1,
        int(
            np.ceil(
                len(panel.columns)
                * config.min_row_completeness
            )
        ),
    )

    panel = panel.dropna(
        thresh=minimum_valid_columns
    )

    # ------------------------------------------------------------------------
    # Remove columns that still contain unresolved gaps.
    #
    # This completes the "missing-data filtering -> gap handling" stages of
    # the reference LPCMCI pipeline order:
    #   missing-data filter -> gap handling -> skew -> variance filter ->
    #   normalize -> stationarity -> collinearity removal -> variable cap.
    # ------------------------------------------------------------------------

    complete_columns: list[str] = []

    for column in panel.columns:
        missing = int(
            panel[column]
            .isna()
            .sum()
        )

        if missing == 0:
            complete_columns.append(
                column
            )
        else:
            dropped_metrics[
                column
            ] = (
                "unresolved_missing_values:"
                f"{missing}"
            )

    panel = panel[
        complete_columns
    ]

    # ------------------------------------------------------------------------
    # Skew handling.
    #
    # Only non-negative, strongly skewed signals are transformed. Runs
    # before variance filtering per the reference pipeline order -- a
    # spike-shaped column's dominant-value/near-constant character is
    # unaffected by the (monotonic) log1p transform.
    # ------------------------------------------------------------------------

    transformed_metrics: list[
        str
    ] = []

    if config.skew_transform_enabled:
        for column in panel.columns:
            series = panel[
                column
            ]

            if series.min() < 0:
                continue

            try:
                skew = float(
                    series.skew()
                )
            except Exception:
                logger.debug(
                    "Unable to calculate manufacturing signal skew.",
                    exc_info=True,
                )
                continue

            if (
                np.isfinite(skew)
                and abs(skew)
                > config.skew_threshold
            ):
                panel[
                    column
                ] = np.log1p(
                    series
                )

                transformed_metrics.append(
                    column
                )

    # ------------------------------------------------------------------------
    # Variance filtering: low-information / dominant-value screening.
    #
    # This specifically handles variables such as MACHINE_SYN_023
    # downtime_minutes:
    #
    #     one value occurs in 499 of 500 rows
    #
    # The whole-series variance is non-zero, but conditional ParCorr
    # calculations repeatedly encounter constant subsets/residuals.
    #
    # We use a statistical property of the observations rather than
    # hardcoding a metric name.
    # ------------------------------------------------------------------------

    information_keep: list[str] = []

    for column in panel.columns:
        dominant_fraction = (
            _dominant_value_fraction(
                panel[column]
            )
        )

        if (
            dominant_fraction
            >= config.max_dominant_value_fraction
        ):
            dominant_count = int(
                panel[column]
                .value_counts(
                    dropna=False
                )
                .iloc[0]
            )

            dropped_metrics[
                column
            ] = (
                "low_information_dominant_value:"
                f"{dominant_count}/{len(panel)}"
            )
        else:
            information_keep.append(
                column
            )

    panel = panel[
        information_keep
    ]

    # ------------------------------------------------------------------------
    # Variance filtering: constant / near-constant screening.
    # ------------------------------------------------------------------------

    variance_keep: list[str] = []

    for column in panel.columns:
        if _is_near_constant(
            panel[column],
            config,
        ):
            dropped_metrics[
                column
            ] = (
                "constant_or_near_constant"
            )
        else:
            variance_keep.append(
                column
            )

    panel = panel[
        variance_keep
    ]

    # ------------------------------------------------------------------------
    # Variable-budget selection criterion.
    #
    # Captured BEFORE optional normalization: once z-scored, every surviving
    # column has variance ~= 1, which would make a post-normalization
    # variance-based budget selection arbitrary/meaningless. Genuine
    # information content is what the ORIGINAL physical variance reflects.
    # ------------------------------------------------------------------------

    pre_normalization_variances = panel.var()

    # ------------------------------------------------------------------------
    # Normalization: optional z-score.
    #
    # LPCMCI's ancestral/non-ancestral phases condition on larger, more
    # varied variable sets than PCMCI, so cross-scale conditioning issues
    # compound faster. Applied after skew compression and variance
    # filtering, once every remaining column is well-conditioned continuous
    # data.
    # ------------------------------------------------------------------------

    if config.normalize_data and len(panel.columns) > 0:
        panel = (
            panel - panel.mean()
        ) / (
            panel.std()
            + 1e-8
        )

    # ------------------------------------------------------------------------
    # Stationarity: ADF/KPSS checking and differencing.
    #
    # LPCMCI/PCMCI's ParCorr conditional-independence test assumes a stable
    # mean/variance; a trending series (e.g. a metric slowly drifting over
    # the analysis window) violates that and can manufacture spurious
    # partial correlations. A column is differenced when EITHER test
    # disagrees with stationarity:
    #
    #   ADF null hypothesis = "series has a unit root" (non-stationary).
    #       adf_p >= alpha -> fail to reject non-stationarity.
    #   KPSS null hypothesis = "series IS stationary".
    #       kpss_p < alpha -> reject stationarity.
    #
    # Both are run (rather than either alone) because ADF and KPSS have
    # complementary blind spots -- requiring one test's disagreement to
    # trigger differencing catches cases either test alone would miss.
    # ------------------------------------------------------------------------

    differenced_columns: list[str] = []

    if (
        config.stationarity_differencing_enabled
        and len(panel) >= config.min_stationarity_observations
        and len(panel.columns) > 0
    ):
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore"
            )

            for column in panel.columns:
                series = panel[
                    column
                ].dropna()

                if (
                    len(series)
                    < config.min_stationarity_observations
                ):
                    continue

                try:
                    adf_p_value = adfuller(
                        series,
                        autolag="AIC",
                    )[1]

                    kpss_p_value = kpss(
                        series,
                        regression="c",
                        nlags="auto",
                    )[1]
                except Exception:
                    logger.debug(
                        "Manufacturing stationarity test failed for %s.",
                        column,
                        exc_info=True,
                    )
                    continue

                if (
                    adf_p_value
                    >= config.stationarity_alpha
                    or kpss_p_value
                    < config.stationarity_alpha
                ):
                    panel[
                        column
                    ] = panel[
                        column
                    ].diff()

                    differenced_columns.append(
                        column
                    )

        if differenced_columns:
            # .diff() introduces a leading NaN; backfill it from the
            # second row rather than dropping a row from every column.
            panel = panel.bfill().fillna(
                0.0
            )

    # ------------------------------------------------------------------------
    # Collinearity removal.
    #
    # Near-duplicate columns (|corr| above threshold) can make LPCMCI's
    # larger conditioning sets behave pathologically. Ties are broken
    # deterministically by column name so dropped-metric reasoning stays
    # reproducible across runs. Runs after stationarity differencing per
    # the reference pipeline order, so collinearity reflects the actual
    # series fed to LPCMCI/PCMCI rather than a pre-differenced trend that
    # would inflate every trending pair's correlation.
    # ------------------------------------------------------------------------

    if len(panel.columns) > 1:
        correlation = panel.corr().abs()

        collinear_drop: list[str] = []

        ordered_columns = sorted(
            panel.columns
        )

        for later_index, later_column in enumerate(
            ordered_columns
        ):
            if later_column in collinear_drop:
                continue

            for earlier_column in ordered_columns[
                :later_index
            ]:
                if earlier_column in collinear_drop:
                    continue

                if (
                    correlation.loc[
                        earlier_column,
                        later_column,
                    ]
                    > config.collinearity_threshold
                ):
                    collinear_drop.append(
                        later_column
                    )

                    dropped_metrics[
                        later_column
                    ] = (
                        "collinear_with:"
                        f"{earlier_column}"
                    )

                    break

        if collinear_drop:
            panel = panel.drop(
                columns=collinear_drop
            )

    # ------------------------------------------------------------------------
    # Deterministic variable cap.
    # ------------------------------------------------------------------------

    if (
        len(panel.columns)
        > config.max_variables
    ):
        # Alphabetical reindex before a STABLE sort guarantees a fully
        # deterministic tie-break (pandas' default quicksort is not
        # stable, so two columns with identical variance could otherwise
        # select differently between runs).
        variances = (
            pre_normalization_variances
            .reindex(
                sorted(
                    panel.columns
                )
            )
            .sort_values(
                ascending=False,
                kind="stable",
            )
        )

        selected_columns = (
            variances
            .head(
                config.max_variables
            )
            .index
            .tolist()
        )

        for column in panel.columns:
            if column not in selected_columns:
                dropped_metrics[
                    column
                ] = (
                    "variable_budget"
                )

        panel = panel[
            selected_columns
        ]

    # ------------------------------------------------------------------------
    # Final numeric sanity check.
    # ------------------------------------------------------------------------

    panel = panel.astype(
        float
    )

    matrix = panel.to_numpy(
        dtype=float
    )

    if not np.isfinite(
        matrix
    ).all():
        raise ValueError(
            "Manufacturing causal panel contains "
            "non-finite values after preprocessing."
        )

    # Keep metadata only for surviving causal variables.
    metadata = {
        column: metadata[
            column
        ]
        for column in panel.columns
        if column in metadata
    }

    logger.info(
        "Built Mahindra manufacturing panel: "
        "%d rows x %d variables; "
        "%d dropped; %d log-transformed",
        len(panel),
        len(panel.columns),
        len(dropped_metrics),
        len(transformed_metrics),
    )

    return ManufacturingPanelResult(
        panel=panel,
        metadata=metadata,
        dropped_metrics=dropped_metrics,
        transformed_metrics=transformed_metrics,
        missing_intervals=missing_intervals,
        duplicate_records_removed=(
            duplicate_records_removed
        ),
        raw_records=raw_record_count,
        differenced_metrics=differenced_columns,
    )
