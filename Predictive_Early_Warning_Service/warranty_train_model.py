"""
Trains one real multi-label RandomForestClassifier per
supplier_component_category cluster (see
docs/Implementation_plan_warranty_predictive_service.md Part B for why
this must be one shared multi-label model per cluster, not one binary
classifier per issue relabeled as a "cluster").

Mirrors Predictive_Early_Warning_Service/train_model.py's conventions:
time-based train/test split (not random - avoids leakage from nearby
checkpoints), skip-and-log rather than crash on insufficient data,
joblib persistence bundling the model with its exact feature-column and
issue-column order.

Usage:
    Causal_Discovery_Service/.venv/bin/python3 train_model.py
"""

from __future__ import annotations

import os

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, precision_score, recall_score

import warranty_config
from warranty_features import FEATURE_COLUMNS, features_to_row
from warranty_training_data import ClusterDataset, build_training_data


def _time_based_split(dataset: ClusterDataset) -> tuple[list[int], list[int]]:
    order = sorted(range(len(dataset.checkpoint_at)), key=lambda i: dataset.checkpoint_at[i])
    split_point = int(len(order) * (1 - warranty_config.TEST_FRACTION))
    return order[:split_point], order[split_point:]


def _to_matrix(dataset: ClusterDataset, indices: list[int]) -> tuple[np.ndarray, np.ndarray]:
    X = np.array([features_to_row(dataset.feature_rows[i]) for i in indices])
    y = np.array(
        [[dataset.label_rows[i][issue] for issue in dataset.issue_categories] for i in indices]
    )
    return X, y


def train_cluster(component_category: str, dataset: ClusterDataset) -> dict | None:
    total_positives = sum(sum(labels.values()) for labels in dataset.label_rows)

    if len(dataset.feature_rows) < warranty_config.MIN_TRAINING_ROWS:
        print(f"SKIP {component_category}: only {len(dataset.feature_rows)} rows (< {warranty_config.MIN_TRAINING_ROWS})")
        return None
    if total_positives < warranty_config.MIN_POSITIVE_LABELS:
        print(f"SKIP {component_category}: 0 positive examples across all issue categories - nothing to learn")
        return None

    train_idx, test_idx = _time_based_split(dataset)
    X_train, y_train = _to_matrix(dataset, train_idx)
    X_test, y_test = _to_matrix(dataset, test_idx)

    model = RandomForestClassifier(
        n_estimators=warranty_config.N_ESTIMATORS,
        max_depth=warranty_config.MAX_DEPTH,
        min_samples_leaf=warranty_config.MIN_SAMPLES_LEAF,
        class_weight="balanced",
        random_state=warranty_config.RANDOM_STATE,
    )
    model.fit(X_train, y_train)

    metrics: dict[str, dict[str, float] | None] = {}
    if len(test_idx) > 0:
        y_pred = model.predict(X_test)
        for column_index, issue in enumerate(dataset.issue_categories):
            y_true_col = y_test[:, column_index]
            y_pred_col = y_pred[:, column_index]
            if len(set(y_true_col)) < 2:
                metrics[issue] = None  # test split has only one class - metric would be meaningless
                continue
            metrics[issue] = {
                "precision": float(precision_score(y_true_col, y_pred_col, zero_division=0)),
                "recall": float(recall_score(y_true_col, y_pred_col, zero_division=0)),
                "f1": float(f1_score(y_true_col, y_pred_col, zero_division=0)),
            }

    bundle = {
        "model": model,
        "feature_columns": FEATURE_COLUMNS,
        "issue_categories": dataset.issue_categories,
        "component_category": component_category,
        "training_rows": len(dataset.feature_rows),
        "total_positive_labels": total_positives,
    }

    os.makedirs(warranty_config.MODELS_DIR, exist_ok=True)
    path = os.path.join(warranty_config.MODELS_DIR, f"{component_category}.joblib")
    joblib.dump(bundle, path)

    valid_metrics = [m for m in metrics.values() if m is not None]
    macro = (
        {k: float(np.mean([m[k] for m in valid_metrics])) for k in ("precision", "recall", "f1")}
        if valid_metrics
        else None
    )

    summary = f"TRAINED {component_category}: rows={len(dataset.feature_rows)} positives={total_positives} test_rows={len(test_idx)}"
    if macro:
        summary += f" macro_f1={macro['f1']:.3f}"
    else:
        summary += " (no usable test metrics - test split single-class)"
    print(summary)

    return {"component_category": component_category, "metrics": metrics, "macro": macro, "path": path}


def train_all() -> list[dict]:
    datasets = build_training_data()
    results = []
    for component_category, dataset in datasets.items():
        result = train_cluster(component_category, dataset)
        if result is not None:
            results.append(result)
    return results


if __name__ == "__main__":
    results = train_all()
    print(f"\nTrained {len(results)} of {len(warranty_config.CLUSTERS)} clusters.")
