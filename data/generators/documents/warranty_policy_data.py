"""
Synthetic warranty-policy reference data shared by the Master Warranty
Policy and Component-Level Coverage Schedule document generators.

Grounding for these numbers/structure:
- Coverage durations (3 years/120,000 km base, 5 years/150,000 km
  extended) are the current real Mahindra terms the user supplied from
  their own research - NOT invented for this PoC.
- Clause structure, exclusion style, and the "blanket coverage + a short
  proprietary/wear exceptions list" pattern are adapted from a real
  Mahindra Thar CRDe Warranty Information & Maintenance Guide (2015)
  the user supplied - see docs/data_required_for_warranty_predictive_model.md
  section 6.6 for the full reasoning.
- The 19-value supplier_component_category list matches the live
  `mahindra_ai` database (warranty_claims.supplier_component_category),
  confirmed directly against real data, not assumed.

All specific numbers below (durations, mileage exceptions) beyond the
two real figures above are synthetic PoC assumptions, clearly not
official Mahindra policy for every component.
"""

from __future__ import annotations

from dataclasses import dataclass

BASE_WARRANTY_YEARS = 3
BASE_WARRANTY_KM = 120_000

EXTENDED_WARRANTY_YEARS = 5
EXTENDED_WARRANTY_KM = 150_000

BATTERY_WARRANTY_MONTHS_FROM_SALE = 12
BATTERY_WARRANTY_MONTHS_FROM_MANUFACTURE = 15


@dataclass(frozen=True)
class ComponentCoverage:
    category: str
    coverage_type: str  # "BASE_EXTENDABLE" | "PROPRIETARY" | "WEAR_LIMITED" | "EXCLUDED" | "CONSUMABLE"
    duration_text: str
    notes: str


# Ordered to match the live database's supplier_component_category values.
COMPONENT_COVERAGE: tuple[ComponentCoverage, ...] = (
    ComponentCoverage(
        "BATTERY", "PROPRIETARY",
        f"{BATTERY_WARRANTY_MONTHS_FROM_SALE} months from date of sale or "
        f"{BATTERY_WARRANTY_MONTHS_FROM_MANUFACTURE} months from date of manufacture, whichever is earlier",
        "Covered under the battery manufacturer's own warranty, not the vehicle's base/extended warranty. "
        "Does not cover damage from irregular servicing, negligent maintenance, or wilful abuse.",
    ),
    ComponentCoverage(
        "BRAKING_SYSTEM", "BASE_EXTENDABLE", "Base warranty duration (extendable)",
        "Covers manufacturing defects in braking system components. Brake pads/linings are wear items and "
        "are excluded once worn through normal use.",
    ),
    ComponentCoverage(
        "STEERING", "BASE_EXTENDABLE", "Base warranty duration (extendable)",
        "Covers manufacturing defects in steering system components.",
    ),
    ComponentCoverage(
        "SUSPENSION", "BASE_EXTENDABLE", "Base warranty duration (extendable)",
        "Covers manufacturing defects in suspension components. Bushings are inspected periodically per "
        "the maintenance schedule and are excluded once worn through normal use.",
    ),
    ComponentCoverage(
        "DRIVETRAIN_COMPONENTS", "BASE_EXTENDABLE", "Base warranty duration (extendable)",
        "Covers manufacturing defects in drivetrain components.",
    ),
    ComponentCoverage(
        "ECU_ELECTRONICS", "BASE_EXTENDABLE", "Base warranty duration (extendable)",
        "Covers manufacturing defects in ECUs, controllers, sensors and related electronics.",
    ),
    ComponentCoverage(
        "ELECTRICAL_WIRING", "BASE_EXTENDABLE", "Base warranty duration (extendable)",
        "Covers manufacturing defects in the wiring harness. Damage from unauthorized tapping/cutting of "
        "wiring for aftermarket accessories is excluded.",
    ),
    ComponentCoverage(
        "EXHAUST", "BASE_EXTENDABLE", "Base warranty duration (extendable)",
        "Covers manufacturing defects in the exhaust system. Corrosion from external damage or road debris "
        "impact is excluded.",
    ),
    ComponentCoverage(
        "HVAC", "BASE_EXTENDABLE", "Base warranty duration (extendable)",
        "Covers manufacturing defects in the HVAC system.",
    ),
    ComponentCoverage(
        "LIGHTING", "BASE_EXTENDABLE", "Base warranty duration (extendable)",
        "Covers manufacturing defects in lighting assemblies. Fused bulbs and fuses are not covered under warranty.",
    ),
    ComponentCoverage(
        "SEATING", "BASE_EXTENDABLE", "Base warranty duration (extendable)",
        "Covers manufacturing defects in seating structure and mechanisms. Soiling, wear, or tearing of seat "
        "trim from normal use is excluded.",
    ),
    ComponentCoverage(
        "STEEL_BODY_PANELS", "BASE_EXTENDABLE", "Base warranty duration (extendable)",
        "Covers manufacturing defects in body panels. Corrosion resulting from holes drilled for accessory "
        "fitment, and dents/scratches from external causes, are excluded.",
    ),
    ComponentCoverage(
        "GLASS", "EXCLUDED", "Not covered",
        "Door glass and windshield glass breakage are not covered under warranty regardless of cause.",
    ),
    ComponentCoverage(
        "RUBBER_SEALS", "WEAR_LIMITED", "12 months / 20,000 km",
        "Covers manufacturing defects only. Normal deterioration due to use and exposure is excluded beyond "
        "this shorter window.",
    ),
    ComponentCoverage(
        "FASTENERS", "WEAR_LIMITED", "12 months / 20,000 km",
        "Covers manufacturing defects only. Loosening from normal use/vibration is addressed under scheduled "
        "maintenance (bolt-torque checks), not warranty.",
    ),
    ComponentCoverage(
        "ADHESIVES", "WEAR_LIMITED", "12 months / 20,000 km",
        "Covers manufacturing defects (bonding failure) only. Damage from improper removal/installation of "
        "trim is excluded.",
    ),
    ComponentCoverage(
        "PLASTIC_TRIM", "WEAR_LIMITED", "12 months / 20,000 km",
        "Covers manufacturing defects only. Cracking or damage caused by improper removal/installation is excluded.",
    ),
    ComponentCoverage(
        "FLUIDS", "CONSUMABLE", "Not covered (consumable)",
        "Engine oil, coolant, brake/clutch fluid and similar fluids are consumables replaced at scheduled "
        "service intervals and are not a warranty matter.",
    ),
    ComponentCoverage(
        "TYRES", "PROPRIETARY", "Covered by tyre manufacturer only",
        "Tyres are covered under the respective tyre manufacturer's own warranty policy, not Mahindra's "
        "vehicle warranty. The tyre manufacturer's decision on any claim is final and binding.",
    ),
)


STANDARD_WARRANTY_EXCLUSIONS: tuple[str, ...] = (
    "Preventive maintenance services (free and paid), as specified in the maintenance schedule, are an "
    "absolute prerequisite for warranty coverage. If a scheduled service is not availed of at the specified "
    "kms/time and a complaint is found to result from non-availing of that service, no warranty consideration "
    "will be given.",
    "Deterioration of appearance items and trim due to normal exposure or use is not covered.",
    "Door glass/windshield glass breakage, fused bulbs and fuses are not covered.",
    "Repairs necessitated by unauthorized modifications that affect the stability or reliability of the "
    "vehicle are not covered.",
    "Repairs required because of accident, misuse, abuse, or neglect are not covered.",
    "Repairs carried out with non-genuine parts which, in the company's judgment, affect reliability are not "
    "covered.",
    "Contingent expenses - towing/transportation to the nearest authorised dealer, telephone expenses, fuel "
    "cost, and loss due to the vehicle being out of commission - are not covered.",
    "Continued use of the vehicle despite knowledge that a defect exists will make the warranty void for the "
    "resulting damage.",
    "The company takes no responsibility for consequential damage or injury resulting from fitment of "
    "unauthorised aftermarket accessories or tapping/cutting wires in the wiring harness.",
    "Damage resulting from natural disasters, and any secondary/consequential damage, is not covered.",
    "Liabilities or losses due to riots, terrorist activity, mutiny, or similar events are not covered.",
    "Driving-behavior exclusion: repairs to a specific component are not covered where telematics data for "
    "the vehicle indicates sustained usage beyond manufacturer-specified thresholds for that component "
    "(e.g. sustained harsh-impact/off-road driving for suspension, excessive steering-angle-rate events for "
    "the steering system) in the period leading up to the failure - see the Driving-Behavior Exclusion "
    "Clauses document for the specific thresholds per component.",
)


def format_component_coverage_table() -> tuple[tuple[str, ...], ...]:
    """Returns the component coverage table as (category, duration, notes) rows,
    used by both the Component-Level Coverage Schedule document and the Master
    Warranty Policy's summary reference."""

    return tuple(
        (c.category.replace("_", " ").title(), c.duration_text, c.notes)
        for c in COMPONENT_COVERAGE
    )
