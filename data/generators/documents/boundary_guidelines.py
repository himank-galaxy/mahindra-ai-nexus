"""
Builds Document #13 from docs/data_required_for_warranty_predictive_model.md
section 6.5: Warranty-Insurance Boundary Guidelines.

Global document (one instance). This document originally reported a real
gap (checked directly against the generator code, not assumed): none of
this fleet's 26 real issue_category values were accident/collision-type,
and no accident/collision event source was wired into warranty_claims or
service_events at all - every category defaulted to WARRANTY routing,
and the INSURANCE branch of the decision tree had nothing to route to.

That gap is now partially closed: data/generators/auto/service.py's
generate_accident_service_events and generate_telematics_linked_accident_events,
plus data/generators/auto/insurance.py's generate_insurance_claims,
produced real accident-caused service events and real insurance claims
from them - see ACCIDENT_CLAIM_STATS below for the current real counts,
read directly from the live data, not estimated. This document has been
updated accordingly rather than left describing a gap that no longer
fully exists.
"""

from __future__ import annotations

import csv
from pathlib import Path

from data.generators.documents.blocks import Document, Heading, Paragraph, Table
from data.generators.documents.boundary_guidelines_data import (
    ACCIDENT_ISSUE_CATEGORY,
    ISSUE_CATEGORIES,
)
from data.generators.common.helpers import SYNTHETIC_DIR


def _read_accident_claim_stats() -> dict[str, int | float]:
    """Reads the real, current counts directly from the live synthetic
    data - kept as a live read rather than hardcoded numbers, so this
    document never silently drifts out of date the way its old
    all-WARRANTY claim eventually did."""
    service_path = SYNTHETIC_DIR / "auto" / "service_events.csv"
    insurance_path = SYNTHETIC_DIR / "auto" / "insurance_claims.csv"

    accident_events = 0
    if service_path.exists():
        with service_path.open(newline="", encoding="utf-8") as handle:
            accident_events = sum(
                1 for row in csv.DictReader(handle) if row.get("is_accident_caused") == "True"
            )

    claims = 0
    approved = 0
    total_claimed = 0.0
    total_approved = 0.0
    if insurance_path.exists():
        with insurance_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                claims += 1
                total_claimed += float(row["claim_amount_inr"])
                total_approved += float(row["approved_amount_inr"])
                if row["claim_status"] == "APPROVED":
                    approved += 1

    return {
        "accident_events": accident_events,
        "claims": claims,
        "approved": approved,
        "total_claimed": total_claimed,
        "total_approved": total_approved,
    }


def build_boundary_guidelines() -> Document:
    stats = _read_accident_claim_stats()

    routing_rows = tuple(
        (
            category.replace("_", " ").title(),
            "WARRANTY",
            "Recognised quality/wear/electrical/noise pattern with no accident signature by definition.",
        )
        for category in ISSUE_CATEGORIES
    )
    routing_rows = routing_rows + (
        (
            ACCIDENT_ISSUE_CATEGORY.replace("_", " ").title(),
            "INSURANCE",
            "Collision/accident-caused damage, not a manufacturing defect - generated from real telematics "
            "evidence for a subset of cases (see the Note below), and always forced to warranty_candidate=False "
            "so it can never be mistaken for a warranty claim.",
        ),
    )

    blocks: tuple = (
        Heading("Purpose", level=2),
        Paragraph(
            "A single reported issue can, in principle, be a manufacturing defect (Mahindra's liability, "
            "under warranty) or the result of an accident or external event (an insurance matter, not "
            "warranty). This document defines how a claim is routed between the two, so the financial-impact "
            "model never double-counts a failure under both, and so a claim isn't silently dropped between "
            "the two processes."
        ),
        Heading("Decision Tree", level=2),
        Paragraph(
            "1. Is there telematics evidence of a collision-level event (an impact-force spike far beyond "
            "normal driving) at or near the time the issue was reported? If yes, this is an accident matter "
            "- route to INSURANCE, not warranty."
        ),
        Paragraph(
            "2. If there is no collision-level telematics evidence, does the reported issue match a "
            "recognised manufacturing-defect pattern for its component category (see the Component-Level "
            "Coverage Schedule and Driving-Behavior Exclusion Clauses)? If yes, route to WARRANTY."
        ),
        Paragraph(
            "3. If the evidence is mixed, insufficient, or the driving-behavior telematics forensics step "
            "(see docs/data_required_for_warranty_predictive_model.md section 6.3) returns an INCONCLUSIVE "
            "finding, route to MANUAL_REVIEW rather than guessing - a human adjuster resolves the ambiguity."
        ),
        Heading("Routing By Issue Category", level=2),
        Paragraph(
            "Every issue_category value currently seen in this fleet's real warranty_claims data, plus "
            f"{ACCIDENT_ISSUE_CATEGORY.replace('_', ' ').title()} (the one category that comes from "
            "service_events, not warranty_claims), with its default routing under the decision tree above:"
        ),
        Table(
            headers=("Issue Category", "Default Routing", "Reasoning"),
            rows=routing_rows,
        ),
        Heading("Current Real Accident/Insurance Data", level=2),
        Paragraph(
            f"As of this document's last generation: {stats['accident_events']} accident-caused service "
            f"events exist in this fleet's data, of which {stats['claims']} were filed as insurance claims "
            f"({stats['approved']} approved). Total claimed: Rs.{stats['total_claimed']:,.2f}. Total "
            f"approved: Rs.{stats['total_approved']:,.2f}. These are real counts read directly from "
            "data/synthetic/auto/service_events.csv and insurance_claims.csv at generation time, not "
            "estimates - this section will automatically stay current the next time this document is regenerated."
        ),
        Heading("A Note On Scope", level=2),
        Paragraph(
            "Telematics-covered evidence is limited: this fleet's telematics data only covers a small, fixed "
            "24-vehicle cohort (each for just their first 7 days after delivery), not the whole fleet. Most "
            "accident-caused service events happen to vehicles or at times outside that cohort/window, so "
            "step 1 of the decision tree above (collision telematics evidence) can only be genuinely "
            "evaluated for a small subset of accidents - the rest are routed to INSURANCE based on the "
            "is_accident_caused flag alone, without a matching telematics signature to point to. Expanding "
            "genuine telematics-backed evidence to more accidents would require widening that 24-vehicle "
            "cohort, which is a separate, larger decision (it affects the live telematics generator, not "
            "just this document)."
        ),
        Paragraph(
            "A claim in any of the 26 non-accident categories can still be moved from WARRANTY to "
            "MANUAL_REVIEW (never automatically to INSURANCE, unless it is genuinely accident-caused) if "
            "claim-time telematics evidence contradicts the default categorization - for example, a "
            "STEERING_NOISE claim following a telematics-flagged harsh-impact event should not be "
            "auto-approved as a routine defect."
        ),
    )

    return Document(
        doc_type="warranty_insurance_boundary_guidelines",
        title="Warranty-Insurance Boundary Guidelines",
        blocks=blocks,
        vehicle_model=None,
        relevant_issue_categories=ISSUE_CATEGORIES + (ACCIDENT_ISSUE_CATEGORY,),
    )
