# AI Simulation Center — implementation plan

Status: **plan only, nothing implemented yet.** This document is the detailed
design for making all five Simulation Center tabs (Auto Sales, Dealer
Allocation, Collections, Logistics Delay, Credit Pricing) genuinely
data-backed, before any code is touched. It follows the same
observe → predict → explain → simulate → recommend → approve → act → learn
lineage used elsewhere in this app (see
[Implementation_plan_mobility_causal.md](Implementation_plan_mobility_causal.md)
for the sibling screen built on the same principle).

---

## 1. What exists today (do not rebuild — replace the broken parts)

- Screen: [frontend/src/routes/simulation.tsx](../frontend/src/routes/simulation.tsx) — layout, tabs, sliders, panels are correct and **stay exactly as they are**. Only the data plumbing underneath changes.
- Routes already at the right paths: [backend/app/api/v1/simulations.py](../backend/app/api/v1/simulations.py) (`/api/v1/simulations/*`).
- `SimulationDomain` enum already has the 5 correct values ([backend/app/models/enums.py](../backend/app/models/enums.py)).
- A `SimulationRun` ORM model already exists ([backend/app/models/simulation.py](../backend/app/models/simulation.py)) but has **no migration** — the table does not exist in Postgres yet.
- `CausalAnalysisRun`/`CausalAnalysisEdge` ([backend/app/models/causal_analysis.py](../backend/app/models/causal_analysis.py)) already exist as a home for "genuine PCMCI causal-discovery executions" but are completely unused — no migration, no service.
- The five "engines" under [backend/app/ai/simulation/](../backend/app/ai/simulation/) are hardcoded arithmetic ports of the frontend's JS formulas — no DB read, no model, no optimizer. These get replaced entirely.
- The real, populated data lives in a separate "runtime schema" — [backend/app/database/runtime_schema.py](../backend/app/database/runtime_schema.py) — 51 tables, static synthetic history spanning **2026-01-01 → 2026-07-31**, queried today only by [backend/app/repositories/reference.py](../backend/app/repositories/reference.py). Every new repository in this plan follows that same pattern (`runtime_tables["<name>"]` + SQLAlchemy Core `select()`), never the orphaned ORM classes in `app/models/{operations,dealer,collections,circularity,logistics}.py`.
- A working LPCMCI/PCMCI causal-discovery engine already exists and is proven in production for other screens ([Causal_Discovery_Service/](../Causal_Discovery_Service/), [backend/app/ai/causal/pcmci_engine.py](../backend/app/ai/causal/pcmci_engine.py)) — this plan reuses it, it does not reimplement causal discovery.

---

## 2. Architecture: one common "Simulation Run" framework

Every tab produces one row through the same pipeline:

```
inputs (user sliders)
   │
   ▼
baseline load (real Postgres aggregate for the selected region/model/segment/route)
   │
   ▼
predictive model(s) / optimizer  →  scenario outcome
   │
   ▼
recommendation logic (rule-based, reads model output — never invents numbers)
   │
   ▼
confidence (derived, not random)
   │
   ▼
persist SimulationRun row  →  run_id returned to frontend
   │
   ├─▶ GET  /simulations/{run_id}                (re-fetch a run)
   ├─▶ GET  /simulations/{run_id}/drivers         (Explain Drivers)
   ├─▶ POST /simulations/{run_id}/summary         (Generate Executive Summary)
   └─▶ POST /simulations/{run_id}/approve         (Approve Recommendation)
```

Nothing about a run is ever recomputed independently by the frontend. Every
button after "Run Simulation" acts on the persisted `run_id`, not on the
current slider values.

### 2.1 `simulation_runs` table (extend the existing model, new Alembic migration)

```
id                  UUID PK
domain              simulation_domain enum (auto_sales | dealer_allocation | collections | logistics_delay | credit_pricing)
scenario_name       text            -- from the top-bar Scenario selector, e.g. "Baseline FY26"
baseline_reference  jsonb           -- the real aggregate baseline computed before the scenario was applied
inputs              jsonb           -- exact slider/select values submitted
outputs             jsonb           -- exact API response shown on screen
driver_json         jsonb           -- Explain Drivers payload, cached after first computation
recommendation_json jsonb           -- structured recommendation (not just a string)
confidence          int             -- 0-100, see §7
confidence_band     text            -- "low" | "medium" | "high"
model_name          text            -- e.g. "auto_sales.booking_conversion_gbm"
model_version       text            -- e.g. "2026-09-16.1" (training date + iteration)
status              simulation_run_status enum: DRAFT | COMPLETED | PROPOSED | APPROVED | REJECTED | HUMAN_REVIEW | EXECUTED
created_at          timestamptz
updated_at          timestamptz
```

### 2.2 `simulation_approvals` table (new — the human-decision ledger for this screen)

```
id            UUID PK
run_id        UUID FK -> simulation_runs.id
decision      text          -- "approved" | "rejected"
reason        text nullable
actor         text          -- from auth context if available, else "demo_user"
decided_at    timestamptz
```

This is **new, app-owned state** — it does not write into the synthetic
`trust_decisions` runtime table. That table is generator-produced historical
data (its own module docstring says "no evaluator ground-truth tables... no
generator dependency at runtime" — it's a sealed synthetic corpus, not a live
ledger a running app should insert into). `simulation_approvals` is this
screen's own trust ledger, in the same spirit as `trust_decisions` but
correctly scoped to real, live, app-generated decisions. The existing
`TrustApproval` enum values (`approved`/`rejected`/`human_review`/`pending`/
`escalated`) are reused for `simulation_runs.status` naming consistency.

Both tables ship in one Alembic migration alongside the app's existing
`runtime_0003` chain (new revision, not touching runtime tables).

---

## 3. Common backend building blocks

- `SimulationRunRepository` — create/get/update rows in `simulation_runs` and `simulation_approvals`. Follows the existing repository pattern (plain SQLAlchemy Core/ORM against the new app-owned tables — these *are* proper ORM tables, unlike the runtime schema).
- Per-domain **feature repositories** reading the runtime schema (e.g. `AutoSalesRepository`, `DealerAllocationRepository`, `CollectionsRepository`, `LogisticsRepository`, `CreditPricingRepository`), each exposing:
  - `get_baseline(filters) -> BaselineSnapshot` — real aggregate metrics for the current selection, computed live from Postgres (never cached longer than the reference-data cache TTL already used for `/meta`).
  - `get_training_frame() -> pandas.DataFrame` — used offline/at startup to fit the domain's model(s); chronologically split (train on the first ~80% of the Jan–Jul 2026 window, test on the last ~20%) to avoid leakage across time.
- A single `confidence.py` helper implementing the shared confidence contract (§7) so no domain invents its own ad hoc scheme.
- `app/ai/simulation/base.py` gets a real `SimulationEngine` protocol: `run(payload, baseline, models) -> EngineResult` where `EngineResult` always carries `{scenario_outputs, baseline_outputs, confidence, confidence_band, drivers, recommendation}` — replacing the current placeholder file.

### 3.1 Leakage rule (applies to every domain, no exceptions)

The runtime schema exposes several columns that are the *generator's own
internal sampling probabilities*, not information available at
decision-time. These are excluded from every feature set, full stop:

`latent_purchase_intent`, `booking_probability`, `cancellation_probability`,
`completion_probability`, `claim_probability`, `request_probability`,
`regional_demand_index`, `allocation_priority_score`, `allocation_priority`,
`risk_score` (shipments' own precomputed synthetic risk).

Models are trained only on fields that would genuinely be known before the
outcome happens (e.g. `budget_fit`, `engagement_score`, `dealer_followup_sla_hours`,
`completed_test_drive`, `good_followup`, `finance_preapproval_signal`,
`dpd_at_interaction`, `warehouse_utilization_pct`, `weather_disruption`, etc.)
and predict/estimate real recorded outcomes (`booking` existence,
`cancellations` existence, `sla_breach`, `payment_after_contact`, etc.).

---

## 4. Per-tab design

### 4.1 Auto Sales

**Inputs (unchanged on screen):** Region, Vehicle Model, Discount % (0–10),
Exchange Bonus ₹ (0–75,000), Campaign Spend ₹Cr (0–5), Dealer Follow-up
Intensity (Low/Medium/High). These four levers are **user-chosen what-if
values**, not read from history — the model's job is to estimate their
effect, not to have observed them before.

**Real data available:** `leads` → `test_drives` → `followups` →
`bookings` → `cancellations` → `finance_applications`, joined by
`lead_id`/`booking_id`, filterable by `region_name`/`vehicle_model_name`.
Rich per-lead features: `budget_fit`, `engagement_score`, `urgency_score`,
`model_interest_score`, `source_quality`; per-test-drive:
`completed_test_drive`, `wait_hours`; per-followup: `channel`,
`within_sla`, `customer_responded`; per-booking:
`finance_assisted`, `finance_preapproval_signal`, `exchange_assisted`,
`long_test_drive_wait`; per-cancellation: `reason`, `finance_delay`
equivalents.

**Gap:** there is no historical column for discount %, exchange-bonus
amount, or campaign spend anywhere in the schema — only the boolean
`exchange_assisted`. There is therefore **no historical variation to train
an incentive-elasticity regression on.** This is a real, structural data gap,
not a modelling shortcut to skip.

**Design (two-layer engine, both layers real, neither a random formula):**

1. **Baseline conversion model** (genuinely trained): a calibrated logistic
   regression / gradient-boosted classifier predicting P(lead → booking)
   from the lead/test-drive/followup features above, trained per
   region+model cohort on the real funnel. This gives the *baseline*
   booking-conversion rate and baseline cancellation rate for the selected
   region/model — the "what happens if we change nothing" anchor.
2. **Incentive response layer** (documented calibrated function, not a
   trained black box, and clearly labelled as such in the API response):
   a monotonic response curve for discount/bonus/campaign built from
   published/assumed price-elasticity ranges for auto retail incentives
   (bounded, diminishing-returns curve, e.g. `Δconversion = k · log(1 + bonus/bonus_ref)`),
   with the multiplier `k` calibrated so the curve's low end reproduces the
   baseline model's conversion rate at bonus≈0. Every response coefficient
   ships in a small, reviewable config file (not scattered magic numbers)
   so a domain expert can adjust them later without touching code.

   The **cancellation-risk** side, by contrast, *is* trainable directly:
   `cancellations` joined to `bookings` gives a real label
   (cancelled vs not, with `finance_delay`/`delivery_delay`/
   `competitor_offer`/`customer_change`/`dealer_issue` reason flags) —
   fit a calibrated classifier on booking-time features, and use
   `finance_preapproval_signal`/`exchange_assisted` (proxies plausibly
   affected by bonus/finance terms) as the channel through which the
   incentive scenario shifts cancellation probability.

3. **Revenue & margin calculator** (pure arithmetic, not a model): scenario
   incremental bookings × average booking value for the region/model (real,
   from `bookings.booking_amount_inr`) minus discount cost minus bonus cost
   minus campaign spend = net revenue impact; margin impact = discount/bonus
   cost as % of average booking value.
4. **Recommendation logic**: rule-based — compares net revenue impact and
   cancellation delta against the baseline and picks one of a small set of
   templated recommendation shapes (deploy / hold / scale back), filling in
   the actual scenario numbers. Never free-text-generated by an LLM at this
   stage (LLM only touches wording in the executive summary, §6).

**Explain Drivers:** two clearly separated blocks in the response —
`predictive_drivers` (feature importances from the trained conversion/
cancellation models, e.g. SHAP or permutation importance) and
`causal_evidence` (LPCMCI run over a new `causal_timeseries`-style daily
panel built from the same auto-sales tables — reusing the existing PCMCI
engine exactly as the Mobility Twin does, landing results in
`causal_analysis_runs`/`causal_analysis_edges`). The UI must never caption
the first block as causal.

**Classification: MAJOR DATA/MODEL WORK** (the incentive-response layer is a
calibrated approximation by necessity, not a modelling gap to "fix" — this
must be stated plainly in the UI, e.g. a small "elasticity assumptions"
info affordance next to the recommendation).

### 4.2 Dealer Allocation

**Inputs:** Vehicle Model, Available Units, Region Demand Intensity, Dealer
Capacity, Waiting Period Target.

**Real data:** `allocations` (real `requested_units`/`allocated_units`/
`waiting_list`/`dealer_capacity`/`allocation_wait_hours` history per
dealer/model/region), `deliveries` (`delay_days`, `dispatch_delay_hours`),
`dealers` (`monthly_booking_capacity`, `dealer_tier`).

**Design — this is genuinely an optimization problem, not an ML problem:**

1. **Demand forecast**: short lagged-regression per dealer/region on
   historical `allocations.requested_units` trend (simple, explainable —
   e.g. recent-weeks weighted average adjusted by the user's demand-intensity
   slider as a multiplier on the historical trend, not a replacement for it).
2. **Sell-through / conversion-quality score per dealer**: derived directly
   from that dealer's historical `allocated_units` → `bookings` conversion
   and `deliveries.delay_days`, i.e. real observed performance, not invented.
3. **Allocation optimizer**: a linear program (scipy.optimize.linprog or
   OR-Tools) that distributes the user's "available units" across dealers
   to **maximize a weighted objective of (expected sell-through × demand
   forecast) minus (waiting-time penalty above the user's target)**,
   subject to: `Σ allocated ≤ available_units`, `allocated_i ≤ dealer_capacity_i`,
   `allocated_i ≥ 0`. This directly produces the "recommended units per
   dealer/region" and "current vs recommended" comparison §6/§14 of the
   original spec asked for.
4. Outputs computed from the optimizer's solution, not separately
   estimated: waiting-time reduction = baseline wait (from historical
   `allocation_wait_hours`) minus optimizer-implied wait; revenue
   improvement = Δunits × average `booking_amount_inr` for that model;
   CSAT impact = a documented function of wait-time reduction (small,
   reviewable, same treatment as the Auto Sales incentive curve).

**Classification: MINOR DATA WORK** — everything needed exists with real
historical variation; the work is almost entirely the optimizer
formulation, not data sourcing.

### 4.3 Collections

**Inputs:** Customer Risk Segment, Contact Channel, Offer Type, Field
Visit Intensity.

**Real data — the richest of the five tabs:** `collection_cases`
(`dpd_at_case_creation`, `current_dpd`, `peak_observed_dpd`,
`current_arrears_inr`, `case_status`), `collection_interactions`
(`channel`, `field_visit_flag`, `contact_success`, `offer_type`,
`customer_response`, `promise_to_pay`, **`payment_after_contact`** — a real
recorded recovery outcome — and `payment_after_contact_amount_inr`),
`loan_accounts` (`principal_inr`, `interest_rate_pct`,
`debt_service_ratio_at_origination`, `secured`), `payment_history`.

**Design — all four required models are directly trainable:**

1. **Roll-forward risk model**: calibrated classifier predicting whether
   `current_dpd` will worsen, trained on `collection_cases` +
   `loan_accounts` features (DPD trajectory, arrears, product, secured
   flag), labelled from the case's own subsequent DPD progression.
2. **Recovery probability model**: calibrated classifier on
   `collection_interactions`, labelled by `payment_after_contact`,
   conditioned on `channel`, `field_visit_flag`, `offer_type`, `dpd_at_interaction`
   — this *is* the per-channel, per-offer response model in one fit (predict
   with the user's selected channel/offer/risk-segment as the scenario
   input).
3. **Recovery cost calculator**: real cost-per-channel derived from
   observed `field_visit_flag` frequency × a documented per-visit cost, plus
   fixed digital/voice cost tiers (small reviewable config, since no direct
   "cost_inr" column exists on interactions).
4. **Friction score**: a documented function of channel intrusiveness and
   field-visit intensity (same treatment as other non-observable business
   judgments in this plan — reviewable config, not invented per-request).
5. **Strategy optimizer**: for the selected risk segment, evaluate the
   trained recovery-probability model across the small enumerable action
   space (channel × offer × field-intensity bucket) and pick the option
   maximizing `recovery_probability × outstanding_amount − cost − compliance_penalty`,
   where the compliance penalty comes from real `compliance_checks` /
   `collections_compliance` signals if present for that segment.

**Classification: READY WITH CURRENT DATA.**

### 4.4 Logistics Delay

**Inputs:** Route, Warehouse Load, Vehicle Availability, Weather
Disruption, SLA Priority.

**Real data:** `shipments` has genuine labelled outcomes —
**`sla_breach`** (boolean), `delay_minutes`, `dispatch_delay_minutes`,
`actual_transit_hours`, and cause flags `weather_disruption`,
`vehicle_breakdown`, `warehouse_delay`, `port_delay`, `customs_delay`;
`routes` (`sla_hours`, `baseline_cost_inr`, `baseline_risk_score`,
`distance_km`); `warehouse_events` (`warehouse_utilization_pct`,
`dock_queue_depth`, `dock_wait_minutes`, `congestion_flag`) — a direct real
proxy for the "Warehouse Load" slider.

**Design:**

1. **Delay/ETA model**: gradient-boosted regressor predicting
   `actual_transit_hours` (or delay minutes) from route, warehouse
   congestion, and the scenario's weather/vehicle-availability inputs,
   trained on real `shipments` history for that route.
2. **SLA breach probability model**: calibrated classifier on the same
   features, labelled by the real `sla_breach` column — this is a properly
   supervised model with a genuine target, not a heuristic.
3. **Reroute/resource optimizer**: compare the selected route's predicted
   delay/breach-probability/cost against the next-best alternative route on
   the same origin-region → destination-region pair (real `routes` rows),
   picking the reroute only if `Δcost < value of avoided SLA-breach risk`
   (avoided-SLA-loss valued via a documented penalty-per-breach figure,
   consistent with how Dealer Allocation treats CSAT).
4. Cost impact = alternative route's `baseline_cost_inr` minus current
   route's, adjusted for the scenario's warehouse/weather multipliers.

**Classification: READY WITH CURRENT DATA.**

### 4.5 Credit Pricing (Circular Economy credits — carbon/EPR/SDG/CD)

**Inputs:** Credit Type, Supply Level, Buyer Demand, Traceability Score,
Verification Readiness.

**Real data:** `credit_listings` (`market_reference_price_per_tco2e_inr`,
`seller_ask_price_per_tco2e_inr`, `buyer_inquiry_count`,
`buyer_bid_count`, `highest_bid_price_per_tco2e_inr`,
`dmrv_available_records`/`dmrv_expected_records`/
`dmrv_timestamp_verified_records`/etc. completeness fields), joined to
`elv_assessments` (`traceability_score`, `document_completeness`,
`buyer_demand_index`) and `dmrv_records` (`recovery_percentage`,
`verification_status`).

**Gap found during audit:** `listing_status` is `OPEN` for all 750 rows —
**there is no recorded closed/not-closed outcome in this data at all.**
A trained closure-probability *classifier* is therefore not honestly
possible from this table alone.

**Design (calibrated function, explicitly labelled, same treatment as
Auto Sales' incentive layer — not a trained classifier presented as one):**

1. **Price prediction / recommended band**: regression on
   `seller_ask_price_per_tco2e_inr` vs `market_reference_price_per_tco2e_inr`,
   `buyer_bid_count`, `dmrv` completeness ratios, and traceability —
   this part *is* trainable (real historical asks and bids exist), giving a
   data-driven central price estimate; the band width derives from the
   residual spread of that regression (a real statistical quantity, not an
   arbitrary ±60 like today).
2. **Closure probability**: a documented monotonic function of
   (price relative to market reference) × (buyer demand / supply) ×
   (traceability + verification completeness), calibrated so it's
   consistent with observed `buyer_bid_count`/`buyer_inquiry_count`
   intensity as a proxy signal — explicitly surfaced in the API as
   `closure_probability_basis: "calibrated_heuristic"` so the frontend/LLM
   summary never claims it's a trained model.
3. **Buyer matching model**: this one *is* trainable — real
   `buyer_inquiry_count`/`buyer_bid_count` against listing attributes
   (credit type, region, traceability) supports a genuine regression for
   expected buyer interest.
4. **Compliance/verification rules**: rule-based thresholds on
   `dmrv_missing_records`, `document_completeness`, `verification_status` —
   already effectively how the current mock does it, but now reading real
   per-listing dMRV fields instead of a slider-only heuristic.
5. **Pricing optimizer**: small 1-D search over price in a bounded band
   maximizing `price × closure_probability(price)` (expected marketplace
   value), which is the correct way to implement "do not simply recommend
   the highest possible price."

**Classification: MINOR DATA WORK** — strong feature data, but the closure
piece must ship as a labelled calibrated function, not a mis-sold trained
classifier.

---

## 5. Confidence — one shared method, not a per-domain guess

`confidence` (0–100) is computed the same way everywhere it comes from a
trained model, and differently but still principled where the domain uses a
calibrated function:

- **Trained-model domains** (Collections, Logistics, Auto Sales' conversion/
  cancellation layer, Credit Pricing's price/buyer-match layer): confidence
  = a function of (a) the model's own calibrated predicted-probability
  margin from 50%, (b) how far the requested scenario inputs sit from the
  training data's observed range for that region/model/segment (in-range →
  higher; extrapolating → capped lower), and (c) training-sample size for
  that specific cohort (thin cohorts get a lower ceiling).
- **Calibrated-function domains** (Auto Sales incentive layer, Credit
  Pricing closure probability, Dealer Allocation's optimizer): confidence is
  capped at a fixed, lower ceiling (e.g. 70%) regardless of inputs, and the
  API marks `confidence_basis: "calibrated_heuristic"` vs
  `"trained_model"` so the UI/executive summary can say so honestly.
- `confidence_band` (`low`/`medium`/`high`) is a simple bucketing of the
  number, used for the badge colour already in the UI.

This replaces every hand-picked arithmetic expression currently in
`app/ai/simulation/*.py`.

---

## 6. Generate Executive Summary — from evidence, not from a bare string

`POST /simulations/{run_id}/summary` loads the persisted `SimulationRun`
row and builds the 9-field template
([backend/app/ai/prompts/executive_summary.py](../backend/app/ai/prompts/executive_summary.py))
from its actual `inputs`/`baseline_reference`/`outputs`/`driver_json`/
`recommendation_json`/`confidence` — never from a bare `use_case` string as
today. If the LLM wording pass is used (reusing
[[mobility_copilot_llm_credentials]]), the prompt is constructed so the
model only rephrases the structured evidence block; it is never given
license to state a number that isn't already in that block, and the system
prompt explicitly forbids inventing figures (same RAG-only-grounding
discipline already required for the Mobility Twin copilot).

---

## 7. Approve Recommendation → Trust Ledger lineage

`POST /simulations/{run_id}/approve` (and a `/reject` counterpart):

1. Loads the run, checks `status == PROPOSED` (or `COMPLETED`) —
   **rejects a second approval attempt on the same run** (idempotency,
   §13's "duplicate approval should be prevented").
2. Writes a `simulation_approvals` row (decision, actor, timestamp).
3. Updates `simulation_runs.status = APPROVED`.
4. Returns the updated run so the frontend can flip the button to
   "Approved" and disable it.

The Compliance Trust Ledger screen ([backend/app/models/trust.py](../backend/app/models/trust.py))
can later read `simulation_approvals` joined to `simulation_runs` as an
additional lineage source alongside its existing `trust_decisions` view —
outside this plan's immediate scope, but the schema is deliberately shaped
so that join is trivial (`domain`, `recommendation_json`, `confidence`,
`decided_at` all line up with `TrustDecision`'s own fields).

---

## 8. API surface (final)

```
GET  /api/v1/simulations/meta                              (already correct, unchanged)
GET  /api/v1/simulations/{run_id}                           NEW
GET  /api/v1/simulations/{run_id}/drivers                    NEW (replaces the domain-only causal-drivers endpoint)
POST /api/v1/simulations/{run_id}/summary                    NEW
POST /api/v1/simulations/{run_id}/approve                    NEW
POST /api/v1/simulations/{run_id}/reject                     NEW

POST /api/v1/simulations/auto-sales/run                      rewritten body, now returns run_id + status
POST /api/v1/simulations/dealer-allocation/run                rewritten body, now returns run_id + status
POST /api/v1/simulations/collections/run                      rewritten body, now returns run_id + status
POST /api/v1/simulations/logistics-delay/run                  rewritten body, now returns run_id + status
POST /api/v1/simulations/credit-pricing/run                   rewritten body, now returns run_id + status
```

Every `*/run` response shape gains a common envelope on top of the existing
domain-specific fields (which stay, so the frontend cards keep working
unchanged):

```jsonc
{
  "run_id": "…",
  "status": "COMPLETED",
  "confidence": 74,
  "confidence_band": "medium",
  "confidence_basis": "trained_model",
  "baseline": { /* same-shaped object as the scenario output, pre-scenario */ },
  // ...existing domain-specific fields (uplift, margin, cancel, rev, recommendedAction, ...)
}
```

---

## 9. Frontend rewiring (screen stays visually identical)

- Delete every `localOut`/`const price = …`/etc. inline formula block from
  [simulation.tsx](../frontend/src/routes/simulation.tsx) — all five tabs.
- `useAutoSalesSim`-style hooks change from always-on `useQuery` (fires on
  every slider drag) to a `useMutation` triggered only by the **Run
  Simulation** button, per §10 of the original brief ("validate → loading →
  send → …"). Sliders update local input state only; nothing is sent to the
  API until Run Simulation is clicked.
- Each tab keeps a `runId` in local state, set from the mutation's
  response; `Explain Drivers`, `Generate Executive Summary`, and `Approve
  Recommendation` are disabled until a `runId` exists, and all three call
  their endpoint with that `runId` — never recomputing from current slider
  values.
- Explicit states per tab, replacing the current always-rendered cards:
  - **Idle** (no run yet): outputs area shows a neutral placeholder ("Run a
    simulation to see predicted impact"), all three post-run buttons
    disabled.
  - **Loading**: outputs area shows a spinner/skeleton + "Running
    simulation…", Run button disabled to prevent double-submits.
  - **Error**: a visible error panel with the backend's message (e.g.
    "Insufficient historical data for East / Thar." or "Simulation failed.
    Check backend logs.") — never a silent fallback to any locally computed
    number.
  - **Success**: existing card layout, now populated only from the API
    response.
  - **Approved**: Approve button becomes a disabled "Approved" state per
    §13, survives a page refresh (re-fetch by `run_id` if the frontend
    keeps it in the URL/local storage — small addition, not required for
    MVP correctness but flagged here for completeness).

---

## 10. Top-bar controls

- **Scenario selector** ("Baseline FY26", etc.): value is threaded into
  every `*/run` call as `scenario_name`, stored on the `SimulationRun` row
  as `scenario_name`/`baseline_reference`. For MVP, only "Baseline FY26"
  resolves to the real historical baseline described in §4 per domain;
  other scenario entries ("High Growth", "Demand Stress", "Supply
  Constraint") are out of scope for this pass (§12) unless requested — they
  would each need their own documented baseline-adjustment rule, not fake
  data.
- **Executive Mode**: renders the *same* `SimulationRun` output through a
  condensed presentational component (fewer cards, headline numbers only) —
  no separate data path, no separate computation.
- **Ask AI Copilot**: when opened from the Simulation Center, the panel is
  seeded with a context object built from the active tab's last
  `SimulationRun` (domain, inputs, baseline, outputs, drivers,
  recommendation) — the same shape the executive summary consumes — so
  follow-up questions can be grounded in the same evidence. This reuses the
  existing copilot context-injection pattern already used for the Mobility
  Twin ([backend/app/services/mobility_copilot_context.py](../backend/app/services/mobility_copilot_context.py)) rather than
  building a new one.
- **Search / Start Demo Story**: unaffected by this work.

---

## 11. Testing plan

- Unit tests per domain repository: baseline aggregate queries against a
  seeded test slice of the runtime schema (fixtures, not the live 50k-row
  tables).
- Unit tests per model wrapper: deterministic given a fixed random seed;
  assert monotonic direction (e.g. higher exchange bonus → non-decreasing
  predicted uplift) rather than exact numbers, since these are statistical
  models.
- Integration tests for the run lifecycle: `run → get → drivers → summary →
  approve → duplicate-approve-rejected`.
- Chronological-split validation report (not a unit test, but required
  before shipping each domain's trained model): AUC/PR-AUC or MAE on the
  held-out last ~20% of the Jan–Jul 2026 window, recorded in
  `model_version`'s accompanying note so `model_name`/`model_version` on
  each run is traceable to a real evaluation.
- Frontend: loading/error/empty states exercised with mocked API
  responses (React Testing Library), plus one manual pass per tab in a
  browser per this project's UI-change convention.

---

## 12. File-by-file summary

**Backend — new:**
`backend/alembic/versions/<new>_simulation_runs.py`,
`backend/app/repositories/{auto_sales,dealer_allocation,collections_sim,logistics,credit_pricing}.py`,
`backend/app/repositories/simulation_run.py`,
`backend/app/ai/simulation/confidence.py`,
`backend/app/ai/simulation/models/*` (trained-model wrappers + a small
offline `train.py` per domain reading `get_training_frame()`),
`backend/app/ai/simulation/optimizers/{dealer_allocation,collections,logistics,credit_pricing}.py`.

**Backend — rewritten:**
`backend/app/api/v1/simulations.py`, `backend/app/schemas/simulation.py`,
`backend/app/services/simulation.py`, all of
`backend/app/ai/simulation/{auto_sales,dealer_allocation,collections_sim,logistics_delay,credit_pricing}.py`,
`backend/app/ai/causal/drivers.py`, `backend/app/services/executive_summary.py`,
`backend/app/ai/prompts/executive_summary.py`.

**Frontend — rewritten:**
`frontend/src/routes/simulation.tsx`, `frontend/src/hooks/use-api.ts`
(simulation section), `frontend/src/lib/api/endpoints.ts`,
`frontend/src/lib/api/types.ts`.

**Removed once the above is verified working:** the hardcoded-formula
bodies of the current `app/ai/simulation/*.py` files (logic deleted, files
kept as the engine entry points), and the `localOut` blocks in
`simulation.tsx`.

---

## 13. Phased delivery (unchanged from the audit, restated for reference)

1. Common framework: migration, `SimulationRunRepository`, confidence
   helper, run lifecycle endpoints (`get`/`approve`/`reject`), frontend
   mutation-based Run Simulation + loading/error states — built once,
   proven end-to-end on **Auto Sales** first.
2. Auto Sales full loop (baseline model + calibrated incentive layer +
   revenue calculator + LPCMCI drivers).
3. Dealer Allocation (optimizer).
4. Collections (fully trainable — the cleanest domain, good sanity check
   for the framework before the harder ones).
5. Logistics Delay (fully trainable).
6. Credit Pricing (price/match trainable, closure calibrated).
7. Cleanup: delete dead code in `app/models/{operations,dealer,collections,circularity,logistics,trust}.py` *if* confirmed unused by any other screen (needs its own short audit — some of these files may back other dashboards and must not be touched here).

---

## 14. Explicitly out of scope for this plan

- Adding discount/bonus/campaign-spend columns to the synthetic generator
  (would fix Auto Sales' data gap properly, but §18/§24 of the brief say
  don't touch the generator unless necessary — the calibrated-function
  approach in §4.1 is the compliant alternative).
- Non-"Baseline FY26" scenario snapshots (High Growth / Demand Stress /
  Supply Constraint) — needs its own design for what "baseline" means under
  each, not assumed here.
- Wiring `simulation_approvals` into the Compliance Trust Ledger UI screen
  itself (the schema supports it; the ledger screen's own read path is a
  separate change).
- Retraining/refresh cadence for the domain models (MVP trains once at
  build time from the static synthetic history; a scheduled retrain job is
  future work, not required while the underlying data doesn't move).
