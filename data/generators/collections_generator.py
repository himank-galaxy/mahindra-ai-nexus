"""Collections & Recovery: agent swarm + prioritized delinquent cases.

Tables: collections_agents, collections_cases.

Interconnection: DPD drives roll-forward risk, which drives the recommended
action and recovery probability — delinquent cases reference the same loan
products as finance_products.
"""

from __future__ import annotations

import random

from common import GenConfig, clamp, inr, make_faker, write_csv

AGENT_NAMES = [
    "Prioritization Agent", "Channel Selection Agent", "Negotiation Agent",
    "Compliance Guard Agent", "Field Visit Optimizer", "Promise-to-Pay Tracker",
    "Restructuring Advisor", "Escalation Router", "Recovery Forecaster",
    "Hardship Detector",
]
CHANNELS = ["WhatsApp", "IVR", "Field visit", "SMS", "Email", "Tele-calling"]
PRODUCTS = ["Vehicle Loan", "Two-Wheeler Loan", "Commercial Vehicle Loan", "Top-up Loan"]


def generate(cfg: GenConfig) -> None:
    fake = make_faker(cfg.seed + 5)
    rng = random.Random(cfg.seed + 5)

    agents = [
        {
            "name": name,
            "status": rng.choice(["active", "active", "active", "reviewing", "recommended"]),
            "sort_order": i,
        }
        for i, name in enumerate(AGENT_NAMES[: cfg.n(cfg.collections_agents)])
    ]
    write_csv("collections_agents", agents)

    cases = []
    for i in range(cfg.n(cfg.collections_cases)):
        dpd = rng.choice([rng.randint(1, 30), rng.randint(31, 60), rng.randint(61, 90), rng.randint(91, 180)])
        roll_risk = clamp(20 + round(dpd * 0.45) + rng.randint(-8, 8))
        if roll_risk >= 70:
            action, flag = "Restructure with 6-month plan", rng.choice(["review", "escalate"])
        elif roll_risk >= 45:
            action, flag = "Negotiated part-payment", "review"
        else:
            action, flag = rng.choice(["WhatsApp reminder", "IVR nudge", "Tele-calling"]), "ok"
        prob = clamp(95 - roll_risk + rng.randint(-5, 10))
        cases.append({
            "customer": fake.unique.first_name() + " " + fake.last_name(),
            "product": rng.choice(PRODUCTS),     # context column: dropped by seeder
            "dpd": dpd,
            "outstanding": inr(rng.uniform(30_000, 25_00_000)),
            "roll_forward_risk": roll_risk,
            "channel": rng.choice(CHANNELS),
            "action": action,
            "prob": prob,
            "compliance_flag": flag,
            "status": "pending",
            "modified_action": None,
            "sort_order": i,
        })
    write_csv("collections_cases", cases)


if __name__ == "__main__":
    generate(GenConfig())
