"""Analytics Copilot: suggested prompt chips + the rule-based chat engine."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot import RuleBasedCopilot
from app.core.cache import cached_read
from app.repositories import CopilotRepository
from app.schemas.copilot import CopilotChatIn, CopilotResultOut
from app.services.base import BaseService


class CopilotService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = CopilotRepository(session)
        self._engine = RuleBasedCopilot()

    async def list_suggested_prompts(self) -> list[str]:
        return await cached_read("copilot:prompts", self._load_prompts)

    async def _load_prompts(self) -> list[str]:
        return list(await self._repo.list_prompt_texts())

    async def chat(self, payload: CopilotChatIn) -> CopilotResultOut:
        result = self._engine.respond(payload.message)
        return CopilotResultOut.model_validate(result)
