"""Shared foundation for all synthetic data generators.

Design rules (see docs/Synthetic_Data_Generation.md):
- Deterministic: every generator seeds Faker/random from GENERATOR_SEED, so
  re-running always produces byte-identical CSVs.
- Indian-flavoured: names, cities and currency are Indian (en_IN locale,
  INR formatting, city pools mapped to the four sales regions).
- Interconnected: entities share the same reference pools (regions, vehicle
  models) and business chains (lead score -> booking prob -> finance approval
  -> CSAT) instead of being random in isolation.
- Schema-locked: CSV columns mirror the PostgreSQL schema 1:1 (see
  backend/app/models/*). Nested JSON columns are serialized as JSON strings.
"""

from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from faker import Faker

# Never change: changing the seed changes every generated dataset.
GENERATOR_SEED = 20260806

DATA_DIR = Path(__file__).resolve().parents[1]
SYNTHETIC_DIR = DATA_DIR / "synthetic"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

# ---------------------------------------------------------------------------
# Reference pools — MUST match backend seed/lookup tables exactly.
# ---------------------------------------------------------------------------
REGIONS = ["West", "North", "South", "East"]
VEHICLE_MODELS = ["XUV700", "Scorpio-N", "Thar", "Bolero", "XUV 3XO"]

REGION_CITIES: dict[str, list[str]] = {
    "West": ["Pune", "Mumbai", "Nashik", "Ahmedabad", "Nagpur", "Surat", "Indore"],
    "North": ["Delhi", "Jaipur", "Lucknow", "Chandigarh", "Ludhiana", "Dehradun"],
    "South": ["Chennai", "Bengaluru", "Hyderabad", "Kochi", "Coimbatore", "Vijayawada"],
    "East": ["Kolkata", "Bhubaneswar", "Ranchi", "Patna", "Guwahati", "Raipur"],
}

# Base ex-showroom price bands (INR lakh) used for revenue math.
MODEL_PRICE_LAKH: dict[str, tuple[float, float]] = {
    "XUV700": (13.5, 26.0),
    "Scorpio-N": (13.5, 24.5),
    "Thar": (11.0, 17.5),
    "Bolero": (7.8, 10.5),
    "XUV 3XO": (8.0, 15.5),
}

DEALER_SUFFIXES = [
    "Motors", "Auto World", "Mobility Hub", "Auto Prime", "SUV Center",
    "Automobiles", "Auto Zone", "Wheels", "Autolinks", "Auto Galaxy",
]

SOLUTION_TAGS = [
    "Auto", "Finance", "Collections", "Logistics",
    "Circularity", "Trust", "Copilot", "XR", "Platform",
]


@dataclass
class GenConfig:
    """Configurable record counts (override via run_all.py --scale)."""

    seed: int = GENERATOR_SEED
    dealers: int = 24
    leads_per_dealer: tuple[int, int] = (4, 8)
    customers: int = 48
    finance_products: int = 10
    collections_agents: int = 8
    collections_cases: int = 40
    routes: int = 12
    signals_per_panel: int = 6
    carbon_credits: int = 20
    trust_decisions: int = 20
    compliance_rules: int = 6
    ai_agents: int = 12
    xr_experiences: int = 6
    mobility_kpis: int = 8
    qa_mobility: int = 8
    qa_dmrv: int = 6
    recommendations: int = 8
    solutions_per_bucket: tuple[int, int] = (3, 5)
    suggested_prompts: int = 10
    simulation_runs: int = 25
    users: int = 5
    poc_items: int = 6
    notifications: int = 50      # future dataset (not seeded yet)
    warranty_claims: int = 60    # future dataset (not seeded yet)
    scale: float = field(default=1.0)

    def n(self, base: int) -> int:
        """Apply the global scale factor to a count."""
        return max(1, round(base * self.scale))


def make_faker(seed: int, locale: str = "en_IN") -> Faker:
    """Deterministic Faker instance."""
    Faker.seed(seed)
    random.seed(seed)
    return Faker(locale)


def inr(amount: float) -> str:
    """Format an INR amount like the UI does ('₹1.8 Cr', '₹42 L')."""
    if amount >= 1_00_00_000:
        return f"₹{amount / 1_00_00_000:,.1f} Cr"
    if amount >= 1_00_000:
        return f"₹{amount / 1_00_000:,.1f} L"
    return f"₹{amount:,.0f}"


def clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


def write_csv(name: str, rows: list[dict], fieldnames: list[str] | None = None) -> Path:
    """Write rows to data/synthetic/<name>.csv (UTF-8, stable column order)."""
    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    out = SYNTHETIC_DIR / f"{name}.csv"
    if rows and fieldnames is None:
        fieldnames = list(rows[0].keys())
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames or [])
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {name:<28} {len(rows):>4} rows -> {out.relative_to(DATA_DIR)}")
    return out


def jdump(value) -> str:
    """Serialize nested structures for JSON/JSONB columns."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def business_chain_score(rng: random.Random) -> dict[str, int]:
    """The core interconnection chain used across modules.

    High lead quality -> higher booking probability -> higher finance
    approval -> higher customer satisfaction. Returns correlated scores so
    dealers/leads/customers/KPIs stay mutually consistent.
    """
    quality = rng.randint(25, 95)                       # lead quality score
    booking_prob = clamp(40 + round(quality * 0.45) + rng.randint(-6, 6))
    finance_approval = clamp(35 + round(booking_prob * 0.55) + rng.randint(-8, 8))
    csat = clamp(55 + round(finance_approval * 0.35) + rng.randint(-5, 5))
    return {
        "quality": quality,
        "booking_prob": booking_prob,
        "finance_approval": finance_approval,
        "csat": csat,
    }
