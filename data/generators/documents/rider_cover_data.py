"""
Synthetic data for Document #10 (docs/data_required_for_warranty_predictive_model.md
section 6.5): Add-on/Rider Cover Documents.

The six riders below are real, standard add-on covers commonly offered
alongside comprehensive private-car motor insurance in India - not
invented categories. Premium-delta percentages and eligibility
conditions are simplified, explicitly-flagged synthetic PoC assumptions
(real insurers vary these by vehicle age, model, and their own pricing).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiderCover:
    name: str
    description: str
    premium_delta_pct_of_od: str  # as % of the own-damage premium
    eligibility: str


RIDER_COVERS: tuple[RiderCover, ...] = (
    RiderCover(
        "Zero Depreciation Cover",
        "Waives the standard depreciation deduction on plastic, rubber, fibre, and metal parts when "
        "settling an own-damage claim - the policyholder receives the full replacement cost instead of a "
        "depreciated amount.",
        "15-20%",
        "Typically available only for vehicles up to 5 years old, and usually capped at 2-4 claims per "
        "policy year.",
    ),
    RiderCover(
        "Engine Protection Cover",
        "Covers damage to the engine and its internal parts from water ingress (hydrostatic lock), oil "
        "leakage, or damage to gearbox/transmission components - damage the base policy would otherwise "
        "treat as a mechanical-breakdown exclusion.",
        "8-12%",
        "Recommended for vehicles in flood-prone regions; typically available for vehicles up to 5 years old.",
    ),
    RiderCover(
        "Roadside Assistance (RSA)",
        "24x7 assistance for towing, flat-tyre change, battery jump-start, minor on-site repair, fuel "
        "delivery, and key-lockout support.",
        "Flat fee, ~Rs.500-1,500/year",
        "Available on any comprehensive policy, regardless of vehicle age.",
    ),
    RiderCover(
        "Return To Invoice (RTI)",
        "In the event of total loss or theft, pays the original invoice price of the vehicle (including "
        "registration and road tax) instead of the depreciated IDV.",
        "10-15%",
        "Typically available only for vehicles up to 3 years old.",
    ),
    RiderCover(
        "Consumables Cover",
        "Covers the cost of consumable items used during a covered repair - engine oil, nuts and bolts, "
        "grease, washers, and similar items that the base policy does not reimburse.",
        "5-8%",
        "Available on any comprehensive policy.",
    ),
    RiderCover(
        "No-Claim-Bonus Protection",
        "Allows the policyholder to make a limited number of claims in a policy year without losing their "
        "accumulated No-Claim-Bonus at the next renewal - see the Claims History / NCB Statement document.",
        "5-7%",
        "Typically available only to policyholders who already hold NCB of 20% or higher.",
    ),
)
