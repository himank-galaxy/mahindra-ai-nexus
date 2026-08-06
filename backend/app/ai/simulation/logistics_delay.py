"""Logistics Delay Simulation — exact port of the ``LogisticsSim`` formulas."""

from __future__ import annotations

from app.ai.utils import js_round
from app.schemas.simulation import LogisticsDelaySimIn, LogisticsDelaySimOut

RECOMMENDED_REROUTE = "Via Panvel bypass"


def run(payload: LogisticsDelaySimIn) -> LogisticsDelaySimOut:
    delay = min(
        95,
        payload.warehouse * 0.3 + payload.weather * 0.4 + (100 - payload.vehicle) * 0.2,
    )
    breach = 42 + payload.weather / 3 if payload.sla == "High" else 18 + payload.weather / 4
    return LogisticsDelaySimOut(
        delay=js_round(delay),
        breach=js_round(breach),
        reroute=RECOMMENDED_REROUTE,
        cost=js_round(payload.warehouse * 320 + payload.weather * 480),
    )
