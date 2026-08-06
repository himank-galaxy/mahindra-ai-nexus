"""Export every seed dataset from backend/app/database/seed_data.py to Parquet.

Read-only with respect to seed_data.py — this script only imports it and writes
one ``.parquet`` file per collection into this folder (Mahindra AI Nexus/database/).

Usage (from anywhere):
    backend\\.venv\\Scripts\\python.exe database\\export_seed_to_parquet.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / "backend"
sys.path.insert(0, str(BACKEND))

import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from app.database import seed_data  # noqa: E402


def write_table(name: str, table: pa.Table) -> None:
    out = HERE / f"{name}.parquet"
    pq.write_table(table, out, compression="snappy")
    print(f"  {name:<32} {table.num_rows:>4} rows  ->  {out.name}")


def from_records(name: str, records: list[dict]) -> None:
    write_table(name, pa.Table.from_pylist(records))


def main() -> None:
    # --- dict-of-records collections -----------------------------------
    from_records("kpis", seed_data.KPIS)
    from_records("recommendations", seed_data.RECOMMENDATIONS)
    from_records("solution_buckets", seed_data.SOLUTION_BUCKETS)
    from_records("dealers", seed_data.DEALERS)
    from_records("dealer_leads", seed_data.DEALER_LEADS)
    from_records("finance_products", seed_data.FINANCE_PRODUCTS)
    from_records("customer_twins", seed_data.CUSTOMER_TWINS)
    from_records("collections_agents", seed_data.COLLECTIONS_AGENTS)
    from_records("collections_cases", seed_data.COLLECTIONS_CASES)
    from_records("logistics_routes", seed_data.LOGISTICS_ROUTES)
    from_records("carbon_credits", seed_data.CARBON_CREDITS)
    from_records("trust_decisions", seed_data.TRUST_DECISIONS)
    from_records("compliance_rules", seed_data.COMPLIANCE_RULES)
    from_records("ai_agents", seed_data.AI_AGENTS)
    from_records("xr_experiences", seed_data.XR_EXPERIENCES)
    from_records("causal_nodes", seed_data.CAUSAL_NODES)
    from_records("mobility_kpis", seed_data.MOBILITY_KPIS)
    from_records("mobility_qa", seed_data.MOBILITY_QA)
    from_records("dmrv_qa", seed_data.DMRV_QA)
    from_records("warehouse_signals", seed_data.WAREHOUSE_SIGNALS)

    # --- plain string lists -> single 'value' column --------------------
    write_table("regions", pa.table({"value": seed_data.REGIONS}))
    write_table("vehicle_models", pa.table({"value": seed_data.VEHICLE_MODELS}))
    write_table("solution_tags", pa.table({"value": seed_data.SOLUTION_TAGS}))
    write_table("suggested_prompts", pa.table({"value": seed_data.SUGGESTED_PROMPTS}))

    # --- tuple collections -> named columns -----------------------------
    write_table(
        "causal_edges",
        pa.table(
            {
                "source": [s for s, _ in seed_data.CAUSAL_EDGES],
                "target": [t for _, t in seed_data.CAUSAL_EDGES],
            }
        ),
    )
    write_table(
        "trust_lineage_static_steps",
        pa.table(
            {
                "step": [s for s, _, _ in seed_data.TRUST_LINEAGE_STATIC_STEPS],
                "title": [t for _, t, _ in seed_data.TRUST_LINEAGE_STATIC_STEPS],
                "detail": [d for _, _, d in seed_data.TRUST_LINEAGE_STATIC_STEPS],
            }
        ),
    )

    # --- single-record dict ---------------------------------------------
    from_records("sample_simulation_run", [seed_data.SAMPLE_SIMULATION_RUN])

    total = sum(
        pq.read_metadata(HERE / f.name).num_rows
        for f in HERE.glob("*.parquet")
    )
    print(f"\nDone. {len(list(HERE.glob('*.parquet')))} parquet files, {total} rows total.")


if __name__ == "__main__":
    main()
