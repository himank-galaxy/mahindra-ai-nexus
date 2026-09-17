"""Auto Sales Explain Drivers: causal evidence from the real business panel.

Computed once per process from a whole-business daily aggregate (leads,
follow-ups, test drives, bookings, cancellations) via the same PCMCI engine
already used for Manufacturing/Telematics/Warranty-Quality causal discovery
— never a hardcoded edge list. This is domain-level evidence (how the
business's own history behaves), not scenario-specific, so it is cached
independently of any one simulation run — see
docs/simulation_centre_implementation.md §4.1/§11.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.ai.causal.pcmci_engine import PcmciTest, run_pcmci_tests
from app.repositories.auto_sales import AutoSalesRepository

METRICS: list[str] = [
    "lead_count",
    "avg_engagement_score",
    "followup_completion_rate",
    "test_drive_completion_rate",
    "booking_count",
    "avg_booking_value_inr",
    "cancellation_count",
]
TAU_MAX_DAYS = 3
PC_ALPHA = 0.1
MIN_OBSERVATIONS = 30
TOP_EDGES = 8
SIGNIFICANCE_THRESHOLD = 0.05


@dataclass(frozen=True)
class CausalPanelResult:
    edges: list[PcmciTest]
    observation_count: int
    note: str


_cache: CausalPanelResult | None = None
_lock = asyncio.Lock()


def reset_cache_for_tests() -> None:
    """Clear the in-process causal-evidence cache — test isolation only, never called at runtime."""
    global _cache
    _cache = None


async def get_or_compute_causal_evidence(repo: AutoSalesRepository) -> CausalPanelResult:
    global _cache
    if _cache is not None:
        return _cache
    async with _lock:
        if _cache is not None:
            return _cache
        panel = await repo.load_daily_business_panel()
        if len(panel) < MIN_OBSERVATIONS:
            _cache = CausalPanelResult(
                edges=[],
                observation_count=len(panel),
                note=(
                    f"Insufficient daily history for causal discovery "
                    f"({len(panel)} days; needs {MIN_OBSERVATIONS}+)."
                ),
            )
            return _cache
        values = panel[METRICS].to_numpy(dtype=float)
        tests = run_pcmci_tests(values, METRICS, tau_max=TAU_MAX_DAYS, pc_alpha=PC_ALPHA)
        significant = sorted(
            (test for test in tests if test.p_value < SIGNIFICANCE_THRESHOLD),
            key=lambda test: (test.p_value, -abs(test.score)),
        )
        _cache = CausalPanelResult(
            edges=significant[:TOP_EDGES],
            observation_count=len(panel),
            note=(
                f"PCMCI over {len(panel)} days of real business history (tau_max={TAU_MAX_DAYS} days). "
                "Synthetic data: relationships describe the generated dataset and require validation "
                "on live business data."
            ),
        )
        return _cache
