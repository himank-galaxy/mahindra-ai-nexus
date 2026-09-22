"""Collections & Recovery AI Swarm: real database-backed case intelligence.

Two governance tracks over the same real ``collection_cases``, exactly
mirroring the Trust Ledger's canonical-vs-live split (see
app/services/trust.py):

- **Canonical**: a subset of cases already carry an immutable
  ``trust_decisions`` row (``target_entity_type='COLLECTION_CASE'``) from
  the Synthetic Data Factory's own governance history — real, historical,
  never re-decided from this screen. Their compliance/approval state is
  read straight from the real canonical tables.
- **Live**: every other case has no decision yet. Approve/Modify/Send-to-
  -review here create/update exactly one ``CollectionCaseDecision`` row
  per case (app/models/collections_case.py) — never a second decision for
  a case that already has one, the same rule Simulation Center follows.

Roll-forward risk and recovery probability/best-channel/best-offer are
never invented: they reuse the exact same trained models Collections
Simulation trains (app/ai/simulation/models/collections_model.py) and the
same channel/offer sweep optimizer (app/ai/simulation/collections_sim.py)
— applied to each real case's own features instead of a cohort average.
Compliance reuses the same five-rule engine the Trust Ledger applies to
Simulation Center runs (app/services/compliance_engine.py), fed a
lightweight snapshot of this case's real recommendation.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from app.ai.simulation.collections_sim import (
    COST_BY_CHANNEL_INR,
    FRICTION_BY_CHANNEL,
    MODEL_NAME,
    MODEL_VERSION,
    recovery_drivers,
    sweep_best_channel_offer,
)
from app.ai.simulation.confidence import trained_model_confidence
from app.ai.simulation.models.collections_model import CollectionsModels, get_or_train_models
from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.database.runtime_schema import runtime_tables
from app.models.collections_case import CollectionCaseDecision
from app.repositories.collections_case_decision import CollectionsCaseDecisionRepository
from app.repositories.collections_simulation import (
    CHANNEL_DISPLAY_NAMES,
    OFFER_DISPLAY_NAMES,
    CollectionsSimulationRepository,
)
from app.schemas.collections import (
    CaseTrustLedgerOut,
    CollectionsAgentOut,
    CollectionsCaseOut,
    MetricTileOut,
)
from app.schemas.trust import ComplianceCheckOut, OutcomeOut
from app.services.base import BaseService
from app.services.collections_priority import score_case_priority
from app.services.compliance_engine import ComplianceResult, derive_audit_status, evaluate_simulation_compliance
from app.services.risk_engine import score_simulation_risk
from app.services.trust import TrustService

MODEL_LABEL = f"{MODEL_NAME} ({MODEL_VERSION})"

# Case lifecycle/governance state collapsed into exactly one of four
# mutually-exclusive buckets the frontend filters by — computed purely
# from real fields already derived above, never a fifth invented state.
_CATEGORY_RESOLVED = "resolved"
_CATEGORY_APPROVED = "approved"
_CATEGORY_REVIEW_REQUIRED = "review_required"
_CATEGORY_ACTIONABLE = "actionable"

COLLECTION_CASES = runtime_tables["collection_cases"]
COLLECTION_INTERACTIONS = runtime_tables["collection_interactions"]
LOAN_ACCOUNTS = runtime_tables["loan_accounts"]
PAYMENT_HISTORY = runtime_tables["payment_history"]
TRUST_DECISIONS = runtime_tables["trust_decisions"]
COMPLIANCE_CHECKS = runtime_tables["compliance_checks"]
CASE_NAMESPACE = uuid.UUID("aaad670c-3b50-4580-b21f-ec2f6a857938")


def _case_uuid(case_id: str) -> uuid.UUID:
    return uuid.uuid5(CASE_NAMESPACE, case_id)


def _inr(amount: float) -> str:
    if amount >= 10_000_000:
        return f"₹{amount / 10_000_000:.1f} Cr"
    if amount >= 100_000:
        return f"₹{amount / 100_000:.1f}L"
    return f"₹{amount:,.0f}"


@dataclass(frozen=True)
class _ResultOnly:
    """Satisfies compliance_engine's ``_HasResult`` protocol for raw
    canonical ``compliance_checks`` mapping rows."""

    result: str


@dataclass(frozen=True)
class _CaseRecommendationSnapshot:
    """Satisfies compliance_engine's ``_HasComplianceFields`` protocol —
    a real case has no ``SimulationRun`` row, so this carries the same
    field names populated from the case's own real data instead."""

    model_name: str
    model_version: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    baseline_reference: dict[str, Any] | None
    driver_json: dict[str, Any] | None
    confidence: int


def _categorize(case_status: str, governance_track: str, approval_status: str) -> str:
    """One of four mutually-exclusive buckets, in priority order — a
    case's lifecycle status always wins (a resolved case is never still
    "actionable"), then whether it already has a real Approved decision,
    then whether it's been escalated or is a historical non-approved
    canonical decision (e.g. Rejected).

    Deliberately never a function of the compliance audit status
    (Passed/Review Required/Failed) — that is a separate, per-row
    "Compliance" column, not a governance-category filter. Collapsing the
    two would conflate approval state with audit/compliance state, which
    this screen (like the Trust Ledger) treats as distinct concepts: an
    undecided case with a Review Required compliance flag is still
    "actionable" — a human can and should still act on it, just with
    that flag visible."""
    if case_status == "RESOLVED":
        return _CATEGORY_RESOLVED
    if approval_status == "Approved":
        return _CATEGORY_APPROVED
    if approval_status == "Escalated" or governance_track == "canonical":
        return _CATEGORY_REVIEW_REQUIRED
    return _CATEGORY_ACTIONABLE


def _best_action_label(channel: str, offer: str) -> str:
    channel_label = CHANNEL_DISPLAY_NAMES[channel]
    if offer == "NONE":
        return channel_label
    return f"{channel_label} + {OFFER_DISPLAY_NAMES[offer]}"


def _build_case_output(
    case: dict[str, object],
    interactions: list[dict[str, object]],
    models: CollectionsModels,
    canonical: dict[str, object] | None,
    canonical_checks: list[dict[str, object]],
    live_decision: CollectionCaseDecision | None,
) -> dict[str, object]:
    """The one place case-level intelligence is computed — shared by the
    list endpoint (batched across all cases) and every case-scoped action
    (single case), so list and detail can never disagree."""
    case_id = str(case["collection_case_id"])
    current_dpd = int(case["current_dpd"] or 0)
    current_arrears = float(case["current_arrears_inr"] or 0.0)
    latest = interactions[-1] if interactions else {}
    # Real current outstanding principal — the latest recorded interaction
    # snapshot if this case has been contacted, else the loan's real
    # origination principal (never the case's arrears, which is a
    # different, smaller figure: how much of that balance is overdue).
    outstanding_inr = float(latest.get("outstanding_principal_at_interaction_inr") or case.get("principal_inr") or 0.0)

    roll_forward_features = {
        "principal_inr": float(case["principal_inr"] or 0.0),
        "interest_rate_pct": float(case["interest_rate_pct"] or 0.0),
        "debt_service_ratio_at_origination": float(case["debt_service_ratio_at_origination"] or 0.0),
        "secured": 1.0 if case["secured"] else 0.0,
    }
    # Roll-forward risk = probability this case keeps rolling forward
    # (inverse of "resolves") — a distinct model, distinct feature set,
    # distinct question from recovery probability below (see module
    # docstring's "never merge them" principle, matching the Trust Ledger
    # audit's own explicit requirement).
    roll_forward_risk = round((1 - models.roll_forward.predict_proba(roll_forward_features)) * 100)

    recovery_features = {
        "dpd_at_interaction": float(current_dpd),
        "arrears_at_interaction_inr": current_arrears,
        "outstanding_principal_at_interaction_inr": outstanding_inr,
    }
    best_channel, best_offer, best_prob, _best_net = sweep_best_channel_offer(models, recovery_features, outstanding_inr)

    modified_channel = live_decision.modified_channel if live_decision is not None else None
    modified_offer = live_decision.modified_offer if live_decision is not None else None
    effective_channel = modified_channel or best_channel
    effective_offer = modified_offer or best_offer
    if effective_channel == best_channel and effective_offer == best_offer:
        effective_prob = best_prob
    else:
        effective_prob = models.recovery.predict_proba(
            recovery_features, {"channel": effective_channel, "offer_type": effective_offer}
        )

    confidence, _band = trained_model_confidence(
        predicted_probability=effective_prob,
        in_training_range=True,
        cohort_sample_size=len(interactions),
    )
    # Real per-channel contact cost/friction (see app/ai/simulation/
    # collections_sim.py) — the same documented business assumptions
    # Collections Simulation uses, applied to the effective (possibly
    # human-modified) channel actually being used for this case.
    contact_cost_inr = COST_BY_CHANNEL_INR[effective_channel]
    friction = FRICTION_BY_CHANNEL[effective_channel]
    net_expected_recovery_inr = effective_prob * outstanding_inr - contact_cost_inr
    risk = score_simulation_risk("collections", confidence, {"net": round(net_expected_recovery_inr / 1000)})

    compliance_checks: list[ComplianceCheckOut]
    if canonical is not None:
        audit_status = derive_audit_status([_ResultOnly(str(c["result"])) for c in canonical_checks])
        approval_status = str(canonical["decision"]).replace("_", " ").title()
        governance_track = "canonical"
        decision_code: str | None = str(canonical["decision_id"])
        compliance_checks = [
            ComplianceCheckOut(
                rule_code=str(c["rule_code"]),
                rule_name=str(c["rule_name"]),
                result=str(c["result"]),  # type: ignore[arg-type]
                reason=str(c["reason"]),
            )
            for c in canonical_checks
        ]
    else:
        snapshot = _CaseRecommendationSnapshot(
            model_name=MODEL_NAME,
            model_version=MODEL_VERSION,
            inputs={
                "dpd": current_dpd,
                "arrears_inr": current_arrears,
                "outstanding_inr": outstanding_inr,
                "channel": effective_channel,
                "offer": effective_offer,
            },
            outputs={
                "recommendedAction": OFFER_DISPLAY_NAMES[effective_offer],
                "net": round(net_expected_recovery_inr / 1000),
            },
            baseline_reference={"case_id": case_id, "interaction_count": len(interactions)},
            driver_json={"predictive_drivers": recovery_drivers(models, effective_channel, effective_offer)},
            confidence=confidence,
        )
        results: list[ComplianceResult] = evaluate_simulation_compliance(snapshot, risk)
        audit_status = derive_audit_status(results)
        approval_status = live_decision.status.title() if live_decision is not None else "Pending"
        governance_track = "live"
        decision_code = case_id if live_decision is not None else None
        compliance_checks = [
            ComplianceCheckOut(rule_code=r.rule_code, rule_name=r.rule_name, result=r.result, reason=r.reason)  # type: ignore[arg-type]
            for r in results
        ]

    case_status = str(case["case_status"])
    category = _categorize(case_status, governance_track, approval_status)
    # A resolved case's lifecycle status is more informative than whatever
    # governance decision it happened to carry — display it plainly,
    # matching the "Resolved" filter bucket above.
    display_status = "Resolved" if case_status == "RESOLVED" else approval_status

    priority = score_case_priority(
        net_expected_recovery_inr=net_expected_recovery_inr,
        roll_forward_risk=roll_forward_risk,
        dpd=current_dpd,
        friction=friction,
    )

    return {
        "case_id": case_id,
        "customer": str(case["finance_customer_id"]),
        "case_status": case_status,
        "dpd": current_dpd,
        "outstanding_inr": outstanding_inr,
        "roll_forward_risk": roll_forward_risk,
        "best_channel": best_channel,
        "best_offer": best_offer,
        "effective_channel": effective_channel,
        "effective_offer": effective_offer,
        "best_action": _best_action_label(effective_channel, effective_offer),
        "recovery_probability": round(effective_prob * 100),
        "audit_status": audit_status,
        "approval_status": display_status,
        "governance_track": governance_track,
        "decision_code": decision_code,
        "compliance_checks": compliance_checks,
        "modified_channel": modified_channel,
        "modified_offer": modified_offer,
        "modification_reason": live_decision.modification_reason if live_decision is not None else None,
        "category": category,
        "priority": priority.level,
        "priority_points": priority.points,
        "priority_reason": priority.reason,
        "net_expected_recovery_inr": net_expected_recovery_inr,
        "scored_at": datetime.now(UTC),
        "model_version": MODEL_LABEL,
    }


def _to_case_out(case: dict[str, object]) -> CollectionsCaseOut:
    return CollectionsCaseOut(
        id=_case_uuid(str(case["case_id"])),
        case_id=str(case["case_id"]),
        customer=str(case["customer"]),
        dpd=int(case["dpd"]),  # type: ignore[arg-type]
        out=_inr(float(case["outstanding_inr"])),  # type: ignore[arg-type]
        roll=int(case["roll_forward_risk"]),  # type: ignore[arg-type]
        channel=CHANNEL_DISPLAY_NAMES[str(case["effective_channel"])],
        action=OFFER_DISPLAY_NAMES[str(case["effective_offer"])],
        best_action=str(case["best_action"]),
        prob=int(case["recovery_probability"]),  # type: ignore[arg-type]
        flag=str(case["audit_status"]),
        status=str(case["approval_status"]),
        governance_track=case["governance_track"],  # type: ignore[arg-type]
        decision_code=case["decision_code"],  # type: ignore[arg-type]
        category=case["category"],  # type: ignore[arg-type]
        priority=case["priority"],  # type: ignore[arg-type]
        priority_reason=str(case["priority_reason"]),
        scored_at=case["scored_at"],  # type: ignore[arg-type]
        model_version=str(case["model_version"]),
    )


class CollectionsService(BaseService):
    async def list_metrics(self) -> list[MetricTileOut]:
        cases = (
            await self._session.execute(
                select(
                    func.count().label("cases"),
                    func.count().filter(COLLECTION_CASES.c.case_status == "OPEN").label("open_cases"),
                    func.count().filter(COLLECTION_CASES.c.current_dpd >= 90).label("ninety_plus_dpd"),
                    func.coalesce(
                        func.sum(COLLECTION_CASES.c.current_arrears_inr),
                        0,
                    ).label("current_arrears"),
                )
            )
        ).one()
        interactions = (
            await self._session.execute(
                select(
                    func.count().label("interactions"),
                    func.count()
                    .filter(COLLECTION_INTERACTIONS.c.payment_after_contact.is_(True))
                    .label("payments_after_contact"),
                    func.count().filter(COLLECTION_INTERACTIONS.c.promise_to_pay.is_(True)).label("promises"),
                    func.count()
                    .filter(COLLECTION_INTERACTIONS.c.payment_after_promise.is_(True))
                    .label("payments_after_promise"),
                )
            )
        ).one()
        payments = (
            await self._session.execute(
                select(
                    func.coalesce(
                        func.sum(PAYMENT_HISTORY.c.actual_payment_amount_inr),
                        0,
                    ).label("actual"),
                    func.coalesce(
                        func.sum(PAYMENT_HISTORY.c.scheduled_payment_amount_inr),
                        0,
                    ).label("scheduled"),
                )
            )
        ).one()

        interaction_count = int(interactions.interactions or 0)
        promise_count = int(interactions.promises or 0)
        contact_recovery_rate = (
            int(interactions.payments_after_contact or 0) / interaction_count * 100 if interaction_count else 0.0
        )
        promise_kept_rate = (
            int(interactions.payments_after_promise or 0) / promise_count * 100 if promise_count else 0.0
        )
        payment_realization = (
            min(100.0, float(payments.actual or 0) / float(payments.scheduled) * 100)
            if float(payments.scheduled or 0)
            else 0.0
        )

        open_cases = int(cases.open_cases or 0)
        total_cases = int(cases.cases or 0)

        return [
            MetricTileOut(
                label="Open collection cases",
                value=str(open_cases),
                tone="warning" if open_cases else "success",
            ),
            MetricTileOut(
                label="Current arrears",
                value=_inr(float(cases.current_arrears or 0)),
                tone="danger" if float(cases.current_arrears or 0) else "success",
            ),
            MetricTileOut(
                label="90+ DPD cases",
                value=str(int(cases.ninety_plus_dpd or 0)),
                tone="danger" if int(cases.ninety_plus_dpd or 0) else "success",
            ),
            MetricTileOut(
                label="Payment after contact",
                value=f"{contact_recovery_rate:.1f}%",
                tone="success" if contact_recovery_rate >= 20 else "warning",
            ),
            MetricTileOut(
                label="Promise kept",
                value=f"{promise_kept_rate:.1f}%",
                tone="success" if promise_kept_rate >= 50 else "warning",
            ),
            MetricTileOut(
                label="Scheduled payment realization",
                value=f"{payment_realization:.1f}%",
                tone="success" if payment_realization >= 90 else "warning",
            ),
            MetricTileOut(
                label="Resolved cases",
                value=str(total_cases - open_cases),
                tone="success",
            ),
        ]

    async def list_agents(self) -> list[CollectionsAgentOut]:
        rows = (
            await self._session.execute(
                select(
                    COLLECTION_INTERACTIONS.c.channel,
                    func.count().label("interactions"),
                )
                .group_by(COLLECTION_INTERACTIONS.c.channel)
                .order_by(COLLECTION_INTERACTIONS.c.channel)
            )
        ).all()
        return [
            CollectionsAgentOut(
                name=f"{channel.replace('_', ' ').title()} workflow",
                status=f"{int(count)} observed interactions",
            )
            for channel, count in rows
        ]

    async def _all_case_outputs(self) -> list[dict[str, object]]:
        models = await get_or_train_models(CollectionsSimulationRepository(self._session))
        cases = (
            (
                await self._session.execute(
                    select(
                        COLLECTION_CASES,
                        LOAN_ACCOUNTS.c.principal_inr,
                        LOAN_ACCOUNTS.c.interest_rate_pct,
                        LOAN_ACCOUNTS.c.debt_service_ratio_at_origination,
                        LOAN_ACCOUNTS.c.secured,
                    )
                    .join(LOAN_ACCOUNTS, LOAN_ACCOUNTS.c.loan_account_id == COLLECTION_CASES.c.loan_account_id)
                    # Every case is returned — including resolved ones, so
                    # the frontend's "Resolved" filter has something real to
                    # show — but the final order below is by real computed
                    # priority, not this base DPD ordering (kept only as a
                    # stable tiebreaker input).
                    .order_by(
                        COLLECTION_CASES.c.current_dpd.desc(),
                        COLLECTION_CASES.c.current_arrears_inr.desc(),
                    )
                )
            )
            .mappings()
            .all()
        )
        if not cases:
            return []
        case_ids = [str(c["collection_case_id"]) for c in cases]

        interaction_rows = (
            (
                await self._session.execute(
                    select(COLLECTION_INTERACTIONS)
                    .where(COLLECTION_INTERACTIONS.c.collection_case_id.in_(case_ids))
                    .order_by(
                        COLLECTION_INTERACTIONS.c.collection_case_id,
                        COLLECTION_INTERACTIONS.c.interaction_sequence,
                    )
                )
            )
            .mappings()
            .all()
        )
        interactions_by_case: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in interaction_rows:
            interactions_by_case[str(row["collection_case_id"])].append(dict(row))

        canonical_rows = (
            (
                await self._session.execute(
                    select(TRUST_DECISIONS).where(
                        TRUST_DECISIONS.c.target_entity_type == "COLLECTION_CASE",
                        TRUST_DECISIONS.c.target_entity_id.in_(case_ids),
                    )
                )
            )
            .mappings()
            .all()
        )
        canonical_by_case = {str(row["target_entity_id"]): dict(row) for row in canonical_rows}
        decision_ids = [row["decision_id"] for row in canonical_by_case.values()]
        canonical_checks_by_decision: dict[str, list[dict[str, object]]] = defaultdict(list)
        if decision_ids:
            check_rows = (
                (
                    await self._session.execute(
                        select(COMPLIANCE_CHECKS).where(COMPLIANCE_CHECKS.c.decision_id.in_(decision_ids))
                    )
                )
                .mappings()
                .all()
            )
            for row in check_rows:
                canonical_checks_by_decision[str(row["decision_id"])].append(dict(row))

        live_decisions = await CollectionsCaseDecisionRepository(self._session).get_decisions(case_ids)

        outputs: list[dict[str, object]] = []
        for case in cases:
            case_id = str(case["collection_case_id"])
            canonical = canonical_by_case.get(case_id)
            checks = canonical_checks_by_decision.get(str(canonical["decision_id"]), []) if canonical else []
            outputs.append(
                _build_case_output(
                    dict(case),
                    interactions_by_case.get(case_id, []),
                    models,
                    canonical,
                    checks,
                    live_decisions.get(case_id),
                )
            )
        # Real priority ranking (see app/services/collections_priority.py)
        # replaces plain DPD-desc ordering — highest-priority-points first,
        # DPD as a stable tiebreaker for cases that score identically.
        outputs.sort(key=lambda row: (row["priority_points"], row["dpd"]), reverse=True)
        return outputs

    async def list_cases(self) -> list[CollectionsCaseOut]:
        return [_to_case_out(case) for case in await self._all_case_outputs()]

    async def _find_case_id(self, case_id: uuid.UUID) -> str:
        candidates = (await self._session.execute(select(COLLECTION_CASES.c.collection_case_id))).scalars().all()
        for candidate in candidates:
            if _case_uuid(str(candidate)) == case_id:
                return str(candidate)
        raise NotFoundError(f"Collections case '{case_id}' not found.", code="case_not_found")

    async def _case_output_by_id(self, case_id: str) -> dict[str, object]:
        row = (
            (
                await self._session.execute(
                    select(
                        COLLECTION_CASES,
                        LOAN_ACCOUNTS.c.principal_inr,
                        LOAN_ACCOUNTS.c.interest_rate_pct,
                        LOAN_ACCOUNTS.c.debt_service_ratio_at_origination,
                        LOAN_ACCOUNTS.c.secured,
                    )
                    .join(LOAN_ACCOUNTS, LOAN_ACCOUNTS.c.loan_account_id == COLLECTION_CASES.c.loan_account_id)
                    .where(COLLECTION_CASES.c.collection_case_id == case_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise NotFoundError(f"Collections case '{case_id}' not found.", code="case_not_found")
        interactions = [
            dict(interaction_row)
            for interaction_row in (
                await self._session.execute(
                    select(COLLECTION_INTERACTIONS)
                    .where(COLLECTION_INTERACTIONS.c.collection_case_id == case_id)
                    .order_by(COLLECTION_INTERACTIONS.c.interaction_sequence)
                )
            )
            .mappings()
            .all()
        ]
        canonical_row = (
            (
                await self._session.execute(
                    select(TRUST_DECISIONS).where(
                        TRUST_DECISIONS.c.target_entity_type == "COLLECTION_CASE",
                        TRUST_DECISIONS.c.target_entity_id == case_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        canonical = dict(canonical_row) if canonical_row is not None else None
        canonical_checks: list[dict[str, object]] = []
        if canonical is not None:
            canonical_checks = [
                dict(check_row)
                for check_row in (
                    await self._session.execute(
                        select(COMPLIANCE_CHECKS).where(COMPLIANCE_CHECKS.c.decision_id == canonical["decision_id"])
                    )
                )
                .mappings()
                .all()
            ]
        live_decision = await CollectionsCaseDecisionRepository(self._session).get_decision(case_id)
        models = await get_or_train_models(CollectionsSimulationRepository(self._session))
        return _build_case_output(dict(row), interactions, models, canonical, canonical_checks, live_decision)

    async def _decide(
        self,
        case_id: str,
        *,
        status: str,
        modified_channel: str | None = None,
        modified_offer: str | None = None,
        modification_reason: str | None = None,
        reviewer_role: str | None = None,
        reason: str | None = None,
    ) -> CollectionsCaseOut:
        current = await self._case_output_by_id(case_id)
        if current["governance_track"] == "canonical":
            raise DomainValidationError(
                "This case already has an immutable canonical governance decision from the Synthetic Data "
                "Factory's own audit history — view it via Trust Ledger; it cannot be re-decided from here.",
                code="immutable_trust_decision",
            )
        if current["case_status"] == "RESOLVED":
            raise DomainValidationError(
                f"Collections case '{case_id}' is already resolved — no action is applicable.",
                code="case_already_resolved",
            )
        repo = CollectionsCaseDecisionRepository(self._session)
        existing = await repo.get_decision(case_id)
        if existing is not None and existing.status == "APPROVED":
            raise ConflictError(
                f"Collections case '{case_id}' was already approved — a decision cannot be recorded twice.",
                code="collections_case_already_decided",
            )
        await repo.upsert_decision(
            collection_case_id=case_id,
            status=status,
            recommended_channel=str(current["best_channel"]),
            recommended_offer=str(current["best_offer"]),
            modified_channel=modified_channel,
            modified_offer=modified_offer,
            modification_reason=modification_reason,
            reviewer_role=reviewer_role,
            reason=reason,
        )
        if status == "ESCALATED":
            await repo.create_human_review(collection_case_id=case_id, reviewer_role=reviewer_role or "", reason=reason)
        return _to_case_out(await self._case_output_by_id(case_id))

    async def approve_case(self, case_id: uuid.UUID) -> CollectionsCaseOut:
        case_id_str = await self._find_case_id(case_id)
        return await self._decide(case_id_str, status="APPROVED")

    async def modify_case(self, case_id: uuid.UUID, channel: str, offer: str, reason: str) -> CollectionsCaseOut:
        case_id_str = await self._find_case_id(case_id)
        return await self._decide(
            case_id_str,
            status="APPROVED",
            modified_channel=channel,
            modified_offer=offer,
            modification_reason=reason or None,
        )

    async def review_case(self, case_id: uuid.UUID, reviewer_role: str, reason: str) -> CollectionsCaseOut:
        case_id_str = await self._find_case_id(case_id)
        return await self._decide(case_id_str, status="ESCALATED", reviewer_role=reviewer_role, reason=reason or None)

    async def get_case_trust_ledger(self, case_id: uuid.UUID) -> CaseTrustLedgerOut:
        case_id_str = await self._find_case_id(case_id)
        case = await self._case_output_by_id(case_id_str)
        compliance = case["compliance_checks"]
        if case["governance_track"] == "canonical":
            outcome = await TrustService(self._session).get_outcome(str(case["decision_code"]))
            return CaseTrustLedgerOut(
                track="canonical",
                decision_code=case["decision_code"],  # type: ignore[arg-type]
                approval=str(case["approval_status"]),
                audit_status=str(case["audit_status"]),
                compliance=compliance,  # type: ignore[arg-type]
                priority=case["priority"],  # type: ignore[arg-type]
                priority_reason=str(case["priority_reason"]),
                scored_at=case["scored_at"],  # type: ignore[arg-type]
                model_version=str(case["model_version"]),
                outcome=outcome,
            )
        return CaseTrustLedgerOut(
            track="live" if case["decision_code"] else "none",
            decision_code=case["decision_code"],  # type: ignore[arg-type]
            approval=str(case["approval_status"]),
            audit_status=str(case["audit_status"]),
            compliance=compliance,  # type: ignore[arg-type]
            priority=case["priority"],  # type: ignore[arg-type]
            priority_reason=str(case["priority_reason"]),
            scored_at=case["scored_at"],  # type: ignore[arg-type]
            model_version=str(case["model_version"]),
            recommended_channel=CHANNEL_DISPLAY_NAMES[str(case["best_channel"])],
            recommended_offer=OFFER_DISPLAY_NAMES[str(case["best_offer"])],
            modified_channel=CHANNEL_DISPLAY_NAMES[str(case["modified_channel"])] if case["modified_channel"] else None,
            modified_offer=OFFER_DISPLAY_NAMES[str(case["modified_offer"])] if case["modified_offer"] else None,
            modification_reason=case["modification_reason"],  # type: ignore[arg-type]
            # Collections AI Swarm has no execution/outcome mechanism yet,
            # the same honest gap Simulation Center runs have (see
            # app/services/trust.py's get_outcome) — never fabricated.
            outcome=OutcomeOut(outcome_status="PENDING"),
        )
