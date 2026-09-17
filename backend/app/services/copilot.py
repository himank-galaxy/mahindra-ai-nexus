"""Analytics Copilot: canonical prompt chips plus the chat engine."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot import RuleBasedCopilot
from app.repositories import CopilotRepository
from app.schemas.copilot import CopilotChatIn, CopilotResultOut
from app.services.base import BaseService


class CopilotService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = CopilotRepository(session)
        self._engine = RuleBasedCopilot()

    async def list_suggested_prompts(self) -> list[str]:
        prompts = await self._repo.list_prompt_texts()
        return list(dict.fromkeys(str(prompt) for prompt in prompts))

    async def chat(self, payload: CopilotChatIn) -> CopilotResultOut:
        result = self._engine.respond(payload.message)
        return CopilotResultOut.model_validate(result)
