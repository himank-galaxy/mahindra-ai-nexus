"""
Generates Document #9 (Insurance Terms & Conditions) and Document #10
(Add-on/Rider Cover Documents) - both single global documents.

Usage:
    Causal_Discovery_Service/.venv/bin/python3 -m data.generators.documents.generate_insurance_reference_docs
"""

from __future__ import annotations

from pathlib import Path

from data.generators.common.helpers import SYNTHETIC_DIR
from data.generators.documents.insurance_terms import build_insurance_terms
from data.generators.documents.render_markdown import render_markdown
from data.generators.documents.render_pdf import render_pdf
from data.generators.documents.rider_cover import build_rider_cover_document

OUTPUT_DIR = SYNTHETIC_DIR / "documents" / "insurance"


def generate_insurance_reference_documents(output_dir: Path = OUTPUT_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for document, stem in (
        (build_insurance_terms(), "insurance_terms_and_conditions"),
        (build_rider_cover_document(), "addon_rider_cover"),
    ):
        md_path = output_dir / f"{stem}.md"
        md_path.write_text(render_markdown(document), encoding="utf-8")
        written.append(md_path)

        pdf_path = output_dir / f"{stem}.pdf"
        render_pdf(document, pdf_path)
        written.append(pdf_path)

    return written


if __name__ == "__main__":
    paths = generate_insurance_reference_documents()
    print(f"Generated {len(paths)} files in {OUTPUT_DIR}:\n")
    for path in sorted(paths):
        print(f"  {path.name}")
