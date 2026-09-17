"""Auto Mobility Causal Twin conversational copilot.

Orchestrates one turn: load history -> build the case file -> assemble one
flat prompt (the LlmProvider protocol only carries a single string, see
app/ai/llm/provider.py) -> call the LLM -> persist both turns -> return
the reply. Replaces the old keyword-matched POST /mobility-twin/ask (see
docs/Implementation_plan_mobility_causal.md §7).
"""

from __future__ import annotations

from app.ai.llm.provider import RuleBasedProvider
from app.ai.llm.registry import get_llm_provider
from app.ai.prompts.mobility_copilot import (
    MOBILITY_COPILOT_EXPLANATION_PROMPT,
    MOBILITY_COPILOT_SYSTEM_PROMPT,
)
from app.core.config import get_settings
from app.repositories.mobility_copilot import MobilityCopilotRepository
from app.schemas.mobility import (
    MobilityCopilotAskIn,
    MobilityCopilotAskOut,
    MobilityCopilotExplainIn,
    MobilityCopilotExplainOut,
    MobilityCopilotHistoryOut,
    MobilityCopilotTurnOut,
    MobilityViewContext,
)
from app.services.base import BaseService
from app.services.mobility_causal_cache import get_or_refresh, get_prior_state
from app.services.mobility_copilot_context import (
    build_case_file,
    build_default_explanation,
    generated_explanation_is_grounded,
    visible_metric_keys,
)
from app.services.operational_mobility import OperationalMobilityService

MAX_HISTORY_TURNS = 10


class MobilityCopilotService(BaseService):
    def __init__(self, session) -> None:  # noqa: ANN001 — matches BaseService's own untyped session param
        super().__init__(session)
        self._repository = MobilityCopilotRepository(session)

    async def _context(
        self,
        snapshot_id: str | None,
        selected_metric: str | None,
        view_context: MobilityViewContext | None,
    ):
        state = await get_or_refresh(snapshot_id)
        requested_metrics = view_context.visible_metrics if view_context else None
        visible = visible_metric_keys(state, requested_metrics)
        selected_node = None
        if selected_metric and selected_metric in visible:
            # Reuses get_node_detail() so the copilot is grounded in the
            # exact same value/trend/drivers/recommendation the user is
            # looking at on screen — never a second, possibly-divergent
            # computation.
            selected_node = await OperationalMobilityService(self._session).get_node_detail(
                selected_metric,
                state=state,
            )

        case_file = build_case_file(
            state,
            get_prior_state(),
            selected_node,
            requested_metrics=visible,
            domain_filter=view_context.domain if view_context else "All Measures",
            chain_focus=view_context.focus if view_context else False,
        )
        return state, selected_node, visible, case_file

    async def ask(self, payload: MobilityCopilotAskIn) -> MobilityCopilotAskOut:
        _, _, _, case_file = await self._context(
            payload.snapshot_id,
            payload.selected_metric,
            payload.view_context,
        )

        prior_turns = await self._repository.list_turns(payload.session_id, limit=MAX_HISTORY_TURNS)
        history_text = (
            "\n".join(f"{turn.role.upper()}: {turn.content}" for turn in prior_turns)
            if prior_turns
            else "(no earlier turns in this conversation)"
        )

        prompt = (
            f"{MOBILITY_COPILOT_SYSTEM_PROMPT}\n\n"
            f"CASE FILE:\n\n{case_file}\n\n"
            f"CONVERSATION SO FAR:\n{history_text}\n\n"
            f"USER: {payload.message}"
        )

        llm = get_llm_provider(get_settings())

        # Both turns are only persisted AFTER a successful reply, together
        # — if the LLM call fails, nothing is saved, so a failed attempt
        # doesn't leave an unanswered question stuck in the transcript
        # (same fix applied to
        # Predictive_Early_Warning_Service/copilot/service.py).
        if isinstance(llm, RuleBasedProvider):
            reply = "Conversational AI is not configured. Here is the available analysis:\n\n" + case_file
        else:
            reply = await llm.complete(prompt)

        await self._repository.append_turn(payload.session_id, "user", payload.message)
        await self._repository.append_turn(payload.session_id, "assistant", reply)

        return MobilityCopilotAskOut(reply=reply)

    async def explain(self, payload: MobilityCopilotExplainIn) -> MobilityCopilotExplainOut:
        state, selected_node, visible, case_file = await self._context(
            payload.snapshot_id,
            payload.selected_metric,
            payload.view_context,
        )
        fallback = build_default_explanation(
            state,
            selected_node,
            requested_metrics=visible,
        )
        llm = get_llm_provider(get_settings())
        if isinstance(llm, RuleBasedProvider):
            reply = fallback
        else:
            prompt = (
                f"{MOBILITY_COPILOT_SYSTEM_PROMPT}\n\n"
                f"{MOBILITY_COPILOT_EXPLANATION_PROMPT}\n\n"
                f"CASE FILE:\n\n{case_file}"
            )
            generated = (await llm.complete(prompt)).strip()
            reply = (
                generated
                if generated_explanation_is_grounded(
                    generated,
                    state,
                    selected_node,
                    requested_metrics=visible,
                )
                else fallback
            )
        return MobilityCopilotExplainOut(reply=reply)

    async def history(self, session_id: str) -> MobilityCopilotHistoryOut:
        turns = await self._repository.list_turns(session_id)
        return MobilityCopilotHistoryOut(
            session_id=session_id,
            turns=[
                MobilityCopilotTurnOut(role=turn.role, content=turn.content, created_at=turn.created_at)
                for turn in turns
            ],
        )

    async def clear(self, session_id: str) -> None:
        await self._repository.clear_turns(session_id)
