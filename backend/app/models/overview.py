"""Executive Overview: KPI cards, drivers and AI recommendations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, uuid_pk
from app.models.enums import RecommendationRisk, RecommendationStatus, enum_column


class Kpi(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Executive overview KPI card."""

    __tablename__ = "kpis"

    code: Mapped[str] = mapped_column(String(32), unique=True)
    label: Mapped[str] = mapped_column(String(128))
    value: Mapped[str] = mapped_column(String(64))
    trend: Mapped[str] = mapped_column(String(32))
    trend_up: Mapped[bool] = mapped_column(Boolean, default=True)
    confidence: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    drivers: Mapped[list[KpiDriver]] = relationship(
        back_populates="kpi",
        cascade="all, delete-orphan",
        order_by="KpiDriver.sort_order",
    )

    __table_args__ = (CheckConstraint("confidence BETWEEN 0 AND 100", name="confidence_range"),)


class KpiDriver(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Bullet driver explaining a KPI movement (owned by its KPI)."""

    __tablename__ = "kpi_drivers"

    kpi_id: Mapped[uuid.UUID] = mapped_column(
        uuid_pk(),
        ForeignKey("kpis.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    driver_text: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    kpi: Mapped[Kpi] = relationship(back_populates="drivers")


class Recommendation(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Actionable AI recommendation surfaced on the overview page."""

    __tablename__ = "recommendations"

    code: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(Text)
    impact: Mapped[str] = mapped_column(String(128))
    confidence: Mapped[int] = mapped_column(Integer)
    risk: Mapped[RecommendationRisk] = mapped_column(enum_column(RecommendationRisk, "recommendation_risk"))
    status: Mapped[RecommendationStatus] = mapped_column(
        enum_column(RecommendationStatus, "recommendation_status"),
        default=RecommendationStatus.PENDING,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0 AND 100", name="confidence_range"),
        Index("ix_recommendations_status_pending", "status", postgresql_where="status = 'pending'"),
    )
