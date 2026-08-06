"""Executive Overview: KPI cards, drivers and AI recommendations.

Tables: kpis, kpi_drivers, recommendations.

Interconnection: headline KPI values are AGGREGATED from the generated
dealer/customer populations (not invented randomly), so the executive
dashboard stays consistent with the dealer funnel and finance twins.
"""

from __future__ import annotations

import random

import dealer_generator
from common import GenConfig, business_chain_score, inr, write_csv

RECOMMENDATION_POOL = [
    ("Launch exchange bonus for XUV700 in {region} Zone", "+₹{v} Cr bookings", "high"),
    ("Escalate {n} stale leads at {city} dealers", "Recover ₹{v} L / month", "low"),
    ("Pre-approve rural thin-file customers", "+{p}% finance conversion", "medium"),
    ("Rebalance allocation towards {region} Zone", "-{d} days delivery delay", "medium"),
    ("Reprice low-traceability carbon credits", "+{p}% closure probability", "low"),
    ("Bundle insurance renewal with service plan", "+₹{v} L cross-sell", "low"),
    ("Shift SLA-risk corridors to air split", "-{p}% SLA breach risk", "medium"),
    ("Deploy WhatsApp NBA across {n} dealers", "+{p}% follow-up conversion", "medium"),
    ("Quarantine warranty batch B-2141", "Protect NPS {csat}", "high"),
    ("Expand AR repair guide to {n} more dealers", "-{p}% repair time", "low"),
]


def generate(cfg: GenConfig) -> None:
    rng = random.Random(cfg.seed + 12)
    dealers, leads = dealer_generator.build(cfg)

    # --- aggregates from the dealer funnel -------------------------------
    total_leads = sum(d["leads"] for d in dealers)
    total_hot = sum(d["hot_leads"] for d in dealers)
    avg_booking = round(sum(d["booking_prob"] for d in dealers) / len(dealers), 1)
    avg_leakage = round(sum(d["leakage_pct"] for d in dealers) / len(dealers), 1)
    converted = sum(1 for l in leads if l["status"] == "converted")
    chain = business_chain_score(rng)

    uplift_cr = round(total_hot * avg_booking / 100 * 0.18, 0)  # ~18L avg deal size heuristic
    kpi_defs = [
        ("rev", "Predicted Revenue Uplift", inr(uplift_cr * 1_00_00_000), f"+{round(rng.uniform(5, 11), 1)}%", True,
         [f"{d['name']} booking conversion +{rng.randint(6, 16)}%" for d in rng.sample(dealers, min(2, len(dealers)))]
         + [f"Rural low-risk finance approval +{rng.randint(5, 12)}%", f"Dealer follow-up leakage -{rng.randint(8, 18)}%"]),
        ("leak", "Leakage Prevented", inr(uplift_cr * 0.35 * 1_00_00_000), f"-{round(avg_leakage / 4, 1)}%", True,
         [f"{total_leads:,} leads scored across {len(dealers)} dealers", f"{total_hot:,} hot leads actioned in SLA"]),
        ("book", "Booking Conversion", f"{avg_booking}%", f"+{round(rng.uniform(1, 3), 1)} pts", True,
         [f"{converted} converted leads in funnel", f"Test-drive SLA adherence {rng.randint(70, 90)}%"]),
        ("fin", "Finance Approval Rate", f"{chain['finance_approval']}%", f"+{rng.randint(2, 6)}%", True,
         ["Alt-data scoring on thin files", f"KYC TAT reduced to {rng.randint(2, 5)} days"]),
        ("del", "Delivery Delay", f"{round(rng.uniform(7, 11), 1)} d", f"-{round(rng.uniform(1, 4), 1)} d", True,
         ["Rebalanced West Zone allocation", "Waiting list normalized post-festive"]),
        ("csat", "Customer Satisfaction", f"NPS {round(chain['csat'] * 0.9)}", f"+{rng.randint(2, 6)}", True,
           ["Delivery experience improvements", "AR technician guide rollout"]),
    ]

    kpis, drivers = [], []
    for i, (code, label, value, trend, up, driver_texts) in enumerate(kpi_defs):
        kpis.append({
            "code": code, "label": label, "value": value, "trend": trend,
            "trend_up": str(up).lower(), "confidence": rng.randint(78, 95), "sort_order": i,
        })
        for j, text in enumerate(driver_texts):
            drivers.append({"kpi_code": code, "driver_text": text, "sort_order": j})
    write_csv("kpis", kpis)
    write_csv("kpi_drivers", drivers)

    # --- recommendations --------------------------------------------------
    recs = []
    for i, (title_t, impact_t, risk) in enumerate(RECOMMENDATION_POOL[: cfg.n(cfg.recommendations)]):
        fmt = dict(
            region=rng.choice(["West", "North", "South", "East"]),
            city=rng.choice(["Pune", "Delhi", "Chennai"]),
            v=round(rng.uniform(2, 40), 1), p=round(rng.uniform(3, 14), 1),
            n=rng.randint(80, 320), d=round(rng.uniform(1, 4), 1), csat=chain["csat"],
        )
        recs.append({
            "code": f"REC-SYN-{i + 1:03d}",
            "title": title_t.format(**fmt),
            "impact": impact_t.format(**fmt),
            "confidence": rng.randint(68, 94),
            "risk": risk,
            "status": "pending",
            "decided_at": None,
            "sort_order": i,
        })
    write_csv("recommendations", recs)


if __name__ == "__main__":
    generate(GenConfig())
