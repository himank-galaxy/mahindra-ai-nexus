"""
Builds Document #4 from docs/data_required_for_warranty_predictive_model.md
section 6.5: Driving-Behavior Exclusion Clauses.

Global document (one instance, not per vehicle model) - the underlying
telematics-derived driving-behavior physics don't vary by model for this
synthetic PoC. Scoped per supplier_component_category so a RAG lookup
for one component returns just its clause, not the whole document.
"""

from __future__ import annotations

from data.generators.documents.blocks import Document, Heading, Paragraph
from data.generators.documents.driving_behavior_data import (
    BEHAVIOR_CLAUSES,
    NO_BEHAVIOR_SIGNAL_CATEGORIES,
)


def build_driving_behavior_exclusions() -> Document:
    blocks: list = [
        Heading("Purpose", level=2),
        Paragraph(
            "This document supports the Master Warranty Policy's driving-behavior exclusion clause, and the "
            "claim-time telematics forensics step (checking whether a specific claim's telematics evidence "
            "is consistent with a manufacturing defect or with driver-caused misuse of that component) "
            "described in docs/data_required_for_warranty_predictive_model.md section 6.3. It defines, per "
            "component category, which telematics signal is evidence of misuse and what pattern in that "
            "signal is grounds for exclusion."
        ),
        Paragraph(
            "All specific thresholds below are illustrative synthetic assumptions for this proof-of-concept, "
            "not real Mahindra engineering specifications - flagged individually wherever they appear. A "
            "production system would replace these with values derived from real reliability/durability "
            "testing data per component and model."
        ),
    ]

    for clause in BEHAVIOR_CLAUSES:
        blocks.append(Heading(clause.category.replace("_", " ").title(), level=2))
        blocks.append(Paragraph(f"Telematics signal(s): {', '.join(clause.telematics_signals)}"))
        blocks.append(Paragraph(f"What this looks like: {clause.trigger_description}"))
        blocks.append(Paragraph(f"Threshold: {clause.illustrative_threshold}"))
        blocks.append(Paragraph(f"Exclusion clause: {clause.exclusion_text}"))

    blocks.append(Heading("Component Categories Without a Defined Behavior Signal", level=2))
    blocks.append(
        Paragraph(
            "No telematics-derived behavior signal is defined for the following component categories - "
            "either because failures in these categories have no real telematics fingerprint (e.g. a seat "
            "rattle or a door-seal leak), or because misuse of them is already addressed elsewhere "
            "(tyres, under the tyre manufacturer's own warranty). Claims involving these categories are "
            "evaluated under the general misuse/accident/continued-use exclusions already stated in the "
            "Master Warranty Policy, not a component-specific telematics threshold: "
            + ", ".join(c.replace("_", " ").title() for c in NO_BEHAVIOR_SIGNAL_CATEGORIES)
            + "."
        )
    )

    return Document(
        doc_type="driving_behavior_exclusion_clauses",
        title="Driving-Behavior Exclusion Clauses",
        blocks=tuple(blocks),
        vehicle_model=None,
        relevant_component_categories=tuple(c.category for c in BEHAVIOR_CLAUSES) + NO_BEHAVIOR_SIGNAL_CATEGORIES,
    )
