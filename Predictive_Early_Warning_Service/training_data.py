"""
Builds a labeled training dataset from historical telemetry already sitting
in vehicle_telematics_timeseries - no manually-labeled data needed.

For each vehicle and a series of past "as of" checkpoints T, this looks at:
    features  = compute_features() over [T - FEATURE_WINDOW_HOURS, T],
                EXCLUDING that warning type's own target metric
    label     = did the warning-type's target metric cross its threshold
                anywhere in [T + LABEL_GAP_HOURS, T + LABEL_GAP_HOURS + LABEL_WINDOW_HOURS]?

Both windows only ever use data that had ALREADY happened by the time they
are computed relative to T - this is what IMPLEMENTATION_PLAN.md's
"avoiding future leakage" rule means in code.

Excluding the target metric from its own features, and requiring the label
window to start LABEL_GAP_HOURS in the future rather than immediately,
are both deliberate: without them, the model mostly learns "is this metric
already near the threshold right now," which produces a near-permanent
current-state flag rather than a genuine forward-looking early warning
(see changes.md for the real correlation numbers that motivated this).

Imports Causal_Discovery_Service's db_reader.py directly (reuse, not
duplication - see IMPLEMENTATION_PLAN.md) rather than writing a second
database connector.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

PREW_ROOT = Path(__file__).resolve().parent
CAUSAL_SERVICE_ROOT = PREW_ROOT.parent / "Causal_Discovery_Service"
if str(CAUSAL_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(CAUSAL_SERVICE_ROOT))

from db_reader import ReadOnlyDatabaseReader  # noqa: E402  (path set above)

from pews_config import (  # noqa: E402
    FEATURE_METRICS,
    FEATURE_WINDOW_HOURS,
    LABEL_GAP_HOURS,
    LABEL_WINDOW_HOURS,
    WARNING_CLUSTERS,
)
from features import compute_features, feature_names  # noqa: E402

CHECKPOINT_SPACING_HOURS = 6


def _label_for_warning(
    label_rows: pd.DataFrame, target_metric: str, threshold: float, direction: str
) -> int:
    if label_rows.empty or target_metric not in label_rows.columns:
        return 0

    values = label_rows[target_metric].dropna()
    if values.empty:
        return 0

    if direction == "above":
        return int((values > threshold).any())
    return int((values < threshold).any())


async def build_training_dataset(
    max_vehicles: int = 300,
) -> dict[str, pd.DataFrame]:
    """
    Returns {cluster: DataFrame} - each DataFrame has one row per
    (vehicle, checkpoint) with that cluster's SHARED feature columns
    (excluding every target metric belonging to that cluster, so none of
    its own warning types' labels can leak into its own features) plus
    one "label__<warning_type>" column per warning type in the cluster.
    This shape - one shared feature block, multiple label columns - is
    what lets train_model.py fit a single multi-label
    RandomForestClassifier per cluster instead of one model per warning
    type, the same sklearn native multi-output approach already proven
    in warranty_train_model.py.
    """

    reader = ReadOnlyDatabaseReader()
    await reader.connect()

    try:
        latest = await reader.latest_timestamp("vehicle_telematics_timeseries")
        if latest is None:
            raise RuntimeError("vehicle_telematics_timeseries is empty")

        row_counts = await reader.telematics_row_counts(
            latest - timedelta(days=365), latest
        )
        vehicle_ids = [
            vehicle_id
            for vehicle_id, count in sorted(
                row_counts.items(), key=lambda item: item[1], reverse=True
            )
        ][:max_vehicles]

        columns = ("vehicle_id", "timestamp") + tuple(
            m for m in FEATURE_METRICS if m not in ("vehicle_id", "timestamp")
        )

        raw_rows = await reader.telematics_rows(
            vehicle_ids, latest - timedelta(days=365), latest, columns
        )
    finally:
        await reader.close()

    all_df = pd.DataFrame([dict(row) for row in raw_rows], columns=columns)
    if all_df.empty:
        return {cluster: pd.DataFrame() for cluster in WARNING_CLUSTERS}

    all_df["timestamp"] = pd.to_datetime(all_df["timestamp"], utc=True)

    per_cluster_rows: dict[str, list[dict]] = {cluster: [] for cluster in WARNING_CLUSTERS}

    max_lookahead = LABEL_GAP_HOURS + LABEL_WINDOW_HOURS

    for vehicle_id, vehicle_df in all_df.groupby("vehicle_id"):
        vehicle_df = vehicle_df.sort_values("timestamp")

        first_seen = vehicle_df["timestamp"].min()
        last_seen = vehicle_df["timestamp"].max()

        checkpoint = first_seen + timedelta(hours=FEATURE_WINDOW_HOURS)
        while checkpoint + timedelta(hours=max_lookahead) <= last_seen:
            feature_window = vehicle_df[
                (vehicle_df["timestamp"] > checkpoint - timedelta(hours=FEATURE_WINDOW_HOURS))
                & (vehicle_df["timestamp"] <= checkpoint)
            ]
            label_window = vehicle_df[
                (vehicle_df["timestamp"] > checkpoint + timedelta(hours=LABEL_GAP_HOURS))
                & (
                    vehicle_df["timestamp"]
                    <= checkpoint + timedelta(hours=LABEL_GAP_HOURS + LABEL_WINDOW_HOURS)
                )
            ]

            for cluster, warnings in WARNING_CLUSTERS.items():
                cluster_target_metrics = tuple(w.target_metric for w in warnings)
                features = compute_features(
                    feature_window, exclude_metrics=cluster_target_metrics
                )
                if features is None:
                    continue

                labels = {
                    f"label__{warning.warning_type}": _label_for_warning(
                        label_window, warning.target_metric, warning.threshold, warning.direction
                    )
                    for warning in warnings
                }
                per_cluster_rows[cluster].append(
                    {
                        **features,
                        **labels,
                        "vehicle_id": vehicle_id,
                        "checkpoint": checkpoint,
                    }
                )

            checkpoint += timedelta(hours=CHECKPOINT_SPACING_HOURS)

    result: dict[str, pd.DataFrame] = {}
    for cluster, warnings in WARNING_CLUSTERS.items():
        rows = per_cluster_rows[cluster]
        if not rows:
            result[cluster] = pd.DataFrame()
            continue
        cluster_target_metrics = tuple(w.target_metric for w in warnings)
        label_columns = [f"label__{w.warning_type}" for w in warnings]
        result[cluster] = pd.DataFrame(
            rows,
            columns=feature_names(exclude_metrics=cluster_target_metrics)
            + label_columns
            + ["vehicle_id", "checkpoint"],
        )
    return result
