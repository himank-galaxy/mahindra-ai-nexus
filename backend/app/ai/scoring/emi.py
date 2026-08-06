"""Finance EMI math — exact port of the Simulate Offer modal formula."""

from __future__ import annotations

from app.ai.utils import js_round


def simulate_offer(amount: float) -> tuple[int, str]:
    """Return (EMI, risk) for a loan amount over the 36-month SME offer."""
    emi = js_round(amount / 36 + amount * 0.006)
    return emi, "Low"
