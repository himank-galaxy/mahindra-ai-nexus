# Mahindra AI Nexus data-layer refactor plan

## Audit baseline — 2026-08-12

The existing UI has 13 modules and a FastAPI endpoint family for each one. The
working frontend source directory is absent from the working tree, although
the tracked source is available in Git and the production bundle is present in
`frontend/.output`. No UI layout changes are part of this refactor.

The live PostgreSQL database is currently revision `0001`, contains only the
original 30 presentation-oriented tables, and was backed up before any work:
`backend/database/backups/mahindra_ai_pre_data_refactor_20260812.dump`.

The current runtime database setting points to SQLite and the PostgreSQL
container is therefore not the active application source of truth. The final
target is PostgreSQL only.

## Existing flow and mock locations

`frontend routes -> use-api hooks -> API client -> /api/v1 routers -> service
-> repository -> current presentation tables` is already established.

The following implementation is presentation/mock dependent and must be
replaced:

- frontend route fallbacks for mobility, circularity, collections, finance,
  logistics, simulations, trust, XR and PoC roadmap;
- static responses in the dealer coach/pitch, collections ledger, agent
  workflow, simulation driver list, executive summary and copilot fallback;
- `kpis`, `mobility_kpis`, `warehouse_signals`, `causal_nodes`, `causal_edges`
  and `causal_qa` rows that are copies of UI cards/graph/Q&A;
- merge and namespacing compatibility code in `services/merger.py` and
  `database/import_synthetic.py`, which exists only because mock and synthetic
  presentation rows collide.

## Synthetic datasets retained and repaired

These remain valid reference or operational inputs and will retain their
natural keys: regions, vehicle models, dealers, dealer leads, customer twins,
finance products, collections agents/cases, carbon credits, trust decisions,
compliance rules, AI agents, XR experiences, solution buckets/solutions,
suggested prompts and simulation-run audit records.

The following are corrected rather than treated as business sources:

- KPI, mobility KPI, route, warehouse/RVSF and causal graph CSVs become
  derived outputs and are no longer runtime sources.
- Causal Q&A is replaced by scoped database analytics.
- Warehouse signal cards are calculated from shipments, allocations and job
  cards.
- catalog/solution duplicate prevention uses normalized domain + name natural
  keys rather than frontend hiding.

## New source-of-truth records

Add SQLAlchemy models and an Alembic migration for:

- `causal_timeseries`
- `bookings`
- `test_drives`
- `cancellations`
- `vehicle_allocations`
- `shipments`
- `elv_assessments`
- `rvsf_job_cards`
- `dmrv_records`

All operational IDs will be deterministic UUID5 values. Generator output will
be daily, entity-aware and seeded, with foreign keys to existing dealers,
vehicle models and lead/booking records. Import will upsert only rows within
the refactor namespace and never truncate or drop unrelated data.

## Data-driven API cutover

1. Executive Overview aggregates bookings, cancellations, finance-linked
   bookings, shipments, trust decisions and dMRV value.
2. Mobility derives KPIs and graph node metrics from historical facts. PCMCI
   is used only when Tigramite is installed; otherwise the causal discovery
   endpoint returns a transparent data-derived correlation/lag graph and does
   not claim PCMCI output.
3. Dealer and finance views aggregate lead, booking, test-drive and customer
   facts; coach, pitch and explanations use the selected entity data.
4. Collections, logistics and circularity metrics aggregate cases, shipments,
   allocations, job cards, ELV assessments and dMRV records.
5. Copilot answers query database aggregates for recognised questions and
   returns an explicit no-data result for unknown questions instead of a
   canned answer.
6. Catalogue, agents, XR and reference prompts remain database reference data
   with deduplication enforced at import.

## Frontend contract and state plan

Restore the tracked `frontend/src` only after backend endpoints are verified.
Keep current request/response field aliases. Replace business fallbacks with
query state objects supplying loading, error and empty UI states. No failed
request may render a mock KPI, graph, card, Q&A response, table row or
simulation result.

## Safety and validation

- Apply only additive migrations; do not drop/truncate the database.
- Backup exists before any cleanup.
- Verify import idempotency, foreign keys, natural-key duplicates, API
  contracts and all 13 routes.
- Deprecate old presentation seed rows only after all response paths are
  proven to use operational synthetic records.
