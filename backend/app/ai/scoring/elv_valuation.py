"""ELV valuation — exact port of the ``ELV`` estimator formulas."""

from __future__ import annotations

from app.ai.utils import js_round

RISK_FLAGS: tuple[str, ...] = ("Incomplete RC", "Missing insurance papers")


def estimate_elv(age: int, condition: int, docs: int) -> tuple[int, int, list[str]]:
    """Return (suggested price, recoverable value, risk flags)."""
    price = js_round(80000 - age * 3800 + condition * 350 + docs * 120)
    recoverable = js_round(price * 0.7)
    risks = list(RISK_FLAGS) if docs < 60 else ["OK"]
    return price, recoverable, risks
