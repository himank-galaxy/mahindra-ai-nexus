"""
Generates the Master Warranty Policy and Component-Level Coverage
Schedule (docs/data_required_for_warranty_predictive_model.md section
6.5, items #1 and #3) - both as single global documents, applying to
every Mahindra model, since neither document's content actually varies
by model in this project's synthetic data (confirmed by diffing
per-model copies before both were consolidated to one document each).

Both as Markdown (for the RAG layer to index) and as PDF (for showcasing).

Usage:
    Causal_Discovery_Service/.venv/bin/python3 -m data.generators.documents.generate_warranty_policy_docs
"""

from __future__ import annotations

from pathlib import Path

from data.generators.common.helpers import SYNTHETIC_DIR
from data.generators.documents.component_coverage_schedule import build_component_coverage_schedule
from data.generators.documents.master_warranty_policy import build_master_warranty_policy
from data.generators.documents.render_markdown import render_markdown
from data.generators.documents.render_pdf import render_pdf

OUTPUT_DIR = SYNTHETIC_DIR / "documents" / "warranty"


def _write(document, output_dir: Path, filename_stem: str) -> list[Path]:
    md_path = output_dir / f"{filename_stem}.md"
    md_path.write_text(render_markdown(document), encoding="utf-8")

    pdf_path = output_dir / f"{filename_stem}.pdf"
    render_pdf(document, pdf_path)

    return [md_path, pdf_path]


def generate_warranty_policy_documents(output_dir: Path = OUTPUT_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    written += _write(build_master_warranty_policy(), output_dir, "master_warranty_policy")
    written += _write(build_component_coverage_schedule(), output_dir, "component_coverage_schedule")

    return written


if __name__ == "__main__":
    paths = generate_warranty_policy_documents()

    print(f"Generated {len(paths)} files in {OUTPUT_DIR}:\n")
    for path in sorted(paths):
        print(f"  {path.relative_to(OUTPUT_DIR)}")
