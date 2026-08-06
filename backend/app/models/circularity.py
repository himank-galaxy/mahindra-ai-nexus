"""Circular Economy: carbon/SDG/EPR credit marketplace rows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CarbonCredit(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Tradable circularity credit with buyer-match and traceability scores."""

    __tablename__ = "carbon_credits"

    code: Mapped[str] = mapped_column(String(32), unique=True)
    type: Mapped[str] = mapped_column(String(16))
    price: Mapped[str] = mapped_column(String(32))
    buyer_match: Mapped[int] = mapped_column(Integer)
    closure_prob: Mapped[int] = mapped_column(Integer)
    traceability: Mapped[int] = mapped_column(Integer)
    repriced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    buyer_matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("buyer_match BETWEEN 0 AND 100", name="buyer_match_range"),
        CheckConstraint("closure_prob BETWEEN 0 AND 100", name="closure_prob_range"),
        CheckConstraint("traceability BETWEEN 0 AND 100", name="traceability_range"),
    )
