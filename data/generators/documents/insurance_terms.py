"""
Builds Document #9 from docs/data_required_for_warranty_predictive_model.md
section 6.5: Insurance Terms & Conditions. Global document (one instance).
"""

from __future__ import annotations

from data.generators.documents.blocks import BulletList, Document, Heading, Paragraph
from data.generators.documents.insurance_terms_data import COVERED_PERILS, STANDARD_EXCLUSIONS


def build_insurance_terms() -> Document:
    blocks: tuple = (
        Heading("Scope Of Cover", level=2),
        Paragraph(
            "This comprehensive motor insurance policy covers accidental loss or damage to the insured "
            "vehicle, and the policyholder's legal liability to third parties, as set out below."
        ),
        Heading("Covered Perils", level=2),
        BulletList(items=COVERED_PERILS, ordered=False),
        Heading("What Is Not Covered", level=2),
        Paragraph("The following are excluded from this policy:"),
        BulletList(items=STANDARD_EXCLUSIONS, ordered=True),
        Heading("Warranty-Insurance Boundary", level=2),
        Paragraph(
            "Mechanical or electrical breakdown is explicitly excluded from this insurance policy - such "
            "issues are a manufacturing-warranty matter, covered (if at all) under the vehicle's Master "
            "Warranty Policy, not this insurance policy. See the Warranty-Insurance Boundary Guidelines "
            "document for the full decision tree used to route a reported issue to the correct process."
        ),
        Heading("Claim Procedure", level=2),
        Paragraph(
            "In the event of a claim, the policyholder must: (1) notify the insurer as soon as reasonably "
            "possible after the incident, (2) not admit liability or make any offer of settlement without "
            "the insurer's consent, (3) allow the insurer's surveyor to inspect the vehicle before repairs "
            "begin (see the Surveyor/Claim Investigation Report document), and (4) provide all requested "
            "documentation, including the registration certificate, driving license, and FIR/police report "
            "where applicable."
        ),
    )

    return Document(
        doc_type="insurance_terms_and_conditions",
        title="Insurance Terms & Conditions",
        blocks=blocks,
        vehicle_model=None,
    )
