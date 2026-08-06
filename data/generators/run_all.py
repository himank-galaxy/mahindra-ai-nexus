"""Orchestrator: run every generator and export all CSVs to data/synthetic/.

Usage (from the repo root, backend venv):
    python data/generators/run_all.py             # default scale (1.0)
    python data/generators/run_all.py --scale 2.5 # 2.5x record counts

Determinism: all generators seed from common.GENERATOR_SEED, so repeated
runs produce byte-identical CSVs (only --scale changes the output).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Allow `python data/generators/run_all.py` from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import GENERATOR_SEED, SYNTHETIC_DIR, GenConfig  # noqa: E402

import reference_generator  # noqa: E402
import dealer_generator  # noqa: E402
import customer_generator  # noqa: E402
import finance_generator  # noqa: E402
import collections_generator  # noqa: E402
import warehouse_generator  # noqa: E402
import shipment_generator  # noqa: E402
import circularity_generator  # noqa: E402
import trust_generator  # noqa: E402
import agent_generator  # noqa: E402
import mobility_generator  # noqa: E402
import overview_generator  # noqa: E402
import catalogue_generator  # noqa: E402
import copilot_generator  # noqa: E402
import simulation_generator  # noqa: E402
import warranty_generator  # noqa: E402  (future dataset)
import notification_generator  # noqa: E402  (future dataset)

# Order = dependency order (parents before children), kept stable for reruns.
GENERATORS = [
    ("Reference & master data", reference_generator),
    ("Dealer funnel", dealer_generator),
    ("Financial Twin (customers)", customer_generator),
    ("Finance products", finance_generator),
    ("Collections", collections_generator),
    ("Warehouse signals", warehouse_generator),
    ("Logistics routes", shipment_generator),
    ("Circularity credits", circularity_generator),
    ("Trust & compliance", trust_generator),
    ("AI agents & XR", agent_generator),
    ("Mobility causal twin", mobility_generator),
    ("Executive overview", overview_generator),
    ("Solution catalogue & PoC", catalogue_generator),
    ("Copilot prompts", copilot_generator),
    ("Simulation runs", simulation_generator),
    ("Warranty claims (future)", warranty_generator),
    ("Notifications (future)", notification_generator),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate all synthetic CSVs")
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Multiplier applied to every record count (default: 1.0)",
    )
    args = parser.parse_args()
    if args.scale <= 0:
        parser.error("--scale must be > 0")

    cfg = GenConfig(scale=args.scale)
    started = time.perf_counter()
    print(f"Synthetic generation | seed={GENERATOR_SEED} scale={cfg.scale}")
    print(f"Output: {SYNTHETIC_DIR}\n")
    for title, module in GENERATORS:
        print(f"[{title}]")
        module.generate(cfg)
        print()
    print(f"Done in {time.perf_counter() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
