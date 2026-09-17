"""
Builds Document #8 from docs/data_required_for_warranty_predictive_model.md
section 6.5: Motor Insurance Policy Certificate - one per insured vehicle
(grain: vehicle/policy, per the template table in section 6.6).
"""

from __future__ import annotations

from data.generators.documents.blocks import Document, Heading, Paragraph, Table
from data.generators.documents.insurance_policy_data import VehiclePolicy


def build_insurance_policy_certificate(policy: VehiclePolicy) -> Document:
    blocks: tuple = (
        Heading("Policy Details", level=2),
        Table(
            headers=("Field", "Value"),
            rows=(
                ("Policy Number", policy.policy_number),
                ("Vehicle", f"{policy.vehicle_model_name} ({policy.variant})"),
                ("Vehicle ID", policy.vehicle_id),
                ("Cover Type", policy.cover_type),
                ("Policy Period", f"{policy.policy_start_date.date()} to {policy.policy_end_date.date()}"),
            ),
        ),
        Heading("Sum Insured (IDV)", level=2),
        Paragraph(
            f"Insured Declared Value (IDV): Rs.{policy.idv_inr:,.2f}, calculated from the vehicle's ex-showroom "
            f"price (Rs.{policy.base_price_inr:,.2f}) less {policy.depreciation_rate * 100:.0f}% depreciation "
            "for vehicle age, per the standard IRDAI depreciation schedule for private cars."
        ),
        Heading("Premium", level=2),
        Table(
            headers=("Component", "Amount (INR)"),
            rows=(
                ("Own Damage Premium", f"{policy.own_damage_premium_inr:,.2f}"),
                ("Third-Party Premium", f"{policy.third_party_premium_inr:,.2f}"),
                ("Total Premium", f"{policy.total_premium_inr:,.2f}"),
            ),
        ),
        Heading("Deductible", level=2),
        Paragraph(
            f"Compulsory deductible: Rs.{policy.deductible_inr:,.2f} per own-damage claim - this amount is "
            "borne by the policyholder and deducted from any approved claim payout before settlement."
        ),
        Heading("A Note On Scope", level=2),
        Paragraph(
            "IDV, premium, and deductible figures above are computed from this vehicle's real model price and "
            "delivery date using the real IRDAI depreciation schedule, but the premium rate and deductible "
            "tiers themselves are simplified synthetic PoC assumptions, not actual insurer pricing filings."
        ),
    )

    return Document(
        doc_type="motor_insurance_policy_certificate",
        title=f"Motor Insurance Policy Certificate — {policy.policy_number}",
        blocks=blocks,
        vehicle_model=policy.vehicle_model_name,
    )
