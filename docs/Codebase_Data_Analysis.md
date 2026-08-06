# Codebase & Data Analysis

Complete file-by-file analysis of the Mahindra AI Command Center, performed
to prepare a production-grade FastAPI + PostgreSQL backend **without touching
the frontend**. Every file is inventoried with: purpose, business module,
data required, mock data currently used, backend API required, database
tables required, relationships, synthetic data required, and notes.

- Frontend: `frontend/src/` — 82 source files (TanStack Start + React + shadcn/ui)
- Backend: `backend/app/` — 130 Python files (FastAPI + SQLAlchemy 2 async)
- Data layer (new, additive): `data/generators/` (19 files), `data/synthetic/` (26 CSVs)
- Seeder (new, additive): `backend/database/seed_database.py`

**Mock-data status:** the frontend contains no hardcoded business data. All
screen data comes from the backend API (`/api/v1/*`), which is seeded from
`backend/app/database/seed_data.py` (curated baseline). The only frontend
fallback data is a single offline copilot answer in `hooks/use-api.ts`.

---

## 1. Business modules & screens

| Module | Route | Screen | Primary tables | Generator |
|---|---|---|---|---|
| Executive Dashboard | `/` (index) | Command Center overview | kpis, kpi_drivers, recommendations | overview_generator |
| Dealer Optimization | `/dealer` | Dealer Revenue Optimizer | dealers, dealer_leads | dealer_generator |
| Financial Twin | `/finance` | Finance products + customer twins | finance_products, customer_twins | finance_generator, customer_generator |
| Collections | `/collections` | Recovery AI Swarm | collections_agents, collections_cases, warehouse_signals | collections_generator, warehouse_generator |
| Logistics | `/logistics` | Control Tower | logistics_routes, warehouse_signals | shipment_generator, warehouse_generator |
| Circular Economy | `/circularity` | Credit marketplace + RVSF + dMRV + ELV | carbon_credits, warehouse_signals, causal_qa | circularity_generator, warehouse_generator, mobility_generator |
| Compliance | `/trust` | Trust Ledger | trust_decisions, compliance_rules | trust_generator |
| AI Factory | `/agents` | Agent swarm + workflow | ai_agents | agent_generator |
| XR | `/xr` | Immersive experiences | xr_experiences | agent_generator |
| Auto Mobility Twin | `/mobility-twin` | Causal graph + Q&A | causal_nodes, causal_edges, mobility_kpis, causal_qa | mobility_generator |
| Simulation | `/simulation` | 5 what-if engines | simulation_runs, regions, vehicle_models | simulation_generator, reference_generator |
| AI Copilot | `/copilot` (+ panel) | Conversational analytics | suggested_prompts, copilot_sessions, copilot_messages | copilot_generator |
| AI Catalogue | `/catalogue` | Buckets, solutions, PoC roadmap | solution_buckets, solutions, poc_items | catalogue_generator |

---

## 2. Frontend — routes (screens)

Every route follows the same pattern: typed queries from `hooks/use-api.ts`
→ `lib/api/endpoints.ts` → FastAPI `/api/v1` → PostgreSQL. None of these
files were modified in this task.

### `routes/index.tsx` — Executive Dashboard
- **Purpose:** landing screen; AI command center summary.
- **Entities/KPIs:** 6 KPI cards (Predicted Revenue Uplift, Leakage Prevented, Booking Conversion, Finance Approval Rate, Delivery Delay, Customer Satisfaction) each with trend, confidence and driver bullets.
- **Tables/cards:** KPI card grid; AI recommendation queue with approve / under-review actions.
- **Filters/dropdowns:** none. **Forms:** recommendation decision buttons (PATCH).
- **Data required:** `GET /overview/kpis`, `GET /overview/recommendations`, `PATCH /recommendations/{code}`.
- **Mock data used:** backend seed (kpis, kpi_drivers, recommendations).
- **DB tables:** kpis, kpi_drivers, recommendations.
- **Relationships:** kpis 1—N kpi_drivers; KPI values aggregate the dealer funnel.
- **Synthetic data:** overview_generator (6 kpis, 14 drivers, 8 recommendations).
- **Notes:** recommendation codes `REC-SYN-xxx` in synthetic set; decisions persist `decided_at`.

### `routes/dealer.tsx` — Dealer Revenue Optimizer
- **Purpose:** dealer network funnel with AI-scored leads.
- **Entities:** dealers (code, name, leads, hot leads, test drives pending, booking prob, revenue at risk, leakage %, bay util %); dealer leads (name, vehicle, score, prob, NBA action, revenue, status).
- **Tables:** dealer ranking table; lead funnel per selected dealer.
- **Cards:** dealer coach panel (AI coaching narrative).
- **Filters:** dealer selection (drill-down). **Forms:** message lead, schedule test drive (slot), convert lead.
- **API:** `GET /dealers`, `GET /dealers/{code}/leads`, `GET /dealers/{code}/coach`, `POST .../pitch`, `POST /dealer-leads/{id}/message|test-drive|convert`.
- **Mock data used:** backend seed (dealers, dealer_leads).
- **DB tables:** dealers, dealer_leads.
- **Relationships:** dealer_leads.dealer_id → dealers; leads reference vehicle_models pool.
- **Synthetic data:** dealer_generator (24 dealers, ~151 leads).
- **Notes:** status machine hot→message_sent→converted drives timestamp columns.

### `routes/finance.tsx` — Financial Twin
- **Purpose:** product portfolio + per-customer financial twins.
- **Entities:** finance products (name, customers, risk, cross-sell, opportunity); customer twins (name, location, income stability, repayment, products, NBA, risk decomposition, cross-sell, approval status).
- **Tables:** product cards grid; twin list.
- **Cards/modals:** twin detail with Explain (TwinExplain), RM script generator, offer simulator, submit-for-approval workflow.
- **Filters:** twin selection. **Forms:** amount input for simulate-offer.
- **API:** `GET /finance/products`, `GET /finance/twins`, `GET /finance/customers/{id}/twin`, `POST .../submit-approval|explain|rm-script|simulate-offer`.
- **DB tables:** finance_products, customer_twins.
- **Relationships:** twins share product pool with collections cases; approval status enum mirrors trust ledger concept.
- **Synthetic data:** finance_generator (10 products), customer_generator (48 twins).
- **Notes:** JSONB columns carry nested UI structures verbatim.

### `routes/collections.tsx` — Collections AI Swarm
- **Purpose:** delinquent account triage by agent swarm.
- **Entities:** collections agents (name, status), cases (customer, DPD, outstanding, roll-forward risk, channel, action, prob, compliance flag, status, modified action).
- **Tables:** metrics strip (warehouse_signals panel=collections_metrics), agent roster, prioritized case table.
- **Forms:** approve / modify (action textarea) / review case; audit ledger view.
- **API:** `GET /collections/metrics|agents|cases`, `POST /collections/cases/{id}/approve|modify|review`, `GET .../ledger`.
- **DB tables:** collections_agents, collections_cases, warehouse_signals.
- **Relationships:** DPD → roll-forward risk → action/flag chain.
- **Synthetic data:** collections_generator (8 agents, 40 cases).

### `routes/logistics.tsx` — Logistics Control Tower
- **Purpose:** freight corridor monitoring + warehouse signals.
- **Entities:** routes (name, SLA risk, delay prob, cost, recommended action, rerouted flag), warehouse signal tiles (panel=warehouse).
- **Tables:** route table with risk badges; signal tile grid.
- **Forms:** predict delay, reroute, auto-heal actions per route.
- **API:** `GET /logistics/routes|warehouse-signals`, `POST /logistics/routes/{id}/predict-delay|reroute|auto-heal`.
- **DB tables:** logistics_routes, warehouse_signals.
- **Synthetic data:** shipment_generator (12 routes), warehouse_generator (warehouse panel).

### `routes/circularity.tsx` — Circular Economy
- **Purpose:** credit marketplace, RVSF metrics, dMRV copilot, ELV valuation.
- **Entities:** carbon credits (code, type, price, buyer match, closure prob, traceability), RVSF metric tiles (warehouse_signals panel=rvsf), dMRV Q&A, ELV estimate form.
- **Tables:** credit table; metric tiles; chat panel.
- **Forms:** ELV estimator (vehicleType, age, condition, docs sliders); dMRV question input; reprice / match-buyer actions.
- **API:** `GET /circularity/credits|rvsf-metrics|dmrv/prompts`, `POST /circularity/dmrv/ask|elv/estimate|credits/{code}/reprice|match-buyer`.
- **DB tables:** carbon_credits, warehouse_signals, causal_qa (category=dmrv).
- **Relationships:** traceability → buyer_match → closure_prob.
- **Synthetic data:** circularity_generator (20 credits), mobility_generator (dMRV QA), warehouse_generator (rvsf panel).

### `routes/trust.tsx` — Compliance Trust Ledger
- **Purpose:** auditable AI decisions + compliance rule status.
- **Entities:** trust decisions (code, use case, recommendation, data sources, confidence, approval, risk, audit, rejection reason, 6-step lineage), compliance rules.
- **Tables:** decision table; rule checklist sidebar; lineage modal.
- **Forms:** approve / reject (reason) / escalate actions.
- **API:** `GET /trust/decisions|compliance-rules`, `POST /trust/decisions/{code}/approve|reject|escalate`.
- **DB tables:** trust_decisions, compliance_rules.
- **Synthetic data:** trust_generator (20 decisions, 6 rules).

### `routes/agents.tsx` — AI Factory
- **Purpose:** registered agent swarm + orchestrated workflow demo.
- **Entities:** ai_agents (name, role, status, last activity, use areas).
- **Tables:** agent grid; workflow run output panel.
- **API:** `GET /agents`, `POST /agents/workflow/run`.
- **DB tables:** ai_agents.
- **Synthetic data:** agent_generator (12 agents). **Notes:** `use_areas` is TEXT[] (JSON list in CSV).

### `routes/xr.tsx` — Immersive Experiences
- **Entities:** xr_experiences (code, title, use case, feature, impact).
- **API:** `GET /xr/experiences`. **DB tables:** xr_experiences.
- **Synthetic data:** agent_generator (6 experiences).

### `routes/mobility-twin.tsx` — Auto Mobility Causal Twin
- **Purpose:** causal decision graph with metrics + "Ask Causal Twin".
- **Entities:** causal nodes (label, x, y, metric, trend, drivers, action), edges, mobility KPIs, QA.
- **Cards:** SVG graph, KPI list, chat panel.
- **API:** `GET /mobility-twin/graph|kpis`, `POST /mobility-twin/ask`.
- **DB tables:** causal_nodes, causal_edges, mobility_kpis, causal_qa.
- **Relationships:** edges reference nodes twice (source/target); warranty risk node + Q&A.
- **Synthetic data:** mobility_generator (12 nodes, 12 edges, 8 KPIs, 14 QA).

### `routes/simulation.tsx` — Simulation Center
- **Purpose:** five what-if engines with sliders/selects + Explain Drivers modal.
- **Entities:** simulation inputs/outputs per domain; regions & vehicle models feed dropdowns; causal drivers per domain.
- **Filters/dropdowns:** region, model selects (`GET /simulations/meta`).
- **Forms:** AutoSales (discount, bonus, campaign, intensity), Dealer Allocation (units, demand, capacity, wait), Collections (risk, channel, offer, field), Logistics Delay (route, warehouse, vehicle, weather, sla), Credit Pricing (type, supply, demand, trace, verif).
- **API:** `POST /simulations/<domain>/run`, `GET /simulations/causal-drivers?domain=`, `GET /simulations/meta`.
- **DB tables:** simulation_runs (audit trail), regions, vehicle_models.
- **Synthetic data:** simulation_generator (25 runs), reference_generator (lookups).
- **Notes:** output keys are camelCase aliases (recommendedAction, suggestedSplit, priceBandLow…) — preserved exactly in synthetic outputs.

### `routes/copilot.tsx` — Dynamic Analytics Copilot
- **Purpose:** chat-based analytics with suggested prompts.
- **Entities:** suggested prompts, chat turns (role/text/result), CopilotResult payload (answer, explanation, sql, python, action, confidence).
- **API:** `GET /copilot/suggested-prompts`, `POST /copilot/chat`.
- **DB tables:** suggested_prompts (+ runtime copilot_sessions/copilot_messages).
- **Synthetic data:** copilot_generator (10 prompts) — templated so answers exist in causal_qa.

### `routes/catalogue.tsx` — AI Solution Catalogue
- **Purpose:** solution buckets + PoC roadmap builder.
- **Entities:** buckets (name, tag), solutions (name, problem, solution, differentiator, impact), PoC items (name, bucket, priority, complexity), roadmap plan.
- **Filters:** tag filter (`GET /catalogue/tags`).
- **Forms:** add/remove PoC items (persisted server-side, replaces localStorage).
- **API:** `GET /catalogue/buckets|tags`, `GET/POST/DELETE /poc`, `GET /poc/roadmap-plan`.
- **DB tables:** solution_buckets, solutions, poc_items.
- **Synthetic data:** catalogue_generator (9 buckets, 36 solutions, 6 PoC items).

---

## 3. Frontend — layout & shared components

| File | Purpose | Module | Data used | Notes |
|---|---|---|---|---|
| `routes/__root.tsx` | App shell: sidebar + top bar + outlet; error boundary | All | none | Untouched |
| `components/layout/sidebar.tsx` | Navigation for all 13 screens | All | static nav config | Untouched |
| `components/layout/top-bar.tsx` | Header with global copilot entry | All | none | Untouched |
| `components/layout/copilot-panel.tsx` | Slide-over copilot usable from any screen | Copilot | `useSuggestedPrompts`, `chatCopilot` | suggested_prompts table |
| `components/layout/demo-overlay.tsx` | Demo/branding overlay | All | none | Untouched |
| `components/executive-summary.tsx` | Board-summary generator dialog (use case → summary fields incl. "Suggested PoC Scope") | Executive | `generateExecutiveSummaryApi` | POST /executive-summary (AI-generated, no table) |
| `components/poc-roadmap.tsx` | PoC roadmap board with add/remove | Catalogue | `fetchPocs`, `addPoc`, `removePoc`, `fetchRoadmapPlan` | poc_items table |
| `components/ui/*.tsx` (44 files) | shadcn/ui primitives (accordion … tooltip) | Shared | none | Pure presentation; zero business data. Not modified. |

## 4. Frontend — hooks, lib, infra

| File | Purpose | Data relevance |
|---|---|---|
| `hooks/use-api.ts` | TanStack Query wrappers for every endpoint; includes the ONLY frontend fallback data (one offline copilot answer) | Central API contract layer — unchanged |
| `hooks/use-mobile.tsx` | Breakpoint hook | none |
| `lib/api/client.ts` | `apiFetch` wrapper (base URL, JSON, errors) | contract plumbing |
| `lib/api/endpoints.ts` | 60+ typed endpoint functions (full map above) | defines required backend API surface |
| `lib/api/types.ts` | 50+ TS interfaces mirroring API schemas | frontend contract definitions |
| `lib/app-context.tsx` | App-level React context | none |
| `lib/utils.ts` | `cn()` helper | none |
| `lib/error-capture.ts`, `lib/error-page.ts`, `lib/lovable-error-reporting.ts` | Error handling/reporting (Lovable) | none |
| `router.tsx`, `routeTree.gen.ts` | TanStack router + generated route tree | routing only |
| `server.ts`, `start.ts` | TanStack Start server bootstrap | infra |
| `styles.css` | Global theme (Mahindra gradient, dark theme) | styling only — untouched |

## 5. Frontend — configuration

| File | Purpose | Notes |
|---|---|---|
| `package.json`, `bun.lock`, `bunfig.toml` | Dependency manifest (bun runtime) | untouched |
| `vite.config.ts`, `tsconfig.json` | Build/TS config | untouched |
| `eslint.config.js`, `.prettierrc`, `.prettierignore`, `components.json` | Lint/format/shadcn config | untouched |
| `.lovable/project.json` | Lovable project binding | untouched |
| `.wrangler/deploy/config.json` | Cloudflare deploy config | untouched |
| `public/favicon.ico` | Branding | untouched |

---

## 6. Backend — API layer (`app/api/`)

Every screen already has its production endpoint. All read endpoints serve
PostgreSQL; write endpoints persist user actions (approvals, messages,
reroutes, repricing, decisions) — these are the real transactional writes.

| File | Endpoints | Tables touched |
|---|---|---|
| `v1/overview.py` | KPIs, recommendations, PATCH decision | kpis, kpi_drivers, recommendations |
| `v1/dealers.py` | dealers, leads, coach, pitch, message/test-drive/convert | dealers, dealer_leads |
| `v1/finance.py` | products, twins, twin detail/approval/explain/rm-script/simulate-offer | finance_products, customer_twins |
| `v1/collections.py` | metrics, agents, cases, approve/modify/review, ledger | collections_agents, collections_cases, warehouse_signals |
| `v1/logistics.py` | routes, signals, predict-delay, reroute, auto-heal | logistics_routes, warehouse_signals |
| `v1/circularity.py` | credits, rvsf-metrics, dmrv prompts/ask, ELV estimate, reprice, match-buyer | carbon_credits, warehouse_signals, causal_qa |
| `v1/trust.py` | decisions, rules, approve/reject/escalate | trust_decisions, compliance_rules |
| `v1/agents.py` | agents, workflow run | ai_agents |
| `v1/mobility.py` | graph, kpis, ask | causal_nodes, causal_edges, mobility_kpis, causal_qa |
| `v1/simulations.py` | meta, causal-drivers, 5× run | simulation_runs (audit), regions, vehicle_models |
| `v1/copilot.py` | suggested-prompts, chat | suggested_prompts, copilot_sessions, copilot_messages |
| `v1/catalogue.py` | buckets, tags | solution_buckets, solutions |
| `v1/poc.py` | poc CRUD, roadmap-plan | poc_items |
| `v1/executive_summary.py` | board summary generation | none (AI synthesis) |
| `v1/router.py` | v1 aggregation | — |
| `health.py`, `deps.py` | health check, DI | — |

## 7. Backend — domain layers

| Layer | Files | Role |
|---|---|---|
| `models/` (17) | ORM models — **schema source of truth** (30 tables incl. runtime) | analyzed in detail in Data_Model.md |
| `schemas/` (15) | Pydantic request/response models; camelCase aliases match frontend exactly | contract layer |
| `repositories/` (15) | Async DB access (select/merge/update) | data access |
| `services/` (16) | Business logic: aggregation, workflows, AI orchestration | rules live here |
| `database/base.py` | Base, mixins, portable JSON/ARRAY/UUID types | conventions |
| `database/session.py` | Async engine + session factory | connectivity |
| `database/seed.py` | Curated baseline seeder (uuid5 + merge, idempotent) | populates demo DB |
| `database/seed_data.py` | Curated content (1,058 lines) — the original "mock data", now DB-resident | baseline only |
| `core/` (6) | config, errors, logging, cache, security | hardening |
| `middleware/` (5) | audit log, rate limit, request context, security headers | hardening |
| `main.py` | FastAPI app assembly, CORS, lifespan | bootstrap |

## 8. Backend — AI layer (`app/ai/`)

| File | Role | Data dependency |
|---|---|---|
| `causal/drivers.py`, `causal/qa.py` | Simulation domain drivers; causal Q&A fallbacks | causal_qa themes |
| `copilot/engine.py`, `copilot/intents.py` | Intent routing → SQL/Python/answer | all tables (NL→SQL) |
| `llm/provider.py`, `llm/registry.py` | Rule vs OpenAI provider switch | config |
| `prompts/*.py` (5) | Fallback/executive/dMRV/finance/RM prompt templates | none |
| `scoring/elv_valuation.py`, `scoring/emi.py` | ELV price + EMI calculators | none |
| `simulation/*.py` (7) | Five deterministic engines + base | engine schemas |
| `utils.py` | Shared AI helpers | — |

---

## 9. Data flow summary (per screen)

```
frontend route → use-api hook → endpoints.ts → /api/v1 → service → repository
   → PostgreSQL table(s)  ←seeded by curated seed.py / new seed_database.py
```

No screen bypasses this chain. Replacing seed data with the synthetic CSV
load changes values, not contracts.

## 10. Synthetic data coverage vs requirements

| Requirement from brief | Covered by |
|---|---|
| Auto Mobility Twin | causal_nodes/edges/kpis/qa (mobility_generator) |
| Financial Twin | customer_twins + finance_products |
| Logistics | logistics_routes + warehouse_signals |
| Circular Economy | carbon_credits + rvsf signals + dMRV QA |
| AI Recommendations | recommendations (+ NBA inside twins/leads) |
| Executive Dashboard | kpis + kpi_drivers aggregated from funnel |
| Dealer Optimization | dealers + dealer_leads |
| Compliance | trust_decisions + compliance_rules |
| AI Copilot | suggested_prompts + causal_qa answer pool |
| Future AI models | simulation_runs audit trail; warranty_claims + notifications CSVs staged for Phase 2 |

## 11. Notes & assumptions

1. **Non-destructive verified:** no frontend file was created, renamed, edited or deleted by this task; all changes are inside `data/`, `docs/` and `backend/database/` (new), plus Faker installed in the backend venv.
2. The brief's example generator names map to this codebase as: booking → dealer_leads funnel; loan/insurance → finance_products cards; inventory → warehouse_signals; shipment → logistics_routes; warranty → causal graph + future warranty_claims; campaign spend → causal node + simulation inputs.
3. Currency/risk values are stored as display strings to preserve frontend contracts byte-for-byte.
4. Executive KPIs are aggregates of the generated populations, guaranteeing dashboard ↔ module consistency.
5. Runtime tables (copilot_sessions/messages) are intentionally not seeded — they accrue from live usage.
6. The curated demo database (`mahindra_ai`) and the synthetic dataset share business values by design; the seeder refuses to mix them (unique-collision guard). Staging/production databases load synthetic (later real) data only.
