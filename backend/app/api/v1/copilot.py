"""Analytics Copilot endpoints: suggested prompts + rule-based chat."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.copilot import CopilotChatIn, CopilotResultOut
from app.services import CopilotService

router = APIRouter()


@router.get("/suggested-prompts", response_model=list[str], summary="Suggested prompt chips")
async def list_suggested_prompts(db: Annotated[AsyncSession, Depends(get_db)]) -> list[str]:
    return await CopilotService(db).list_suggested_prompts()


@router.post(
    "/chat",
    response_model=CopilotResultOut,
    response_model_exclude_none=True,
    summary="Ask the analytics copilot",
)
async def chat(
    payload: CopilotChatIn,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CopilotResultOut:
    return await CopilotService(db).chat(payload)
