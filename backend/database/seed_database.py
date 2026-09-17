"""Seed PostgreSQL from the synthetic CSVs in ``data/synthetic/``.

Design guarantees
-----------------
- Schema-locked: every CSV header is validated against the ORM metadata in
  ``app.models`` before a single row is written. Unknown columns, missing
  required columns, bad enum values and malformed JSON all abort the run.
- FK-preserving: child tables carry human-readable helper columns
  (``dealer_code``, ``kpi_code``, ``bucket_name``, ``source_label`` /
  ``target_label``) which are resolved to parent UUIDs. Parent UUIDs are
  deterministic (uuid5 over a dedicated namespace + natural key), so children
  resolve FKs without querying the database.
- Idempotent: rows are upserted with ``session.merge`` keyed on deterministic
  UUIDs — rerunning never duplicates. ``--reset-synthetic`` removes only the
  rows this script created (curated rows are never touched).
- Safe: unique-column collisions with pre-existing NON-synthetic rows abort
  the run BEFORE any write.

Context columns present in the CSVs but not in the schema (dealers.region,
dealers.city, collections_cases.product) are dropped at load time.

Usage (from ``backend/`` with the venv):
    python database/seed_database.py --dry-run
    python database/seed_database.py --database-url "postgresql+asyncpg://user:pw@host:5432/db"
    python database/seed_database.py --reset-synthetic   # wipe synthetic rows first
    python database/seed_database.py --ensure-schema     # create_all on a fresh DB

IMPORTANT: point this at a FRESH or staging database. Never run it against a
database already holding curated UI seed data — the synthetic dataset
intentionally mirrors the same business values and would trip unique keys.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Make the backend package importable regardless of the working directory.
BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import Enum as SAEnum  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy import Boolean, DateTime, Float, Integer  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

import app.models  # noqa: E402,F401  (registers all tables on Base.metadata)
from app.database.base import Base  # noqa: E402

# Dedicated namespace for synthetic rows — MUST differ from the curated
# seed namespace so synthetic UUIDs can never collide with curated ones.
SYNTHETIC_NAMESPACE = uuid.UUID("7c3e9a1d-52b8-4e06-9f41-d2a8b6c0e517")

DATA_DIR_DEFAULT = REPO_ROOT / "data" / "synthetic"

# CSVs generated for future phases — no table exists yet; skip with a notice.
FUTURE_DATASETS = {"notifications", "warranty_claims"}


def synthetic_id(table: str, natural_key: str) -> uuid.UUID:
    """Deterministic UUID for one synthetic row."""
    return uuid.uuid5(SYNTHETIC_NAMESPACE, f"synthetic:{table}:{natural_key}")


@dataclass
class TableSpec:
    """Load contract for one CSV -> table mapping."""

    model: type
    natural_key: str  # format string applied to the CSV row
    drop: set[str] = field(default_factory=set)  # context columns, not in schema
    fk_helpers: dict[str, tuple[str, str]] = field(default_factory=dict)
    # csv column -> (target column, parent table); the helper VALUE is the
    # parent's natural key, so the parent UUID is computed without a query.
    indexed: bool = True  # rows resolved by synthetic UUID (False = natural PK)


def _registry() -> dict[str, TableSpec]:
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


# Parents first; reverse order is used for --reset-synthetic deletes.
LOAD_ORDER = [
    "regions", "vehicle_models", "users", "dealers", "dealer_leads",
    "customer_twins", "finance_products", "collections_agents",
    "collections_cases", "warehouse_signals", "logistics_routes",
    "carbon_credits", "trust_decisions", "compliance_rules", "ai_agents",
    "xr_experiences", "causal_nodes", "causal_edges", "mobility_kpis",
    "causal_qa", "kpis", "kpi_drivers", "recommendations", "solution_buckets",
    "solutions", "poc_items", "suggested_prompts", "simulation_runs",
]


# ---------------------------------------------------------------------------
# Value coercion
# ---------------------------------------------------------------------------

def _parse_bool(raw: str) -> bool:
    if raw.strip().lower() in {"true", "1", "yes"}:
        return True
    if raw.strip().lower() in {"false", "0", "no"}:
        return False
    raise ValueError(f"unparseable boolean: {raw!r}")


def coerce(column, raw: str):
    """Convert a CSV string into the Python type the ORM column expects."""
    nullable = column.nullable
    if raw == "":
        if nullable or column.default is not None or column.server_default is not None:
            return None
        raise ValueError(f"empty value for required column {column.name!r}")

    col_type = column.type
    if isinstance(col_type, SAEnum):
        allowed = set(col_type.enums)
        if raw not in allowed:
            raise ValueError(f"{column.name!r}: {raw!r} not in enum {sorted(allowed)}")
        return raw
    if isinstance(col_type, Boolean):
        return _parse_bool(raw)
    if isinstance(col_type, Integer):
        return int(raw)
    if isinstance(col_type, Float):
        return float(raw)
    if isinstance(col_type, DateTime):
        value = datetime.fromisoformat(raw)
        if not col_type.timezone and value.tzinfo is not None:
            value = value.replace(tzinfo=None)  # naive column, aware input
        elif col_type.timezone and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)  # timestamptz column, naive input
        return value
    # JSON / JSONB columns (incl. JSON-with-variant) and ARRAY string pools
    if col_type.__class__.__name__ in {"JSON", "JSONB"}:
        return json.loads(raw)
    if col_type.__class__.__name__ == "ARRAY":
        return json.loads(raw)
    return raw


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_headers(table_name: str, spec: TableSpec, headers: list[str]) -> None:
    model_cols = {c.name for c in spec.model.__table__.columns}
    allowed = model_cols | spec.drop | set(spec.fk_helpers)
    unknown = [h for h in headers if h not in allowed]
    if unknown:
        raise SystemExit(f"[{table_name}] unknown CSV columns: {unknown}")

    managed = {"id", "created_at", "updated_at", "deleted_at"}
    for col in spec.model.__table__.columns:
        if col.name in managed:
            continue
        optional = col.nullable or col.default is not None or col.server_default is not None
        source = headers if col.name in headers else [
            h for h in headers if spec.fk_helpers.get(h, ("", ""))[0] == col.name
        ]
        if not optional and not source and col.primary_key is False:
            raise SystemExit(f"[{table_name}] required column missing from CSV: {col.name}")


def read_csv(data_dir: Path, table_name: str) -> list[dict]:
    path = data_dir / f"{table_name}.csv"
    if not path.exists():
        raise SystemExit(f"missing CSV: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# Core seeding
# ---------------------------------------------------------------------------

async def unique_collision_check(session: AsyncSession, table_name: str, spec: TableSpec, rows: list[dict]) -> None:
    """Abort if a unique column value already belongs to a non-synthetic row."""
    for col in spec.model.__table__.columns:
        if not col.unique or col.primary_key or col.name == "id":
            continue
        values = [r[col.name] for r in rows if r.get(col.name)]
        if not values:
            continue
        existing = (await session.execute(
            select(col, spec.model.__table__.c.id).where(col.in_(values))
        )).all()
        for value, existing_id in existing:
            natural_rows = [r for r in rows if r.get(col.name) == value]
            expected = {
                synthetic_id(table_name, spec.natural_key.format(row_index=i, **r))
                for i, r in enumerate(natural_rows) if spec.indexed
            }
            if existing_id not in expected and spec.indexed:
                raise SystemExit(
                    f"[{table_name}] unique column {col.name!r} value {value!r} "
                    f"already exists (id={existing_id}) outside the synthetic set. "
                    f"Seed a fresh database instead."
                )


async def seed_table(session: AsyncSession, table_name: str, spec: TableSpec, rows: list[dict]) -> tuple[int, int]:
    inserted = updated = 0
    for index, row in enumerate(rows):
        key = spec.natural_key.format(row_index=index, **row)
        data: dict = {}
        for header, raw in row.items():
            if header in spec.drop:
                continue
            if header in spec.fk_helpers:
                target_col, parent_table = spec.fk_helpers[header]
                data[target_col] = synthetic_id(parent_table, raw)
                continue
            column = spec.model.__table__.columns[header]
            data[header] = coerce(column, raw)

        if spec.indexed:
            row_id = synthetic_id(table_name, key)
            existing = await session.get(spec.model, row_id)
        else:  # reference tables with natural primary keys
            row_id = None
            existing = await session.get(spec.model, tuple(data[c.name] for c in spec.model.__table__.primary_key))

        if existing is None:
            instance = spec.model(**({"id": row_id} if row_id else {}), **data)
            session.add(instance)
            inserted += 1
        else:
            for attr, value in data.items():
                setattr(existing, attr, value)
            updated += 1
    return inserted, updated


async def reset_synthetic(session: AsyncSession, data_dir: Path) -> None:
    """Delete only rows whose deterministic UUIDs match the current CSVs."""
    for table_name in reversed(LOAD_ORDER):
        spec = _registry()[table_name]
        if not spec.indexed:
            continue  # shared lookups (regions, vehicle_models) stay untouched
        rows = read_csv(data_dir, table_name)
        ids = [
            synthetic_id(table_name, spec.natural_key.format(row_index=i, **r))
            for i, r in enumerate(rows)
        ]
        result = await session.execute(delete(spec.model.__table__).where(spec.model.__table__.c.id.in_(ids)))
        if result.rowcount:
            print(f"  reset {table_name:<22} {result.rowcount:>4} rows removed")


async def run(args: argparse.Namespace) -> int:
    registry = _registry()
    data_dir = Path(args.data_dir)

    # -- Load + validate every CSV up front (fail fast, no partial writes) --
    payloads: dict[str, list[dict]] = {}
    for table_name in LOAD_ORDER:
        rows = read_csv(data_dir, table_name)
        with (data_dir / f"{table_name}.csv").open(newline="", encoding="utf-8") as fh:
            headers = next(csv.reader(fh))
        validate_headers(table_name, registry[table_name], headers)
        payloads[table_name] = rows

    skipped = [name for name in FUTURE_DATASETS if (data_dir / f"{name}.csv").exists()]

    engine = create_async_engine(args.database_url, echo=False)
    async with engine.begin() as conn:
        if args.ensure_schema:
            await conn.run_sync(Base.metadata.create_all)
            print("schema ensured (create_all)\n")

    async with AsyncSession(engine) as session:
        if args.reset_synthetic:
            print("resetting synthetic rows...")
            await reset_synthetic(session, data_dir)
            await session.commit()
            print()

        if not args.dry_run:
            for table_name in LOAD_ORDER:
                await unique_collision_check(session, table_name, registry[table_name], payloads[table_name])

        total_in = total_up = 0
        for table_name in LOAD_ORDER:
            rows = payloads[table_name]
            if args.dry_run:
                # coerce every value so dry-run catches type/enum errors too
                for index, row in enumerate(rows):
                    spec = registry[table_name]
                    for header, raw in row.items():
                        if header in spec.drop or header in spec.fk_helpers:
                            continue
                        coerce(spec.model.__table__.columns[header], raw)
                    spec.natural_key.format(row_index=index, **row)
                print(f"  dry-run {table_name:<22} {len(rows):>4} rows validated")
                continue
            ins, upd = await seed_table(session, table_name, registry[table_name], rows)
            total_in += ins
            total_up += upd
            print(f"  {table_name:<28} {ins:>4} inserted, {upd:>4} updated")
        if not args.dry_run:
            await session.commit()

    await engine.dispose()
    print()
    if skipped:
        print(f"skipped future datasets (no table yet): {', '.join(sorted(skipped))}")
    if args.dry_run:
        print("dry-run complete — no rows were written.")
    else:
        print(f"committed: {total_in} inserted, {total_up} updated across {len(LOAD_ORDER)} tables.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed PostgreSQL from data/synthetic CSVs")
    parser.add_argument("--database-url", default=None, help="Async SQLAlchemy URL (default: backend settings)")
    parser.add_argument("--data-dir", default=str(DATA_DIR_DEFAULT), help="Directory containing the CSVs")
    parser.add_argument("--dry-run", action="store_true", help="Validate CSVs without writing")
    parser.add_argument("--reset-synthetic", action="store_true", help="Delete synthetic rows first")
    parser.add_argument("--ensure-schema", action="store_true", help="Run create_all for a fresh database")
    args = parser.parse_args()

    if args.database_url is None:
        from app.core.config import get_settings
        args.database_url = get_settings().database_url
    print(f"target: {args.database_url.split('@')[-1]}\n")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
