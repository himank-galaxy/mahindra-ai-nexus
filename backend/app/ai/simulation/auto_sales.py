"""Auto Sales Simulation — exact port of the ``AutoSales`` formulas."""

from __future__ import annotations

from app.ai.utils import format_inr, js_round
from app.schemas.simulation import AutoSalesSimIn, AutoSalesSimOut

_REGION_BOOST = {"West": 1.15, "North": 1.08}
_INTENSITY_MULT = {"High": 1.25, "Medium": 1.1}


def run(payload: AutoSalesSimIn) -> AutoSalesSimOut:
    region_boost = _REGION_BOOST.get(payload.region, 1.0)
    intensity_mult = _INTENSITY_MULT.get(payload.intensity, 1.0)
    uplift = js_round(
        (payload.discount * 1.4 + payload.bonus / 6000 + payload.campaign * 3) * region_boost * intensity_mult
    )
    margin = js_round(-(payload.discount * 1.1) - payload.campaign * 0.3)
    cancel = max(0, js_round(10 - intensity_mult * 4 - payload.bonus / 20000))
    rev = js_round(uplift * 3.2 + margin * 1.8)
    conf = min(97, 72 + js_round(intensity_mult * 8 + region_boost * 6))
    return AutoSalesSimOut(
        uplift=uplift,
        margin=margin,
        cancel=cancel,
        rev=rev,
        conf=conf,
        recommended_action=(
            f"Deploy exchange bonus ₹{format_inr(payload.bonus)} in {payload.region} "
            f"for {payload.model} with {payload.intensity.lower()} follow-up."
        ),
    )
