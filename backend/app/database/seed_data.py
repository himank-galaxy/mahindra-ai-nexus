"""Deterministic seed data — verbatim port of the frontend mock datasets.

Sources mirrored 1:1 (guarantees an identical first render once the API is
wired in Phase 5):

- ``frontend/src/lib/mock-data.ts``  — KPIs, recommendations, catalogue,
  dealers, leads, finance products, collections cases, routes, credits,
  trust ledger, agents, suggested prompts, regions, models.
- ``frontend/src/routes/mobility-twin.tsx`` — causal nodes/edges, KPIs, Q&A.
- ``frontend/src/routes/collections.tsx``   — swarm agents, metric tiles.
- ``frontend/src/routes/logistics.tsx``     — warehouse signal tiles.
- ``frontend/src/routes/circularity.tsx``   — RVSF tiles, dMRV Q&A.
- ``frontend/src/routes/finance.tsx``       — Suresh Jadhav customer twin.
- ``frontend/src/routes/trust.tsx``         — compliance rules.
- ``frontend/src/routes/xr.tsx``            — XR experience cards.

Never edit values here without the matching frontend change — parity is
asserted by tests.
"""

from __future__ import annotations

REGIONS = ["West", "North", "South", "East"]

VEHICLE_MODELS = ["XUV700", "Scorpio-N", "Thar", "Bolero", "XUV 3XO"]

# Catalogue filter chips (frontend SOLUTION_TAGS; superset of bucket tags).
SOLUTION_TAGS = [
    "Auto",
    "Finance",
    "Logistics",
    "Circularity",
    "ESG",
    "Compliance",
    "Copilot",
    "Simulation",
    "Agentic AI",
]

KPIS = [
    {
        "code": "rev",
        "label": "Predicted Revenue Uplift",
        "value": "₹412 Cr",
        "trend": "+8.4%",
        "up": True,
        "confidence": 92,
        "drivers": [
            "West Zone booking conversion +12%",
            "Rural low-risk finance approval +9%",
            "Dealer follow-up leakage -14%",
            "XUV700 exchange bonus response +18%",
        ],
    },
    {
        "code": "leak",
        "label": "Leakage Prevented",
        "value": "₹86 Cr",
        "trend": "+4.1%",
        "up": True,
        "confidence": 88,
        "drivers": [
            "Warranty anomaly caught in batch B-2214",
            "Duplicate collections outreach avoided",
            "Dealer discount policy breach flagged",
            "Route reassignment prevented SLA penalty",
        ],
    },
    {
        "code": "conv",
        "label": "Dealer Conversion Uplift",
        "value": "+7.8%",
        "trend": "+2.2 pts",
        "up": True,
        "confidence": 90,
        "drivers": [
            "Next-best-action pitch adoption 71%",
            "Test-drive slot AI scheduler",
            "Finance pre-approval speed -37%",
            "Personalized WhatsApp brochures",
        ],
    },
    {
        "code": "risk",
        "label": "Financial Risk Reduction",
        "value": "-11.4%",
        "trend": "-1.6 pts",
        "up": True,
        "confidence": 87,
        "drivers": [
            "Thin-file rural credit twin",
            "Early roll-forward detection",
            "Channel optimization for medium risk",
            "Fraud graph flagged 214 anomalies",
        ],
    },
    {
        "code": "sla",
        "label": "SLA Breach Avoidance",
        "value": "23,420",
        "trend": "+12%",
        "up": True,
        "confidence": 85,
        "drivers": [
            "Predictive delay model on 5 corridors",
            "Auto-heal reroute workflows",
            "Warehouse dock congestion signal",
            "Weather-adjusted ETA",
        ],
    },
    {
        "code": "esg",
        "label": "ESG / Circularity Value",
        "value": "₹38 Cr",
        "trend": "+6.2%",
        "up": True,
        "confidence": 81,
        "drivers": [
            "ELV valuation optimization",
            "Carbon credit repricing",
            "dMRV completeness +23%",
            "Buyer match score improved",
        ],
    },
]

RECOMMENDATIONS = [
    {
        "code": "r1",
        "title": "Reallocate 120 XUV units from low-conversion dealers to West Zone",
        "impact": "₹18.4 Cr revenue",
        "confidence": 91,
        "risk": "low",
    },
    {
        "code": "r2",
        "title": "Launch targeted exchange-bonus campaign for Pune & Nashik",
        "impact": "+9.2% bookings",
        "confidence": 87,
        "risk": "low",
    },
    {
        "code": "r3",
        "title": "Prioritize 8,420 medium-risk collections cases for digital outreach",
        "impact": "₹6.1 Cr recovery",
        "confidence": 89,
        "risk": "medium",
    },
    {
        "code": "r4",
        "title": "Reprice 36 circularity certificates with low closure probability",
        "impact": "₹1.8 Cr ESG revenue",
        "confidence": 78,
        "risk": "medium",
    },
    {
        "code": "r5",
        "title": "Investigate warranty anomaly in vehicle batch B-2214",
        "impact": "Prevent ₹2.4 Cr claims",
        "confidence": 84,
        "risk": "high",
    },
]

SOLUTION_BUCKETS = [
    {
        "name": "Auto, Mobility & Dealer Intelligence",
        "tag": "Auto",
        "items": [
            {
                "name": "Auto Mobility Causal Twin",
                "problem": "Fragmented view of demand→delivery→service",
                "solution": "Causal decision graph linking OEM to CX",
                "diff": "Causal + counterfactual reasoning",
                "impact": "+7% conversion, -12% cancellation",
            },
            {
                "name": "Dealer Revenue Optimizer",
                "problem": "Leaked leads & inconsistent follow-up",
                "solution": "Next-best-action for every lead",
                "diff": "Learns dealer-specific behavior",
                "impact": "+₹42 Cr dealer revenue",
            },
            {
                "name": "Warranty & Quality Early-Warning Graph",
                "problem": "Late warranty spike detection",
                "solution": "Graph anomaly detection on components",
                "diff": "Batch-level causal linkage",
                "impact": "-18% claim cost",
            },
            {
                "name": "Aftermarket & Pre-Owned Commerce AI",
                "problem": "Weak pricing & matching",
                "solution": "Dynamic pricing + buyer match",
                "diff": "Multi-channel demand signal fusion",
                "impact": "+11% margin",
            },
            {
                "name": "AR/VR/XR Experience Intelligence",
                "problem": "Static showroom & training",
                "solution": "Immersive AI journeys",
                "diff": "Personalized to role & context",
                "impact": "+22% training ROI",
            },
        ],
    },
    {
        "name": "Financial Services Intelligence",
        "tag": "Finance",
        "items": [
            {
                "name": "Thin-File Rural Credit Twin",
                "problem": "Limited traditional credit data",
                "solution": "Alternate-data credit twin",
                "diff": "Behavior + geo + agri signals",
                "impact": "+14% approval, -9% NPA",
            },
            {
                "name": "Collections & Recovery AI Swarm",
                "problem": "Blunt collections strategy",
                "solution": "Multi-agent decisioning",
                "diff": "Compliance-guarded agents",
                "impact": "+11% recovery",
            },
            {
                "name": "Insurance, MF & Wealth Copilots",
                "problem": "Underused customer signal",
                "solution": "Cross-product copilot",
                "diff": "Unified customer twin",
                "impact": "+18% cross-sell",
            },
            {
                "name": "Fraud, Mis-selling & Business Quality Graph",
                "problem": "Reactive fraud detection",
                "solution": "Graph-based anomaly network",
                "diff": "Explainable to auditor",
                "impact": "-24% mis-selling",
            },
        ],
    },
    {
        "name": "AI Simulation Center",
        "tag": "Simulation",
        "items": [
            {
                "name": "What-if Business Simulations",
                "problem": "Decisions made without testing",
                "solution": "Business flight simulator",
                "diff": "Causal + optimization loop",
                "impact": "Faster, safer decisions",
            },
            {
                "name": "Causal Impact Analysis",
                "problem": "Correlation ≠ causation",
                "solution": "Counterfactual reasoning",
                "diff": "Boardroom-ready explanations",
                "impact": "Higher trust",
            },
            {
                "name": "Predictive Optimization",
                "problem": "Reactive planning",
                "solution": "Constraint-aware optimization",
                "diff": "Explainable trade-offs",
                "impact": "+8% margin",
            },
            {
                "name": "Scenario Planning",
                "problem": "Ad-hoc annual planning",
                "solution": "Continuous scenario library",
                "diff": "Reusable scenario templates",
                "impact": "Faster response",
            },
        ],
    },
    {
        "name": "Non-Auto Growth Businesses",
        "tag": "Logistics",
        "items": [
            {
                "name": "Logistics AI Control Tower",
                "problem": "SLA visibility gaps",
                "solution": "Predictive + auto-heal ops",
                "diff": "Causal delay attribution",
                "impact": "-32% SLA breach",
            },
            {
                "name": "Real Estate & Hospitality Intelligence",
                "problem": "Static occupancy planning",
                "solution": "Demand + guest experience AI",
                "diff": "Cross-property learning",
                "impact": "+9% RevPAR",
            },
            {
                "name": "Renewable Energy Asset Intelligence",
                "problem": "Underused telemetry",
                "solution": "Asset health + generation forecast",
                "diff": "Weather-fused causal",
                "impact": "-14% downtime",
            },
        ],
    },
    {
        "name": "Circular Economy & ESG Intelligence",
        "tag": "Circularity",
        "items": [
            {
                "name": "ELV Valuation",
                "problem": "Inconsistent scrap pricing",
                "solution": "AI valuation model",
                "diff": "Doc-completeness aware",
                "impact": "+₹6 Cr margin",
            },
            {
                "name": "RVSF Operations Intelligence",
                "problem": "Throughput bottlenecks",
                "solution": "Job-card delay prediction",
                "diff": "dMRV integrated",
                "impact": "+21% throughput",
            },
            {
                "name": "Carbon / SDG Credit Intelligence",
                "problem": "Illiquid credits",
                "solution": "Dynamic pricing + buyer match",
                "diff": "Traceability-driven trust",
                "impact": "+₹18 Cr ESG value",
            },
            {
                "name": "dMRV & Compliance Trust Layer",
                "problem": "Manual verification",
                "solution": "Continuous digital MRV",
                "diff": "Audit-ready lineage",
                "impact": "-60% audit time",
            },
        ],
    },
    {
        "name": "Horizontal AI Factory",
        "tag": "Agentic AI",
        "items": [
            {
                "name": "Multi-Agent Ecosystem",
                "problem": "Siloed AI models",
                "solution": "Orchestrated agent registry",
                "diff": "Memory + guardrails + HITL",
                "impact": "Reusable Group-wide",
            },
            {
                "name": "Auto-Code Analytics Copilot",
                "problem": "Slow analyst cycles",
                "solution": "NL → SQL/Python + charts",
                "diff": "Executive-ready outputs",
                "impact": "10x analyst throughput",
            },
            {
                "name": "HITL Learning",
                "problem": "Static models",
                "solution": "Human feedback learning",
                "diff": "Continuous improvement",
                "impact": "Model drift avoided",
            },
            {
                "name": "Auto-Heal Workflows",
                "problem": "Manual incident response",
                "solution": "AI-driven remediation",
                "diff": "Approval-gated automation",
                "impact": "-45% MTTR",
            },
            {
                "name": "Governance & Compliance",
                "problem": "Ad-hoc AI oversight",
                "solution": "Trust ledger for every decision",
                "diff": "Data lineage + confidence",
                "impact": "Audit-ready",
            },
        ],
    },
]

DEALERS = [
    {
        "code": "d1",
        "name": "Pune Auto World",
        "leads": 142,
        "hot_leads": 28,
        "test_drives_pending": 14,
        "booking_prob": 71,
        "revenue_at_risk": "₹1.8 Cr",
        "leakage_pct": 12,
        "bay_util_pct": 82,
    },
    {
        "code": "d2",
        "name": "Nashik Mobility Hub",
        "leads": 98,
        "hot_leads": 21,
        "test_drives_pending": 9,
        "booking_prob": 66,
        "revenue_at_risk": "₹1.1 Cr",
        "leakage_pct": 17,
        "bay_util_pct": 74,
    },
    {
        "code": "d3",
        "name": "Jaipur SUV Center",
        "leads": 121,
        "hot_leads": 33,
        "test_drives_pending": 18,
        "booking_prob": 69,
        "revenue_at_risk": "₹1.4 Cr",
        "leakage_pct": 9,
        "bay_util_pct": 79,
    },
    {
        "code": "d4",
        "name": "Chennai Auto Prime",
        "leads": 88,
        "hot_leads": 19,
        "test_drives_pending": 11,
        "booking_prob": 63,
        "revenue_at_risk": "₹0.9 Cr",
        "leakage_pct": 14,
        "bay_util_pct": 68,
    },
    {
        "code": "d5",
        "name": "Lucknow Motors",
        "leads": 76,
        "hot_leads": 15,
        "test_drives_pending": 8,
        "booking_prob": 58,
        "revenue_at_risk": "₹0.7 Cr",
        "leakage_pct": 21,
        "bay_util_pct": 61,
    },
]

# Mock data shows one lead pool; the demo selects dealer d1 by default, so
# all ported leads belong to Pune Auto World.
DEALER_LEADS = [
    {
        "dealer": "d1",
        "name": "Rakesh Patil",
        "vehicle": "XUV700",
        "score": 92,
        "prob": 74,
        "action": "Call within 2 hours + exchange bonus",
        "revenue": "₹19.8L",
        "status": "hot",
    },
    {
        "dealer": "d1",
        "name": "Asha Verma",
        "vehicle": "Thar",
        "score": 86,
        "prob": 68,
        "action": "Offer test drive slot",
        "revenue": "₹16.4L",
        "status": "warm",
    },
    {
        "dealer": "d1",
        "name": "Imran Shaikh",
        "vehicle": "Scorpio-N",
        "score": 79,
        "prob": 61,
        "action": "Send finance pre-approval",
        "revenue": "₹17.2L",
        "status": "warm",
    },
    {
        "dealer": "d1",
        "name": "Priya Nair",
        "vehicle": "XUV 3XO",
        "score": 72,
        "prob": 54,
        "action": "WhatsApp video brochure",
        "revenue": "₹11.6L",
        "status": "warm",
    },
    {
        "dealer": "d1",
        "name": "Sandeep Rao",
        "vehicle": "Bolero",
        "score": 68,
        "prob": 49,
        "action": "Schedule finance advisor callback",
        "revenue": "₹9.8L",
        "status": "cool",
    },
]

FINANCE_PRODUCTS = [
    {
        "name": "Vehicle Loans",
        "customers": "1.42M",
        "risk": "Low",
        "cross_sell": "High",
        "opportunity": "Repeat buyers",
    },
    {"name": "SME Loans", "customers": "84K", "risk": "Medium", "cross_sell": "High", "opportunity": "Working capital"},
    {
        "name": "Digital Finance",
        "customers": "612K",
        "risk": "Low",
        "cross_sell": "Medium",
        "opportunity": "Instant top-up",
    },
    {
        "name": "Fixed Deposits",
        "customers": "241K",
        "risk": "Very Low",
        "cross_sell": "Medium",
        "opportunity": "Family FD",
    },
    {"name": "Leasing", "customers": "38K", "risk": "Low", "cross_sell": "Low", "opportunity": "Fleet upgrade"},
    {
        "name": "Rural Housing Finance",
        "customers": "182K",
        "risk": "Medium",
        "cross_sell": "Medium",
        "opportunity": "Land + build",
    },
    {
        "name": "Insurance Broking",
        "customers": "920K",
        "risk": "Low",
        "cross_sell": "Very High",
        "opportunity": "Motor renewal",
    },
    {"name": "Mutual Funds", "customers": "156K", "risk": "Low", "cross_sell": "High", "opportunity": "SIP upgrade"},
]

CUSTOMER_TWINS = [
    {
        "name": "Suresh Jadhav",
        "location": "Sangli, Maharashtra",
        "income_stability": "Medium-High",
        "repayment": "Good",
        "products": ["Tractor Loan", "Motor Insurance", "Fixed Deposit"],
        "nba": {
            "headline": "Offer ₹4.5L pre-approved SME working capital loan",
            "risk": "Low",
            "expected_margin": "₹42K",
            "confidence": 87,
        },
        "risk_decomposition": {
            "Repayment history": "A",
            "Alt-data signal": "A-",
            "Agri-cycle": "B+",
            "Geography": "A",
        },
        "cross_sell": {
            "SME loan": "87%",
            "Life insurance": "62%",
            "SIP": "41%",
        },
    },
]

COLLECTIONS_AGENTS = [
    {"name": "Risk Prediction Agent", "status": "active"},
    {"name": "Channel Optimization Agent", "status": "active"},
    {"name": "Offer Recommendation Agent", "status": "recommended"},
    {"name": "Field Route Agent", "status": "active"},
    {"name": "Compliance Guardrail Agent", "status": "reviewing"},
    {"name": "Human Review Agent", "status": "active"},
]

COLLECTIONS_CASES = [
    {
        "customer": "Ganesh Kulkarni",
        "dpd": 42,
        "outstanding": "₹1.24L",
        "roll_forward_risk": 74,
        "channel": "Voice + WhatsApp",
        "action": "Restructure offer",
        "prob": 68,
        "compliance_flag": "ok",
    },
    {
        "customer": "Farah Ansari",
        "dpd": 28,
        "outstanding": "₹86K",
        "roll_forward_risk": 58,
        "channel": "Digital-first",
        "action": "Pay-link nudge",
        "prob": 71,
        "compliance_flag": "ok",
    },
    {
        "customer": "Mohan Rathi",
        "dpd": 61,
        "outstanding": "₹2.14L",
        "roll_forward_risk": 82,
        "channel": "Field visit",
        "action": "Field officer + settlement",
        "prob": 54,
        "compliance_flag": "review",
    },
    {
        "customer": "Kavita Iyer",
        "dpd": 15,
        "outstanding": "₹42K",
        "roll_forward_risk": 34,
        "channel": "Auto-debit retry",
        "action": "Retry + reminder",
        "prob": 84,
        "compliance_flag": "ok",
    },
    {
        "customer": "Vikram Singh",
        "dpd": 88,
        "outstanding": "₹3.62L",
        "roll_forward_risk": 91,
        "channel": "Legal",
        "action": "Legal notice review",
        "prob": 38,
        "compliance_flag": "escalate",
    },
]

LOGISTICS_ROUTES = [
    {
        "name": "Mumbai → Pune",
        "sla_risk": 22,
        "delay_prob": 34,
        "cost": "₹1.2L",
        "recommended_action": "Reroute via Panvel",
    },
    {
        "name": "Chennai → Bengaluru",
        "sla_risk": 41,
        "delay_prob": 52,
        "cost": "₹2.4L",
        "recommended_action": "Shift to night lane",
    },
    {"name": "Delhi → Jaipur", "sla_risk": 18, "delay_prob": 24, "cost": "₹0.8L", "recommended_action": "Maintain"},
    {
        "name": "Mundra Port → NCR",
        "sla_risk": 58,
        "delay_prob": 67,
        "cost": "₹4.1L",
        "recommended_action": "Split load + air uplift",
    },
    {
        "name": "Kolkata → Guwahati",
        "sla_risk": 47,
        "delay_prob": 61,
        "cost": "₹3.2L",
        "recommended_action": "Weather delay buffer",
    },
]

CARBON_CREDITS = [
    {"code": "CR-2214", "type": "Carbon", "price": "₹1,240", "buyer_match": 82, "closure_prob": 71, "traceability": 88},
    {"code": "CR-2215", "type": "EPR", "price": "₹840", "buyer_match": 74, "closure_prob": 63, "traceability": 79},
    {"code": "CR-2216", "type": "SDG", "price": "₹2,180", "buyer_match": 66, "closure_prob": 48, "traceability": 72},
    {"code": "CR-2217", "type": "CD", "price": "₹1,560", "buyer_match": 88, "closure_prob": 79, "traceability": 91},
    {"code": "CR-2218", "type": "Carbon", "price": "₹1,120", "buyer_match": 58, "closure_prob": 41, "traceability": 68},
]

TRUST_DECISIONS = [
    {
        "code": "AUTO-1042",
        "use_case": "Vehicle allocation to West Zone",
        "recommendation": "Reallocate 120 units",
        "data_sources": "Bookings, dealer capacity, waiting list",
        "confidence": 91,
        "approval": "approved",
        "risk": "low",
        "audit": "complete",
    },
    {
        "code": "FIN-8821",
        "use_case": "Rural SME loan approval",
        "recommendation": "Approve ₹4.5L",
        "data_sources": "Alternate credit, geo, agri",
        "confidence": 87,
        "approval": "approved",
        "risk": "low",
        "audit": "complete",
    },
    {
        "code": "COLL-3329",
        "use_case": "Restructuring offer",
        "recommendation": "Offer 6-month plan",
        "data_sources": "DPD, income stability",
        "confidence": 78,
        "approval": "human_review",
        "risk": "medium",
        "audit": "pending",
    },
    {
        "code": "CIRC-7712",
        "use_case": "Carbon credit repricing",
        "recommendation": "Reprice batch -12%",
        "data_sources": "Buyer demand, traceability",
        "confidence": 74,
        "approval": "pending",
        "risk": "medium",
        "audit": "pending",
    },
    {
        "code": "LOG-2281",
        "use_case": "SLA reroute",
        "recommendation": "Split load via air",
        "data_sources": "Route telemetry, weather",
        "confidence": 82,
        "approval": "approved",
        "risk": "low",
        "audit": "complete",
    },
]

# Six lineage steps rendered by the trust lineage modal (frontend builds them
# from row fields; we persist the same structure server-side).
TRUST_LINEAGE_STATIC_STEPS = [
    (5, "Action taken", "Executed via Action Agent · SLA logged"),
    (6, "Feedback captured", "Outcome fed to Learning Agent"),
]

COMPLIANCE_RULES = [
    {"label": "Consent check", "status": "OK"},
    {"label": "Bias / fairness check", "status": "OK"},
    {"label": "Regulatory rule check", "status": "OK"},
    {"label": "Business policy check", "status": "1 pending"},
    {"label": "Audit trail complete", "status": "OK"},
]

AI_AGENTS = [
    {
        "name": "Data Agent",
        "role": "Ingest & normalize signals",
        "status": "active",
        "last_activity": "Refreshed dealer feed 2m ago",
        "use_areas": ["Auto", "Finance"],
    },
    {
        "name": "Prediction Agent",
        "role": "Forecast outcomes",
        "status": "active",
        "last_activity": "Forecast bookings Pune",
        "use_areas": ["Auto", "Logistics"],
    },
    {
        "name": "Causal Graph Agent",
        "role": "Explain drivers",
        "status": "active",
        "last_activity": "Explained cancellation drivers",
        "use_areas": ["Auto"],
    },
    {
        "name": "Simulation Agent",
        "role": "What-if scenarios",
        "status": "reviewing",
        "last_activity": "Tested exchange bonus",
        "use_areas": ["Auto", "Finance"],
    },
    {
        "name": "Code Analytics Agent",
        "role": "NL→SQL/Python",
        "status": "active",
        "last_activity": "Generated warranty query",
        "use_areas": ["All"],
    },
    {
        "name": "Compliance Agent",
        "role": "Guardrails & policy",
        "status": "active",
        "last_activity": "Blocked risky offer",
        "use_areas": ["Finance"],
    },
    {
        "name": "Action Agent",
        "role": "Execute approved actions",
        "status": "recommended",
        "last_activity": "Sent WhatsApp to 214 leads",
        "use_areas": ["Auto"],
    },
    {
        "name": "Human Review Agent",
        "role": "Route to human",
        "status": "active",
        "last_activity": "3 items pending",
        "use_areas": ["All"],
    },
    {
        "name": "Learning Agent",
        "role": "Feedback learning",
        "status": "active",
        "last_activity": "Updated propensity model",
        "use_areas": ["All"],
    },
    {
        "name": "Memory Agent",
        "role": "Long-term memory",
        "status": "active",
        "last_activity": "Stored 1,204 decisions",
        "use_areas": ["All"],
    },
]

XR_EXPERIENCES = [
    {
        "code": "showroom",
        "title": "AI Virtual Showroom",
        "use_case": "Immersive vehicle exploration",
        "feature": "Generative sales assistant + config",
        "impact": "+18% online-to-visit conversion",
    },
    {
        "code": "config",
        "title": "3D Vehicle Configurator",
        "use_case": "Personalized configurations",
        "feature": "Real-time AI recommendations",
        "impact": "+12% variant upsell",
    },
    {
        "code": "repair",
        "title": "AR Technician Repair Guide",
        "use_case": "Step-by-step service",
        "feature": "Component-aware AR overlays",
        "impact": "-24% repair time",
    },
    {
        "code": "training",
        "title": "VR Dealer Sales Training",
        "use_case": "Immersive skill building",
        "feature": "AI feedback on pitch & objections",
        "impact": "+22% training ROI",
    },
]

CAUSAL_NODES = [
    {
        "label": "Campaign Spend",
        "x": 50,
        "y": 60,
        "metric": "₹4.2 Cr",
        "trend": "+8%",
        "drivers": ["Digital-heavy allocation", "Regional festive push"],
        "action": "Reallocate 12% to programmatic",
    },
    {
        "label": "Lead Quality",
        "x": 180,
        "y": 60,
        "metric": "Score 72",
        "trend": "+4",
        "drivers": ["Better source mix", "Improved landing pages"],
        "action": "Increase retargeting",
    },
    {
        "label": "Dealer Follow-up",
        "x": 320,
        "y": 60,
        "metric": "SLA 74%",
        "trend": "+6%",
        "drivers": ["NBA adoption", "WhatsApp templates"],
        "action": "Escalate stale leads > 2h",
    },
    {
        "label": "Test Drive",
        "x": 460,
        "y": 60,
        "metric": "72% completion",
        "trend": "+4%",
        "drivers": ["AI scheduler", "SMS reminders"],
        "action": "Add Sunday slots",
    },
    {
        "label": "Booking",
        "x": 600,
        "y": 60,
        "metric": "17.4%",
        "trend": "+2.1",
        "drivers": ["Exchange bonus", "Finance TAT"],
        "action": "Bundle offers",
    },
    {
        "label": "Finance Approval",
        "x": 50,
        "y": 180,
        "metric": "78%",
        "trend": "+3%",
        "drivers": ["Alt-data model", "Faster KYC"],
        "action": "Pre-approve rural",
    },
    {
        "label": "Vehicle Allocation",
        "x": 180,
        "y": 180,
        "metric": "89% utilization",
        "trend": "+5%",
        "drivers": ["Demand model", "Dealer capacity"],
        "action": "Rebalance West",
    },
    {
        "label": "Delivery Delay",
        "x": 320,
        "y": 180,
        "metric": "9.4 d",
        "trend": "-3.1d",
        "drivers": ["Reduced waiting", "Better allocation"],
        "action": "Monitor Q1",
    },
    {
        "label": "Customer Satisfaction",
        "x": 460,
        "y": 180,
        "metric": "NPS 62",
        "trend": "+5",
        "drivers": ["Delivery experience", "Service quality"],
        "action": "Expand digital handover",
    },
    {
        "label": "Service Experience",
        "x": 600,
        "y": 180,
        "metric": "82% CSAT",
        "trend": "+3%",
        "drivers": ["Bay utilization", "AR technician guide"],
        "action": "Roll out to 40 more dealers",
    },
    {
        "label": "Warranty Claims",
        "x": 180,
        "y": 300,
        "metric": "Batch B-2214 flagged",
        "trend": "spike",
        "drivers": ["Component supplier variance"],
        "action": "Quarantine batch",
    },
    {
        "label": "Repeat Purchase",
        "x": 460,
        "y": 300,
        "metric": "24%",
        "trend": "+2%",
        "drivers": ["Loyalty program", "Cross-sell"],
        "action": "Bundle insurance renewal",
    },
]

CAUSAL_EDGES = [
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

MOBILITY_KPIS = [
    {"label": "Lead → booking conversion", "value": "17.4%", "trend": "+2.1 pts"},
    {"label": "Test drive completion", "value": "72%", "trend": "+4%"},
    {"label": "Cancellation risk", "value": "6.8%", "trend": "-1.2 pts"},
    {"label": "Delivery delay", "value": "9.4 d", "trend": "-3.1 d"},
    {"label": "Warranty risk", "value": "Low", "trend": "stable"},
    {"label": "Finance approval rate", "value": "78%", "trend": "+3%"},
    {"label": "Dealer follow-up leakage", "value": "12%", "trend": "-4%"},
]

MOBILITY_QA = [
    {
        "question": "Why did bookings drop in Pune?",
        "answer": "Bookings dropped due to follow-up leakage at 2 Pune dealers (47%), competitor promo (28%), finance TAT (15%). Recommend: exchange bonus + follow-up SLA.",  # noqa: E501
    },
    {
        "question": "What is causing delivery delay in West Zone?",
        "answer": "West Zone waiting is elevated by uneven allocation between Pune/Nashik vs Nagpur (63% of delay). Reallocate 120 units.",  # noqa: E501
    },
    {
        "question": "Which factor has highest impact on cancellation?",
        "answer": "Finance approval TAT (>4 days) explains 41% of cancellations. Pre-approval for low-risk rural cuts it by 22%.",  # noqa: E501
    },
    {
        "question": "How can we improve finance-assisted conversions?",
        "answer": "Pair thin-file credit twin with dealer NBA. Expected +6.4% conversion, -2.1% NPA risk.",
    },
]

DMRV_QA = [
    {
        "question": "Estimate carbon credits for this batch.",
        "answer": "Estimated 214 tCO2e from batch RVSF-Nagpur-Q3, of which 182 are verification-ready.",
    },
    {
        "question": "Which fields are incomplete?",
        "answer": "Missing: origin geo-tag, weight tickets for 12 vehicles, technician attestation for 4 units.",
    },
    {
        "question": "Is this verification-ready?",
        "answer": "78% ready — after adding origin geo-tags, verification confidence rises to 92%.",
    },
    {
        "question": "Generate audit summary.",
        "answer": "Audit summary generated. 5 batches, 214 tCO2e, 91% traceable, 3 pending human reviews.",
    },
]

SUGGESTED_PROMPTS = [
    "Why did bookings drop in Pune last week?",
    "Which dealers have the highest revenue leakage?",
    "Which finance customers are most likely to roll forward?",
    "Which logistics routes are likely to breach SLA?",
    "Which circularity credits should be repriced?",
    "What is the highest ROI AI use case for Mahindra to start with?",
    "Show me the top causal drivers of warranty claims.",
    "Generate a board summary of AI impact.",
]

# Signal tiles, grouped by UI panel (``warehouse_signals`` table).
WAREHOUSE_SIGNALS = [
    {"panel": "warehouse", "label": "Dock congestion", "value": "62%", "tone": "warning"},
    {"panel": "warehouse", "label": "Picking delay", "value": "9 min", "tone": "warning"},
    {"panel": "warehouse", "label": "Inventory imbalance", "value": "-14%", "tone": "danger"},
    {"panel": "warehouse", "label": "Vehicle availability", "value": "78%", "tone": "success"},
    {"panel": "warehouse", "label": "Load utilization", "value": "84%", "tone": "success"},
    {"panel": "collections_metrics", "label": "Accounts at risk", "value": "12,842", "tone": "default"},
    {"panel": "collections_metrics", "label": "Predicted roll-forward", "value": "3,214", "tone": "default"},
    {"panel": "collections_metrics", "label": "Recovery opportunity", "value": "₹42 Cr", "tone": "default"},
    {"panel": "collections_metrics", "label": "Field visit optimization", "value": "-28% cost", "tone": "default"},
    {"panel": "collections_metrics", "label": "Compliance alerts", "value": "6 flagged", "tone": "default"},
    {"panel": "rvsf", "label": "Job-card delay prediction", "value": "2.4 hrs", "tone": "warning"},
    {"panel": "rvsf", "label": "Throughput", "value": "141 vehicles / day", "tone": "success"},
    {"panel": "rvsf", "label": "Bottleneck", "value": "De-pollution bay", "tone": "danger"},
    {"panel": "rvsf", "label": "dMRV completeness", "value": "78%", "tone": "warning"},
    {"panel": "rvsf", "label": "Compliance risk", "value": "Low", "tone": "success"},
]

# Sample simulation run — outputs computed with the exact AutoSales formulas
# (implementation_plan.md §4.1) for inputs: West, XUV700, discount 8%,
# bonus ₹30,000, campaign 4, intensity High.
SAMPLE_SIMULATION_RUN = {
    "domain": "auto_sales",
    "inputs": {
        "region": "West",
        "model": "XUV700",
        "discount_pct": 8,
        "bonus": 30000,
        "campaign_spend": 4,
        "intensity": "High",
    },
    "outputs": {
        "uplift_pct": 41,
        "margin_impact_pct": -10,
        "cancellation_pct": 4,
        "revenue_index": 113,
    },
    "confidence": 89,
}
