"""Simulation Center: persisted what-if run audit trail.

Tables: simulation_runs.

Inputs/outputs mirror the backend engine schemas (app/schemas/simulation.py)
exactly — output keys use the camelCase aliases the frontend consumes. Runs
draw inputs from realistic slider ranges so the audit trail looks like actual
usage, with outputs consistent with the business chain (e.g. high demand +
low capacity -> longer delay).
"""

from __future__ import annotations

import random

from common import REGIONS, VEHICLE_MODELS, GenConfig, business_chain_score, clamp, jdump, write_csv

ROUTES = ["Mumbai → Pune", "Chennai → Bengaluru", "Delhi → Jaipur", "Kolkata → Ranchi", "Nagpur → Indore"]
CREDIT_TYPES = ["Carbon", "EPR", "Circular Materials"]


def _auto_sales(rng: random.Random) -> tuple[dict, dict, int]:
    discount = round(rng.uniform(0, 10), 1)
    bonus = rng.randint(0, 15) * 5000
    campaign = round(rng.uniform(0, 5), 1)
    intensity = rng.choice(["Low", "Medium", "High"])
    uplift = clamp(round(discount * 180 + bonus / 1000 + campaign * 120 + {"Low": -30, "Medium": 0, "High": 40}[intensity]), 0, 4000)
    inputs = {
        "region": rng.choice(REGIONS),
        "model": rng.choice(VEHICLE_MODELS),
        "discount": discount,
        "bonus": bonus,
        "campaign": campaign,
        "intensity": intensity,
    }
    outputs = {
        "uplift": uplift,
        "margin": clamp(round(discount * -9 + 40), 0, 100),
        "cancel": clamp(round(12 - discount * 0.6 - campaign * 0.4), 0, 30),
        "rev": uplift * 18,  # ~₹18L avg deal size
        "conf": 0,
        "recommendedAction": "Increase exchange bonus in high-propensity segments" if uplift > 1200 else "Hold current pricing; monitor weekly",
    }
    outputs["conf"] = rng.randint(62, 92)
    return inputs, outputs, outputs["conf"]


def _dealer_allocation(rng: random.Random) -> tuple[dict, dict, int]:
    units = rng.randint(20, 400)
    demand = rng.randint(20, 100)
    capacity = rng.randint(30, 100)
    wait = rng.randint(5, 45)
    pressure = max(0, demand - capacity)
    inputs = {"units": units, "demand": demand, "capacity": capacity, "wait": wait}
    delay = clamp(round(wait * 0.4 + pressure * 0.35), 0, 45)
    w, n, s = rng.randint(30, 50), rng.randint(20, 35), 0
    s = 100 - w - n
    outputs = {
        "delay": delay,
        "rev": units * rng.randint(15, 22),
        "csat": clamp(90 - delay),
        "suggestedSplit": f"West {w}% · North {n}% · South {s}%",
    }
    return inputs, outputs, rng.randint(60, 90)


def _collections(rng: random.Random, chain: dict) -> tuple[dict, dict, int]:
    risk = rng.choice(["Low", "Medium", "High"])
    channel = rng.choice(["Digital", "Voice", "Field"])
    offer = rng.choice(["Restructure", "Waiver", "Settlement", "None"])
    field = rng.randint(0, 100)
    base = {"Low": 78, "Medium": 58, "High": 38}[risk]
    inputs = {"risk": risk, "channel": channel, "offer": offer, "field": field}
    outputs = {
        "prob": clamp(base + round(chain["finance_approval"] / 8) + (10 if offer != "None" else 0)),
        "cost": {"Digital": 12, "Voice": 30, "Field": 70}[channel] + field,
        "friction": {"Restructure": 20, "Waiver": 35, "Settlement": 45, "None": 10}[offer],
        "net": 0,
    }
    outputs["net"] = clamp(outputs["prob"] - outputs["cost"] // 2 - outputs["friction"] // 3, 0, 100)
    return inputs, outputs, rng.randint(58, 88)


def _logistics(rng: random.Random) -> tuple[dict, dict, int]:
    warehouse = rng.randint(0, 100)
    vehicle = rng.randint(20, 100)
    weather = rng.randint(0, 100)
    sla = rng.choice(["Low", "Medium", "High"])
    delay = clamp(round(warehouse * 0.2 + (100 - vehicle) * 0.25 + weather * 0.2))
    inputs = {"route": rng.choice(ROUTES), "warehouse": warehouse, "vehicle": vehicle, "weather": weather, "sla": sla}
    outputs = {
        "delay": delay,
        "breach": clamp(delay + {"Low": -10, "Medium": 0, "High": 12}[sla]),
        "reroute": "Via Nagpur bypass" if delay > 25 else "Keep primary corridor",
        "cost": delay * rng.randint(800, 1500),
    }
    return inputs, outputs, None


def _credit_pricing(rng: random.Random) -> tuple[dict, dict, int]:
    supply = rng.randint(10, 100)
    demand = rng.randint(10, 100)
    trace = rng.randint(10, 100)
    verif = rng.randint(10, 100)
    balance = demand - supply
    low = clamp(400 + balance * 6 + trace, 100, 2000)
    inputs = {"type": rng.choice(CREDIT_TYPES), "supply": supply, "demand": demand, "trace": trace, "verif": verif}
    outputs = {
        "priceBandLow": low,
        "priceBandHigh": low + rng.randint(150, 400),
        "closure": clamp(40 + balance // 2 + verif // 4),
        "match": clamp(50 + demand // 3),
        "complianceRisk": "Low" if verif > 70 else ("Medium" if verif > 45 else "High"),
    }
    return inputs, outputs, None


def generate(cfg: GenConfig) -> None:
    rng = random.Random(cfg.seed + 15)
    chain = business_chain_score(rng)

    builders = {
        "auto_sales": lambda: _auto_sales(rng),
        "dealer_allocation": lambda: _dealer_allocation(rng),
        "collections": lambda: _collections(rng, chain),
        "logistics_delay": lambda: _logistics(rng),
        "credit_pricing": lambda: _credit_pricing(rng),
    }
    domains = list(builders)
    runs = []
    for i in range(cfg.n(cfg.simulation_runs)):
        domain = domains[i % len(domains)]
        inputs, outputs, confidence = builders[domain]()
        runs.append({
            "domain": domain,
            "inputs": jdump(inputs),
            "outputs": jdump(outputs),
            "confidence": confidence,
        })
    write_csv("simulation_runs", runs)


if __name__ == "__main__":
    generate(GenConfig())
