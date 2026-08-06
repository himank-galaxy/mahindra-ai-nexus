"""Warehouse / inventory signal tiles for three UI panels.

Tables: warehouse_signals (panel enum: warehouse | collections_metrics | rvsf).

This is the project's "inventory/warehouse" dataset: one table scoped by the
``panel`` column serves the Logistics warehouse grid, the Collections metrics
strip and the RVSF (circularity) tiles.
"""

from __future__ import annotations

import random

from common import GenConfig, write_csv

PANEL_TEMPLATES = {
    "warehouse": [
        ("Dock congestion", "{v}%", (40, 90), "warning"),
        ("Picking delay", "{v} min", (4, 25), "warning"),
        ("Inventory imbalance", "{v}%", (-30, -5), "danger"),
        ("Vehicle availability", "{v}%", (60, 95), "success"),
        ("Load utilization", "{v}%", (65, 95), "success"),
        ("Stock accuracy", "{v}%", (90, 99), "success"),
        ("Inbound backlog", "{v} units", (10, 240), "warning"),
    ],
    "collections_metrics": [
        ("Accounts at risk", "{v}", (8000, 20000), "default"),
        ("Predicted roll-forward", "{v}", (1500, 6000), "default"),
        ("Recovery opportunity", "₹{v} Cr", (20, 80), "default"),
        ("Field visit optimization", "-{v}% cost", (15, 40), "default"),
        ("Compliance alerts", "{v} flagged", (2, 14), "default"),
        ("Promise-to-pay keep rate", "{v}%", (55, 85), "default"),
    ],
    "rvsf": [
        ("Job-card delay prediction", "{v} hrs", (1, 6), "warning"),
        ("Throughput", "{v} vehicles / day", (90, 180), "success"),
        ("Bottleneck", "De-pollution bay", (0, 0), "danger"),
        ("dMRV completeness", "{v}%", (60, 90), "warning"),
        ("Compliance risk", "Low", (0, 0), "success"),
        ("Parts recovery rate", "{v}%", (55, 88), "success"),
    ],
}


def generate(cfg: GenConfig) -> None:
    rng = random.Random(cfg.seed + 6)

    rows = []
    order = 0
    for panel, templates in PANEL_TEMPLATES.items():
        for label, fmt, (lo, hi), tone in templates[: cfg.n(cfg.signals_per_panel)]:
            value = fmt.format(v=f"{rng.randint(lo, hi):,}") if lo != hi else fmt
            rows.append({"panel": panel, "label": label, "value": value, "tone": tone, "sort_order": order})
            order += 1

    write_csv("warehouse_signals", rows)


if __name__ == "__main__":
    generate(GenConfig())
