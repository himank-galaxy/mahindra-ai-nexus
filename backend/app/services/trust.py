"""Compliance Trust Ledger over canonical decisions and checks.

Also surfaces Simulation Center runs (see app/models/simulation.py) as
rows prefixed ``SIM_`` so they're visually and functionally distinct from
the immutable canonical ``trust_decisions`` rows. Unlike the canonical
track — pre-generated Synthetic Data Factory history that can never be
re-decided — simulation runs are a genuine second governance entry
point: a still-open (``PROPOSED``/``HUMAN_REVIEW_PENDING``) run can be
approved/rejected/escalated from here, and doing so calls straight into
``SimulationService`` (the same code path the Simulation Center screen
itself uses) so the decision is recorded exactly once, never duplicated.
Canonical rows stay immutable and always refuse these actions.

Compliance results are always per-decision, never a global aggregate:
canonical rows read their own real ``compliance_checks`` rows; simulation
rows are evaluated once by app/services/compliance_engine.py (real risk
score from app/services/risk_engine.py feeding the human-control-gate
rule) and cached in ``ai_state.simulation_compliance_checks`` — a run's
inputs never change after creation, so re-evaluating would always give
the same answer, but persisting still gives a stable, inspectable record.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainValidationError, NotFoundError
from app.database.runtime_schema import runtime_tables
from app.models.simulation import (
    SimulationApproval,
    SimulationComplianceCheck,
    SimulationHumanReview,
    SimulationRun,
)
from app.repositories.simulation_run import SimulationRunRepository
from app.schemas.trust import (
    AuditEventOut,
    ComplianceCheckOut,
    EvidenceItemOut,
    ExplanationDriverOut,
    ExplanationOut,
    LineageStepOut,
    OutcomeOut,
    TrustDecisionOut,
)
from app.services.base import BaseService
from app.services.compliance_engine import derive_audit_status, evaluate_simulation_compliance
from app.services.risk_engine import score_simulation_risk

TRUST_DECISIONS = runtime_tables["trust_decisions"]
COMPLIANCE_CHECKS = runtime_tables["compliance_checks"]
RECOMMENDATIONS = runtime_tables["recommendations"]
AUDIT_EVENTS = runtime_tables["audit_events"]
ACTION_OUTCOMES = runtime_tables["action_outcomes"]
SIMULATION_ID_PREFIX = "SIM_"


def _decision_out(row: dict[str, object]) -> TrustDecisionOut:
    requires_review = bool(row["human_review_required"]) or int(row["compliance_review_required_count"] or 0) > 0
    failed = int(row["compliance_fail_count"] or 0) > 0
    audit = "Failed" if failed else "Review Required" if requires_review else "Passed"
    decision = str(row["decision"])
    # This is completed, immutable history: `decision` already reflects
    # the outcome of any human review that was required at the time, so
    # eligibility only needs the final decision plus the one thing a
    # human sign-off can never override — a mandatory check that FAILED.
    execution_eligible = decision == "APPROVED" and not failed
    if decision != "APPROVED":
        execution_eligible_reason = f"Blocked: this decision was {decision.lower()}, not approved."
    elif failed:
        execution_eligible_reason = (
            "Blocked: a mandatory compliance check failed for this decision, which overrides approval."
        )
    else:
        execution_eligible_reason = "Approved, and no mandatory compliance check failed."
    return TrustDecisionOut(
        id=str(row["decision_id"]),
        use=str(row["use_case"]).replace("_", " ").title(),
        rec=str(row["recommendation_type"]).replace("_", " ").title(),
        data=f"{row['target_entity_type']}: {row['target_entity_id']}",
        conf=round(float(row["recommendation_confidence"]) * 100),
        approval=str(row["decision"]).replace("_", " ").title(),
        risk=str(row["recommendation_risk_level"]).replace("_", " ").title(),
        audit=audit,
        execution_eligible_reason=execution_eligible_reason,
        execution_eligible=execution_eligible,
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


def _simulation_target_descriptor(domain: str, inputs: dict[str, object]) -> str:
    """What this run was actually about — real per-domain identifying
    values, never a fabricated ID. Auto Sales and Logistics Delay target
    a real single row (a vehicle model, a real ``route_id``); Dealer
    Allocation/Collections/Credit Pricing simulate over a real cohort/
    segment rather than one entity, so there is no single row's primary
    key to show — the real cohort-defining inputs are shown instead."""
    if domain == "auto-sales":
        return f"{inputs.get('region', '?')} / {inputs.get('model', '?')}"
    if domain == "dealer-allocation":
        return f"{inputs.get('units', '?')} units / {inputs.get('capacity', '?')}% capacity"
    if domain == "collections":
        return f"{inputs.get('risk', '?')} risk / {inputs.get('channel', '?')}"
    if domain == "logistics-delay":
        return f"Route {inputs.get('route', '?')}"
    if domain == "credit-pricing":
        return str(inputs.get("type", "?"))
    return "?"


def _simulation_approval_label(run: SimulationRun, approval: SimulationApproval | None) -> str:
    if approval is not None:
        return approval.decision.title()
    if run.status == "HUMAN_REVIEW_PENDING":
        return "Escalated"
    return "Pending"


class TrustService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._run_repo = SimulationRunRepository(session)

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
        """Every persisted run, decided or still pending — a pending run
        (no approval yet, or escalated) is a live, actionable governance
        entry, not just a historical mirror, so it must be visible here
        too, not only once someone has already decided it."""
        rows = (
            await self._session.execute(
                select(SimulationRun, SimulationApproval).outerjoin(
                    SimulationApproval, SimulationApproval.run_id == SimulationRun.id
                )
            )
        ).all()
        return [
            (
                approval.decided_at if approval is not None else run.created_at,
                await self._build_simulation_decision(run, approval),
            )
            for run, approval in rows
        ]

    async def _get_or_evaluate_simulation_compliance(self, run: SimulationRun) -> list[SimulationComplianceCheck]:
        existing = await self._run_repo.get_compliance_checks(run.id)
        if existing:
            return existing
        risk = score_simulation_risk(run.domain, run.confidence, run.outputs or {})
        results = evaluate_simulation_compliance(run, risk)
        return await self._run_repo.create_compliance_checks(
            run.id,
            [(r.rule_code, r.rule_name, r.result, r.reason) for r in results],
        )

    async def _build_simulation_decision(
        self,
        run: SimulationRun,
        approval: SimulationApproval | None,
    ) -> TrustDecisionOut:
        inputs = run.inputs or {}
        outputs = run.outputs or {}
        risk = score_simulation_risk(run.domain, run.confidence, outputs)
        checks = await self._get_or_evaluate_simulation_compliance(run)
        audit = derive_audit_status(checks)  # duck-typed on `.result`; works for both ComplianceResult and the ORM rows
        # This system has no autonomous execution path at all — every
        # decision, whatever its risk, already requires a human to click
        # Approve before anything happens, so that click IS the human-
        # control gate being satisfied. What approval can never override
        # is a mandatory check that genuinely FAILED (a data/integrity
        # problem, not just "needs a second look").
        approval_label = _simulation_approval_label(run, approval)
        any_failed = any(c.result == "FAIL" for c in checks)
        execution_eligible = approval_label == "Approved" and not any_failed
        if approval_label != "Approved":
            execution_eligible_reason = {
                "Pending": "Blocked: awaiting a human decision (approve, reject, or escalate).",
                "Escalated": "Blocked: awaiting a human reviewer's decision after escalation.",
                "Rejected": "Blocked: this recommendation was rejected.",
            }.get(approval_label, f"Blocked: current status is {approval_label}.")
        elif any_failed:
            execution_eligible_reason = (
                "Blocked: a mandatory compliance check failed for this run, which overrides approval."
            )
        else:
            execution_eligible_reason = "Approved by a human reviewer, and no mandatory compliance check failed."
        return TrustDecisionOut(
            id=_simulation_code(run.id),
            use=f"{run.domain.replace('-', ' ').title()} Simulation",
            rec=str(outputs.get("recommendedAction", ""))[:120],
            data=_simulation_target_descriptor(run.domain, inputs),
            conf=run.confidence,
            approval=approval_label,
            risk=risk.level,
            audit=audit,
            execution_eligible=execution_eligible,
            execution_eligible_reason=execution_eligible_reason,
        )

    async def get_compliance(self, code: str) -> list[ComplianceCheckOut]:
        run_id = _simulation_run_id(code)
        if run_id is not None:
            run = await self._run_repo.get_run(run_id)
            if run is None:
                raise NotFoundError(f"Trust decision '{code}' not found.", code="decision_not_found")
            checks = await self._get_or_evaluate_simulation_compliance(run)
            return [
                ComplianceCheckOut(rule_code=c.rule_code, rule_name=c.rule_name, result=c.result, reason=c.reason)
                for c in checks
            ]
        await self._decision_row(code)
        rows = (
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
            ComplianceCheckOut(
                rule_code=row["rule_code"],
                rule_name=row["rule_name"],
                result=row["result"],
                reason=row["reason"],
            )
            for row in rows
        ]

    async def _get_recommendation_row(self, recommendation_id: str) -> dict[str, object] | None:
        row = (
            (
                await self._session.execute(
                    select(RECOMMENDATIONS).where(RECOMMENDATIONS.c.recommendation_id == recommendation_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    async def get_explanation(self, code: str) -> ExplanationOut:
        run_id = _simulation_run_id(code)
        if run_id is not None:
            return await self._simulation_explanation(run_id, code)
        row = await self._decision_row(code)
        rec_row = await self._get_recommendation_row(str(row["recommendation_id"]))
        evidence: dict[str, object] = {}
        if rec_row is not None and rec_row["evidence_json"]:
            evidence = json.loads(rec_row["evidence_json"])
        return ExplanationOut(
            recommendation=str(row["recommendation_type"]).replace("_", " ").title(),
            confidence=round(float(row["recommendation_confidence"]) * 100),
            confidence_basis="generated",
            confidence_reason=(
                "Confidence score attached to this recommendation by the originating engine — no per-feature "
                "driver weights are stored for canonical (Synthetic Data Factory) decisions, so no drivers are "
                "listed below; the real business evidence that fed the recommendation is."
            ),
            drivers=[],
            supporting_evidence=[
                EvidenceItemOut(label=str(key).replace("_", " ").title(), value=str(value))
                for key, value in evidence.items()
            ],
        )

    async def _simulation_explanation(self, run_id: uuid.UUID, code: str) -> ExplanationOut:
        run, _approval = await self._simulation_row(run_id, code)
        driver_items = (run.driver_json or {}).get("predictive_drivers") or []
        drivers = [
            ExplanationDriverOut(
                name=item["name"],
                direction=item["direction"],
                contribution=item["contribution"],
                source=item["source"],
                detail=item["detail"],
            )
            for item in driver_items
        ]
        baseline = run.baseline_reference or {}
        if run.confidence_basis == "trained_model":
            confidence_reason = "A model trained on real historical outcomes for this domain produced this confidence score."
        else:
            confidence_reason = (
                "A documented calibrated assumption produced this confidence score — no historical outcome "
                "variation exists in the business data to fit a trained model against."
            )
        return ExplanationOut(
            recommendation=str(run.outputs.get("recommendedAction", "")),
            confidence=run.confidence,
            confidence_basis=run.confidence_basis,
            confidence_reason=confidence_reason,
            drivers=drivers,
            supporting_evidence=[
                EvidenceItemOut(label=str(key).replace("_", " ").title(), value=str(value))
                for key, value in baseline.items()
            ],
        )

    async def get_events(self, code: str) -> list[AuditEventOut]:
        """Real, chronological, append-only history — never a synthesized
        intermediate step that wasn't actually recorded (see module
        docstring). Canonical rows read the real hash-chained
        ``audit_events`` table; simulation rows are assembled from the
        run's own real timestamps across simulation_runs/human_reviews/
        approvals — coarser-grained (no per-compliance-check event yet)
        but every entry is a genuine persisted timestamp, not invented."""
        run_id = _simulation_run_id(code)
        if run_id is not None:
            return await self._simulation_events(run_id, code)
        await self._decision_row(code)
        rows = (
            (
                await self._session.execute(
                    select(AUDIT_EVENTS)
                    .where(AUDIT_EVENTS.c.decision_id == code)
                    .order_by(AUDIT_EVENTS.c.event_sequence)
                )
            )
            .mappings()
            .all()
        )
        return [
            AuditEventOut(
                event_type=row["event_type"],
                event_at=row["event_at"],
                actor=f"{row['actor_type']}:{row['actor_id']}",
                summary=row["event_summary"],
            )
            for row in rows
        ]

    async def _simulation_events(self, run_id: uuid.UUID, code: str) -> list[AuditEventOut]:
        run, approval = await self._simulation_row(run_id, code)
        reviews: list[SimulationHumanReview] = await self._run_repo.get_human_reviews(run_id)
        events = [
            AuditEventOut(
                event_type="DECISION_CREATED",
                event_at=run.created_at,
                actor="system",
                summary=f"{run.domain.replace('-', ' ').title()} simulation run created (model {run.model_name} {run.model_version}).",
            )
        ]
        for review in reviews:
            events.append(
                AuditEventOut(
                    event_type="HUMAN_ESCALATED",
                    event_at=review.requested_at,
                    actor=review.requested_by,
                    summary=f"Escalated to {review.reviewer_role}"
                    + (f" — {review.reason}" if review.reason else "") ,
                )
            )
        if approval is not None:
            events.append(
                AuditEventOut(
                    event_type="HUMAN_APPROVED" if approval.decision == "approved" else "HUMAN_REJECTED",
                    event_at=approval.decided_at,
                    actor=approval.actor,
                    summary=f"Decision {approval.decision}"
                    + (f" — {approval.reason}" if approval.reason else ""),
                )
            )
        return sorted(events, key=lambda e: e.event_at)

    async def get_outcome(self, code: str) -> OutcomeOut:
        """Real observed/expected outcome only — never fabricated.

        Canonical: ``expected_impact`` comes from the decision's real
        ``recommendations`` row (present whenever a recommendation
        exists); the observed outcome comes from a real ``action_outcomes``
        row keyed to this exact ``decision_id``, which only exists once
        the recommendation has actually been executed (verified: it
        never exists for a REJECTED decision). No action_outcomes row
        yet means the outcome is genuinely pending, not unknown.

        Simulation: there is no execution/outcome mechanism for
        Simulation Center runs at all yet, so every simulation decision
        is honestly PENDING with no expected impact to show — this is a
        real absence of data, not a placeholder.
        """
        run_id = _simulation_run_id(code)
        if run_id is not None:
            await self._simulation_row(run_id, code)  # 404s if the run doesn't exist
            return OutcomeOut(outcome_status="PENDING")

        row = await self._decision_row(code)
        rec_row = await self._get_recommendation_row(str(row["recommendation_id"]))
        expected_impact: dict[str, object] | None = None
        if rec_row is not None and rec_row["expected_impact"]:
            expected_impact = json.loads(rec_row["expected_impact"])

        outcome_row = (
            (
                await self._session.execute(
                    select(ACTION_OUTCOMES).where(ACTION_OUTCOMES.c.decision_id == code)
                )
            )
            .mappings()
            .one_or_none()
        )
        if outcome_row is None:
            return OutcomeOut(outcome_status="PENDING", expected_impact=expected_impact)
        return OutcomeOut(
            outcome_status="OBSERVED",
            expected_impact=expected_impact,
            observed_outcome_type=outcome_row["outcome_type"],
            observed_outcome_value=outcome_row["outcome_value"],
            observed_at=outcome_row["observed_at"],
            business_outcome_observed=outcome_row["business_outcome_observed"],
            business_outcome_note=outcome_row["business_outcome_note"] or None,
        )

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
                title=f"Data: {_simulation_target_descriptor(run.domain, run.inputs)} cohort",
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
        if approval is not None:
            human_decision_detail = (
                f"By {approval.actor} at {approval.decided_at.isoformat()}"
                + (f" — {approval.reason}" if approval.reason else "")
            )
            human_decision_title = f"Human decision: {approval.decision.title()}"
        elif run.status == "HUMAN_REVIEW_PENDING":
            human_decision_title = "Human decision: Escalated"
            human_decision_detail = "Awaiting a human reviewer's decision."
        else:
            human_decision_title = "Human decision: Pending"
            human_decision_detail = "No decision has been recorded yet."
        steps.append(LineageStepOut(step=next_step + 1, title=human_decision_title, detail=human_decision_detail))
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

    async def _simulation_row(self, run_id: uuid.UUID, code: str) -> tuple[SimulationRun, SimulationApproval | None]:
        row = (
            await self._session.execute(
                select(SimulationRun, SimulationApproval)
                .outerjoin(SimulationApproval, SimulationApproval.run_id == SimulationRun.id)
                .where(SimulationRun.id == run_id)
            )
        ).first()
        if row is None:
            raise NotFoundError(f"Trust decision '{code}' not found.", code="decision_not_found")
        return row

    async def approve_decision(self, code: str) -> TrustDecisionOut:
        run_id = _simulation_run_id(code)
        if run_id is not None:
            from app.services.simulation import SimulationService  # local import: avoids a module-load cycle

            await SimulationService(self._session).approve_run(run_id, reason=None)
            return await self._simulation_decision_out_by_id(run_id, code)
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
        run_id = _simulation_run_id(code)
        if run_id is not None:
            from app.services.simulation import SimulationService

            await SimulationService(self._session).reject_run(run_id, reason=reason or None)
            return await self._simulation_decision_out_by_id(run_id, code)
        await self._decision_row(code)
        raise DomainValidationError(
            "Canonical trust decisions are immutable audit records.",
            code="immutable_trust_decision",
        )

    async def escalate_decision(self, code: str, reviewer_role: str, reason: str) -> TrustDecisionOut:
        run_id = _simulation_run_id(code)
        if run_id is not None:
            from app.services.simulation import SimulationService

            await SimulationService(self._session).escalate_run(run_id, reviewer_role=reviewer_role, reason=reason or None)
            return await self._simulation_decision_out_by_id(run_id, code)
        await self._decision_row(code)
        raise DomainValidationError(
            "Canonical trust decisions are immutable audit records — escalation is already recorded in human_reviews.",
            code="immutable_trust_decision",
        )

    async def _simulation_decision_out_by_id(self, run_id: uuid.UUID, code: str) -> TrustDecisionOut:
        run, approval = await self._simulation_row(run_id, code)
        return await self._build_simulation_decision(run, approval)
