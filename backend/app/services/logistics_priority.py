"""Real, deterministic route-priority scoring for the Logistics AI
Control Tower.

Mirrors app/services/collections_priority.py's own pattern exactly: a
transparent, bounded, point-based score over real signals, never
randomly assigned. Priority answers "which route needs attention first,"
a genuinely different question from any single input alone:

- Expected risk cost — the real calibrated rupee exposure from predicted
  delay/breach probability across this route's own real shipments (see
  app/ai/simulation/logistics_delay.py's ``expected_risk_cost_inr``),
  summed rather than averaged, so a route with many at-risk shipments
  scores higher than one with a single outlier at the same probability.
- SLA-breach probability — how likely intervention is needed at all.
- Affected shipment count — how many real shipments this route's
  problem actually touches.

Every threshold here is a documented, reviewable business judgment (the
same honest treatment risk_engine.py/collections_priority.py give their
own bands) — there is no historical "how urgently was this route worked"
column in the runtime schema to fit thresholds against.
"""

from __future__ import annotations

from dataclasses import dataclass

COST_EXPOSURE_HIGH_INR = 500_000
COST_EXPOSURE_MEDIUM_INR = 100_000
COST_EXPOSURE_LOW_INR = 20_000

BREACH_PROBABILITY_HIGH = 40
BREACH_PROBABILITY_MEDIUM = 20

AFFECTED_SHIPMENTS_HIGH = 15
AFFECTED_SHIPMENTS_MEDIUM = 5

PRIORITY_LEVEL_BY_POINTS = [(6, "Critical"), (4, "High"), (2, "Medium"), (0, "Low")]


@dataclass(frozen=True)
class PriorityAssessment:
    level: str  # Critical | High | Medium | Low
    points: int
    reason: str


def score_route_priority(
    *,
    total_expected_risk_cost_inr: float,
    breach_probability: int,
    affected_shipments: int,
) -> PriorityAssessment:
    points = 0
    factors: list[str] = []

    if total_expected_risk_cost_inr >= COST_EXPOSURE_HIGH_INR:
        points += 3
        factors.append(f"expected risk cost ₹{total_expected_risk_cost_inr:,.0f} (high)")
    elif total_expected_risk_cost_inr >= COST_EXPOSURE_MEDIUM_INR:
        points += 2
        factors.append(f"expected risk cost ₹{total_expected_risk_cost_inr:,.0f} (medium)")
    elif total_expected_risk_cost_inr >= COST_EXPOSURE_LOW_INR:
        points += 1
        factors.append(f"expected risk cost ₹{total_expected_risk_cost_inr:,.0f} (low)")
    else:
        factors.append(f"expected risk cost ₹{total_expected_risk_cost_inr:,.0f} (negligible)")

    if breach_probability >= BREACH_PROBABILITY_HIGH:
        points += 2
        factors.append(f"SLA-breach probability {breach_probability}% (high)")
    elif breach_probability >= BREACH_PROBABILITY_MEDIUM:
        points += 1
        factors.append(f"SLA-breach probability {breach_probability}% (medium)")
    else:
        factors.append(f"SLA-breach probability {breach_probability}% (low)")

    if affected_shipments >= AFFECTED_SHIPMENTS_HIGH:
        points += 1
        factors.append(f"{affected_shipments} shipments affected")
    elif affected_shipments >= AFFECTED_SHIPMENTS_MEDIUM:
        factors.append(f"{affected_shipments} shipments affected")
    else:
        factors.append(f"{affected_shipments} shipments affected (small batch)")

    level = next(label for threshold, label in PRIORITY_LEVEL_BY_POINTS if points >= threshold)
    reason = f"{level} priority ({points} pts): " + ", ".join(factors) + "."
    return PriorityAssessment(level=level, points=points, reason=reason)
