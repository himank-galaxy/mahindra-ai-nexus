"""
Feature computation.

This ONE function is called both by training_data.py (to build the
historical training set) and scheduler.py (to score a vehicle live). Using
the same function in both places is deliberate - if training and live
scoring computed features differently, the model would be scored on data
that doesn't match what it learned from ("train/serve skew").

exclude_metrics matters for genuine early-warning behavior: a model that
gets to see "is the target metric already near the threshold" as an input
feature mostly just detects the CURRENT state rather than forecasting it
ahead of time. Every caller building a feature vector to predict a
specific warning type's target metric should pass that same metric in
exclude_metrics, so the model has to infer risk from OTHER precursor
signals instead of a shortcut.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pews_config import FEATURE_METRICS


def compute_features(
    window_rows: pd.DataFrame, exclude_metrics: tuple[str, ...] = ()
) -> dict[str, float] | None:
    """
    Given raw telemetry rows for one vehicle within one time window (any
    length), compute a fixed-size feature vector: for each metric in
    FEATURE_METRICS (minus exclude_metrics), its mean, min, max, and trend
    (last observed value minus first observed value, in chronological
    order).

    Returns None if there isn't enough data in the window to compute
    meaningful features (fewer than 3 rows).
    """

    if window_rows is None or len(window_rows) < 3:
        return None

    ordered = window_rows.sort_values("timestamp")

    features: dict[str, float] = {}

    for metric in FEATURE_METRICS:
        if metric in exclude_metrics or metric not in ordered.columns:
            continue

        series = ordered[metric].dropna()

        if series.empty:
            features[f"{metric}__mean"] = np.nan
            features[f"{metric}__min"] = np.nan
            features[f"{metric}__max"] = np.nan
            features[f"{metric}__trend"] = np.nan
            continue

        features[f"{metric}__mean"] = float(series.mean())
        features[f"{metric}__min"] = float(series.min())
        features[f"{metric}__max"] = float(series.max())
        features[f"{metric}__trend"] = float(series.iloc[-1] - series.iloc[0])

    return features


def feature_names(exclude_metrics: tuple[str, ...] = ()) -> list[str]:
    """
    The fixed, ordered list of feature column names compute_features()
    produces for the given exclusion set - used to build the training
    matrix in a stable column order. Must be called with the SAME
    exclude_metrics used when computing the features, both at training
    time and at live-scoring time.
    """

    names: list[str] = []
    for metric in FEATURE_METRICS:
        if metric in exclude_metrics:
            continue
        names.extend(
            [f"{metric}__mean", f"{metric}__min", f"{metric}__max", f"{metric}__trend"]
        )
    return names
