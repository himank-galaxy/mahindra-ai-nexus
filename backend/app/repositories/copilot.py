"""Copilot prompt reads from the canonical runtime schema."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.runtime_schema import runtime_tables

SUGGESTED_PROMPTS = runtime_tables["suggested_prompts"]


class CopilotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_prompt_texts(self) -> Sequence[str]:
        result = await self._session.execute(
            select(SUGGESTED_PROMPTS.c.prompt_text)
            .where(SUGGESTED_PROMPTS.c.enabled.is_(True))
            .order_by(SUGGESTED_PROMPTS.c.display_order)
        )
        return result.scalars().all()
