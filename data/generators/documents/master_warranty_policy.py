"""
Builds Document #1 from docs/data_required_for_warranty_predictive_model.md
section 6.5: the Master Warranty Policy.

One single document, not one per vehicle model: the coverage durations,
exclusion list, and proprietary-items list are all pulled from the same
shared constants in warranty_policy_data.py regardless of model, so a
per-model copy would be word-for-word identical except for the model
name - confirmed by diffing two generated copies before this was
simplified to one document. Model-specific coverage differences (if any
ever exist) belong in the Component-Level Coverage Schedule, which is
already generated per model.

Structure and clause style adapted from a real Mahindra Thar CRDe
Warranty Information & Maintenance Guide (2015) the user supplied -
see warranty_policy_data.py's module docstring for the full grounding.
"""

from __future__ import annotations

from data.generators.documents.blocks import BulletList, Document, Heading, Paragraph
from data.generators.documents.warranty_policy_data import (
    BASE_WARRANTY_KM,
    BASE_WARRANTY_YEARS,
    COMPONENT_COVERAGE,
    EXTENDED_WARRANTY_KM,
    EXTENDED_WARRANTY_YEARS,
    STANDARD_WARRANTY_EXCLUSIONS,
)


def build_master_warranty_policy() -> Document:
    proprietary_categories = [c.category.replace("_", " ").title() for c in COMPONENT_COVERAGE if c.coverage_type == "PROPRIETARY"]

    blocks: tuple = (
        Heading("Coverage Statement", level=2),
        Paragraph(
            "Mahindra & Mahindra Ltd. (\"Company\") warrants each new Mahindra vehicle manufactured by it to "
            "be free from defects in material and workmanship under normal use, as instructed in the Owner's "
            "Manual. Under this warranty, the Company's Authorised Dealer will repair or replace, free of "
            "charge, any part found on examination to be defective in material or workmanship. This policy "
            "applies to every Mahindra model covered by this warranty program; model-specific coverage "
            "differences, where they exist, are listed in that model's Component-Level Coverage Schedule."
        ),
        Paragraph(
            f"Standard Warranty: {BASE_WARRANTY_YEARS} years or {BASE_WARRANTY_KM:,} km from the date of retail "
            "sale to the customer, whichever occurs first."
        ),
        Paragraph(
            f"Extended Warranty (optional, purchased separately): {EXTENDED_WARRANTY_YEARS} years or "
            f"{EXTENDED_WARRANTY_KM:,} km from the date of retail sale to the customer, whichever occurs first."
        ),
        Paragraph(
            "This warranty is limited to the delivery, free of charge at an Authorised Dealer's workshop, of "
            "the part or parts (new or repaired) in exchange for those acknowledged by the Dealer to be "
            "defective. This warranty is in lieu of all other warranties, express or implied, and no person, "
            "agent, or representative of the Company is authorised to give any other warranty on the Company's "
            "behalf."
        ),
        Heading("What Is Not Covered", level=2),
        Paragraph(
            "To provide a clear understanding of this policy, the following are not covered under this warranty:"
        ),
        BulletList(items=STANDARD_WARRANTY_EXCLUSIONS, ordered=True),
        Heading("Proprietary Items", level=2),
        Paragraph(
            "The following items are covered under their respective manufacturers' own warranty policies, not "
            "this vehicle warranty: " + ", ".join(proprietary_categories) + ". See the Component-Level Coverage "
            "Schedule for the specific model for full details of every component category's coverage terms."
        ),
        Heading("Dispute Resolution", level=2),
        Paragraph(
            "Any dispute arising between the Company and the purchaser on the liability of the Company under "
            "this warranty shall be taken up in a Civil court having jurisdiction in Greater Mumbai only."
        ),
    )

    return Document(
        doc_type="master_warranty_policy",
        title="Master Warranty Policy — Mahindra",
        blocks=blocks,
        vehicle_model=None,
        relevant_component_categories=tuple(c.category for c in COMPONENT_COVERAGE),
    )
