"""Compliance Trust Ledger: audited AI decisions and compliance rules."""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, JSONType, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TrustApproval, TrustAudit, TrustRisk, enum_column


class TrustDecision(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """One auditable AI decision with lineage and approval state."""

    __tablename__ = "trust_decisions"

    code: Mapped[str] = mapped_column(String(32), unique=True)
    use_case: Mapped[str] = mapped_column(String(256))
    recommendation: Mapped[str] = mapped_column(String(256))
    data_sources: Mapped[str] = mapped_column(String(256))
    confidence: Mapped[int] = mapped_column(Integer)
    approval: Mapped[TrustApproval] = mapped_column(
        enum_column(TrustApproval, "trust_approval"),
        default=TrustApproval.PENDING,
    )
    risk: Mapped[TrustRisk] = mapped_column(enum_column(TrustRisk, "trust_risk"))
    audit: Mapped[TrustAudit] = mapped_column(
        enum_column(TrustAudit, "trust_audit"),
        default=TrustAudit.PENDING,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    lineage: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (CheckConstraint("confidence BETWEEN 0 AND 100", name="confidence_range"),)


class ComplianceRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Compliance rule check shown in the trust sidebar."""

    __tablename__ = "compliance_rules"

    label: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="OK")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
