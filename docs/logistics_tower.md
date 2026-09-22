# Logistics AI Control Tower — implementation plan

Turns `/logistics` from a screen with two real, well-computed aggregate
endpoints (route cards, warehouse signals) plus four effectively-mock
action buttons, into a fully working, database-backed, governed screen —
using the same architecture already proven for Collections & Recovery AI
Swarm: reuse the Logistics Delay Simulation's real trained models instead
of building new ones, and reuse the Compliance Trust Ledger's real
governance model instead of building a second audit system.

This plan assumes the audit in `docs/` (Logistics AI Control Tower audit,
delivered inline, 2026-09-21) as ground truth. Key facts from it that
drive every decision below:

- Route cards and Warehouse Signals are **already real** — live SQL
  aggregates over `routes`/`shipments`/`warehouses`/`warehouse_events`,
  correct math, no fabrication. Do not rebuild these.
- All four action buttons (Predict Delay, Recommend Reroute, Auto-Heal,
  SLA Report) are effectively non-functional: no persistence, two of them
  don't even call a real optimizer, one makes no API call at all.
- A real, unused canonical governance trail already exists in Postgres:
  `trust_decisions` with `target_entity_type='SHIPMENT'`, `domain
  ='LOGISTICS'` (400 rows), linked `compliance_checks`, and
  `action_outcomes` (140 rows) — structurally identical to the
  `COLLECTION_CASE` trail that Collections AI Swarm now reuses.
- Logistics Delay Simulation already has two real trained classifiers
  (any-delay, SLA-breach), a genuine cost-minimizing reroute optimizer,
  real driver/explainability logic, and real confidence banding — all
  currently called only from the Simulation Center's scenario-input flow,
  never from a real route/shipment.
- The dead `app/services/logistics.py` / `app/repositories/logistics.py`
  / `app/models/logistics.py` stack targets tables that don't exist in the
  live database at all. Leave it alone — do not delete it in this pass
  (out of scope), just never build on top of it.

```
Target pipeline (mirrors Collections AI Swarm exactly):

routes + shipments + warehouse_events                  real, live Postgres
        │
        ▼
Logistics Delay Simulation's trained models             REUSED, not rebuilt
  (any_delay / sla_breach classifiers,                  app/ai/simulation/
   route_cohort_features, reroute optimizer,             logistics_delay.py +
   predictive_drivers, confidence banding)                models/logistics_delay_model.py
        │  applied per real shipment/route instead of a scenario input
        ▼
OperationalLogisticsService                              real per-route/shipment
  (extended, not replaced)                                intelligence + priority
        │
        ├─ canonical track: real trust_decisions/compliance_checks/       REUSED
        │  action_outcomes rows where target_entity_type='SHIPMENT'      (read-only)
        │
        └─ live track: new ai_state tables mirroring                     NEW, mirrors
           collection_case_decisions/human_reviews exactly,              app/models/
           keyed by shipment_id                                          collections_case.py
        │
        ▼
compliance_engine.py + risk_engine.py                     REUSED, not rebuilt
        │
        ▼
FastAPI /api/v1/logistics/... (extended)
        │
        ▼
Logistics AI Control Tower screen — same layout, real actions
```

## 1. What already exists (do not rebuild — reuse or extend it)

**Real and correct today:**
- `GET /logistics/routes` → `OperationalLogisticsService._routes()` — real
  SLA risk / delay prob / avg cost per route. Keep the aggregation; only
  the "recommendation" field and the sort key need to change (see §3, §7).
- `GET /logistics/warehouse-signals` → real utilization/congestion/dock-wait
  aggregates with real thresholds, correctly evaluated. Keep as-is; only
  needs an explainability endpoint added alongside it (see §6).
- `app/ai/simulation/models/logistics_delay_model.py` — `get_or_train_models()`
  returns `LogisticsDelayModels(any_delay, breach, frame)`; `any_delay` and
  `breach` are both `FittedLogit` instances with `.predict_proba()`,
  `.numeric_drivers()`, `.categorical_coefficient()` — identical shape to
  the Collections recovery/roll-forward models already reused. Real
  features already keyed by `route_id`/`priority`, so per-shipment scoring
  needs no new model, no retraining, no schema change.
- `app/ai/simulation/logistics_delay.py` — `run()` contains a genuine
  cost-minimizing reroute sweep over real alternative routes sharing an
  origin/destination region, plus `predictive_drivers` construction and
  cost constants (`COST_PER_DELAY_HOUR_INR`, `SLA_BREACH_PENALTY_INR`).
  Exactly like Collections' `sweep_best_channel_offer`/`recovery_drivers`,
  these need to be **extracted into reusable functions** (not duplicated)
  so both the scenario simulation and the real control-tower path call the
  same code.
- `app/repositories/logistics_delay_simulation.py` — `get_route`,
  `get_route_alternatives`, `load_shipment_frame` are already generic
  enough to back real per-route/shipment inference with no changes.
- `app/services/compliance_engine.py` (`evaluate_simulation_compliance`,
  now accepting the `_HasComplianceFields` Protocol) and
  `app/services/risk_engine.py` (`score_simulation_risk`) — reuse exactly
  as Collections does: build a lightweight snapshot dataclass with the
  same field names, no changes needed to either file.
- `app/services/trust.py` (`TrustService.get_outcome`, canonical
  `trust_decisions`/`compliance_checks` reads) — reuse directly for the
  canonical `SHIPMENT` track, exactly as Collections reuses it for
  `COLLECTION_CASE`.
- The `collection_case_decisions` / `collection_case_human_reviews` ORM
  models (`app/models/collections_case.py`) and their repository
  (`app/repositories/collections_case_decision.py`) are the exact template
  to copy for the new live-track tables here (see §4) — same shape, same
  reasoning for why compliance is recomputed live rather than cached.

**Leave alone entirely (out of scope, do not touch):**
- `app/services/logistics.py`, `app/repositories/logistics.py`,
  `app/models/logistics.py`, and the archived migration in
  `alembic/legacy_versions_archive/0001_initial_schema.py`. Dead code
  against non-existent tables; removing it is a separate, unrelated
  cleanup decision, not part of making this screen real.
- The stale test file `tests/api/test_writes_collections_logistics.py`'s
  remaining logistics tests, until this work makes the endpoints they
  exercise real again (they currently fail for an unrelated reason — a
  removed legacy seed mechanism — and will need to be rewritten anyway
  once the real behavior changes, exactly as was done for Collections).

## 2. New database objects

Two new `ai_state` tables, mirroring `collection_case_decisions` /
`collection_case_human_reviews` field-for-field, keyed by
`shipment_id: str` instead of a case id string (no FK to `shipments` —
same cross-schema reasoning as Collections: that table is Synthetic Data
Factory-owned runtime-schema data):

```
route_shipment_decisions            (ai_state schema)
  id                UUID PK
  shipment_id       String(64) UNIQUE, indexed
  status            String(24)   -- APPROVED | ESCALATED
  recommended_action        String(32)  -- e.g. "MAINTAIN" | "REROUTE"
  recommended_route_id      String(64) NULL  -- the optimizer's suggested alternative, if any
  modified_action            String(32) NULL  -- human override, preserved separately
  modified_route_id          String(64) NULL
  modification_reason        Text NULL
  reviewer_role     String(32) NULL
  reason            Text NULL
  actor             String(64) default "demo_user"
  decided_at        DateTime(timezone=True)
  created_at / updated_at (TimestampMixin)

route_shipment_human_reviews        (ai_state schema)
  id                UUID PK
  shipment_id       String(64), indexed
  reviewer_role     String(32)
  reason            Text NULL
  requested_by      String(64) default "demo_user"
  requested_at      DateTime(timezone=True)
  created_at / updated_at
```

No compliance-check cache table — same reasoning as Collections:
compliance is recomputed live from the decision row's own stored action,
never cached, since a shipment's effective recommendation can change
across re-decisions while the underlying facts don't.

One new Alembic migration in `alembic_ai_state/versions/`, chained after
the current head (`ai_state_0014`), creating both tables — same style as
`20260918_0600_ai_state_0014_collection_case_decisions.py`.

## 3. Backend changes, by area

**3.1 Real delay/SLA-breach prediction per route (replaces the historical
re-aggregate in "Predict Delay")**

Extract two reusable pieces from `logistics_delay.py`, exactly like
`sweep_best_channel_offer`/`recovery_drivers` were extracted from
`collections_sim.py`:
- A function that, given `LogisticsDelayModels` and a route's real
  cohort features (`route_cohort_features(route_id)`), returns
  `(any_delay_prob, sla_breach_prob)` — two genuinely separate numbers
  (the audit's §4 finding: these must never be collapsed into one).
- The existing `predictive_drivers` builder, parameterized the same way
  `recovery_drivers()` is.

`OperationalLogisticsService` gains a real per-route (and, once shipments
are exposed, per-shipment) computation path using these, called from
`predict_delay()` instead of the current re-aggregate. The "SLA Risk"
badge on the route card itself should switch from the historical-rate
calculation to this real model's `sla_breach_prob` (still labeled
distinctly from `any_delay_prob`/"Delay prob.").

**3.2 Real reroute optimizer wired to "Recommend Reroute"**

Extract the existing cost-minimizing sweep in `logistics_delay.py` into a
reusable function taking a route + its real alternatives
(`get_route_alternatives`) and returning the same shape Collections'
`sweep_best_channel_offer` returns: best alternative, expected cost
delta, expected avoided SLA loss. `reroute()` calls this for real instead
of returning a static string, and the route card's own "Rec." field
becomes this optimizer's real output ("Maintain current route" or
"Reroute via {alternative}") instead of the 2-way hardcoded branch.

**3.3 Persistence for Reroute/Auto-Heal, governance tracks**

Mirror `CollectionsService._decide()`/`_build_case_output()` exactly:
- A shipment (or route-level batch of shipments — see §3.5) already
  covered by a canonical `trust_decisions` row (`target_entity_type=
  'SHIPMENT'`) is immutable — Approve/Modify/Escalate refuse with
  `immutable_trust_decision`, same as Collections' canonical guard.
- Otherwise, Reroute/Auto-Heal write to the new `route_shipment_decisions`
  table via a new `RouteShipmentDecisionRepository` (copy of
  `CollectionsCaseDecisionRepository`), preserving the optimizer's
  original recommendation separately from any human override, exactly
  per the "never overwrite the original AI recommendation" rule already
  enforced for Collections.
- Compliance for the live track is evaluated on demand via
  `evaluate_simulation_compliance()` fed a lightweight snapshot
  (`model_name`, `model_version`, `inputs`, `outputs`, `baseline_reference`,
  `driver_json`, `confidence`) — same pattern, no new compliance code.
- "Auto-Heal" becomes the terminal action that actually requires this
  gate to pass (or a human override) before it "executes" — satisfying
  the screen's own "approval-gated execution" claim for the first time.
  A mandatory compliance FAIL still blocks it even after approval, same
  rule as everywhere else in this app.

**3.4 Real SLA Report**

New endpoint `GET /logistics/routes/{route_id}/sla-report` aggregating,
per route, real counts already available from `shipments`: active
shipments, on-time vs at-risk (by real `sla_breach`/`delay_minutes`),
expected-breach count (from the real `sla_breach_prob` in §3.1, not a
guess), average delay, cost exposure (`SUM(baseline_cost_inr)` for
at-risk shipments), and the real drivers from §3.1. No new tables needed
— pure aggregation over existing data plus the reused model.

**3.5 Shipment drill-down**

New endpoint `GET /logistics/routes/{route_id}/shipments` returning real
`shipment_id`, status, `expected_arrival`/`actual_arrival`, per-shipment
delay/SLA-breach probability (§3.1's function applied at the individual
shipment's own features rather than the route cohort average), current
warehouse (via `warehouse_events`), and — since there's no real vehicle-
availability table (confirmed absent in the audit) — `shipments.vehicle_id`
shown as-is with an honest label, never a fabricated "available/
unavailable" state. This is what makes "12 active shipments, 3 at risk"
in the target flow real rather than illustrative.

**3.6 Warehouse explainability**

Extend `SignalOut` (or add a sibling endpoint) to return the real
threshold value alongside the current value and tone (all three
thresholds already exist as constants in `operational_logistics.py` —
just expose them), plus — cheaply, from data already joined —
which real routes touch that warehouse, so "is this affecting any
routes" is a real join, not new logic.

**3.7 Route prioritization**

Replace the `(-sla_risk, name)` sort with a scoring function in the same
spirit as `app/services/collections_priority.py`: combine real SLA-breach
probability, real cost exposure (`SUM` of at-risk shipments' cost, not
just the average), and real affected-shipment count into a documented,
explainable point score (Critical/High/Medium/Low), reusing that exact
module's pattern (thresholds as named constants, a `reason` string
listing contributing factors, click-to-explain on the frontend).

## 4. Frontend changes

- Route card actions wired to the new real responses (drop
  `useFireMutation`'s discard-the-response behavior for these three
  mutations — use real `useMutation` objects with `onSuccess`/`onError`,
  exactly as Collections' Approve/Modify/Review were converted).
- Auto-Heal dialog renders the backend's real returned step list instead
  of the hardcoded JSX array.
- Reroute's "Rerouted" indicator comes from the persisted decision status
  returned by the API, not local component state.
- SLA Report button opens a real dialog populated by §3.4's endpoint.
- New shipment drill-down view under each route card (list from §3.5),
  including each shipment's own explainable delay/SLA-breach numbers.
- Warehouse tiles become click-to-explain (same `infoDetail` dialog
  pattern already built for Collections' KPI/Agent Swarm cards).
- Route Priority badge, click-to-explain, same pattern.
- No redesign of the existing layout/styling — same card shapes, same
  panel structure, same interaction model as today.

## 5. Testing plan

Mirrors the Collections test suite shape:
- KPI/aggregate correctness for route cards and warehouse signals
  (already real — add regression tests since none currently exist for
  `operational_logistics.py`'s math).
- Delay/SLA-breach probability matches direct model calls for a known
  seeded route.
- Reroute optimizer picks the real minimum-expected-cost alternative;
  "maintain route" case when no alternative beats the current one.
- Approve/Reroute/Auto-Heal persistence: creates/updates exactly one
  `route_shipment_decisions` row, never a duplicate.
- Canonical `SHIPMENT` trust_decisions rows are immutable via these
  actions (422 `immutable_trust_decision`), matching the Collections test.
- Original recommendation preserved separately from any human override.
- SLA report and shipment drill-down endpoints return real, non-fabricated
  aggregates against a seeded fixture.
- Priority score is deterministic and explainable (same style as
  `test_priority_is_backend_derived_and_explainable`).

## 6. Explicit non-goals for this pass

- No new vehicle-availability/fleet table — "Reassign vehicle" stays
  descriptive (shows `vehicle_id`) rather than fabricating a real
  reassignment capability that doesn't exist in the data.
- No deletion of the dead `app/services/logistics.py` stack — flagged as
  a separate cleanup, not bundled into this functional work.
- No change to Compliance Trust Ledger's own UI/list — Logistics'
  canonical `SHIPMENT` decisions are read via `TrustService`, never by
  modifying `trust.py`'s `list_decisions()` output, same boundary already
  respected for Collections.
- No change to Logistics Delay Simulation's own scenario-input UI/API —
  only its underlying model/optimizer code gets factored into reusable
  functions, exactly as `collections_sim.py` was refactored without
  changing its own behavior (verified via its existing passing tests).
