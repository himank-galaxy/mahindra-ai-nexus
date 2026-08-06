"""Logistics Control Tower: routes and warehouse signal tiles."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SignalPanel, enum_column


class LogisticsRoute(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Freight corridor with predictive SLA metrics."""

    __tablename__ = "logistics_routes"

    name: Mapped[str] = mapped_column(String(128), unique=True)
    sla_risk: Mapped[int] = mapped_column(Integer)
    delay_prob: Mapped[int] = mapped_column(Integer)
    cost: Mapped[str] = mapped_column(String(32))
    recommended_action: Mapped[str] = mapped_column(String(128))
    rerouted: Mapped[bool] = mapped_column(Boolean, default=False)
    rerouted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_healed: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        CheckConstraint("sla_risk BETWEEN 0 AND 100", name="sla_risk_range"),
        CheckConstraint("delay_prob BETWEEN 0 AND 100", name="delay_prob_range"),
    )


class WarehouseSignal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Signal tile; ``panel`` scopes rows to warehouse / collections / RVSF UIs."""

    __tablename__ = "warehouse_signals"

    panel: Mapped[SignalPanel] = mapped_column(
        enum_column(SignalPanel, "signal_panel"),
        default=SignalPanel.WAREHOUSE,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(128))
    value: Mapped[str] = mapped_column(String(64))
    tone: Mapped[str] = mapped_column(String(16), default="success")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
