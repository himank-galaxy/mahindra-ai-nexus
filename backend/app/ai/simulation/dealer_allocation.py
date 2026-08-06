"""Dealer Allocation Simulation — exact port of the ``DealerAlloc`` formulas."""

from __future__ import annotations

from app.ai.utils import js_round
from app.schemas.simulation import DealerAllocationSimIn, DealerAllocationSimOut

SUGGESTED_SPLIT = "West 45% · North 30% · South 25%"


def run(payload: DealerAllocationSimIn) -> DealerAllocationSimOut:
    return DealerAllocationSimOut(
        delay=max(1, payload.wait - js_round((payload.demand + payload.capacity) / 20)),
        rev=js_round(payload.units * (payload.demand / 100) * 18),
        csat=min(95, 70 + js_round(payload.capacity / 5)),
        suggested_split=SUGGESTED_SPLIT,
    )
