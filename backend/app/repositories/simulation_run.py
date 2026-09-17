"""Data access for persisted Simulation Center runs and approvals.

Reads/writes ``ai_state.simulation_runs``/``ai_state.simulation_approvals``
directly via the ORM (unlike the runtime-schema repositories, these tables
are app-owned and safe to write to — see app/models/simulation.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.simulation import SimulationApproval, SimulationRun


class SimulationRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(
        self,
        *,
        domain: str,
        scenario_name: str,
        status: str,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        confidence: int,
        confidence_band: str,
        confidence_basis: str,
        model_name: str,
        model_version: str,
        baseline_reference: dict[str, Any] | None = None,
        driver_json: dict[str, Any] | None = None,
        recommendation_json: dict[str, Any] | None = None,
    ) -> SimulationRun:
        run = SimulationRun(
            domain=domain,
            scenario_name=scenario_name,
            status=status,
            inputs=inputs,
            baseline_reference=baseline_reference,
            outputs=outputs,
            driver_json=driver_json,
            recommendation_json=recommendation_json,
            confidence=confidence,
            confidence_band=confidence_band,
            confidence_basis=confidence_basis,
            model_name=model_name,
            model_version=model_version,
        )
        self._session.add(run)
        await self._session.commit()
        await self._session.refresh(run)
        return run

    async def get_run(self, run_id: uuid.UUID) -> SimulationRun | None:
        return await self._session.get(SimulationRun, run_id)

    async def update_status(self, run: SimulationRun, status: str) -> SimulationRun:
        run.status = status
        await self._session.commit()
        await self._session.refresh(run)
        return run

    async def create_approval(
        self,
        *,
        run_id: uuid.UUID,
        decision: str,
        reason: str | None = None,
        actor: str = "demo_user",
    ) -> SimulationApproval:
        approval = SimulationApproval(
            run_id=run_id,
            decision=decision,
            reason=reason,
            actor=actor,
            decided_at=datetime.now(UTC),
        )
        self._session.add(approval)
        await self._session.commit()
        await self._session.refresh(approval)
        return approval

    async def get_latest_approval(self, run_id: uuid.UUID) -> SimulationApproval | None:
        result = await self._session.execute(
            select(SimulationApproval)
            .where(SimulationApproval.run_id == run_id)
            .order_by(SimulationApproval.decided_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
