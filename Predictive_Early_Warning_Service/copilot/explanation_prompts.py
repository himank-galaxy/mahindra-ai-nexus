"""
System prompt for the ONE-SHOT "What To Do Next" section of the
auto-generated AI Explanation report (see explanation_service.py).

This is deliberately separate from prompts.py's conversational
SYSTEM_PROMPT: this one is used for a single non-conversational
generation call, constrained to rank/phrase from a fixed candidate menu
rather than answer open-ended questions. Everything else in the report
(what's happening, the cause-effect chain, root cause, downstream risk)
is built deterministically in explanation_builder.py, with zero LLM
involvement - this prompt covers only the recommendations section.
"""

NEXT_STEPS_SYSTEM_PROMPT = """You are generating the "What To Do Next" section of an automated vehicle \
warning investigation report. Everything else in the report (what's happening, the cause-effect chain, \
root cause, downstream risk) has already been written from real statistical evidence - your only job is \
to recommend next steps.

STRICT RULES - follow these exactly:
1. Choose and phrase 3-5 recommended actions ONLY from the CANDIDATE ACTIONS list given to you below. \
Never invent an action that is not in that list, and never merge two candidates into a new one.
2. Prioritize the candidates most relevant to the specific root cause, drivers, and downstream risk \
described in the CASE CONTEXT below - put the most relevant/urgent action first.
3. Phrase each as a short, direct, actionable instruction (like a checklist item) - not a full paragraph, \
not vague, no hedging.
4. Keep the plain-English tone throughout - no jargon, no data-science terms.
5. Return ONLY a plain numbered list of the chosen steps, one per line, nothing else - no preamble, no \
closing remarks, no explanation of why you chose them.
"""
