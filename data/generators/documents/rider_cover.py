"""
Builds Document #10 from docs/data_required_for_warranty_predictive_model.md
section 6.5: Add-on/Rider Cover Documents. Global document (one instance
listing every rider, per the template table's note that global documents
are one instance, not one per rider type - a separate file per rider
would be six near-empty documents for no benefit here).
"""

from __future__ import annotations

from data.generators.documents.blocks import Document, Heading, Paragraph, Table
from data.generators.documents.rider_cover_data import RIDER_COVERS


def build_rider_cover_document() -> Document:
    blocks: list = [
        Heading("Purpose", level=2),
        Paragraph(
            "Add-on/rider covers extend a base comprehensive motor insurance policy with additional, "
            "optional protection. Each is priced as an additional percentage of the own-damage premium "
            "(see the Motor Insurance Policy Certificate document for a specific vehicle's own-damage "
            "premium) unless noted as a flat fee."
        ),
    ]

    for rider in RIDER_COVERS:
        blocks.append(Heading(rider.name, level=2))
        blocks.append(Paragraph(rider.description))
        blocks.append(
            Table(
                headers=("Premium Delta", "Eligibility"),
                rows=((rider.premium_delta_pct_of_od, rider.eligibility),),
            )
        )

    blocks.append(Heading("A Note On Scope", level=2))
    blocks.append(
        Paragraph(
            "Premium-delta percentages and eligibility conditions above are simplified synthetic PoC "
            "assumptions - real insurers vary these by vehicle age, model, and their own pricing filings."
        )
    )

    return Document(
        doc_type="addon_rider_cover",
        title="Add-on / Rider Cover Documents",
        blocks=tuple(blocks),
        vehicle_model=None,
    )
