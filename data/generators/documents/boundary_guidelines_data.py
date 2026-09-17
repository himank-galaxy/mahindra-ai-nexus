"""
Synthetic data for Document #13 (docs/data_required_for_warranty_predictive_model.md
section 6.5): Warranty-Insurance Boundary Guidelines.

The 26 issue_category values below match the live `mahindra_ai` database
(warranty_claims.issue_category), confirmed directly against real data
earlier in this project (see docs/data_required_for_warranty_predictive_model.md
section 3) - not re-derived from the generator's full ~40-value candidate
list in data/generators/auto/service.py's COMPONENT_ISSUE_MAP, which
includes several categories that haven't actually appeared in a claim yet
given the current small sample size.

ACCIDENT_DAMAGE is listed separately below: it did not exist anywhere in
this fleet's data when this document was first written (that was the
main finding at the time - see git history / prior conversation). It now
does: data/generators/auto/service.py's generate_accident_service_events
and generate_telematics_linked_accident_events, plus
data/generators/auto/insurance.py's generate_insurance_claims, produced
real accident-caused service events and real insurance claims from them
(see boundary_guidelines.py for the current real counts). This is the
one category that routes to INSURANCE rather than WARRANTY.
"""

from __future__ import annotations

# Every one of these is a quality/wear/electrical/noise-pattern category -
# none is accident/collision-type by definition.
ISSUE_CATEGORIES: tuple[str, ...] = (
    "BATTERY_WARNING",
    "BODY_ALIGNMENT",
    "BONDING_DEFECT",
    "BRAKE_NOISE",
    "ELECTRICAL_WARNING",
    "ELECTRONIC_CONTROL",
    "EXHAUST_NOISE",
    "EXHAUST_WARNING",
    "FASTENER_LOOSENESS",
    "FLUID_LEVEL",
    "GLASS_ALIGNMENT",
    "HVAC_NOISE",
    "INTERIOR_RATTLE",
    "INTERMITTENT_ELECTRICAL",
    "LIGHTING_FAULT",
    "LIGHT_ALIGNMENT",
    "POWER_DELIVERY",
    "RATTLE_NOISE",
    "RIDE_QUALITY",
    "SEAT_NOISE",
    "STEERING_FEEL",
    "STEERING_NOISE",
    "TRIM_SEPARATION",
    "TYRE_VIBRATION",
    "TYRE_WEAR",
    "WATER_SEALING",
)

# The one category that routes to INSURANCE, not WARRANTY - kept
# separate from ISSUE_CATEGORIES above since it has different default
# routing and reasoning, not just a different name.
ACCIDENT_ISSUE_CATEGORY = "ACCIDENT_DAMAGE"
