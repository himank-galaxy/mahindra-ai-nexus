"""
Builds Document #11 from docs/data_required_for_warranty_predictive_model.md
section 6.5: Claims History / No-Claim-Bonus Statement - one per insured
vehicle/policy (grain: policy, per renewal cycle).

NCB slabs below are the real, standard IRDAI No-Claim-Bonus schedule for
private cars (0% in year 1, then 20/25/35/45/50% for consecutive
claim-free renewal years) - not invented. Every policy in this fleet's
data is a first-year policy (no renewal has happened yet - see
insurance_policy_data.py), so every statement reports the same real
rule: 0% now, and what the vehicle becomes eligible for at its first
renewal depends on whether it filed a claim this year.
"""

from __future__ import annotations

from data.generators.documents.blocks import Document, Heading, Paragraph, Table
from data.generators.documents.insurance_policy_data import VehiclePolicy

NCB_SLABS_BY_CLAIM_FREE_YEARS = {1: 0.20, 2: 0.25, 3: 0.35, 4: 0.45, 5: 0.50}


def build_claims_history_ncb(policy: VehiclePolicy, claims: list[dict]) -> Document:
    has_claim_this_period = len(claims) > 0
    next_renewal_ncb = 0.0 if has_claim_this_period else NCB_SLABS_BY_CLAIM_FREE_YEARS[1]

    claim_rows = tuple(
        (
            str(claim["insurance_claim_id"]),
            str(claim["claim_submitted_at"])[:10],
            str(claim["supplier_component_category"]).replace("_", " ").title(),
            f"{float(claim['claim_amount_inr']):,.2f}",
            str(claim["claim_status"]),
        )
        for claim in claims
    )

    blocks: list = [
        Heading("Policy", level=2),
        Paragraph(
            f"{policy.policy_number} — {policy.vehicle_model_name} ({policy.variant}), "
            f"current policy period {policy.policy_start_date.date()} to {policy.policy_end_date.date()}."
        ),
        Heading("Claims Filed This Policy Period", level=2),
    ]

    if claim_rows:
        blocks.append(
            Table(headers=("Claim ID", "Date Filed", "Component", "Amount (INR)", "Status"), rows=claim_rows)
        )
    else:
        blocks.append(Paragraph("No claims filed during this policy period."))

    blocks += [
        Heading("No-Claim-Bonus Status", level=2),
        Paragraph(
            "This is a first-year policy - no renewal has occurred yet, so the current NCB is 0%, per the "
            "standard IRDAI schedule (No-Claim-Bonus only begins accruing from the first claim-free renewal)."
        ),
        Paragraph(
            (
                f"Because {'a claim was' if has_claim_this_period else 'no claim was'} filed during this policy "
                f"period, this vehicle is projected to renew at {next_renewal_ncb * 100:.0f}% NCB "
                f"{'(NCB resets to 0% after any claim, per standard policy terms)' if has_claim_this_period else '(the standard first-year claim-free step)'}."
            )
        ),
    ]

    return Document(
        doc_type="claims_history_ncb_statement",
        title=f"Claims History / NCB Statement — {policy.policy_number}",
        blocks=tuple(blocks),
        vehicle_model=policy.vehicle_model_name,
    )
