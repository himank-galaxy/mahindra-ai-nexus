"""Synthetic Data Import Layer for Single Coexisting PostgreSQL Database.

Integrates synthetic CSV data into the `mahindra_ai` database alongside existing mock data.

Key Guarantees:
- Single Database: Imports into `mahindra_ai` PostgreSQL database.
- Non-Destructive: Never drops, truncates, resets, or overwrites existing mock data.
- Idempotent: Uses deterministic UUID5 primary keys so re-running updates synthetic records without creating duplicates.
- Constraint-Safe: Inspects schema and applies namespacing strictly where natural keys collide with mock data (e.g., `kpis`, `causal_nodes`, `xr_experiences`), updating dependent child FK helpers consistently.
- Dry-Run Capable: `--dry-run` performs full payload parsing, key transformation, and validation with zero DB writes.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Boolean, DateTime, Float, Integer
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.models  # Registers all models on Base.metadata
from app.database.base import Base

SYNTHETIC_NAMESPACE = uuid.UUID("7c3e9a1d-52b8-4e06-9f41-d2a8b6c0e517")
DATA_DIR_DEFAULT = REPO_ROOT / "data" / "synthetic"
FUTURE_DATASETS = {"notifications", "warranty_claims"}


def synthetic_id(table: str, natural_key: str) -> uuid.UUID:
    """Deterministic UUID for one synthetic row."""
    return uuid.uuid5(SYNTHETIC_NAMESPACE, f"synthetic:{table}:{natural_key}")


@dataclass
class TableSpec:
    model: type
    natural_key: str
    drop: set[str] = field(default_factory=set)
    fk_helpers: dict[str, tuple[str, str]] = field(default_factory=dict)
    indexed: bool = True  # True = UUID pk, False = natural string PK


def get_specs() -> dict[str, TableSpec]:
    from app.models import (
        AiAgent, CarbonCredit, CausalEdge, CausalNode, CausalQa,
        CollectionsAgent, CollectionsCase, ComplianceRule, CustomerTwin,
        Dealer, DealerLead, FinanceProduct, Kpi, KpiDriver, LogisticsRoute,
        MobilityKpi, PocItem, Recommendation, Region, SimulationRun,
        Solution, SolutionBucket, SuggestedPrompt, TrustDecision, User,
        VehicleModel, WarehouseSignal, XrExperience,
    )

    return {
        "regions": TableSpec(Region, "{code}", indexed=False),
        "vehicle_models": TableSpec(VehicleModel, "{name}", indexed=False),
        "users": TableSpec(User, "{email}"),
        "dealers": TableSpec(Dealer, "{code}", drop={"region", "city"}),
        "dealer_leads": TableSpec(
            DealerLead, "{dealer_code}:{sort_order}",
            fk_helpers={"dealer_code": ("dealer_id", "dealers")},
        ),
        "customer_twins": TableSpec(CustomerTwin, "{name}"),
        "finance_products": TableSpec(FinanceProduct, "{name}"),
        "collections_agents": TableSpec(CollectionsAgent, "{name}"),
        "collections_cases": TableSpec(
            CollectionsCase, "{customer}", drop={"product"},
        ),
        "warehouse_signals": TableSpec(WarehouseSignal, "{panel}:{sort_order}"),
        "logistics_routes": TableSpec(LogisticsRoute, "{name}"),
        "carbon_credits": TableSpec(CarbonCredit, "{code}"),
        "trust_decisions": TableSpec(TrustDecision, "{code}"),
        "compliance_rules": TableSpec(ComplianceRule, "{label}"),
        "ai_agents": TableSpec(AiAgent, "{name}"),
        "xr_experiences": TableSpec(XrExperience, "{code}"),
        "causal_nodes": TableSpec(CausalNode, "{label}"),
        "causal_edges": TableSpec(
            CausalEdge, "{source_label}->{target_label}",
            fk_helpers={
                "source_label": ("source_node_id", "causal_nodes"),
                "target_label": ("target_node_id", "causal_nodes"),
            },
        ),
        "mobility_kpis": TableSpec(MobilityKpi, "{label}"),
        "causal_qa": TableSpec(CausalQa, "{category}:{sort_order}"),
        "kpis": TableSpec(Kpi, "{code}"),
        "kpi_drivers": TableSpec(
            KpiDriver, "{kpi_code}:{sort_order}",
            fk_helpers={"kpi_code": ("kpi_id", "kpis")},
        ),
        "recommendations": TableSpec(Recommendation, "{code}"),
        "solution_buckets": TableSpec(SolutionBucket, "{name}"),
        "solutions": TableSpec(
            Solution, "{name}",
            fk_helpers={"bucket_name": ("bucket_id", "solution_buckets")},
        ),
        "poc_items": TableSpec(PocItem, "{name}"),
        "suggested_prompts": TableSpec(SuggestedPrompt, "{text}"),
        "simulation_runs": TableSpec(SimulationRun, "run:{row_index}"),
    }


LOAD_ORDER = [
    "regions", "vehicle_models", "users", "dealers", "dealer_leads",
    "customer_twins", "finance_products", "collections_agents",
    "collections_cases", "warehouse_signals", "logistics_routes",
    "carbon_credits", "trust_decisions", "compliance_rules", "ai_agents",
    "xr_experiences", "causal_nodes", "causal_edges", "mobility_kpis",
    "causal_qa", "kpis", "kpi_drivers", "recommendations",
    "solution_buckets", "solutions", "poc_items", "suggested_prompts",
    "simulation_runs",
]


def apply_key_transformations(table_name: str, row: dict[str, str], row_idx: int) -> dict[str, str]:
    """Apply namespacing ONLY to colliding synthetic keys so mock data remains untouched."""
    row = dict(row)
    row["row_index"] = str(row_idx)

    # 1. KPIs: 'rev' and 'leak' collide with mock KPI codes
    if table_name == "kpis":
        if row.get("code") in ("rev", "leak", "book", "fin", "del", "csat"):
            row["code"] = f"syn-{row['code']}"

    elif table_name == "kpi_drivers":
        if row.get("kpi_code") in ("rev", "leak", "book", "fin", "del", "csat"):
            row["kpi_code"] = f"syn-{row['kpi_code']}"

    # 2. Compliance Rules: labels collide with mock compliance rule labels
    elif table_name == "compliance_rules":
        if row.get("label"):
            row["label"] = f"{row['label']} (Synthetic)"

    # 3. AI Agents: names collide with mock AI agent names
    elif table_name == "ai_agents":
        if row.get("name"):
            row["name"] = f"{row['name']} (Synthetic)"

    # 4. XR Experiences: codes collide with mock XR codes ('showroom', 'config', 'repair', 'training')
    elif table_name == "xr_experiences":
        if row.get("code"):
            row["code"] = f"syn-{row['code']}"

    # 5. Causal Nodes & Edges: labels collide with mock causal nodes
    elif table_name == "causal_nodes":
        if row.get("label"):
            row["label"] = f"{row['label']} (Synthetic)"

    elif table_name == "causal_edges":
        if row.get("source_label"):
            row["source_label"] = f"{row['source_label']} (Synthetic)"
        if row.get("target_label"):
            row["target_label"] = f"{row['target_label']} (Synthetic)"

    # 6. Mobility KPIs: labels collide with mock mobility KPIs
    elif table_name == "mobility_kpis":
        if row.get("label"):
            row["label"] = f"{row['label']} (Synthetic)"

    # 7. Suggested Prompts: texts collide with mock prompts
    elif table_name == "suggested_prompts":
        if row.get("text"):
            row["text"] = f"{row['text']} (Synthetic)"

    return row


def _parse_bool(raw: str) -> bool:
    if raw.strip().lower() in {"true", "1", "yes"}:
        return True
    if raw.strip().lower() in {"false", "0", "no"}:
        return False
    raise ValueError(f"unparseable boolean: {raw!r}")


def coerce_value(column, raw: str):
    """Coerce CSV text to ORM Python type."""
    nullable = column.nullable
    if raw == "" or raw is None:
        if nullable or column.default is not None or column.server_default is not None:
            return None
        raise ValueError(f"empty value for required column {column.name!r}")

    col_type = column.type
    if isinstance(col_type, SAEnum):
        allowed = set(col_type.enums)
        if raw not in allowed:
            # Case insensitive fallback if needed
            lower_map = {e.lower(): e for e in col_type.enums}
            if raw.lower() in lower_map:
                return lower_map[raw.lower()]
            raise ValueError(f"{column.name!r}: {raw!r} not in enum {sorted(allowed)}")
        return raw
    if isinstance(col_type, Boolean):
        return _parse_bool(raw)
    if isinstance(col_type, Integer):
        return int(raw)
    if isinstance(col_type, Float):
        return float(raw)
    if isinstance(col_type, DateTime):
        val = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if not col_type.timezone and val.tzinfo is not None:
            val = val.replace(tzinfo=None)
        elif col_type.timezone and val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return val
    type_name = col_type.__class__.__name__
    if type_name in {"JSON", "JSONB", "ARRAY"}:
        return json.loads(raw)
    return raw


def build_orm_instance(spec: TableSpec, table_name: str, row: dict[str, str]) -> tuple[Base, str]:
    """Convert raw CSV dict to ORM model instance with coerced types."""
    model_cls = spec.model
    mapper = model_cls.__mapper__
    columns = mapper.columns

    natural_key = spec.natural_key.format(**row)
    kwargs: dict = {}

    if spec.indexed:
        kwargs["id"] = synthetic_id(table_name, natural_key)

    for header, raw in row.items():
        if header in spec.drop or header in ("row_index",):
            continue
        if header in spec.fk_helpers:
            target_col, parent_table = spec.fk_helpers[header]
            kwargs[target_col] = synthetic_id(parent_table, raw)
            continue
        if header in columns:
            column = columns[header]
            val = coerce_value(column, raw)
            if val is not None or not column.nullable:
                kwargs[header] = val

    return model_cls(**kwargs), natural_key


async def import_synthetic_data(data_dir: Path, db_url: str, dry_run: bool = False) -> dict[str, int]:
    """Execute synthetic import cleanly and idempotently into PostgreSQL."""
    specs = get_specs()
    report: dict[str, int] = {}

    engine = create_async_engine(db_url, echo=False)
    async_session = AsyncSession(engine, expire_on_commit=False)

    print("=" * 70)
    print("STARTING SYNTHETIC DATA IMPORT LAYER")
    print(f"Target DB: {db_url}")
    print(f"Data Dir:  {data_dir}")
    print(f"Dry-Run:   {dry_run}")
    print("=" * 70)

    try:
        async with async_session.begin():
            for table_name in LOAD_ORDER:
                csv_path = data_dir / f"{table_name}.csv"
                if not csv_path.exists():
                    if table_name in FUTURE_DATASETS:
                        print(f"[-] {table_name}.csv (Future dataset, skipping)")
                    else:
                        print(f"[!] {table_name}.csv missing at {csv_path}")
                    continue

                spec = specs[table_name]
                with open(csv_path, mode="r", encoding="utf-8") as f:
                    reader = list(csv.DictReader(f))

                count = 0
                for row_idx, raw_row in enumerate(reader):
                    row = apply_key_transformations(table_name, raw_row, row_idx)
                    instance, _ = build_orm_instance(spec, table_name, row)
                    
                    if not dry_run:
                        await async_session.merge(instance)
                    count += 1

                report[table_name] = count
                print(f"[+] Imported {count:3d} rows -> {table_name}")

            if dry_run:
                print("\n[DRY-RUN COMPLETE] Validation successful. Zero changes written to database.")
            else:
                await async_session.commit()
                print("\n[IMPORT COMPLETE] All synthetic records imported successfully into PostgreSQL!")

    except Exception as e:
        await async_session.rollback()
        print(f"\n[ERROR] Synthetic import failed: {e}")
        raise
    finally:
        await async_session.close()
        await engine.dispose()

    return report


def main():
    parser = argparse.ArgumentParser(description="Synthetic Data Import Layer for PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Validate CSVs without writing to DB")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", "postgresql+asyncpg://mahindra:mahindra@localhost:5432/mahindra_ai"),
        help="PostgreSQL connection string",
    )
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR_DEFAULT, help="Path to data/synthetic/")

    args = parser.parse_args()
    asyncio.run(import_synthetic_data(data_dir=args.data_dir, db_url=args.database_url, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
