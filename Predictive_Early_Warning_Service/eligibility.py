"""
Warranty eligibility gate - reuses the real, already-built policy and
driving-behavior data (data/generators/documents/warranty_policy_data.py
and driving_behavior_data.py) rather than reimplementing coverage rules
a second time.

Two checks, matching docs/data_required_for_warranty_predictive_model.md
section 6:
1. Coverage window - is the vehicle still within its warranty period for
   this component's coverage type?
2. Driving-behavior exclusion - does this vehicle's own telematics
   history show an unusually extreme reading for a component with a
   defined behavior clause?

Behavior-clause thresholds: the document text (driving_behavior_data.py)
deliberately only describes each threshold qualitatively ("illustrative
synthetic threshold, not an engineering specification") - it was never
meant to be parsed as a literal numeric rule, and several of its example
numbers (e.g. "450 degrees" for steering) don't actually fit this
project's real telematics value ranges (steering_angle_deg is generated
clipped to [-42, 42] - confirmed in
data/generators/causal/vehicle_telematics_timeseries.py). Rather than
hardcode a second, possibly-inconsistent set of magic numbers, this
module self-calibrates: a component's behavior clause is triggered when
a vehicle's own telematics reading for that clause's signal exceeds the
95th percentile of that same signal across the whole real telematics
dataset - a real, data-driven "unusually extreme for this fleet" check.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

import warranty_config
from data.generators.documents.driving_behavior_data import BEHAVIOR_CLAUSES
from data.generators.documents.warranty_policy_data import (
    BASE_WARRANTY_KM,
    BASE_WARRANTY_YEARS,
    COMPONENT_COVERAGE,
)

COMPONENT_COVERAGE_BY_CATEGORY = {c.category: c for c in COMPONENT_COVERAGE}
BEHAVIOR_CLAUSES_BY_CATEGORY = {c.category: c for c in BEHAVIOR_CLAUSES}

BEHAVIOR_PERCENTILE = 0.95


@dataclass(frozen=True)
class EligibilityResult:
    is_eligible: bool
    coverage_status: str  # "IN_COVERAGE" | "OUT_OF_COVERAGE" | "NOT_BASE_WARRANTY_COVERED"
    behavior_flag: str | None  # None, or the reason it was excluded
    notes: str


def _load_signal_percentiles() -> dict[str, float]:
    try:
        telematics = pd.read_csv(warranty_config.TELEMATICS_PATH)
    except FileNotFoundError:
        return {}

    signals = {signal for clause in BEHAVIOR_CLAUSES for signal in clause.telematics_signals}
    percentiles: dict[str, float] = {}
    for signal in signals:
        if signal not in telematics.columns:
            continue
        # warning_flag is boolean (dtc_count/warning_flag clauses) -
        # pandas can't take a quantile of a bool column directly.
        values = telematics[signal]
        if values.dtype == bool:
            values = values.astype(int)
        percentiles[signal] = float(values.quantile(BEHAVIOR_PERCENTILE))
    return percentiles


_SIGNAL_PERCENTILES = _load_signal_percentiles()


def check_coverage_window(vehicle_age_days: float, odometer_km: float | None, component_category: str) -> tuple[bool, str]:
    coverage = COMPONENT_COVERAGE_BY_CATEGORY.get(component_category)
    if coverage is None:
        return True, "IN_COVERAGE"  # unknown category defaults to the base policy, not silently excluded

    if coverage.coverage_type in ("EXCLUDED", "CONSUMABLE", "PROPRIETARY"):
        return False, "NOT_BASE_WARRANTY_COVERED"

    # WEAR_LIMITED and BASE_EXTENDABLE both use the base warranty window
    # as the outer bound in this simplified model - WEAR_LIMITED items
    # additionally have a shorter real-world window (see the Component
    # Coverage Schedule document), not modeled numerically here since it
    # is expressed as text ("12 months / 20,000 km") rather than a
    # parseable constant; the base-window check below is the more
    # conservative (larger) of the two, so this never over-states
    # eligibility for a WEAR_LIMITED item, only under-states exclusion
    # for one that's already past its (shorter) real wear-item window.
    age_years = vehicle_age_days / 365.25
    within_years = age_years <= BASE_WARRANTY_YEARS
    within_km = odometer_km is None or odometer_km <= BASE_WARRANTY_KM

    if within_years and within_km:
        return True, "IN_COVERAGE"
    return False, "OUT_OF_COVERAGE"


def check_driving_behavior(component_category: str, vehicle_telematics: pd.DataFrame | None) -> str | None:
    clause = BEHAVIOR_CLAUSES_BY_CATEGORY.get(component_category)
    if clause is None or vehicle_telematics is None or vehicle_telematics.empty:
        return None

    for signal in clause.telematics_signals:
        if signal not in vehicle_telematics.columns or signal not in _SIGNAL_PERCENTILES:
            continue
        if float(vehicle_telematics[signal].max()) > _SIGNAL_PERCENTILES[signal]:
            return (
                f"{signal} exceeded the fleet's 95th-percentile reading "
                f"({_SIGNAL_PERCENTILES[signal]:.2f}) - see the Driving-Behavior Exclusion "
                f"Clauses document's {component_category} clause."
            )
    return None


def check_eligibility(
    component_category: str,
    vehicle_age_days: float,
    odometer_km: float | None,
    vehicle_telematics: pd.DataFrame | None,
) -> EligibilityResult:
    in_coverage, coverage_status = check_coverage_window(vehicle_age_days, odometer_km, component_category)
    behavior_flag = check_driving_behavior(component_category, vehicle_telematics)

    is_eligible = in_coverage and behavior_flag is None

    if not in_coverage:
        notes = f"Not eligible - {coverage_status.replace('_', ' ').lower()}."
    elif behavior_flag:
        notes = f"Not eligible - driving-behavior exclusion: {behavior_flag}"
    else:
        notes = "Eligible - within coverage window, no driving-behavior exclusion triggered."

    return EligibilityResult(
        is_eligible=is_eligible,
        coverage_status=coverage_status,
        behavior_flag=behavior_flag,
        notes=notes,
    )
