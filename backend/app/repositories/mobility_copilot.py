"""Read/write access to mobility copilot conversation turns (ai_state schema)."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mobility_copilot_state import MobilityCopilotTurn


class MobilityCopilotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_turns(self, session_id: str, *, limit: int | None = None) -> list[MobilityCopilotTurn]:
        statement = (
            select(MobilityCopilotTurn)
            .where(MobilityCopilotTurn.session_id == session_id)
            .order_by(MobilityCopilotTurn.created_at)
        )
        if limit is not None:
            # Most-recent-N: order descending to take the tail, then
            # restore chronological order for the caller.
            statement = (
                select(MobilityCopilotTurn)
                .where(MobilityCopilotTurn.session_id == session_id)
                .order_by(MobilityCopilotTurn.created_at.desc())
                .limit(limit)
            )
            rows = (await self._session.execute(statement)).scalars().all()
            return list(reversed(rows))
        return list((await self._session.execute(statement)).scalars().all())

    async def append_turn(self, session_id: str, role: str, content: str) -> MobilityCopilotTurn:
        turn = MobilityCopilotTurn(session_id=session_id, role=role, content=content)
        self._session.add(turn)
        await self._session.commit()
        await self._session.refresh(turn)
        return turn

    async def clear_turns(self, session_id: str) -> None:
        await self._session.execute(
            delete(MobilityCopilotTurn).where(MobilityCopilotTurn.session_id == session_id)
        )
        await self._session.commit()
