"""Financial Services product portfolio (loans, insurance & add-ons).

Tables: finance_products.

Covers the "loan" and "insurance" entities as product cards — the same shape
the Finance page renders (name, customers, risk, cross-sell, opportunity).
"""

from __future__ import annotations

import random

from common import GenConfig, business_chain_score, inr, make_faker, write_csv

PRODUCTS = [
    ("Vehicle Loan", "Lending"),
    ("Two-Wheeler Loan", "Lending"),
    ("Commercial Vehicle Loan", "Lending"),
    ("Loan Protection Insurance", "Insurance"),
    ("Comprehensive Vehicle Insurance", "Insurance"),
    ("EMI Shield", "Insurance"),
    ("Extended Warranty", "Add-on"),
    ("Service Plan Bundle", "Add-on"),
    ("Exchange Bonus Program", "Retention"),
    ("Top-up Loan", "Lending"),
]
OPPORTUNITIES = [
    "Cross-sell to {n} pre-approved customers",
    "Renewal wave next quarter: {n} policies",
    "Reduce TAT to lift conversion by {p}%",
    "Target {n} thin-file customers with alt-data",
    "Bundle with XUV700 festive offer",
]


def generate(cfg: GenConfig) -> None:
    rng = random.Random(cfg.seed + 4)

    rows = []
    for i, (name, _category) in enumerate(PRODUCTS[: cfg.n(cfg.finance_products)]):
        chain = business_chain_score(rng)
        rows.append({
            "name": name,
            "customers": f"{rng.randint(2, 64):,}K",
            "risk": f"{rng.randint(20, 100 - chain['finance_approval'] + 40)}% low" if chain["finance_approval"] >= 60 else f"{rng.randint(5, 35)}% elevated",
            "cross_sell": f"+{round(rng.uniform(2, 14), 1)}%",
            "opportunity": rng.choice(OPPORTUNITIES).format(n=rng.randint(400, 5200), p=round(rng.uniform(3, 12), 1)),
            "sort_order": i,
        })

    write_csv("finance_products", rows)
    _ = inr  # reserved for future amount columns


if __name__ == "__main__":
    generate(GenConfig())
