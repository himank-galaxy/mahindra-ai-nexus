"""AI Factory: registered agents and the XR experience catalogue."""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, string_array
from app.models.enums import AgentStatus, enum_column


class AiAgent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Registered AI factory agent."""

    __tablename__ = "ai_agents"

    name: Mapped[str] = mapped_column(String(128), unique=True)
    role: Mapped[str] = mapped_column(String(128))
    status: Mapped[AgentStatus] = mapped_column(
        enum_column(AgentStatus, "agent_status", create_type=False),
        default=AgentStatus.ACTIVE,
    )
    last_activity: Mapped[str] = mapped_column(String(256))
    use_areas: Mapped[list[str]] = mapped_column(string_array(), default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class XrExperience(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """AR/VR experience card."""

    __tablename__ = "xr_experiences"

    code: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(128))
    use_case: Mapped[str] = mapped_column(String(128))
    feature: Mapped[str] = mapped_column(String(128))
    impact: Mapped[str] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
