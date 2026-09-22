"""
Scores a vehicle against every trained cluster model, applies the cost
reference and eligibility gate, and returns per-issue expected Mahindra
liability - the same expected cost = P(issue) x cost x is-eligible
formula from docs/data_required_for_warranty_predictive_model.md
section 4.

Feature computation reuses compute_features() from features.py, the same
function training_data.py uses - but evaluated with "now" (the latest
known data point) as the checkpoint, using everything known about the
vehicle to date, rather than the fixed early-life checkpoint training
used for labeling. This is standard for a live-scoring pipeline (PEWS's
own scheduler.py does the same: train on any qualifying historical
window, score live using the current window) - the feature *function* is
identical either way, only the checkpoint moment differs.

All CSVs/models/cost-reference are loaded ONCE into a PredictionContext,
not per vehicle - rank.py scores the whole fleet through the same
context, so it doesn't re-read every CSV and reload every model ~1,300
times.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass

import joblib
import pandas as pd

import warranty_config
from cost_reference import CostEstimate, build_cost_reference
from eligibility import EligibilityResult, check_eligibility
from warranty_features import Checkpoint, compute_features, features_to_row


@dataclass(frozen=True)
class IssuePrediction:
    issue_category: str
    component_category: str
    probability: float
    cost: CostEstimate
    eligibility: EligibilityResult
    expected_liability_inr: float
    low_confidence: bool  # True if this cluster trained on very few positive examples - see warranty_config.py


@dataclass
class PredictionContext:
    deliveries: pd.DataFrame
    service_events: pd.DataFrame
    telematics: pd.DataFrame | None
    models: dict[str, dict]
    cost_reference: dict[str, CostEstimate]
    now: pd.Timestamp


def load_prediction_context() -> PredictionContext:
    deliveries = pd.read_csv(warranty_config.DELIVERIES_PATH)
    deliveries["actual_delivery_date"] = pd.to_datetime(deliveries["actual_delivery_date"])

    service_events = pd.read_csv(warranty_config.SERVICE_EVENTS_PATH)
    service_events["service_started_at"] = pd.to_datetime(service_events["service_started_at"])

    try:
        telematics = pd.read_csv(warranty_config.TELEMATICS_PATH)
        telematics["timestamp"] = pd.to_datetime(telematics["timestamp"])
    except FileNotFoundError:
        telematics = None

    models: dict[str, dict] = {}
    for path in glob.glob(os.path.join(warranty_config.MODELS_DIR, "*.joblib")):
        bundle = joblib.load(path)
        models[bundle["component_category"]] = bundle

    now = (
        pd.Timestamp(service_events["service_started_at"].max())
        if not service_events.empty
        else pd.Timestamp.now(tz="Asia/Kolkata")
    )

    return PredictionContext(
        deliveries=deliveries,
        service_events=service_events,
        telematics=telematics,
        models=models,
        cost_reference=build_cost_reference(),
        now=now,
    )


def _build_current_checkpoint(vehicle_id: str, delivery_row: pd.Series, vehicle_events: pd.DataFrame, now: pd.Timestamp) -> Checkpoint:
    first_inspections = vehicle_events[vehicle_events["service_type"] == "FIRST_INSPECTION"]
    had_first_inspection = not first_inspections.empty
    first_inspection_service_score = float(first_inspections.iloc[0]["service_score"]) if had_first_inspection else None

    return Checkpoint(
        vehicle_id=vehicle_id,
        checkpoint_at=now,
        delivery_at=pd.Timestamp(delivery_row["actual_delivery_date"]),
        vehicle_model_name=str(delivery_row["vehicle_model_name"]),
        production_quality_score=float(delivery_row["production_quality_score"]),
        supplier_lot_quality_score=float(delivery_row["supplier_lot_quality_score"]),
        had_first_inspection=had_first_inspection,
        first_inspection_service_score=first_inspection_service_score,
    )


def predict_for_vehicle_in_context(vehicle_id: str, context: PredictionContext) -> list[IssuePrediction]:
    delivery_rows = context.deliveries[context.deliveries["vehicle_id"] == vehicle_id]
    if delivery_rows.empty:
        raise ValueError(f"No delivered vehicle found with vehicle_id={vehicle_id!r}")
    delivery_row = delivery_rows.iloc[0]

    vehicle_events = context.service_events[context.service_events["vehicle_id"] == vehicle_id]
    vehicle_telematics = (
        context.telematics[context.telematics["vehicle_id"] == vehicle_id]
        if context.telematics is not None
        else None
    )

    checkpoint = _build_current_checkpoint(vehicle_id, delivery_row, vehicle_events, context.now)
    odometer_km = float(vehicle_events["odometer_km"].max()) if not vehicle_events.empty else None
    vehicle_age_days = max(0.0, (checkpoint.checkpoint_at - checkpoint.delivery_at).total_seconds() / 86400.0)

    predictions: list[IssuePrediction] = []
    for component_category, bundle in context.models.items():
        features = compute_features(checkpoint, vehicle_events, bundle["issue_categories"], vehicle_telematics)
        row = [features_to_row(features)]
        probabilities = bundle["model"].predict_proba(row)

        eligibility = check_eligibility(component_category, vehicle_age_days, odometer_km, vehicle_telematics)
        low_confidence = bundle["total_positive_labels"] < warranty_config.RELIABLE_POSITIVE_LABELS_THRESHOLD

        for issue_index, issue_category in enumerate(bundle["issue_categories"]):
            # predict_proba for a multi-label RandomForestClassifier
            # returns one array per output column, each shaped
            # (n_samples, n_classes) - column 1 is P(label=1) except
            # when that output was single-class at fit time (see
            # train_model.py), in which case there is only one column.
            proba_array = probabilities[issue_index]
            probability = float(proba_array[0][1]) if proba_array.shape[1] > 1 else float(proba_array[0][0])

            cost = context.cost_reference.get(
                issue_category,
                CostEstimate(issue_category=issue_category, typical_cost_inr=0.0, sample_count=0, source="fleet_average"),
            )

            expected_liability = probability * cost.typical_cost_inr * (1.0 if eligibility.is_eligible else 0.0)

            predictions.append(
                IssuePrediction(
                    issue_category=issue_category,
                    component_category=component_category,
                    probability=probability,
                    cost=cost,
                    eligibility=eligibility,
                    expected_liability_inr=expected_liability,
                    low_confidence=low_confidence,
                )
            )

    return sorted(predictions, key=lambda p: p.expected_liability_inr, reverse=True)


def predict_for_fleet_in_context(context: PredictionContext) -> dict[str, list[IssuePrediction]]:
    """
    Scores every delivered vehicle against every cluster model, batched
    per cluster (one predict_proba call per cluster, over every
    vehicle's feature row at once) rather than per (vehicle, cluster)
    pair - ~19 model calls instead of ~1,349 x 19. Use this for
    fleet-wide work (rank.py, scheduler.py); predict_for_vehicle stays
    the simple single-vehicle path for the API/ad-hoc lookups.
    """
    vehicle_ids = context.deliveries["vehicle_id"].astype(str).tolist()

    checkpoints: dict[str, Checkpoint] = {}
    vehicle_events_by_id: dict[str, pd.DataFrame] = {}
    vehicle_telematics_by_id: dict[str, pd.DataFrame | None] = {}
    odometer_by_id: dict[str, float | None] = {}
    age_days_by_id: dict[str, float] = {}

    events_by_vehicle = {
        str(vid): group for vid, group in context.service_events.groupby("vehicle_id")
    }
    telematics_by_vehicle = (
        {str(vid): group for vid, group in context.telematics.groupby("vehicle_id")}
        if context.telematics is not None
        else {}
    )
    delivery_by_vehicle = context.deliveries.set_index(context.deliveries["vehicle_id"].astype(str))

    for vehicle_id in vehicle_ids:
        delivery_row = delivery_by_vehicle.loc[vehicle_id]
        vehicle_events = events_by_vehicle.get(vehicle_id, context.service_events.iloc[0:0])
        vehicle_events_by_id[vehicle_id] = vehicle_events
        vehicle_telematics = telematics_by_vehicle.get(vehicle_id)
        vehicle_telematics_by_id[vehicle_id] = vehicle_telematics

        checkpoint = _build_current_checkpoint(vehicle_id, delivery_row, vehicle_events, context.now)
        checkpoints[vehicle_id] = checkpoint
        odometer_by_id[vehicle_id] = float(vehicle_events["odometer_km"].max()) if not vehicle_events.empty else None
        age_days_by_id[vehicle_id] = max(0.0, (checkpoint.checkpoint_at - checkpoint.delivery_at).total_seconds() / 86400.0)

    results: dict[str, list[IssuePrediction]] = {vehicle_id: [] for vehicle_id in vehicle_ids}

    for component_category, bundle in context.models.items():
        rows = [
            features_to_row(
                compute_features(
                    checkpoints[vehicle_id],
                    vehicle_events_by_id[vehicle_id],
                    bundle["issue_categories"],
                    vehicle_telematics_by_id[vehicle_id],
                )
            )
            for vehicle_id in vehicle_ids
        ]
        probabilities = bundle["model"].predict_proba(rows)
        low_confidence = bundle["total_positive_labels"] < warranty_config.RELIABLE_POSITIVE_LABELS_THRESHOLD

        # Eligibility depends only on (component_category, vehicle age/odometer/telematics) -
        # compute once per vehicle per cluster, not once per issue within the cluster.
        eligibility_by_vehicle = {
            vehicle_id: check_eligibility(
                component_category, age_days_by_id[vehicle_id], odometer_by_id[vehicle_id], vehicle_telematics_by_id[vehicle_id]
            )
            for vehicle_id in vehicle_ids
        }

        for issue_index, issue_category in enumerate(bundle["issue_categories"]):
            proba_array = probabilities[issue_index]
            has_both_classes = proba_array.shape[1] > 1
            cost = context.cost_reference.get(
                issue_category,
                CostEstimate(issue_category=issue_category, typical_cost_inr=0.0, sample_count=0, source="fleet_average"),
            )

            for row_index, vehicle_id in enumerate(vehicle_ids):
                probability = float(proba_array[row_index][1]) if has_both_classes else float(proba_array[row_index][0])
                eligibility = eligibility_by_vehicle[vehicle_id]
                expected_liability = probability * cost.typical_cost_inr * (1.0 if eligibility.is_eligible else 0.0)

                results[vehicle_id].append(
                    IssuePrediction(
                        issue_category=issue_category,
                        component_category=component_category,
                        probability=probability,
                        cost=cost,
                        eligibility=eligibility,
                        expected_liability_inr=expected_liability,
                        low_confidence=low_confidence,
                    )
                )

    for vehicle_id in results:
        results[vehicle_id].sort(key=lambda p: p.expected_liability_inr, reverse=True)

    return results


def predict_for_vehicle(vehicle_id: str) -> list[IssuePrediction]:
    """Convenience entry point for a single ad-hoc lookup (e.g. the API,
    or this module's own __main__). Loads a fresh context - for scoring
    many vehicles, build one PredictionContext with
    load_prediction_context() and call predict_for_vehicle_in_context()
    directly instead (see rank.py)."""
    context = load_prediction_context()
    return predict_for_vehicle_in_context(vehicle_id, context)


if __name__ == "__main__":
    import sys

    vehicle_id = sys.argv[1] if len(sys.argv) > 1 else "VEHUNIT_SYN_0000065"
    for prediction in predict_for_vehicle(vehicle_id)[:10]:
        flag = " [LOW-CONFIDENCE: cluster trained on <5 real positive examples]" if prediction.low_confidence else ""
        print(
            f"{prediction.issue_category:25s} P={prediction.probability:.3f} "
            f"cost=Rs.{prediction.cost.typical_cost_inr:10,.2f} "
            f"eligible={prediction.eligibility.is_eligible} "
            f"expected_liability=Rs.{prediction.expected_liability_inr:10,.2f}{flag}"
        )
