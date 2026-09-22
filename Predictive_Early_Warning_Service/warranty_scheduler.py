"""
Periodic tick that recomputes warranty-liability predictions for the
whole fleet, persists one JSON record per vehicle, and also computes +
persists the fleet-wide ranking (warranty_rank.py) from that same
in-memory data. Runs as its OWN separate background process (own
run_warranty_scheduler.sh/stop_warranty_scheduler.sh), independent of
PEWS's own scheduler.py - the two have very different cadences and
workloads: PEWS's scheduler reacts to fresh telematics every ~60s,
this one recomputes the whole batch fleet roughly hourly - mirrors how
PEWS's own api/main.py and scheduler.py are already separate processes,
not one loop entangling both concerns.

Adapted for this domain: warranty/service data is a periodically-
refreshed batch dataset (see
data/scripts/refresh_accident_insurance_claims.py), not a continuously-
streaming feed, so each tick recomputes the full fleet using the
efficient batched path (predict_for_fleet_in_context) rather than
PEWS's "only vehicles with fresh telemetry since last tick" logic.

The ranking is computed HERE, once per tick, from the fleet_predictions
already in memory - not left for the API to re-aggregate from ~1,300
individual files on every request (measured directly: that took ~46s,
slower than just recomputing from the models). The API only ever reads
what this tick already computed - same "scheduler computes, API reads"
principle PEWS's API follows.

Usage:
    Causal_Discovery_Service/.venv/bin/python3 warranty_scheduler.py          # run forever, tick every WPS_SCHEDULER_TICK_SECONDS
    Causal_Discovery_Service/.venv/bin/python3 warranty_scheduler.py --once   # single tick, then exit (for cron/manual refresh)
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import asdict
from datetime import datetime, timezone

import warranty_config
from warranty_predict import load_prediction_context, predict_for_fleet_in_context
from warranty_predictions_store import save_fleet_ranking, save_vehicle_predictions
from warranty_rank import _aggregate_and_rank, _typical_severity


def _serialize_prediction(prediction) -> dict:
    # CostEstimate/EligibilityResult are dataclasses too - asdict()
    # already recurses into them, so the result is fully
    # JSON-serializable as-is.
    return asdict(prediction)


def run_tick() -> int:
    started_at = datetime.now(timezone.utc)
    context = load_prediction_context()
    fleet_predictions = predict_for_fleet_in_context(context)

    serialized_by_vehicle: dict[str, list[dict]] = {}
    for vehicle_id, predictions in fleet_predictions.items():
        serialized = [_serialize_prediction(p) for p in predictions]
        serialized_by_vehicle[vehicle_id] = serialized
        save_vehicle_predictions(vehicle_id, serialized)

    severities = {
        issue: _typical_severity(issue, context.service_events)
        for predictions in serialized_by_vehicle.values()
        for issue in {p["issue_category"] for p in predictions}
    }
    ranked = _aggregate_and_rank(serialized_by_vehicle, len(fleet_predictions), severities)
    save_fleet_ranking([asdict(r) for r in ranked])

    duration = (datetime.now(timezone.utc) - started_at).total_seconds()
    print(
        f"[{started_at.isoformat()}] tick complete: {len(fleet_predictions)} vehicles scored, "
        f"{len(ranked)} issues ranked, in {duration:.1f}s"
    )
    return len(fleet_predictions)


async def run_forever() -> None:
    while True:
        try:
            run_tick()
        except Exception as exc:  # noqa: BLE001 - one bad tick must not kill the loop
            print(f"tick failed: {exc}")
        await asyncio.sleep(warranty_config.SCHEDULER_TICK_SECONDS)


if __name__ == "__main__":
    if "--once" in sys.argv:
        run_tick()
    else:
        asyncio.run(run_forever())
