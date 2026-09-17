# Auto Mobility Causal Twin — implementation plan

Turns the Auto Mobility Causal Twin screen from a static mock-data page into
a working screen backed by real, live, minute-cadence data — using the
architecture that already exists for it (`backend/app/services/operational_mobility.py`
and friends), fixed and extended, not replaced with the replay/scheduler
machinery built for Manufacturing/Telematics.

```
Live_Data_Formation/Mobility_Timeseries/          per-minute generator
        │  (already running — see Live_Data_Formation)
        ▼
public.mobility_timeseries                        runtime table, live,
                                                    no replay/ingestion layer
        │  plain SQL read, on request
        ▼
ai/causal/data_loader.py                          region → national panel,
                                                    11 business metrics
        │
        ▼
ai/causal/preprocessing.standardize + pcmci_engine.run_pcmci
        │  window = 28 days (40,320 rows), tau_max = 360 (6h), pc_alpha configurable
        ▼
ai/causal/edge_filter.py (business-sane directions) + graph_builder.py
        │
        ▼
FastAPI  /api/v1/mobility-twin/{graph,kpis,nodes/{metric},copilot/*}
        │
        ▼
Auto Mobility Causal Twin screen — same layout as today, real data
```

This is deliberately **not** a copy of the Warranty & Quality pipeline
(`docs/LIVE_CAUSAL_PIPELINE.md`). That pipeline exists to reconcile a
*simulated replay clock* over frozen historical data across two domains with
non-overlapping source windows. `mobility_timeseries` has no replay clock —
it is written live, every real minute, by `Live_Data_Formation/`. There is
nothing to reconcile, so there is no replay-ingestor, no per-domain
watermark, and no persisted causal-run history table in this plan. Every
computation simply reads `mobility_timeseries` as it currently stands.

## 1. What already exists (do not rebuild this — fix and extend it)

- `frontend/src/routes/mobility-twin.tsx` — the screen. Currently renders
  hardcoded `NODES`/`EDGES`/`ASKS` arrays. Already calls
  `useMobilityKpis()`/`useMobilityGraph()`/`useAskAnswer(askMobilityTwin)`,
  preferring the API result over the mock data when present — so once the
  backend returns real data, most of the wiring gap closes on its own.
- `backend/app/api/v1/mobility.py` — `GET /mobility-twin/graph`,
  `GET /mobility-twin/kpis`, `POST /mobility-twin/ask`, already live.
- `backend/app/services/operational_mobility.py` (`OperationalMobilityService`,
  aliased `MobilityService` in the router) — reads `mobility_timeseries` via
  `data_loader.py`, runs PCMCI, filters/renders via `edge_filter.py` +
  `graph_builder.py`, answers "ask" by keyword match. This is the one and
  only real backend for the screen (`services/mobility.py`'s static-seed
  version is dead code, confirmed unreferenced by any route — leave it
  alone).
- `ai/causal/data_loader.py` — `load_daily_causal_input()`, aggregates all 4
  regions into one national panel per minute-window, computing 11 metrics:
  `lead_volume`, `lead_engagement_score`, `dealer_followup_rate`,
  `test_drive_completion_rate`, `booking_conversion_rate`,
  `finance_approval_rate`, `vehicle_allocation_count`,
  `allocation_delay_days`, `delivery_delay_days`, `cancellation_rate`,
  `revenue`.
- `ai/causal/pcmci_engine.py` — generic, reusable causal-discovery core.
  Already called via `run_pcmci` (plain PCMCI) — this plan keeps that engine
  choice (see §3; LPCMCI was considered and dropped per explicit
  instruction).
- `ai/causal/edge_filter.py` — a fixed whitelist of business-sane directed
  metric pairs (`ALLOWED_RELATIONSHIPS`).
- `ai/causal/graph_builder.py` — hardcoded node layout coordinates
  (`DISPLAY` dict) and, today, a **single hardcoded action string per
  metric** — this is the entire current "recommended action" mechanism and
  is one of the things this plan replaces with something real.
- `backend/app/ai/llm/provider.py` / `registry.py` + `Settings.ai_provider` /
  `openai_api_key` — a prepared seam for a real LLM provider. Currently the
  only implementation, `RuleBasedProvider`, is not actually LLM-backed —
  `ai_provider="openai"` logs a warning and silently falls back to rules.

## 2. Real bugs to fix as part of this work (not new features)

- **`windows_per_week = 14` in `operational_mobility.py`** means "the last
  14 rows" — which, now that `mobility_timeseries` is minute-cadence, is
  the last 14 *minutes*, mislabeled everywhere as "vs prior week." Replace
  with an explicitly-named, correctly-sized comparison window (e.g. latest
  60 minutes vs. the 60 minutes before that, or whatever window is chosen
  once this is live and tunable — the point is it must be named for what it
  actually is, not left as a stale weekly assumption).
- **`_EDGE_CACHE`** is a bare module-level dict keyed by an input-array
  hash. Keep the idea (cheap re-use when nothing changed) but make sure it
  actually invalidates correctly as new minutes arrive rather than quietly
  accumulating.
- **Recommended actions are static text**, not derived from data at all —
  replaced in §5 below.

## 3. PCMCI configuration (revised 2026-09-07 — sampling stride fix)

**Why this changed**: every `mobility_timeseries` row is itself a trailing
12-HOUR ROLLING window, rewritten every real minute — so two rows a minute
apart share ~99.86% of the same underlying 12 hours. The original design
(§3 v1) sampled every 1-minute row, which fed PCMCI a sequence of
near-duplicate observations — manufactured autocorrelation from the
rolling-window construction, not genuine timing, and the graph barely
appeared to move because 40,320 rows of that duplication anchored any new
data to almost nothing. Diagnosed from real user observation ("the graph
didn't change in one hour") plus first-principles review of the rolling
window mechanics.

- **Engine**: still plain `run_pcmci`, unchanged — see the original
  reasoning above (kept for reference below this revision).
- **Sampling stride: 12 hours** (`mobility_causal_sample_stride_hours`,
  default 12) — matches the rolling window's own length exactly, so
  consecutive sampled observations are fully independent: zero overlap,
  zero gap. Implemented in `data_loader.py` via a SQL `date_bin` + `DISTINCT
  ON`-style query that picks one representative tick (all regions) per
  stride bucket, rather than pulling every 1-minute row and discarding
  most of it in Python.
- **Window (lookback ceiling): 90 days** (`mobility_causal_window_days`,
  default 90, was 28) — a target, not a promise: real accumulated history
  is currently far short of 90 days, so whatever's actually available is
  used. Chosen as a realistic ~2-month target rather than the originally
  discussed 180 days, which is roughly 6 months out from when this was
  decided.
- **Minimum observations floor: 50** (`mobility_causal_min_observations`,
  default 50, was a hardcoded 90) — lowered because at a 12h stride, real
  history today (~30-34 days) yields only ~60-70 observations, below the
  old hardcoded floor. This lets the graph run now instead of blocking for
  months; results this close to the floor are lower-confidence than a
  fully-populated window, and the copilot's case file says so explicitly
  when asked (see §7).
- **tau_max: 2** (`mobility_causal_tau_max`, default 2, was 360) — now
  expressed in SAMPLE STEPS, not minutes, since the panel is no longer
  1-minute cadence (2 steps × 12h stride = 24 hours). Deliberately narrow
  while real observation counts are low (~50-70) — testing more lags
  spreads the same small sample across more hypotheses. **Revisit once
  real history passes ~90 days (~180 observations)**: widen the sweep to
  include 4-6 steps (2-3 days), since `allocation_delay_days`/
  `delivery_delay_days` are plausibly multi-day processes a 24-hour cap
  could miss.
- **pc_alpha**: unchanged, 0.05.
- Real measured effect of this change: `refresh()` dropped from ~217
  seconds to ~1.1 seconds (tau_max 360→2, observations 40,320→70), and the
  discovered edges changed qualitatively — lags now express as clean
  business timescales ("24 hours earlier") instead of odd minute counts,
  and the specific relationships found shifted (e.g. a genuine
  `lead_volume → dealer_followup_rate` relationship appeared that the
  1-minute-stride version never found).
- `edge.lag` from PCMCI is in sample steps, not minutes — every place that
  renders a lag (node-detail relationships, the copilot's case file, the
  recommended-action prompt, the frontend) converts through
  `graph_builder.format_duration_minutes()` (backend) / a matching
  frontend helper, so a lag always reads as real time ("24 hours"), never
  a raw step count.

## 4. How the graph stays synchronized with new data (revised)

No scheduler, no background service, no persisted run-history table needed
— every fresh computation reads `mobility_timeseries` as it currently
stands, so the result is always "as of right now" at the moment it runs.

- **The refresh loop wakes every 60 minutes to CHECK, but only actually
  recomputes when a new complete 12-hour sample bucket has become
  available** since the last recompute — at the default 12h stride, that
  means an actual PCMCI run happens roughly twice a day even though the
  check runs hourly. Re-running PCMCI when the sampled panel hasn't
  changed would just reproduce the same result for the full cost of a run.
  Implemented via a bucket-index comparison in
  `mobility_causal_cache.py` (`_bucket_index`/`_last_computed_bucket`).
- **Mechanism**: still a background asyncio task inside the same backend
  process (no new docker service) — but the PCMCI call itself is now
  wrapped in `asyncio.to_thread()`. This was a real bug caught during the
  first live deployment: `run_pcmci` is synchronous/CPU-bound, and calling
  it directly inside `async def refresh()` blocked the entire process's
  event loop for the full computation — freezing *every* endpoint (not
  just mobility ones), which was the actual root cause of the backend
  container's pre-existing "unhealthy" Docker status. Fixed by running it
  on a worker thread instead.
- "What changed recently" (for the copilot, §7) is answered by keeping the
  *previous* computed result alongside the *latest* one (two values, not a
  history table) and diffing edges (new / removed / strengthened /
  weakened / sign-changed) between them — now "since the last 12-hour
  sample" rather than "since the last hour."
- The copilot's case file also reports the real observation count against
  the configured floor/target, and explicitly flags lower confidence when
  the graph is running on a smaller-than-ideal sample — see §7.

## 5. Node click → node-detail view

New endpoint `GET /mobility-twin/nodes/{metric}`, new service method,
returning:

- **Current/latest value** — same aggregation `data_loader.py` already
  does, latest window.
- **Recent trend/history** — a short time series of that one metric
  (national, and optionally per-region) for a sparkline; a lightweight new
  query against `mobility_timeseries`, independent of the PCMCI run.
- **Stats/KPIs for that variable** — real `avg()`/`min()`/`max()`/`stddev()`
  SQL aggregates over a rolling window (same measured-not-guessed principle
  used for the PEWS thresholds), not hardcoded.
- **Strongest causal relationships** — read from the latest computed graph,
  edges touching this metric in either direction, sorted by `|score|`.
- **Top drivers** — confidently-directed edges pointing *into* this node
  from the latest graph. This is a plain graph-adjacency read, not a
  root-cause/upstream-downstream classification — no target-node framing,
  consistent with "global graph" instruction.
- **Driver strength** — the edge's real `|score|`, shown directly (today's
  `graph_builder.py` discards this and substitutes a driver-count string;
  fixed here).

Frontend: keep the existing on-screen shape (metric+trend card, top-drivers
card, recommended-action banner, all appearing inline under the graph when
a node is selected — see §7) but populate it from this richer endpoint
instead of the static `Node` mock shape.

## 6. Recommended actions

Three layers, same discipline used for the Predictive Early-Warning
Copilot — causal data and a domain-knowledge menu bound what's *possible*
to say; the LLM only prioritizes and phrases within that bound:

1. **Causal results decide *what* to act on** — the node's strongest
   upstream drivers (by `|score|`, from §5) indicate which levers plausibly
   move this metric, and their sign indicates which direction.
2. **A small domain-knowledge table decides the *menu* of candidate
   actions** — replaces `graph_builder.py`'s single hardcoded string per
   metric with 2–4 candidate actions per metric (e.g. `dealer_followup_rate`
   → "escalate stale leads," "add WhatsApp reminder templates," "reassign
   to higher-SLA dealers"). This is a small, explicit, editable table — not
   LLM-generated — so there's always a grounded menu to choose from.
3. **The LLM prioritizes and explains** — given the node's real current
   value/trend, real top drivers with real strengths, and this metric's
   candidate-action menu, one LLM call ranks and phrases the recommendation
   in plain English (why this action, why now, expected direction of
   effect). It does not invent actions outside the menu or numbers outside
   the case file.
4. **Priority ordering** = driver strength × how far the node's current
   value sits from its own healthy historical range (from §5's stats) — an
   explainable formula, not a black-box LLM ranking.

## 7. Conversational copilot (replaces "Ask Causal Twin")

- **Reuse the existing `LlmProvider` seam in this backend**
  (`app/ai/llm/provider.py` Protocol, `app/ai/llm/registry.get_llm_provider`,
  `Settings.ai_provider`/`openai_api_key`) rather than importing the
  separate `Predictive_Early_Warning_Service/copilot` — different app,
  different config, pattern-reuse only:
  - Add `OpenAiProvider` implementing `LlmProvider.complete(prompt) -> str`,
    same approach as `Predictive_Early_Warning_Service/copilot/llm_client.py`.
  - Add sibling settings fields next to `ai_provider`/`openai_api_key` in
    `core/config.py` (e.g. `openai_base_url`, `openai_model`), same
    `Field(default=..., description=...)` convention already used there.
  - Wire `get_llm_provider` to actually return `OpenAiProvider` when
    `ai_provider == "openai"` instead of silently falling back to rules —
    the one real gap keeping the existing seam inert today.
- **Context (RAG) layer**: context-window RAG, not a vector database — same
  reasoning as the PEWS Copilot. One request's relevant "document" is: the
  current global graph (11 metrics, a handful of edges — small), the
  selected node's detail (§5), its top drivers, its recommended actions
  (§6), and the recent-change diff (§4). All of it fits in one prompt;
  nothing to fuzzy-search over. A `build_case_file(...)` function, same
  shape as `Predictive_Early_Warning_Service/copilot/context_builder.py`.
- **Conversation history**: a new small table (e.g. `MobilityCopilotTurn`)
  via the existing SQLAlchemy/Alembic pattern this backend already uses
  elsewhere — a DB table rather than local JSON files, since this backend
  already has a database and doesn't use file-based persistence elsewhere.
  Keyed by a session id the frontend generates and keeps client-side.
- **Endpoints**: `POST /mobility-twin/copilot/ask`, `GET
  /mobility-twin/copilot/history`, `DELETE /mobility-twin/copilot` —
  replacing `POST /mobility-twin/ask`.
- **Answers, grounded**: why generated / current value & trend / strongest
  drivers / relationship to another named variable / recommended actions /
  what changed recently / which variables have the strongest influence —
  all answerable directly from the case file above.
- **Hallucination prevention**: same discipline as the PEWS Copilot's
  system prompt — only use facts in the case file; say plainly when
  something isn't covered; never present a driver as a proven cause; never
  claim a relationship PCMCI found is stronger or more certain than its
  actual score/significance supports.

## 8. Frontend — same screen you already have, made real

**The on-screen layout does not change.** Per the screenshots: a
three-column grid — **Business Health** (left, KPI cards), **Causal Graph**
(center, SVG boxes + arrows, click a node to reveal its metric/trend card,
top-drivers card, and a recommended-action banner directly beneath the
graph — exactly `mobility-twin.tsx` lines 222–311 today), **Ask Causal
Twin** (right). This plan does **not** adopt the more elaborate
pan/zoom/multi-band SVG component built for Warranty & Quality
(`warranty-quality-causal-graph.tsx`) — that was considered in an earlier
draft of this plan and dropped; the existing simple SVG graph stays, wired
to real nodes/edges instead of the mock arrays.

Concretely:

- Delete `mobility-twin.tsx`'s `NODES`/`EDGES`/`ASKS` mock arrays and the
  `?? NODES`/`?? EDGES` fallbacks once the backend returns real data; the
  `useMobilityGraph()`/`useMobilityKpis()` hooks already exist and are
  already called.
- Node click already exists (`setSel(n)`) — extend the `Node` type/shape to
  carry the richer §5 fields (real trend history, real stats, real driver
  strengths) instead of the current flat mock shape, and add a hook for
  `GET /mobility-twin/nodes/{metric}` fired on selection.
- The existing metric/trend card, top-drivers card, and recommended-action
  banner (lines 286–309) keep their current visual position and styling —
  just render the richer real fields from §5/§6 instead of `active.metric`/
  `active.drivers`/`active.action`.
- **"Ask Causal Twin" panel**: keep its exact position, width, and panel
  title in the layout; replace its *internal* content — today a static list
  of 4 preset-question buttons plus a single answer box — with a small chat
  surface (message list, optional suggestion chips seeded from the same
  kind of question categories already shown, a text input, send button)
  wired to the §7 copilot endpoints. Same visual language as the panel
  already has (`Panel` component, existing button/border styles) — this is
  a content change inside the existing panel, not a new panel or a layout
  change.
- **Live refresh**: no scheduler-status polling needed (§4) — the backend
  recomputes on its own 60-minute cycle (§4), so the frontend just re-fetches
  `graph`/`kpis` on a matching interval (e.g. every few minutes is enough to
  pick up a new 60-minute result promptly without hammering the endpoint;
  exact frontend polling interval to be tuned once live) and always gets
  whatever the backend's latest computed result is; no signature/
  version-keyed query is required the way it is for Warranty & Quality.

## 9. File-by-file summary

**New:**
- Node-detail endpoint + service method (`GET /mobility-twin/nodes/{metric}`)
- Domain-knowledge action-candidate table/module for §6
- `OpenAiProvider` (`app/ai/llm/`)
- New settings fields (`openai_base_url`, `openai_model`) in `core/config.py`
- Mobility copilot: context-builder, `MobilityCopilotTurn` table + Alembic
  migration, `ask`/`history`/`DELETE` endpoints
- Frontend: node-detail hook, copilot chat hook + UI (inside the existing
  "Ask Causal Twin" panel), richer `Node` type

**Modified:**
- `ai/causal/pcmci_engine.py` call site — keep `run_pcmci`, pass the §3
  config (window/tau_max/pc_alpha) explicitly instead of inline defaults
- `ai/causal/graph_builder.py` — real driver strength instead of a count
  string; hand off action text generation to §6 instead of the static
  `DISPLAY` action field
- `ai/causal/data_loader.py` — window config per §3 (28 days / 40,320 rows)
- `backend/app/services/operational_mobility.py` — fix `windows_per_week`
  (§2), wire in the node-detail/recommended-actions/copilot pieces
- `backend/app/ai/llm/registry.py` — actually return `OpenAiProvider` for
  `ai_provider="openai"`
- `frontend/src/routes/mobility-twin.tsx` — remove mock arrays, wire real
  hooks, extend the "Ask Causal Twin" panel's internal content

**Explicitly not touched:** `services/mobility.py`/`models/mobility.py`
(dead static-seed code, left alone), the Warranty & Quality
replay/scheduler pipeline and its docker services, `Causal_Discovery_Service`
and `Predictive_Early_Warning_Service` (separate services, reused only by
pattern/analogy, never imported).

## 10. Explicitly out of scope

- No root-cause / upstream / downstream / target-node framing anywhere in
  this graph or its copilot — global graph only, per instruction.
- No replay-ingestor, no per-domain watermark, no persisted causal-run
  history table, no new docker scheduler service for mobility.
- No dependency from this plan's code onto `Causal_Discovery_Service` or
  `Predictive_Early_Warning_Service` — both stay independent; only their
  *patterns* (context-window RAG, config-driven tau_max/pc_alpha, LLM
  client shape) are reused by analogy.
