"""
Synthetic data for Document #6 (docs/data_required_for_warranty_predictive_model.md
section 6.5): Claim Adjudication Guidelines.

Grounded directly in the real decision logic already used by this
project's warranty-claim generator
(data/generators/auto/warranty.py: _derive_claim_decision and
_derive_root_cause_domain) - this document describes the actual rules
this fleet's synthetic warranty_claims data was generated under, not an
invented rulebook. Like that generator's own docstring says, these are
synthetic PoC assumptions, not real Mahindra adjudication policy -
repeated here for the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass

PRODUCTION_QUALITY_REFERENCE = 0.95
SUPPLIER_QUALITY_REFERENCE = 0.90


@dataclass(frozen=True)
class RootCauseDomain:
    name: str
    definition: str


ROOT_CAUSE_DOMAINS: tuple[RootCauseDomain, ...] = (
    RootCauseDomain(
        "SUPPLIER_QUALITY",
        "The supplier lot behind the failed part scored below the supplier-quality reference "
        f"({SUPPLIER_QUALITY_REFERENCE}) and no other evidence factor is also implicated.",
    ),
    RootCauseDomain(
        "MANUFACTURING_QUALITY",
        "The production batch scored below the production-quality reference "
        f"({PRODUCTION_QUALITY_REFERENCE}) and no other evidence factor is also implicated.",
    ),
    RootCauseDomain(
        "COMPONENT_FAILURE",
        "The reported issue category is a recognised component-failure type (e.g. battery, brake, ECU, "
        "electrical, HVAC, steering, suspension, tyre, drivetrain, exhaust, lighting, or fluid-related) and "
        "no supplier- or production-quality evidence is implicated.",
    ),
    RootCauseDomain(
        "MULTIPLE_FACTORS",
        "Two or more of the above (supplier quality, production quality, component-failure category) are "
        "implicated at once - the most common real-world case, and treated as such here.",
    ),
    RootCauseDomain(
        "SERVICE_DIAGNOSIS",
        "None of the above evidence factors are implicated - the issue is attributed to the service "
        "diagnosis itself rather than a traceable manufacturing/supplier/component cause.",
    ),
)

EVIDENCE_FACTORS: tuple[str, ...] = (
    "Severity of the reported issue (HIGH / MEDIUM / LOW) - the single strongest factor.",
    f"Supplier lot quality score, relative to the {SUPPLIER_QUALITY_REFERENCE} reference - a lot scoring "
    "below this reference adds supporting evidence for the claim.",
    f"Production batch quality score, relative to the {PRODUCTION_QUALITY_REFERENCE} reference - a batch "
    "scoring below this reference adds supporting evidence for the claim.",
    "Claim amount - a very large claim amount is treated as a weak negative factor (large claims get "
    "slightly more scrutiny, not an automatic red flag).",
)

DECISION_GUIDE: tuple[tuple[str, str, str], ...] = (
    (
        "HIGH severity, supplier lot AND production batch both below reference",
        "Strong evidence",
        "Most likely APPROVED - this is the strongest evidentiary combination the system recognises.",
    ),
    (
        "HIGH severity, only one of supplier lot / production batch below reference",
        "Moderate-strong evidence",
        "Likely APPROVED, with a real but smaller chance of MANUAL_REVIEW.",
    ),
    (
        "MEDIUM severity, at least one quality reference missed",
        "Moderate evidence",
        "Split between APPROVED and MANUAL_REVIEW, leaning APPROVED.",
    ),
    (
        "LOW severity, no quality reference missed",
        "Weak evidence",
        "Most likely to see MANUAL_REVIEW or REJECTED among the three outcomes.",
    ),
    (
        "Any severity, unusually large claim amount",
        "Evidence slightly weakened",
        "Slightly increases the chance of MANUAL_REVIEW or REJECTED relative to an otherwise-identical "
        "smaller claim - large claims are not rejected outright, just reviewed more carefully.",
    ),
)
