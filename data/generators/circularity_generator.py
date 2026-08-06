"""Circular Economy: carbon / EPR / SDG credit marketplace rows.

Tables: carbon_credits.

Interconnection: traceability score drives buyer match, which drives closure
probability — the same logic the dMRV copilot answers describe.
"""

from __future__ import annotations

import random

from common import GenConfig, clamp, write_csv

TYPES = ["Carbon", "EPR", "SDG", "CD"]
BATCHES = ["RVSF-Nagpur", "RVSF-Chennai", "ELV-Pune", "ELV-Lucknow", "Plant-Zahirabad"]


def generate(cfg: GenConfig) -> None:
    rng = random.Random(cfg.seed + 8)

    rows = []
    for i in range(cfg.n(cfg.carbon_credits)):
        traceability = rng.randint(45, 98)
        buyer_match = clamp(traceability - rng.randint(0, 20))
        closure_prob = clamp(buyer_match - rng.randint(0, 18))
        base = rng.choice([rng.randint(600, 1200), rng.randint(1200, 2600)])
        rows.append({
            "code": f"SYN-{rng.choice(BATCHES).split('-')[0]}-{2300 + i}",
            "type": rng.choice(TYPES),
            "price": f"₹{base:,}",
            "buyer_match": buyer_match,
            "closure_prob": closure_prob,
            "traceability": traceability,
            "repriced_at": None,
            "buyer_matched_at": None,
            "sort_order": i,
        })

    write_csv("carbon_credits", rows)


if __name__ == "__main__":
    generate(GenConfig())
