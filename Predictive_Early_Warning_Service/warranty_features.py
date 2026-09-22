"""
Feature engineering for the Warranty Predictive Service.

Shared by training_data.py and predict.py, the same "one function, used
by both training and serving" convention as
Predictive_Early_Warning_Service/features.py, to avoid train/serve skew.

KNOWN, DOCUMENTED GAP: telematics-derived features are only available
for the small 24-vehicle telematics cohort (confirmed earlier this
session - vehicle_telematics_timeseries.csv covers 24 vehicles, each for
just their first 7 days post-delivery). For every other vehicle, the
telematics-derived columns below are filled with 0.0 and
has_telematics_coverage=False, rather than silently dropped or
fabricated - callers/consumers of these features must treat a 0.0 here
as "no data," not "measured zero."
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

VEHICLE_MODEL_NAMES: tuple[str, ...] = ("XUV700", "Scorpio-N", "Thar", "Bolero", "XUV 3XO")

FEATURE_COLUMNS: tuple[str, ...] = (
    "production_quality_score",
    "supplier_lot_quality_score",
    "vehicle_age_at_checkpoint_days",
    "had_first_inspection",
    "first_inspection_service_score",
    "prior_issue_count_total",
    "prior_issue_count_in_cluster",
    "has_telematics_coverage",
    "telematics_max_impact_g_force",
    "telematics_min_vehicle_speed_kph",
    "telematics_warning_flag_rate",
) + tuple(f"model_{name.replace(' ', '_').replace('-', '_')}" for name in VEHICLE_MODEL_NAMES)


@dataclass(frozen=True)
class Checkpoint:
    vehicle_id: str
    checkpoint_at: pd.Timestamp
    delivery_at: pd.Timestamp
    vehicle_model_name: str
    production_quality_score: float
    supplier_lot_quality_score: float
    had_first_inspection: bool
    first_inspection_service_score: float | None


def compute_features(
    checkpoint: Checkpoint,
    prior_service_events: pd.DataFrame,
    cluster_issue_categories: tuple[str, ...],
    telematics_window: pd.DataFrame | None,
) -> dict[str, float]:
    """
    prior_service_events: this vehicle's service_events rows with
    service_started_at <= checkpoint.checkpoint_at (already filtered by
    the caller - see training_data.py/predict.py for why the cutoff must
    be enforced there, not here, to keep this function a pure
    transformation).
    telematics_window: this vehicle's telematics rows up to the
    checkpoint, or None if this vehicle has no telematics coverage.
    """

    age_days = max(0.0, (checkpoint.checkpoint_at - checkpoint.delivery_at).total_seconds() / 86400.0)

    repairs = prior_service_events[prior_service_events["service_type"] == "UNSCHEDULED_REPAIR"]
    prior_issue_count_total = int(len(repairs))
    prior_issue_count_in_cluster = int(repairs["issue_category"].isin(cluster_issue_categories).sum())

    features: dict[str, float] = {
        "production_quality_score": float(checkpoint.production_quality_score),
        "supplier_lot_quality_score": float(checkpoint.supplier_lot_quality_score),
        "vehicle_age_at_checkpoint_days": age_days,
        "had_first_inspection": float(checkpoint.had_first_inspection),
        "first_inspection_service_score": float(checkpoint.first_inspection_service_score or 0.0),
        "prior_issue_count_total": float(prior_issue_count_total),
        "prior_issue_count_in_cluster": float(prior_issue_count_in_cluster),
    }

    if telematics_window is not None and not telematics_window.empty:
        features["has_telematics_coverage"] = 1.0
        features["telematics_max_impact_g_force"] = float(telematics_window["impact_g_force"].max())
        features["telematics_min_vehicle_speed_kph"] = float(telematics_window["vehicle_speed_kph"].min())
        features["telematics_warning_flag_rate"] = float(telematics_window["warning_flag"].astype(bool).mean())
    else:
        features["has_telematics_coverage"] = 0.0
        features["telematics_max_impact_g_force"] = 0.0
        features["telematics_min_vehicle_speed_kph"] = 0.0
        features["telematics_warning_flag_rate"] = 0.0

    for name in VEHICLE_MODEL_NAMES:
        column = f"model_{name.replace(' ', '_').replace('-', '_')}"
        features[column] = 1.0 if checkpoint.vehicle_model_name == name else 0.0

    return features


def features_to_row(features: dict[str, float]) -> list[float]:
    """Orders a features dict into FEATURE_COLUMNS order - the exact
    column order the model was fit on must be reproduced at predict
    time, the same discipline PEWS's joblib bundle enforces."""
    return [features[column] for column in FEATURE_COLUMNS]
