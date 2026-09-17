"""Collections & Recovery AI Swarm: agents and prioritized cases."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    AgentStatus,
    CollectionsCaseStatus,
    CollectionsComplianceFlag,
    enum_column,
)


class CollectionsAgent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Member of the collections agent swarm."""

    __tablename__ = "collections_agents"

    name: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[AgentStatus] = mapped_column(
        enum_column(AgentStatus, "agent_status"),
        default=AgentStatus.ACTIVE,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class CollectionsCase(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Delinquent account prioritized by the collections swarm."""

    __tablename__ = "collections_cases"

    customer: Mapped[str] = mapped_column(String(128))
    dpd: Mapped[int] = mapped_column(Integer)
    outstanding: Mapped[str] = mapped_column(String(32))
    roll_forward_risk: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(128))
    prob: Mapped[int] = mapped_column(Integer)
    compliance_flag: Mapped[CollectionsComplianceFlag] = mapped_column(
        enum_column(CollectionsComplianceFlag, "collections_compliance_flag"),
        default=CollectionsComplianceFlag.OK,
    )
    status: Mapped[CollectionsCaseStatus] = mapped_column(
        enum_column(CollectionsCaseStatus, "collections_case_status"),
        default=CollectionsCaseStatus.PENDING,
    )
    modified_action: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("roll_forward_risk BETWEEN 0 AND 100", name="roll_forward_risk_range"),
        CheckConstraint("prob BETWEEN 0 AND 100", name="prob_range"),
    )
