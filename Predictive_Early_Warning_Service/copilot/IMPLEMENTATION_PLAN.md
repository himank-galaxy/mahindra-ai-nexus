# Warning Investigation Copilot — Implementation Plan

This is the plan the Copilot was actually built from, kept here as a
record of the design decisions. See `README.md` for the shorter,
usage-oriented summary.

## 1. RAG architecture

**Context-window RAG, not vector-database RAG.**

Classic RAG exists to solve retrieval over a large, heterogeneous document
pool: embed everything, index it, and pull back the top-k chunks similar
to the query. That problem doesn't exist here. Each warning has exactly
one relevant "document" — its own case file — and that document is small
enough (a warning record plus a target-centered causal graph, already
pruned to a few dozen nodes/edges at most) to fit entirely inside a single
prompt.

So "retrieval" is one deterministic function,
`context_builder.build_case_file(warning, investigation)`, not a
similarity search:

1. Look up the warning record (`warnings_store.get_warning`).
2. Look up its investigation result, if one has been run
   (`investigation_store.load_investigation`) — durable storage, survives
   an API restart.
3. Format both as a structured plain-English case file.
4. Fold that case file into the system prompt for every turn of that
   warning's conversation.

This is retrieval-augmented in the sense that matters — the model answers
from real, warning-specific data rather than its own generic knowledge —
without the operational overhead of a vector index for documents that are
never searched, only ever read once in full.

## 2. Data retrieved

For a given `warning_id`:

- **Warning record** (`warnings_store.get_warning`): warning type, vehicle
  ID, target metric, predicted risk probability, forecast window
  (`forecast_gap_hours` → `forecast_horizon_hours`), severity, status,
  detection timestamp.
- **Investigation result**, if present (`investigation_store.load_investigation`):
  - `window_start` / `window_end` — the exact historical window LPCMCI
    analyzed for this vehicle.
  - `panel_shape` — (time-steps, variables) analyzed.
  - `classifications` — every node's role relative to the target
    (`TARGET`, `ROOT_CANDIDATE`, `UPSTREAM`, `DOWNSTREAM`,
    `UNCERTAIN_LINK`) and its hop-distance, from `graph_walker.py`'s
    BFS walk — the same source of truth `ui/investigate.js` uses to color
    and filter the graph shown on screen.
  - `graph.edges` — source, target, lag, strength, edge mark, p-value for
    every causal link LPCMCI found.

Nothing outside this one warning is retrieved. No other vehicle's data, no
raw database query, no other warning's graph — the Copilot cannot answer
about anything not already visible on the Warning Investigation screen for
this specific warning.

## 3. Graph-to-context conversion

Handled entirely in `context_builder.py`, in plain Python — no LLM
involved in this step, so the interpretation is deterministic and
consistent with the graph the user sees.

- **Mirrored-edge merge**: LPCMCI reports the same lag-0 relationship as
  both `A -> B` and `B -> A`. `_merge_mirrored_edges` collapses these to
  one line per `(unordered pair, lag)`, keeping the stronger `|strength|`
  — the identical rule `ui/investigate.js` already applies when drawing
  the graph, duplicated in Python so the case file matches what's on
  screen.
- **Lag → real time**: `_lag_to_text` converts a lag step count into
  "N minutes earlier" / "N hours earlier" using `CAUSAL_RESAMPLE_MINUTES`,
  instead of leaving the model to guess what a raw lag integer means.
- **Direction confidence**: an edge is described as "confidently
  directed" only if its edge mark is `-->` or `<--`; every other mark
  (`<->`, `o-o`, `o->`, `<-o`) is described as "direction UNCERTAIN" —
  this is the same distinction `graph_walker.py` uses to decide whether an
  edge can be walked during the BFS at all.
- **Case file sections**, in order: WARNING SUMMARY, (CAUSAL ANALYSIS
  WINDOW / TARGET NODE / ROOT-CAUSE CANDIDATE(S) / UPSTREAM NODES /
  DOWNSTREAM NODES / UNCERTAIN-DIRECTION RELATIONSHIPS — only if an
  investigation has run), IMPORTANT INTERPRETATION NOTES. Each root-cause
  candidate and uncertain-direction node lists its actual edges
  (`_describe_edge`), with strength, sign, direction, edge mark, and
  p-value spelled out in words.
- If no investigation has been run yet, the case file stops after the
  warning summary and explicitly tells the model it does not have a
  graph, so it can correctly tell the user to run one instead of
  fabricating one.

## 4. Conversation history handling

- One JSON file per warning: `copilot_conversations/<warning_id>.json`,
  written by `conversation_store.py` — the same one-file-per-id pattern
  already used by `warnings_store.py` and `investigation_store.py`. No new
  database or schema.
- `recent_turns_for_prompt(warning_id)` returns only the last
  `PEWS_COPILOT_MAX_HISTORY_TURNS` turns (default 10) to bound prompt
  size; the full history is still persisted and returned in full by the
  history endpoint for display.
- A turn is appended only *after* a successful LLM reply, and the user's
  question and the assistant's answer are written together in
  `service.ask_copilot`. If the LLM call raises, neither turn is saved —
  a failed attempt never leaves an unanswered question permanently stuck
  in the transcript (this was an actual bug during development; see the
  "known limitation" note below and the fix it prompted).
- `DELETE /api/warnings/{warning_id}/copilot` clears a warning's
  conversation entirely (`conversation_store.clear_conversation`), wired
  to the "Clear chat" button in the UI.

## 5. Backend / API architecture

New module: `Predictive_Early_Warning_Service/copilot/` — a self-contained
package with no FastAPI dependency of its own (only `service.py` is
imported by the API layer), so it could be tested or reused standalone:

```
copilot/
  __init__.py
  prompts.py            system prompt + grounding rules
  context_builder.py    warning + investigation -> case file text
  conversation_store.py per-warning JSON conversation history
  llm_client.py          OpenAI-compatible chat completion call
  service.py             orchestrates one turn end-to-end
  copilot_conversations/ (runtime data, one JSON file per warning_id)
```

`api/main.py` adds `copilot/` to `sys.path` (alongside the existing
service-root insert) and three endpoints:

- `GET /api/warnings/{warning_id}/copilot/history` — full turn history.
- `POST /api/warnings/{warning_id}/copilot/ask` — body `{"message": str}`,
  calls `service.ask_copilot(warning.__dict__, message)`. Maps
  `CopilotNotConfiguredError` (missing `.env` values) to HTTP 503, any
  other failure (LLM call error, etc.) to HTTP 502.
- `DELETE /api/warnings/{warning_id}/copilot` — clears history.

Also added in this same change: `investigation_store.py` and
`GET /api/warnings/{warning_id}/investigation` — a durable, warning-id-keyed
lookup for investigation results. This was a pre-existing gap unrelated to
the LLM itself: investigation results previously only lived in
`api/main.py`'s in-memory `_JOBS` dict, wiped on every API restart, which
would have made the Copilot (and reopening an old warning generally)
unable to explain any investigation older than the last restart. Now
`_run_investigation` persists to this store immediately after completing,
and both the UI's page-load and the Copilot read from it.

## 6. UI design

Added directly to the existing Warning Investigation screen
(`ui/investigate.html`), as a new panel below the causal graph and
classifications table — not a separate screen, since the Copilot exists to
explain what's already on screen, not to replace it.

- A chat-style message list (`#copilotMessages`), user bubbles
  right-aligned, assistant bubbles left-aligned, a `pending`
  ("Thinking...") bubble shown while a request is in flight and removed
  once it resolves, and an `error` bubble style if a request fails.
- Six suggestion chips pre-filled with the task's required question
  categories (why generated, root cause, target meaning, upstream
  influence, downstream effects, overall confidence) — clicking one sends
  it immediately, same as typing and submitting.
- A text input + Send button (`#copilotForm`/`#copilotInput`), and a
  "Clear chat" button that calls the `DELETE` endpoint and empties the
  message list.
- A disabled state (`#copilotDisabledNote`, input and Send both
  `disabled`) shown until an investigation exists for this warning — set
  from `ui/investigate.js`'s `setCopilotEnabled(false)` — with the note
  "Run the investigation above first." The panel becomes visible on page
  load either way, so the user always sees it's there before the state
  resolves.
- A framing line, always visible, under the input: "This is statistical
  evidence from LPCMCI, explained by an LLM - not a guaranteed physical
  diagnosis. The Copilot only knows what's in the analysis above."
- On page load, `ui/investigate.js` now calls the new durable
  `/investigation` endpoint automatically (`loadExistingInvestigation`).
  If a result already exists, it's rendered immediately and the Copilot
  panel is enabled with its history preloaded — the user does not have to
  re-run LPCMCI just to re-open an old investigation or ask it more
  questions.

## 7. Hallucination prevention

Enforced at two layers:

1. **Data layer** — the model is never given raw numbers to interpret on
   its own. Every judgment call (is this direction confident? what role
   does this node play? what does this lag mean in real time?) is made in
   `context_builder.py` before the prompt is built, so there's nothing
   left for the model to get wrong about the underlying graph structure.
2. **Prompt layer** — `prompts.py`'s `SYSTEM_PROMPT` states explicit,
   numbered rules: only use facts in the case file; if asked something
   the case file doesn't cover, say so plainly rather than guessing; never
   present a root-cause *candidate* as a proven cause; never claim a
   relationship is confidently directed when the case file marks it
   uncertain; keep answers short and conversational; this is one
   vehicle's own historical data analyzed statistically, not a certainty.

This was verified against the real endpoint, not just written and
assumed: a follow-up question ("is this vehicle definitely going to
overheat?") correctly produced "No, it is not guaranteed... not a
certainty" rather than an overconfident answer, and root-cause questions
consistently used the case file's own "candidate" framing rather than
asserting causation outright.

## 8. Files touched

New:
- `copilot/__init__.py`
- `copilot/prompts.py`
- `copilot/context_builder.py`
- `copilot/conversation_store.py`
- `copilot/llm_client.py`
- `copilot/service.py`
- `copilot/README.md`, `copilot/IMPLEMENTATION_PLAN.md` (this file)
- `investigation_store.py` (durable investigation persistence, not
  Copilot-specific but required for it)
- `.env`, `.env.example` (service root)

Modified:
- `pews_config.py` — loads `.env`, exposes `OPENAI_API_BASE_URL`,
  `OPENAI_API_KEY`, `LLM_NAME`, and the `COPILOT_*` tuning knobs.
- `api/main.py` — `copilot/` added to `sys.path`; new investigation and
  Copilot endpoints; `_run_investigation` now calls `save_investigation`.
- `ui/investigate.html` — new Copilot panel section.
- `ui/style.css` — new `.suggestion-chip`, `.copilot-messages`,
  `.copilot-bubble` (+ `.user`/`.assistant`/`.pending`/`.error`),
  `.copilot-input-row`, `.secondary-btn` rules.
- `ui/investigate.js` — `loadExistingInvestigation`, `setCopilotEnabled`,
  `appendBubble`, `loadCopilotHistory`, `sendCopilotMessage`, and the
  event listeners wiring the panel's form, suggestion chips, and clear
  button to the new endpoints.
- `requirements.txt` — added `python-dotenv`, `openai`.

## Known limitation

The configured LLM gateway (`gpt-oss-120b`) accepts only one `system`
message per request and requires it to be first — sending the
instructions and the case file as two separate system messages was
confirmed (against the real endpoint) to fail with
`400 System message must be at the beginning.` `service.ask_copilot`
folds both into a single system message to work around this.
