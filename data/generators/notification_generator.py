"""FUTURE DATASET — notifications (no table in the current schema yet).

Exports: notifications.csv (kept in data/synthetic/ for Phase-2 planning;
seed_database.py skips it until a ``notifications`` table exists).

Interconnection: events are generated ABOUT the already-generated entities
(dealers, SLA-risk routes, carbon credits, recommendations) so a future
notification center can be wired up without inventing new subjects.
"""

from __future__ import annotations

import random

from common import GenConfig, write_csv

import dealer_generator

TEMPLATES = [
    ("warning", "Follow-up SLA breach", "{dealer} has {n} stale leads (> 48h) — escalate now"),
    ("success", "Lead converted", "Hot lead converted at {dealer}"),
    ("info", "Test drive scheduled", "New test drive slot booked at {dealer}"),
    ("warning", "SLA breach risk", "Route SLA risk above 70% — reroute recommended"),
    ("danger", "Collections escalation", "{n} DPD>60 accounts need human review"),
    ("info", "Credit repriced", "Low-traceability carbon credit repriced (+{n}% closure)"),
    ("success", "Recommendation approved", "AI recommendation REC-SYN-{n:03d} approved"),
    ("info", "Simulation completed", "What-if run finished with {n}% confidence"),
]


def generate(cfg: GenConfig) -> None:
    rng = random.Random(cfg.seed + 17)
    dealers, _ = dealer_generator.build(cfg)

    rows: list[dict] = []
    for i in range(cfg.n(cfg.notifications)):
        tone, title, body_t = rng.choice(TEMPLATES)
        rows.append({
            "notification_code": f"NTF-SYN-{i + 1:05d}",
            "tone": tone,
            "title": title,
            "body": body_t.format(dealer=rng.choice(dealers)["name"], n=rng.randint(2, 40)),
            "module": rng.choice(["dealer", "finance", "logistics", "circularity", "overview", "simulation"]),
            "read": "false" if rng.random() < 0.6 else "true",
            "created_at": f"2026-07-{rng.randint(15, 31):02d}T{rng.randint(8, 20):02d}:{rng.randint(0, 59):02d}:00+00:00",
        })
    write_csv("notifications", rows)


if __name__ == "__main__":
    generate(GenConfig())
