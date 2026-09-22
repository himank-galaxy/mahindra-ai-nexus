"""
Domain-knowledge menu of candidate "what to do next" actions per PEWS
warning type. Mirrors the same pattern already used and proven for the
Auto Mobility Causal Twin (backend/app/ai/causal/action_candidates.py):
a small, explicit, human-editable table - never LLM-generated - so a
recommendation always has a grounded set of real options to choose from.
The LLM (see explanation_service.py) only ranks and phrases within this
menu; it never invents an action outside it.
"""

from __future__ import annotations

ACTION_CANDIDATES: dict[str, tuple[str, ...]] = {
    "BATTERY_OVERHEATING": (
        "Schedule a battery cooling-system inspection before the predicted risk window",
        "Advise the driver to avoid rapid charging or heavy load until the vehicle is inspected",
        "Check the vehicle's recent ambient-temperature exposure and parking/charging conditions",
        "Flag the vehicle for a dealer diagnostic check on the battery thermal management system",
        "Review whether the cooling fan/coolant loop for the battery pack needs servicing",
    ),
    "LOW_BATTERY_VOLTAGE": (
        "Schedule a battery health check and cell-balancing service",
        "Advise the driver to fully charge the vehicle before the predicted risk window",
        "Check for parasitic drain or a failing charging circuit",
        "Flag the vehicle for a dealer diagnostic check on the battery pack",
        "Verify the onboard charger is completing full charge cycles correctly",
    ),
    "BATTERY_DEGRADATION": (
        "Schedule a battery capacity / state-of-health test",
        "Review the vehicle's charging history for patterns known to accelerate degradation "
        "(e.g. frequent fast-charging, deep discharge cycles)",
        "Advise the driver on charging practices that reduce further degradation",
        "Flag the vehicle for a warranty-eligible battery inspection if still within coverage",
        "Compare this vehicle's degradation curve against others from the same production batch",
    ),
}


def candidates_for(warning_type: str) -> tuple[str, ...]:
    return ACTION_CANDIDATES.get(warning_type, ())
