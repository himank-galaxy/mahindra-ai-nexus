"""
Builds Document #6 from docs/data_required_for_warranty_predictive_model.md
section 6.5: Claim Adjudication Guidelines.

Global, internal-facing document (one instance) - describes the real
evidence-weighing logic this project's synthetic warranty_claims data
was generated under, so a copilot explaining "why was this claim
approved/rejected" can cite an actual rulebook rather than guessing.
"""

from __future__ import annotations

from data.generators.documents.blocks import BulletList, Document, Heading, Paragraph, Table
from data.generators.documents.claim_adjudication_data import (
    DECISION_GUIDE,
    EVIDENCE_FACTORS,
    ROOT_CAUSE_DOMAINS,
)


def build_claim_adjudication_guidelines() -> Document:
    blocks: tuple = (
        Heading("Purpose", level=2),
        Paragraph(
            "This document describes how a warranty claim's evidence is weighed to reach one of three "
            "outcomes - APPROVED, MANUAL_REVIEW, or REJECTED - and how a claim's root-cause domain is "
            "classified. It reflects the actual rules this fleet's warranty-claim data is generated under, "
            "not a general industry standard, and is intended for internal use (e.g. by the Copilot "
            "explaining a claim decision), not customer-facing."
        ),
        Heading("Evidence Factors Considered", level=2),
        BulletList(items=EVIDENCE_FACTORS, ordered=False),
        Heading("Root-Cause Domain Classification", level=2),
        Paragraph("Every claim is classified into exactly one of the following domains:"),
        Table(
            headers=("Domain", "Definition"),
            rows=tuple((d.name, d.definition) for d in ROOT_CAUSE_DOMAINS),
        ),
        Heading("Decision Guide", level=2),
        Paragraph(
            "The following describes, in plain English, how combinations of the evidence factors above tend "
            "to resolve to an outcome. This is a qualitative guide, not an exact formula - the underlying "
            "system computes a continuous evidence-strength score and samples an outcome from it, so any "
            "individual claim can still land differently."
        ),
        Table(
            headers=("Evidence Pattern", "Evidence Strength", "Likely Outcome"),
            rows=DECISION_GUIDE,
        ),
        Heading("A Note On Scope", level=2),
        Paragraph(
            "These rules are synthetic proof-of-concept assumptions used to generate this project's "
            "warranty_claims data - they are not real Mahindra warranty-adjudication policy or actual "
            "operational statistics."
        ),
    )

    return Document(
        doc_type="claim_adjudication_guidelines",
        title="Claim Adjudication Guidelines",
        blocks=blocks,
        vehicle_model=None,
    )
