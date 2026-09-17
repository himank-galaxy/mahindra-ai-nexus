"""Collections & Recovery AI Swarm endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.collections import (
    CollectionsAgentOut,
    CollectionsCaseOut,
    MetricTileOut,
    ModifyActionIn,
)
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


@router.post("/cases/{case_id}/approve", response_model=CollectionsCaseOut, summary="Approve case action")
async def approve_case(
    case_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CollectionsCaseOut:
    return await CollectionsService(db).approve_case(case_id)


@router.post("/cases/{case_id}/modify", response_model=CollectionsCaseOut, summary="Replace case action")
async def modify_case(
    case_id: uuid.UUID,
    payload: ModifyActionIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CollectionsCaseOut:
    return await CollectionsService(db).modify_case(case_id, payload.action)


@router.post("/cases/{case_id}/review", response_model=CollectionsCaseOut, summary="Send case to human review")
async def review_case(
    case_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CollectionsCaseOut:
    return await CollectionsService(db).review_case(case_id)


@router.get("/cases/{case_id}/ledger", response_model=list[str], summary="Trust-trail steps for a case")
async def get_case_ledger(
    case_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[str]:
    return await CollectionsService(db).get_case_ledger(case_id)
