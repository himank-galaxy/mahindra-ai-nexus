"""Compliance Trust Ledger: decisions, rules, lineage and approval actions."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cached_read
from app.core.errors import NotFoundError
from app.models import TrustDecision
from app.models.enums import TrustApproval
from app.repositories import TrustRepository
from app.schemas.trust import ComplianceRuleOut, LineageStepOut, TrustDecisionOut
from app.services.base import BaseService
from app.utils.display import TRUST_APPROVAL_DISPLAY, TRUST_AUDIT_DISPLAY, TRUST_RISK_DISPLAY


class TrustService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._repo = TrustRepository(session)

    async def list_decisions(self) -> list[TrustDecisionOut]:
        decisions = await self._repo.list_all()
        return [self._to_out(decision) for decision in decisions]

    async def list_rules(self) -> list[ComplianceRuleOut]:
        return await cached_read("trust:rules", self._load_rules)

    async def _load_rules(self) -> list[ComplianceRuleOut]:
        rules = await self._repo.list_rules()
        return [ComplianceRuleOut(label=rule.label, status=rule.status) for rule in rules]

    async def get_lineage(self, code: str) -> list[LineageStepOut]:
        decision = await self._get_decision(code)
        return [
            LineageStepOut(step=step["step"], title=step["title"], detail=step.get("detail"))
            for step in decision.lineage
        ]

    async def approve_decision(self, code: str) -> TrustDecisionOut:
        """Approve the audited AI decision."""
        decision = await self._get_decision(code)
        decision.approval = TrustApproval.APPROVED
        await self._session.commit()
        return self._to_out(decision)

    async def reject_decision(self, code: str, reason: str) -> TrustDecisionOut:
        """Reject the decision, optionally recording a reason."""
        decision = await self._get_decision(code)
        decision.approval = TrustApproval.REJECTED
        decision.rejection_reason = reason or None
        await self._session.commit()
        return self._to_out(decision)

    async def escalate_decision(self, code: str) -> TrustDecisionOut:
        """Escalate the decision to the compliance officer."""
        decision = await self._get_decision(code)
        decision.approval = TrustApproval.ESCALATED
        await self._session.commit()
        return self._to_out(decision)

    async def _get_decision(self, code: str) -> TrustDecision:
        decision = await self._repo.get_by_code(code)
        if decision is None:
            raise NotFoundError(f"Trust decision '{code}' not found.", code="decision_not_found")
        return decision

    @staticmethod
    def _to_out(decision: TrustDecision) -> TrustDecisionOut:
        return TrustDecisionOut(
            id=decision.code,
            use=decision.use_case,
            rec=decision.recommendation,
            data=decision.data_sources,
            conf=decision.confidence,
            approval=TRUST_APPROVAL_DISPLAY[decision.approval],
            risk=TRUST_RISK_DISPLAY[decision.risk],
            audit=TRUST_AUDIT_DISPLAY[decision.audit],
        )
