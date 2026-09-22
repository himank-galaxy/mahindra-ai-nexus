"""
Shared preprocessing pipeline for the Causal Discovery Service.

Applied identically to both domains (manufacturing, telematics), per
IMPLEMENTATION_PLAN.md section 8:

    pivot -> resample -> reindex -> interpolate small gaps ->
    drop near-constant columns -> standardize -> stationarity check

This module has no imports from backend/ or Live_Data_Formation/.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller


def pivot_to_wide(
    long_df: pd.DataFrame,
    entity_column: str,
    numeric_columns: tuple[str, ...],
    boolean_columns: tuple[str, ...] = (),
) -> pd.DataFrame:
    """
    Convert long-format rows (one row per entity per timestamp) into a wide
    panel: index = timestamp, columns = "<entity_id>||<metric>".

    boolean_columns are cast to 0/1 integers before pivoting (e.g.
    telematics' warning_flag).
    """

    frame = long_df.copy()

    for column in boolean_columns:
        if column in frame.columns:
            frame[column] = frame[column].astype("boolean").astype("Int64")

    value_columns = [
        column for column in numeric_columns if column in frame.columns
    ]

    wide = frame.pivot_table(
        index="timestamp",
        columns=entity_column,
        values=value_columns,
        aggfunc="mean",
    )

    # wide.columns is a MultiIndex (metric, entity_id); flatten to
    # "entity_id||metric" per the plan's naming convention.
    wide.columns = [
        f"{entity_id}||{metric}" for metric, entity_id in wide.columns
    ]

    wide = wide.sort_index()

    return wide


def resample_and_reindex(
    wide: pd.DataFrame, resample_minutes: int
) -> pd.DataFrame:
    """
    Resample every column to fixed bins (mean aggregation), then reindex
    onto one complete, regular time axis spanning the observed range so
    every column shares the exact same time steps.
    """

    freq = f"{resample_minutes}min"
    resampled = wide.resample(freq).mean()

    if resampled.empty:
        return resampled

    full_index = pd.date_range(
        start=resampled.index.min(),
        end=resampled.index.max(),
        freq=freq,
    )
    return resampled.reindex(full_index)


def interpolate_small_gaps(
    panel: pd.DataFrame, max_gap_bins: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Linearly interpolate runs of at most `max_gap_bins` consecutive missing
    values, restricted to gaps strictly inside the observed range (no
    extrapolation at the edges). Larger gaps are left as NaN.

    Returns (interpolated_panel, missing_mask) where missing_mask is a
    boolean DataFrame, same shape, True wherever a value is still missing
    after interpolation.
    """

    interpolated = panel.interpolate(
        method="linear",
        limit=max_gap_bins,
        limit_area="inside",
    )

    missing_mask = interpolated.isna()

    return interpolated, missing_mask


def drop_near_constant_columns(
    panel: pd.DataFrame,
    std_threshold: float,
    protected_columns: tuple[str, ...] = (),
) -> tuple[pd.DataFrame, list[str]]:
    """
    Drop any column whose standard deviation (over non-missing values) is
    below std_threshold - it carries no information a lagged-correlation
    test could use.

    protected_columns (optional, default none - existing callers are
    unaffected) are never dropped by this filter even if they look
    near-constant. Used by Predictive_Early_Warning_Service so a warning's
    target metric can never disappear from its own investigation panel.
    """

    stds = panel.std(skipna=True)
    dropped = [
        column
        for column in stds[stds.fillna(0.0) < std_threshold].index.tolist()
        if column not in protected_columns
    ]

    kept = panel.drop(columns=dropped)

    return kept, dropped


def standardize(panel: pd.DataFrame) -> pd.DataFrame:
    """
    Z-score every column (mean 0, std 1) over its own non-missing values,
    so no metric's raw magnitude dominates ParCorr/LPCMCI purely by scale.
    """

    means = panel.mean(skipna=True)
    stds = panel.std(skipna=True)

    # Any column reaching here already passed the near-constant filter, so
    # stds should be well away from zero; guard anyway to avoid division
    # by zero on a pathological single-non-null-value column.
    safe_stds = stds.replace(0.0, np.nan)

    return (panel - means) / safe_stds


def check_stationarity(
    panel: pd.DataFrame, pvalue_threshold: float
) -> list[str]:
    """
    Run an Augmented Dickey-Fuller test per column. Columns that fail to
    reject a unit root (ADF p-value > pvalue_threshold) are returned as
    "possibly non-stationary" - logged for human review, never
    auto-corrected here (see IMPLEMENTATION_PLAN.md section 8, step 9).
    """

    warnings: list[str] = []

    for column in panel.columns:
        series = panel[column].dropna()

        # ADF requires a reasonable number of observations; skip columns
        # too short to test meaningfully rather than raising.
        if len(series) < 20:
            continue

        try:
            _, p_value, *_ = adfuller(
                series, autolag="AIC", result_object=False
            )
        except Exception:
            # A column that fails the ADF test outright (e.g. exactly
            # constant after all) is not actionable here; skip it.
            continue

        if p_value > pvalue_threshold:
            warnings.append(column)

    return warnings


@dataclass
class PreprocessResult:
    panel: pd.DataFrame
    missing_mask: pd.DataFrame
    columns_dropped_near_constant: list[str] = field(default_factory=list)
    columns_with_stationarity_warning: list[str] = field(
        default_factory=list
    )
    missing_data_pct_after_interpolation: float = 0.0


def preprocess_panel(
    long_df: pd.DataFrame,
    entity_column: str,
    numeric_columns: tuple[str, ...],
    boolean_columns: tuple[str, ...],
    resample_minutes: int,
    max_gap_bins: int,
    near_constant_std_threshold: float,
    stationarity_pvalue_threshold: float,
    protected_columns: tuple[str, ...] = (),
) -> PreprocessResult:
    """
    Run the full preprocessing pipeline end-to-end and return the final
    panel plus the diagnostics needed for run_metadata.json.

    protected_columns: optional, defaults to none (existing callers -
    run_manufacturing_causal_discovery.py, run_telematics_causal_discovery.py,
    test_ui - are unaffected). See drop_near_constant_columns().
    """

    wide = pivot_to_wide(
        long_df, entity_column, numeric_columns, boolean_columns
    )

    resampled = resample_and_reindex(wide, resample_minutes)

    interpolated, missing_mask = interpolate_small_gaps(
        resampled, max_gap_bins
    )

    filtered, dropped_columns = drop_near_constant_columns(
        interpolated, near_constant_std_threshold, protected_columns
    )
    missing_mask = missing_mask[filtered.columns]

    standardized = standardize(filtered)

    stationarity_warnings = check_stationarity(
        standardized, stationarity_pvalue_threshold
    )

    total_cells = standardized.shape[0] * max(standardized.shape[1], 1)
    missing_pct = (
        float(missing_mask.to_numpy().sum()) / total_cells * 100.0
        if total_cells
        else 0.0
    )

    return PreprocessResult(
        panel=standardized,
        missing_mask=missing_mask,
        columns_dropped_near_constant=dropped_columns,
        columns_with_stationarity_warning=stationarity_warnings,
        missing_data_pct_after_interpolation=round(missing_pct, 2),
    )
