"""Five-minute analytical panels for one vehicle at a time."""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller, kpss

from app.ai.causal.telematics_loader import (
    TELEMATICS_CONTEXT_FIELDS,
    TELEMATICS_METRICS,
)


@dataclass(frozen=True)
class TelematicsPanelConfig:
    """Cleaning/resampling contract for one independent vehicle panel."""

    analysis_frequency: str = "5min"
    min_panel_observations: int = 288
    min_data_coverage: float = 0.90
    ffill_limit: int = 1
    min_row_completeness: float = 0.80
    min_variance: float = 1e-12
    relative_std_threshold: float = 1e-7
    max_dominant_value_fraction: float = 0.995
    skew_transform_enabled: bool = False
    skew_threshold: float = 2.0
    # Drop one column of any pair whose absolute correlation exceeds this
    # threshold. Defensive against LPCMCI's larger conditioning sets
    # behaving pathologically on near-duplicate columns.
    collinearity_threshold: float = 0.999
    # Z-score normalize surviving columns. See ManufacturingPanelConfig for
    # rationale (LPCMCI conditions on larger, more varied variable sets than
    # PCMCI).
    normalize_data: bool = True
    # ADF/KPSS stationarity checking and differencing. See
    # ManufacturingPanelConfig for rationale; enabled by default to match
    # the reference pipeline, backed by a real statsmodels dependency.
    stationarity_differencing_enabled: bool = True
    stationarity_alpha: float = 0.05
    min_stationarity_observations: int = 10
    max_variables: int = 24


DEFAULT_TELEMATICS_PANEL_CONFIG = TelematicsPanelConfig()


# Continuous signals are averaged over a five-minute bucket.  Impacts are
# maxima because averaging would erase the event amplitude that carries the
# physical meaning of the signal.
TELEMATICS_METRIC_AGGREGATIONS: dict[str, str] = dict.fromkeys(TELEMATICS_METRICS, "mean")
TELEMATICS_METRIC_AGGREGATIONS["impact_g_force"] = "max"


@dataclass
class TelematicsPanelResult:
    panel: pd.DataFrame
    metadata: dict[str, dict[str, Any]]
    dropped_metrics: dict[str, str]
    transformed_metrics: list[str]
    missing_intervals: dict[str, int] = field(default_factory=dict)
    duplicate_records_removed: int = 0
    raw_records: int = 0
    raw_rows: int = 0
    vehicle_id: str | None = None
    # See ManufacturingPanelResult.differenced_metrics for rationale.
    differenced_metrics: list[str] = field(default_factory=list)


def _dominant_value_fraction(series: pd.Series) -> float:
    values = series.dropna()
    if values.empty:
        return 1.0
    return float(values.value_counts().iloc[0] / len(values))


def _is_near_constant(series: pd.Series, config: TelematicsPanelConfig) -> bool:
    finite = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    if finite.size < 2:
        return True
    variance = float(np.var(finite, ddof=1))
    if not np.isfinite(variance) or variance <= config.min_variance:
        return True
    mean_abs = max(abs(float(np.mean(finite))), 1.0)
    return float(np.std(finite, ddof=1) / mean_abs) <= config.relative_std_threshold


def _metadata_for(dataframe: pd.DataFrame) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for column in sorted(dataframe["column"].unique()):
        subset = dataframe[dataframe["column"] == column]
        first = subset.iloc[0]
        metric = str(first["metric"])
        metadata[column] = {
            "entity": str(first["entity"]),
            "vehicle_id": str(first["entity"]),
            "metric": metric,
            "aggregation": TELEMATICS_METRIC_AGGREGATIONS[metric],
            "role": "vehicle_telemetry_physical_signal",
            **{field: first.get(field) for field in TELEMATICS_CONTEXT_FIELDS if field != "vehicle_id"},
        }
    return metadata


def build_telematics_panel(
    records: Sequence[dict[str, Any]],
    config: TelematicsPanelConfig = DEFAULT_TELEMATICS_PANEL_CONFIG,
) -> TelematicsPanelResult:
    """Build a regular panel for exactly one vehicle.

    Vehicle boundaries are a hard contract: callers must provide one vehicle
    per panel, so no cross-vehicle concatenation can enter PCMCI.
    """

    if not records:
        return TelematicsPanelResult(pd.DataFrame(), {}, {}, [], raw_records=0)
    required = {"timestamp", "entity", "metric", "value"}
    for index, record in enumerate(records):
        missing = required - set(record)
        if missing:
            raise ValueError(f"Telematics record {index} missing fields: {sorted(missing)}")

    dataframe = pd.DataFrame(records).copy()
    raw_record_count = len(dataframe)
    dataframe["timestamp"] = pd.to_datetime(dataframe["timestamp"], utc=True, errors="coerce")
    dataframe["entity"] = dataframe["entity"].astype(str).str.strip()
    dataframe["metric"] = dataframe["metric"].astype(str).str.strip()
    entities = tuple(sorted(value for value in dataframe["entity"].unique() if value))
    if len(entities) != 1:
        raise ValueError("A telematics panel must contain exactly one vehicle.")
    vehicle_id = entities[0]
    dropped: dict[str, str] = {}

    unsupported = dataframe[~dataframe["metric"].isin(TELEMATICS_METRICS)]
    for metric in sorted(unsupported["metric"].dropna().unique()):
        dropped[f"{vehicle_id}||{metric}"] = "not_a_telematics_physical_signal"
    dataframe = dataframe[dataframe["metric"].isin(TELEMATICS_METRICS)]
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")
    dataframe = dataframe.dropna(subset=["timestamp", "value"])
    dataframe = dataframe[np.isfinite(dataframe["value"])]
    before = len(dataframe)
    dataframe = dataframe.drop_duplicates(subset=["timestamp", "entity", "metric"], keep="last")
    duplicate_count = before - len(dataframe)
    if dataframe.empty:
        return TelematicsPanelResult(
            pd.DataFrame(),
            {},
            dropped,
            [],
            duplicate_records_removed=duplicate_count,
            raw_records=raw_record_count,
            raw_rows=0,
            vehicle_id=vehicle_id,
        )

    dataframe["column"] = dataframe["entity"] + "||" + dataframe["metric"]
    metadata = _metadata_for(dataframe)
    origin = dataframe["timestamp"].min()
    series: list[pd.Series] = []
    for column in sorted(dataframe["column"].unique()):
        subset = dataframe[dataframe["column"] == column].sort_values("timestamp")
        metric = str(subset["metric"].iloc[0])
        resampler = subset.set_index("timestamp")["value"].resample(
            config.analysis_frequency,
            origin=origin,
        )
        values = resampler.max() if TELEMATICS_METRIC_AGGREGATIONS[metric] == "max" else resampler.mean()
        values.name = column
        series.append(values)
    panel = pd.concat(series, axis=1).sort_index()
    missing_intervals = {str(column): int(panel[column].isna().sum()) for column in panel.columns}

    if len(panel) < config.min_panel_observations:
        raise ValueError(
            f"Telematics panel for {vehicle_id} has {len(panel)} analytical rows; "
            f"minimum is {config.min_panel_observations}."
        )

    minimum_observations = int(np.ceil(len(panel) * config.min_data_coverage))
    keep: list[str] = []
    for column in panel.columns:
        available = int(panel[column].notna().sum())
        if available >= minimum_observations:
            keep.append(column)
        else:
            dropped[column] = f"insufficient_coverage:{available}/{len(panel)}"
    panel = panel[keep]
    if panel.empty:
        return TelematicsPanelResult(
            panel,
            {},
            dropped,
            [],
            missing_intervals,
            duplicate_count,
            raw_record_count,
            len(dataframe[["timestamp", "entity"]].drop_duplicates()),
            vehicle_id,
        )

    if config.ffill_limit > 0:
        panel = panel.ffill(limit=config.ffill_limit)
    minimum_valid_columns = max(1, int(np.ceil(len(panel.columns) * config.min_row_completeness)))
    panel = panel.dropna(thresh=minimum_valid_columns)

    complete: list[str] = []
    for column in panel.columns:
        missing = int(panel[column].isna().sum())
        if missing == 0:
            complete.append(column)
        else:
            dropped[column] = f"unresolved_missing_values:{missing}"
    panel = panel[complete]

    # Preprocessing order below matches the reference LPCMCI pipeline:
    # missing-data filter -> gap handling (above) -> skew -> variance filter
    # -> normalize -> stationarity -> collinearity removal -> variable cap.

    transformed: list[str] = []
    if config.skew_transform_enabled:
        for column in panel.columns:
            values = panel[column]
            if values.min() < 0:
                continue
            skew = float(values.skew())
            if np.isfinite(skew) and abs(skew) > config.skew_threshold:
                panel[column] = np.log1p(values)
                transformed.append(column)

    informative: list[str] = []
    for column in panel.columns:
        dominant = _dominant_value_fraction(panel[column])
        if dominant >= config.max_dominant_value_fraction:
            dropped[column] = f"low_information_dominant_value:{int(round(dominant * len(panel)))}/{len(panel)}"
        elif not _is_near_constant(panel[column], config):
            informative.append(column)
        else:
            dropped[column] = "constant_or_near_constant"
    panel = panel[informative]

    # Captured BEFORE optional normalization: once z-scored, every surviving
    # column has variance ~= 1, which would make a post-normalization
    # variance-based budget selection arbitrary/meaningless.
    pre_normalization_variances = panel.var()

    if config.normalize_data and len(panel.columns) > 0:
        panel = (panel - panel.mean()) / (panel.std() + 1e-8)

    # Stationarity: ADF/KPSS checking and differencing. See
    # manufacturing_panel.build_manufacturing_panel for the full rationale;
    # identical logic here.
    differenced_columns: list[str] = []
    if (
        config.stationarity_differencing_enabled
        and len(panel) >= config.min_stationarity_observations
        and len(panel.columns) > 0
    ):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            for column in panel.columns:
                series = panel[column].dropna()
                if len(series) < config.min_stationarity_observations:
                    continue
                try:
                    adf_p_value = adfuller(series, autolag="AIC")[1]
                    kpss_p_value = kpss(series, regression="c", nlags="auto")[1]
                except Exception:
                    continue
                if adf_p_value >= config.stationarity_alpha or kpss_p_value < config.stationarity_alpha:
                    panel[column] = panel[column].diff()
                    differenced_columns.append(column)
        if differenced_columns:
            panel = panel.bfill().fillna(0.0)

    # Collinearity removal: near-duplicate columns can make LPCMCI's larger
    # conditioning sets behave pathologically. Deterministic alphabetical
    # tie-break keeps dropped-metric reasoning reproducible.
    if len(panel.columns) > 1:
        correlation = panel.corr().abs()
        collinear_drop: list[str] = []
        ordered_columns = sorted(panel.columns)
        for later_index, later_column in enumerate(ordered_columns):
            if later_column in collinear_drop:
                continue
            for earlier_column in ordered_columns[:later_index]:
                if earlier_column in collinear_drop:
                    continue
                if correlation.loc[earlier_column, later_column] > config.collinearity_threshold:
                    collinear_drop.append(later_column)
                    dropped[later_column] = f"collinear_with:{earlier_column}"
                    break
        if collinear_drop:
            panel = panel.drop(columns=collinear_drop)

    if len(panel.columns) > config.max_variables:
        selected = (
            pre_normalization_variances.reindex(sorted(panel.columns))
            .sort_values(ascending=False, kind="stable")
            .head(config.max_variables)
            .index.tolist()
        )
        for column in panel.columns:
            if column not in selected:
                dropped[column] = "variable_budget"
        panel = panel[selected]

    matrix = panel.to_numpy(dtype=float)
    if not panel.empty and not np.isfinite(matrix).all():
        raise ValueError("Telematics panel contains non-finite values after preprocessing.")
    metadata = {column: metadata[column] for column in panel.columns}
    raw_rows = int(dataframe[["timestamp", "entity"]].drop_duplicates().shape[0])
    return TelematicsPanelResult(
        panel.astype(float),
        metadata,
        dropped,
        transformed,
        missing_intervals,
        duplicate_count,
        raw_record_count,
        raw_rows,
        vehicle_id,
        differenced_columns,
    )


__all__ = [
    "DEFAULT_TELEMATICS_PANEL_CONFIG",
    "TELEMATICS_METRIC_AGGREGATIONS",
    "TelematicsPanelConfig",
    "TelematicsPanelResult",
    "build_telematics_panel",
]
