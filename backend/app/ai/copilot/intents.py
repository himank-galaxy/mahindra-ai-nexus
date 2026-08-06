"""Keyword → intent registry for the rule-based copilot.

Ordered, first-match-wins — an exact port of ``generateCopilotResponse`` in
``frontend/src/lib/copilot.ts``. Each entry pairs a predicate over the
lower-cased prompt with the response payload (answer / explanation / sql /
python / optional chart or table / action / confidence).
"""

from __future__ import annotations

from collections.abc import Callable

IntentResult = dict[str, object]

_BOOKING_PUNE: IntentResult = {
    "answer": (
        "Bookings in Pune dropped 12.4% week-on-week, driven mainly by dealer follow-up "
        "leakage and reduced exchange bonus perception."
    ),
    "explanation": (
        "Causal decomposition attributes 47% of the drop to follow-up leakage at 2 dealers, "
        "28% to competitor promo activity, 15% to finance approval delay, and 10% to walk-in decline."
    ),
    "sql": (
        "SELECT dealer, SUM(bookings) AS b\n"
        "FROM auto.bookings\n"
        "WHERE region = 'West' AND city = 'Pune'\n"
        "  AND week BETWEEN '2026-06-20' AND '2026-06-27'\n"
        "GROUP BY dealer\n"
        "ORDER BY b DESC;"
    ),
    "python": (
        "df = load('bookings.pune')\n"
        "drop = causal.attribute(df, target='bookings', drivers=['followup','promo','finance_tat','walkins'])\n"
        "print(drop.top(4))"
    ),
    "chart": [
        {"label": "Follow-up", "value": 47},
        {"label": "Competitor", "value": 28},
        {"label": "Finance TAT", "value": 15},
        {"label": "Walk-ins", "value": 10},
    ],
    "action": "Launch exchange-bonus campaign + assign follow-up SLA to top 2 Pune dealers.",
    "confidence": 89,
}

_DEALER_LEAKAGE: IntentResult = {
    "answer": (
        "Top 3 dealers by revenue leakage: Lucknow Motors (21%), Nashik Mobility Hub (17%), Chennai Auto Prime (14%)."
    ),
    "explanation": (
        "Leakage attributed to missed follow-ups within 2 hours of hot lead creation and to "
        "under-utilized test-drive slots."
    ),
    "sql": "SELECT dealer, leakage_pct FROM auto.dealer_kpi ORDER BY leakage_pct DESC LIMIT 5;",
    "python": ("leak = kpi.groupby('dealer').agg({'leakage': 'mean'}).sort_values('leakage', ascending=False)"),
    "table": {
        "headers": ["Dealer", "Leakage", "Revenue at Risk"],
        "rows": [
            ["Lucknow Motors", "21%", "₹0.7 Cr"],
            ["Nashik Mobility Hub", "17%", "₹1.1 Cr"],
            ["Chennai Auto Prime", "14%", "₹0.9 Cr"],
        ],
    },
    "action": "Push next-best-action coach to top 3 dealers + auto-escalate stale hot leads.",
    "confidence": 92,
}

_COLLECTIONS_ROLL_FORWARD: IntentResult = {
    "answer": (
        "8,420 medium-risk accounts show high roll-forward probability. Digital-first outreach "
        "recommended for 71% of them."
    ),
    "explanation": (
        "Roll-forward driven by income variability + prior 30-DPD history. Digital-first is "
        "cheaper and non-invasive for these segments."
    ),
    "sql": (
        "SELECT customer_id, roll_forward_prob FROM fin.collections\n"
        "WHERE segment='medium' AND roll_forward_prob > 0.6;"
    ),
    "python": (
        "seg = collections.query('segment==\"medium\"')\n"
        "high = seg[seg.roll_forward_prob > 0.6]\n"
        "channel = optimizer.recommend(high)"
    ),
    "chart": [
        {"label": "Digital", "value": 71},
        {"label": "Voice", "value": 18},
        {"label": "Field", "value": 11},
    ],
    "action": "Trigger Collections AI Swarm with digital-first playbook + compliance guardrail.",
    "confidence": 87,
}

_LOGISTICS_SLA: IntentResult = {
    "answer": (
        "Mundra Port → NCR and Kolkata → Guwahati have SLA breach probability above 55%. Auto-heal reroute recommended."
    ),
    "explanation": (
        "Weather disruption + warehouse dock congestion increases delay probability. Split-load "
        "with air uplift reduces breach risk by ~38%."
    ),
    "sql": "SELECT route, delay_prob, sla_risk FROM log.routes WHERE sla_risk > 0.45;",
    "python": "at_risk = routes[routes.sla_risk > 0.45]\nplan = autoheal.recommend(at_risk)",
    "chart": [
        {"label": "Mundra→NCR", "value": 67},
        {"label": "Kolkata→Guwahati", "value": 61},
        {"label": "Chennai→Blr", "value": 52},
    ],
    "action": "Approve auto-heal workflow for 2 high-risk corridors and notify customers.",
    "confidence": 85,
}

_CIRCULARITY_CREDITS: IntentResult = {
    "answer": (
        "36 credits show low closure probability. Reprice batch CR-2216 and CR-2218 by -10% to improve buyer match."
    ),
    "explanation": (
        "Traceability gap in dMRV + weak buyer match reduces closure. Repricing + additional "
        "traceability metadata lifts closure ~19%."
    ),
    "sql": "SELECT credit_id, closure_prob FROM circ.credits WHERE closure_prob < 0.5;",
    "python": ("low = credits[credits.closure_prob < 0.5]\nnew_price = pricer.reprice(low, elasticity=0.35)"),
    "table": {
        "headers": ["Credit ID", "Type", "Old Price", "New Price"],
        "rows": [
            ["CR-2216", "SDG", "₹2,180", "₹1,960"],
            ["CR-2218", "Carbon", "₹1,120", "₹1,010"],
        ],
    },
    "action": "Approve repricing batch and refresh marketplace listings.",
    "confidence": 81,
}

_WARRANTY_BATCH: IntentResult = {
    "answer": (
        "Warranty spike attributed to vehicle batch B-2214 — supplier component variance is the dominant causal driver."
    ),
    "explanation": (
        "Graph anomaly on batch B-2214 correlates with a component supplier shift on Week 22. "
        "Confidence high after cross-checking service telemetry."
    ),
    "sql": "SELECT batch, claim_rate FROM warranty.claims WHERE batch='B-2214';",
    "python": "anom = graph.detect(warranty, groupby='batch')\nprint(anom.top())",
    "chart": [
        {"label": "B-2214 Comp", "value": 62},
        {"label": "Assembly", "value": 18},
        {"label": "Dealer PDI", "value": 12},
        {"label": "Other", "value": 8},
    ],
    "action": "Quarantine batch + open supplier corrective action.",
    "confidence": 90,
}

_BOARD_ROI: IntentResult = {
    "answer": (
        "Highest-ROI starting point: AI Simulation Center + Dealer Revenue Optimizer + "
        "Financial Services AI Command Center."
    ),
    "explanation": (
        "Combined 6-month impact: ₹412 Cr predicted revenue uplift, ₹86 Cr leakage prevented, "
        "-11.4% financial risk. Reusable across group."
    ),
    "sql": "-- Executive KPI rollup\nSELECT usecase, SUM(impact_inr) FROM ai.outcomes GROUP BY usecase;",
    "python": "roll = outcomes.groupby('usecase').impact.sum().sort_values(ascending=False)",
    "chart": [
        {"label": "Sim Center", "value": 148},
        {"label": "Dealer Opt", "value": 124},
        {"label": "Fin AI", "value": 96},
        {"label": "Circular", "value": 44},
    ],
    "action": "Launch 3 flagship PoCs in Q1 with shared Trust Ledger.",
    "confidence": 93,
}

# Ordered rules — first match wins, mirroring the TS if-chain.
INTENT_RULES: list[tuple[Callable[[str], bool], IntentResult]] = [
    (lambda p: "booking" in p and "pune" in p, _BOOKING_PUNE),
    (lambda p: "dealer" in p or "leakage" in p, _DEALER_LEAKAGE),
    (
        lambda p: "roll forward" in p or "finance" in p or "collections" in p,
        _COLLECTIONS_ROLL_FORWARD,
    ),
    (lambda p: "logistics" in p or "sla" in p or "route" in p, _LOGISTICS_SLA),
    (lambda p: "credit" in p or "circularity" in p or "carbon" in p, _CIRCULARITY_CREDITS),
    (lambda p: "warranty" in p, _WARRANTY_BATCH),
    (
        lambda p: "board" in p or "summary" in p or "roi" in p or "use case" in p,
        _BOARD_ROI,
    ),
]
