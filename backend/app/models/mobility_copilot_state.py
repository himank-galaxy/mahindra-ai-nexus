"""Auto Mobility Causal Twin copilot conversation history (ai_state schema).

One row per turn (user question or assistant reply), keyed by a
client-generated session_id — the same "one thread per id" shape as
Predictive_Early_Warning_Service/copilot/conversation_store.py, just as a
migrated database table instead of local JSON files (see
docs/Implementation_plan_mobility_causal.md §7).

Lives in the ai_state schema (alembic_ai_state.ini / app/database/ai_state_base.py),
NOT the generic app.models Base — that lineage has no working Alembic
migration in this codebase (app/models/copilot.py's CopilotSession/
CopilotMessage were never migrated and do not exist in the live database;
confirmed against the real database before choosing this schema). ai_state
is the real, working lineage already used for persisted AI-adjacent state
such as the manufacturing/telematics causal run tables — see
app/models/causal_runtime_state.py for the sibling pattern this follows.
"""

from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.ai_state_base import AI_STATE_SCHEMA, AiStateBase
from app.database.base import TimestampMixin


class MobilityCopilotTurn(TimestampMixin, AiStateBase):
    """One turn in a mobility copilot conversation.

    `role` is a plain string ("user" / "assistant") rather than a
    Postgres ENUM, matching how conversation_store.py already models this
    elsewhere in the project — avoids the schema-qualification questions a
    cross-schema ENUM type would raise for no real benefit at this scale.
    """

    __tablename__ = "mobility_copilot_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = {"schema": AI_STATE_SCHEMA}
