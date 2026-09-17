"""
Builds Document #12 from docs/data_required_for_warranty_predictive_model.md
section 6.5: Surveyor/Claim Investigation Report - one per real insurance
claim (grain: claim, per the template table in section 6.6).

Every fact in this report is read from the real claim/service/telematics
data, the same "structured data decides, template only renders it"
pattern used throughout this document corpus - nothing here is
generated free-form.
"""

from __future__ import annotations

from data.generators.documents.blocks import Document, Heading, Paragraph, Table
from data.generators.documents.surveyor_report_data import ClaimInvestigation

_SEVERITY_FINDINGS = {
    "LOW": "Minor cosmetic/panel damage consistent with a low-speed impact. No structural or safety-critical "
    "component involvement observed.",
    "MEDIUM": "Moderate damage requiring component replacement, consistent with a moderate-speed impact. "
    "No indication of structural frame damage.",
    "HIGH": "Significant damage consistent with a high-force impact. Structural/safety-critical component "
    "involvement is possible and should be confirmed by a qualified technician before the vehicle returns "
    "to service.",
}

_STATUS_RECOMMENDATION = {
    "APPROVED": "Recommend payout as assessed below - evidence is consistent with a genuine accident claim "
    "within policy terms.",
    "MANUAL_REVIEW": "Recommend holding for manual review - claim value or evidence pattern warrants a "
    "second review before a payout decision is finalised.",
    "REJECTED": "Recommend no payout - evidence or policy terms do not support this claim as assessed.",
}


def build_surveyor_report(investigation: ClaimInvestigation) -> Document:
    claim = investigation.claim
    component = str(claim["supplier_component_category"]).replace("_", " ").title()
    severity = str(claim["severity"])

    blocks: list = [
        Heading("Claim Summary", level=2),
        Paragraph(
            f"Claim {claim['insurance_claim_id']} (Policy {claim['policy_number']}) - "
            f"{claim['vehicle_model_name']} {claim['variant']}, vehicle {claim['vehicle_id']}, "
            f"{claim['odometer_km']:,} km on the odometer at the time of the incident. "
            f"Reported component affected: {component}. Assessed severity: {severity}."
        ),
        Heading("Inspection Findings", level=2),
        Paragraph(_SEVERITY_FINDINGS.get(severity, "Damage assessment on file.")),
    ]

    blocks.append(Heading("Cause Assessment", level=2))
    if investigation.telematics_window is not None:
        peak_impact = float(investigation.telematics_window["impact_g_force"].max())
        min_speed = float(investigation.telematics_window["vehicle_speed_kph"].min())
        blocks.append(
            Paragraph(
                f"ACCIDENT / COLLISION DAMAGE - confirmed by matching telematics evidence (see below). Peak "
                f"recorded impact force during the inspected window: {peak_impact:.2f} g, with vehicle speed "
                f"dropping to {min_speed:.1f} km/h immediately after - a pattern consistent with a collision, "
                "not a mechanical or wear-related failure."
            )
        )
        blocks.append(Heading("Telematics Cross-Reference", level=2))
        blocks.append(
            Paragraph(
                "Recorded vehicle telemetry in the minutes surrounding the reported incident time "
                f"({investigation.accident_at}):"
            )
        )
        rows = tuple(
            (
                str(row["timestamp"]),
                f"{row['vehicle_speed_kph']:.1f}",
                f"{row['impact_g_force']:.2f}",
                f"{row['vertical_acceleration_g']:.2f}",
                f"{row['lateral_acceleration_g']:.2f}",
            )
            for _, row in investigation.telematics_window.iterrows()
        )
        blocks.append(
            Table(
                headers=("Timestamp", "Speed (km/h)", "Impact (g)", "Vertical Accel. (g)", "Lateral Accel. (g)"),
                rows=rows,
            )
        )
    else:
        blocks.append(
            Paragraph(
                "ACCIDENT / COLLISION DAMAGE - assessed from physical inspection and the service record. No "
                "telematics coverage is available for this vehicle at the time of the incident (this fleet's "
                "telematics data covers only a small subset of vehicles for a short window after delivery), "
                "so this assessment relies on physical inspection findings alone, not telematics evidence."
            )
        )
        blocks.append(Heading("Telematics Cross-Reference", level=2))
        blocks.append(
            Paragraph(
                "No telematics data is available for this vehicle at the time of the incident - see the "
                "Warranty-Insurance Boundary Guidelines document's \"A Note On Scope\" section for why."
            )
        )

    blocks.append(Heading("Recommended Payout", level=2))
    approved = float(claim["approved_amount_inr"])
    claimed = float(claim["claim_amount_inr"])
    blocks.append(
        Paragraph(
            f"Assessed claim amount: Rs.{claimed:,.2f}. "
            f"{'Approved amount' if claim['claim_status'] == 'APPROVED' else 'Amount if approved'}: "
            f"Rs.{approved:,.2f}. Status: {claim['claim_status']}. "
            + _STATUS_RECOMMENDATION.get(str(claim["claim_status"]), "")
        )
    )

    return Document(
        doc_type="surveyor_claim_investigation_report",
        title=f"Surveyor Report — Claim {claim['insurance_claim_id']}",
        blocks=tuple(blocks),
        vehicle_model=str(claim["vehicle_model_name"]),
        relevant_issue_categories=("ACCIDENT_DAMAGE",),
        relevant_component_categories=(str(claim["supplier_component_category"]),),
    )
