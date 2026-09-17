"""Warranty, Quality & Service Early-Warning Graph endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.database.runtime_schema import runtime_tables
from app.models.causal_runtime_state import CausalIngestionState
from app.models.manufacturing_causal_state import ManufacturingCausalRun
from app.models.telematics_causal_state import TelematicsCausalRun
from app.models.warning_runtime_state import WarrantyQualityEvaluationRun
from app.schemas.warranty_quality import (
    CausalDataFreshnessOut,
    CausalGraphDeltaOut,
    CausalIngestionStatusOut,
    CausalRunStatusOut,
    CausalSchedulerStatusOut,
    CausalSimulationStatusOut,
    CausalWarningStatusOut,
    WarrantyQualityCausalStatusOut,
    WarrantyQualityEarlyWarningOut,
)
from app.services.causal_runtime import get_graph_delta, get_replay_state, get_scheduler_state
from app.services.live_ingestion import INGESTION_SOURCES, runtime_count, runtime_max
from app.services.warranty_quality_early_warning import (
    WarrantyQualityEarlyWarningService,
)
from app.services.warranty_quality_evaluation import get_latest_snapshot

router = APIRouter()


@router.get(
    "/early-warnings",
    response_model=WarrantyQualityEarlyWarningOut,
    summary="Warranty and quality causal early warnings",
    description=(
        "Returns issue-category early warnings backed by observed service "
        "and warranty evidence, exact manufacturing lineage inside the "
        "selected causal-run source window, and persisted stable PCMCI "
        "causal candidates. Causal scores are statistical evidence and "
        "must not be interpreted as causal probabilities."
    ),
)
async def get_early_warnings(
    db: Annotated[
        AsyncSession,
        Depends(get_db),
    ],
    run_id: Annotated[
        UUID | None,
        Query(
            description=(
                "Optional persisted manufacturing causal-run ID. "
                "When omitted, the latest persisted manufacturing "
                "causal run is used."
            )
        ),
    ] = None,
    telematics_run_id: Annotated[
        UUID | None,
        Query(
            description=(
                "Optional persisted telematics causal-run ID. "
                "When omitted, the latest persisted telematics "
                "causal run is used when available."
            )
        ),
    ] = None,
) -> WarrantyQualityEarlyWarningOut:
    """Return exact-lineage warranty/quality early-warning evidence."""

    replay_state = await get_replay_state(db, initialize=False)
    snapshot = await get_latest_snapshot(db, run_id=run_id, telematics_run_id=telematics_run_id)
    if snapshot is not None:
        return WarrantyQualityEarlyWarningOut.model_validate(snapshot)
    result = await WarrantyQualityEarlyWarningService(
        db
    ).get_warnings(
        run_id=run_id,
        telematics_run_id=telematics_run_id,
        simulation_as_of=(replay_state.simulation_as_of if replay_state is not None else None),
    )

    if result is None:
        if run_id is None:
            raise NotFoundError(
                "No persisted manufacturing causal run was found.",
                code="manufacturing_causal_run_not_found",
            )

        raise NotFoundError(
            f"Manufacturing causal run '{run_id}' was not found.",
            code="manufacturing_causal_run_not_found",
        )

    if (
        telematics_run_id is not None
        and result.telematics_causal_run_id != telematics_run_id
    ):
        raise NotFoundError(
            f"Telematics causal run '{telematics_run_id}' was not found.",
            code="telematics_causal_run_not_found",
        )

    return WarrantyQualityEarlyWarningOut.model_validate(
        result
    )


async def _data_freshness(
    db: AsyncSession,
    *,
    source: str,
    observed_at: datetime | None,
    simulation_as_of: datetime,
) -> CausalDataFreshnessOut:
    age = None
    if observed_at is not None:
        age = max(0.0, (simulation_as_of - observed_at).total_seconds() / 60.0)
    return CausalDataFreshnessOut(
        source=source,
        observed_at=observed_at,
        age_minutes=age,
        status="AVAILABLE" if observed_at is not None else "NOT_AVAILABLE",
    )


@router.get(
    "/causal-status",
    response_model=WarrantyQualityCausalStatusOut,
    summary="Replay and causal pipeline status",
    description="Read-only replay watermark, source freshness, persisted causal runs, graph deltas, and scheduler checkpoints.",
)
async def get_causal_status(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WarrantyQualityCausalStatusOut:
    """Return dynamic causal status without triggering PCMCI."""
    state = await get_replay_state(db, initialize=True)
    assert state is not None
    settings = get_settings()
    tables = runtime_tables
    as_of = state.simulation_as_of

    observed_queries = {
        "manufacturing": select(func.max(tables["manufacturing_timeseries"].c.timestamp)).where(tables["manufacturing_timeseries"].c.timestamp <= as_of),
        "telematics": select(func.max(tables["vehicle_telematics_timeseries"].c.timestamp)).where(tables["vehicle_telematics_timeseries"].c.timestamp <= as_of),
        "service": select(func.max(tables["service_events"].c.service_started_at)).where(tables["service_events"].c.service_started_at <= as_of),
        "warranty": select(func.max(tables["warranty_claims"].c.claim_submitted_at)).where(tables["warranty_claims"].c.claim_submitted_at <= as_of),
    }
    observed = {name: (await db.execute(query)).scalar_one_or_none() for name, query in observed_queries.items()}
    freshness = tuple(
        [
            await _data_freshness(db, source=name, observed_at=value, simulation_as_of=as_of)
            for name, value in observed.items()
        ]
    )

    async def domain_status(domain: str) -> CausalRunStatusOut:
        scheduler_state = await get_scheduler_state(db, domain)
        model = ManufacturingCausalRun if domain == "manufacturing" else TelematicsCausalRun
        run = None
        if scheduler_state is not None and scheduler_state.last_run_id is not None:
            run = (await db.execute(select(model).where(model.id == scheduler_state.last_run_id))).scalar_one_or_none()
        if run is None:
            run = (await db.execute(select(model).order_by(model.computed_at.desc(), model.id.desc()).limit(1))).scalar_one_or_none()
        delta = await get_graph_delta(db, domain, run_id=(run.id if run is not None else None))
        run_freshness = await _data_freshness(db, source=domain, observed_at=observed[domain], simulation_as_of=as_of)
        return CausalRunStatusOut(
            domain=domain,
            status=(scheduler_state.status if scheduler_state is not None else "NOT_READY"),
            run_id=(run.id if run is not None else None),
            signature=(run.signature if run is not None else None),
            computed_at=(run.computed_at if run is not None else None),
            source_from=(run.source_from if run is not None else None),
            source_to=(run.source_to if run is not None else None),
            source_rows=(int(run.source_rows) if run is not None else None),
            stable_edge_count=(int(run.stable_edge_count) if run is not None else None),
            data_freshness=run_freshness,
            model_freshness=(run.computed_at if run is not None else None),
            graph_delta=CausalGraphDeltaOut.model_validate(delta),
            last_refresh_at=(scheduler_state.last_refresh_at if scheduler_state is not None else None),
            next_refresh_at=(scheduler_state.next_refresh_at if scheduler_state is not None else None),
            last_error=(scheduler_state.last_error if scheduler_state is not None else None),
            diagnostics=(scheduler_state.last_diagnostics or {} if scheduler_state is not None else {}),
            active_run_started_at=(scheduler_state.active_run_started_at if scheduler_state is not None else None),
            active_target_watermark=(scheduler_state.active_target_watermark if scheduler_state is not None else None),
            pending_refresh=(scheduler_state.pending_refresh if scheduler_state is not None else False),
            pending_target_watermark=(scheduler_state.pending_target_watermark if scheduler_state is not None else None),
            last_runtime_seconds=(scheduler_state.last_runtime_seconds if scheduler_state is not None else None),
            last_completed_at=(scheduler_state.last_completed_at if scheduler_state is not None else None),
        )

    manufacturing_status = await domain_status("manufacturing")
    telematics_status = await domain_status("telematics")
    next_refreshes = [value for value in (manufacturing_status.next_refresh_at, telematics_status.next_refresh_at) if value is not None]
    scheduler_last = [value for value in (manufacturing_status.last_refresh_at, telematics_status.last_refresh_at) if value is not None]
    ingestion_states = list((await db.execute(select(CausalIngestionState).order_by(CausalIngestionState.domain))).scalars())
    ingestion_status_rows: list[CausalIngestionStatusOut] = []
    for row in ingestion_states:
        # Physical proof, read straight off the runtime table rather than from
        # the checkpoint, so the panel cannot claim growth that did not happen.
        source = INGESTION_SOURCES[row.domain]
        runtime_row_count = await runtime_count(db, source["source_table"])
        runtime_max_timestamp = await runtime_max(db, source["source_table"], source["time_column"])
        ingestion_status_rows.append(
            CausalIngestionStatusOut(
                domain=row.domain,
                source_table=row.source_table,
                status=row.status,
                source_available_from=row.source_available_from,
                source_available_to=row.source_available_to,
                replay_start=row.replay_start,
                replay_cursor=row.replay_cursor,
                initialized_at=row.initialized_at,
                exhausted_at=row.exhausted_at,
                last_tick_at=row.last_tick_at,
                tick_count=int(row.tick_count or 0),
                last_ingested_timestamp=row.last_ingested_timestamp,
                last_ingested_rows=row.last_ingested_rows,
                rows_ingested_total=row.rows_ingested_total,
                runtime_row_count=runtime_row_count,
                runtime_max_timestamp=runtime_max_timestamp,
                last_commit_at=row.last_commit_at,
                last_error=row.last_error,
                diagnostics=row.diagnostics or {},
            )
        )
    ingestion_status = tuple(ingestion_status_rows)
    evaluation = (await db.execute(select(WarrantyQualityEvaluationRun).order_by(WarrantyQualityEvaluationRun.computed_at.desc()).limit(1))).scalar_one_or_none()
    warning_status = CausalWarningStatusOut(
        status=(evaluation.status if evaluation is not None else "NOT_READY"),
        evaluation_run_id=(evaluation.id if evaluation is not None else None),
        evaluation_signature=(evaluation.evaluation_signature if evaluation is not None else None),
        field_evidence_signature=(evaluation.field_evidence_signature if evaluation is not None else None),
        manufacturing_causal_run_id=(evaluation.manufacturing_causal_run_id if evaluation is not None else None),
        telematics_causal_run_id=(evaluation.telematics_causal_run_id if evaluation is not None else None),
        computed_at=(evaluation.computed_at if evaluation is not None else None),
        last_evaluated_at=(evaluation.last_evaluated_at if evaluation is not None else None),
        warning_count=(evaluation.warning_count if evaluation is not None else 0),
        lifecycle_counts=(evaluation.lifecycle_counts if evaluation is not None else {}),
        runtime_seconds=(evaluation.runtime_seconds if evaluation is not None else None),
        last_error=(evaluation.last_error if evaluation is not None else None),
    )
    simulation_status = "COMPLETE" if as_of >= state.replay_end else ("PAUSED" if state.paused else "RUNNING")
    return WarrantyQualityCausalStatusOut(
        simulation=CausalSimulationStatusOut(
            simulation_as_of=as_of,
            replay_start=state.replay_start,
            replay_end=state.replay_end,
            replay_speed=state.replay_speed,
            paused=state.paused,
            status=simulation_status,
            last_tick_at=state.last_tick_at,
            tick_count=state.tick_count,
        ),
        data_freshness=freshness,
        ingestion=ingestion_status,
        manufacturing=manufacturing_status,
        telematics=telematics_status,
        warning=warning_status,
        scheduler=CausalSchedulerStatusOut(
            enabled=settings.causal_scheduler_enabled,
            last_refresh_at=max(scheduler_last) if scheduler_last else None,
            next_refresh_at=min(next_refreshes) if next_refreshes else None,
            status="RUNNING" if settings.causal_scheduler_enabled else "DISABLED",
        ),
    )
