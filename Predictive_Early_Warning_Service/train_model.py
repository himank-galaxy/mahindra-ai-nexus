"""
Trains one shared multi-label RandomForestClassifier per cluster (BATTERY,
STEERING, SUSPENSION, ...) and saves it under models/ - not one classifier
per warning type. Mirrors warranty_train_model.py's proven multi-label
pattern (sklearn's RandomForestClassifier fit directly on a 2D y, one
column per warning type in the cluster), applied here to live telematics
instead of warranty/service data.

Uses a TIME-based train/test split (train on the earlier checkpoints, test
on the later ones) rather than a random split - a random split would leak
information, since nearby checkpoints for the same vehicle are correlated.

Run manually:
    .venv/bin/python3 train_model.py
"""

from __future__ import annotations

import asyncio
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, precision_score, recall_score

from features import feature_names
from pews_config import MODELS_DIR, WARNING_CLUSTERS
from training_data import build_training_dataset

TEST_FRACTION = 0.2
MIN_TRAINING_ROWS = 50
MIN_POSITIVE_LABELS = 1


def _time_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    ordered = df.sort_values("checkpoint")
    split_index = int(len(ordered) * (1 - TEST_FRACTION))
    return ordered.iloc[:split_index], ordered.iloc[split_index:]


def _train_cluster(cluster: str, warnings: tuple, df: pd.DataFrame) -> dict:
    # Exclude every target metric belonging to this cluster from its own
    # shared feature set - see training_data.py's module docstring for why.
    cluster_target_metrics = tuple(w.target_metric for w in warnings)
    feature_columns = feature_names(exclude_metrics=cluster_target_metrics)
    label_columns = [f"label__{w.warning_type}" for w in warnings]
    warning_types = [w.warning_type for w in warnings]

    df = df.dropna(subset=feature_columns)

    if len(df) < MIN_TRAINING_ROWS:
        return {"cluster": cluster, "status": "SKIPPED_INSUFFICIENT_DATA", "rows_available": len(df)}

    total_positives = int(df[label_columns].sum().sum())
    if total_positives < MIN_POSITIVE_LABELS:
        return {"cluster": cluster, "status": "SKIPPED_NO_POSITIVE_LABELS", "rows_available": len(df)}

    train_df, test_df = _time_split(df)

    # Fit on the DataFrame slice (not .to_numpy()) so the model retains
    # feature names - scheduler.py scores it with a named DataFrame too
    # (feature_row), and a numpy/DataFrame mismatch here just produces a
    # harmless but noisy sklearn UserWarning on every single scoring call.
    X_train = train_df[feature_columns]
    y_train = train_df[label_columns].to_numpy()
    X_test = test_df[feature_columns]
    y_test = test_df[label_columns].to_numpy()

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=6,
        min_samples_leaf=5,
        class_weight="balanced",
        random_state=42,
    )
    model.fit(X_train, y_train)

    metrics: dict[str, dict[str, float] | None] = {}
    if len(test_df) > 0:
        y_pred = model.predict(X_test)
        # sklearn silently squeezes a single-column y (one warning type in
        # this cluster) down to a 1D fit/predict, same as a plain binary
        # classifier - normalize back to 2D so the indexing below is
        # uniform regardless of cluster size.
        if y_pred.ndim == 1:
            y_pred = y_pred.reshape(-1, 1)
        for column_index, warning_type in enumerate(warning_types):
            y_true_col = y_test[:, column_index]
            y_pred_col = y_pred[:, column_index]
            if len(set(y_true_col)) < 2:
                metrics[warning_type] = None
                continue
            metrics[warning_type] = {
                "precision": round(float(precision_score(y_true_col, y_pred_col, zero_division=0)), 3),
                "recall": round(float(recall_score(y_true_col, y_pred_col, zero_division=0)), 3),
                "f1": round(float(f1_score(y_true_col, y_pred_col, zero_division=0)), 3),
            }

    os.makedirs(MODELS_DIR, exist_ok=True)
    model_path = os.path.join(MODELS_DIR, f"{cluster}.joblib")
    joblib.dump(
        {
            "model": model,
            "feature_columns": feature_columns,
            "warning_types": warning_types,
            "cluster": cluster,
        },
        model_path,
    )

    valid_metrics = [m for m in metrics.values() if m is not None]
    macro = (
        {k: round(float(np.mean([m[k] for m in valid_metrics])), 3) for k in ("precision", "recall", "f1")}
        if valid_metrics
        else None
    )

    return {
        "cluster": cluster,
        "status": "TRAINED",
        "rows_train": len(train_df),
        "rows_test": len(test_df),
        "total_positive_labels": total_positives,
        "metrics": metrics,
        "macro": macro,
        "model_path": model_path,
    }


async def main() -> None:
    print("Building training dataset from live telemetry...")
    datasets = await build_training_dataset(max_vehicles=300)

    trained = 0
    for cluster, warnings in WARNING_CLUSTERS.items():
        result = _train_cluster(cluster, warnings, datasets[cluster])
        print(f"\n{cluster}: {result['status']}")
        for key, value in result.items():
            if key in ("cluster", "status"):
                continue
            print(f"  {key}: {value}")
        if result["status"] == "TRAINED":
            trained += 1

    print(f"\nTrained {trained} of {len(WARNING_CLUSTERS)} clusters.")


if __name__ == "__main__":
    asyncio.run(main())
