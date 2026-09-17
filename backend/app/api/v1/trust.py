"""Compliance Trust Ledger endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.trust import (
    ComplianceRuleOut,
    LineageStepOut,
    RejectDecisionIn,
    TrustDecisionOut,
)
from app.services import TrustService

router = APIRouter()


@router.get("/decisions", response_model=list[TrustDecisionOut], summary="Audited AI decision rows")
async def list_decisions(db: Annotated[AsyncSession, Depends(get_db)]) -> list[TrustDecisionOut]:
    return await TrustService(db).list_decisions()


@router.get("/compliance-rules", response_model=list[ComplianceRuleOut], summary="Compliance rule checks")
async def list_rules(db: Annotated[AsyncSession, Depends(get_db)]) -> list[ComplianceRuleOut]:
    return await TrustService(db).list_rules()


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
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TrustDecisionOut:
    return await TrustService(db).escalate_decision(decision_code)
