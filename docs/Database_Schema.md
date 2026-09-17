# Database Schema

Physical PostgreSQL schema for the Mahindra AI Command Center. The ORM
models in `backend/app/models/` are the single source of truth; the CSVs in
`data/synthetic/` match this schema **column-for-column** so the seeder can
load them without transformation (only type coercion + 4 documented FK
helper resolutions).

## Conventions (every table)

- UUID primary key `id` (native PG `UUID`) — except `regions`/`vehicle_models` which use natural string PKs.
- `created_at` / `updated_at` timestamptz, server-populated.
- `deleted_at` soft-delete tombstone on: dealer_leads, collections_cases, carbon_credits, trust_decisions, recommendations, poc_items.
- Deterministic constraint naming (`uq_`, `ck_`, `fk_`, `ix_`, `pk_` conventions).
- Enums are PG `ENUM` types stored **lowercase**; the API maps them back to display casing for the frontend.

## ENUM types

| PG type | Values | Used by |
|---|---|---|
| `recommendation_risk` | low, medium, high | recommendations.risk |
| `recommendation_status` | pending, approved, under_review | recommendations.status |
| `dealer_lead_status` | hot, warm, cool, message_sent, converted | dealer_leads.status |
| `twin_approval_status` | draft, under_review, approved | customer_twins.approval_status |
| `collections_compliance_flag` | ok, review, escalate | collections_cases.compliance_flag |
| `collections_case_status` | pending, approved, human_review, modified | collections_cases.status |
| `agent_status` | active, reviewing, recommended | collections_agents, ai_agents |
| `trust_approval` | approved, human_review, pending, rejected, escalated | trust_decisions.approval |
| `trust_risk` | low, medium, high | trust_decisions.risk |
| `trust_audit` | complete, pending | trust_decisions.audit |
| `copilot_role` | user, assistant | copilot_messages.role |
| `simulation_domain` | auto_sales, dealer_allocation, collections, logistics_delay, credit_pricing | simulation_runs.domain |
| `signal_panel` | warehouse, collections_metrics, rvsf | warehouse_signals.panel |
| `qa_category` | mobility, dmrv | causal_qa.category |

## Table reference

### Lookup & master
| Table | Key columns | Unique | Notes |
|---|---|---|---|
| regions | `code` (PK) | — | 4 zones |
| vehicle_models | `name` (PK) | — | 5 models |
| users | email, full_name, is_active | email | demo principal fixed |
| dealers | code, name, leads, hot_leads, test_drives_pending, booking_prob, revenue_at_risk, leakage_pct, bay_util_pct, sort_order | code | CHECK 0–100 on prob/leakage/bay |
| finance_products | name, customers, risk, cross_sell, opportunity, sort_order | name | loan/insurance cards |
| solution_buckets | name, tag, sort_order | name | tag indexed |
| causal_nodes | label, x, y, metric, trend, drivers(JSON), action, sort_order | label | SVG coords |
| collections_agents | name, status, sort_order | name | |
| ai_agents | name, role, status, last_activity, use_areas(TEXT[]), sort_order | name | |

### Transactional
| Table | FK | Key columns | Constraints |
|---|---|---|---|
| dealer_leads | dealer_id → dealers CASCADE | name, vehicle, score, prob, action, revenue, status, test_drive_slot, message_sent_at, converted_at | score/prob 0–100 |
| customer_twins | — | name, location, income_stability, repayment, products(JSON), nba(JSON), risk_decomposition(JSON), cross_sell(JSON), approval_status | |
| collections_cases | — | customer, dpd, outstanding, roll_forward_risk, channel, action, prob, compliance_flag, status, modified_action | risk/prob 0–100 |
| logistics_routes | — | name, sla_risk, delay_prob, cost, recommended_action, rerouted, rerouted_at, auto_healed | sla/delay 0–100 |
| carbon_credits | — | code, type, price, buyer_match, closure_prob, traceability, repriced_at, buyer_matched_at | 3× 0–100 CHECK |
| trust_decisions | — | code, use_case, recommendation, data_sources, confidence, approval, risk, audit, rejection_reason, lineage(JSON) | confidence 0–100 |
| recommendations | — | code, title, impact, confidence, risk, status, decided_at | confidence 0–100; partial index on status=pending |
| simulation_runs | — | domain, inputs(JSON), outputs(JSON), confidence | confidence NULL or 0–100 |
| copilot_messages | session_id → copilot_sessions CASCADE | role, content, result(JSON), confidence | runtime only |

### Analytical / derived
| Table | FK | Key columns |
|---|---|---|
| kpis | — | code, label, value, trend, trend_up(bool), confidence |
| kpi_drivers | kpi_id → kpis CASCADE | driver_text, sort_order |
| solutions | bucket_id → solution_buckets RESTRICT | name, problem, solution, differentiator, impact |
| poc_items | — | name, bucket, priority, complexity |
| mobility_kpis | — | label, value, trend |
| causal_edges | source/target_node_id → causal_nodes CASCADE | UNIQUE(source,target) |
| causal_qa | — | category, question, answer |
| warehouse_signals | — | panel, label, value, tone |
| compliance_rules | — | label, status |
| xr_experiences | — | code, title, use_case, feature, impact |
| suggested_prompts | — | text (UNIQUE) |

## CSV ↔ PostgreSQL mapping rules

| CSV convention | PostgreSQL type | Seeder behaviour |
|---|---|---|
| plain text | VARCHAR/TEXT | pass-through |
| `"true"`/`"false"` | BOOLEAN | parsed |
| integer strings | INTEGER | `int()` |
| float strings | FLOAT | `float()` |
| compact JSON strings | JSONB | `json.loads` |
| JSON list strings | TEXT[] (`use_areas`) | `json.loads` |
| ISO-8601 strings | TIMESTAMP(TZ) | `fromisoformat`, tz stripped for naive columns |
| lowercase enum values | PG ENUM | validated against enum members |
| empty cell | nullable column | NULL |

### CSV helper/context columns (not part of the schema)

| CSV column | Handling |
|---|---|
| `dealers.region`, `dealers.city` | dropped (generator context) |
| `collections_cases.product` | dropped (generator context) |
| `dealer_leads.dealer_code` | resolved → `dealer_id` UUID |
| `kpi_drivers.kpi_code` | resolved → `kpi_id` UUID |
| `solutions.bucket_name` | resolved → `bucket_id` UUID |
| `causal_edges.source_label` / `target_label` | resolved → node UUIDs |

## Frontend contract preservation

The schema was reverse-engineered from the frontend mock data and the API
schemas in `backend/app/schemas/`:

- Field names match the JSON the frontend consumes (API layer maps snake_case DB columns to the camelCase keys where the UI expects them, e.g. `recommendedAction`, `suggestedSplit`, `priceBandLow`).
- Display-formatted values (`₹1.8 Cr`, `34K`, `+8.4%`) are stored as strings exactly as rendered.
- Nested structures (NBA, risk decomposition, lineage, drivers) are JSONB — the same shape the mock data provides.
- Enum display casing is restored by API schemas, so DB stores lowercase only.

Result: swapping mock data for API responses requires **zero** frontend changes.
