"""Persistent scheduler for replayed manufacturing and telematics causality.

Scheduling contract
-------------------
The source-change check runs every poll.  A causal run starts only when the
domain's deterministic source signature actually changes, never because a
timer fired.  At most one run per domain may be active: a PostgreSQL advisory
lock enforces single flight, and a tick that arrives while a run is active
records a coalesced pending target instead of queueing another job.  When a
run finishes and a pending target is recorded, exactly one follow-up run
executes against the newest data.

The two domains never block each other.  They hold different advisory locks,
use different sessions, and in the deployed stack run in separate processes.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.causal.manufacturing_filter import DEFAULT_MANUFACTURING_FILTER_CONFIG
from app.ai.causal.manufacturing_panel import DEFAULT_MANUFACTURING_PANEL_CONFIG
from app.ai.causal.telematics_filter import DEFAULT_TELEMATICS_FILTER_CONFIG
from app.ai.causal.telematics_panel import DEFAULT_TELEMATICS_PANEL_CONFIG
from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.runtime_schema import runtime_tables
from app.database.session import get_session_factory
from app.models.causal_runtime_state import CausalIngestionState, CausalSchedulerState
from app.services.causal_runtime import (
    advance_replay_clock,
    ensure_scheduler_states,
    get_replay_state,
    get_scheduler_state,
    release_advisory_lock,
    stable_source_signature,
    try_advisory_lock_session,
    update_scheduler_state,
    utc_now,
)
from app.services.manufacturing_causal import ManufacturingCausalService
from app.services.manufacturing_causal import effective_pc_alpha as manufacturing_effective_pc_alpha
from app.services.manufacturing_causal import effective_tau_max as manufacturing_effective_tau_max
from app.services.telematics_causal import TelematicsCausalService
from app.services.telematics_causal import effective_pc_alpha as telematics_effective_pc_alpha
from app.services.telematics_causal import effective_tau_max as telematics_effective_tau_max
from app.services.warranty_quality_evaluation import evaluate_and_persist

logger = get_logger(__name__)

#: Validated rolling raw history per domain. Manufacturing resamples 72 raw
#: hours to 15-minute analytical buckets; telematics resamples 168 raw
#: post-delivery hours to 5-minute buckets.
MANUFACTURING_HISTORY_HOURS = 72.0
TELEMATICS_HISTORY_HOURS = 168.0

#: A machine is only admitted when the rolling window holds enough raw rows to
#: fill the analytical panel it will be resampled into.
MANUFACTURING_ANALYSIS_MINUTES = 15
TELEMATICS_ANALYSIS_MINUTES = 5

#: Bump when the fingerprinted fields below change meaning in a way that
#: isn't otherwise mechanically detectable (e.g. a preprocessing step is
#: added but happens not to change any dataclass field value) -- forces
#: every scheduler-fast-path reuse decision to re-evaluate against the
#: service on the next tick after a deploy.
#:
#: v1 -> v2: the persisted tau_min for LPCMCI with test_contemporaneous=True
#: was incorrectly recorded as 1 while the engine actually ran with
#: tau_min=0 (fixed in effective_tau_min / _analysis_parameters /
#: _configuration_parameters). tau_min feeds this same fingerprint (via the
#: tau_min value the scheduler now resolves and passes through), so scheduler
#: state persisted under the old, incorrect v1 semantics must not fast-path
#: reuse against the corrected v2 configuration -- bumping the version
#: forces exactly one fresh service call per domain to re-evaluate under
#: the fix, the same mechanism already used for the PCMCI -> LPCMCI cutover.
CAUSAL_ANALYSIS_CONFIG_VERSION = "v2"


def _analysis_config_signature(
    *,
    domain: str,
    algorithm: str,
    test_contemporaneous: bool,
    tau_max: int,
    pc_alpha: float,
    algorithm_config: dict[str, Any] | None,
    panel_config: Any,
    filter_config: Any,
) -> str:
    """
    Deterministic fingerprint of the causal-analysis CONFIGURATION the
    scheduler is about to request -- distinct from ``plan.signature``
    (the pure source-data signature built by build_manufacturing_source_
    plan/build_telematics_source_plan).

    Why this must be separate from the source signature
    -----------------------------------------------------
    ``plan.signature`` only ever changes when the underlying observations
    change. A deployment-time configuration change (e.g. flipping
    causal_algorithm from "pcmci" to "lpcmci") does NOT touch source data
    at all, so folding algorithm/config into the source signature would
    require redefining what "source signature" means -- exactly the
    conflation this function exists to avoid. Reusing a persisted run
    requires BOTH signatures to match; either one changing means a fresh
    call to the orchestration service is required (the service then
    computes its OWN deterministic run signature -- see
    ManufacturingCausalService._analysis_parameters/_source_signature --
    which is the actual authority on whether a persisted run can be
    reused; this scheduler-level fingerprint only decides whether the
    scheduler's OWN fast-path may skip calling the service at all).
    """

    return stable_source_signature(
        {
            "config_version": CAUSAL_ANALYSIS_CONFIG_VERSION,
            "domain": domain,
            "algorithm": algorithm,
            "test_contemporaneous": (
                test_contemporaneous
                if algorithm == "lpcmci"
                else None
            ),
            "tau_max": tau_max,
            "pc_alpha": pc_alpha,
            "algorithm_config": dict(algorithm_config or {}),
            "panel_config": asdict(panel_config),
            "filter_config": asdict(filter_config),
        }
    )


@dataclass(frozen=True)
class SchedulerReuseDecision:
    #: True only when the scheduler may skip calling the orchestration
    #: service entirely and resurface the last persisted run as-is.
    reuse: bool
    #: One of "source_signature_unchanged" (fast-path reuse taken),
    #: "analysis_config_changed", "source_signature_changed", or
    #: "force_refresh" (all three: service must be called).
    decision: str


def _scheduler_reuse_decision(
    *,
    force_refresh: bool,
    state: CausalSchedulerState | None,
    source_signature: str,
    analysis_config_signature: str,
) -> SchedulerReuseDecision:
    """
    Pure routing decision: may the scheduler skip calling the orchestration
    service and resurface the last persisted run as-is?

    Reuse requires ALL of: not forced, a prior state row with a persisted
    run exists, AND both the source-data signature and the analysis-
    configuration signature are unchanged from that prior run.

    Source and configuration are independent axes. A PCMCI -> LPCMCI
    deployment-time cutover changes nothing about the source data, so
    checking last_source_signature alone (the pre-fix behavior) would
    silently keep resurfacing a historical PCMCI run forever whenever the
    source itself happened not to change -- the service would never even
    be called, so it would never get the chance to compute a fresh LPCMCI
    run signature. Either axis changing here means the service MUST be
    called; the service alone is the authority on whether a persisted run
    genuinely already matches the request (via its own deterministic run
    signature, e.g. ManufacturingCausalService._source_signature).

    A missing state row (no prior run at all) is routed the same as a
    changed source: there is nothing to compare against, so nothing can be
    "unchanged".
    """

    if state is None or state.last_run_id is None:
        return SchedulerReuseDecision(
            reuse=False,
            decision="source_signature_changed",
        )

    source_unchanged = (
        state.last_source_signature
        == source_signature
    )

    config_unchanged = (
        state.last_analysis_config_signature
        == analysis_config_signature
    )

    if (
        not force_refresh
        and source_unchanged
        and config_unchanged
    ):
        return SchedulerReuseDecision(
            reuse=True,
            decision="source_signature_unchanged",
        )

    if force_refresh:
        decision = "force_refresh"
    elif not source_unchanged:
        decision = "source_signature_changed"
    else:
        decision = "analysis_config_changed"

    return SchedulerReuseDecision(
        reuse=False,
        decision=decision,
    )


@dataclass(frozen=True)
class ManufacturingSourcePlan:
    machine_ids: tuple[str, ...]
    source_from: datetime
    source_to: datetime
    analysis_end: datetime | None
    history_hours: float
    signature: str
    diagnostics: dict[str, Any]
    persisted_run_id: Any = None


@dataclass(frozen=True)
class TelematicsSourcePlan:
    vehicle_ids: tuple[str, ...]
    source_from: datetime
    source_to: datetime
    history_hours: float
    signature: str
    diagnostics: dict[str, Any]


class SourceNotReady(RuntimeError):
    def __init__(self, reason: str, diagnostics: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.diagnostics = diagnostics or {}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _lineage_predicate(table: Any, lineage_keys: list[tuple[str, str, str]]) -> Any:
    return or_(
        *(
            and_(
                table.c.machine_id == machine,
                table.c.production_batch_id == batch,
                table.c.supplier_lot_id == lot,
            )
            for machine, batch, lot in lineage_keys
        )
    )


async def _domain_cursor(session: AsyncSession, domain: str) -> datetime | None:
    """Return how far this domain's own immutable source has been replayed."""
    state = await session.get(CausalIngestionState, domain)
    if state is None or state.replay_cursor is None:
        return None
    return utc_now(state.replay_cursor)


async def _visible_field_lineages(session: AsyncSession, as_of: datetime) -> list[tuple[str, str, str]]:
    """Exact (machine, batch, lot) triples implicated by visible field evidence."""
    tables = runtime_tables
    service = tables["service_events"]
    warranty = tables["warranty_claims"]
    service_rows = (
        await session.execute(
            select(
                service.c.representative_machine_id,
                service.c.production_batch_id,
                service.c.primary_supplier_lot_id,
            )
            .where(service.c.issue_category.is_not(None), service.c.service_started_at <= as_of)
            .where(
                service.c.representative_machine_id.is_not(None),
                service.c.production_batch_id.is_not(None),
                service.c.primary_supplier_lot_id.is_not(None),
            )
            .distinct()
        )
    ).all()
    warranty_rows = (
        await session.execute(
            select(
                warranty.c.representative_machine_id,
                warranty.c.production_batch_id,
                warranty.c.primary_supplier_lot_id,
            )
            .where(warranty.c.issue_category.is_not(None), warranty.c.claim_submitted_at <= as_of)
            .where(
                warranty.c.representative_machine_id.is_not(None),
                warranty.c.production_batch_id.is_not(None),
                warranty.c.primary_supplier_lot_id.is_not(None),
            )
            .distinct()
        )
    ).all()
    values = {
        (str(machine), str(batch), str(lot))
        for machine, batch, lot in [*service_rows, *warranty_rows]
        if machine and batch and lot
    }
    return sorted(values)


async def _field_relevant_vehicles(session: AsyncSession, as_of: datetime) -> set[str]:
    """Vehicles carrying visible field-issue evidence at the business clock.

    These vehicles receive cohort priority.  Membership is derived from the
    runtime evidence tables every time it is needed, so no warning vehicle is
    ever hard-coded into the scheduler.
    """
    tables = runtime_tables
    service = tables["service_events"]
    warranty = tables["warranty_claims"]
    service_rows = (
        await session.execute(
            select(service.c.vehicle_id)
            .where(service.c.issue_category.is_not(None), service.c.service_started_at <= as_of)
            .where(service.c.vehicle_id.is_not(None))
            .distinct()
        )
    ).scalars().all()
    warranty_rows = (
        await session.execute(
            select(warranty.c.vehicle_id)
            .where(warranty.c.issue_category.is_not(None), warranty.c.claim_submitted_at <= as_of)
            .where(warranty.c.vehicle_id.is_not(None))
            .distinct()
        )
    ).scalars().all()
    return {str(value) for value in [*service_rows, *warranty_rows] if value}


# ---------------------------------------------------------------------------
# Manufacturing plan
# ---------------------------------------------------------------------------


async def build_manufacturing_source_plan(
    session: AsyncSession,
    as_of: datetime,
    *,
    manufacturing_cursor: datetime | None = None,
) -> ManufacturingSourcePlan:
    """Plan the rolling manufacturing window anchored on the implicated production.

    The window is the trailing ``72 h`` of physically ingested production
    observations ending where the implicated batches were actually built — not
    where the replay clock happens to be.  A field failure is caused by the
    production run that made that vehicle, so sliding the window past that
    production would silently swap the evidence for an unrelated later shift.
    The cohort keeps the validated exact-lineage rule: only production lines
    that actually built a vehicle carrying visible field evidence are admitted,
    and the line's own machines join so PCMCI has process context.

    The signature still moves as the pipeline runs: it changes when new field
    evidence implicates a different batch or lot, and while the implicated
    production window is still being physically ingested.
    """
    tables = runtime_tables
    manufacturing = tables["manufacturing_timeseries"]
    machines_table = tables["machines"]

    lineages = await _visible_field_lineages(session, as_of)
    if not lineages:
        raise SourceNotReady("NO_VISIBLE_FIELD_LINEAGE", {"visible_field_lineages": 0})

    ingested_to = manufacturing_cursor
    if ingested_to is None:
        ingested_to = (
            await session.execute(select(func.max(manufacturing.c.timestamp)))
        ).scalar_one_or_none()
    if ingested_to is None:
        raise SourceNotReady(
            "NO_INGESTED_MANUFACTURING_ROWS", {"visible_field_lineages": len(lineages)}
        )
    ingested_to = utc_now(ingested_to)

    # Anchor on the newest physically ingested observation that belongs to the
    # exact (machine, batch, lot) lineage carrying visible field evidence.
    lineage_bounds = (
        await session.execute(
            select(
                func.min(manufacturing.c.timestamp).label("lineage_from"),
                func.max(manufacturing.c.timestamp).label("lineage_to"),
                func.count().label("lineage_rows"),
            )
            .where(manufacturing.c.timestamp <= ingested_to)
            .where(_lineage_predicate(manufacturing, lineages))
        )
    ).mappings().one()
    if lineage_bounds["lineage_to"] is None:
        raise SourceNotReady(
            "NO_VISIBLE_MANUFACTURING_ROWS",
            {
                "visible_field_lineages": len(lineages),
                "manufacturing_ingested_to": ingested_to.isoformat(),
                "reason": "no ingested production row matches the exact field lineage",
            },
        )
    lineage_from = utc_now(lineage_bounds["lineage_from"])
    lineage_to = utc_now(lineage_bounds["lineage_to"])

    # The window must CONTAIN the implicated production, not end at it: the
    # causal dynamics of those machines are estimated over a full 72 h of
    # their own observations, starting where the implicated batches were
    # built. While ingestion is still filling that window the end advances
    # with the cursor, so the signature moves and PCMCI genuinely re-runs;
    # once the window is complete the signature settles and runs are reused.
    analysis_end = min(
        lineage_from + timedelta(hours=MANUFACTURING_HISTORY_HOURS), ingested_to
    )
    analysis_end = max(analysis_end, lineage_to)
    source_from = analysis_end - timedelta(hours=MANUFACTURING_HISTORY_HOURS)

    exact_machines = tuple(
        sorted(
            str(value)
            for value in (
                await session.execute(
                    select(manufacturing.c.machine_id)
                    .where(
                        manufacturing.c.timestamp > source_from,
                        manufacturing.c.timestamp <= analysis_end,
                    )
                    .where(_lineage_predicate(manufacturing, lineages))
                    .distinct()
                )
            ).scalars().all()
        )
    )
    if not exact_machines:
        raise SourceNotReady(
            "NO_VISIBLE_MANUFACTURING_ROWS",
            {
                "visible_field_lineages": len(lineages),
                "window_from": source_from.isoformat(),
                "window_to": analysis_end.isoformat(),
            },
        )

    # Production-line peers of the implicated machines. This is the validated
    # cohort rule and is not widened to unrelated lines.
    lines = (
        await session.execute(
            select(machines_table.c.production_line_id)
            .where(machines_table.c.machine_id.in_(exact_machines))
            .distinct()
        )
    ).scalars().all()
    line_ids = tuple(sorted(str(value) for value in lines if value))

    minimum_rows = int(
        DEFAULT_MANUFACTURING_PANEL_CONFIG.min_panel_observations * MANUFACTURING_ANALYSIS_MINUTES
    )
    cohort_rows = (
        await session.execute(
            select(manufacturing.c.machine_id, func.count().label("row_count"))
            .select_from(
                manufacturing.join(
                    machines_table, machines_table.c.machine_id == manufacturing.c.machine_id
                )
            )
            .where(manufacturing.c.timestamp > source_from, manufacturing.c.timestamp <= analysis_end)
            .where(
                or_(
                    machines_table.c.production_line_id.in_(line_ids),
                    manufacturing.c.machine_id.in_(exact_machines),
                )
            )
            .group_by(manufacturing.c.machine_id)
        )
    ).mappings().all()

    eligible = {
        str(row["machine_id"]): int(row["row_count"])
        for row in cohort_rows
        if int(row["row_count"]) >= minimum_rows
    }
    excluded = {
        str(row["machine_id"]): "insufficient_raw_history"
        for row in cohort_rows
        if int(row["row_count"]) < minimum_rows
    }
    machine_ids = tuple(sorted(eligible))
    if len(machine_ids) < 2:
        raise SourceNotReady(
            "INSUFFICIENT_MANUFACTURING_MACHINES",
            {
                "machines_eligible": len(machine_ids),
                "minimum_raw_rows": minimum_rows,
                "exclusions": excluded,
            },
        )

    missing_exact = sorted(set(exact_machines) - set(machine_ids))
    source_rows = sum(eligible.values())
    signature = stable_source_signature(
        {
            "domain": "manufacturing",
            "machine_ids": machine_ids,
            "source_from": source_from,
            "source_to": analysis_end,
            "source_rows": source_rows,
            "history_hours": MANUFACTURING_HISTORY_HOURS,
            "analysis_frequency": DEFAULT_MANUFACTURING_PANEL_CONFIG.analysis_frequency,
            "exact_lineage_machines": exact_machines,
            "lineage_rows_ingested": int(lineage_bounds["lineage_rows"]),
        }
    )
    return ManufacturingSourcePlan(
        machine_ids=machine_ids,
        source_from=source_from,
        source_to=analysis_end,
        analysis_end=analysis_end,
        history_hours=MANUFACTURING_HISTORY_HOURS,
        signature=signature,
        diagnostics={
            "cohort_source": "exact_field_lineage_production_lines",
            "window_anchor": "implicated_production_lineage",
            "visible_field_lineages": len(lineages),
            "exact_lineage_machines": list(exact_machines),
            "production_lines": list(line_ids),
            "machines_eligible": len(machine_ids),
            "machines_excluded": excluded,
            "exact_lineage_machines_excluded": missing_exact,
            "minimum_raw_rows": minimum_rows,
            "source_rows": source_rows,
            "window_from": source_from.isoformat(),
            "window_to": analysis_end.isoformat(),
            "rolling_window_hours": MANUFACTURING_HISTORY_HOURS,
            "lineage_production_from": lineage_from.isoformat(),
            "lineage_production_to": lineage_to.isoformat(),
            "lineage_rows_ingested": int(lineage_bounds["lineage_rows"]),
            "manufacturing_ingested_to": ingested_to.isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# Telematics plan
# ---------------------------------------------------------------------------


async def build_telematics_source_plan(
    session: AsyncSession,
    as_of: datetime,
    *,
    telematics_cursor: datetime | None = None,
) -> TelematicsSourcePlan:
    """Plan the post-delivery rolling window, prioritising field-relevant vehicles.

    Cohort membership is an eligibility decision, never a recency decision.  A
    vehicle that carries visible field evidence joins the cohort whenever it is
    genuinely analysable inside the current window; if it is not, the exact
    factual reason is persisted instead of being silently dropped.  The
    ``supporting_vehicle_ids`` intersection in the warning layer is untouched.
    """
    tables = runtime_tables
    telemetry = tables["vehicle_telematics_timeseries"]
    deliveries = tables["deliveries"]
    panel = DEFAULT_TELEMATICS_PANEL_CONFIG

    source_to = telematics_cursor
    if source_to is None:
        source_to = (
            await session.execute(
                select(func.max(telemetry.c.timestamp)).where(telemetry.c.timestamp <= as_of)
            )
        ).scalar_one_or_none()
    if source_to is None:
        raise SourceNotReady("NO_INGESTED_TELEMATICS_ROWS", {"vehicles_seen": 0})
    source_to = utc_now(source_to)
    source_from = source_to - timedelta(hours=TELEMATICS_HISTORY_HOURS)

    raw_rows_required = int(panel.min_panel_observations * TELEMATICS_ANALYSIS_MINUTES)
    field_vehicles = await _field_relevant_vehicles(session, as_of)

    delivered = {
        str(row["vehicle_id"])
        for row in (
            await session.execute(
                select(deliveries.c.vehicle_id).where(deliveries.c.actual_delivery_date.is_not(None))
            )
        ).mappings().all()
        if row["vehicle_id"]
    }

    rows = (
        await session.execute(
            select(
                telemetry.c.vehicle_id,
                func.count().label("row_count"),
                func.min(telemetry.c.timestamp).label("window_from"),
                func.max(telemetry.c.timestamp).label("window_to"),
            )
            .select_from(
                telemetry.join(deliveries, deliveries.c.vehicle_id == telemetry.c.vehicle_id)
            )
            .where(telemetry.c.timestamp <= source_to, telemetry.c.timestamp >= source_from)
            .where(
                deliveries.c.actual_delivery_date.is_not(None),
                telemetry.c.timestamp >= deliveries.c.actual_delivery_date,
            )
            .group_by(telemetry.c.vehicle_id)
        )
    ).mappings().all()

    in_window = {str(row["vehicle_id"]): row for row in rows}
    eligible: dict[str, int] = {}
    exclusions: dict[str, str] = {}
    for vehicle_id, row in in_window.items():
        row_count = int(row["row_count"])
        if row_count < raw_rows_required:
            exclusions[vehicle_id] = "insufficient_raw_history"
            continue
        if row_count // TELEMATICS_ANALYSIS_MINUTES < panel.min_panel_observations:
            exclusions[vehicle_id] = "insufficient_analytical_rows"
            continue
        eligible[vehicle_id] = row_count

    # Explain every field-relevant vehicle that could not join the cohort.
    for vehicle_id in sorted(field_vehicles):
        if vehicle_id in eligible or vehicle_id in exclusions:
            continue
        if vehicle_id not in delivered:
            exclusions[vehicle_id] = "not_delivered"
        elif vehicle_id not in in_window:
            exclusions[vehicle_id] = "outside_source_window"

    if not eligible:
        raise SourceNotReady(
            "INSUFFICIENT_HISTORY",
            {
                "vehicles_seen": len(in_window),
                "vehicles_eligible": 0,
                "minimum_raw_rows": raw_rows_required,
                "window_from": source_from.isoformat(),
                "window_to": source_to.isoformat(),
                "eligibility_exclusions": exclusions,
            },
        )

    prioritised = sorted(set(eligible) & field_vehicles)
    background = sorted(set(eligible) - field_vehicles)
    max_vehicles = get_settings().telematics_causal_max_vehicles
    selected = [*prioritised, *background][: max(len(prioritised), max_vehicles)]
    vehicle_ids = tuple(sorted(selected))

    signature = stable_source_signature(
        {
            "domain": "telematics",
            "vehicle_ids": vehicle_ids,
            "source_from": source_from,
            "source_to": source_to,
            "row_counts": {vehicle_id: eligible[vehicle_id] for vehicle_id in vehicle_ids},
            "history_hours": TELEMATICS_HISTORY_HOURS,
            "analysis_frequency": panel.analysis_frequency,
        }
    )
    return TelematicsSourcePlan(
        vehicle_ids=vehicle_ids,
        source_from=source_from,
        source_to=source_to,
        history_hours=TELEMATICS_HISTORY_HOURS,
        signature=signature,
        diagnostics={
            "cohort_source": "eligible_field_relevant_plus_background",
            "vehicles_seen": len(in_window),
            "vehicles_eligible": len(eligible),
            "vehicles_selected": len(vehicle_ids),
            "field_relevant_vehicles": sorted(field_vehicles),
            "field_relevant_selected": prioritised,
            "background_selected": [v for v in vehicle_ids if v not in prioritised],
            "eligibility_exclusions": exclusions,
            "minimum_raw_rows": raw_rows_required,
            "minimum_analytical_rows": panel.min_panel_observations,
            "window_from": source_from.isoformat(),
            "window_to": source_to.isoformat(),
            "chronology_filter": "telemetry_at_or_after_actual_delivery",
            "rolling_window_hours": TELEMATICS_HISTORY_HOURS,
        },
    )


# ---------------------------------------------------------------------------
# Domain jobs
# ---------------------------------------------------------------------------


async def _run_manufacturing_job(
    job: AsyncSession, as_of: datetime, now: datetime, force_refresh: bool
) -> bool:
    cursor = await _domain_cursor(job, "manufacturing")
    plan = await build_manufacturing_source_plan(job, as_of, manufacturing_cursor=cursor)
    state = await get_scheduler_state(job, "manufacturing")
    next_refresh = now + timedelta(minutes=get_settings().manufacturing_causal_refresh_minutes)

    settings = get_settings()
    # Resolved via the SAME algorithm-aware function the service itself
    # uses (not a static constant) so the fingerprint can never drift from
    # what get_or_run() actually computes -- LPCMCI's cheap tau_max=2/
    # pc_alpha=0.10 vs. PCMCI rollback's legacy tau_max=12/pc_alpha=0.05.
    tau_max = manufacturing_effective_tau_max(settings.causal_algorithm, None)
    pc_alpha = manufacturing_effective_pc_alpha(settings.causal_algorithm, None)
    analysis_config_signature = _analysis_config_signature(
        domain="manufacturing",
        algorithm=settings.causal_algorithm,
        test_contemporaneous=settings.lpcmci_test_contemporaneous,
        tau_max=tau_max,
        pc_alpha=pc_alpha,
        algorithm_config=None,
        panel_config=DEFAULT_MANUFACTURING_PANEL_CONFIG,
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
    )

    routing = _scheduler_reuse_decision(
        force_refresh=force_refresh,
        state=state,
        source_signature=plan.signature,
        analysis_config_signature=analysis_config_signature,
    )

    if routing.reuse:
        assert state is not None and state.last_run_id is not None
        await update_scheduler_state(
            job,
            "manufacturing",
            status="REUSED",
            now=now,
            next_refresh_at=next_refresh,
            run_id=state.last_run_id,
            source_signature=plan.signature,
            analysis_config_signature=analysis_config_signature,
            source_from=state.last_source_from,
            source_to=state.last_source_to,
            error=None,
            diagnostics={**plan.diagnostics, "decision": routing.decision},
            update_run=True,
        )
        logger.info(
            "causal_run_reused",
            domain="manufacturing",
            run_id=str(state.last_run_id),
            source_signature=plan.signature[:16],
        )
        return False

    decision = routing.decision

    result = await ManufacturingCausalService(job).get_or_run(
        plan.machine_ids,
        history_hours=plan.history_hours,
        analysis_end=plan.analysis_end,
        algorithm=settings.causal_algorithm,
        test_contemporaneous=settings.lpcmci_test_contemporaneous,
        tau_max=tau_max,
        pc_alpha=pc_alpha,
    )
    await update_scheduler_state(
        job,
        "manufacturing",
        status="REUSED" if result.reused else "READY",
        now=now,
        next_refresh_at=next_refresh,
        run_id=result.run_id,
        source_signature=plan.signature,
        analysis_config_signature=analysis_config_signature,
        source_from=result.source_from,
        source_to=result.source_to,
        error=None,
        diagnostics={
            **plan.diagnostics,
            "decision": decision,
            "service_reused": result.reused,
            "service_decision": (
                "compatible_run_reused"
                if result.reused
                else "new_run_computed"
            ),
            "stable_edge_count": result.stable_edge_count,
        },
        update_run=True,
    )
    logger.info(
        "causal_run_completed",
        domain="manufacturing",
        run_id=str(result.run_id),
        reused=result.reused,
        decision=decision,
        stable_edges=result.stable_edge_count,
        machines=len(plan.machine_ids),
        window=f"{plan.source_from.isoformat()}..{plan.source_to.isoformat()}",
    )
    return not result.reused


async def _run_telematics_job(
    job: AsyncSession, as_of: datetime, now: datetime, force_refresh: bool
) -> bool:
    cursor = await _domain_cursor(job, "telematics")
    plan = await build_telematics_source_plan(job, as_of, telematics_cursor=cursor)
    state = await get_scheduler_state(job, "telematics")
    next_refresh = now + timedelta(minutes=get_settings().telematics_causal_refresh_minutes)

    settings = get_settings()
    # See _run_manufacturing_job: resolved via the same algorithm-aware
    # function the service uses, so the fingerprint can never drift.
    tau_max = telematics_effective_tau_max(settings.causal_algorithm, None)
    pc_alpha = telematics_effective_pc_alpha(settings.causal_algorithm, None)
    analysis_config_signature = _analysis_config_signature(
        domain="telematics",
        algorithm=settings.causal_algorithm,
        test_contemporaneous=settings.lpcmci_test_contemporaneous,
        tau_max=tau_max,
        pc_alpha=pc_alpha,
        algorithm_config=None,
        panel_config=DEFAULT_TELEMATICS_PANEL_CONFIG,
        filter_config=DEFAULT_TELEMATICS_FILTER_CONFIG,
    )

    # See _run_manufacturing_job for the full rationale: source and
    # analysis configuration are independent axes, and a fast-path reuse
    # requires both unchanged.
    routing = _scheduler_reuse_decision(
        force_refresh=force_refresh,
        state=state,
        source_signature=plan.signature,
        analysis_config_signature=analysis_config_signature,
    )

    if routing.reuse:
        assert state is not None and state.last_run_id is not None
        await update_scheduler_state(
            job,
            "telematics",
            status="REUSED",
            now=now,
            next_refresh_at=next_refresh,
            run_id=state.last_run_id,
            source_signature=plan.signature,
            analysis_config_signature=analysis_config_signature,
            source_from=state.last_source_from,
            source_to=state.last_source_to,
            error=None,
            diagnostics={**plan.diagnostics, "decision": routing.decision},
            update_run=True,
        )
        logger.info(
            "causal_run_reused",
            domain="telematics",
            run_id=str(state.last_run_id),
            source_signature=plan.signature[:16],
        )
        return False

    decision = routing.decision

    result = await TelematicsCausalService(job).get_or_run(
        plan.vehicle_ids,
        history_hours=plan.history_hours,
        source_from=plan.source_from,
        source_to=plan.source_to,
        algorithm=settings.causal_algorithm,
        test_contemporaneous=settings.lpcmci_test_contemporaneous,
        tau_max=tau_max,
        pc_alpha=pc_alpha,
    )
    await update_scheduler_state(
        job,
        "telematics",
        status="REUSED" if result.reused else "READY",
        now=now,
        next_refresh_at=next_refresh,
        run_id=result.run_id,
        source_signature=plan.signature,
        analysis_config_signature=analysis_config_signature,
        source_from=result.source_from,
        source_to=result.source_to,
        error=None,
        diagnostics={
            **plan.diagnostics,
            "decision": decision,
            "service_reused": result.reused,
            "service_decision": (
                "compatible_run_reused"
                if result.reused
                else "new_run_computed"
            ),
            "stable_edge_count": result.stable_edge_count,
        },
        update_run=True,
    )
    logger.info(
        "causal_run_completed",
        domain="telematics",
        run_id=str(result.run_id),
        reused=result.reused,
        decision=decision,
        stable_edges=result.stable_edge_count,
        vehicles=len(plan.vehicle_ids),
        window=f"{plan.source_from.isoformat()}..{plan.source_to.isoformat()}",
    )
    return not result.reused


DOMAIN_RUNNERS = {
    "manufacturing": _run_manufacturing_job,
    "telematics": _run_telematics_job,
}


async def _service_domain(
    factory: async_sessionmaker[AsyncSession],
    domain_name: str,
    *,
    as_of: datetime,
    current: datetime,
    force_refresh: bool,
) -> None:
    """Service one domain under single flight, then drain a coalesced target."""
    runner = DOMAIN_RUNNERS[domain_name]
    settings = get_settings()
    refresh_minutes = (
        settings.manufacturing_causal_refresh_minutes
        if domain_name == "manufacturing"
        else settings.telematics_causal_refresh_minutes
    )

    async with factory() as job:
        if not await try_advisory_lock_session(job, domain_name):
            await job.rollback()
            async with factory() as pending_session:
                pending_state = await get_scheduler_state(pending_session, domain_name)
                if pending_state is not None:
                    pending_state.pending_refresh = True
                    pending_state.pending_target_watermark = max(
                        pending_state.pending_target_watermark or as_of, as_of
                    )
                    await pending_session.commit()
            logger.info(
                "causal_run_coalesced",
                domain=domain_name,
                target_watermark=as_of.isoformat(),
                reason="domain_run_already_active",
            )
            return

        started = time.perf_counter()
        try:
            state = await get_scheduler_state(job, domain_name)
            if state is not None:
                state.status = "RUNNING"
                state.active_run_started_at = current
                state.active_target_watermark = as_of
                state.pending_refresh = False
                state.pending_target_watermark = None
                await job.commit()

            produced_new_run = await runner(job, as_of, current, force_refresh)

            # Exactly one coalesced follow-up: another tick that arrived while
            # this run was active is serviced now, against the newest data,
            # instead of being queued as its own job.
            state = await get_scheduler_state(job, domain_name)
            pending_target = None
            if state is not None and state.pending_refresh:
                pending_target = utc_now(state.pending_target_watermark or as_of)
                state.pending_refresh = False
                state.pending_target_watermark = None
                await job.commit()
            if pending_target is not None:
                logger.info(
                    "causal_run_coalesced_followup",
                    domain=domain_name,
                    target_watermark=pending_target.isoformat(),
                )
                produced_new_run = (
                    await runner(job, pending_target, current, False) or produced_new_run
                )

            if produced_new_run:
                try:
                    await evaluate_and_persist(job, now=current)
                except Exception as warning_exc:  # noqa: BLE001 - causal success survives evaluator failure
                    logger.exception(
                        "warning_evaluation_after_causal_failed",
                        domain=domain_name,
                        error=str(warning_exc),
                    )

            elapsed = time.perf_counter() - started
            state = await get_scheduler_state(job, domain_name)
            if state is not None:
                state.active_run_started_at = None
                state.active_target_watermark = None
                state.last_runtime_seconds = elapsed
                state.last_completed_at = current
                await job.commit()
        except SourceNotReady as exc:
            await job.rollback()
            async with factory() as status_session:
                await update_scheduler_state(
                    status_session,
                    domain_name,
                    status="NOT_READY",
                    now=current,
                    next_refresh_at=current + timedelta(minutes=refresh_minutes),
                    error=str(exc),
                    diagnostics=exc.diagnostics,
                    runtime_seconds=time.perf_counter() - started,
                    clear_active=True,
                )
            logger.info(
                "causal_run_not_ready",
                domain=domain_name,
                reason=str(exc),
                diagnostics=exc.diagnostics,
            )
        except Exception as exc:  # noqa: BLE001 - one domain failure must not stop the other
            await job.rollback()
            async with factory() as status_session:
                # The previous completed run and its persisted edges remain the
                # served graph; a failed refresh never empties it.
                await update_scheduler_state(
                    status_session,
                    domain_name,
                    status="ERROR",
                    now=current,
                    next_refresh_at=current + timedelta(minutes=refresh_minutes),
                    error=str(exc)[:2000],
                    runtime_seconds=time.perf_counter() - started,
                    clear_active=True,
                )
            logger.exception("causal_run_failed", domain=domain_name, error=str(exc))
        finally:
            await release_advisory_lock(job, domain_name)


async def run_scheduler_once(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    now: datetime | None = None,
    advance: bool = False,
    domain: str = "all",
    force_refresh: bool = False,
) -> None:
    """Check every requested domain's source signature and service what changed."""
    factory = session_factory or get_session_factory()
    current = utc_now(now)
    async with factory() as clock_session:
        if advance:
            replay = await advance_replay_clock(clock_session, now=current)
        else:
            replay = await get_replay_state(clock_session, initialize=True, now=current)
        assert replay is not None
        await ensure_scheduler_states(clock_session)
        as_of = utc_now(replay.simulation_as_of)

    requested = [name for name in DOMAIN_RUNNERS if domain in {"all", name}]
    for domain_name in requested:
        await _service_domain(
            factory,
            domain_name,
            as_of=as_of,
            current=current,
            force_refresh=force_refresh,
        )


async def scheduler_loop(domain: str | None = None) -> None:
    settings = get_settings()
    if not settings.causal_scheduler_enabled:
        logger.info("causal_scheduler_disabled")
        return
    target = domain or settings.causal_scheduler_domain
    logger.info(
        "causal_scheduler_started",
        poll_seconds=settings.causal_scheduler_poll_seconds,
        domain=target,
    )
    while True:
        try:
            await run_scheduler_once(domain=target)
        except Exception as exc:  # noqa: BLE001 — loop must survive transient DB failures
            logger.exception("causal_scheduler_iteration_failed", error=str(exc))
        await asyncio.sleep(settings.causal_scheduler_poll_seconds)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Run one scheduler iteration and exit.")
    parser.add_argument("--domain", choices=("all", "manufacturing", "telematics"), default=None)
    parser.add_argument(
        "--no-advance",
        action="store_true",
        help="Inspect/refresh without advancing the replay clock.",
    )
    parser.add_argument(
        "--advance",
        action="store_true",
        help="Legacy/manual mode: advance the replay clock in this process.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Run due domains immediately even if the signature is unchanged.",
    )
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    if args.once:
        await run_scheduler_once(
            advance=args.advance and not args.no_advance,
            domain=args.domain or "all",
            force_refresh=args.force_refresh,
        )
        return
    await scheduler_loop(args.domain)


if __name__ == "__main__":
    asyncio.run(_main())
