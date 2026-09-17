# Mahindra AI Command Center — Implementation Plan

**FastAPI + PostgreSQL + AI Backend for the existing Lovable frontend**

Version: 1.0 · Status: Approved for execution · Owner: Platform Engineering

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Analysis](#2-current-architecture-analysis)
3. [Frontend Feature Inventory & Data Flow](#3-frontend-feature-inventory--data-flow)
4. [Business Logic Currently in the Frontend (to be extracted)](#4-business-logic-currently-in-the-frontend)
5. [Target Architecture](#5-target-architecture)
6. [Backend Folder Structure](#6-backend-folder-structure)
7. [PostgreSQL Schema Design](#7-postgresql-schema-design)
8. [API Design](#8-api-design)
9. [AI Architecture](#9-ai-architecture)
10. [Frontend Integration Strategy](#10-frontend-integration-strategy)
11. [Synthetic Data Strategy](#11-synthetic-data-strategy)
12. [Migration Strategy](#12-migration-strategy)
13. [Feature-by-Feature Roadmap & Phases](#13-feature-by-feature-roadmap--phases)
14. [Testing Strategy](#14-testing-strategy)
15. [Deployment Strategy](#15-deployment-strategy)
16. [Risks & Mitigation](#16-risks--mitigation)
17. [Future Scalability Recommendations](#17-future-scalability-recommendations)
18. [Deliverables Checklist](#18-deliverables-checklist)

---

## 1. Executive Summary

The Mahindra AI Command Center currently ships as a **Lovable-generated TanStack Start (React 19) frontend** where **100% of the business data and logic lives in client-side TypeScript** (`src/lib/mock-data.ts` ≈ 730 lines, `src/lib/copilot.ts` rule engine, simulation formulas embedded in route components, `localStorage` for PoC state). There is no backend, no database, and no API.

This plan transforms the system into:

- **Frontend** — untouched Lovable app (`frontend/`), converted into a pure presentation layer that fetches from REST APIs.
- **Backend** — Python **FastAPI** (`backend/`) with Clean/Layered Architecture (routes → services → repositories).
- **Database** — **PostgreSQL 16** via **SQLAlchemy 2.x (async)** + **Alembic** migrations + repository pattern.
- **Validation** — **Pydantic v2** schemas for every request/response.
- **AI layer** — modular `backend/app/ai/` package (copilot engine, simulation engines, causal graph, scoring, forecasting) behind a service layer, replaceable without touching routes.
- **Data** — deterministic synthetic seed data for every entity so the app is fully functional offline.

**Invariant:** zero visual/UX changes. Only frontend files that perform data access may change (API client, query hooks, env config). Every formula, recommendation, and rule is reproduced bit-for-bit in Python so outputs are identical.

---

## 2. Current Architecture Analysis

### 2.1 Repository layout (today)

```
Mahindra AI Nexus/
├── .git/
├── frontend/                    # Lovable app (moved here to prepare monorepo)
│   ├── src/
│   │   ├── routes/              # 13 TanStack Router pages (flat, all children of __root)
│   │   ├── components/
│   │   │   ├── layout/          # Sidebar, TopBar, CopilotPanel, DemoOverlay
│   │   │   ├── ui/              # ~50 shadcn/ui primitives + custom Panel/StatPill/etc.
│   │   │   ├── executive-summary.tsx
│   │   │   └── poc-roadmap.tsx
│   │   ├── lib/                 # app-context, copilot engine, mock-data, utils, error libs
│   │   ├── hooks/use-mobile.tsx
│   │   ├── router.tsx / start.ts / server.ts / routeTree.gen.ts
│   │   └── styles.css           # Tailwind v4 OKLCH dark "cockpit" theme
│   ├── docs/                    # initial_aim.txt (2089 lines), README.md (1845 lines)
│   ├── package.json             # React 19, TanStack Start/Router/Query, Tailwind 4, Bun
│   └── vite.config.ts           # @lovable.dev/vite-tanstack-config preset
└── (backend/ does not exist yet)
```

### 2.2 Frontend tech stack (frozen — do not upgrade/replace)

| Concern | Technology |
|---|---|
| Framework | React 19 + TanStack Start v1 (SSR via Nitro/Cloudflare) |
| Routing | TanStack Router, file-based, 13 flat routes |
| Server data | TanStack Query v5 (installed, `QueryClient` in router context — currently unused for data) |
| Styling | Tailwind CSS v4, shadcn/ui (New York), Radix UI, lucide-react icons |
| Charts | Custom inline SVG (`Sparkline`, `MiniBar`, SVG causal graph) — no chart lib dependency |
| State | React Context (`AppProvider`): PoC list (localStorage), copilot messages, scenario, executive mode, demo step |
| Forms/validation | react-hook-form + zod (installed, unused) |
| Build/runtime | Vite 8, Bun, ESLint 9 + Prettier |
| Hosting constraint | **Lovable-connected repo** — never rewrite pushed history; keep branch buildable |

### 2.3 Where data & logic live today

| Location | What it contains | Migration target |
|---|---|---|
| `lib/mock-data.ts` | KPIs, recommendations, solution buckets (6 buckets, ~25 solutions), dealers (5), leads (5), finance products (8), collections cases (5), logistics routes (5), carbon credits (5), trust ledger (5), AI agents (10), suggested prompts | PostgreSQL tables + seed script |
| `lib/copilot.ts` | Keyword-matching copilot rule engine (7 intent branches + fallback) + executive summary template generator | `ai/copilot/` + `ai/prompts/` behind `CopilotService` |
| `routes/simulation.tsx` | 5 simulation formulas (`AutoSales`, `DealerAlloc`, `CollectionsSim`, `LogisticsSim`, `CreditPricing`) | `ai/simulation/` engines |
| `routes/circularity.tsx` | ELV valuation formula + risk flags | `ai/scoring/elv_valuation.py` |
| `routes/finance.tsx` | EMI formula | `ai/scoring/emi.py` |
| `routes/mobility-twin.tsx` | Causal graph nodes/edges, KPIs, Q&A pairs | `causal_nodes`, `causal_edges`, `mobility_kpis`, `causal_qa` tables |
| `lib/app-context.tsx` | PoC roadmap CRUD persisted to `localStorage("mah_poc")` | `poc_items` table + REST API |
| Route-local state | Approve/review/modify statuses (recommendations, collections rows, trust ledger rows, lead conversions) | Status columns on respective tables + PATCH/POST endpoints |

### 2.4 Missing backend functionality (gap analysis)

1. No HTTP API of any kind.
2. No persistence — page reload resets all approvals/statuses; PoC survives only via browser storage.
3. No identity/authorization (auth **hooks** only, per requirements — no login UI added).
4. No audit trail of user decisions (approvals "logged to Trust Ledger" are toasts only).
5. No real compute — simulations/copilot run in the browser.

---

## 3. Frontend Feature Inventory & Data Flow

### 3.1 Route → data → interaction map

| Route | Page | Data consumed | User interactions (writes) |
|---|---|---|---|
| `/` | Executive Overview | `KPI_CARDS` (6), `RECOMMENDATIONS` (5) | Explain KPI (modal), Simulate rec (modal), **Approve**, **Human Review** |
| `/catalogue` | AI Solution Catalogue | `SOLUTION_BUCKETS`, `SOLUTION_TAGS` | Tag filter, **Add to PoC**, View Demo (exec summary modal) |
| `/simulation` | Simulation Center | `REGIONS`, `MODELS` lookups | 5 simulators: slider/select inputs → **Run Simulation**; Explain Drivers; Generate Executive Summary; **Approve Recommendation** |
| `/mobility-twin` | Auto Mobility Twin | 12 causal `NODES`, 12 `EDGES`, 7 KPIs, 4 Q&A | Node selection (client), Ask Causal Twin (Q&A lookup) |
| `/dealer` | Dealer Revenue Optimizer | `DEALERS` (5), `DEALER_LEADS` (5) | Dealer switch, **Generate Pitch**, **Send WhatsApp**, **Schedule Test Drive**, **Mark Converted**, Deliver Coach Playbook |
| `/finance` | Financial Services | `FIN_PRODUCTS` (8), customer twin | **Send for Approval** (Draft→Under Review), Explain, RM Script, **Simulate Offer** (EMI) |
| `/collections` | Collections AI Swarm | 6 swarm agents, 5 KPI tiles, `COLLECTIONS` (5) | Per row: **Approve**, **Modify** (choose action), **Human Review**, view Trust Ledger |
| `/logistics` | Logistics Control Tower | `ROUTES` (5), 5 warehouse signals | **Predict Delay**, **Recommend Reroute**, **Auto-Heal** (approve 5-step workflow), SLA Report |
| `/circularity` | Circular Economy | `CREDITS` (5), RVSF metrics, dMRV Q&A | **ELV estimate** (formula), **Reprice**, **Match Buyer**, ESG Report, Trace, dMRV ask |
| `/xr` | AR/VR Experience | 4 experience cards | Launch demo modals (read-only) |
| `/trust` | Compliance Trust Ledger | `TRUST_LEDGER` (5), 5 compliance rules | **Approve**, **Reject** (with reason), **Escalate**, view Lineage |
| `/agents` | AI Factory Agents | `AGENTS` (10) | Inspect agent (modal), Run Agent Workflow (client animation) |
| `/copilot` | Analytics Copilot | `SUGGESTED_PROMPTS` | Chat turns via rule engine, Simulate, **Approve**, Export Summary |
| (global) | TopBar / CopilotPanel / DemoOverlay | scenario list, copilot engine, 8-step tour | Open copilot, chat, start demo |

### 3.2 Current data flow

```
mock-data.ts ──static import──▶ route components ──render──▶ JSX
copilot.ts ─────call──────────▶ copilot.tsx / copilot-panel.tsx
app-context.tsx ◀─localStorage─▶ PoC roadmap (only persisted state)
user clicks ──▶ toast only (no server side-effect)
```

### 3.3 Target data flow

```
browser component ──TanStack Query hook──▶ api-client (fetch, VITE_API_BASE_URL)
        │                                        │  JSON over HTTPS
        ▼                                        ▼
 optimistic cache (invalidation)          FastAPI /api/v1/* routes
                                                │
                                     service layer (business rules)
                                       │                  │
                              repository layer      ai/* engines
                                       │
                                 PostgreSQL 16
```

---

## 4. Business Logic Currently in the Frontend

These formulas/rules are reproduced **exactly** in Python (same constants, same rounding) so demo outputs are identical. Unit tests pin each formula against the current TS implementation.

### 4.1 Simulation engines (`routes/simulation.tsx`)

**AutoSales** — inputs: `region`, `model`, `discount%`, `bonus`, `campaign`, `intensity`
```
regionBoost  = West:1.15 | North:1.08 | else 1.0
intensityMul = High:1.25 | Medium:1.1 | Low:1.0
uplift = round((discount*1.4 + bonus/6000 + campaign*3) * regionBoost * intensityMul)
margin = round(-(discount*1.1) - campaign*0.3)
cancel = max(0, round(10 - intensityMul*4 - bonus/20000))
rev    = round(uplift*3.2 + margin*1.8)
conf   = min(97, 72 + round(intensityMul*8 + regionBoost*6))
```

**DealerAlloc** — `delay = max(1, wait - round((demand+capacity)/20))`, `rev = round(units*(demand/100)*18)`, `csat = min(95, 70 + round(capacity/5))`, fixed split `West 45% · North 30% · South 25%`.

**CollectionsSim** — `prob = Low:82|Medium:68|High:42`; `cost = Field:1200+field*8 | Voice:320 | Digital:90`; `friction = Field:62|Voice:34|Digital:12`; `net = round(prob*(Settlement?0.7:1.0)*42)`.

**LogisticsSim** — `delay = min(95, wh*0.3 + weather*0.4 + (100-vehicle)*0.2)`; `breach = High? 42+weather/3 : 18+weather/4`; `cost = round(wh*320 + weather*480)`; reroute text `Via Panvel bypass`.

**CreditPricing** — `price = round(800 + demand*15 + trace*6 - supply*5)`; `closure = min(95, 30 + demand*0.4 + trace*0.3 - supply*0.15)`; `match = min(98, 40 + demand*0.5 + verif*0.2)`; compliance risk from `verif` thresholds (40/70).

### 4.2 ELV valuation (`routes/circularity.tsx`)

```
price = round(80000 - age*3800 + condition*350 + docs*120)
recoverable = round(price * 0.7)
risk_flags = docs < 60 ? ["Incomplete RC", "Missing insurance papers"] : ["OK"]
```

### 4.3 Finance (`routes/finance.tsx`)

```
emi = round(offer/36 + offer*0.006)
```

### 4.4 Copilot rule engine (`lib/copilot.ts`)

Keyword matcher, ordered branches (first match wins): `booking+pune` → `dealer|leakage` → `roll forward|finance|collections` → `logistics|sla|route` → `credit|circularity|carbon` → `warranty` → `board|summary|roi|use case` → fallback. Each branch returns: answer, explanation, sql, python, optional chart/table, action, confidence. Executive summary generator returns 9 templated fields for any `use_case` string.

### 4.5 Other logic

- Catalogue tag filtering (bucket-level tag match).
- PoC roadmap: dedupe by name, timestamp, priority/complexity derived from list position (`["High","High","Medium","Medium","Low"]` cyclic).
- Status transitions: recommendations (`Approved`/`Under Review`), collections (`Approved`/`Human Review`/custom action), trust (`Approved`/`Rejected`+reason/`Escalated`), leads (`Message Sent`/`Converted` + test-drive slot), logistics (`rerouted`), finance twin (`Draft`→`Under Review`).

---

## 5. Target Architecture

```
┌─────────────────────────────┐        ┌──────────────────────────────────────────┐
│  frontend/ (Lovable, frozen │  REST  │  backend/  (Python 3.12, FastAPI)        │
│  UI; API client + hooks     │◀──────▶│  ┌────────────────────────────────────┐  │
│  added)                     │ /api/v1│  │ api/v1 routers (Pydantic I/O)      │  │
│  TanStack Query cache       │        │  ├────────────────────────────────────┤  │
└─────────────────────────────┘        │  │ services (business rules, txns)    │  │
                                       │  ├────────────────────────────────────┤  │
                                       │  │ repositories (SQLAlchemy 2.x async)│  │
                                       │  ├────────────────────────────────────┤  │
                                       │  │ ai/ (copilot, simulation, causal,  │  │
                                       │  │    scoring, forecasting, llm)      │  │
                                       │  └────────────────────────────────────┘  │
                                       │            │ asyncpg pool                │
                                       │            ▼                             │
                                       │      PostgreSQL 16                       │
                                       └──────────────────────────────────────────┘
```

**Layering rules**

- `api/` — thin: parse/validate (Pydantic), call one service, return schema. No SQL, no formulas.
- `services/` — all business rules; orchestrate repositories + AI engines; own transactions.
- `repositories/` — data access only; one repository per entity; no business rules.
- `ai/` — pure computation modules with typed interfaces; injected into services (FastAPI `Depends`).
- `models/` (SQLAlchemy) ↔ `schemas/` (Pydantic) kept separate; mapping happens in services/schemas.

**Cross-cutting**

- **DI:** FastAPI `Depends` for session, repositories, services, AI engines.
- **Config:** `pydantic-settings`, single `Settings` object from env (`.env`).
- **Errors:** domain exceptions → exception handlers → structured JSON (`{detail, code, request_id}`); consistent 4xx/5xx.
- **Logging:** `structlog` JSON logs, request-id middleware.
- **Auth hook:** `get_current_user` dependency returning an anonymous demo user for now; designed to swap to JWT without route changes.
- **Versioning:** all routes under `/api/v1`.
- **Caching:** in-process TTL cache (`cachetools`) for reference data (buckets, agents, prompts); invalidated on writes. Redis optional later.
- **Background tasks:** FastAPI `BackgroundTasks` for audit-log flush; Celery/Arq only if real ML jobs appear later.

---

## 6. Backend Folder Structure

```
backend/
├── app/
│   ├── main.py                     # app factory, router mount, middleware, handlers
│   ├── core/
│   │   ├── config.py               # pydantic-settings (env-driven)
│   │   ├── logging.py              # structlog setup
│   │   ├── errors.py               # domain exceptions + handlers
│   │   └── security.py             # auth hook (anonymous → JWT-ready)
│   ├── database/
│   │   ├── base.py                 # DeclarativeBase, UUID/audit mixins
│   │   ├── session.py              # async engine, sessionmaker, pooling config
│   │   └── seed.py                 # synthetic data loader (idempotent)
│   ├── models/                     # SQLAlchemy 2.x Mapped models (one file per domain)
│   ├── schemas/                    # Pydantic v2 request/response models
│   ├── repositories/               # BaseRepository + per-entity repositories
│   ├── services/                   # overview, catalogue, simulation, dealer, finance,
│   │                               # collections, logistics, circularity, trust,
│   │                               # agents, mobility, copilot, poc services
│   ├── ai/
│   │   ├── copilot/                # intent router + response builders
│   │   ├── simulation/             # auto_sales, dealer_allocation, collections,
│   │   │                           # logistics_delay, credit_pricing engines
│   │   ├── causal/                 # graph model, traversal, Q&A
│   │   ├── scoring/                # elv valuation, lead scoring, emi
│   │   ├── forecasting/            # hook: sparkline/trend generation
│   │   ├── anomaly_detection/      # hook: warranty batch anomaly narrative
│   │   ├── llm/                    # provider interface (rule-based impl now)
│   │   ├── prompts/                # template texts (copilot, exec summary)
│   │   ├── utils/
│   │   └── models/                 # serialized model artifacts (placeholder)
│   ├── api/
│   │   ├── deps.py                 # shared Depends factories
│   │   └── v1/
│   │       ├── router.py           # APIRouter aggregation
│   │       └── endpoints/          # overview.py, catalogue.py, simulations.py,
│   │                               # mobility.py, dealers.py, finance.py,
│   │                               # collections.py, logistics.py, circularity.py,
│   │                               # trust.py, agents.py, copilot.py, poc.py, xr.py
│   ├── middleware/                 # request-id, timing, CORS config
│   └── utils/
├── alembic/                        # env.py + versions/ (one migration per phase)
├── tests/
│   ├── unit/                       # services + ai engines (no DB)
│   ├── integration/                # repositories against test Postgres
│   └── api/                        # httpx AsyncClient end-to-end per endpoint
├── scripts/                        # seed_db.py, smoke_check.py
├── Dockerfile
├── docker-compose.yml              # postgres + api (dev)
├── pyproject.toml                  # ruff, mypy, pytest config
├── requirements.txt
├── .env.example
└── README.md
```

**Pinned core dependencies** (`requirements.txt`): `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]>=2.0`, `asyncpg`, `alembic`, `pydantic>=2.7`, `pydantic-settings`, `structlog`, `httpx` (tests), `pytest`, `pytest-asyncio`, `testcontainers[postgres]`, `python-dotenv`, `cachetools`. Optional AI extras (`scikit-learn`, `networkx`) isolated behind interfaces so the app runs without them.

---

## 7. PostgreSQL Schema Design

### 7.1 Conventions

- **PK strategy:** `UUID` (`gen_random_uuid`, pgcrypto) for transactional tables; natural string codes for pure reference data.
- **Audit fields:** `created_at`, `updated_at` (trigger-maintained) on all tables; `deleted_at` soft delete on mutable business tables.
- **Enums:** Postgres `ENUM` types for statuses (type-safe, indexable).
- **Indexing:** FKs indexed by default; partial indexes for active records; GIN on tag arrays.
- **Integrity:** CHECK constraints on ranges (0–100 percentages), FK `ON DELETE RESTRICT` for reference data, `CASCADE` for owned children (drivers, edges).
- **JSONB:** only for flexible payloads (chart/table payloads, lineage, workflow steps) — never a substitute for relational structure.

### 7.2 Table catalog

| # | Table | Key columns | Notes |
|---|---|---|---|
| 1 | `regions` | code PK (`West`...) | reference |
| 2 | `vehicle_models` | name PK | reference |
| 3 | `kpis` | id, label, value, trend, trend_up, confidence, sort_order | overview cards |
| 4 | `kpi_drivers` | id, kpi_id FK, driver_text, sort_order | cascade |
| 5 | `recommendations` | id, title, impact, confidence, risk ENUM, status ENUM(`pending/approved/under_review`), decided_at | partial idx `status='pending'` |
| 6 | `solution_buckets` | id, name, tag | 6 rows |
| 7 | `solutions` | id, bucket_id FK, name, problem, solution, differentiator, impact, sort_order | ~25 rows |
| 8 | `dealers` | id, name, leads, hot_leads, test_drives_pending, booking_prob, revenue_at_risk, leakage_pct, bay_util | |
| 9 | `dealer_leads` | id, dealer_id FK, name, vehicle, score, prob, action, revenue, status ENUM(`hot/warm/cool/message_sent/converted`), test_drive_slot | |
| 10 | `finance_products` | id, name, customers, risk, cross_sell, opportunity | |
| 11 | `customer_twins` | id, name, location, income_stability, repayment, products JSONB, nba JSONB, risk_decomposition JSONB, crosssell JSONB, approval_status ENUM | seeded twin (Suresh Jadhav) + synthetic extras |
| 12 | `collections_agents` | id, name, status ENUM | swarm |
| 13 | `collections_cases` | id, customer, dpd, outstanding, roll_forward, channel, action, prob, compliance_flag ENUM, status ENUM, modified_action | |
| 14 | `logistics_routes` | id, name, sla_risk, delay_prob, cost, recommended_action, rerouted bool | |
| 15 | `warehouse_signals` | id, label, value, tone | |
| 16 | `carbon_credits` | id, code, type, price, buyer_match, closure_prob, traceability, repriced_at | |
| 17 | `trust_decisions` | id, code (`AUTO-1042`), use_case, recommendation, data_sources, confidence, approval ENUM, risk ENUM, audit ENUM, status, rejection_reason, lineage JSONB | |
| 18 | `compliance_rules` | id, label, status | |
| 19 | `ai_agents` | id, name, role, status, last_activity, use_areas TEXT[] | GIN idx |
| 20 | `causal_nodes` | id, label, x, y, metric, trend, drivers JSONB, action | mobility twin graph |
| 21 | `causal_edges` | id, source_node_id FK, target_node_id FK | UNIQUE(source, target) |
| 22 | `mobility_kpis` | id, label, value, trend | |
| 23 | `causal_qa` | id, question, answer | |
| 24 | `poc_items` | id, name UNIQUE, bucket, priority, complexity, added_at | replaces localStorage |
| 25 | `copilot_sessions` / `copilot_messages` | session id, role ENUM, content, result JSONB, created_at | chat persistence |
| 26 | `simulation_runs` | id, domain ENUM, inputs JSONB, outputs JSONB, confidence, created_at | audit of every run |
| 27 | `xr_experiences` | id, code, title, use_case, feature, impact | |
| 28 | `users` | id, email UNIQUE, full_name, is_active | auth hook, seeded demo user |

All business tables carry `created_at`/`updated_at`; soft delete on #5, 9, 13, 16, 17, 24.

### 7.3 Alembic strategy

- `alembic init` wired to `app.database.session` (async engine via `run_async`).
- Migration `0001_initial_schema` generated via `--autogenerate`, then hand-reviewed (enums, indexes, checks, `updated_at` trigger).
- Seed data is **not** in migrations — loaded via `scripts/seed_db.py` (idempotent upserts), keeping migrations deterministic.

---

## 8. API Design

Base URL `{VITE_API_BASE_URL}` → `http://localhost:8000/api/v1` in dev. Response shapes mirror the **exact JSON the frontend components already consume** so component JSX never changes.

### 8.1 Endpoint catalog

| Method & Path | Purpose | Frontend consumer |
|---|---|---|
| `GET /health` | liveness/readiness | deploy probes |
| **Overview** | | |
| `GET /overview/kpis` | KPI cards + drivers | `index.tsx` |
| `GET /overview/recommendations` | recommendations + statuses | `index.tsx` |
| `PATCH /recommendations/{id}` | status: approve / human_review | `index.tsx` |
| **Catalogue** | | |
| `GET /catalogue/buckets?tag=` | filtered buckets | `catalogue.tsx` |
| `GET /catalogue/tags` | tag list | `catalogue.tsx` |
| **PoC** | | |
| `GET/POST/DELETE /poc` | roadmap CRUD (dedupe server-side) | `poc-roadmap.tsx`, context |
| `GET /poc/roadmap-plan` | phased rollout content | `poc-roadmap.tsx` |
| **Simulations** | | |
| `POST /simulations/auto-sales/run` | inputs → outputs | `simulation.tsx` |
| `POST /simulations/dealer-allocation/run` | | `simulation.tsx` |
| `POST /simulations/collections/run` | | `simulation.tsx` |
| `POST /simulations/logistics-delay/run` | | `simulation.tsx` |
| `POST /simulations/credit-pricing/run` | | `simulation.tsx` |
| `GET /simulations/meta` | regions + models + option lists | `simulation.tsx` selects |
| `GET /simulations/causal-drivers?domain=` | explain-drivers modal content | `simulation.tsx` |
| `POST /executive-summary` | body `{use_case}` → 9 fields | `executive-summary.tsx`, catalogue, simulation |
| **Mobility Twin** | | |
| `GET /mobility-twin/graph` | nodes + edges | `mobility-twin.tsx` SVG |
| `GET /mobility-twin/kpis` | 7 business health KPIs | `mobility-twin.tsx` |
| `POST /mobility-twin/ask` | body `{question}` → answer | `mobility-twin.tsx` |
| **Dealers** | | |
| `GET /dealers` | dealer list + metrics | `dealer.tsx` select + tiles |
| `GET /dealers/{id}/leads` | AI-scored leads | `dealer.tsx` table |
| `POST /dealers/{id}/leads/{lead_id}/pitch` | generated pitch text | pitch modal |
| `POST /dealer-leads/{id}/message` | mark WhatsApp sent | `dealer.tsx` |
| `POST /dealer-leads/{id}/test-drive` | body `{slot}` | test-drive modal |
| `POST /dealer-leads/{id}/convert` | mark converted | `dealer.tsx` |
| `GET /dealers/{id}/coach` | top action, best offer, best time, risk | AI Dealer Coach panel |
| **Finance** | | |
| `GET /finance/products` | 8 product cards | `finance.tsx` |
| `GET /finance/customers/{id}/twin` | twin profile + NBA + risk + cross-sell | `finance.tsx` |
| `POST /finance/twins/{id}/explain` | explanation bullets | explain modal |
| `POST /finance/twins/{id}/rm-script` | generated script | RM script modal |
| `POST /finance/twins/{id}/simulate-offer` | body `{amount}` → EMI + risk | simulate modal |
| `POST /finance/twins/{id}/submit-approval` | status → Under Review | `finance.tsx` |
| **Collections** | | |
| `GET /collections/metrics` | 5 headline tiles | `collections.tsx` |
| `GET /collections/agents` | swarm agents | `collections.tsx` |
| `GET /collections/cases` | prioritization table rows | `collections.tsx` |
| `POST /collections/cases/{id}/approve` | | row action |
| `POST /collections/cases/{id}/modify` | body `{action}` | modify modal |
| `POST /collections/cases/{id}/review` | send to human review | row action |
| `GET /collections/cases/{id}/ledger` | trust trail steps | ledger modal |
| **Logistics** | | |
| `GET /logistics/routes` | route cards | `logistics.tsx` |
| `GET /logistics/warehouse-signals` | 5 signals | `logistics.tsx` |
| `POST /logistics/routes/{id}/predict-delay` | updated delay prob | Predict Delay btn |
| `POST /logistics/routes/{id}/reroute` | sets rerouted flag | Recommend Reroute |
| `POST /logistics/routes/{id}/auto-heal` | approve 5-step workflow | Auto-Heal modal |
| **Circularity** | | |
| `POST /circularity/elv/estimate` | inputs → price, recoverable, risks | ELV tab |
| `GET /circularity/rvsf-metrics` | 5 tiles | RVSF tab |
| `GET /circularity/credits` | marketplace rows | Marketplace tab |
| `POST /circularity/credits/{id}/reprice` | new price | Reprice btn |
| `POST /circularity/credits/{id}/match-buyer` | | Match Buyer btn |
| `GET /circularity/dmrv/prompts` + `POST /circularity/dmrv/ask` | Q&A | dMRV tab |
| **Trust Ledger** | | |
| `GET /trust/decisions` | ledger rows | `trust.tsx` |
| `GET /trust/compliance-rules` | 5 rules | sidebar |
| `POST /trust/decisions/{id}/approve` | | row action |
| `POST /trust/decisions/{id}/reject` | body `{reason}` | row action |
| `POST /trust/decisions/{id}/escalate` | | row action |
| `GET /trust/decisions/{id}/lineage` | 6-step lineage | lineage modal |
| **Agents / XR** | | |
| `GET /agents` | registry + statuses | `agents.tsx` |
| `GET /agents/{id}` | inspect detail | inspect modal |
| `POST /agents/workflow/run` | returns staged flow messages | Run Agent Workflow |
| `GET /xr/experiences` | 4 experience cards | `xr.tsx` |
| **Copilot** | | |
| `GET /copilot/suggested-prompts` | 8 prompts | copilot page + panel |
| `POST /copilot/chat` | body `{message, session_id?}` → full `CopilotResult` | copilot page + panel |

### 8.2 Conventions

- Response shapes mirror existing TS types (`KpiCard`, `CopilotResult`, etc.); a thin `api-client` normalizes any casing differences so zero JSX edits are needed.
- Errors: `422` validation (FastAPI default), `404` missing entity, `409` duplicate PoC item, `500` structured `{detail, code, request_id}`.
- Mutations return the updated entity (UI updates state without refetch).
- OpenAPI auto-generated at `/docs` (Swagger) and `/redoc`; response models tagged per endpoint.

---

## 9. AI Architecture

### 9.1 Design principles

1. **Interface-first:** every AI capability is a Python protocol/ABC (`CopilotEngine`, `SimulationEngine`, `CausalGraphService`, `Scorer`, `Forecaster`, `LlmProvider`). Business services depend on interfaces; implementations are swappable (rule-based today → LLM/model-backed tomorrow).
2. **Deterministic first:** current rule engines and formulas are ported exactly so demo output is identical and unit-testable. No nondeterminism introduced.
3. **LLM-ready seam:** `ai/llm/provider.py` defines `complete(prompt, schema) -> str/JSON`. `RuleBasedCopilot` implements it now; an `OpenAICopilot` can be added behind an env flag (`AI_PROVIDER=rule|openai`) with no route changes. Prompts live in `ai/prompts/*.py`.
4. **No model files yet:** `ai/models/` holds the serialized-artifacts contract (placeholder) for future forecasting/anomaly models; services already call through interfaces so swapping is config-only.

### 9.2 Module map

```
ai/
├── copilot/
│   ├── engine.py            # CopilotEngine protocol + RuleBasedCopilot (port of copilot.ts)
│   ├── intents.py           # keyword→intent registry (ordered, first-match)
│   └── responses.py         # CopilotResult builders (sql/python/chart/table/action/conf)
├── simulation/
│   ├── base.py              # SimulationEngine protocol: run(inputs) -> SimulationResult
│   ├── auto_sales.py        # exact port of AutoSales formulas
│   ├── dealer_allocation.py
│   ├── collections_sim.py
│   ├── logistics_delay.py
│   └── credit_pricing.py
├── causal/
│   ├── graph.py             # nodes/edges model, adjacency, downstream impact traversal
│   └── qa.py                # Ask Causal Twin matcher (causal_qa table)
├── scoring/
│   ├── elv_valuation.py     # ELV formula + risk flags
│   ├── emi.py               # finance EMI formula
│   └── lead_scoring.py      # pitch generation + next-best-action text assembly
├── forecasting/             # TrendGenerator (sparkline series), hook for future models
├── anomaly_detection/       # Warranty batch narrative generator (hook for isolation forest)
├── llm/
│   ├── provider.py          # LlmProvider protocol + RuleBasedProvider
│   └── registry.py          # provider selection from Settings.AI_PROVIDER
├── prompts/
│   ├── executive_summary.py # 9-field template (port of generateExecutiveSummary)
│   ├── copilot_fallback.py
│   ├── rm_script.py
│   └── pitch.py
└── utils/                   # JS-compatible rounding helpers, numeric utils
```

### 9.3 Service → AI wiring example

```python
# services/simulation_service.py
class SimulationService:
    def __init__(self, engines: dict[str, SimulationEngine], repo: SimulationRunRepository):
        self._engines, self._repo = engines, repo

    async def run(self, domain: str, inputs: dict) -> SimulationResult:
        engine = self._engines[domain]          # KeyError -> 404 handler
        result = engine.run(inputs)             # pure computation
        await self._repo.save_run(domain, inputs, result)  # audit
        return result
```

---

## 10. Frontend Integration Strategy

**Allowed changes only.** Visual tree, routing, styling, icons, animations untouched.

### 10.1 New files (additive)

```
frontend/src/
├── lib/
│   ├── api-client.ts          # fetch wrapper: base URL, JSON, error normalization
│   └── api/
│       ├── overview.ts  ├── catalogue.ts  ├── simulations.ts  ├── mobility.ts
│       ├── dealers.ts   ├── finance.ts    ├── collections.ts  ├── logistics.ts
│       ├── circularity.ts ├── trust.ts    ├── agents.ts       ├── copilot.ts
│       └── poc.ts                            # one module per domain, typed fetch functions
└── hooks/
    └── use-api.ts             # TanStack Query hooks per endpoint (query keys, invalidation)
```

### 10.2 Modified files (data wiring only)

| File | Change |
|---|---|
| `src/lib/app-context.tsx` | PoC state hydrated from `GET /poc`; `addPoc`/`removePoc` call API with optimistic update + rollback; copilot messages optionally persist via session id. Context **shape stays identical**. |
| Each of the 13 route files | Replace `import { X } from "@/lib/mock-data"` with `useQuery` hooks; replace `useState` status maps with mutation-backed state; replace inline formula calls with API calls. **JSX structure unchanged.** |
| `src/components/layout/copilot-panel.tsx` | `generateCopilotResponse()` → `POST /copilot/chat` (same `CopilotResult` shape). |
| `src/components/executive-summary.tsx` | `generateExecutiveSummary()` → `POST /executive-summary`. |
| `src/lib/copilot.ts` | **Deleted** (logic moved to backend). Types re-exported from `api/copilot.ts`. |
| `src/lib/mock-data.ts` | **Deleted last** (Phase 6) after every consumer is migrated; interim phase keeps it as fallback behind a feature flag. |

### 10.3 Environment configuration

- `frontend/.env.example` → `VITE_API_BASE_URL=http://localhost:8000/api/v1` (Vite injects `VITE_*` automatically via the Lovable config).
- SSR note: TanStack Start renders server-side; data hooks use client-only fetching (`useQuery` inside components, no route loaders hitting the backend) so the Nitro server never needs backend access. Loading states reuse existing `shimmer`/skeleton utilities already in the theme — no new visual elements.

### 10.4 Parity guarantee

1. Every endpoint's response JSON is validated against the current TS type definitions (contract tests: exported TS shapes ↔ Pydantic schemas).
2. Snapshot/visual smoke: `bun run build` + preview, walk all 13 routes comparing screenshots before/after (manual checklist in Phase 6).
3. `frontend/docs/initial_aim.txt` remains the UX acceptance spec.

---

## 11. Synthetic Data Strategy

`backend/scripts/seed_db.py` (also exposed as `POST /admin/seed` in dev-only builds) loads **deterministic** data:

1. **Ported data** — every row from `mock-data.ts` verbatim (KPIs, recommendations, solutions, dealers, leads, products, cases, routes, credits, trust decisions, agents, graph, prompts, XR cards). Guarantees identical first render.
2. **Generated data** — `faker`-based expansions (flagged, not replacing ported rows): 50 dealers, 500 leads, 2,000 collections cases, 20 routes, 40 credits, 30 trust decisions, 5 copilot sessions — enables future pagination/filter demos without touching current UI.
3. **Derived data** — `simulation_runs` and `copilot_messages` seeded with sample history.
4. Idempotent upserts keyed on natural fields (`code`, `name`, `(source,target)` for edges).
5. Reproducible: fixed RNG seed; `--reset` flag drops & reseeds.

---

## 12. Migration Strategy

Order of operations minimizes risk and keeps the app working at every commit:

1. **Scaffold backend** (no frontend change). Health endpoint green.
2. **Schema + seed**: migrations + ported data; every table queryable.
3. **Read APIs first**, domain by domain. Frontend feature flag `VITE_DATA_SOURCE=mock|api` (default `mock`) lets each route flip independently.
4. **Write APIs** (approvals/statuses/PoC) once reads are stable per domain.
5. **AI endpoints** (simulations, copilot, ELV, exec summary) — outputs verified against TS originals via parity tests.
6. **Cutover**: flip default to `api`, soak, then delete `mock-data.ts`, `copilot.ts`, flag code.
7. Rollback = flip flag back to `mock` (until Phase 6 deletion).

---

## 13. Feature-by-Feature Roadmap & Phases

| Phase | Scope | Exit criteria |
|---|---|---|
| **0 — Foundations (2 d)** | Backend scaffold, config, logging, error handling, CORS, health, CI lint/typecheck; Docker Compose (pg16); Alembic init | `GET /health` 200; `docker compose up` works |
| **1 — Schema & Seed (3 d)** | All tables, mixins, indexes, triggers; migration 0001; `seed_db.py` ported data | Seed loads idempotently; integration tests green |
| **2 — Read APIs (4 d)** | Overview, catalogue, dealers, finance, collections, logistics, circularity (reads), trust (reads), agents, xr, mobility graph/kpis | Frontend renders 100% identical via flag |
| **3 — Write APIs (3 d)** | Recommendation approvals, lead actions, collections actions, logistics reroute/auto-heal, trust approve/reject/escalate, finance approval, PoC CRUD | Mutations persist across reload; toasts unchanged |
| **4 — AI Layer (4 d)** | Simulation engines ×5, ELV, EMI, copilot rule engine, executive summary, causal QA, agent workflow | Parity tests: identical outputs vs TS originals |
| **5 — Frontend Wiring (4 d)** | api-client, hooks, route-by-route switch, copilot panel, exec summary modal, context PoC | All routes on API; zero mock imports except flag fallback |
| **6 — Hardening (3 d)** | Delete mock-data/copilot.ts, remove flag, caching, rate limiting, audit log, Swagger review, basic load test, security pass (headers, input bounds) | Full visual walkthrough checklist passed |
| **7 — Docs & Deploy (2 d)** | README (root + backend), deployment guide, `.env.example` final, OpenAPI published | Team can onboard from docs alone |

Total ≈ 4 engineering-weeks (solo) — parallelizable across 2 engineers after Phase 1.

---

## 14. Testing Strategy

| Layer | Tooling | Coverage target |
|---|---|---|
| Unit (AI engines) | pytest + hypothesis (boundary inputs) | 100% of simulation formulas, ELV, EMI, copilot intents, exec summary — **parity fixtures** capturing exact TS outputs |
| Unit (services) | pytest + repository mocks | status transitions, dedupe, validation rules |
| Integration (repos) | testcontainers-postgres + pytest-asyncio | CRUD, constraints, soft delete, upserts |
| API (e2e) | httpx AsyncClient against app | happy path + 400/404/409/422 per endpoint |
| Contract | pydantic schemas vs exported TS types | response shape drift detection |
| Frontend smoke | `bun run build` + manual 13-route checklist | pixel parity |

Tests live in `backend/tests/{unit,integration,api}`; CI runs ruff + mypy + pytest on every push.

---

## 15. Deployment Strategy

**Local dev**

```
docker compose up -d postgres        # port 5432
alembic upgrade head && python scripts/seed_db.py
uvicorn app.main:app --reload        # port 8000, CORS http://localhost:5173/3000
cd frontend && bun run dev           # Lovable dev server, VITE_API_BASE_URL -> :8000
```

**Production (recommended)**

- **Backend:** containerized FastAPI (gunicorn+uvicorn workers) on any container host (Fly.io / Cloud Run / Azure Container Apps). Image from `backend/Dockerfile` (multi-stage, non-root).
- **Database:** managed PostgreSQL 16 (Neon/RDS/Azure Flexible) with automated backups; connection pooling (pool size 10, overflow 20; PgBouncer optional).
- **Frontend:** keep Lovable/Cloudflare deployment as-is (Nitro). Only change: production env `VITE_API_BASE_URL=https://api.<domain>/api/v1`.
- **Secrets:** `.env` per environment; never committed. `.env.example` documents all keys (`DATABASE_URL`, `AI_PROVIDER`, `CORS_ORIGINS`, `LOG_LEVEL`).
- **Ops:** `/health` probe, structlog JSON to stdout, request-id tracing, Alembic migrations run as release step (never auto-migrate on boot in prod).

**Constraint honored:** no git history rewrite; all work is additive commits on the connected branch (AGENTS.md/Lovable requirement).

---

## 16. Risks & Mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| Formula port drift (rounding/JS vs Python semantics) | Visual output mismatch | Parity fixtures from TS outputs; JS `Math.round` (half-up) replicated via `decimal` helper; property tests |
| SSR fetch failures (Nitro server can't reach API) | Blank pages | Client-only data fetching (`enabled` guards); SSR renders shell only |
| Lovable sync conflicts (edits from Lovable editor) | Merge pain | Frontend changes concentrated in `lib/api*` + `hooks/`; component JSX edits minimal & mechanical |
| Scope creep into redesign | Violates invariant | PR checklist: "does this change pixels? → reject" |
| Async DB misuse (blocking calls) | Latency spikes | asyncpg + SQLAlchemy async enforced; no sync ORM calls; mypy |
| Seed ≠ schema drift | Broken deploys | Migrations are source of truth; seed script runs in CI against fresh DB |
| Single demo user, no auth | Security review questions | Auth dependency seam present; endpoints documented as demo-tier; no PII in synthetic data |
| Copilot latency if later swapped to LLM | UX regression | Streaming endpoint (`POST /copilot/chat/stream`, SSE) pre-designed; rule engine remains default |

---

## 17. Future Scalability Recommendations

1. **Real LLM copilot** behind existing `LlmProvider` seam (RAG over solution catalogue + trust ledger).
2. **Redis** for session/copilot cache and rate limiting when multi-instance.
3. **Celery/Arq** for scheduled forecasting jobs writing to `forecast_outputs`.
4. **Pagination & server-side filtering** on dealer/collections tables (UI-ready once product asks).
5. **Event sourcing** for trust decisions (append-only ledger) if audit requirements harden.
6. **Observability:** OpenTelemetry traces from request-id middleware; Prometheus metrics endpoint.
7. **JWT/OIDC** (Entra ID) via existing `security.py` seam; row-level roles per business unit.
8. **Multi-region read replicas** for PostgreSQL if group-wide rollout.

---

## 18. Deliverables Checklist

- [ ] `backend/` production-ready FastAPI app (clean architecture)
- [ ] PostgreSQL schema (28 tables) + Alembic migration `0001`
- [ ] Repository + service layers, Pydantic v2 schemas
- [ ] `backend/app/ai/` modular AI package (copilot, simulation, causal, scoring, llm seam)
- [ ] REST API v1 (~70 endpoints) + Swagger at `/docs`
- [ ] Synthetic seed script (ported + generated data)
- [ ] Frontend API layer (`api-client.ts`, `api/*`, `use-api.ts`) — UI untouched
- [ ] Parity tests proving identical outputs
- [ ] `.env.example` (backend + frontend), `requirements.txt`, Dockerfile, docker-compose
- [ ] `implementation_plan.md` (this document), root `README.md`, backend `README.md`
- [ ] `backend/tests/` (unit/integration/api)
- [ ] Deployment + local-dev guides

**Acceptance:** the application looks and behaves exactly like the current prototype, with every number, status, and recommendation now sourced from FastAPI + PostgreSQL.
