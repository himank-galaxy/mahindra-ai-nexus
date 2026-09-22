"""Real risk scoring for Simulation Center decisions.

Replaces the previous crude ``{"low": "High", "medium": "Medium", "high":
"Low"}`` confidence inversion (which conflated model uncertainty with
business risk and ignored everything else) with a transparent, bounded,
deterministic score over real signals: financial exposure (from the
run's own persisted ``outputs``), model confidence, and two documented
per-domain judgments — reversibility and customer-facing-ness — that
have no real column to fit against (there is no historical "we reversed
this decision" record anywhere in the runtime schema), so they stay
explicit, reviewable constants rather than invented per-run values.

Never randomly assigned; never independent of the run's own real
confidence/impact numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Thresholds live here, not scattered across callers/frontend — the
# spec's own requirement ("do not hardcode thresholds in many
# components"). Financial-impact bands in INR.
FINANCIAL_IMPACT_HIGH_INR = 10_00_00_000  # >= 10 Cr
FINANCIAL_IMPACT_MEDIUM_INR = 1_00_00_000  # >= 1 Cr
FINANCIAL_IMPACT_LOW_INR = 10_00_000  # >= 10 L

CONFIDENCE_LOW = 40
CONFIDENCE_MEDIUM = 60
CONFIDENCE_HIGH = 75

RISK_LEVEL_BY_POINTS = [(7, "Critical"), (5, "High"), (3, "Medium"), (0, "Low")]

# Reversibility/customer-facing-ness have no real historical column to
# derive them from (no runtime table records "was this decision ever
# reversed") — these are documented business judgments, reviewed once
# per domain, not per-run assumptions:
#   - Auto Sales: an incentive campaign, once launched, has already
#     spent budget/customer expectation — low reversibility.
#   - Dealer Allocation: a monthly unit split can be revised next cycle
#     — medium reversibility.
#   - Collections: a single contact attempt is low-stakes to reverse —
#     high reversibility, but the customer interaction itself is
#     customer-facing.
#   - Logistics Delay: a reroute recommendation for the next shipment
#     is fully reversible — high reversibility, not customer-facing
#     (an internal logistics decision).
#   - Credit Pricing: a listing's ask price can be changed at any time
#     — high reversibility, but the marketplace listing is buyer-facing.
_DOMAIN_RISK_PROFILE: dict[str, tuple[str, bool]] = {
    "auto-sales": ("low", True),
    "dealer-allocation": ("medium", False),
    "collections": ("high", True),
    "logistics-delay": ("high", False),
    "credit-pricing": ("high", True),
}


def _financial_impact_inr(domain: str, outputs: dict[str, Any]) -> float:
    """Real magnitude already produced by the engine's own output —
    never a new computation, just unit conversion to a common INR base."""
    if domain == "auto-sales":
        return abs(float(outputs.get("rev", 0))) * 1e7  # ₹ Cr
    if domain == "dealer-allocation":
        return abs(float(outputs.get("rev", 0))) * 1e5  # ₹ L
    if domain == "collections":
        return abs(float(outputs.get("net", 0))) * 1e3  # ₹K
    if domain == "logistics-delay":
        return abs(float(outputs.get("cost", 0)))  # already ₹
    if domain == "credit-pricing":
        return abs(float(outputs.get("priceBandHigh", 0)))  # ₹/tCO2e, already a real per-credit price
    return 0.0


@dataclass(frozen=True)
class RiskAssessment:
    level: str  # Low | Medium | High | Critical
    reason: str
    financial_impact_inr: float
    reversibility: str
    customer_facing: bool


def score_simulation_risk(domain: str, confidence: int, outputs: dict[str, Any]) -> RiskAssessment:
    financial_impact = _financial_impact_inr(domain, outputs)
    reversibility, customer_facing = _DOMAIN_RISK_PROFILE.get(domain, ("medium", False))

    points = 0
    if financial_impact >= FINANCIAL_IMPACT_HIGH_INR:
        points += 3
    elif financial_impact >= FINANCIAL_IMPACT_MEDIUM_INR:
        points += 2
    elif financial_impact >= FINANCIAL_IMPACT_LOW_INR:
        points += 1

    if confidence < CONFIDENCE_LOW:
        points += 3
    elif confidence < CONFIDENCE_MEDIUM:
        points += 2
    elif confidence < CONFIDENCE_HIGH:
        points += 1

    if reversibility == "low":
        points += 2
    elif reversibility == "medium":
        points += 1

    if customer_facing:
        points += 1

    level = next(label for threshold, label in RISK_LEVEL_BY_POINTS if points >= threshold)
    reason = (
        f"Estimated financial exposure ₹{financial_impact:,.0f}, {confidence}% model confidence, "
        f"{reversibility} reversibility, {'customer-facing' if customer_facing else 'internal-only'} action."
    )
    return RiskAssessment(
        level=level,
        reason=reason,
        financial_impact_inr=financial_impact,
        reversibility=reversibility,
        customer_facing=customer_facing,
    )
