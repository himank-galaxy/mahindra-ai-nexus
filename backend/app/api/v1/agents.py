"""AI Factory endpoints: agent registry and XR experiences."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.agent import AiAgentOut, WorkflowRunOut, XrExperienceOut
from app.services import AiAgentService

router = APIRouter()
xr_router = APIRouter()


@router.get("", response_model=list[AiAgentOut], summary="Registered agents")
async def list_agents(db: Annotated[AsyncSession, Depends(get_db)]) -> list[AiAgentOut]:
    return await AiAgentService(db).list_agents()


@router.get("/{agent_id}", response_model=AiAgentOut, summary="Inspect one agent")
async def get_agent(
    agent_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AiAgentOut:
    return await AiAgentService(db).get_agent(agent_id)


@router.post("/workflow/run", response_model=WorkflowRunOut, summary="Staged agent collaboration flow")
async def run_workflow() -> WorkflowRunOut:
    return AiAgentService.run_workflow()


@xr_router.get("/experiences", response_model=list[XrExperienceOut], summary="XR experience cards")
async def list_xr(db: Annotated[AsyncSession, Depends(get_db)]) -> list[XrExperienceOut]:
    return await AiAgentService(db).list_xr()
