"""Real, deterministic case-priority scoring for Collections AI Swarm.

Mirrors app/services/risk_engine.py's own pattern exactly: a transparent,
bounded, point-based score over real signals, never randomly assigned and
never independent of the case's own real numbers. Priority answers "which
case should a collections agent work first," which is a genuinely
different question from any single one of its inputs:

- Net expected recoverable value (recovery probability x outstanding,
  minus the recommended channel's real contact cost) — how much money is
  actually at stake and how likely and cheap it is to get it back. This
  one figure already folds together "outstanding exposure," "recovery
  probability," and "cost" the way a collections desk would naturally
  weigh them together, rather than three independent, harder-to-combine
  numbers.
- Roll-forward risk — how urgent it is to intervene before the case gets
  worse.
- Days past due — how long this has already been left unaddressed.
- Customer friction of the recommended channel — a high-friction action
  (e.g. an in-person field visit) is only worth its intrusiveness when
  the case already scores highly on the factors above; friction alone
  never inflates priority.

Every threshold here is a documented, reviewable business judgment (the
same honest treatment risk_engine.py gives its own bands) — there is no
historical "how urgently was this case actually worked" column in the
runtime schema to fit thresholds against.
"""

from __future__ import annotations

from dataclasses import dataclass

NET_RECOVERY_HIGH_INR = 200_000
NET_RECOVERY_MEDIUM_INR = 50_000
NET_RECOVERY_LOW_INR = 10_000

ROLL_FORWARD_RISK_HIGH = 70
ROLL_FORWARD_RISK_MEDIUM = 40

DPD_URGENT = 180
DPD_ELEVATED = 90

FRICTION_HIGH = 50

PRIORITY_LEVEL_BY_POINTS = [(6, "Critical"), (4, "High"), (2, "Medium"), (0, "Low")]


@dataclass(frozen=True)
class PriorityAssessment:
    level: str  # Critical | High | Medium | Low
    points: int
    reason: str


def score_case_priority(
    *,
    net_expected_recovery_inr: float,
    roll_forward_risk: int,
    dpd: int,
    friction: int,
) -> PriorityAssessment:
    points = 0
    factors: list[str] = []

    if net_expected_recovery_inr >= NET_RECOVERY_HIGH_INR:
        points += 3
        factors.append(f"net expected recovery ₹{net_expected_recovery_inr:,.0f} (high)")
    elif net_expected_recovery_inr >= NET_RECOVERY_MEDIUM_INR:
        points += 2
        factors.append(f"net expected recovery ₹{net_expected_recovery_inr:,.0f} (medium)")
    elif net_expected_recovery_inr >= NET_RECOVERY_LOW_INR:
        points += 1
        factors.append(f"net expected recovery ₹{net_expected_recovery_inr:,.0f} (low)")
    else:
        factors.append(f"net expected recovery ₹{net_expected_recovery_inr:,.0f} (negligible)")

    if roll_forward_risk >= ROLL_FORWARD_RISK_HIGH:
        points += 2
        factors.append(f"roll-forward risk {roll_forward_risk}% (high)")
    elif roll_forward_risk >= ROLL_FORWARD_RISK_MEDIUM:
        points += 1
        factors.append(f"roll-forward risk {roll_forward_risk}% (medium)")
    else:
        factors.append(f"roll-forward risk {roll_forward_risk}% (low)")

    if dpd >= DPD_URGENT:
        points += 2
        factors.append(f"{dpd} days past due (urgent)")
    elif dpd >= DPD_ELEVATED:
        points += 1
        factors.append(f"{dpd} days past due (elevated)")
    else:
        factors.append(f"{dpd} days past due")

    if friction >= FRICTION_HIGH:
        points -= 1
        factors.append("recommended action is high-friction (only justified by the factors above)")

    points = max(0, points)
    level = next(label for threshold, label in PRIORITY_LEVEL_BY_POINTS if points >= threshold)
    reason = f"{level} priority ({points} pts): " + ", ".join(factors) + "."
    return PriorityAssessment(level=level, points=points, reason=reason)
