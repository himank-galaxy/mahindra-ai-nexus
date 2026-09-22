"""Compliance Trust Ledger endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.trust import (
    AuditEventOut,
    ComplianceCheckOut,
    EscalateDecisionIn,
    ExplanationOut,
    LineageStepOut,
    OutcomeOut,
    RejectDecisionIn,
    TrustDecisionOut,
)
from app.services import TrustService

router = APIRouter()


@router.get("/decisions", response_model=list[TrustDecisionOut], summary="Audited AI decision rows")
async def list_decisions(db: Annotated[AsyncSession, Depends(get_db)]) -> list[TrustDecisionOut]:
    return await TrustService(db).list_decisions()


@router.get(
    "/decisions/{decision_code}/compliance",
    response_model=list[ComplianceCheckOut],
    summary="Real per-decision compliance rule results",
)
async def get_compliance(
    decision_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ComplianceCheckOut]:
    return await TrustService(db).get_compliance(decision_code)


@router.get(
    "/decisions/{decision_code}/explanation",
    response_model=ExplanationOut,
    summary="Why this recommendation was made, grounded in its own evidence",
)
async def get_explanation(
    decision_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExplanationOut:
    return await TrustService(db).get_explanation(decision_code)


@router.get(
    "/decisions/{decision_code}/lineage",
    response_model=list[LineageStepOut],
    summary="Six-step decision lineage",
)
async def get_lineage(
    decision_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[LineageStepOut]:
    return await TrustService(db).get_lineage(decision_code)


@router.get(
    "/decisions/{decision_code}/events",
    response_model=list[AuditEventOut],
    summary="Real, chronological, append-only decision history",
)
async def get_events(
    decision_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AuditEventOut]:
    return await TrustService(db).get_events(decision_code)


@router.get(
    "/decisions/{decision_code}/outcome",
    response_model=OutcomeOut,
    summary="Real observed/expected outcome, or a clear pending state",
)
async def get_outcome(
    decision_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OutcomeOut:
    return await TrustService(db).get_outcome(decision_code)


@router.post("/decisions/{decision_code}/approve", response_model=TrustDecisionOut, summary="Approve decision")
async def approve_decision(
    decision_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TrustDecisionOut:
    return await TrustService(db).approve_decision(decision_code)


@router.post("/decisions/{decision_code}/reject", response_model=TrustDecisionOut, summary="Reject decision")
async def reject_decision(
    decision_code: str,
    payload: RejectDecisionIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TrustDecisionOut:
    return await TrustService(db).reject_decision(decision_code, payload.reason)


@router.post("/decisions/{decision_code}/escalate", response_model=TrustDecisionOut, summary="Escalate decision")
async def escalate_decision(
    decision_code: str,
    payload: EscalateDecisionIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TrustDecisionOut:
    return await TrustService(db).escalate_decision(decision_code, payload.reviewer_role, payload.reason)
