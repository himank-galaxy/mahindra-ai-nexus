"""Reference data: regions and vehicle models (natural string keys)."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Region(Base):
    """Sales region reference (West, North, South, East)."""

    __tablename__ = "regions"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)


class VehicleModel(Base):
    """Vehicle model reference (XUV700, Scorpio-N, ...)."""

    __tablename__ = "vehicle_models"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
