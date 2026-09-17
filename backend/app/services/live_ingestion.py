"""Physical minute-granularity ingestion from immutable replay sources.

Design
------
Every domain replays its OWN immutable source with its OWN watermark.  A
single global watermark cannot work here: production observations and
post-delivery field telemetry occupy different, non-overlapping source
windows, so forcing both through one clock means one of them can never be
complete and every tick rolls back.

Each tick, per domain:

    previous cursor
        -> target cursor (previous + elapsed * replay_speed, clamped to the
           domain's own immutable source maximum)
        -> INSERT every source row in (previous, target]
        -> persist cursor, physical row counts and diagnostics

Rows are inserted physically.  Nothing filters a pre-loaded future dataset by
watermark, so ``count(*)`` and ``max(timestamp)`` on the runtime tables
genuinely grow.  Inserts use the runtime natural key with ``ON CONFLICT DO
NOTHING`` so replaying the same interval produces zero duplicates.

A domain whose cursor reaches its source maximum reports ``SOURCE_EXHAUSTED``
rather than an error: an immutable source that has been fully replayed is a
fact about the source, not an ingestion failure.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.runtime_schema import runtime_tables
from app.models.causal_runtime_state import CausalIngestionState, CausalReplayState
from app.services.causal_runtime import get_replay_state, utc_now

logger = get_logger(__name__)


INGESTION_SOURCES: dict[str, dict[str, str]] = {
    "manufacturing": {"source_table": "manufacturing_timeseries", "time_column": "timestamp"},
    "telematics": {"source_table": "vehicle_telematics_timeseries", "time_column": "timestamp"},
    "service": {"source_table": "service_events", "time_column": "service_started_at"},
    "warranty": {"source_table": "warranty_claims", "time_column": "claim_submitted_at"},
}

#: Dense minute-grain streams. Their runtime tables carry an explicit
#: ``(timestamp, entity)`` natural key and feed PCMCI directly.
TIMESERIES_DOMAINS = frozenset({"manufacturing", "telematics"})

#: Domains whose cursor also drives the shared field/business clock used for
#: warning evaluation and cohort planning.  Manufacturing is deliberately not
#: one of them: its production window precedes the field window.
FIELD_CLOCK_DOMAINS = ("telematics", "service", "warranty")

#: Entity column used to report how many distinct entities a tick carried.
DOMAIN_ENTITY_COLUMN: dict[str, str] = {
    "manufacturing": "machine_id",
    "telematics": "vehicle_id",
}

STATUS_READY = "READY"
STATUS_PAUSED = "PAUSED"
STATUS_ERROR = "ERROR"
STATUS_NOT_READY = "NOT_READY"
STATUS_EXHAUSTED = "SOURCE_EXHAUSTED"
STATUS_UNINITIALIZED = "AWAITING_CUTOVER"


@dataclass(frozen=True)
class DomainTick:
    """One domain's physical ingestion result for a single tick."""

    domain: str
    advanced: bool
    status: str
    previous_cursor: datetime | None
    cursor: datetime | None
    rows_inserted: int
    entities_inserted: int
    max_timestamp: datetime | None
    batch_id: uuid.UUID | None
    error: str | None = None


@dataclass(frozen=True)
class IngestionTick:
    """Aggregate result of one ingestion tick across every domain."""

    advanced: bool
    previous_as_of: datetime
    simulation_as_of: datetime
    rows_by_domain: dict[str, int] = field(default_factory=dict)
    batch_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    domains: dict[str, DomainTick] = field(default_factory=dict)


class ReplaySourceNotReady(RuntimeError):
    """Raised when a domain cannot be replayed at all (no immutable source)."""

    def __init__(self, domain: str, reason: str) -> None:
        self.domain = domain
        self.reason = reason
        super().__init__(f"{domain} replay source is not usable: {reason}")


# ---------------------------------------------------------------------------
# State bootstrap
# ---------------------------------------------------------------------------


async def ensure_ingestion_states(session: AsyncSession) -> list[CausalIngestionState]:
    """Create the per-domain checkpoint rows once; never overwrite them."""
    for domain, source in INGESTION_SOURCES.items():
        await session.execute(
            pg_insert(CausalIngestionState)
            .values(domain=domain, source_table=source["source_table"], status=STATUS_NOT_READY)
            .on_conflict_do_nothing(index_elements=[CausalIngestionState.domain])
        )
    await session.commit()
    return list(
        (
            await session.execute(
                select(CausalIngestionState).order_by(CausalIngestionState.domain)
            )
        ).scalars()
    )


async def source_bounds(
    session: AsyncSession, table_name: str, time_column: str
) -> tuple[datetime | None, datetime | None]:
    """Return the immutable replay source's own first/last timestamp."""
    row = (
        await session.execute(
            text(
                f"SELECT min({time_column}) AS source_from, max({time_column}) AS source_to "
                f"FROM replay.{table_name}"
            )
        )
    ).mappings().one()
    return row["source_from"], row["source_to"]


async def runtime_max(
    session: AsyncSession, table_name: str, time_column: str
) -> datetime | None:
    table = runtime_tables[table_name]
    return (
        await session.execute(select(func.max(getattr(table.c, time_column))))
    ).scalar_one_or_none()


async def runtime_count(session: AsyncSession, table_name: str) -> int:
    table = runtime_tables[table_name]
    return int((await session.execute(select(func.count()).select_from(table))).scalar_one())


# ---------------------------------------------------------------------------
# Physical insert
# ---------------------------------------------------------------------------


async def _insert_due_rows(
    session: AsyncSession,
    *,
    domain: str,
    table_name: str,
    time_column: str,
    previous_cursor: datetime,
    target_cursor: datetime,
) -> tuple[int, int, datetime | None]:
    """Insert every immutable source row in ``(previous, target]``.

    Returns the physical row count, the distinct entity count carried by the
    interval, and the newest timestamp actually inserted.  ``ON CONFLICT DO
    NOTHING`` on the runtime natural key makes a replayed interval a no-op.
    """
    table = runtime_tables[table_name]
    columns = ", ".join(f'"{column.name}"' for column in table.columns)
    entity_column = DOMAIN_ENTITY_COLUMN.get(domain)

    entity_expression = f", count(DISTINCT {entity_column}) AS entities" if entity_column else ", 0 AS entities"
    due = (
        await session.execute(
            text(
                f"SELECT count(*) AS due_rows, max({time_column}) AS due_max{entity_expression} "
                f"FROM replay.{table_name} "
                f"WHERE {time_column} > :previous_cursor AND {time_column} <= :target_cursor"
            ),
            {"previous_cursor": previous_cursor, "target_cursor": target_cursor},
        )
    ).mappings().one()

    if int(due["due_rows"]) == 0:
        return 0, 0, None

    result = await session.execute(
        text(
            f"INSERT INTO public.{table_name} ({columns}) "
            f"SELECT {columns} FROM replay.{table_name} AS src "
            f"WHERE src.{time_column} > :previous_cursor AND src.{time_column} <= :target_cursor "
            "ON CONFLICT DO NOTHING"
        ),
        {"previous_cursor": previous_cursor, "target_cursor": target_cursor},
    )
    return max(0, int(result.rowcount or 0)), int(due["entities"]), due["due_max"]


# ---------------------------------------------------------------------------
# Per-domain tick
# ---------------------------------------------------------------------------


def _target_cursor(
    *,
    previous_cursor: datetime,
    elapsed_seconds: float,
    replay_speed: float,
    source_to: datetime,
) -> datetime:
    """Advance one domain cursor by replayed simulated minutes, clamped."""
    advanced = previous_cursor + timedelta(minutes=(elapsed_seconds / 60.0) * replay_speed)
    return min(advanced, source_to)


async def ingest_domain_tick(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    domain: str,
    now: datetime,
    elapsed_seconds: float,
    replay_speed: float,
    paused: bool,
) -> DomainTick:
    """Replay one domain independently inside its own transaction.

    One domain's failure must never roll back another domain's committed
    minute, and a failed insert must never advance that domain's checkpoint.
    """
    source = INGESTION_SOURCES[domain]
    table_name = source["source_table"]
    time_column = source["time_column"]

    async with session_factory() as session:
        try:
            state = (
                await session.execute(
                    select(CausalIngestionState)
                    .where(CausalIngestionState.domain == domain)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if state is None:
                await session.rollback()
                return DomainTick(domain, False, STATUS_NOT_READY, None, None, 0, 0, None, None, "no_checkpoint_row")

            available_from, available_to = await source_bounds(session, table_name, time_column)
            state.source_available_from = available_from
            state.source_available_to = available_to
            state.last_attempt_at = now

            if available_to is None:
                state.status = STATUS_NOT_READY
                state.last_error = "immutable replay source is empty"
                await session.commit()
                return DomainTick(domain, False, STATUS_NOT_READY, None, None, 0, 0, None, None, state.last_error)

            if state.initialized_at is None or state.replay_cursor is None:
                state.status = STATUS_UNINITIALIZED
                state.last_error = None
                await session.commit()
                return DomainTick(
                    domain, False, STATUS_UNINITIALIZED, state.replay_cursor, state.replay_cursor, 0, 0, None, None
                )

            previous_cursor = utc_now(state.replay_cursor)

            if paused:
                state.status = STATUS_PAUSED
                state.last_error = None
                await session.commit()
                return DomainTick(domain, False, STATUS_PAUSED, previous_cursor, previous_cursor, 0, 0, None, None)

            if previous_cursor >= utc_now(available_to):
                state.status = STATUS_EXHAUSTED
                state.exhausted_at = state.exhausted_at or now
                state.last_ingested_rows = 0
                state.last_error = None
                state.diagnostics = {
                    "reason": "replay_cursor_reached_immutable_source_maximum",
                    "replay_cursor": previous_cursor.isoformat(),
                    "source_available_to": utc_now(available_to).isoformat(),
                }
                await session.commit()
                return DomainTick(
                    domain, False, STATUS_EXHAUSTED, previous_cursor, previous_cursor, 0, 0, None, None
                )

            target_cursor = _target_cursor(
                previous_cursor=previous_cursor,
                elapsed_seconds=elapsed_seconds,
                replay_speed=replay_speed,
                source_to=utc_now(available_to),
            )
            if target_cursor <= previous_cursor:
                state.status = STATUS_READY
                state.last_error = None
                await session.commit()
                return DomainTick(domain, False, STATUS_READY, previous_cursor, previous_cursor, 0, 0, None, None)

            batch_id = uuid.uuid4()
            rows, entities, inserted_max = await _insert_due_rows(
                session,
                domain=domain,
                table_name=table_name,
                time_column=time_column,
                previous_cursor=previous_cursor,
                target_cursor=target_cursor,
            )

            state.replay_cursor = target_cursor
            state.last_ingested_rows = rows
            state.rows_ingested_total = int(state.rows_ingested_total or 0) + rows
            state.last_batch_id = batch_id
            state.last_batch_signature = f"{domain}:{target_cursor.isoformat()}"
            state.last_commit_at = now
            state.last_tick_at = now
            state.tick_count = int(state.tick_count or 0) + 1
            state.last_error = None
            if inserted_max is not None:
                state.last_ingested_timestamp = inserted_max
            state.status = (
                STATUS_EXHAUSTED if target_cursor >= utc_now(available_to) else STATUS_READY
            )
            if state.status == STATUS_EXHAUSTED:
                state.exhausted_at = state.exhausted_at or now
            state.diagnostics = {
                "previous_cursor": previous_cursor.isoformat(),
                "replay_cursor": target_cursor.isoformat(),
                "simulated_minutes_replayed": round(
                    (target_cursor - previous_cursor).total_seconds() / 60.0, 3
                ),
                "rows_inserted": rows,
                "entities_inserted": entities,
                "newest_row_inserted": inserted_max.isoformat() if inserted_max else None,
                "source_available_to": utc_now(available_to).isoformat(),
            }
            await session.commit()

            logger.info(
                "replay_ingestion_committed",
                domain=domain,
                previous_cursor=previous_cursor.isoformat(),
                replay_cursor=target_cursor.isoformat(),
                rows_inserted=rows,
                entities_inserted=entities,
                newest_row_inserted=inserted_max.isoformat() if inserted_max else None,
                status=state.status,
            )
            return DomainTick(
                domain=domain,
                advanced=True,
                status=state.status,
                previous_cursor=previous_cursor,
                cursor=target_cursor,
                rows_inserted=rows,
                entities_inserted=entities,
                max_timestamp=inserted_max,
                batch_id=batch_id,
            )
        except Exception as exc:  # noqa: BLE001 - the checkpoint must not advance
            await session.rollback()
            logger.exception("replay_ingestion_rolled_back", domain=domain, error=str(exc))
            async with session_factory() as error_session:
                state = await error_session.get(CausalIngestionState, domain)
                if state is not None:
                    state.status = STATUS_ERROR
                    state.last_error = str(exc)[:2000]
                    state.last_attempt_at = now
                    await error_session.commit()
            return DomainTick(domain, False, STATUS_ERROR, None, None, 0, 0, None, None, str(exc)[:2000])


# ---------------------------------------------------------------------------
# Tick orchestration
# ---------------------------------------------------------------------------


async def ingest_tick(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    now: datetime | None = None,
) -> IngestionTick | None:
    """Replay one tick for every domain and advance the shared field clock."""
    current = utc_now(now)
    settings = get_settings()
    tick_interval = max(1, settings.simulation_tick_interval_seconds)

    async with session_factory() as clock_session:
        replay = await get_replay_state(clock_session, initialize=True, now=current)
        assert replay is not None
        replay = (
            await clock_session.execute(
                select(CausalReplayState)
                .where(CausalReplayState.state_key == "default")
                .with_for_update()
            )
        ).scalar_one()

        previous_as_of = utc_now(replay.simulation_as_of)
        paused = bool(replay.paused)
        replay_speed = float(replay.replay_speed)
        elapsed = max(0.0, (current - utc_now(replay.last_tick_at)).total_seconds())

        if paused:
            replay.last_tick_at = current
            replay.last_error = None
            await clock_session.commit()
        elif elapsed < tick_interval:
            await clock_session.rollback()
            return IngestionTick(False, previous_as_of, previous_as_of)
        else:
            await clock_session.rollback()

    domains = await asyncio.gather(
        *(
            ingest_domain_tick(
                session_factory,
                domain=domain,
                now=current,
                elapsed_seconds=elapsed,
                replay_speed=replay_speed,
                paused=paused,
            )
            for domain in INGESTION_SOURCES
        )
    )
    by_domain = {result.domain: result for result in domains}

    if paused:
        return IngestionTick(False, previous_as_of, previous_as_of, {}, {}, by_domain)

    # The shared field clock follows the field domains only. Manufacturing
    # replays an earlier production window and must not drag the clock back.
    field_cursors = [
        by_domain[domain].cursor
        for domain in FIELD_CLOCK_DOMAINS
        if by_domain.get(domain) is not None and by_domain[domain].cursor is not None
    ]
    simulation_as_of = max(field_cursors) if field_cursors else previous_as_of
    simulation_as_of = max(utc_now(simulation_as_of), previous_as_of)

    async with session_factory() as clock_session:
        replay = (
            await clock_session.execute(
                select(CausalReplayState)
                .where(CausalReplayState.state_key == "default")
                .with_for_update()
            )
        ).scalar_one()
        replay.simulation_as_of = min(simulation_as_of, utc_now(replay.replay_end))
        replay.last_tick_at = current
        replay.tick_count = int(replay.tick_count or 0) + 1
        errors = [result.error for result in domains if result.error]
        replay.last_error = "; ".join(errors)[:2000] if errors else None
        await clock_session.commit()
        committed_as_of = utc_now(replay.simulation_as_of)

    rows_by_domain = {result.domain: result.rows_inserted for result in domains}
    batch_ids = {
        result.domain: result.batch_id for result in domains if result.batch_id is not None
    }
    advanced = any(result.advanced for result in domains)
    logger.info(
        "replay_tick_completed",
        simulation_as_of=committed_as_of.isoformat(),
        elapsed_seconds=round(elapsed, 2),
        rows_by_domain=rows_by_domain,
        statuses={result.domain: result.status for result in domains},
    )
    return IngestionTick(
        advanced=advanced,
        previous_as_of=previous_as_of,
        simulation_as_of=committed_as_of,
        rows_by_domain=rows_by_domain,
        batch_ids=batch_ids,
        domains=by_domain,
    )


async def ingestion_loop() -> None:
    settings = get_settings()
    if not settings.causal_ingestion_enabled:
        logger.info("causal_ingestion_disabled")
        return
    from app.database.session import get_session_factory

    factory = get_session_factory()
    logger.info(
        "causal_ingestion_started",
        poll_seconds=settings.causal_ingestion_poll_seconds,
        tick_interval_seconds=settings.simulation_tick_interval_seconds,
    )
    while True:
        try:
            async with factory() as setup:
                await ensure_ingestion_states(setup)
            await ingest_tick(factory)
        except Exception as exc:  # noqa: BLE001 - the worker must survive transient failures
            logger.exception("causal_ingestion_iteration_failed", error=str(exc))
        await asyncio.sleep(settings.causal_ingestion_poll_seconds)


__all__ = [
    "DOMAIN_ENTITY_COLUMN",
    "FIELD_CLOCK_DOMAINS",
    "INGESTION_SOURCES",
    "STATUS_EXHAUSTED",
    "STATUS_READY",
    "STATUS_UNINITIALIZED",
    "TIMESERIES_DOMAINS",
    "DomainTick",
    "IngestionTick",
    "ReplaySourceNotReady",
    "ensure_ingestion_states",
    "ingest_domain_tick",
    "ingest_tick",
    "ingestion_loop",
    "runtime_count",
    "runtime_max",
    "source_bounds",
]
