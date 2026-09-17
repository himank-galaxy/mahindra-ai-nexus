"""Causal driver explanations for the simulation Explain Drivers modal.

All five simulators share one driver list in the frontend
(``useSimShell``); the API keeps the domain parameter so a future
per-domain causal graph can be served without contract changes.
"""

from __future__ import annotations

CAUSAL_DRIVERS: tuple[str, ...] = (
    "Historical elasticity (finance approval, exchange bonus)",
    "Regional propensity model output",
    "Dealer capacity + waiting-list dynamics",
    "Competitor promo signal",
    "Weather / calendar events",
)

SIMULATION_DOMAINS: tuple[str, ...] = (
    "auto-sales",
    "dealer-allocation",
    "collections",
    "logistics-delay",
    "credit-pricing",
)
