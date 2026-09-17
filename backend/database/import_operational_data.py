"""Idempotently import normalized synthetic records into PostgreSQL.

This importer is intentionally isolated from ``seed_database.py``.  The
latter imports legacy presentation/card tables, while this module imports only
event-level operational data introduced by Alembic revision 0002.  It never
deletes, truncates, or mutates legacy rows.

Usage (from ``backend/``):
    python database/import_operational_data.py --dry-run
    python database/import_operational_data.py
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

import app.models  # noqa: E402,F401  # Registers complete ORM metadata.
from app.models.operations import (  # noqa: E402
    Booking, BusinessCustomer, BusinessDealer, BusinessLead, Cancellation,
    CausalTimeSeries, DmrvRecord, ElvAssessment, FinanceApplication,
    RvsfJobCard, Shipment, TestDrive, VehicleAllocation,
)

DATA_DIR_DEFAULT = REPO_ROOT / "data" / "synthetic"
OPERATIONAL_NAMESPACE = uuid.UUID("c0992170-6a11-4a5d-8b89-b147a914cf17")


def operational_id(table: str, natural_key: str) -> uuid.UUID:
    """Stable UUID5 so an identical import updates, never duplicates."""
    return uuid.uuid5(OPERATIONAL_NAMESPACE, f"mahindra-operations:{table}:{natural_key}")


@dataclass(frozen=True)
class TableSpec:
    model: type
    natural_key: str
    fk_helpers: dict[str, tuple[str, str]] = field(default_factory=dict)


def registry() -> dict[str, TableSpec]:
    return {
        "business_dealers": TableSpec(BusinessDealer, "{code}"),
        "business_customers": TableSpec(BusinessCustomer, "{customer_code}"),
        "business_leads": TableSpec(BusinessLead, "{lead_code}", {"dealer_code": ("dealer_id", "business_dealers")}),
        "finance_applications": TableSpec(FinanceApplication, "{application_code}", {"customer_code": ("customer_id", "business_customers"), "dealer_code": ("dealer_id", "business_dealers")}),
        "bookings": TableSpec(Booking, "{booking_code}", {"dealer_code": ("dealer_id", "business_dealers"), "lead_code": ("lead_id", "business_leads"), "customer_code": ("customer_id", "business_customers")}),
        "test_drives": TableSpec(TestDrive, "{test_drive_code}", {"lead_code": ("lead_id", "business_leads"), "dealer_code": ("dealer_id", "business_dealers")}),
        "cancellations": TableSpec(Cancellation, "{cancellation_code}", {"booking_code": ("booking_id", "bookings")}),
        "vehicle_allocations": TableSpec(VehicleAllocation, "{allocation_code}", {"dealer_code": ("dealer_id", "business_dealers")}),
        "shipments": TableSpec(Shipment, "{shipment_code}"),
        "elv_assessments": TableSpec(ElvAssessment, "{assessment_code}"),
        "rvsf_job_cards": TableSpec(RvsfJobCard, "{job_card_code}"),
        "dmrv_records": TableSpec(DmrvRecord, "{dmrv_code}"),
        "causal_timeseries": TableSpec(CausalTimeSeries, "{observed_on}:{dealer_code}:{vehicle_model}", {"dealer_code": ("dealer_id", "business_dealers")}),
    }


LOAD_ORDER = [
    "business_dealers", "business_customers", "business_leads", "finance_applications",
    "bookings", "test_drives", "cancellations", "vehicle_allocations", "shipments",
    "elv_assessments", "rvsf_job_cards", "dmrv_records", "causal_timeseries",
]


def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise SystemExit(f"missing required operational CSV: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def _coerce(column, raw: str):
    if raw == "":
        if column.nullable or column.default is not None or column.server_default is not None:
            return None
        raise ValueError(f"{column.table.name}.{column.name} is required")
    col_type = column.type
    if isinstance(col_type, Boolean):
        if raw.lower() not in {"true", "false"}:
            raise ValueError(f"{column.name}: expected true/false, got {raw!r}")
        return raw.lower() == "true"
    if isinstance(col_type, Integer):
        return int(raw)
    if isinstance(col_type, Float):
        return float(raw)
    if isinstance(col_type, Numeric):
        return Decimal(raw)
    if isinstance(col_type, Date):
        return date.fromisoformat(raw)
    if isinstance(col_type, DateTime):
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if col_type.__class__.__name__ in {"JSON", "JSONB"}:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError(f"{column.name}: expected JSON list")
        return parsed
    return raw


def _natural(spec: TableSpec, row: dict[str, str]) -> str:
    return spec.natural_key.format(**row)


def validate(table_name: str, spec: TableSpec, headers: list[str], rows: list[dict[str, str]]) -> None:
    columns = {column.name: column for column in spec.model.__table__.columns}
    allowed = set(columns) | set(spec.fk_helpers)
    unknown = set(headers) - allowed
    if unknown:
        raise SystemExit(f"{table_name}: unknown CSV columns {sorted(unknown)}")
    for column in spec.model.__table__.columns:
        if column.name in {"id", "created_at", "updated_at"}:
            continue
        supplied = column.name in headers or any(target == column.name for target, _ in spec.fk_helpers.values())
        optional = column.nullable or column.default is not None or column.server_default is not None
        if not supplied and not optional:
            raise SystemExit(f"{table_name}: required column {column.name!r} is absent")
    for row in rows:
        _natural(spec, row)
        for header, raw in row.items():
            if header not in spec.fk_helpers:
                _coerce(columns[header], raw)


async def check_unique_collisions(session: AsyncSession, table_name: str, spec: TableSpec, rows: list[dict[str, str]]) -> None:
    """Refuse an accidental overwrite of a non-operational row on a unique key."""
    table = spec.model.__table__
    for column in table.columns:
        if not column.unique or column.name == "id":
            continue
        values = {row.get(column.name) for row in rows if row.get(column.name)}
        if not values:
            continue
        matches = (await session.execute(select(column, table.c.id).where(column.in_(values)))).all()
        expected = {operational_id(table_name, _natural(spec, row)) for row in rows}
        collisions = [(value, existing_id) for value, existing_id in matches if existing_id not in expected]
        if collisions:
            value, existing_id = collisions[0]
            raise SystemExit(
                f"{table_name}: unique key {column.name}={value!r} belongs to an unrelated row ({existing_id}); import stopped."
            )


async def upsert_table(session: AsyncSession, table_name: str, spec: TableSpec, rows: list[dict[str, str]]) -> tuple[int, int]:
    inserted = updated = 0
    columns = spec.model.__table__.columns
    for row in rows:
        data: dict[str, object] = {}
        for header, raw in row.items():
            if header in spec.fk_helpers:
                target_column, parent_table = spec.fk_helpers[header]
                parent_spec = registry()[parent_table]
                # Parent natural keys are their respective stable business codes.
                parent_key = raw
                data[target_column] = operational_id(parent_table, parent_key)
            else:
                data[header] = _coerce(columns[header], raw)
        row_id = operational_id(table_name, _natural(spec, row))
        existing = await session.get(spec.model, row_id)
        if existing is None:
            session.add(spec.model(id=row_id, **data))
            inserted += 1
        else:
            for name, value in data.items():
                setattr(existing, name, value)
            updated += 1
    return inserted, updated


async def run(args: argparse.Namespace) -> int:
    specs = registry()
    data_dir = Path(args.data_dir)
    payloads: dict[str, list[dict[str, str]]] = {}
    for table_name in LOAD_ORDER:
        headers, rows = _read(data_dir / f"{table_name}.csv")
        validate(table_name, specs[table_name], headers, rows)
        payloads[table_name] = rows

    if args.dry_run:
        for table_name in LOAD_ORDER:
            print(f"  dry-run {table_name:<24} {len(payloads[table_name]):>5} rows validated")
        print("dry-run complete — nothing was written.")
        return 0

    engine = create_async_engine(args.database_url, echo=False)
    try:
        async with AsyncSession(engine) as session:
            for table_name in LOAD_ORDER:
                await check_unique_collisions(session, table_name, specs[table_name], payloads[table_name])
            inserted = updated = 0
            for table_name in LOAD_ORDER:
                created, changed = await upsert_table(session, table_name, specs[table_name], payloads[table_name])
                inserted += created
                updated += changed
                print(f"  {table_name:<24} {created:>5} inserted, {changed:>5} updated")
            await session.commit()
        print(f"committed: {inserted} inserted, {updated} updated; legacy tables were not changed.")
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Import normalized Mahindra synthetic business data")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--data-dir", default=str(DATA_DIR_DEFAULT))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.database_url is None:
        from app.core.config import get_settings
        args.database_url = get_settings().database_url
    safe_target = args.database_url.split("@")[-1]
    print(f"target: {safe_target}")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
