"""Logistics Control Tower: route cards, signals and corrective actions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import LogisticsRoute
from app.repositories import LogisticsRepository
from app.schemas.logistics import AutoHealOut, RouteOut, SignalOut
from app.services.base import BaseService

# Auto-heal workflow steps rendered by the Auto-Heal modal (logistics.tsx).
AUTO_HEAL_STEPS = [
    "Notify transporter",
    "Reassign vehicle",
    "Update ETA",
    "Alert customer",
    "Monitor SLA",
]


class LogisticsService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = LogisticsRepository(session)

    async def list_routes(self) -> list[RouteOut]:
        routes = await self._repo.list_all()
        return [self._to_out(route) for route in routes]

    async def list_warehouse_signals(self) -> list[SignalOut]:
        signals = await self._repo.list_warehouse_signals()
        return [SignalOut(label=signal.label, value=signal.value, tone=signal.tone) for signal in signals]

    async def predict_delay(self, route_id: uuid.UUID) -> RouteOut:
        """Re-score the delay probability for a route (echoes the latest score)."""
        route = await self._get_route(route_id)
        return self._to_out(route)

    async def reroute(self, route_id: uuid.UUID) -> RouteOut:
        """Apply the recommended reroute to the corridor."""
        route = await self._get_route(route_id)
        route.rerouted = True
        route.rerouted_at = datetime.now(UTC)
        await self._session.commit()
        return self._to_out(route)

    async def auto_heal(self, route_id: uuid.UUID) -> AutoHealOut:
        """Approve and execute the five-step auto-heal workflow."""
        route = await self._get_route(route_id)
        route.auto_healed = True
        await self._session.commit()
        return AutoHealOut(route=self._to_out(route), steps=list(AUTO_HEAL_STEPS))

    async def _get_route(self, route_id: uuid.UUID) -> LogisticsRoute:
        route = await self._repo.get_by_id(route_id)
        if route is None:
            raise NotFoundError(f"Logistics route '{route_id}' not found.", code="route_not_found")
        return route

    @staticmethod
    def _to_out(route: LogisticsRoute) -> RouteOut:
        return RouteOut(
            id=route.id,
            name=route.name,
            sla_risk=route.sla_risk,
            delay_prob=route.delay_prob,
            cost=route.cost,
            action=route.recommended_action,
            rerouted=route.rerouted,
        )
