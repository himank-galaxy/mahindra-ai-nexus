"""Financial Twin: customer twins with NBA, risk decomposition, cross-sell.

Tables: customer_twins.

Interconnection: income stability & repayment behaviour come from the same
business chain that drives dealer leads (finance approval leg), so customer
risk profiles correlate with the dealer funnel quality.
"""

from __future__ import annotations

import random

from common import REGION_CITIES, REGIONS, GenConfig, business_chain_score, inr, jdump, make_faker, write_csv

PRODUCT_POOL = ["Vehicle Loan", "Insurance", "Warranty Ext.", "EMI Shield", "Exchange", "Service Plan"]
NBA_ACTIONS = [
    "Pre-approve top-up loan",
    "Offer EMI holiday for 2 months",
    "Pitch insurance renewal bundling",
    "Upgrade to premium variant with exchange",
    "Send service plan discount",
    "Refer to relationship manager",
]


def generate(cfg: GenConfig) -> None:
    fake = make_faker(cfg.seed + 3)
    rng = random.Random(cfg.seed + 3)

    rows: list[dict] = []
    for i in range(cfg.n(cfg.customers)):
        region = REGIONS[i % len(REGIONS)]
        chain = business_chain_score(rng)

        if chain["finance_approval"] >= 70:
            stability, repayment, approval = "High", "On-time", "approved"
        elif chain["finance_approval"] >= 45:
            stability, repayment = rng.choice([("Medium", "On-time"), ("Medium", "1 late")])
            approval = "draft"
        else:
            stability, repayment = rng.choice([("Low", "1 late"), ("Low", "2 late")])
            approval = "under_review"

        products = rng.sample(PRODUCT_POOL, rng.randint(1, 4))
        candidates = [p for p in PRODUCT_POOL if p not in products]
        cross_sell = {
            product: f"{max(10, min(95, chain['csat'] + rng.randint(-15, 15)))}%"
            for product in rng.sample(candidates, min(len(candidates), rng.randint(2, 3)))
        }

        rows.append({
            "name": fake.unique.first_name() + " " + fake.last_name(),
            "location": rng.choice(REGION_CITIES[region]),
            "income_stability": stability,
            "repayment": repayment,
            "products": jdump(products),
            "nba": jdump({
                "headline": rng.choice(NBA_ACTIONS),
                "risk": rng.choice(["Low", "Medium"]) if chain["finance_approval"] >= 55 else "Elevated",
                "expected_margin": inr(rng.uniform(0.2, 1.6)),
                "confidence": chain["finance_approval"],
            }),
            "risk_decomposition": jdump({
                "credit": f"{rng.randint(10, 45)}%",
                "income": f"{rng.randint(5, 30)}%",
                "behaviour": f"{rng.randint(5, 25)}%",
                "market": f"{rng.randint(2, 15)}%",
            }),
            "cross_sell": jdump(cross_sell),
            "approval_status": approval,
        })

    write_csv("customer_twins", rows)


if __name__ == "__main__":
    generate(GenConfig())
