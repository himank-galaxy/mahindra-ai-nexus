"""
Builds Document #5 from docs/data_required_for_warranty_predictive_model.md
section 6.5: Maintenance/Service Compliance.

Global document (one instance, not per vehicle model) - the underlying
compliance rule (data/generators/auto/service.py's FIRST_INSPECTION
window) is not model-specific in this project's actual synthetic data,
so generating five near-identical per-model copies would misrepresent
what the data supports. This is a deliberate deviation from the "grain:
model" originally sketched in docs/.../section 6.6's template table -
noted there when this document was implemented.
"""

from __future__ import annotations

from data.generators.documents.blocks import BulletList, Document, Heading, Paragraph
from data.generators.documents.maintenance_compliance_data import (
    CRITICAL_SERVICE_ITEMS,
    FIRST_INSPECTION_MAX_DAYS,
    FIRST_INSPECTION_MIN_DAYS,
    FIRST_INSPECTION_REAL_ATTENDANCE_RATE,
)


def build_maintenance_compliance() -> Document:
    missed_rate_pct = round((1 - FIRST_INSPECTION_REAL_ATTENDANCE_RATE) * 100)

    blocks: tuple = (
        Heading("Scheduled Maintenance Requirement", level=2),
        Paragraph(
            f"Every vehicle must attend a First Inspection service between {FIRST_INSPECTION_MIN_DAYS} and "
            f"{FIRST_INSPECTION_MAX_DAYS} days after delivery, at any Mahindra Authorised Dealer or Service "
            "Centre. This is the scheduled maintenance checkpoint tracked against warranty eligibility for "
            "every vehicle in the fleet."
        ),
        Paragraph(
            f"Historically, approximately {missed_rate_pct}% of vehicles do not attend this First Inspection "
            "within the required window. This is a real, measured non-compliance rate from this fleet's "
            "service history, not an assumption - and is the population the warranty eligibility check in "
            "section 6.1 of the requirements plan needs to be able to identify."
        ),
        Heading("Consequence of a Missed Service", level=2),
        Paragraph(
            "As stated in the Master Warranty Policy's exclusion list: if a scheduled service is not availed "
            "of within the specified window and a later complaint is found to result from non-availing of "
            "that service, no warranty consideration will be given for that complaint. A missed First "
            "Inspection does not automatically void the entire warranty - it removes coverage specifically "
            "for issues traceable to the lack of that inspection (e.g. an early-life defect that inspection "
            "would normally have caught)."
        ),
        Heading("Critical Service Checklist", level=2),
        Paragraph(
            "The following items, drawn from the maintenance schedule, are checked at the First Inspection "
            "and are the ones most commonly linked to early-life warranty claims when skipped:"
        ),
        BulletList(items=CRITICAL_SERVICE_ITEMS, ordered=False),
        Heading("Where This Is Recorded", level=2),
        Paragraph(
            "Service attendance is recorded in this fleet's service_events data as a "
            "service_type=FIRST_INSPECTION record for the vehicle. A vehicle with no such record within the "
            f"{FIRST_INSPECTION_MIN_DAYS}-{FIRST_INSPECTION_MAX_DAYS} day window is a missed-service case for "
            "the purposes of warranty eligibility checking."
        ),
        Heading("A Note On Scope", level=2),
        Paragraph(
            "This fleet's data currently models one scheduled maintenance checkpoint (First Inspection). Real "
            "Mahindra practice includes a fuller multi-visit schedule (free and paid services at successive "
            "odometer milestones). Extending this document and the eligibility check to a fuller schedule "
            "would first require the underlying service-event data to model those additional scheduled visits."
        ),
    )

    return Document(
        doc_type="maintenance_service_compliance",
        title="Maintenance / Service Compliance Requirements",
        blocks=blocks,
        vehicle_model=None,
    )
