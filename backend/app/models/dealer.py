"""Dealer Revenue Optimizer: dealers and AI-scored leads."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, uuid_pk
from app.models.enums import DealerLeadStatus, enum_column


class Dealer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Dealership with headline operating metrics."""

    __tablename__ = "dealers"

    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    leads: Mapped[int] = mapped_column(Integer)
    hot_leads: Mapped[int] = mapped_column(Integer)
    test_drives_pending: Mapped[int] = mapped_column(Integer)
    booking_prob: Mapped[int] = mapped_column(Integer)
    revenue_at_risk: Mapped[str] = mapped_column(String(32))
    leakage_pct: Mapped[int] = mapped_column(Integer)
    bay_util_pct: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    leads_: Mapped[list[DealerLead]] = relationship(
        back_populates="dealer",
        cascade="all, delete-orphan",
        order_by="DealerLead.sort_order",
    )

    __table_args__ = (
        CheckConstraint("booking_prob BETWEEN 0 AND 100", name="booking_prob_range"),
        CheckConstraint("leakage_pct BETWEEN 0 AND 100", name="leakage_pct_range"),
        CheckConstraint("bay_util_pct BETWEEN 0 AND 100", name="bay_util_pct_range"),
    )


class DealerLead(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """AI-scored lead owned by a dealer."""

    __tablename__ = "dealer_leads"

    dealer_id: Mapped[uuid.UUID] = mapped_column(
        uuid_pk(),
        ForeignKey("dealers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128))
    vehicle: Mapped[str] = mapped_column(String(64))
    score: Mapped[int] = mapped_column(Integer)
    prob: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(256))
    revenue: Mapped[str] = mapped_column(String(32))
    status: Mapped[DealerLeadStatus] = mapped_column(
        enum_column(DealerLeadStatus, "dealer_lead_status"),
        default=DealerLeadStatus.WARM,
    )
    test_drive_slot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    dealer: Mapped[Dealer] = relationship(back_populates="leads_")

    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),
        CheckConstraint("prob BETWEEN 0 AND 100", name="prob_range"),
    )
