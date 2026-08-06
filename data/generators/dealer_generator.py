"""Dealer Revenue Optimizer: dealers + AI-scored leads (the booking funnel).

Tables: dealers, dealer_leads.

Business chain implemented here (and reused by overview/customer generators):
    dealer quality tier -> lead score -> booking prob -> revenue at risk
Leads inherit their dealer's region city pool and a vehicle from the model
reference, so the funnel stays consistent with dealer attributes.
"""

from __future__ import annotations

import random

from common import (
    DEALER_SUFFIXES,
    MODEL_PRICE_LAKH,
    REGION_CITIES,
    REGIONS,
    VEHICLE_MODELS,
    GenConfig,
    business_chain_score,
    clamp,
    inr,
    make_faker,
    write_csv,
)

LEAD_ACTIONS = [
    "WhatsApp follow-up with exchange offer",
    "Schedule test drive this weekend",
    "Call with finance pre-approval pitch",
    "Send festive bonus campaign",
    "Escalate to sales manager (stale > 48h)",
    "Share EMI calculator link",
]


def build(cfg: GenConfig) -> tuple[list[dict], list[dict]]:
    """Return (dealer_rows, lead_rows). Deterministic for a given config."""
    fake = make_faker(cfg.seed + 2)
    rng = random.Random(cfg.seed + 2)

    dealers: list[dict] = []
    leads: list[dict] = []
    used_names: set[str] = set()

    for i in range(cfg.n(cfg.dealers)):
        region = REGIONS[i % len(REGIONS)]
        city = rng.choice(REGION_CITIES[region])
        name = f"{city} {rng.choice(DEALER_SUFFIXES)}"
        while name in used_names:
            name = f"{city} {rng.choice(DEALER_SUFFIXES)} {rng.choice(['II', 'Central', 'Westside', 'Plus'])}"
        used_names.add(name)

        chain = business_chain_score(rng)
        lead_volume = rng.randint(60, 220)
        hot = clamp(round(lead_volume * chain["quality"] / 100 * rng.uniform(0.25, 0.45)), 0, lead_volume)
        price_lo, price_hi = MODEL_PRICE_LAKH[rng.choice(VEHICLE_MODELS)]
        revenue_at_risk = inr(rng.uniform(price_lo, price_hi) * hot * 1_00_000)

        dealer = {
            "code": f"syn-d{i + 1:03d}",
            "name": name,
            "region": region,          # context column: dropped by seeder (not in schema)
            "city": city,              # context column: dropped by seeder
            "leads": lead_volume,
            "hot_leads": hot,
            "test_drives_pending": clamp(round(hot * rng.uniform(0.3, 0.6)), 0, hot),
            "booking_prob": chain["booking_prob"],
            "revenue_at_risk": revenue_at_risk,
            "leakage_pct": clamp(100 - chain["quality"] + rng.randint(-5, 10)),
            "bay_util_pct": rng.randint(55, 95),
            "sort_order": i,
        }
        dealers.append(dealer)

        # --- leads for this dealer ---------------------------------------
        lo, hi = cfg.leads_per_dealer
        for j in range(rng.randint(lo, hi)):
            model = rng.choice(VEHICLE_MODELS)
            score = clamp(chain["quality"] + rng.randint(-20, 20))
            prob = clamp(30 + round(score * 0.6) + rng.randint(-5, 5))
            if score >= 75:
                status = "hot"
            elif score >= 55:
                status = rng.choice(["warm", "message_sent", "converted"])
            else:
                status = rng.choice(["cool", "warm"])
            lo_p, hi_p = MODEL_PRICE_LAKH[model]
            lead = {
                "dealer_code": dealer["code"],
                "name": fake.unique.first_name() + " " + fake.last_name(),
                "vehicle": model,
                "score": score,
                "prob": prob,
                "action": rng.choice(LEAD_ACTIONS),
                "revenue": inr(rng.uniform(lo_p, hi_p) * 1_00_000),
                "status": status,
                "test_drive_slot": rng.choice(["Sat 11:00", "Sun 16:30", "Sat 17:00", ""]) or None,
                "message_sent_at": "2026-07-28T10:30:00+00:00" if status in ("message_sent", "converted") else None,
                "converted_at": "2026-07-30T14:05:00+00:00" if status == "converted" else None,
                "sort_order": j,
            }
            leads.append(lead)

    return dealers, leads


def generate(cfg: GenConfig) -> None:
    dealers, leads = build(cfg)
    write_csv("dealers", dealers)
    write_csv("dealer_leads", leads)


if __name__ == "__main__":
    generate(GenConfig())
