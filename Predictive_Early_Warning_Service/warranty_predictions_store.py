"""
Durable storage for computed predictions - mirrors
Predictive_Early_Warning_Service/warnings_store.py's exact pattern: one
JSON file per record, so a completed prediction run survives an API
restart instead of only living in memory.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import warranty_config


@dataclass(frozen=True)
class VehiclePredictionRecord:
    vehicle_id: str
    computed_at: str
    predictions: list[dict]  # serialized IssuePrediction rows (see scheduler.py)


def _path_for(vehicle_id: str) -> str:
    return os.path.join(warranty_config.PREDICTIONS_DIR, f"{vehicle_id}.json")


def save_vehicle_predictions(vehicle_id: str, predictions: list[dict]) -> None:
    os.makedirs(warranty_config.PREDICTIONS_DIR, exist_ok=True)
    record = VehiclePredictionRecord(
        vehicle_id=vehicle_id,
        computed_at=datetime.now(timezone.utc).isoformat(),
        predictions=predictions,
    )
    with open(_path_for(vehicle_id), "w", encoding="utf-8") as file:
        json.dump(asdict(record), file, indent=2)


def load_vehicle_predictions(vehicle_id: str) -> dict | None:
    path = _path_for(vehicle_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_all_predictions() -> list[dict]:
    if not os.path.isdir(warranty_config.PREDICTIONS_DIR):
        return []
    records = []
    for filename in os.listdir(warranty_config.PREDICTIONS_DIR):
        # _fleet_ranking.json (see save_fleet_ranking below) is a
        # different record shape (no vehicle_id/predictions) - it must
        # never be mixed into the per-vehicle records this returns.
        if filename.endswith(".json") and filename != _RANKING_PATH_NAME:
            with open(os.path.join(warranty_config.PREDICTIONS_DIR, filename), "r", encoding="utf-8") as file:
                records.append(json.load(file))
    return records


# --- Fleet-wide ranking cache ---
#
# Aggregating the ranking from ~1,300 individual per-vehicle files on
# every read is too slow for an API request (measured directly: ~46s -
# slower than just recomputing predictions from the models, ~25s).
# scheduler.py computes the ranking once per tick, from the same
# in-memory fleet_predictions it already has (no per-file disk reads),
# and persists it here as a single small file - the API then just reads
# this one file directly, the same "scheduler computes, API only reads"
# principle PEWS's API already follows.

_RANKING_PATH_NAME = "_fleet_ranking.json"


def save_fleet_ranking(ranked: list[dict]) -> None:
    os.makedirs(warranty_config.PREDICTIONS_DIR, exist_ok=True)
    record = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "ranked_issues": ranked,
    }
    path = os.path.join(warranty_config.PREDICTIONS_DIR, _RANKING_PATH_NAME)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(record, file, indent=2)


def load_fleet_ranking() -> dict | None:
    path = os.path.join(warranty_config.PREDICTIONS_DIR, _RANKING_PATH_NAME)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)
