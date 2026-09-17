"""
Generates Document #5 (Maintenance/Service Compliance) - a single
global document, not one per vehicle model (see maintenance_compliance.py
for why).

Usage:
    Causal_Discovery_Service/.venv/bin/python3 -m data.generators.documents.generate_maintenance_compliance_doc
"""

from __future__ import annotations

from pathlib import Path

from data.generators.common.helpers import SYNTHETIC_DIR
from data.generators.documents.maintenance_compliance import build_maintenance_compliance
from data.generators.documents.render_markdown import render_markdown
from data.generators.documents.render_pdf import render_pdf

OUTPUT_DIR = SYNTHETIC_DIR / "documents" / "warranty"


def generate_maintenance_compliance_document(output_dir: Path = OUTPUT_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    document = build_maintenance_compliance()

    md_path = output_dir / "maintenance_service_compliance.md"
    md_path.write_text(render_markdown(document), encoding="utf-8")

    pdf_path = output_dir / "maintenance_service_compliance.pdf"
    render_pdf(document, pdf_path)

    return [md_path, pdf_path]


if __name__ == "__main__":
    paths = generate_maintenance_compliance_document()

    print(f"Generated {len(paths)} files in {OUTPUT_DIR}:\n")
    for path in sorted(paths):
        print(f"  {path.name}")
