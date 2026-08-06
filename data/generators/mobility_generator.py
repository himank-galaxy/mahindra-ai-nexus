"""Auto Mobility Causal Twin: causal graph, KPIs and Q&A (incl. warranty).

Tables: causal_nodes, causal_edges, mobility_kpis, causal_qa.

The graph topology is fixed (it is a UX layout, not random data); node
metrics and KPIs are generated from the shared business chain so they stay
consistent with dealer/customer data. Warranty risk appears as a node + Q&A
rows — this is where the "warranty" entity lives in the current schema.
"""

from __future__ import annotations

import random

from common import VEHICLE_MODELS, GenConfig, business_chain_score, jdump, write_csv

# Fixed topology: (label, x, y, drivers)
NODES = [
    ("Campaign Spend", 50, 60, ["Digital-heavy allocation", "Regional festive push"]),
    ("Lead Quality", 180, 60, ["Better source mix", "Improved landing pages"]),
    ("Dealer Follow-up", 320, 60, ["NBA adoption", "WhatsApp templates"]),
    ("Test Drive", 460, 60, ["AI scheduler", "SMS reminders"]),
    ("Booking", 600, 60, ["Exchange bonus", "Finance TAT"]),
    ("Finance Approval", 50, 180, ["Alt-data model", "Faster KYC"]),
    ("Vehicle Allocation", 180, 180, ["Demand model", "Dealer capacity"]),
    ("Delivery Delay", 320, 180, ["Reduced waiting", "Better allocation"]),
    ("Customer Satisfaction", 460, 180, ["Delivery experience", "Service quality"]),
    ("Service Experience", 600, 180, ["Bay utilization", "AR technician guide"]),
    ("Warranty Claims", 180, 300, ["Component supplier variance"]),
    ("Repeat Purchase", 460, 300, ["Loyalty program", "Cross-sell"]),
]
EDGES = [
    ("Campaign Spend", "Lead Quality"),
    ("Lead Quality", "Dealer Follow-up"),
    ("Dealer Follow-up", "Test Drive"),
    ("Test Drive", "Booking"),
    ("Finance Approval", "Booking"),
    ("Booking", "Vehicle Allocation"),
    ("Vehicle Allocation", "Delivery Delay"),
    ("Delivery Delay", "Customer Satisfaction"),
    ("Service Experience", "Customer Satisfaction"),
    ("Customer Satisfaction", "Repeat Purchase"),
    ("Warranty Claims", "Customer Satisfaction"),
    ("Service Experience", "Warranty Claims"),
]
KPI_DEFS = [
    ("Lead → booking conversion", "{v}%", (12, 22), "+{d} pts"),
    ("Test drive completion", "{v}%", (60, 82), "+{d}%"),
    ("Cancellation risk", "{v}%", (4, 11), "-{d} pts"),
    ("Delivery delay", "{v} d", (7, 13), "-{d} d"),
    ("Warranty risk", "Low", (0, 0), "stable"),
    ("Finance approval rate", "{v}%", (65, 85), "+{d}%"),
    ("Dealer follow-up leakage", "{v}%", (8, 18), "-{d}%"),
    ("Service CSAT", "{v}%", (72, 90), "+{d}%"),
]
MOBILITY_QA_POOL = [
    ("Why did bookings drop in {city}?", "Bookings dropped due to follow-up leakage at 2 {city} dealers ({a}%), competitor promo ({b}%), finance TAT ({c}%). Recommend: exchange bonus + follow-up SLA."),
    ("What is causing delivery delay in {region} Zone?", "{region} Zone waiting is elevated by uneven allocation ({a}% of delay). Reallocate {n} units."),
    ("Which factor has highest impact on cancellation?", "Finance approval TAT (>4 days) explains {a}% of cancellations. Pre-approval for low-risk rural cuts it by {b}%."),
    ("How can we improve finance-assisted conversions?", "Pair thin-file credit twin with dealer NBA. Expected +{x}% conversion, -{y}% NPA risk."),
    ("Where should exchange bonus be targeted?", "Target {n} {model} prospects in {region} Zone — propensity {a}% with current exchange values."),
    ("Which dealers leak the most revenue?", "{city} dealers show {a}% leakage from stale leads; escalation SLA recovers ~₹{n} L/month."),
    ("What drives repeat purchase?", "Loyalty program + cross-sell timing; CSAT above {v} lifts repeat rate by {d}%."),
    ("Why are warranty claims spiking?", "Component supplier variance on batch {batch}; quarantine recommended."),
]
DMRV_QA_POOL = [
    ("Estimate carbon credits for this batch.", "Estimated {n} tCO2e from batch {batch}, of which {m} are verification-ready."),
    ("Which fields are incomplete?", "Missing: origin geo-tag, weight tickets for {n} vehicles, technician attestation for {m} units."),
    ("Is this verification-ready?", "{v}% ready — after adding origin geo-tags, verification confidence rises to {w}%."),
    ("Generate audit summary.", "Audit summary generated. {n} batches, {m} tCO2e, {v}% traceable, {k} pending human reviews."),
    ("Which credits should be repriced?", "Reprice {n} credits with traceability below {v}% — expected closure uplift {d}%."),
    ("Show EPR compliance status.", "{v}% of EPR certificates verified; {k} awaiting buyer confirmation."),
]


def generate(cfg: GenConfig) -> None:
    rng = random.Random(cfg.seed + 11)
    chain = business_chain_score(rng)

    nodes = [
        {
            "label": label,
            "x": x,
            "y": y,
            "metric": _node_metric(label, chain, rng),
            "trend": rng.choice(["+2%", "+4%", "+5%", "+8%", "-3.1d", "spike", "+2.1"]),
            "drivers": jdump(drivers),
            "action": rng.choice([
                "Reallocate 12% to programmatic", "Increase retargeting", "Escalate stale leads > 2h",
                "Add Sunday slots", "Bundle offers", "Pre-approve rural", "Rebalance West",
                "Monitor Q1", "Expand digital handover", "Roll out to 40 more dealers",
                "Quarantine batch", "Bundle insurance renewal",
            ]),
            "sort_order": i,
        }
        for i, (label, x, y, drivers) in enumerate(NODES)
    ]
    write_csv("causal_nodes", nodes)

    edges = [
        {"source_label": s, "target_label": t, "sort_order": i}
        for i, (s, t) in enumerate(EDGES)
    ]
    write_csv("causal_edges", edges)

    kpis = []
    for i, (label, fmt, (lo, hi), trend_fmt) in enumerate(KPI_DEFS[: cfg.n(cfg.mobility_kpis)]):
        value = fmt.format(v=round(rng.uniform(lo, hi), 1)) if lo != hi else "Low"
        kpis.append({"label": label, "value": value, "trend": trend_fmt.format(d=round(rng.uniform(1, 5), 1)), "sort_order": i})
    write_csv("mobility_kpis", kpis)

    qa = []
    order = 0
    cities, regions = ["Pune", "Delhi", "Chennai", "Jaipur"], ["West", "North", "South", "East"]
    for q, a in MOBILITY_QA_POOL[: cfg.n(cfg.qa_mobility)]:
        qa.append({
            "category": "mobility",
            "question": q.format(city=rng.choice(cities), region=rng.choice(regions), model=rng.choice(["XUV700", "Scorpio-N"])),
            "answer": a.format(
                city=rng.choice(cities), region=rng.choice(regions), model=rng.choice(VEHICLE_MODELS),
                a=rng.randint(20, 50), b=rng.randint(10, 30),
                c=rng.randint(8, 20), n=rng.randint(80, 240), x=round(rng.uniform(3, 9), 1), y=round(rng.uniform(1, 4), 1),
                v=rng.randint(55, 75), d=rng.randint(3, 9), batch=f"B-{rng.randint(2100, 2400)}",
            ),
            "sort_order": order,
        })
        order += 1
    for q, a in DMRV_QA_POOL[: cfg.n(cfg.qa_dmrv)]:
        qa.append({
            "category": "dmrv",
            "question": q,
            "answer": a.format(
                n=rng.randint(120, 320), m=rng.randint(60, 240), v=rng.randint(65, 85), w=rng.randint(85, 96),
                k=rng.randint(1, 6), d=rng.randint(4, 12), batch=f"RVSF-{rng.choice(['Nagpur', 'Chennai'])}-Q{rng.randint(1, 4)}",
            ),
            "sort_order": order,
        })
        order += 1
    write_csv("causal_qa", qa)


def _node_metric(label: str, chain: dict, rng: random.Random) -> str:
    if label == "Booking":
        return f"{round(chain['booking_prob'] / 4.2, 1)}%"
    if label == "Finance Approval":
        return f"{chain['finance_approval']}%"
    if label == "Customer Satisfaction":
        return f"NPS {round(chain['csat'] * 0.9)}"
    if label == "Lead Quality":
        return f"Score {chain['quality']}"
    if label == "Campaign Spend":
        return f"₹{round(rng.uniform(2.5, 6.5), 1)} Cr"
    if label == "Dealer Follow-up":
        return f"SLA {rng.randint(60, 88)}%"
    if label == "Test Drive":
        return f"{rng.randint(60, 82)}% completion"
    if label == "Vehicle Allocation":
        return f"{rng.randint(75, 95)}% utilization"
    if label == "Delivery Delay":
        return f"{round(rng.uniform(7, 12), 1)} d"
    if label == "Service Experience":
        return f"{chain['csat']}% CSAT"
    if label == "Warranty Claims":
        return f"Batch B-{rng.randint(2100, 2400)} flagged"
    return f"{rng.randint(18, 30)}%"


if __name__ == "__main__":
    generate(GenConfig())
