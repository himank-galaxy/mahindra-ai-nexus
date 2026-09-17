"""Compliance Trust Ledger over canonical decisions and checks.

Also surfaces already-decided Simulation Center runs (Auto Sales approvals/
rejections — see app/models/simulation.py) as read-only rows, prefixed
``SIM_`` so they're visually and functionally distinct from the immutable
canonical ``trust_decisions`` rows: a simulation decision was already made
in the Simulation Center itself, so lineage is shown but approve/reject/
escalate from here is refused with a message pointing back there.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select

from app.core.errors import DomainValidationError, NotFoundError
from app.database.runtime_schema import runtime_tables
from app.models.simulation import SimulationApproval, SimulationRun
from app.schemas.trust import ComplianceRuleOut, LineageStepOut, TrustDecisionOut
from app.services.base import BaseService

TRUST_DECISIONS = runtime_tables["trust_decisions"]
COMPLIANCE_CHECKS = runtime_tables["compliance_checks"]
RESULT_PRIORITY = {"PASS": 0, "WARN": 1, "REVIEW_REQUIRED": 2, "FAIL": 3}
SIMULATION_ID_PREFIX = "SIM_"


def _decision_out(row: dict[str, object]) -> TrustDecisionOut:
    requires_review = bool(row["human_review_required"]) or int(row["compliance_review_required_count"] or 0) > 0
    failed = int(row["compliance_fail_count"] or 0) > 0
    audit = "Failed" if failed else "Review Required" if requires_review else "Passed"
    return TrustDecisionOut(
        id=str(row["decision_id"]),
        use=str(row["use_case"]).replace("_", " ").title(),
        rec=str(row["recommendation_type"]).replace("_", " ").title(),
        data=f"{row['target_entity_type']}: {row['target_entity_id']}",
        conf=round(float(row["recommendation_confidence"]) * 100),
        approval=str(row["decision"]).replace("_", " ").title(),
        risk=str(row["recommendation_risk_level"]).replace("_", " ").title(),
        audit=audit,
    )


def _simulation_code(run_id: uuid.UUID) -> str:
    return f"{SIMULATION_ID_PREFIX}{run_id.hex}"


def _simulation_run_id(code: str) -> uuid.UUID | None:
    if not code.startswith(SIMULATION_ID_PREFIX):
        return None
    try:
        return uuid.UUID(hex=code[len(SIMULATION_ID_PREFIX) :])
    except ValueError:
        return None


def _simulation_decision_out(run: SimulationRun, approval: SimulationApproval) -> TrustDecisionOut:
    inputs = run.inputs or {}
    outputs = run.outputs or {}
    risk_by_band = {"low": "High", "medium": "Medium", "high": "Low"}
    return TrustDecisionOut(
        id=_simulation_code(run.id),
        use=f"{run.domain.replace('-', ' ').title()} Simulation",
        rec=str(outputs.get("recommendedAction", ""))[:120],
        data=f"{inputs.get('region', '?')} / {inputs.get('model', inputs.get('type', '?'))}",
        conf=run.confidence,
        approval=approval.decision.title(),
        risk=risk_by_band.get(run.confidence_band, "Medium"),
        audit="Review Required" if run.confidence_basis == "calibrated_heuristic" else "Passed",
    )


class TrustService(BaseService):
    async def list_decisions(self) -> list[TrustDecisionOut]:
        rows = (
            (await self._session.execute(select(TRUST_DECISIONS).order_by(TRUST_DECISIONS.c.decided_at.desc())))
            .mappings()
            .all()
        )
        canonical: list[tuple[datetime, TrustDecisionOut]] = [
            (row["decided_at"], _decision_out(dict(row))) for row in rows
        ]
        simulation = await self._list_simulation_decisions()
        combined = sorted(canonical + simulation, key=lambda pair: pair[0], reverse=True)
        return [decision for _decided_at, decision in combined]

    async def _list_simulation_decisions(self) -> list[tuple[datetime, TrustDecisionOut]]:
        rows = (
            await self._session.execute(
                select(SimulationRun, SimulationApproval)
                .join(SimulationApproval, SimulationApproval.run_id == SimulationRun.id)
                .order_by(SimulationApproval.decided_at.desc())
            )
        ).all()
        return [(approval.decided_at, _simulation_decision_out(run, approval)) for run, approval in rows]

    async def list_rules(self) -> list[ComplianceRuleOut]:
        rows = (
            await self._session.execute(
                select(
                    COMPLIANCE_CHECKS.c.rule_code,
                    COMPLIANCE_CHECKS.c.rule_name,
                    COMPLIANCE_CHECKS.c.result,
                )
            )
        ).all()
        grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
        for code, name, result in rows:
            grouped[(str(code), str(name))].append(str(result))
        output = []
        for (_code, name), results in grouped.items():
            status = max(
                results,
                key=lambda result: RESULT_PRIORITY.get(result, 0),
            )
            output.append(
                ComplianceRuleOut(
                    label=name,
                    status=status.replace("_", " ").title(),
                )
            )
        return sorted(output, key=lambda rule: rule.label)

    async def get_lineage(self, code: str) -> list[LineageStepOut]:
        run_id = _simulation_run_id(code)
        if run_id is not None:
            return await self._simulation_lineage(run_id, code)
        await self._decision_row(code)
        checks = (
            (
                await self._session.execute(
                    select(COMPLIANCE_CHECKS)
                    .where(COMPLIANCE_CHECKS.c.decision_id == code)
                    .order_by(COMPLIANCE_CHECKS.c.checked_at)
                )
            )
            .mappings()
            .all()
        )
        return [
            LineageStepOut(
                step=index,
                title=(f"{row['rule_name']}: {str(row['result']).replace('_', ' ').title()}"),
                detail=row["reason"],
            )
            for index, row in enumerate(checks, start=1)
        ]

    async def _simulation_lineage(self, run_id: uuid.UUID, code: str) -> list[LineageStepOut]:
        """Real lineage from the run's own persisted evidence, not synthetic
        compliance-check rows — data -> model -> drivers -> recommendation ->
        human decision, matching this app's own observe-predict-explain-
        simulate-recommend-approve chain."""
        run, approval = await self._simulation_row(run_id, code)
        drivers = run.driver_json or {}
        steps = [
            LineageStepOut(
                step=1,
                title=f"Data: {run.inputs.get('region', '?')} / {run.inputs.get('model', '?')} cohort",
                detail=(run.baseline_reference or {}),
            ),
            LineageStepOut(
                step=2,
                title=f"Model: {run.model_name} ({run.model_version})",
                detail=f"Confidence {run.confidence}% ({run.confidence_band}, {run.confidence_basis}).",
            ),
        ]
        for index, driver in enumerate((drivers.get("predictive_drivers") or [])[:3], start=3):
            steps.append(LineageStepOut(step=index, title=f"Driver: {driver['name']}", detail=driver["detail"]))
        next_step = len(steps) + 1
        steps.append(
            LineageStepOut(step=next_step, title="Recommendation", detail=run.outputs.get("recommendedAction", ""))
        )
        steps.append(
            LineageStepOut(
                step=next_step + 1,
                title=f"Human decision: {approval.decision.title()}",
                detail=f"By {approval.actor} at {approval.decided_at.isoformat()}"
                + (f" — {approval.reason}" if approval.reason else ""),
            )
        )
        return steps

    async def _decision_row(self, code: str) -> dict[str, object]:
        row = (
            (await self._session.execute(select(TRUST_DECISIONS).where(TRUST_DECISIONS.c.decision_id == code)))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise NotFoundError(
                f"Trust decision '{code}' not found.",
                code="decision_not_found",
            )
        return dict(row)

    async def _simulation_row(self, run_id: uuid.UUID, code: str) -> tuple[SimulationRun, SimulationApproval]:
        row = (
            await self._session.execute(
                select(SimulationRun, SimulationApproval)
                .join(SimulationApproval, SimulationApproval.run_id == SimulationRun.id)
                .where(SimulationRun.id == run_id)
            )
        ).first()
        if row is None:
            raise NotFoundError(f"Trust decision '{code}' not found.", code="decision_not_found")
        return row

    async def approve_decision(self, code: str) -> TrustDecisionOut:
        if _simulation_run_id(code) is not None:
            raise DomainValidationError(
                "This decision was already recorded in the Simulation Center and cannot be changed here.",
                code="simulation_decision_immutable",
            )
        await self._decision_row(code)
        raise DomainValidationError(
            "Canonical trust decisions are immutable audit records.",
            code="immutable_trust_decision",
        )

    async def reject_decision(
        self,
        code: str,
        reason: str,
    ) -> TrustDecisionOut:
        if _simulation_run_id(code) is not None:
            raise DomainValidationError(
                "This decision was already recorded in the Simulation Center and cannot be changed here.",
                code="simulation_decision_immutable",
            )
        await self._decision_row(code)
        raise DomainValidationError(
            "Canonical trust decisions are immutable audit records.",
            code="immutable_trust_decision",
        )

    async def escalate_decision(self, code: str) -> TrustDecisionOut:
        if _simulation_run_id(code) is not None:
            raise DomainValidationError(
                "This decision was already recorded in the Simulation Center and cannot be changed here.",
                code="simulation_decision_immutable",
            )
        await self._decision_row(code)
        raise DomainValidationError(
            "Escalation must be recorded through canonical human_reviews.",
            code="canonical_review_workflow_required",
        )
