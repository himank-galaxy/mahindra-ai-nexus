"""Persisted deterministic warning evaluation and lifecycle transitions."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.manufacturing_causal_state import ManufacturingCausalRun
from app.models.telematics_causal_state import TelematicsCausalRun
from app.models.warning_runtime_state import (
    WarrantyQualityEvaluationRun,
    WarrantyQualityWarning,
    WarrantyQualityWarningEvent,
)
from app.schemas.warranty_quality import WarrantyQualityEarlyWarningOut
from app.services.causal_runtime import try_advisory_lock, utc_now
from app.services.warranty_quality_early_warning import WarrantyQualityEarlyWarningService

logger = get_logger(__name__)

LIFECYCLE_STATES = frozenset({"NEW", "ACTIVE", "ESCALATED", "DEESCALATED", "RESOLVED", "UNCHANGED"})
PRIORITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

#: Each evaluation stores a full warning snapshot, and live field evidence
#: mints a new one whenever it materially moves. Retaining the newest window
#: keeps the audit trail useful without letting the table grow unbounded. The
#: per-warning lifecycle rows and transition events are never pruned.
EVALUATION_RETENTION = 200


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evaluation_signature(
    *,
    manufacturing_signature: str,
    telematics_signature: str | None,
    field_evidence_signature: str,
) -> str:
    """Identify one logical evaluation by what it was actually derived from.

    Deliberately excludes the wall/simulation clock.  Keying on time would mint
    a fresh evaluation every minute even when nothing material moved, which is
    what produces duplicate-looking warning history.  A new evaluation appears
    only when a causal run or the field evidence genuinely changes.
    """
    return _canonical_hash(
        {
            "manufacturing_signature": manufacturing_signature,
            "telematics_signature": telematics_signature,
            "field_evidence_signature": field_evidence_signature,
            # Bumped for the LPCMCI edge-orientation fields added to
            # CausalPathSupportOut/EvidenceGraphEdgeOut -- a real evidentiary
            # content change (old snapshots would be missing these fields
            # entirely, not just defaulted), so old snapshots must not be
            # reused as-is.
            "evaluator_version": "live-warning-v3",
        }
    )


async def field_evidence_signature(session: AsyncSession, as_of: datetime) -> str:
    """Fingerprint the visible complaint/service/warranty evidence.

    Counts plus newest timestamps are enough to detect that material field
    evidence moved, without hashing every row on every tick.
    """
    from app.database.runtime_schema import runtime_tables

    tables = runtime_tables
    service = tables["service_events"]
    warranty = tables["warranty_claims"]
    service_row = (
        await session.execute(
            select(
                func.count().label("events"),
                func.max(service.c.service_started_at).label("newest"),
                func.count(service.c.issue_category).label("categorised"),
            ).where(service.c.service_started_at <= as_of)
        )
    ).mappings().one()
    warranty_row = (
        await session.execute(
            select(
                func.count().label("claims"),
                func.max(warranty.c.claim_submitted_at).label("newest"),
                func.count(warranty.c.issue_category).label("categorised"),
            ).where(warranty.c.claim_submitted_at <= as_of)
        )
    ).mappings().one()
    return _canonical_hash(
        {
            "service_events": int(service_row["events"]),
            "service_categorised": int(service_row["categorised"]),
            "service_newest": service_row["newest"],
            "warranty_claims": int(warranty_row["claims"]),
            "warranty_categorised": int(warranty_row["categorised"]),
            "warranty_newest": warranty_row["newest"],
        }
    )


def _warning_payload(warning: dict[str, Any]) -> dict[str, Any]:
    payload = dict(warning)
    for key in ("lifecycle_state", "warning_signature", "first_seen_at", "last_seen_at", "last_transition_at"):
        payload.pop(key, None)
    return payload


def warning_signature(warning: dict[str, Any]) -> str:
    return _canonical_hash(_warning_payload(warning))


def _next_state(previous: WarrantyQualityWarning | None, current: dict[str, Any], signature: str) -> str:
    if previous is None or previous.lifecycle_state == "RESOLVED":
        return "NEW"
    if previous.warning_signature == signature:
        return "UNCHANGED"
    old_priority = PRIORITY_RANK.get(str((previous.payload or {}).get("priority", "LOW")), 3)
    new_priority = PRIORITY_RANK.get(str(current.get("priority", "LOW")), 3)
    if new_priority < old_priority:
        return "ESCALATED"
    if new_priority > old_priority:
        return "DEESCALATED"
    return "ACTIVE"


async def _latest_run(session: AsyncSession, model: Any, domain: str) -> Any:
    """Return the causal run the scheduler currently considers active.

    The scheduler's ``last_run_id`` is authoritative, not ``max(computed_at)``.
    When a plan resolves to an already-persisted run the service legitimately
    reuses it, so the active run can be older than some other completed run;
    ordering by timestamp would then serve a run the scheduler has moved off.
    Falls back to the newest completed run when no scheduler state exists yet.
    """
    from app.models.causal_runtime_state import CausalSchedulerState

    state = await session.get(CausalSchedulerState, domain)
    if state is not None and state.last_run_id is not None:
        active = await session.get(model, state.last_run_id)
        if active is not None:
            return active
    return (
        await session.execute(select(model).order_by(model.computed_at.desc(), model.id.desc()).limit(1))
    ).scalar_one_or_none()


async def evaluate_and_persist(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> WarrantyQualityEvaluationRun | None:
    """Evaluate only completed causal runs and atomically persist lifecycle state."""

    current = utc_now(now)
    if not await try_advisory_lock(session, "warning-evaluator"):
        await session.rollback()
        logger.info("warning_evaluation_skipped", reason="already_running")
        return None

    manufacturing = await _latest_run(session, ManufacturingCausalRun, "manufacturing")
    if manufacturing is None:
        await session.rollback()
        return None
    telematics = await _latest_run(session, TelematicsCausalRun, "telematics")
    replay_as_of = manufacturing.source_to
    from app.models.causal_runtime_state import CausalReplayState

    replay = await session.get(CausalReplayState, "default")
    if replay is not None:
        replay_as_of = replay.simulation_as_of

    from app.models.causal_runtime_state import CausalIngestionState

    manufacturing_state = await session.get(CausalIngestionState, "manufacturing")
    telematics_state = await session.get(CausalIngestionState, "telematics")
    manufacturing_cursor = manufacturing_state.replay_cursor if manufacturing_state else None
    telematics_cursor = telematics_state.replay_cursor if telematics_state else None

    evidence_signature = await field_evidence_signature(session, replay_as_of)
    signature = evaluation_signature(
        manufacturing_signature=manufacturing.signature,
        telematics_signature=telematics.signature if telematics is not None else None,
        field_evidence_signature=evidence_signature,
    )
    started = time.perf_counter()
    result = await WarrantyQualityEarlyWarningService(session).get_warnings(
        run_id=manufacturing.id,
        telematics_run_id=telematics.id if telematics is not None else None,
        simulation_as_of=replay_as_of,
    )
    if result is None:
        await session.rollback()
        return None

    snapshot = WarrantyQualityEarlyWarningOut.model_validate(result).model_dump(mode="json")
    existing_run = (
        await session.execute(
            select(WarrantyQualityEvaluationRun)
            .where(WarrantyQualityEvaluationRun.evaluation_signature == signature)
            .with_for_update()
        )
    ).scalar_one_or_none()
    evaluation = existing_run or WarrantyQualityEvaluationRun(
        id=uuid.uuid4(),
        evaluation_signature=signature,
        status="READY",
        simulation_as_of=replay_as_of,
        manufacturing_causal_run_id=manufacturing.id,
        telematics_causal_run_id=telematics.id if telematics is not None else None,
        field_evidence_signature=evidence_signature,
        manufacturing_cursor=manufacturing_cursor,
        telematics_cursor=telematics_cursor,
        warning_count=0,
        lifecycle_counts={},
        snapshot={},
        computed_at=current,
        last_evaluated_at=current,
    )
    if existing_run is None:
        session.add(evaluation)

    warning_rows = list(
        (
            await session.execute(
                select(WarrantyQualityWarning).with_for_update()
            )
        ).scalars()
    )
    previous_by_key = {row.warning_key: row for row in warning_rows}
    lifecycle_counts: dict[str, int] = {}
    seen_keys: set[str] = set()
    snapshot_warnings: list[dict[str, Any]] = []

    for raw_warning in snapshot.get("warnings", []):
        warning = dict(raw_warning)
        key = str(warning["issue_category"])[:128]
        seen_keys.add(key)
        sig = warning_signature(warning)
        previous = previous_by_key.get(key)
        state = _next_state(previous, warning, sig)
        lifecycle_counts[state] = lifecycle_counts.get(state, 0) + 1
        enriched = {
            **warning,
            "lifecycle_state": state,
            "warning_signature": sig,
            "first_seen_at": (previous.first_seen_at.isoformat() if previous is not None else current.isoformat()),
            "last_seen_at": current.isoformat(),
            "last_transition_at": (
                current.isoformat()
                if previous is None or state != "UNCHANGED"
                else previous.last_transition_at.isoformat()
            ),
        }
        snapshot_warnings.append(enriched)
        if previous is None:
            row = WarrantyQualityWarning(
                warning_key=key,
                warning_signature=sig,
                issue_category=key,
                lifecycle_state=state,
                first_seen_at=current,
                last_seen_at=current,
                last_transition_at=current,
                last_evaluation_id=evaluation.id,
                payload=enriched,
            )
            session.add(row)
        else:
            previous_state = previous.lifecycle_state
            previous.warning_signature = sig
            previous.lifecycle_state = state
            previous.last_seen_at = current
            previous.last_evaluation_id = evaluation.id
            previous.payload = enriched
            previous.resolved_at = None
            if state != "UNCHANGED":
                previous.last_transition_at = current
            if state != "UNCHANGED":
                session.add(
                    WarrantyQualityWarningEvent(
                        warning_key=key,
                        evaluation_id=evaluation.id,
                        previous_state=previous_state,
                        new_state=state,
                        warning_signature=sig,
                        event_at=current,
                        payload=enriched,
                    )
                )
        if previous is None:
            session.add(
                WarrantyQualityWarningEvent(
                    warning_key=key,
                    evaluation_id=evaluation.id,
                    previous_state=None,
                    new_state=state,
                    warning_signature=sig,
                    event_at=current,
                    payload=enriched,
                )
            )

    for row in warning_rows:
        if row.warning_key in seen_keys or row.lifecycle_state == "RESOLVED":
            continue
        previous_state = row.lifecycle_state
        row.lifecycle_state = "RESOLVED"
        row.resolved_at = current
        row.last_transition_at = current
        row.last_evaluation_id = evaluation.id
        lifecycle_counts["RESOLVED"] = lifecycle_counts.get("RESOLVED", 0) + 1
        session.add(
            WarrantyQualityWarningEvent(
                warning_key=row.warning_key,
                evaluation_id=evaluation.id,
                previous_state=previous_state,
                new_state="RESOLVED",
                warning_signature=row.warning_signature,
                event_at=current,
                payload=row.payload,
            )
        )

    snapshot["warnings"] = snapshot_warnings
    snapshot["warnings_generated"] = len(snapshot_warnings)
    evaluation.status = "READY"
    evaluation.simulation_as_of = replay_as_of
    evaluation.manufacturing_causal_run_id = manufacturing.id
    evaluation.telematics_causal_run_id = telematics.id if telematics is not None else None
    evaluation.field_evidence_signature = evidence_signature
    evaluation.manufacturing_cursor = manufacturing_cursor
    evaluation.telematics_cursor = telematics_cursor
    evaluation.warning_count = len(snapshot_warnings)
    evaluation.lifecycle_counts = lifecycle_counts
    evaluation.snapshot = snapshot
    evaluation.last_evaluated_at = current
    evaluation.runtime_seconds = time.perf_counter() - started
    evaluation.last_error = None
    await _prune_evaluations(session, keep_id=evaluation.id)
    await session.commit()
    logger.info(
        "warning_evaluation_completed",
        evaluation_signature=signature,
        warning_count=len(snapshot_warnings),
        lifecycle_counts=lifecycle_counts,
        runtime_seconds=evaluation.runtime_seconds,
    )
    return evaluation


async def _prune_evaluations(session: AsyncSession, *, keep_id: uuid.UUID) -> None:
    """Drop evaluation snapshots older than the retention window.

    Only the snapshot history is pruned. The per-warning lifecycle rows and
    their transition events are the durable record and are never removed.
    """
    survivors = (
        await session.execute(
            select(WarrantyQualityEvaluationRun.id)
            .order_by(
                WarrantyQualityEvaluationRun.last_evaluated_at.desc(),
                WarrantyQualityEvaluationRun.id.desc(),
            )
            .limit(EVALUATION_RETENTION)
        )
    ).scalars().all()
    keep = {keep_id, *survivors}
    await session.execute(
        delete(WarrantyQualityEvaluationRun).where(
            WarrantyQualityEvaluationRun.id.not_in(list(keep))
        )
    )


async def get_latest_snapshot(
    session: AsyncSession,
    *,
    run_id: uuid.UUID | None = None,
    telematics_run_id: uuid.UUID | None = None,
) -> dict[str, Any] | None:
    query = select(WarrantyQualityEvaluationRun).where(WarrantyQualityEvaluationRun.status == "READY")
    if run_id is not None:
        query = query.where(WarrantyQualityEvaluationRun.manufacturing_causal_run_id == run_id)
    if telematics_run_id is not None:
        query = query.where(WarrantyQualityEvaluationRun.telematics_causal_run_id == telematics_run_id)
    row = (
        await session.execute(query.order_by(WarrantyQualityEvaluationRun.computed_at.desc()).limit(1))
    ).scalar_one_or_none()
    return dict(row.snapshot) if row is not None and row.snapshot else None


__all__ = [
    "evaluate_and_persist",
    "evaluation_signature",
    "field_evidence_signature",
    "get_latest_snapshot",
    "warning_signature",
]
