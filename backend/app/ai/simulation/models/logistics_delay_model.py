"""Logistics Delay trained models: any-delay and SLA-breach probability.

Both are genuine classifiers on real ``shipments`` outcome columns —
``delay_minutes > 0`` (~58% of shipments) and ``sla_breach`` (~10% of
shipments) — sharing one real feature set (reusing the mixed
numeric+categorical fitting in app/ai/simulation/models/logit.py, the
same code Auto Sales/Collections use). ``route_id`` and ``priority`` are
real categorical features, so each route's own historical delay/breach
effect — and each priority tier's own effect — can be surfaced as a
driver rather than folded into a generic average.

Two scenario sliders (Weather Disruption, Vehicle Availability) have no
continuous real column to fit against — only the boolean
``weather_disruption``/``vehicle_breakdown`` flags exist — so the trained
coefficient (fit on genuine 0/1 outcome variation) is evaluated at the
slider's fractional value as a linear extrapolation in logit-space, the
same mechanism any numeric slider uses in a logistic regression. This
stays labelled ``trained_model``, not ``calibrated_heuristic``, because
the coefficient itself is fit on real variation, not asserted.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pandas as pd

from app.ai.simulation.models.logit import FittedLogit, fit_logit
from app.core.errors import DomainValidationError
from app.repositories.logistics_delay_simulation import LogisticsDelaySimulationRepository

MIN_TRAINING_ROWS = 100
MIN_ROUTE_COHORT = 5

NUMERIC_FEATURES: list[str] = [
    "distance_km",
    "warehouse_utilization_pct",
    "dock_wait_minutes",
    "weather_disruption",
    "vehicle_breakdown",
]
CATEGORICAL_FEATURES: list[str] = ["route_id", "priority"]

FRIENDLY_NAMES: dict[str, str] = {
    "distance_km": "Route distance",
    "warehouse_utilization_pct": "Warehouse utilization",
    "dock_wait_minutes": "Dock wait time",
    "weather_disruption": "Weather disruption",
    "vehicle_breakdown": "Vehicle breakdown risk",
}


@dataclass(frozen=True)
class LogisticsDelayModels:
    any_delay: FittedLogit
    breach: FittedLogit
    frame: pd.DataFrame

    def route_cohort_features(self, route_id: str) -> tuple[dict[str, float], int]:
        """Real per-route averages for features the scenario sliders don't control."""
        cohort = self.frame[self.frame["route_id"] == route_id]
        source = cohort if len(cohort) >= MIN_ROUTE_COHORT else self.frame
        return {
            "distance_km": float(source["distance_km"].mean()),
            "dock_wait_minutes": float(source["dock_wait_minutes"].mean()),
        }, len(cohort)

    def mean_delay_minutes_when_delayed(self, route_id: str) -> float:
        cohort = self.frame[(self.frame["route_id"] == route_id) & (self.frame["delay_minutes"] > 0)]
        source = cohort if len(cohort) >= MIN_ROUTE_COHORT else self.frame[self.frame["delay_minutes"] > 0]
        return float(source["delay_minutes"].mean()) if len(source) else 0.0

    def warehouse_utilization_bounds(self) -> tuple[float, float]:
        """Real observed (min, max) — the runtime schema's warehouse
        utilization only ever varies within a narrow real band (roughly
        0.57-0.85), far short of the UI slider's full 0-100% range.
        Predicting at a value outside this band would linearly extrapolate
        the standardized coefficient well past anything the model was fit
        on; the caller clips to this range and flags the scenario as
        outside the training range for the confidence contract instead."""
        return float(self.frame["warehouse_utilization_pct"].min()), float(self.frame["warehouse_utilization_pct"].max())


_cache: LogisticsDelayModels | None = None
_lock = asyncio.Lock()


def reset_cache_for_tests() -> None:
    """Clear the in-process model cache — test isolation only, never called at runtime."""
    global _cache
    _cache = None


async def get_or_train_models(repo: LogisticsDelaySimulationRepository) -> LogisticsDelayModels:
    global _cache
    if _cache is not None:
        return _cache
    async with _lock:
        if _cache is not None:
            return _cache
        frame = await repo.load_shipment_frame()
        if len(frame) < MIN_TRAINING_ROWS or frame["any_delay"].nunique() < 2 or frame["sla_breach"].nunique() < 2:
            raise DomainValidationError(
                "Insufficient historical shipment data to train the Logistics Delay models.",
                code="insufficient_training_data",
            )
        any_delay = fit_logit(frame, NUMERIC_FEATURES, "any_delay", categorical_features=CATEGORICAL_FEATURES)
        breach = fit_logit(frame, NUMERIC_FEATURES, "sla_breach", categorical_features=CATEGORICAL_FEATURES)
        _cache = LogisticsDelayModels(any_delay=any_delay, breach=breach, frame=frame)
        return _cache
