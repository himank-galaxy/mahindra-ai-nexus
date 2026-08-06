"""FUTURE DATASET — warranty claims (no table in the current schema yet).

Exports: warranty_claims.csv (kept in data/synthetic/ for Phase-2 planning;
seed_database.py skips it until a ``warranty_claims`` table exists).

Interconnection: claims reference generated dealer codes (dealer_generator)
and the same warranty batch IDs that appear in the mobility causal graph
("Warranty Claims" node + QA pool), so the future table plugs into the
existing twin narrative without rework. Claim frequency correlates with the
dealer's quality chain (weaker dealers -> more claims).
"""

from __future__ import annotations

import random

from common import VEHICLE_MODELS, GenConfig, business_chain_score, make_faker, write_csv

import dealer_generator

COMPONENTS = [
    "Turbocharger assembly", "Infotainment head unit", "AC compressor",
    "Clutch assembly", "Suspension strut", "Battery pack", "Fuel injector",
    "Power window motor", "Brake booster", "DPF sensor",
]
STATUSES = ["Open", "In Review", "Approved", "Rejected", "Closed"]


def generate(cfg: GenConfig) -> None:
    fake = make_faker(cfg.seed + 16)
    rng = random.Random(cfg.seed + 16)
    dealers, _ = dealer_generator.build(cfg)

    rows: list[dict] = []
    for i in range(cfg.n(cfg.warranty_claims)):
        dealer = rng.choice(dealers)
        chain = business_chain_score(rng)
        km = rng.randint(2_000, 85_000)
        # B-2141 is the flagged batch referenced by the mobility causal graph
        # and the executive recommendation pool — keep a slice of claims on it.
        batch = "B-2141" if rng.random() < 0.15 else f"B-{rng.randint(2100, 2400)}"
        severity = "High" if chain["quality"] < 40 else rng.choice(["Low", "Medium", "High"])
        rows.append({
            "claim_code": f"WC-SYN-{i + 1:05d}",
            "dealer_code": dealer["code"],
            "dealer_name": dealer["name"],
            "customer_name": fake.first_name() + " " + fake.last_name(),
            "vehicle": rng.choice(VEHICLE_MODELS),
            "component": rng.choice(COMPONENTS),
            "batch": batch,
            "mileage_km": km,
            "severity": severity,
            "status": rng.choice(STATUSES),
            "cost_inr": rng.randint(3, 120) * 1000,
            "filed_on": f"2026-{rng.randint(1, 7):02d}-{rng.randint(1, 28):02d}",
        })
    write_csv("warranty_claims", rows)


if __name__ == "__main__":
    generate(GenConfig())
