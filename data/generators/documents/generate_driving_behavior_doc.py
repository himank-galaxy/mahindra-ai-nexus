"""
Generates Document #4 (Driving-Behavior Exclusion Clauses) - a single
global document, not one per vehicle model.

Usage:
    Causal_Discovery_Service/.venv/bin/python3 -m data.generators.documents.generate_driving_behavior_doc
"""

from __future__ import annotations

from pathlib import Path

from data.generators.common.helpers import SYNTHETIC_DIR
from data.generators.documents.driving_behavior_exclusions import build_driving_behavior_exclusions
from data.generators.documents.render_markdown import render_markdown
from data.generators.documents.render_pdf import render_pdf

OUTPUT_DIR = SYNTHETIC_DIR / "documents" / "warranty"


def generate_driving_behavior_document(output_dir: Path = OUTPUT_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    document = build_driving_behavior_exclusions()

    md_path = output_dir / "driving_behavior_exclusion_clauses.md"
    md_path.write_text(render_markdown(document), encoding="utf-8")

    pdf_path = output_dir / "driving_behavior_exclusion_clauses.pdf"
    render_pdf(document, pdf_path)

    return [md_path, pdf_path]


if __name__ == "__main__":
    paths = generate_driving_behavior_document()

    print(f"Generated {len(paths)} files in {OUTPUT_DIR}:\n")
    for path in sorted(paths):
        print(f"  {path.name}")
