"""Compliance Trust Ledger: audited AI decisions + compliance rules.

Tables: trust_decisions, compliance_rules.

Each decision carries the same six-step lineage JSON structure the frontend
trust modal renders. Confidence correlates with approval state.
"""

from __future__ import annotations

import random

from common import GenConfig, jdump, make_faker, write_csv

USE_CASES = [
    ("Vehicle allocation to {region} Zone", "Reallocate {n} units", "Bookings, dealer capacity, waiting list"),
    ("Rural SME loan approval", "Approve ₹{amt}L", "Alternate credit, geo, agri"),
    ("Collections restructuring offer", "Offer {n}-month plan", "DPD, income stability"),
    ("Carbon credit repricing", "Reprice batch {pct}%", "Buyer demand, traceability"),
    ("SLA reroute on corridor", "Split load via air", "Route telemetry, weather"),
    ("Dealer lead escalation", "Escalate {n} stale leads", "Lead scores, SLA telemetry"),
    ("Exchange bonus targeting", "Target {n} XUV700 prospects", "Propensity, exchange values"),
]
PREFIXES = ["AUTO", "FIN", "COLL", "CIRC", "LOG", "DEAL"]
LINEAGE_STEPS = [
    (1, "Data ingested", "Signals collected from {n} sources"),
    (2, "Model scored", "Ensemble confidence {c}%"),
    (3, "Policy checked", "All guardrails passed"),
    (4, "Recommendation issued", "Routed to decision queue"),
    (5, "Action taken", "Executed via Action Agent · SLA logged"),
    (6, "Feedback captured", "Outcome fed to Learning Agent"),
]


def generate(cfg: GenConfig) -> None:
    rng = random.Random(cfg.seed + 9)

    rows = []
    for i in range(cfg.n(cfg.trust_decisions)):
        tmpl = rng.choice(USE_CASES)
        confidence = rng.randint(55, 96)
        if confidence >= 85:
            approval, risk, audit = "approved", "low", "complete"
        elif confidence >= 70:
            approval, risk, audit = rng.choice(["approved", "human_review"]), rng.choice(["low", "medium"]), "pending"
        else:
            approval, risk, audit = rng.choice(["human_review", "pending"]), rng.choice(["medium", "high"]), "pending"

        lineage = [
            {"step": s, "title": t, "detail": d.format(n=rng.randint(3, 9), c=confidence, pct=rng.randint(5, 15))}
            for s, t, d in LINEAGE_STEPS
        ]
        rows.append({
            "code": f"{rng.choice(PREFIXES)}-{5000 + i}",
            "use_case": tmpl[0].format(region=rng.choice(["West", "North", "South", "East"])),
            "recommendation": tmpl[1].format(n=rng.randint(3, 12), amt=round(rng.uniform(1.5, 9.5), 1), pct=rng.randint(5, 15)),
            "data_sources": tmpl[2],
            "confidence": confidence,
            "approval": approval,
            "risk": risk,
            "audit": audit,
            "rejection_reason": None,
            "lineage": jdump(lineage),
            "sort_order": i,
        })
    write_csv("trust_decisions", rows)

    rules = [
        ("Consent check", "OK"),
        ("Bias / fairness check", "OK"),
        ("Regulatory rule check", "OK"),
        ("Business policy check", f"{rng.randint(0, 3)} pending"),
        ("Audit trail complete", "OK"),
        ("Data retention check", "OK"),
    ]
    write_csv("compliance_rules", [
        {"label": label, "status": status, "sort_order": i}
        for i, (label, status) in enumerate(rules[: cfg.n(cfg.compliance_rules)])
    ])
    _ = make_faker  # reserved for future use-case text variation


if __name__ == "__main__":
    generate(GenConfig())
