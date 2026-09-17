"""
Generates Document #12 (Surveyor/Claim Investigation Report) - one per
real insurance claim currently in data/synthetic/auto/insurance_claims.csv.

Usage:
    Causal_Discovery_Service/.venv/bin/python3 -m data.generators.documents.generate_surveyor_reports_docs
"""

from __future__ import annotations

from pathlib import Path

from data.generators.common.helpers import SYNTHETIC_DIR
from data.generators.documents.render_markdown import render_markdown
from data.generators.documents.render_pdf import render_pdf
from data.generators.documents.surveyor_report import build_surveyor_report
from data.generators.documents.surveyor_report_data import load_claim_investigations

OUTPUT_DIR = SYNTHETIC_DIR / "documents" / "insurance" / "surveyor_reports"


def generate_surveyor_report_documents(output_dir: Path = OUTPUT_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for investigation in load_claim_investigations():
        document = build_surveyor_report(investigation)
        claim_id = investigation.claim["insurance_claim_id"]

        md_path = output_dir / f"surveyor_report_{claim_id}.md"
        md_path.write_text(render_markdown(document), encoding="utf-8")
        written.append(md_path)

        pdf_path = output_dir / f"surveyor_report_{claim_id}.pdf"
        render_pdf(document, pdf_path)
        written.append(pdf_path)

    return written


if __name__ == "__main__":
    paths = generate_surveyor_report_documents()
    telematics_backed = sum(1 for p in paths if p.suffix == ".md")
    print(f"Generated {len(paths)} files ({telematics_backed} claims) in {OUTPUT_DIR}")
