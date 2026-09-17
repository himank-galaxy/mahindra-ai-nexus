"""Dealer Allocation optimizer: a real linear program, not a predictive model.

A scarce pool of vehicle units is distributed across real dealers to
maximize expected sell-through, weighted by each dealer's REAL historical
demand share and REAL delivery reliability. See
docs/simulation_centre_implementation.md §4.2 — this is deliberately an
optimization problem (scipy.optimize.linprog), never a deep-learning
model, and the runtime schema has no historical shortage example to fit a
predictive model against anyway (``requested_units`` == ``allocated_units``
in every historical row).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linprog

# A pure demand+quality ranking can legitimately zero out an entire region
# if all its dealers score below the pool's cutoff (verified against real
# data: this happens for regions with systematically weaker delivery
# reliability, not from a bug). The original brief calls out "regional
# constraints" as something the optimizer should respect, so each region
# is floored at this fraction of what its own historical demand share
# would proportionally entitle it to — capped at that region's own real
# capacity — while the optimizer still concentrates the remaining pool on
# whichever dealers score best.
MIN_REGION_DEMAND_SHARE = 0.3


@dataclass(frozen=True)
class DealerAllocationResult:
    dealer_id: list[str]
    dealer_name: list[str]
    region_name: list[str]
    recommended_units: np.ndarray
    naive_units: np.ndarray
    demand_weight: np.ndarray
    quality_score: np.ndarray
    capacity_ceiling: np.ndarray


def _naive_capacity_proportional_split(capacity_ceiling: np.ndarray, available_units: float) -> np.ndarray:
    """Counterfactual "current policy": split purely by capacity share,
    ignoring demand and quality — what the optimizer's real gain is measured
    against, since there is no historical constrained-allocation baseline."""
    total_capacity = capacity_ceiling.sum()
    if total_capacity <= 0:
        return np.zeros_like(capacity_ceiling)
    naive = np.minimum(capacity_ceiling, capacity_ceiling / total_capacity * available_units)
    remaining = available_units - naive.sum()
    for _ in range(5):
        if remaining <= 1e-6:
            break
        headroom = capacity_ceiling - naive
        headroom_total = headroom.sum()
        if headroom_total <= 1e-6:
            break
        naive = naive + np.minimum(headroom, headroom / headroom_total * remaining)
        remaining = available_units - naive.sum()
    return naive


def optimize(dealers: pd.DataFrame, *, available_units: float, capacity_pct: float) -> DealerAllocationResult:
    demand_weight = (dealers["total_requested"] / dealers["total_requested"].sum()).to_numpy()
    quality_score = (1 - dealers["delayed_rate"].clip(0, 1)).to_numpy()
    capacity_ceiling = (dealers["monthly_booking_capacity"] * (capacity_pct / 100)).clip(lower=0).to_numpy()

    # Blend: half weight on real demand share, half on real delivery
    # reliability — a dealer with more historical demand AND fewer delayed
    # deliveries gets priority for the scarce pool.
    score = demand_weight * (0.5 + 0.5 * quality_score)

    n = len(dealers)
    regions = dealers["region_name"].to_numpy()
    a_ub = [np.ones(n)]
    b_ub = [available_units]
    for region in pd.unique(regions):
        mask = (regions == region).astype(float)
        region_demand_share = float((demand_weight * mask).sum())
        region_capacity = float((capacity_ceiling * mask).sum())
        floor = min(MIN_REGION_DEMAND_SHARE * region_demand_share * available_units, region_capacity)
        if floor > 1e-9:
            a_ub.append(-mask)
            b_ub.append(-floor)

    result = linprog(
        c=-score,
        A_ub=np.array(a_ub),
        b_ub=np.array(b_ub),
        bounds=[(0, cap) for cap in capacity_ceiling],
        method="highs",
    )
    recommended = result.x if result.success else np.zeros(n)

    return DealerAllocationResult(
        dealer_id=dealers["dealer_id"].tolist(),
        dealer_name=dealers["dealer_name"].tolist(),
        region_name=dealers["region_name"].tolist(),
        recommended_units=recommended,
        naive_units=_naive_capacity_proportional_split(capacity_ceiling, available_units),
        demand_weight=demand_weight,
        quality_score=quality_score,
        capacity_ceiling=capacity_ceiling,
    )
