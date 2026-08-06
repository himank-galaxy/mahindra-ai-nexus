"""Analytics Copilot: chat sessions, messages and suggested prompts."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin, uuid_pk
from app.models.enums import CopilotRole, enum_column


class CopilotSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One copilot conversation."""

    __tablename__ = "copilot_sessions"

    title: Mapped[str | None] = mapped_column(String(256), nullable=True)

    messages: Mapped[list[CopilotMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="CopilotMessage.created_at",
    )


class CopilotMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Single chat turn; assistant turns store the full CopilotResult payload."""

    __tablename__ = "copilot_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        uuid_pk(),
        ForeignKey("copilot_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[CopilotRole] = mapped_column(enum_column(CopilotRole, "copilot_role"))
    content: Mapped[str] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped[CopilotSession] = relationship(back_populates="messages")


class SuggestedPrompt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Suggested prompt chip shown on the copilot page/panel."""

    __tablename__ = "suggested_prompts"

    text: Mapped[str] = mapped_column(Text, unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
