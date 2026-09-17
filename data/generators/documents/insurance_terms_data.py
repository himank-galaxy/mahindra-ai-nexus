"""
Synthetic data for Document #9 (docs/data_required_for_warranty_predictive_model.md
section 6.5): Insurance Terms & Conditions.

Covered perils and exclusions below reflect standard IRDAI-regulated
comprehensive private-car motor insurance wording in India (real
industry-standard categories, not invented) - the same grounding
approach already used for the Master Warranty Policy (adapted from a
real Mahindra document). Exact clause phrasing is written for this
project, not copied from any specific insurer's filed wording.
"""

from __future__ import annotations

COVERED_PERILS: tuple[str, ...] = (
    "Accidental damage from collision, overturning, or self-caused impact",
    "Fire, explosion, or self-ignition",
    "Lightning",
    "Burglary, housebreaking, or theft",
    "Riot and strike",
    "Earthquake (fire and shock damage)",
    "Flood, typhoon, hurricane, storm, or inundation",
    "Terrorism (where opted as an add-on)",
    "Damage in transit by road, rail, inland waterway, lift, elevator, or air",
    "Malicious act by a third party",
    "Third-party legal liability - bodily injury or death",
    "Third-party legal liability - property damage",
)

STANDARD_EXCLUSIONS: tuple[str, ...] = (
    "Normal wear and tear, and gradual deterioration of the vehicle.",
    "Mechanical or electrical breakdown, failure, or malfunction - this is a manufacturing-warranty matter, "
    "not an insurance matter. See the Warranty-Insurance Boundary Guidelines document for how a claim is "
    "routed between the two.",
    "Depreciation of the vehicle's value, except as covered by an opted Zero Depreciation add-on cover.",
    "Consequential loss of any kind arising from the incident.",
    "Damage while the vehicle is driven without a valid driving license.",
    "Damage while the driver is under the influence of alcohol or drugs.",
    "Use of the vehicle for a purpose other than what is declared on the policy (e.g. undeclared commercial "
    "use of a private-registered vehicle).",
    "Loss or damage caused by war, invasion, act of foreign enemy, or nuclear risk.",
    "Any contractual liability not otherwise covered under this policy.",
    "Loss or damage to tyres and tubes, unless the vehicle itself is damaged in the same incident, in which "
    "case liability is limited to 50% of the claim for tyres/tubes.",
)
