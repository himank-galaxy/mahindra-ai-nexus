# Warning Investigation Copilot

A conversational AI assistant embedded in the Warning Investigation screen
(`ui/investigate.html`). It explains a warning's causal graph — root cause,
upstream/downstream nodes, edge meanings, direction, lag, strength — in
plain English, and answers follow-up questions about it.

It is **grounded**: every reply is generated from a plain-English "case
file" built directly from that one warning's own data (the prediction
record and, if one has been run, its LPCMCI investigation result). The LLM
never sees any other warning, any other vehicle, or the raw database — only
the facts already on screen, restated as text.

## Why this design (RAG, without a vector database)

The plan called for RAG (retrieval-augmented generation) so the Copilot
answers from real data instead of guessing. Classic RAG uses a vector
database because the "document" pool is too big to fit in a prompt and the
relevant chunk has to be found by similarity search.

That doesn't apply here: for a single warning, the entire "document" — the
warning record plus its causal graph, already filtered down to the
target-centered subgraph the user is looking at (see
`Causal_Discovery_Service`'s graph-declutter logic, reused via
`graph_walker.py`) — comfortably fits in a single prompt. There is exactly
one relevant document per screen, not thousands to search over. So
"retrieval" here means one deterministic Python function
(`context_builder.build_case_file`) reading the right two things
(`warnings_store.get_warning` + `investigation_store.load_investigation`)
and formatting them as text — not a nearest-neighbor search. Same
grounding guarantee, without the operational cost of standing up and
maintaining a vector index for a per-warning document that never repeats.

## How it's grounded, concretely

1. `context_builder.build_case_file(warning, investigation)` turns the
   warning record and (if present) the investigation result into a
   structured plain-English case file: warning summary, analysis window,
   target node, root-cause candidate(s), upstream nodes, downstream nodes,
   uncertain-direction relationships, and a fixed set of interpretation
   notes (what "root-cause candidate" means, what edge strength means,
   that every edge already passed a p-value < 0.05 test, that this is
   statistical evidence from one vehicle's own history — not a guaranteed
   physical diagnosis).
2. That case file is folded into the system prompt for every turn — the
   model is instructed to only use facts it contains, to say plainly when
   something isn't covered, to never claim a relationship is confidently
   directed when the case file marks it `UNCERTAIN_LINK`, and to never
   present a root-cause *candidate* as a proven cause.
3. If no investigation has been run yet, the case file says so explicitly
   and instructs the model to tell the user to run one first, rather than
   inventing a graph.
4. All interpretive judgment (is this edge confidently directed? what does
   this lag number mean in real time? which edges are the same underlying
   relationship reported twice?) happens in Python in
   `context_builder.py`, using the exact same rules `ui/investigate.js`
   uses to draw the graph — never left for the LLM to infer from raw
   numbers. This is what keeps the Copilot's explanations consistent with
   what's on screen.

See `IMPLEMENTATION_PLAN.md` for the full architecture and file-by-file
breakdown.

## Configuration

The LLM endpoint is configured entirely through `Predictive_Early_Warning_Service/.env`
(gitignored) and read via `pews_config.py`:

```
OPENAI_API_BASE_URL="http://10.10.90.94:2026/v1"
OPENAI_API_KEY="..."
LLM_NAME="gpt-oss-120b"
```

`.env.example` in the service root documents the variable names with no
real values. Optional tuning knobs (all have defaults, none required):

- `PEWS_COPILOT_TEMPERATURE` (default `0.2`)
- `PEWS_COPILOT_MAX_HISTORY_TURNS` (default `10`)
- `PEWS_COPILOT_MAX_RESPONSE_TOKENS` (default `700`)

If the `.env` values are missing, `copilot/llm_client.py` raises
`CopilotNotConfiguredError`, which the API turns into an HTTP 503 — the
rest of the service (predictions, warnings, LPCMCI investigation) keeps
working with the Copilot simply unavailable.

## Files

| File | Role |
|---|---|
| `prompts.py` | The system prompt: the Copilot's persona and strict grounding rules. |
| `context_builder.py` | Builds the plain-English case file from a warning + investigation result. This is the "R" in RAG. |
| `conversation_store.py` | Per-warning conversation history, persisted as one JSON file per warning under `copilot_conversations/`. |
| `llm_client.py` | Thin wrapper around the OpenAI-compatible chat completions call, reading config from `pews_config.py`. |
| `service.py` | Orchestrates one turn: load investigation → build case file → assemble prompt with history → call the LLM → persist both turns → return the reply. |
| `IMPLEMENTATION_PLAN.md` | Full architecture, data flow, and the plan this was built from. |

Endpoints live in `api/main.py` (`/api/warnings/{id}/copilot/history`,
`/api/warnings/{id}/copilot/ask`, `DELETE /api/warnings/{id}/copilot`), and
the UI panel lives in `ui/investigate.html` / `ui/style.css` /
`ui/investigate.js`, alongside the existing causal graph it explains — not
as a separate page.

## Persistence

Conversation history is stored per-warning as
`copilot_conversations/<warning_id>.json` — the same "one JSON file per
id" pattern already used by `warnings_store.py` and `investigation_store.py`
elsewhere in this service. No new database or schema.

A turn is only persisted after a successful LLM reply, and the user's
question and the assistant's answer are written together — if the LLM
call fails, nothing is saved, so a failed attempt never leaves an
unanswered question stuck in the transcript.

## Known limitation

This LLM gateway (`gpt-oss-120b` via the configured OpenAI-compatible
endpoint) accepts only one `system` message per request, and it must be
first. The case file is therefore folded into the same system message as
the instructions rather than sent as a second system message — sending two
was confirmed (against the real endpoint) to fail with `400 System message
must be at the beginning.`
