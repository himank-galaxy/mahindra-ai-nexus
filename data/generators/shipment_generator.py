"""Logistics Control Tower: freight corridors (shipments) with SLA risk.

Tables: logistics_routes.

The "shipment" entity of this project is a route/corridor row carrying
predictive SLA metrics — delay probability drives the recommended action,
and corridors link plant/warehouse cities from the shared region pools.
"""

from __future__ import annotations

import random

from common import REGION_CITIES, GenConfig, clamp, inr, write_csv

ACTIONS = [
    "Split load via air for priority SKUs",
    "Pre-dispatch 4h earlier via alternate corridor",
    "Shift 20% volume to rail",
    "Add buffer stock at destination hub",
    "Keep route; monitor weather window",
    "Consolidate with return leg",
]


def generate(cfg: GenConfig) -> None:
    rng = random.Random(cfg.seed + 7)

    all_cities = [c for cities in REGION_CITIES.values() for c in cities]
    rows = []
    used: set[str] = set()
    for i in range(cfg.n(cfg.routes)):
        origin = rng.choice(all_cities)
        dest = rng.choice([c for c in all_cities if c != origin])
        name = f"{origin} → {dest}"
        while name in used:
            origin, dest = rng.choice(all_cities), rng.choice(all_cities)
            name = f"{origin} → {dest}"
        used.add(name)

        delay_prob = rng.randint(10, 90)
        sla_risk = clamp(delay_prob + rng.randint(-10, 15))
        rows.append({
            "name": name,
            "sla_risk": sla_risk,
            "delay_prob": delay_prob,
            "cost": inr(rng.uniform(1_50_000, 9_00_000)),
            "recommended_action": ACTIONS[0] if sla_risk >= 75 else rng.choice(ACTIONS),
            "rerouted": "false",
            "rerouted_at": None,
            "auto_healed": "false",
            "sort_order": i,
        })

    write_csv("logistics_routes", rows)


if __name__ == "__main__":
    generate(GenConfig())
