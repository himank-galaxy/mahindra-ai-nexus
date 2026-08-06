"""Reference & master data: regions, vehicle models, users.

Tables: regions, vehicle_models, users.
Regions and models mirror the backend lookup tables exactly (they drive the
simulation dropdowns), so they are fixed pools, not random values.
"""

from __future__ import annotations

import random

from common import GenConfig, REGIONS, VEHICLE_MODELS, make_faker, write_csv


def generate(cfg: GenConfig) -> None:
    fake = make_faker(cfg.seed + 1)
    rng = random.Random(cfg.seed + 1)

    write_csv("regions", [{"code": r} for r in REGIONS])
    write_csv("vehicle_models", [{"name": m} for m in VEHICLE_MODELS])

    users = [
        {
            "email": fake.unique.company_email().lower().replace(" ", "."),
            "full_name": fake.unique.first_name() + " " + fake.unique.last_name(),
            "is_active": "true" if i < cfg.n(cfg.users) - 1 else "false",
        }
        for i in range(cfg.n(cfg.users))
    ]
    # Deterministic first user is always the demo principal.
    users[0] = {"email": "demo@mahindra.ai", "full_name": "Command Center Admin", "is_active": "true"}
    _ = rng  # rng reserved for future attribute jitter; kept for determinism parity
    write_csv("users", users)


if __name__ == "__main__":
    generate(GenConfig())
