"""Collections & Recovery AI Swarm endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.collections import (
    CaseTrustLedgerOut,
    CollectionsAgentOut,
    CollectionsCaseOut,
    MetricTileOut,
    ModifyActionIn,
)
from app.schemas.trust import EscalateDecisionIn
from app.services import CollectionsService

router = APIRouter()


@router.get("/metrics", response_model=list[MetricTileOut], summary="Headline metric tiles")
async def list_metrics(db: Annotated[AsyncSession, Depends(get_db)]) -> list[MetricTileOut]:
    return await CollectionsService(db).list_metrics()


@router.get("/agents", response_model=list[CollectionsAgentOut], summary="Swarm agents")
async def list_agents(db: Annotated[AsyncSession, Depends(get_db)]) -> list[CollectionsAgentOut]:
    return await CollectionsService(db).list_agents()


@router.get("/cases", response_model=list[CollectionsCaseOut], summary="Prioritized case rows")
async def list_cases(db: Annotated[AsyncSession, Depends(get_db)]) -> list[CollectionsCaseOut]:
    return await CollectionsService(db).list_cases()


@router.post("/cases/{case_id}/approve", response_model=CollectionsCaseOut, summary="Approve the AI recommendation")
async def approve_case(
    case_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CollectionsCaseOut:
    return await CollectionsService(db).approve_case(case_id)


@router.post(
    "/cases/{case_id}/modify",
    response_model=CollectionsCaseOut,
    summary="Approve with a human-modified channel/offer",
)
async def modify_case(
    case_id: uuid.UUID,
    payload: ModifyActionIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CollectionsCaseOut:
    return await CollectionsService(db).modify_case(case_id, payload.channel, payload.offer, payload.reason)


@router.post("/cases/{case_id}/review", response_model=CollectionsCaseOut, summary="Send case to human review")
async def review_case(
    case_id: uuid.UUID,
    payload: EscalateDecisionIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CollectionsCaseOut:
    return await CollectionsService(db).review_case(case_id, payload.reviewer_role, payload.reason)


@router.get(
    "/cases/{case_id}/ledger",
    response_model=CaseTrustLedgerOut,
    summary="Real compliance/approval/outcome state for a case",
)
async def get_case_trust_ledger(
    case_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CaseTrustLedgerOut:
    return await CollectionsService(db).get_case_trust_ledger(case_id)
