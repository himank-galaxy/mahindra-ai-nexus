"""Validate immutable replay sources and perform the explicit runtime cutover.

Examples
--------
    python -m app.scripts.replay_cutover --validate-only
    python -m app.scripts.replay_cutover --copy-current
    python -m app.scripts.replay_cutover --initialize-runtime \
        --backup-reference database/backups/<stamp>/runtime_timeseries.dump

Three separate, explicit operations:

``--validate-only``
    Compare ``replay.*`` against ``public.*`` on row counts, source windows,
    distinct entity counts, natural-key duplicates and lineage integrity.
    Reads only.

``--copy-current``
    Additively populate ``replay.*`` from ``public.*`` with ``ON CONFLICT DO
    NOTHING`` and record the resulting source windows.  Never truncates or
    rewrites operational rows.

``--initialize-runtime``
    The cutover.  Only runs after validation passes.  Deletes runtime rows
    strictly after each domain's own replay start so the runtime tables hold
    pre-start history only, then seeds each per-domain ingestion checkpoint.
    Requires ``--backup-reference`` naming an existing dump, and refuses to
    re-run over an initialized, already-advanced pipeline unless
    ``--force-reinitialize`` is given.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session_factory
from app.models.causal_runtime_state import CausalReplayState
from app.services.live_ingestion import (
    DOMAIN_ENTITY_COLUMN,
    FIELD_CLOCK_DOMAINS,
    INGESTION_SOURCES,
    STATUS_READY,
    ensure_ingestion_states,
)

#: Rolling raw history each domain's PCMCI needs before it can produce a run.
#: The runtime tables are seeded with at least this much history so causal
#: discovery is valid from the very first tick instead of warming up blind.
MANUFACTURING_HISTORY_HOURS = 72.0
TELEMATICS_HISTORY_HOURS = 168.0

#: Natural key used to detect duplicate logical rows in a replay source.
NATURAL_KEYS: dict[str, tuple[str, ...]] = {
    "manufacturing": ("timestamp", "machine_id"),
    "telematics": ("timestamp", "vehicle_id"),
    "service": ("service_event_id",),
    "warranty": ("warranty_claim_id",),
}

#: ``warranty_claims.service_event_id`` references ``service_events``, so the
#: cutover deletes children before parents and backfills parents before
#: children.  Doing it in dictionary order trips the foreign key.
CUTOVER_DELETE_ORDER: tuple[str, ...] = ("manufacturing", "telematics", "warranty", "service")
CUTOVER_INSERT_ORDER: tuple[str, ...] = ("manufacturing", "telematics", "service", "warranty")

#: Lineage columns that must never be orphaned in a replay source.
LINEAGE_COLUMNS: dict[str, tuple[str, ...]] = {
    "manufacturing": ("machine_id", "production_batch_id", "supplier_lot_id", "plant_id"),
    "telematics": ("vehicle_id", "production_batch_id", "supplier_lot_id", "plant_id"),
}


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


async def _table_stats(
    session: AsyncSession, schema: str, table_name: str, time_column: str, domain: str
) -> dict[str, Any]:
    entity_column = DOMAIN_ENTITY_COLUMN.get(domain)
    entity_expression = (
        f", count(DISTINCT {entity_column}) AS entity_count" if entity_column else ", 0 AS entity_count"
    )
    row = (
        await session.execute(
            text(
                f"SELECT count(*) AS row_count, min({time_column}) AS source_from, "
                f"max({time_column}) AS source_to{entity_expression} FROM {schema}.{table_name}"
            )
        )
    ).mappings().one()
    return {
        "row_count": int(row["row_count"]),
        "source_from": _iso(row["source_from"]),
        "source_to": _iso(row["source_to"]),
        "entity_count": int(row["entity_count"]),
    }


async def _duplicate_count(session: AsyncSession, domain: str, table_name: str) -> int:
    key = ", ".join(f'"{column}"' for column in NATURAL_KEYS[domain])
    return int(
        (
            await session.execute(
                text(
                    f"SELECT count(*) FROM (SELECT {key} FROM replay.{table_name} "
                    f"GROUP BY {key} HAVING count(*) > 1) AS duplicated"
                )
            )
        ).scalar_one()
    )


async def _lineage_nulls(session: AsyncSession, domain: str, table_name: str) -> dict[str, int]:
    columns = LINEAGE_COLUMNS.get(domain)
    if not columns:
        return {}
    projection = ", ".join(
        f'count(*) FILTER (WHERE "{column}" IS NULL) AS "{column}"' for column in columns
    )
    row = (
        await session.execute(text(f"SELECT {projection} FROM replay.{table_name}"))
    ).mappings().one()
    return {column: int(row[column]) for column in columns}


async def validate(session: AsyncSession) -> dict[str, Any]:
    """Compare immutable source and runtime table without modifying either."""
    report: dict[str, Any] = {}
    for domain, source in INGESTION_SOURCES.items():
        table_name = source["source_table"]
        time_column = source["time_column"]
        replay_stats = await _table_stats(session, "replay", table_name, time_column, domain)
        runtime_stats = await _table_stats(session, "public", table_name, time_column, domain)
        duplicates = await _duplicate_count(session, domain, table_name)
        lineage_nulls = await _lineage_nulls(session, domain, table_name)
        missing_in_replay = int(
            (
                await session.execute(
                    text(
                        f"SELECT count(*) FROM public.{table_name} p "
                        f"WHERE NOT EXISTS (SELECT 1 FROM replay.{table_name} r WHERE "
                        + " AND ".join(f'r."{c}" = p."{c}"' for c in NATURAL_KEYS[domain])
                        + ")"
                    )
                )
            ).scalar_one()
        )
        checks = {
            "replay_source_present": replay_stats["row_count"] > 0,
            "no_natural_key_duplicates": duplicates == 0,
            "no_orphan_lineage": all(count == 0 for count in lineage_nulls.values()),
            "runtime_rows_covered_by_replay": missing_in_replay == 0,
        }
        report[domain] = {
            "replay": replay_stats,
            "runtime": runtime_stats,
            "duplicate_natural_keys": duplicates,
            "lineage_null_counts": lineage_nulls,
            "runtime_rows_missing_from_replay": missing_in_replay,
            "checks": checks,
            "valid": all(checks.values()),
        }
    report["valid"] = all(report[domain]["valid"] for domain in INGESTION_SOURCES)
    return report


async def _copy_current(session: AsyncSession) -> None:
    for source in INGESTION_SOURCES.values():
        table_name = source["source_table"]
        await session.execute(
            text(
                f"INSERT INTO replay.{table_name} SELECT * FROM public.{table_name} "
                "ON CONFLICT DO NOTHING"
            )
        )
    await session.commit()


async def _resolve_replay_starts(
    session: AsyncSession,
    validation: dict[str, Any],
    *,
    manufacturing_start: datetime | None,
    field_start: datetime | None,
) -> dict[str, datetime]:
    """Derive each domain's own replay anchor from its own immutable source.

    Manufacturing anchors ``72 h`` into its production window and telematics
    ``168 h`` into its post-delivery window so both PCMCI engines have their
    full validated rolling history on the very first tick.  The field domains
    share one anchor because they feed the same business clock.
    """
    manufacturing_source_from = datetime.fromisoformat(
        validation["manufacturing"]["replay"]["source_from"]
    )
    telematics_source_from = datetime.fromisoformat(
        validation["telematics"]["replay"]["source_from"]
    )

    resolved_manufacturing = manufacturing_start or (
        manufacturing_source_from + timedelta(hours=MANUFACTURING_HISTORY_HOURS)
    )

    resolved_field = field_start
    if resolved_field is None:
        replay = await session.get(CausalReplayState, "default")
        if replay is not None:
            resolved_field = replay.simulation_as_of.astimezone(UTC)
    if resolved_field is None:
        resolved_field = telematics_source_from + timedelta(hours=TELEMATICS_HISTORY_HOURS)

    starts = {"manufacturing": resolved_manufacturing.astimezone(UTC)}
    for domain in FIELD_CLOCK_DOMAINS:
        starts[domain] = resolved_field.astimezone(UTC)
    return starts


async def initialize_runtime(
    session: AsyncSession,
    *,
    validation: dict[str, Any],
    backup_reference: str,
    manufacturing_start: datetime | None,
    field_start: datetime | None,
    force: bool,
    now: datetime,
) -> dict[str, Any]:
    """Reset runtime tables to each domain's replay start and seed checkpoints."""
    if not validation["valid"]:
        raise RuntimeError("Replay source validation failed; refusing to initialize runtime tables.")

    states = {
        state.domain: state
        for state in (await ensure_ingestion_states(session))
    }
    already = [
        domain
        for domain, state in states.items()
        if state.initialized_at is not None and int(state.rows_ingested_total or 0) > 0
    ]
    if already and not force:
        return {
            "initialized": False,
            "reason": "already_initialized_and_advanced",
            "domains_already_advanced": sorted(already),
            "hint": "pass --force-reinitialize to rewind the runtime tables",
        }

    starts = await _resolve_replay_starts(
        session,
        validation,
        manufacturing_start=manufacturing_start,
        field_start=field_start,
    )

    deleted_rows: dict[str, int] = {}
    for domain in CUTOVER_DELETE_ORDER:
        source = INGESTION_SOURCES[domain]
        deleted = await session.execute(
            text(
                f"DELETE FROM public.{source['source_table']} "
                f"WHERE {source['time_column']} > :start"
            ),
            {"start": starts[domain]},
        )
        deleted_rows[domain] = max(0, int(deleted.rowcount or 0))

    outcome: dict[str, Any] = {}
    for domain in CUTOVER_INSERT_ORDER:
        source = INGESTION_SOURCES[domain]
        table_name = source["source_table"]
        time_column = source["time_column"]
        start = starts[domain]

        # Anything at or before the anchor must be physically present so the
        # rolling PCMCI window is complete from the first tick onward.
        backfilled = await session.execute(
            text(
                f"INSERT INTO public.{table_name} SELECT * FROM replay.{table_name} "
                f"WHERE {time_column} <= :start ON CONFLICT DO NOTHING"
            ),
            {"start": start},
        )
        remaining = (
            await session.execute(
                text(
                    f"SELECT count(*) AS row_count, max({time_column}) AS max_ts "
                    f"FROM public.{table_name}"
                )
            )
        ).mappings().one()

        state = states[domain]
        state.replay_start = start
        state.replay_cursor = start
        state.initialized_at = now
        state.exhausted_at = None
        state.last_ingested_timestamp = remaining["max_ts"]
        state.last_ingested_rows = 0
        state.rows_ingested_total = 0
        state.tick_count = 0
        state.last_error = None
        state.status = STATUS_READY
        state.diagnostics = {
            "cutover": {
                "replay_start": _iso(start),
                "rows_deleted_after_start": deleted_rows[domain],
                "rows_backfilled_to_start": max(0, int(backfilled.rowcount or 0)),
                "runtime_rows_after_cutover": int(remaining["row_count"]),
                "backup_reference": backup_reference,
            }
        }
        outcome[domain] = dict(state.diagnostics["cutover"])
        outcome[domain]["runtime_max_timestamp"] = _iso(remaining["max_ts"])

    # The shared business clock restarts at the field anchor. Manufacturing
    # keeps its own cursor and never drags this clock into the production past.
    replay = await session.get(CausalReplayState, "default")
    if replay is not None:
        replay.simulation_as_of = starts[FIELD_CLOCK_DOMAINS[0]]
        replay.replay_start = starts[FIELD_CLOCK_DOMAINS[0]]
        replay.last_tick_at = now
        replay.tick_count = 0
        replay.paused = False
        replay.last_error = None

    await session.commit()
    return {"initialized": True, "replay_starts": {k: _iso(v) for k, v in starts.items()}, "domains": outcome}


async def _record_manifest(
    session: AsyncSession, *, payload: dict[str, Any], status: str, notes: dict[str, Any]
) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    source_version = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    await session.execute(
        text(
            "INSERT INTO replay.cutover_manifest "
            "(manifest_key, source_version, validation_status, row_counts, source_windows, notes) "
            "VALUES ('default', :source_version, :status, CAST(:stats AS JSONB), CAST(:stats AS JSONB), "
            "CAST(:notes AS JSONB)) "
            "ON CONFLICT (manifest_key) DO UPDATE SET source_version = EXCLUDED.source_version, "
            "validation_status = EXCLUDED.validation_status, row_counts = EXCLUDED.row_counts, "
            "source_windows = EXCLUDED.source_windows, notes = EXCLUDED.notes, updated_at = now()"
        ),
        {
            "source_version": source_version,
            "status": status,
            "stats": serialized,
            "notes": json.dumps(notes, default=str),
        },
    )
    await session.commit()
    return source_version


async def run(
    *,
    copy_current: bool,
    initialize: bool,
    backup_reference: str | None,
    manufacturing_start: datetime | None,
    field_start: datetime | None,
    force: bool,
) -> dict[str, Any]:
    factory = get_session_factory()
    now = datetime.now(UTC)
    async with factory() as session:
        if copy_current:
            await _copy_current(session)

        validation = await validate(session)
        result: dict[str, Any] = {
            "validated_at": now.isoformat(),
            "validation": validation,
            "copy_current": copy_current,
        }

        if initialize:
            result["cutover"] = await initialize_runtime(
                session,
                validation=validation,
                backup_reference=backup_reference or "",
                manufacturing_start=manufacturing_start,
                field_start=field_start,
                force=force,
                now=now,
            )

        result["source_version"] = await _record_manifest(
            session,
            payload={domain: validation[domain]["replay"] for domain in INGESTION_SOURCES},
            status="VALIDATED" if validation["valid"] else "INVALID",
            notes={
                "copy_current": copy_current,
                "initialize_runtime": initialize,
                "backup_reference": backup_reference,
                "validated_at": now.isoformat(),
                "cutover": result.get("cutover", {}),
            },
        )
    return result


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("Replay start timestamps must include a timezone offset.")
    return parsed.astimezone(UTC)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-only", action="store_true", help="Validate replay sources only."
    )
    parser.add_argument(
        "--copy-current",
        action="store_true",
        help="Copy missing operational rows into replay sources.",
    )
    parser.add_argument(
        "--initialize-runtime",
        action="store_true",
        help="Reset runtime tables to each domain's replay start.",
    )
    parser.add_argument(
        "--backup-reference",
        default=None,
        help="Path/identifier of the dump taken before the cutover.",
    )
    parser.add_argument(
        "--manufacturing-start",
        type=_timestamp,
        default=None,
        help="Explicit manufacturing replay anchor (ISO-8601 with offset).",
    )
    parser.add_argument(
        "--field-start",
        type=_timestamp,
        default=None,
        help="Explicit telematics/service/warranty replay anchor.",
    )
    parser.add_argument(
        "--force-reinitialize",
        action="store_true",
        help="Rewind an already-advanced runtime pipeline.",
    )
    args = parser.parse_args()
    if args.initialize_runtime and not args.backup_reference:
        parser.error("--initialize-runtime requires --backup-reference")
    return args


def main() -> None:
    args = _parse_args()
    result = asyncio.run(
        run(
            copy_current=bool(args.copy_current),
            initialize=bool(args.initialize_runtime),
            backup_reference=args.backup_reference,
            manufacturing_start=args.manufacturing_start,
            field_start=args.field_start,
            force=bool(args.force_reinitialize),
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
