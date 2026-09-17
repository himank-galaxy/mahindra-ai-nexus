"""
Builds Document #3 from docs/data_required_for_warranty_predictive_model.md
section 6.5: the Component-Level Coverage Schedule.

One single document, not one per vehicle model - same reasoning as
master_warranty_policy.py: COMPONENT_COVERAGE doesn't vary by model in
this project's synthetic data, so per-model copies were word-for-word
identical except for the title and were dropped in favour of one
document. If a model-specific coverage difference is ever introduced,
this is the place to reintroduce per-model generation for just that
difference, not before.
"""

from __future__ import annotations

from data.generators.documents.blocks import Document, Heading, Paragraph, Table
from data.generators.documents.warranty_policy_data import (
    BASE_WARRANTY_KM,
    BASE_WARRANTY_YEARS,
    COMPONENT_COVERAGE,
)

_COVERAGE_TYPE_LABEL = {
    "BASE_EXTENDABLE": "Base warranty (extendable)",
    "PROPRIETARY": "Separate manufacturer warranty",
    "WEAR_LIMITED": "Limited wear coverage",
    "EXCLUDED": "Not covered",
    "CONSUMABLE": "Consumable (not covered)",
}


def build_component_coverage_schedule() -> Document:
    rows = tuple(
        (
            c.category.replace("_", " ").title(),
            _COVERAGE_TYPE_LABEL[c.coverage_type],
            c.duration_text,
            c.notes,
        )
        for c in COMPONENT_COVERAGE
    )

    blocks = (
        Heading("How To Read This Schedule", level=2),
        Paragraph(
            f"The Master Warranty Policy covers most components, on every Mahindra model, for the standard "
            f"{BASE_WARRANTY_YEARS}-year/{BASE_WARRANTY_KM:,} km period (extendable). This schedule lists the "
            "components that instead follow a different rule - a shorter wear-limited period, coverage under a "
            "separate manufacturer's warranty, or no coverage at all - along with every component category for "
            "completeness."
        ),
        Table(
            headers=("Component Category", "Coverage Type", "Duration / Limit", "Notes"),
            rows=rows,
        ),
    )

    return Document(
        doc_type="component_coverage_schedule",
        title="Component-Level Coverage Schedule — Mahindra",
        blocks=blocks,
        vehicle_model=None,
        relevant_component_categories=tuple(c.category for c in COMPONENT_COVERAGE),
    )
