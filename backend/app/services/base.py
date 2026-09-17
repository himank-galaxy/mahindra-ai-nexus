"""Service layer base: services own mapping/formatting, repositories own data access."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseService:
    """Holds the request session; concrete services build their repositories."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
