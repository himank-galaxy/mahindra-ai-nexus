"""
Generates Document #8 (Motor Insurance Policy Certificate) and Document
#11 (Claims History / NCB Statement) - one of each per insured vehicle
(see insurance_policy_data.py for the real per-vehicle policy data and
its scope).

Usage:
    Causal_Discovery_Service/.venv/bin/python3 -m data.generators.documents.generate_insurance_policy_docs
"""

from __future__ import annotations

from pathlib import Path

from data.generators.common.helpers import SYNTHETIC_DIR
from data.generators.documents.claims_history_ncb import build_claims_history_ncb
from data.generators.documents.insurance_policy_certificate import build_insurance_policy_certificate
from data.generators.documents.insurance_policy_data import load_insured_vehicle_policies
from data.generators.documents.render_markdown import render_markdown
from data.generators.documents.render_pdf import render_pdf

OUTPUT_DIR = SYNTHETIC_DIR / "documents" / "insurance"


def generate_insurance_policy_documents(output_dir: Path = OUTPUT_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    certificates_dir = output_dir / "policy_certificates"
    ncb_dir = output_dir / "claims_history_ncb"
    certificates_dir.mkdir(parents=True, exist_ok=True)
    ncb_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for policy, claims in load_insured_vehicle_policies():
        certificate = build_insurance_policy_certificate(policy)
        cert_md = certificates_dir / f"policy_certificate_{policy.policy_number}.md"
        cert_md.write_text(render_markdown(certificate), encoding="utf-8")
        cert_pdf = certificates_dir / f"policy_certificate_{policy.policy_number}.pdf"
        render_pdf(certificate, cert_pdf)
        written += [cert_md, cert_pdf]

        ncb_statement = build_claims_history_ncb(policy, claims)
        ncb_md = ncb_dir / f"claims_history_ncb_{policy.policy_number}.md"
        ncb_md.write_text(render_markdown(ncb_statement), encoding="utf-8")
        ncb_pdf = ncb_dir / f"claims_history_ncb_{policy.policy_number}.pdf"
        render_pdf(ncb_statement, ncb_pdf)
        written += [ncb_md, ncb_pdf]

    return written


if __name__ == "__main__":
    paths = generate_insurance_policy_documents()
    policies = len(paths) // 4
    print(f"Generated {len(paths)} files ({policies} policies x 2 documents x 2 formats) in {OUTPUT_DIR}")
