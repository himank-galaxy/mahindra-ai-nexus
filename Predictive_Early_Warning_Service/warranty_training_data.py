"""
Builds the labeled training dataset for every cluster from real data:
data/synthetic/auto/deliveries.csv + service_events.csv (+ telematics
where available).

Checkpoint rule (adapted from PEWS's gap-window labeling for this
domain's real data shape - see docs/Implementation_plan_warranty_predictive_service.md
Part B): each vehicle's real FIRST_INSPECTION service event, or
CHECKPOINT_FALLBACK_DAYS after delivery if it never attended one.
Features are computed from everything known up to the checkpoint; labels
are whether an issue occurred in service_events strictly AFTER it - this
gap is what makes a positive prediction genuinely forward-looking rather
than "detecting" an issue that already happened before the checkpoint.

Label source is service_events (UNSCHEDULED_REPAIR + repair_required),
not warranty_claims - see the implementation plan for why: only 53 real
warranty claims exist, too few and too sparse across 26 issue categories
to train on directly.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

import warranty_config
from warranty_features import Checkpoint, compute_features

TIMEZONE = "Asia/Kolkata"


@dataclass(frozen=True)
class ClusterDataset:
    component_category: str
    issue_categories: tuple[str, ...]
    feature_rows: list[dict[str, float]]
    label_rows: list[dict[str, int]]  # one 0/1 per issue_category
    checkpoint_at: list[pd.Timestamp]  # parallel to feature_rows/label_rows, for time-based split
    vehicle_ids: list[str]


def _load_raw() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    deliveries = pd.read_csv(warranty_config.DELIVERIES_PATH)
    deliveries = deliveries[deliveries["delivery_status"] == "DELIVERED"].copy()
    deliveries["actual_delivery_date"] = pd.to_datetime(deliveries["actual_delivery_date"])

    service_events = pd.read_csv(warranty_config.SERVICE_EVENTS_PATH)
    service_events["service_started_at"] = pd.to_datetime(service_events["service_started_at"])

    telematics: pd.DataFrame | None
    try:
        telematics = pd.read_csv(warranty_config.TELEMATICS_PATH)
        telematics["timestamp"] = pd.to_datetime(telematics["timestamp"])
    except FileNotFoundError:
        telematics = None

    return deliveries, service_events, telematics


def _build_checkpoints(deliveries: pd.DataFrame, service_events: pd.DataFrame) -> dict[str, Checkpoint]:
    first_inspections = (
        service_events[service_events["service_type"] == "FIRST_INSPECTION"]
        .sort_values("service_started_at")
        .drop_duplicates("vehicle_id", keep="first")
        .set_index("vehicle_id")
    )

    checkpoints: dict[str, Checkpoint] = {}
    for delivery in deliveries.itertuples(index=False):
        vehicle_id = str(delivery.vehicle_id)
        delivery_at = pd.Timestamp(delivery.actual_delivery_date)

        if vehicle_id in first_inspections.index:
            inspection = first_inspections.loc[vehicle_id]
            checkpoint_at = pd.Timestamp(inspection["service_started_at"])
            had_first_inspection = True
            first_inspection_service_score = float(inspection["service_score"])
        else:
            checkpoint_at = delivery_at + pd.Timedelta(days=warranty_config.CHECKPOINT_FALLBACK_DAYS)
            had_first_inspection = False
            first_inspection_service_score = None

        checkpoints[vehicle_id] = Checkpoint(
            vehicle_id=vehicle_id,
            checkpoint_at=checkpoint_at,
            delivery_at=delivery_at,
            vehicle_model_name=str(delivery.vehicle_model_name),
            production_quality_score=float(delivery.production_quality_score),
            supplier_lot_quality_score=float(delivery.supplier_lot_quality_score),
            had_first_inspection=had_first_inspection,
            first_inspection_service_score=first_inspection_service_score,
        )

    return checkpoints


def build_training_data(generation_end: pd.Timestamp | None = None) -> dict[str, ClusterDataset]:
    """Returns one ClusterDataset per component_category cluster. A
    vehicle whose checkpoint hasn't happened yet (relative to
    generation_end - "now" for this batch dataset) is excluded, since we
    can't yet observe whether an issue occurred after it."""

    deliveries, service_events, telematics = _load_raw()

    if generation_end is None:
        generation_end = pd.Timestamp(service_events["service_started_at"].max())
    if generation_end.tzinfo is None and not service_events.empty:
        generation_end = generation_end.tz_localize(service_events["service_started_at"].dt.tz)

    checkpoints = _build_checkpoints(deliveries, service_events)

    telematics_by_vehicle: dict[str, pd.DataFrame] = {}
    if telematics is not None:
        for vehicle_id, group in telematics.groupby("vehicle_id"):
            telematics_by_vehicle[str(vehicle_id)] = group

    events_by_vehicle = {
        str(vehicle_id): group.sort_values("service_started_at")
        for vehicle_id, group in service_events.groupby("vehicle_id")
    }

    datasets: dict[str, ClusterDataset] = {}
    for component_category, issue_categories in warranty_config.CLUSTERS.items():
        feature_rows: list[dict[str, float]] = []
        label_rows: list[dict[str, int]] = []
        checkpoint_ats: list[pd.Timestamp] = []
        vehicle_ids: list[str] = []

        for vehicle_id, checkpoint in checkpoints.items():
            if checkpoint.checkpoint_at >= generation_end:
                continue  # checkpoint hasn't happened yet - can't label it

            vehicle_events = events_by_vehicle.get(vehicle_id, service_events.iloc[0:0])
            prior_events = vehicle_events[vehicle_events["service_started_at"] <= checkpoint.checkpoint_at]
            future_events = vehicle_events[vehicle_events["service_started_at"] > checkpoint.checkpoint_at]
            future_repairs = future_events[future_events["service_type"] == "UNSCHEDULED_REPAIR"]

            telematics_window = None
            vehicle_telematics = telematics_by_vehicle.get(vehicle_id)
            if vehicle_telematics is not None:
                telematics_window = vehicle_telematics[
                    vehicle_telematics["timestamp"] <= checkpoint.checkpoint_at
                ]

            features = compute_features(checkpoint, prior_events, issue_categories, telematics_window)
            labels = {
                issue: int((future_repairs["issue_category"] == issue).any())
                for issue in issue_categories
            }

            feature_rows.append(features)
            label_rows.append(labels)
            checkpoint_ats.append(checkpoint.checkpoint_at)
            vehicle_ids.append(vehicle_id)

        datasets[component_category] = ClusterDataset(
            component_category=component_category,
            issue_categories=issue_categories,
            feature_rows=feature_rows,
            label_rows=label_rows,
            checkpoint_at=checkpoint_ats,
            vehicle_ids=vehicle_ids,
        )

    return datasets
