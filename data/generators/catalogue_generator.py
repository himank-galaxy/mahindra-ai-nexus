"""AI Solution Catalogue: buckets, solutions, and PoC roadmap items.

Tables: solution_buckets, solutions, poc_items.
Solutions are composed from capability × domain templates so text stays
business-plausible instead of random word salad.
"""

from __future__ import annotations

import random

from common import SOLUTION_TAGS, GenConfig, write_csv

BUCKETS = [
    ("Revenue Intelligence", "Auto"),
    ("Credit & Risk Intelligence", "Finance"),
    ("Recovery Optimization", "Collections"),
    ("Supply Chain Control Tower", "Logistics"),
    ("Circular Value Recovery", "Circularity"),
    ("Trust & Compliance", "Trust"),
    ("Conversational Analytics", "Copilot"),
    ("Immersive Experience", "XR"),
    ("Platform & MLOps", "Platform"),
]
CAPABILITIES = [
    ("Demand forecasting", "Forecast demand at dealer-model granularity", "Causal driver explanations", "+{p}% forecast accuracy"),
    ("Lead scoring", "Score every lead on conversion propensity", "NBA next-action engine", "+{p}% conversion"),
    ("Churn prediction", "Predict cancellation risk before booking loss", "Intervention playbooks", "-{p}% cancellations"),
    ("Alt-data underwriting", "Underwrite thin-file customers with alternate data", "Explainable risk decomposition", "+{p}% approvals"),
    ("Dynamic pricing", "Reprice credits & offers with demand signals", "Buyer-match intelligence", "+{p}% closure"),
    ("Anomaly detection", "Detect operational anomalies in real time", "Auto-heal workflows", "-{p}% breaches"),
    ("Document intelligence", "Extract & verify documents automatically", "Audit-grade lineage", "-{p}% TAT"),
]
DOMAIN_CONTEXT = {
    "Auto": "dealer network", "Finance": "loan book", "Collections": "recovery pipeline",
    "Logistics": "freight corridors", "Circularity": "credit marketplace", "Trust": "decision ledger",
    "Copilot": "analytics copilot", "XR": "immersive workflows", "Platform": "AI platform",
}


def generate(cfg: GenConfig) -> None:
    rng = random.Random(cfg.seed + 13)

    buckets, solutions, poc = [], [], []
    lo, hi = cfg.solutions_per_bucket
    order = 0
    for i, (bucket_name, tag) in enumerate(BUCKETS[: cfg.n(len(BUCKETS))]):
        buckets.append({"name": bucket_name, "tag": tag, "sort_order": i})
        for j in range(rng.randint(lo, hi)):
            cap = rng.choice(CAPABILITIES)
            context = DOMAIN_CONTEXT[tag]
            name = f"{cap[0]} — {context.title()}"
            # keep solution names unique across buckets
            k = 2
            while any(s["name"] == name for s in solutions):
                name = f"{cap[0]} {k} — {context.title()}"
                k += 1
            solutions.append({
                "bucket_name": bucket_name,
                "name": name,
                "problem": f"{cap[1]} across the {context}.",
                "solution": f"{cap[2]} powering {cap[0].lower()} for the {context}.",
                "differentiator": f"Mahindra group data fabric + causal explanations tuned to the {context}.",
                "impact": cap[3].format(p=round(rng.uniform(8, 32), 0)),
                "sort_order": order,
            })
            order += 1

    write_csv("solution_buckets", buckets)
    write_csv("solutions", solutions)

    # PoC roadmap: shortlist top solutions with priority/complexity ratings.
    picks = rng.sample(solutions, min(cfg.n(cfg.poc_items), len(solutions)))
    poc = [
        {
            "name": s["name"],
            "bucket": s["bucket_name"],
            "priority": rng.choice(["High", "Medium", "Low"]),
            "complexity": rng.choice(["Low", "Medium", "High"]),
            "sort_order": i,
        }
        for i, s in enumerate(picks)
    ]
    write_csv("poc_items", poc)
    _ = SOLUTION_TAGS  # tag pool mirrors backend seed_data.SOLUTION_TAGS


if __name__ == "__main__":
    generate(GenConfig())
