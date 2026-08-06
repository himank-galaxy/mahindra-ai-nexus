"""AI Factory: registered agents + XR experience catalogue.

Tables: ai_agents, xr_experiences.
"""

from __future__ import annotations

import random

from common import GenConfig, jdump, write_csv

AGENTS = [
    ("Data Agent", "Ingest & normalize signals", ["Auto", "Finance"]),
    ("Prediction Agent", "Forecast outcomes", ["Auto", "Logistics"]),
    ("Causal Graph Agent", "Explain drivers", ["Auto"]),
    ("Simulation Agent", "What-if scenarios", ["Auto", "Finance"]),
    ("Code Analytics Agent", "NL→SQL/Python", ["All"]),
    ("Compliance Agent", "Guardrails & policy", ["Finance"]),
    ("Action Agent", "Execute approved actions", ["Auto"]),
    ("Human Review Agent", "Route to human", ["All"]),
    ("Learning Agent", "Feedback learning", ["All"]),
    ("Memory Agent", "Long-term memory", ["All"]),
    ("Anomaly Agent", "Detect signal spikes", ["Logistics", "Circularity"]),
    ("Pricing Agent", "Dynamic credit pricing", ["Circularity"]),
]
ACTIVITIES = [
    "Refreshed dealer feed {n}m ago",
    "Forecast bookings {city}",
    "Explained cancellation drivers",
    "Tested exchange bonus scenario",
    "Generated warranty query",
    "Blocked {n} risky offers",
    "Sent WhatsApp to {n} leads",
    "{n} items pending review",
    "Updated propensity model",
    "Stored {n} decisions",
]
XR = [
    ("showroom", "AI Virtual Showroom", "Immersive vehicle exploration", "Generative sales assistant + config"),
    ("config", "3D Vehicle Configurator", "Personalized configurations", "Real-time AI recommendations"),
    ("repair", "AR Technician Repair Guide", "Step-by-step service", "Component-aware AR overlays"),
    ("training", "VR Dealer Sales Training", "Immersive skill building", "AI feedback on pitch & objections"),
    ("inspect", "AR Pre-Delivery Inspection", "Guided quality checks", "Defect auto-capture"),
    ("support", "VR Customer Handover", "Feature walkthrough", "Personalized onboarding"),
]
IMPACTS = ["+18% online-to-visit conversion", "+12% variant upsell", "-24% repair time", "+22% training ROI", "-31% inspection time", "+15% NPS"]


def generate(cfg: GenConfig) -> None:
    rng = random.Random(cfg.seed + 10)

    agents = [
        {
            "name": name,
            "role": role,
            "status": rng.choice(["active", "active", "active", "reviewing", "recommended"]),
            "last_activity": rng.choice(ACTIVITIES).format(n=rng.randint(2, 230), city=rng.choice(["Pune", "Delhi", "Chennai"])),
            "use_areas": jdump(areas),
            "sort_order": i,
        }
        for i, (name, role, areas) in enumerate(AGENTS[: cfg.n(cfg.ai_agents)])
    ]
    write_csv("ai_agents", agents)

    xr = [
        {"code": code, "title": title, "use_case": use_case, "feature": feature, "impact": IMPACTS[i % len(IMPACTS)], "sort_order": i}
        for i, (code, title, use_case, feature) in enumerate(XR[: cfg.n(cfg.xr_experiences)])
    ]
    write_csv("xr_experiences", xr)


if __name__ == "__main__":
    generate(GenConfig())
