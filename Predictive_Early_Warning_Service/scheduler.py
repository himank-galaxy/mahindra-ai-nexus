"""
Live scoring loop: reacts to genuinely NEW minute-level telemetry as it
arrives, scores the vehicles that just got new data, and creates a warning
the moment risk first crosses the threshold for that vehicle - not on
every tick for every vehicle regardless of whether anything changed.

Mirrors the shape of Live_Data_Formation/live_pipeline.py (a simple async
loop with its own tick interval, matched to the same ~1-minute cadence
that pipeline inserts data at) but this one only ever reads
vehicle_telematics_timeseries - it never writes to it.

How "new data" selection works: each tick only looks at which vehicles
received a row since the END of the previous tick (a small, recent slice)
to decide WHO to re-score. The actual feature computation for those
vehicles still uses the full trailing FEATURE_WINDOW_HOURS of history, as
before - only the "who's worth checking right now" decision is reactive.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import pandas as pd

# When this process's stdout is redirected to a log file (as it is when
# run in the background - see run_scheduler.sh), Python defaults to block
# buffering rather than line buffering, so print() output can sit unwritten
# for a long time. Force line buffering so every tick's log line actually
# reaches the file promptly, regardless of how this script is launched.
try:
    sys.stdout.reconfigure(line_buffering=True)
except (AttributeError, ValueError):
    pass  # not all stdout wrappers support reconfigure(); harmless if so

PREW_ROOT = Path(__file__).resolve().parent
CAUSAL_SERVICE_ROOT = PREW_ROOT.parent / "Causal_Discovery_Service"
if str(CAUSAL_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(CAUSAL_SERVICE_ROOT))

from db_reader import ReadOnlyDatabaseReader  # noqa: E402

import warranty_config  # noqa: E402
from eligibility import check_eligibility  # noqa: E402
from features import compute_features  # noqa: E402
from impact_ranking import compute_impact_ranking  # noqa: E402
from pews_config import (  # noqa: E402
    FEATURE_METRICS,
    FEATURE_WINDOW_HOURS,
    LABEL_GAP_HOURS,
    LABEL_WINDOW_HOURS,
    MIN_RAW_ROWS_TO_SCORE,
    MODELS_DIR,
    RISK_THRESHOLD,
    SCHEDULER_TICK_SECONDS,
    WARNING_CLUSTERS,
)
from warnings_store import (  # noqa: E402
    create_or_update_warning,
    find_open_warning,
    save_impact_ranking,
)
from dataclasses import asdict  # noqa: E402

MAX_VEHICLES_PER_TICK = 100  # matches Live_Data_Formation's own per-minute sample size


def _load_eligibility_inputs() -> dict[str, dict]:
    """
    Vehicle age/odometer come from the same batch delivery/service data
    the warranty side already reads (deliveries.csv/service_events.csv) -
    live telematics has no concept of "delivery date," so this is loaded
    once at process startup, not per tick, the same one-time-load
    convention warranty_predict.py's load_prediction_context() uses.
    """

    deliveries = pd.read_csv(warranty_config.DELIVERIES_PATH)
    deliveries["actual_delivery_date"] = pd.to_datetime(deliveries["actual_delivery_date"])

    service_events = pd.read_csv(warranty_config.SERVICE_EVENTS_PATH)
    odometer_by_vehicle = service_events.groupby("vehicle_id")["odometer_km"].max().to_dict()

    inputs: dict[str, dict] = {}
    for _, row in deliveries.iterrows():
        vehicle_id = str(row["vehicle_id"])
        inputs[vehicle_id] = {
            "delivery_at": row["actual_delivery_date"],
            "odometer_km": odometer_by_vehicle.get(vehicle_id),
        }
    return inputs


def _load_models() -> dict[str, dict]:
    # One bundle per CLUSTER, not per warning type - each bundle holds a
    # single shared multi-label model (see train_model.py) plus the
    # ordered warning_types list its output columns correspond to.
    models = {}
    for cluster in WARNING_CLUSTERS:
        path = Path(MODELS_DIR) / f"{cluster}.joblib"
        if path.exists():
            models[cluster] = joblib.load(path)
    return models


def _label_probabilities(model, feature_row: pd.DataFrame) -> list[float]:
    """
    Returns one probability-of-positive per output column, for a
    multi-output RandomForestClassifier fit on a 2D y. Handles the case
    where a given label was single-class (e.g. always 0) during training -
    predict_proba() for that output then only has one class in
    model.classes_[i], so there is no "probability of class 1" to read;
    that label is reported as 0.0 rather than raising.

    sklearn silently squeezes a single-column y (a cluster with exactly
    one warning type) down to a plain single-output fit: model.classes_
    is then a flat array and predict_proba() returns a single 2D array
    rather than a list of arrays. Normalized to the multi-output shape
    here so callers never need to know which case they're in.
    """

    raw = model.predict_proba(feature_row)
    if model.n_outputs_ == 1:
        raw = [raw]
        classes_per_output = [model.classes_]
    else:
        classes_per_output = model.classes_

    probabilities = []
    for i, classes in enumerate(classes_per_output):
        column = raw[i]
        classes_list = list(classes)
        if 1 in classes_list:
            probabilities.append(float(column[0, classes_list.index(1)]))
        else:
            probabilities.append(0.0)
    return probabilities


async def score_once(
    reader: ReadOnlyDatabaseReader,
    models: dict[str, dict],
    new_data_since: datetime,
    eligibility_inputs: dict[str, dict] | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """
    One scoring pass. Only scores vehicles that received at least one new
    row of telemetry since `new_data_since` - i.e. genuinely new
    minute-level data, not a fixed re-scan of everyone every tick.

    Returns a list of {vehicle_id, warning_type, probability,
    is_new_detection, still_active} dicts for logging/testing.
    """

    if not models:
        return []

    now = now or datetime.now(timezone.utc)
    eligibility_inputs = eligibility_inputs or {}

    # Step 1: who got new data since the last tick?
    fresh_row_counts = await reader.telematics_row_counts(new_data_since, now)
    vehicles_with_fresh_data = list(fresh_row_counts.keys())[:MAX_VEHICLES_PER_TICK]

    if not vehicles_with_fresh_data:
        return []

    # Step 2: for those vehicles only, pull their full trailing feature
    # window so compute_features() has enough history to work with.
    feature_window_start = now - timedelta(hours=FEATURE_WINDOW_HOURS)
    columns = ("vehicle_id", "timestamp") + tuple(FEATURE_METRICS)
    raw_rows = await reader.telematics_rows(
        vehicles_with_fresh_data, feature_window_start, now, columns
    )

    all_df = pd.DataFrame([dict(row) for row in raw_rows], columns=columns)
    if all_df.empty:
        return []

    results = []

    for vehicle_id, vehicle_df in all_df.groupby("vehicle_id"):
        if len(vehicle_df) < MIN_RAW_ROWS_TO_SCORE:
            continue

        for cluster, warnings in WARNING_CLUSTERS.items():
            bundle = models.get(cluster)
            if bundle is None:
                continue

            # A cluster's warning types all share ONE feature set, excluding
            # every target metric that belongs to the cluster - must match
            # training_data.py/train_model.py exactly, or the model sees a
            # different feature schema than it was trained on.
            # bundle["feature_columns"] is the exact column list that model
            # was fit on; bundle["warning_types"] is the exact order its
            # output columns correspond to.
            cluster_target_metrics = tuple(w.target_metric for w in warnings)
            features = compute_features(vehicle_df, exclude_metrics=cluster_target_metrics)
            if features is None:
                continue

            feature_row = pd.DataFrame([features])[bundle["feature_columns"]]
            if feature_row.isna().any(axis=None):
                continue

            probabilities = _label_probabilities(bundle["model"], feature_row)
            warning_by_type = {w.warning_type: w for w in warnings}

            for warning_type, probability in zip(bundle["warning_types"], probabilities):
                warning = warning_by_type[warning_type]

                is_new_detection = False
                still_active = False

                if probability >= RISK_THRESHOLD:
                    already_open = find_open_warning(str(vehicle_id), warning.warning_type)
                    is_new_detection = already_open is None
                    still_active = not is_new_detection

                    # Cluster names equal the real supplier_component_category
                    # values by construction (confirmed against
                    # COMPONENT_ISSUE_MAP) - check_eligibility() takes that
                    # directly, no translation needed.
                    vehicle_info = eligibility_inputs.get(str(vehicle_id))
                    if vehicle_info is not None:
                        age_days = max(0.0, (now - vehicle_info["delivery_at"]).total_seconds() / 86400.0)
                        odometer_km = vehicle_info["odometer_km"]
                        eligibility = check_eligibility(cluster, age_days, odometer_km, vehicle_df)
                    else:
                        eligibility = check_eligibility(cluster, 0.0, None, vehicle_df)

                    create_or_update_warning(
                        vehicle_id=str(vehicle_id),
                        vehicle_model_id=None,
                        warning_type=warning.warning_type,
                        target_metric=warning.target_metric,
                        probability=round(probability, 4),
                        forecast_gap_hours=LABEL_GAP_HOURS,
                        forecast_horizon_hours=LABEL_GAP_HOURS + LABEL_WINDOW_HOURS,
                        severity=warning.severity_label,
                        is_warranty_eligible=eligibility.is_eligible,
                        eligibility_notes=eligibility.notes,
                    )

                results.append(
                    {
                        "vehicle_id": vehicle_id,
                        "warning_type": warning.warning_type,
                        "cluster": cluster,
                        "probability": round(probability, 4),
                        "is_new_detection": is_new_detection,
                        "still_active": still_active,
                    }
                )

    return results


async def main() -> None:
    models = _load_models()
    if not models:
        print(
            "No trained models found under models/. Run train_model.py first.",
            file=sys.stderr,
        )
        return

    print(f"Loaded models for: {list(models.keys())}")
    print(
        f"Reactive scoring: checking for new telemetry every {SCHEDULER_TICK_SECONDS}s, "
        f"up to {MAX_VEHICLES_PER_TICK} freshly-updated vehicles per tick."
    )

    eligibility_inputs = _load_eligibility_inputs()
    print(f"Loaded eligibility inputs (age/odometer) for {len(eligibility_inputs)} vehicles.")

    reader = ReadOnlyDatabaseReader()
    await reader.connect()

    # First tick looks back one full tick interval so it has something to
    # find on startup rather than an empty (now, now] window.
    last_tick_end = datetime.now(timezone.utc) - timedelta(seconds=SCHEDULER_TICK_SECONDS)

    try:
        while True:
            tick_start = datetime.now(timezone.utc)
            try:
                results = await score_once(
                    reader,
                    models,
                    new_data_since=last_tick_end,
                    eligibility_inputs=eligibility_inputs,
                    now=tick_start,
                )
                new_detections = [r for r in results if r["is_new_detection"]]
                print(
                    f"{tick_start.isoformat()} | {len(results)} (vehicle, warning_type) pairs "
                    f"scored from fresh data | {len(new_detections)} NEW warnings detected"
                )
                for detection in new_detections:
                    print(
                        f"    NEW: {detection['vehicle_id']} | {detection['warning_type']} "
                        f"| risk={detection['probability']}"
                    )
                last_tick_end = tick_start

                # Recomputed from ALL currently open warnings (not just
                # this tick's fresh detections) - a vehicle's warning stays
                # open across many ticks, and the ranking must reflect the
                # whole open set every time, not just what changed just now.
                ranked = compute_impact_ranking()
                save_impact_ranking([asdict(r) for r in ranked])
            except Exception as exc:  # noqa: BLE001
                print(f"Scoring tick failed: {exc}", file=sys.stderr)

            await asyncio.sleep(SCHEDULER_TICK_SECONDS)
    finally:
        await reader.close()


if __name__ == "__main__":
    asyncio.run(main())
