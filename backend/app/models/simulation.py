"""Simulation Center: audit trail of every what-if run."""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SimulationDomain, enum_column


class SimulationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persisted input/output snapshot of a simulation engine run."""

    __tablename__ = "simulation_runs"

    domain: Mapped[SimulationDomain] = mapped_column(enum_column(SimulationDomain, "simulation_domain"), index=True)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONType)
    outputs: Mapped[dict[str, Any]] = mapped_column(JSONType)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 100", name="confidence_range"),)
