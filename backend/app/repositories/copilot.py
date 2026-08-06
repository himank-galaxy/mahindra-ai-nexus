"""Copilot reads: suggested prompt chips (sessions/messages are Phase 3)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from app.models import SuggestedPrompt
from app.repositories.base import BaseRepository


class CopilotRepository(BaseRepository[SuggestedPrompt]):
    model_type = SuggestedPrompt

    async def list_prompt_texts(self) -> Sequence[str]:
        stmt = select(SuggestedPrompt.text).order_by(SuggestedPrompt.sort_order)
        result = await self._session.execute(stmt)
        return result.scalars().all()
