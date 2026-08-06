"""Finance Collections Simulation — exact port of the ``CollectionsSim`` formulas."""

from __future__ import annotations

from app.ai.utils import js_round
from app.schemas.simulation import CollectionsSimIn, CollectionsSimOut

_PROB_BY_RISK = {"Low": 82, "Medium": 68, "High": 42}
_FRICTION_BY_CHANNEL = {"Field": 62, "Voice": 34, "Digital": 12}


def run(payload: CollectionsSimIn) -> CollectionsSimOut:
    prob = _PROB_BY_RISK.get(payload.risk, 60)
    if payload.channel == "Field":
        cost = 1200 + payload.field * 8
    elif payload.channel == "Voice":
        cost = 320
    else:
        cost = 90
    return CollectionsSimOut(
        prob=prob,
        cost=cost,
        friction=_FRICTION_BY_CHANNEL[payload.channel],
        net=js_round(prob * (0.7 if payload.offer == "Settlement" else 1.0) * 42),
    )
