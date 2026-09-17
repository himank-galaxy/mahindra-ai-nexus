"""
Generates Document #6 (Claim Adjudication Guidelines) - a single global
document.

Usage:
    Causal_Discovery_Service/.venv/bin/python3 -m data.generators.documents.generate_claim_adjudication_doc
"""

from __future__ import annotations

from pathlib import Path

from data.generators.common.helpers import SYNTHETIC_DIR
from data.generators.documents.claim_adjudication_guidelines import build_claim_adjudication_guidelines
from data.generators.documents.render_markdown import render_markdown
from data.generators.documents.render_pdf import render_pdf

OUTPUT_DIR = SYNTHETIC_DIR / "documents" / "warranty"


def generate_claim_adjudication_document(output_dir: Path = OUTPUT_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    document = build_claim_adjudication_guidelines()

    md_path = output_dir / "claim_adjudication_guidelines.md"
    md_path.write_text(render_markdown(document), encoding="utf-8")

    pdf_path = output_dir / "claim_adjudication_guidelines.pdf"
    render_pdf(document, pdf_path)

    return [md_path, pdf_path]


if __name__ == "__main__":
    paths = generate_claim_adjudication_document()

    print(f"Generated {len(paths)} files in {OUTPUT_DIR}:\n")
    for path in sorted(paths):
        print(f"  {path.name}")
