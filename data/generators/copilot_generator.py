"""Analytics Copilot: suggested prompt chips.

Tables: suggested_prompts.

Prompts are templated over real entities (regions, cities, vehicle models) so
they stay answerable by the same synthetic dataset — the copilot Q&A pool in
mobility_generator is keyed to exactly these themes.
"""

from __future__ import annotations

import random

from common import REGION_CITIES, REGIONS, VEHICLE_MODELS, GenConfig, write_csv

PROMPT_TEMPLATES = [
    "Why did bookings drop in {city} last week?",
    "Which dealers have the highest revenue leakage?",
    "Which finance customers are most likely to roll forward?",
    "Which logistics routes are likely to breach SLA?",
    "Which circularity credits should be repriced?",
    "What is the highest ROI AI use case for Mahindra to start with?",
    "Show me the top causal drivers of warranty claims.",
    "Generate a board summary of AI impact.",
    "How should we rebalance {model} allocation across {region} Zone?",
    "Which {city} dealers need follow-up escalation today?",
    "What is the finance approval trend for thin-file customers?",
    "Estimate carbon credits for the latest RVSF batch.",
    "Which collections cases should go to human review?",
    "Where is delivery delay highest in {region} Zone?",
    "Summarize compliance status for EPR certificates.",
    "What drives repeat purchase in {region} Zone?",
]


def generate(cfg: GenConfig) -> None:
    rng = random.Random(cfg.seed + 14)
    texts: list[str] = []
    for template in PROMPT_TEMPLATES[: cfg.n(cfg.suggested_prompts)]:
        text = template.format(
            city=rng.choice(REGION_CITIES[rng.choice(REGIONS)]),
            region=rng.choice(REGIONS),
            model=rng.choice(VEHICLE_MODELS),
        )
        if text not in texts:
            texts.append(text)
    write_csv(
        "suggested_prompts",
        [{"text": t, "sort_order": i} for i, t in enumerate(texts)],
    )


if __name__ == "__main__":
    generate(GenConfig())
