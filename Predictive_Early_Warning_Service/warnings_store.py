"""
Reads and writes warning records as local JSON files under warnings/ - not
a new database schema (see IMPLEMENTATION_PLAN.md "out of scope for this
first pass").

One file per warning: warnings/<warning_id>.json. A vehicle + warning_type
pair has at most one OPEN warning at a time - a new prediction above
threshold updates the existing open warning rather than creating a
duplicate, mirroring how the existing causal service avoids duplicate
warnings for an unchanged issue.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from pews_config import IMPACT_RANKING_PATH, WARNINGS_DIR

OPEN_STATUSES = {"OPEN", "ACKNOWLEDGED", "INVESTIGATING", "ACTION_RECOMMENDED", "ACTION_APPROVED"}


@dataclass
class Warning:
    warning_id: str
    vehicle_id: str
    vehicle_model_id: str | None
    warning_type: str
    target_metric: str
    prediction_probability: float
    forecast_horizon_hours: int
    severity: str
    warning_timestamp: str  # ISO timestamp - when this issue was FIRST detected. Frozen once set.
    status: str = "OPEN"
    causal_run_id: str | None = None
    last_seen_at: str = ""  # ISO timestamp - updates every time a re-score still finds this at-risk
    forecast_gap_hours: int = 0  # the predicted event isn't expected before this many hours from now
    # Warranty liability gate (eligibility.py::check_eligibility()) run
    # for this vehicle + the warning's cluster at detection time. None on
    # warnings persisted before this field existed, and defaults to None
    # here so those old JSON files still load - not every warning is
    # guaranteed to have gone through the gate.
    is_warranty_eligible: bool | None = None
    eligibility_notes: str = ""


def _path_for(warning_id: str) -> str:
    return os.path.join(WARNINGS_DIR, f"{warning_id}.json")


def _load(path: str) -> Warning:
    with open(path, "r", encoding="utf-8") as file:
        return Warning(**json.load(file))


def _save(warning: Warning) -> None:
    os.makedirs(WARNINGS_DIR, exist_ok=True)
    with open(_path_for(warning.warning_id), "w", encoding="utf-8") as file:
        json.dump(asdict(warning), file, indent=2)


def list_warnings(status: str | None = None) -> list[Warning]:
    if not os.path.isdir(WARNINGS_DIR):
        return []

    warnings = []
    for filename in os.listdir(WARNINGS_DIR):
        if not filename.endswith(".json"):
            continue
        warning = _load(os.path.join(WARNINGS_DIR, filename))
        if status is None or warning.status == status:
            warnings.append(warning)

    warnings.sort(key=lambda w: w.warning_timestamp, reverse=True)
    return warnings


def get_warning(warning_id: str) -> Warning | None:
    path = _path_for(warning_id)
    if not os.path.exists(path):
        return None
    return _load(path)


def find_open_warning(vehicle_id: str, warning_type: str) -> Warning | None:
    for warning in list_warnings():
        if (
            warning.vehicle_id == vehicle_id
            and warning.warning_type == warning_type
            and warning.status in OPEN_STATUSES
        ):
            return warning
    return None


def create_or_update_warning(
    vehicle_id: str,
    vehicle_model_id: str | None,
    warning_type: str,
    target_metric: str,
    probability: float,
    forecast_horizon_hours: int,
    severity: str,
    forecast_gap_hours: int = 0,
    is_warranty_eligible: bool | None = None,
    eligibility_notes: str = "",
) -> Warning:
    """
    If this vehicle already has an open warning of this type, refresh its
    probability, last_seen_at, and eligibility ONLY - warning_timestamp is
    frozen at first detection, so the warnings list reflects genuinely new
    detections arriving over time rather than the entire list appearing
    to refresh every scoring tick. Otherwise create a new one.

    Eligibility is refreshed on every update (not frozen like
    warning_timestamp) since a vehicle's coverage window/odometer moves
    forward over the life of an open warning, and re-running the gate is
    cheap compared to the model scoring that already happens every tick.
    """

    existing = find_open_warning(vehicle_id, warning_type)
    now_iso = datetime.now(timezone.utc).isoformat()

    if existing is not None:
        existing.prediction_probability = probability
        existing.last_seen_at = now_iso
        existing.is_warranty_eligible = is_warranty_eligible
        existing.eligibility_notes = eligibility_notes
        _save(existing)
        return existing

    warning = Warning(
        warning_id=uuid.uuid4().hex,
        vehicle_id=vehicle_id,
        vehicle_model_id=vehicle_model_id,
        warning_type=warning_type,
        target_metric=target_metric,
        prediction_probability=probability,
        forecast_horizon_hours=forecast_horizon_hours,
        severity=severity,
        warning_timestamp=now_iso,
        status="OPEN",
        last_seen_at=now_iso,
        forecast_gap_hours=forecast_gap_hours,
        is_warranty_eligible=is_warranty_eligible,
        eligibility_notes=eligibility_notes,
    )
    _save(warning)
    return warning


def set_status(warning_id: str, status: str) -> Warning | None:
    warning = get_warning(warning_id)
    if warning is None:
        return None
    warning.status = status
    _save(warning)
    return warning


def attach_causal_run(warning_id: str, causal_run_id: str) -> Warning | None:
    warning = get_warning(warning_id)
    if warning is None:
        return None
    warning.causal_run_id = causal_run_id
    warning.status = "INVESTIGATING"
    _save(warning)
    return warning


# --- Fleet-wide financial-impact ranking cache ---
#
# Same "scheduler computes, API only reads" principle as
# warranty_predictions_store.py's fleet ranking cache: recomputing this
# from every open Warning on every API request would mean re-reading
# every file under WARNINGS_DIR per request. scheduler.py computes it
# once per tick (see impact_ranking.py) and persists it here; the API
# just reads this one file.


def save_impact_ranking(ranked: list[dict]) -> None:
    record = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "ranked_issues": ranked,
    }
    with open(IMPACT_RANKING_PATH, "w", encoding="utf-8") as file:
        json.dump(record, file, indent=2)


def load_impact_ranking() -> dict | None:
    if not os.path.exists(IMPACT_RANKING_PATH):
        return None
    with open(IMPACT_RANKING_PATH, "r", encoding="utf-8") as file:
        return json.load(file)
