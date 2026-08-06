"""Circularity Credit Pricing Simulation — exact port of ``CreditPricing``."""

from __future__ import annotations

from app.ai.utils import js_round
from app.schemas.simulation import CreditPricingSimIn, CreditPricingSimOut


def run(payload: CreditPricingSimIn) -> CreditPricingSimOut:
    price = js_round(800 + payload.demand * 15 + payload.trace * 6 - payload.supply * 5)
    closure = js_round(min(95, 30 + payload.demand * 0.4 + payload.trace * 0.3 - payload.supply * 0.15))
    match = js_round(min(98, 40 + payload.demand * 0.5 + payload.verif * 0.2))
    if payload.verif < 40:
        compliance_risk = "High"
    elif payload.verif < 70:
        compliance_risk = "Medium"
    else:
        compliance_risk = "Low"
    return CreditPricingSimOut(
        price_band_low=price - 60,
        price_band_high=price + 60,
        closure=closure,
        match=match,
        compliance_risk=compliance_risk,
    )
