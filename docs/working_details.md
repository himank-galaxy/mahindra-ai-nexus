# Mahindra AI Command Center — Complete Working Details

> **What this document is.** A full, beginner-friendly explanation of everything in this
> repository: what each file does, why it exists, how the pieces talk to each other, and how a
> request travels from a button click in the browser all the way to PostgreSQL and back.
>
> Every explanation below was written from the actual code. Nothing is assumed.
>
> **Repository layout at a glance**
>
> ```
> Mahindra AI Nexus/
> ├── backend/                 # Python FastAPI backend (built in this project)
> ├── frontend/                # React / TanStack Start UI (pre-existing, wired to the backend)
> ├── docs/                    # Project aim & notes
> ├── implementation_plan.md   # The master blueprint this project followed
> └── working_details.md       # This document
> ```

---

# Project Overview

## What problem does this project solve?

The repository started life as a **demo prototype** of the "Mahindra AI Command Center" — a
dashboard that shows AI-powered views over many Mahindra businesses (Auto sales, Financial
Services, Collections, Logistics, Circular Economy, Compliance, and more).

That prototype had a serious limitation: **all of its data and business logic lived inside the
frontend**. Numbers were hardcoded in a TypeScript file (`mock-data.ts`), "AI answers" were
produced by local functions, and nothing was saved anywhere. Refresh the page and every change
was lost. It could be shown in a demo, but it could never run in production.

This project's job was to turn that prototype into a **real full-stack application**:

1. Build a **production-grade backend** (FastAPI + PostgreSQL) that owns the data, the business
   rules, and the AI logic.
2. Move every piece of business logic that lived in the frontend (simulation formulas, copilot
   answers, scoring math) into backend modules **without changing a single number** — the UI must
   look and behave pixel-identically.
3. Rewire the frontend to fetch everything from REST endpoints instead of local mock files.
4. Remove the mock files completely once the live backend is proven.
5. Harden the API (rate limiting, caching, audit logging, security headers) and document it.

## Overall architecture

| Layer      | Technology                                                                 | Location     |
| ---------- | -------------------------------------------------------------------------- | ------------ |
| Frontend   | React 19, TanStack Start (SSR), TanStack Router, TanStack Query, Tailwind 4, shadcn/ui | `frontend/` |
| Backend    | FastAPI (async), Pydantic v2, SQLAlchemy 2.x (async), structlog            | `backend/`   |
| Database   | PostgreSQL 16 (Docker) — SQLite fallback for local dev/tests               | `backend/dev.db` or container |
| Migrations | Alembic (async)                                                            | `backend/alembic/` |
| AI layer   | Deterministic rule-based engines behind pluggable Protocol seams           | `backend/app/ai/` |
| Tests      | pytest + pytest-asyncio + httpx (ASGI in-process), 132 passing tests       | `backend/tests/` |

## High-level workflow

1. A user opens a page in the browser (e.g. **Executive Overview**).
2. React hooks call typed fetch functions in `frontend/src/lib/api/endpoints.ts`.
3. Those functions hit the FastAPI backend at `http://localhost:8000/api/v1/...`.
4. FastAPI validates the request, a **service** applies business rules, a **repository** runs SQL
   through an async SQLAlchemy session, and (for AI endpoints) an **AI engine** computes an answer.
5. The backend serializes a Pydantic response model to JSON.
6. TanStack Query caches the response; React re-renders the page with live data.
7. User actions (approve, convert, reprice…) go through the same path as POST/PATCH/DELETE calls
   and are persisted in PostgreSQL.

---

# Overall Architecture

## Layer diagram

```mermaid
flowchart TB
    subgraph Browser
        UI[React pages & components<br/>frontend/src/routes/*]
        Hooks[TanStack Query hooks<br/>hooks/use-api.ts]
        EP[Typed API functions<br/>lib/api/endpoints.ts]
        Client[apiFetch JSON client<br/>lib/api/client.ts]
    end

    subgraph Backend["FastAPI backend (backend/app)"]
        MW[Middleware stack<br/>CORS → SecurityHeaders → RequestContext → RateLimit → AuditLog]
        Router[API routers<br/>api/v1/*.py]
        Service[Services — business logic + transactions<br/>services/*.py]
        Repo[Repositories — the only SQL layer<br/>repositories/*.py]
        AI[AI engines — rule-based, pluggable<br/>ai/**]
    end

    DB[(PostgreSQL 16 / SQLite dev fallback)]

    UI --> Hooks --> EP --> Client -->|HTTP JSON /api/v1| MW
    MW --> Router --> Service
    Service --> Repo --> DB
    Service --> AI
    AI -.->|pure functions, no DB| Service
    Service -->|Pydantic response models| Router -->|JSON| Client --> Hooks --> UI
```

## Request lifecycle (compact)

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend (React)
    participant A as FastAPI router
    participant S as Service
    participant R as Repository
    participant D as Database

    U->>F: clicks "Approve"
    F->>A: POST /api/v1/trust/decisions/TD-01/approve
    A->>S: TrustService(db).approve_decision("TD-01")
    S->>R: get_by_code("TD-01")
    R->>D: SELECT ... WHERE code = 'TD-01'
    D-->>R: row
    R-->>S: TrustDecision model
    S->>S: decision.approval = APPROVED
    S->>D: COMMIT
    S-->>A: TrustDecisionOut (Pydantic)
    A-->>F: 200 JSON
    F->>F: invalidate ["trust","decisions"] cache → refetch list → UI updates
```

Key design rules enforced across the codebase:

- **Routers never touch SQLAlchemy.** They only translate HTTP ↔ service calls.
- **Services own transactions.** They are the only layer that calls `session.commit()`.
- **Repositories are the only layer that writes queries.** They never commit.
- **AI engines are pure functions/objects** with no database access, so they are trivially testable
  and swappable (`AI_PROVIDER=rule|openai`).
- **Every error** — no matter where it happens — comes back as the same JSON envelope:
  `{"detail": "...", "code": "machine_readable_code", "request_id": "..."}`.

---

# Phase-by-Phase Implementation

This is the heart of the document. The project was executed in eight phases (Phase 0 … Phase 7),
exactly as defined in `implementation_plan.md`. For each phase you will find: why it exists, what
was added, how the files interact, and a per-file table.

## Phase 0 — Foundations

### Why this phase exists

Before any business feature can be built, the application needs a skeleton that is safe to grow:
a way to create the app, configuration that comes from environment variables, structured logs,
one consistent error format, a database session that never leaks, a health check for load
balancers, and containers for deployment. Phase 0 is that skeleton. **Every later phase imports
from Phase 0 files.**

### What was added and why

| Piece | File(s) | Why |
| ----- | ------- | --- |
| App factory | `app/main.py` | One function `create_app()` assembles logging, middleware, error handlers and routers. Tests can create fresh app instances; behavior in production differs from dev via settings only. |
| Configuration | `app/core/config.py` | A single `Settings` object (pydantic-settings) reads `.env` / environment variables. Nothing else in the codebase reads `os.environ` directly, so there is exactly one place configuration can come from. |
| Logging | `app/core/logging.py` | structlog with context variables, bridged into Python's standard logging so third-party libraries log in the same format. Dev prints pretty console lines; production prints JSON. |
| Global error handling | `app/core/errors.py` | A small exception hierarchy (`AppError` → `NotFoundError`, `ConflictError`, `BadRequestError`, `DomainValidationError`, `ExternalServiceError`) plus FastAPI exception handlers. Guarantees the same JSON envelope for every failure, including unexpected crashes. |
| Database session | `app/database/session.py`, `app/database/base.py`, `app/api/deps.py` | Lazily-created async engine with connection pooling, a session factory, and the `get_db` FastAPI dependency that hands each request a session, rolls back on error and always closes. |
| Health checks | `app/api/health.py`, `app/schemas/health.py` | `GET /health` answers liveness and runs `SELECT 1` to verify the database — needed by Docker healthchecks and load balancers. |
| Docker | `Dockerfile`, `docker-compose.yml`, `.dockerignore` | Two-stage production image (non-root user, `/health` healthcheck) and a compose file that starts PostgreSQL 16 + the API together. |
| Alembic scaffold | `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako` | Async Alembic wired to the same `Settings.database_url`, importing `app.models` so future migrations see the ORM metadata. |
| Quality gates | `pyproject.toml`, `requirements.txt` | Ruff lint rules, mypy, pytest configuration, and the pinned dependency list. |

### How the files interact

```mermaid
flowchart LR
    ENV[.env / environment] --> CFG[core/config.py Settings]
    CFG --> LOG[core/logging.py setup_logging]
    CFG --> SES[database/session.py engine]
    CFG --> MAIN[main.py create_app]
    MAIN --> LOG
    MAIN --> ERR[core/errors.py handlers]
    MAIN --> MW[middleware/*]
    MAIN --> H[api/health.py]
    MAIN --> V1[api/v1/router.py]
    SES --> DEP[api/deps.py get_db]
    V1 -.uses.-> DEP
```

Startup order inside `create_app()`:

1. `setup_logging()` configures structlog (needs settings first).
2. The `FastAPI` app is created; in production (`environment == "production"`) the Swagger/ReDoc
   docs and the OpenAPI JSON are disabled.
3. Middleware is added in this order — because Starlette runs the **last added middleware first**,
   the effective execution order is the reverse:
   `AuditLogMiddleware` → `RateLimitMiddleware` (only if `rate_limit_enabled`) →
   `RequestContextMiddleware` → `SecurityHeadersMiddleware` → `CORSMiddleware` (outermost).
4. `register_exception_handlers(app)` installs the four error handlers.
5. The health router is mounted at the app **root** (`/health`), and the v1 router under
   `settings.api_v1_prefix` (`/api/v1`).
6. A lifespan context logs startup/shutdown and calls `dispose_engine()` on shutdown so the
   connection pool closes cleanly.

At the bottom of `main.py`, `app = create_app()` runs at import time so `uvicorn app.main:app`
works directly.

### Dependencies introduced

`fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `sqlalchemy`, `asyncpg`, `aiosqlite`
(dev/tests), `alembic`, `structlog`, `httpx` (tests), `pytest` family, `ruff`, `mypy`.

### How later phases depend on it

- Phase 1 registers ORM models on `Base` (from `database/base.py`) and writes Alembic migrations
  executed by the `alembic/env.py` scaffold.
- Phase 2 services receive the session produced by `get_db`; they raise `AppError` subclasses from
  `core/errors.py`.
- Phase 3 routers are mounted on `api_v1_router` created in Phase 0.
- Phase 7 hardening middleware (rate limit, cache, audit) plugs into the Phase 0 middleware stack.

### Files introduced in this phase

| File | Purpose | Why created | Who imports it | Execution order |
| ---- | ------- | ----------- | -------------- | --------------- |
| `backend/app/main.py` | App factory + module-level `app` | Single assembly point for the whole backend | uvicorn, tests, scripts | 1st at boot |
| `backend/app/core/config.py` | `Settings` + cached `get_settings()` | Central env-driven configuration | Almost everything | Before anything else |
| `backend/app/core/logging.py` | structlog setup | Uniform structured logs | `main.py` | At app creation |
| `backend/app/core/errors.py` | Error classes + handlers | One error envelope everywhere | Services, `main.py` | Registered at app creation; raised at request time |
| `backend/app/core/security.py` | Security seam (placeholder for future auth) | Reserved hook so later auth changes don't reshape the app | (reserved) | — |
| `backend/app/database/base.py` | `Base`, mixins, portable column types, naming convention | Models need UUID PKs, timestamps, soft delete; SQLite & PostgreSQL must share one metadata | All models, migrations | At import |
| `backend/app/database/session.py` | Engine, session factory, `get_db`, `check_database`, `dispose_engine` | Request-scoped DB access with pooling | `api/deps.py`, scripts, health | Lazily on first request |
| `backend/app/api/deps.py` | FastAPI dependencies (`get_db`) | Keep router signatures clean | All v1 routers | Per request |
| `backend/app/api/health.py` | `/health` endpoint | Liveness/readiness for Docker & LBs | `main.py` | On each health probe |
| `backend/app/schemas/health.py` | Health response schema | Typed health JSON | `api/health.py` | — |
| `backend/Dockerfile` | Two-stage production image | Containerized API | docker compose | Build time |
| `backend/docker-compose.yml` | postgres + api services, healthchecks | One-command full stack | Docker | Deploy time |
| `backend/.env.example` | Documented environment template | Safe starting point for `.env` | Developers | — |
| `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako` | Async Alembic scaffold | Versioned schema changes | `alembic` CLI | Migration time |
| `backend/pyproject.toml` | ruff/mypy/pytest config | Enforced code quality | Tooling | Dev time |
| `backend/requirements.txt` | Pinned dependencies | Reproducible installs | pip / Docker | Install time |

**Simple explanation:** Phase 0 is the foundation of a house. Nothing visible to the user yet,
but every later room (feature) stands on it.

---

## Phase 1 — Data Model & Migrations

### Why this phase exists

The frontend prototype carried all its data as JavaScript constants. To become real, that data
needs a durable home: a relational schema with constraints, relationships, and a seed dataset
that reproduces the prototype's numbers exactly so the UI keeps looking identical.

### What was added

- **16 model modules registering 28 domain tables** (30 physical tables once the two reference
  lookup tables `regions` and `vehicle_models` are counted), grouped by business domain.
- **14 PostgreSQL ENUM types** for statuses/categories, created via a helper `enum_column()` that
  uses `values_callable` so the DB stores the lowercase *values* of the Python enums.
- **Portable column types** so the same ORM metadata works on PostgreSQL and SQLite:
  `JSONType` (JSONB ↔ JSON), `string_array()` (TEXT[] ↔ JSON), `uuid_pk()` (native UUID ↔ generic Uuid).
  This is what allows the test suite and Docker-less development to run on SQLite.
- **Deterministic constraint names** (`NAMING_CONVENTION`) so Alembic autogenerate produces
  stable names like `ck_dealers_booking_prob_range`.
- **One hand-written migration** `alembic/versions/0001_initial_schema.py` (599 lines) creating
  every table, index, check constraint, FK, ENUM, plus a clean `downgrade()` that drops tables in
  reverse order and then the enum types.
- **Seed system**: `seed_data.py` (verbatim port of the frontend mock data, ~1,000 lines) and
  `seed.py` (the loader that upserts it with deterministic UUID5 primary keys).

### The 30 tables by domain

| Domain | Tables | Notes |
| ------ | ------ | ----- |
| Reference | `regions`, `vehicle_models` | Natural string primary keys (`code`, `name`), no UUID/audit mixins — pure lookup data feeding the simulator dropdowns |
| Identity | `users` | Minimal user table (future auth seam) |
| Overview | `kpis`, `kpi_drivers`, `recommendations` | KPI → drivers one-to-many; recommendations carry a partial index `ix_recommendations_status_pending` on pending rows |
| Catalogue | `solution_buckets`, `solutions` | Bucket → solutions one-to-many |
| Dealers | `dealers`, `dealer_leads` | Lead FK to dealer with `ON DELETE CASCADE`; CHECK constraints keep percentages 0–100 |
| Finance | `finance_products`, `customer_twins` | `customer_twins` stores NBA, risk decomposition and cross-sell as JSONB |
| Collections | `collections_agents`, `collections_cases` | Cases hold DPD, roll-forward risk, recommended action, `modified_action` |
| Logistics | `logistics_routes`, `warehouse_signals` | `warehouse_signals.panel` enum scopes one table to three UI panels (warehouse / collections metrics / RVSF tiles) |
| Circularity | `carbon_credits` | Reprice/buyer-match timestamps for audit |
| Trust | `trust_decisions`, `compliance_rules` | `trust_decisions.lineage` is a JSONB array of the six lineage steps |
| AI factory | `ai_agents`, `xr_experiences` | `ai_agents.use_areas` is a TEXT[] with a GIN index; `agent_status` enum is shared and created with `create_type=False` in the agents model |
| Mobility twin | `causal_nodes`, `causal_edges`, `mobility_kpis`, `causal_qa` | Nodes carry SVG x/y coordinates; edges have a unique (source, target) pair; `causal_qa.category` splits mobility vs dMRV Q&A (composite index on category+question) |
| PoC | `poc_items` | Unique name, soft-deletable |
| Copilot | `copilot_sessions`, `copilot_messages`, `suggested_prompts` | Messages FK to session with CASCADE; sessions are **not** seeded (they grow from real usage) |
| Simulation audit | `simulation_runs` | JSONB inputs/outputs — the audit trail hook for simulation runs |

### Relationships & constraints in plain English

- **Parent/child with CASCADE**: delete a dealer → its leads disappear; delete a copilot session →
  its messages disappear; delete a causal node → its edges disappear. This matches the demo
  behavior where children never outlive parents.
- **CHECK constraints** guard every percentage column (`BETWEEN 0 AND 100`) so bad data can never
  be stored even if application code has a bug.
- **UNIQUE constraints** protect natural keys: dealer codes, credit codes, trust decision codes,
  PoC item names, compliance rule labels, suggested prompt texts.
- **`sort_order` columns** preserve the curated display order of the prototype (the UI shows rows
  in a specific sequence, not alphabetical).
- **`deleted_at` (soft delete)** on user-facing rows (dealers, leads, credits, trust decisions,
  poc items, collections cases) so "delete" never destroys audit history; repositories filter
  soft-deleted rows automatically.

### Seed data — deterministic by design

`seed.py` generates every primary key with `uuid.uuid5(SEED_NAMESPACE, "table:identifier")`
through a tiny helper `uid(*parts)`. Because UUID5 is deterministic, **running the seeder twice
produces the exact same IDs**, which lets `session.merge()` upsert instead of duplicate. This is
what makes seeding idempotent — you can re-run it any time, on any environment, and get the same
database. `--reset` TRUNCATEs first when a clean slate is wanted.

The seeder also builds the six-step **trust lineage** JSON (`build_lineage`) reused by every
`trust_decisions` row, and returns a `SeedReport` with per-table row counts printed by the CLI.

### How later phases depend on it

Repositories query these models; services depend on enums; the whole test suite boots by seeding
this data into in-memory SQLite; the frontend types mirror the schemas that mirror these models.

### Files introduced in this phase

| File | Purpose | Why created | Who imports it |
| ---- | ------- | ----------- | -------------- |
| `app/models/__init__.py` | Imports/exports all 28 model classes | One import point registers every table on `Base.metadata` | Alembic env, tests, seeder |
| `app/models/enums.py` | 14 `StrEnum`s + `enum_column()` | Type-safe statuses shared by models, services, display maps | All model modules |
| `app/models/user.py` … `app/models/simulation.py` (14 more modules) | One module per domain | Domain separation — each page of the UI maps to one module | `models/__init__.py` |
| `alembic/versions/0001_initial_schema.py` | The full schema migration | Apply the schema to PostgreSQL with explicit control over ENUMs, indexes, constraints | Alembic CLI |
| `app/database/seed_data.py` | The dataset (verbatim port of frontend mocks) | UI parity: the live app must show the same numbers as the prototype | `seed.py`, `catalogue` service (tag chips) |
| `app/database/seed.py` | Idempotent loader (`seed_database`) | Repeatable provisioning for dev, Docker, tests | scripts, `tests/conftest.py` |
| `tests/database/test_metadata.py`, `tests/database/test_migration.py`, `tests/database/test_seed.py` | Schema/migration/seed tests | Prove the model metadata matches the migration (column counts, FKs, enums) and that seeding is idempotent | pytest |

**Simple explanation:** Phase 1 built the filing cabinet — labeled drawers (tables), rules about
what fits in each drawer (constraints), and a starter set of perfectly reproduced files (seed data).

---

## Phase 2 — Repositories & Services

### Why this phase exists

With tables in place, the code needs two cleanly separated jobs:

1. **Data access** — "give me all dealers sorted by order, ignoring soft-deleted rows."
2. **Business logic** — "approving a twin that is not in Draft state is a conflict; a duplicate
   PoC name is a 409."

Splitting these means SQL changes never ripple into business rules and vice versa, and it gives
tests a narrow seam to replace the database.

### Repository layer

- `repositories/base.py` defines `BaseRepository[ModelT]` using Python 3.12 generics
  (PEP 695 syntax: `class BaseRepository[ModelT: Base]`).
- Its `_base_query()` always applies the soft-delete filter (`deleted_at IS NULL`) when the model
  has `SoftDeleteMixin`, and orders by `sort_order` when present — so **no repository can
  accidentally return hidden rows or unsorted lists**.
- It provides `list_all()` and `get_by_id()`; each domain repository adds its own finders:
  e.g. `DealerRepository.list_leads(dealer_code)`, `TrustRepository.get_by_code(code)`,
  `MobilityRepository.list_qa(category=...)`, `CatalogueRepository.list_buckets(tag=...)`.
- Repositories receive the `AsyncSession` in their constructor; **they never commit**.

### Service layer

- `services/base.py` defines `BaseService` which simply holds the session.
- Each domain service composes one or more repositories, validates domain rules, mutates models,
  and calls `await self._session.commit()` **explicitly** — transactions are owned here.
- Services return **Pydantic schemas**, never ORM objects. While converting they apply display
  labels from `app/utils/display.py` so the JSON the frontend receives is render-ready
  (e.g. enum `UNDER_REVIEW` becomes the string `"Under Review"` exactly as the prototype showed).
- Domain errors raise typed exceptions: `NotFoundError("...'", code="twin_not_found")`,
  `ConflictError(..., code="duplicate_poc_item")`, `DomainValidationError` — the Phase 0 handlers
  turn them into the standard envelope.

### Representative service behaviors (from the actual code)

| Service | Notable logic |
| ------- | ------------- |
| `OverviewService` | Maps KPIs with their driver texts; `update_recommendation_status` parses the *display label* ("Approved" / "Under Review") back into the enum, rejects "Pending", stamps `decided_at`, commits |
| `DealerService` | Builds lead pitch text from `PITCH_TEMPLATE`; static `COACH_CONTENT`; lead actions (message / test-drive / convert) move the lead status and commit |
| `FinanceService` | Twin approval is a state machine Draft → Under Review; second submit raises `ConflictError`. `explain` / `rm-script` return curated bullets/script from `app/ai/prompts/*`; `simulate_offer` calls the AI scoring function `simulate_offer(amount)` → EMI + risk |
| `CollectionsService` | approve/modify/review set the case status enum; `get_case_ledger` returns the static six trust-trail steps (`CASE_LEDGER_STEPS`) — identical for every case, matching the prototype |
| `LogisticsService` | `reroute` sets `rerouted=True` + timestamp; `auto_heal` returns the five workflow steps (`AUTO_HEAL_STEPS`) alongside the updated route |
| `CircularityService` | dMRV ask uses the Q&A matcher (`match_answer`) over seeded questions with `DMRV_FALLBACK`; ELV estimate is a pure AI scoring call; reprice/match-buyer stamp timestamps and set `buyer_match=100` |
| `TrustService` | Rules are served through the read cache (`cached_read("trust:rules", ...)`); approve/reject/escalate set the `TrustApproval` enum; lineage comes straight from the JSONB column |
| `MobilityService` | Graph + KPIs are cached; edges are returned as label pairs by resolving node ids; `ask` uses the same Q&A matcher with `MOBILITY_FALLBACK` |
| `AiAgentService` | Agent/XR lists cached; `run_workflow()` returns the eight staged collaboration steps with a 700 ms replay interval for the frontend animation |
| `CatalogueService` | Bucket lists cached per tag; tag chips come from `seed_data.SOLUTION_TAGS` |
| `PocService` | Server-side dedupe (duplicate name → 409), `sort_order = len(items)`, `added_at` returned as epoch-millis (with a SQLite naive-datetime fix) |
| `SimulationService` | Meta (regions/models) from reference tables and cached; causal drivers validated against `SIMULATION_DOMAINS`; the five `run_*` methods delegate to the AI engine modules |
| `CopilotService` | Suggested prompts cached; `chat` calls `RuleBasedCopilot().respond(message)` |
| `ExecutiveSummaryService` | Session-free static method: pure template expansion from `app/ai/prompts/executive_summary.py` |

### How the layers interact

```mermaid
flowchart LR
    R[Router] -->|calls| S[Service]
    S -->|queries| Rp[Repository]
    Rp -->|SQL via AsyncSession| DB[(DB)]
    S -->|validates, mutates, commits| DB
    S -->|converts with display maps| Py[Pydantic Out schemas]
    Py -->|returned to| R
```

### Files introduced in this phase

| File | Purpose | Who imports it |
| ---- | ------- | -------------- |
| `app/repositories/base.py` | Generic base repository (soft-delete + ordering) | All 14 domain repositories |
| `app/repositories/{dealer,overview,catalogue,poc,finance,collections,logistics,circularity,trust,mobility,agent,copilot,reference}.py` + `__init__.py` | Domain finders | Corresponding services |
| `app/services/base.py` | `BaseService` (holds session) | All services |
| `app/services/*.py` (15 modules) + `__init__.py` | Business logic per domain | v1 routers |
| `app/utils/display.py` | Enum → display-label maps (single source of truth) | Services (outputs) and label parsing (inputs) |
| `tests/api/test_writes_*.py` (4 files) | Write-path tests | pytest |

**Simple explanation:** repositories are librarians (they only fetch and shelve), services are
clerks (they apply the rules and stamp the paperwork), and neither talks to the outside world
directly — routers do.

---

## Phase 3 — REST API v1

### Why this phase exists

The backend's capabilities are useless until they are exposed over HTTP with strict contracts.
Phase 3 defines the entire public surface: ~60 endpoints under `/api/v1`, each with a Pydantic
request/response schema, so the frontend can be rewired mechanically in Phase 5.

### Design decisions visible in the code

- **One router module per domain**, all mounted by `app/api/v1/router.py` with prefixes and OpenAPI
  tags. A comment in that file documents the rollout order (reads first, writes next, AI last).
- **Response models mirror the frontend TypeScript types 1:1** (same JSON keys). Where the
  prototype used camelCase keys (`recommendedAction`, `priceBandLow`, `sessionId`), the Pydantic
  models use `Field(alias=...)` + `populate_by_name=True` so the wire format stays camelCase while
  Python code keeps snake_case. This is why the frontend needed **zero** rendering changes.
- **Display labels over enums on the wire.** The frontend renders strings like "Under Review";
  services convert enums to those labels, and write endpoints parse labels back. The API therefore
  speaks the UI's language directly.
- **Proper HTTP semantics**: 201 for created PoC items, 204 for PoC deletion, 404 with error codes
  for unknown resources, 409 for conflicts, 422 for validation failures.
- **`Annotated[AsyncSession, Depends(get_db)]`** on every handler that needs a database; AI-only
  endpoints (ELV estimate, simulation runs, executive summary, workflow run) take no session at all.

### Router inventory (mounted by `app/api/v1/router.py`)

| Prefix | Module | Endpoints |
| ------ | ------ | --------- |
| `/overview` (+ v1 root) | `overview.py` | GET kpis, GET recommendations, PATCH `/recommendations/{rec_code}` |
| `/catalogue` | `catalogue.py` | GET buckets (optional `?tag=`), GET tags |
| `/poc` | `poc.py` | GET list, POST add, DELETE `?name=`, GET roadmap-plan |
| `/dealers`, `/dealer-leads` | `dealers.py` (two routers) | GET dealers, GET/…leads, GET coach, POST pitch; POST message/test-drive/convert on leads |
| `/finance` | `finance.py` | GET products, GET twins, GET customers/{id}/twin; POST submit-approval, explain, rm-script, simulate-offer |
| `/collections` | `collections.py` | GET metrics/agents/cases; POST approve/modify/review; GET ledger |
| `/logistics` | `logistics.py` | GET routes, warehouse-signals; POST predict-delay, reroute, auto-heal |
| `/circularity` | `circularity.py` | GET credits, rvsf-metrics, dmrv/prompts; POST dmrv/ask, elv/estimate, credits reprice, match-buyer |
| `/trust` | `trust.py` | GET decisions, compliance-rules, decisions/{code}/lineage; POST approve, reject, escalate |
| `/agents`, `/xr` | `agents.py` (two routers) | GET agents, GET agents/{id}, POST workflow/run; GET xr/experiences |
| `/mobility-twin` | `mobility.py` | GET graph, GET kpis, POST ask |
| `/simulations` | `simulations.py` | GET meta, GET causal-drivers; POST {domain}/run ×5 |
| `/copilot` | `copilot.py` | GET suggested-prompts, POST chat |
| (v1 root) | `executive_summary.py` | POST /executive-summary |

### Validation & request/response flow

1. **Inbound**: FastAPI parses path/query/body into typed parameters; Pydantic schemas enforce
   bounds (`Field(ge=0, le=100)`, `max_length`, `Literal` choices, `min_length=1` on chat
   messages). Invalid input → 422 with the standard envelope (via the `RequestValidationError`
   handler).
2. **Business**: the service applies domain rules (e.g. "approval already submitted").
3. **Outbound**: `response_model` serializes the Pydantic output; `response_model_exclude_none`
   (used by copilot chat) drops absent optional fields so the JSON matches the prototype shape.

### Files introduced in this phase

| File | Purpose |
| ---- | ------- |
| `app/api/v1/router.py` | Mounts all 14 domain routers with prefixes/tags |
| `app/api/v1/{overview,catalogue,poc,dealers,finance,collections,logistics,circularity,trust,agents,mobility,simulations,copilot,executive_summary}.py` | Thin HTTP layer per domain |
| `app/schemas/*.py` (16 modules) | API contracts (input bounds, aliases, output shapes) |
| `tests/api/test_overview.py`, `test_catalogue.py`, `test_dealers.py`, `test_finance.py`, `test_collections.py`, `test_logistics.py`, `test_circularity.py`, `test_trust.py`, `test_mobility.py`, `test_agents_xr.py` | Read/write endpoint tests |

**Simple explanation:** Phase 3 is the reception desk — it takes orders (requests), checks them
for correctness, hands them to the clerks (services), and returns neatly packaged answers.

---

## Phase 4 — AI Layer

### Why this phase exists

The prototype's "AI" was a collection of formulas and canned answers in TypeScript. To move it to
the backend **without changing any output**, the project built a dedicated `app/ai/` package of
deterministic, dependency-free engines — and wrapped each behind a Protocol seam so a real LLM can
be swapped in later without touching services or routers.

### Architecture

```mermaid
flowchart TB
    subgraph Services
        CS[CopilotService] --> CE[CopilotEngine protocol]
        FS[FinanceService] --> EM[scoring.emi]
        CIR[CircularityService] --> ELV[scoring.elv_valuation]
        CIR --> QA[causal.qa.match_answer]
        MS[MobilityService] --> QA
        SS[SimulationService] --> SE[simulation engines ×5]
        ES[ExecutiveSummaryService] --> PT[prompts.executive_summary]
    end
    CE --> RB[RuleBasedCopilot]
    RB --> IR[copilot.intents INTENT_RULES]
    RB --> FB[prompts.copilot_fallback]
    LR[llm.registry get_llm_provider] -.fallback.-> RBP[RuleBasedProvider]
```

### What each part does

- **Copilot** (`ai/copilot/`): `engine.py` defines the `CopilotEngine` Protocol (a contract:
  anything with `respond(message) -> dict` qualifies) and `RuleBasedCopilot`, which walks
  `INTENT_RULES` — an ordered list of (keyword tuple → answer payload) pairs — and returns the
  **first** intent whose keywords all appear in the question (case-insensitive). No match →
  `COPILOT_FALLBACK`. This is an exact port of the old frontend `copilot.ts`, including 7 intents
  (bookings leakage, collections, SLA delays, credits, warranty, etc.) with answer, explanation,
  SQL, Python, optional chart/table, action and confidence.
- **LLM seam** (`ai/llm/`): `provider.py` defines the `LlmProvider` Protocol; `registry.py`
  returns the configured provider (`AI_PROVIDER=openai|rule`) and **logs a warning + falls back**
  to `RuleBasedProvider` when the requested one is unavailable. This is the future-proofing seam:
  a real LLM can be dropped in without changing any caller.
- **Simulation engines** (`ai/simulation/`): five pure-function modules, each exposing
  `run(payload) -> Out` following the contract documented in `base.py`:
  - `auto_sales.py` — uplift/margin/cancellation/revenue/confidence with region & intensity
    multipliers, plus the recommended action text.
  - `dealer_allocation.py` — delay, revenue, CSAT and a suggested regional split.
  - `collections_sim.py` — recovery probability by risk, cost by channel, friction, net value.
  - `logistics_delay.py` — weighted delay probability, SLA breach risk, reroute suggestion, cost.
  - `credit_pricing.py` — price band, closure probability, buyer match, compliance risk tier.
- **Causal helpers** (`ai/causal/`): `drivers.py` holds `CAUSAL_DRIVERS` (the shared explanation
  bullets) and `SIMULATION_DOMAINS`; `qa.py` implements `match_answer()` — case-insensitive exact
  question matching against seeded Q&A pairs with a per-domain fallback, plus `MOBILITY_FALLBACK`.
- **Scoring** (`ai/scoring/`): `elv_valuation.py`
  (`price = 80000 − age×3800 + condition×350 + docs×120`, plus recoverable value and risk notes)
  and `emi.py` (`emi = amount/36 + amount×0.006`, risk tier from amount) — the finance twin's
  offer simulator.
- **Prompts** (`ai/prompts/`): curated text blocks used as deterministic "generation":
  `copilot_fallback.py`, `dmrv.py`, `executive_summary.py` (the 9-field template builder),
  `finance_explain.py`, `rm_script.py`.
- **Parity utilities** (`ai/utils.py`): `js_round(value)` = `math.floor(value + 0.5)` reproduces
  JavaScript's `Math.round`, and `format_inr()` reproduces Indian digit grouping (`1,23,456`).
  These two tiny functions are what guarantee the backend's numbers match the prototype to the
  last digit.

### RAG / embeddings status

No vector store, embeddings, or retrieval pipeline is implemented. Q&A is exact-match lookup over
seeded pairs. The design intentionally keeps the seam (`LlmProvider`, `CopilotEngine` protocols)
ready for RAG later — the **Summary** section lists this as a future improvement.

### Files introduced in this phase

| File | Purpose |
| ---- | ------- |
| `app/ai/copilot/{engine,intents}.py` | Copilot contract + rule engine + 7 intents |
| `app/ai/llm/{provider,registry}.py` | LLM provider contract + selection with fallback |
| `app/ai/simulation/{base,auto_sales,dealer_allocation,collections_sim,logistics_delay,credit_pricing}.py` | Five deterministic engines |
| `app/ai/causal/{drivers,qa}.py` | Shared driver bullets; Q&A matcher |
| `app/ai/scoring/{elv_valuation,emi}.py` | Valuation + EMI math |
| `app/ai/prompts/*.py` (5 files) | Curated answer templates |
| `app/ai/utils.py` | JS rounding / INR formatting parity |
| `tests/api/test_ai_copilot_summary.py`, `test_ai_simulations.py`, `test_ai_domains.py`, `test_meta_copilot.py` | AI parity tests |

**Simple explanation:** Phase 4 rebuilt the prototype's "brain" in Python, neuron-for-neuron, so
answers stay identical — and left sockets where a real LLM can be plugged in later.

---

## Phase 5 — Frontend Wiring

### Why this phase exists

The frontend had to switch from local mock data to the live API **without any visible change** and
without breaking the Lovable-connected build (SSR via Nitro). Phase 5 is strictly additive: new
files were added; existing UI components were edited only to swap data sources.

### What was added

- **`lib/api/client.ts`** — the JSON client:
  - `apiBaseUrl` from `VITE_API_BASE_URL`, defaulting to `http://localhost:8000/api/v1`.
  - `isSsr` (`typeof window === "undefined"`) and `apiEnabled = !isSsr` — queries **never run
    during server rendering**, so the Nitro SSR server needs no backend access.
  - `ApiError` class carrying `status` + backend `code`; `apiFetch<T>()` sets JSON headers,
    stringifies bodies, parses the error envelope, and returns `undefined` for 204 responses.
- **`lib/api/endpoints.ts`** — ~60 typed one-liner functions, one per backend endpoint
  (`fetchKpis`, `approveCase`, `runAutoSalesSim`, `chatCopilot`, …), with a small `q()` helper to
  build query strings from possibly-undefined params.
- **`lib/api/types.ts`** — TypeScript types mirroring every Pydantic schema 1:1.
- **`hooks/use-api.ts`** — the query/mutation layer:
  - `apiQueryOptions(key, fn, enabled?)` wraps `queryOptions` with `enabled: apiEnabled && enabled`,
    `staleTime: Infinity` (data is demo-stable; refetch only on invalidation), `retry: false`.
  - List hooks end with `?? []` so components can map immediately without crashing while loading.
  - "View" types (e.g. `RecommendationView`, `RouteView`) make server-generated fields like `id`
    optional so optimistic UI works before the API responds.
  - `useFireMutation(fn, invalidateKeys?)` — the standard fire-and-invalidate mutation used by all
    action buttons.
  - `usePocMutations()` adds **optimistic updates with rollback** for the PoC shortlist.
  - POST-generated content (explain, RM script, simulate-offer, lead pitch) is exposed as *queries
    gated by an `enabled` flag* — triggered by dialog opens rather than imperative calls, which
    keeps them cacheable and deduplicated.
- **Route re-wiring** — each of the 13 route files swapped `import { mockData } from ...` for the
  corresponding hooks; optimistic local state (e.g. recommendation status) is layered on top and
  reconciled by cache invalidation.
- **`lib/app-context.tsx`** became API-backed: the PoC list now comes from `usePocQuery()` and
  mutations go through `usePocMutations()` (no localStorage, no local copies).

### How later phases depend on it

Phase 6 could only delete the mock files because Phase 5 made every consumer API-backed first.

### Files introduced in this phase

| File | Purpose |
| ---- | ------- |
| `frontend/src/lib/api/client.ts` | Base URL, SSR guard, `ApiError`, `apiFetch` |
| `frontend/src/lib/api/endpoints.ts` | All typed endpoint functions |
| `frontend/src/lib/api/types.ts` | Response type contracts |
| `frontend/src/hooks/use-api.ts` | All queries/mutations (541 lines) |
| edits to `frontend/src/routes/*.tsx` (13 pages) | Hook-based data sources |
| edits to `frontend/src/lib/app-context.tsx` | API-backed PoC state |

**Simple explanation:** Phase 5 replaced the extension cord (mock files) with a real power line
(HTTP API) without anyone in the building noticing the lights flicker.

---

## Phase 6 — Mock Removal & Cutover

### Why this phase exists

Until mocks are physically gone, someone could accidentally import them and silently bypass the
backend. Phase 6 deletes them, verifies zero remaining references, and runs an end-to-end
verification against the live stack.

### What happened

1. Confirmed **zero importers** remained for `mock-data.ts` and `copilot.ts` (searched the whole
   frontend tree).
2. **Deleted** `frontend/src/lib/mock-data.ts` and `frontend/src/lib/copilot.ts`.
3. Cleaned the last dead branches in `app-context.tsx` (local PoC fallbacks, localStorage reads).
4. **Fixed a real cutover bug** found during the walkthrough: `routes/dealer.tsx` used
   `dealers.find((d) => d.id === activeId)!` — a non-null assertion that crashed during the brief
   window when the dealer list is still empty while loading. Replaced with a guard
   (`if (!dealer) return null;`) after all hook calls.
5. **Verification**: ESLint clean (0 errors), `tsc` clean, production build clean (client + SSR +
   Nitro), and a 13-route browser walkthrough against the live backend — every page rendered live
   API data; copilot chat verified end-to-end (POST `/copilot/chat` → 200 → full AI card rendered).

### Files changed in this phase

| File | Change |
| ---- | ------ |
| `frontend/src/lib/mock-data.ts` | Deleted |
| `frontend/src/lib/copilot.ts` | Deleted |
| `frontend/src/lib/app-context.tsx` | Removed dead mock/localStorage branches |
| `frontend/src/routes/dealer.tsx` | Non-null assertion crash fix |

**Simple explanation:** the training wheels came off, and the bike was ridden around the block to
prove it stays up.

---

## Phase 7 — Documentation & Hardening

### Why this phase exists

A demo backend becomes a production backend through cross-cutting protections and observability:
abuse control, caching, auditing, secure defaults, and docs.

### What was added

- **`middleware/rate_limit.py`** — fixed-window rate limiter using a TTL cache keyed by
  `(client_ip, bucket)`. Two budgets per 60 s window: `rate_limit_requests` (default 300) for
  normal traffic and a stricter `rate_limit_ai_requests` (default 30) for AI endpoints detected via
  `AI_PATH_MARKERS`. Returns 429 with `Retry-After`. Fully toggleable via `RATE_LIMIT_ENABLED`
  (tests run with it off — `tests/conftest.py` sets the env var *before* importing the app).
- **`middleware/audit_log.py`** — after every **successful** mutation (POST/PATCH/PUT/DELETE),
  emits a structured `audit_event` log with method, path, status, and request id.
- **`middleware/request_context.py`** — generates/propagates `X-Request-ID`, binds it into
  structlog's contextvars so every log line for that request carries the same id, and echoes the
  id in the response header (this is the `request_id` you see in every error envelope).
- **`middleware/security_headers.py`** — `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Cache-Control: no-store`, and HSTS when `environment == "production"`.
- **`core/cache.py`** — an in-process TTL read cache: `cached_read[T](key, loader)` (PEP 695
  generic) with `read_cache_ttl_seconds` (default 300 s) and `clear_read_cache()`. Services use it
  for stable reads (trust rules, mobility graph/KPIs, agent/XR lists, catalogue buckets,
  copilot prompts, simulation meta).
- **Input hardening** — every inbound schema has explicit bounds (`max_length`, `ge/le`,
  `Literal`), so oversized or malformed payloads are rejected at the edge with 422.
- **Docs** — `backend/README.md` (stack, architecture, quick start, test commands), and this
  document.

### Testing suite (final state: 132 passing tests)

| Area | Files | What they prove |
| ---- | ----- | --------------- |
| Health/config/cache | `test_health.py`, `core/test_config.py`, `core/test_cache.py` | Health envelope, settings loading, TTL cache behavior |
| Schema integrity | `database/test_metadata.py`, `test_migration.py` | ORM metadata ↔ migration parity, 28 tables, FKs, enums |
| Seeding | `database/test_seed.py` | Deterministic IDs, idempotent re-runs, row counts |
| Domain reads/writes | `api/test_*.py` (14 files) | Every endpoint's happy path + 404/409/422 cases |
| AI parity | `test_ai_simulations.py`, `test_ai_copilot_summary.py`, `test_ai_domains.py` | Backend outputs match the prototype's exact numbers/text |
| Hardening | `api/test_hardening.py` | Rate limit 429, security headers, request-id propagation |

Test infrastructure: `tests/conftest.py` boots an in-memory SQLite engine with `StaticPool`
(single shared connection), overrides `get_db`, seeds fresh data per test, clears the read cache,
and drives the app through `httpx` `ASGITransport` — real HTTP semantics, no sockets.

### Operational scripts

| Script | Purpose |
| ------ | ------- |
| `scripts/seed_db.py` | CLI seeder for the configured DB (`--reset` to TRUNCATE first) |
| `scripts/dev_sqlite_seed.py` | Creates + seeds a local SQLite `dev.db` (the Docker-less dev path) |
| `scripts/smoke_writes.py` | Exercises mutation endpoints against a running server |
| `scripts/smoke_ai.py` | Exercises copilot/simulation endpoints and prints answers |
| `scripts/load_test.py` | Simple concurrent load probe for the rate limiter & cache |

### Files introduced in this phase

| File | Purpose |
| ---- | ------- |
| `app/middleware/{rate_limit,audit_log,request_context,security_headers}.py` | Hardening middleware |
| `app/core/cache.py` | TTL read cache |
| `tests/api/test_hardening.py` | Hardening tests |
| `backend/scripts/*.py` (5 files) | Ops tooling |
| `backend/README.md` | Backend documentation |

**Simple explanation:** Phase 7 added the alarm system, the cameras, and the instruction manual.

---

# File-by-File Explanation

This section walks through every meaningful project file. (Generated artifacts like
`routeTree.gen.ts`, lockfiles, and `__pycache__` are noted but not expanded.) Each entry covers
purpose, main functions, when it runs, and how it connects to the rest.

## Backend — application core

### `backend/app/main.py` (97 lines)
- **Purpose:** the app factory — assembles the entire FastAPI application.
- **Main functions:** `create_app()` builds and returns the configured app; a lifespan context
  manager logs "started" on boot and calls `dispose_engine()` on shutdown; the module ends with
  `app = create_app()` so ASGI servers can import it.
- **Logic:** configure logging → instantiate FastAPI (docs disabled when
  `environment == "production"`) → add middleware (audit, rate-limit if enabled, request-context,
  security headers, CORS) → register exception handlers → include `/health` at root and the v1
  router under `/api/v1`.
- **Imports:** config, logging, errors, middleware, health router, v1 router, session disposal.
- **Imported by:** uvicorn, every test, smoke scripts.

### `backend/app/core/config.py` (103 lines)
- **Purpose:** single source of configuration.
- **Main class:** `Settings(BaseSettings)` — reads environment variables and `.env` automatically.
  Fields include: `app_name`, `app_version`, `environment` (`development|staging|production`),
  `database_url` (default `postgresql+asyncpg://mahindra:mahindra@localhost:5432/mahindra_ai`),
  pool sizing (`db_pool_size`, `db_max_overflow`), `cors_origins` (comma-separated string),
  `api_v1_prefix` (`/api/v1`), `ai_provider` (`rule|openai`), `openai_api_key`, `log_level`, and
  hardening knobs (`rate_limit_enabled`, `rate_limit_requests=300`, `rate_limit_ai_requests=30`,
  `rate_limit_window_seconds=60`, `read_cache_ttl_seconds=300`).
- **Helpers:** `cors_origin_list` property splits the comma string; `json_logs` property is true
  in production; `@lru_cache get_settings()` makes the settings a singleton.
- **Why written this way:** one typed object means no scattered `os.environ` reads, and tests can
  override any value through environment variables.

### `backend/app/core/logging.py` (82 lines)
- **Purpose:** structured logging for the whole process.
- **Logic:** `setup_logging()` configures structlog with contextvars (so request ids attach
  automatically), pretty console rendering in development and JSON rendering in production, and
  bridges Python's standard `logging` into structlog so library logs (uvicorn, sqlalchemy) share
  the format and level.

### `backend/app/core/errors.py` (146 lines)
- **Purpose:** the error vocabulary and the handlers that serialize it.
- **Classes:** `AppError` (base: `status_code`, `default_code`, `detail`) with subclasses
  `BadRequestError` (400), `NotFoundError` (404), `ConflictError` (409),
  `DomainValidationError` (422), `ExternalServiceError` (502).
- **Functions:** four handlers registered on the app — one for `AppError`, one for FastAPI's
  `RequestValidationError`, one for Starlette HTTP exceptions, and a catch-all for unexpected
  `Exception` (logged with the traceback, returned as 500 without leaking internals). All produce
  the same `_envelope`: `{"detail", "code", "request_id"}`. Also defines `json_dumps`, the JSON
  serializer used for JSONB columns.

### `backend/app/core/security.py` (38 lines)
- **Purpose:** reserved seam for authentication/authorization. Currently minimal — it exists so
  adding auth later is an additive change.

### `backend/app/core/cache.py` (43 lines)
- **Purpose:** tiny in-process TTL cache for stable reads.
- **Main function:** `cached_read[T](key, loader)` — returns the cached value if fresh (under
  `read_cache_ttl_seconds`), otherwise awaits `loader()`, stores and returns it.
  `clear_read_cache()` empties it (used by tests and after seeding).
- **Why:** the demo dataset is stable; caching avoids re-querying identical reference data on
  every page load while keeping behavior simple (single process, no Redis needed).

## Backend — database layer

### `backend/app/database/base.py` (93 lines)
- **Purpose:** the shared foundation for every ORM model.
- **Pieces:** `NAMING_CONVENTION` (deterministic constraint names); `Base` (declarative base
  carrying that metadata); `UUIDPrimaryKeyMixin` (UUID v4 PK named `id`); `TimestampMixin`
  (`created_at`/`updated_at` with server defaults); `SoftDeleteMixin` (`deleted_at` +
  `is_deleted` property); portable type helpers `JSONType` (JSONB on PostgreSQL, JSON on SQLite),
  `string_array()` (TEXT[] vs JSON) and `uuid_pk()` (native UUID vs generic Uuid).
- **Why:** this file is what makes one codebase run on PostgreSQL in production and SQLite in
  tests/local dev without branching anywhere else.

### `backend/app/database/session.py` (87 lines)
- **Purpose:** engine + session lifecycle.
- **Main functions:** `get_engine()` (`@lru_cache`; pool size from settings, `pool_pre_ping=True`
  so dead connections are recycled; falls back to SQLite settings when the URL is sqlite) →
  `get_session_factory()` (`expire_on_commit=False` so models stay usable after commit) →
  `get_db()` async generator used as a FastAPI dependency: yields a session, rolls back on
  exception, always closes. `check_database()` runs `SELECT 1` for the health check.
  `dispose_engine()` closes the pool at shutdown.
- **Important rule:** `get_db` never commits — commits belong to services.

### `backend/app/database/seed_data.py` (1,058 lines)
- **Purpose:** the dataset. See the **Synthetic Data** section for the full story — it is a
  verbatim, structured port of the frontend mock files with per-domain Python constants
  (KPIs, recommendations, buckets/solutions, dealers/leads, finance products/twins, collections,
  logistics signals/routes, credits, trust decisions + rules, agents, XR, mobility graph/KPIs/QA,
  copilot prompts, regions, vehicle models, solution tags).

### `backend/app/database/seed.py` (544 lines)
- **Purpose:** loads `seed_data` into the database idempotently.
- **Main functions:** `uid(*parts)` → deterministic UUID5 from `SEED_NAMESPACE`; `build_lineage()`
  → the six-step trust lineage JSON; `reset_database()` → TRUNCATE … CASCADE of all seeded
  tables; `seed_database(session, reset=False)` → merges (upserts) every table in dependency
  order (reference tables first, then domains, children after parents) and returns a `SeedReport`
  of per-table counts. Copilot sessions/messages are deliberately not seeded.

### `backend/alembic/env.py` (84 lines)
- **Purpose:** async Alembic environment. Injects `settings.database_url` over `alembic.ini`,
  imports `app.models` so `Base.metadata` is complete, and runs migrations through an async
  engine (`run_async` with `run_sync` bridge).

### `backend/alembic/versions/0001_initial_schema.py` (599 lines)
- **Purpose:** the complete schema in one hand-written migration.
- **Logic:** `upgrade()` creates 14 ENUM types first, then 30 tables grouped by domain with
  explicit check constraints, unique constraints, FKs with `ON DELETE CASCADE`, indexes (including
  a GIN index on `ai_agents.use_areas` and a partial index on pending recommendations); an
  `_audit_columns()` helper supplies `created_at`/`updated_at` to every table.
  `downgrade()` drops tables in reverse order and then the enum types.

## Backend — middleware

| File | What it does, in plain English |
| ---- | ------------------------------ |
| `middleware/request_context.py` | Reads an incoming `X-Request-ID` or generates a UUID; binds it to structlog context so all logs for the request carry it; echoes it back in the response header. Runs for every request. |
| `middleware/security_headers.py` | Adds defensive headers to every response; adds HSTS only in production. |
| `middleware/rate_limit.py` | Counts requests per `(client_ip, bucket)` in a fixed window using a TTL cache. AI paths (detected by `AI_PATH_MARKERS` like `/copilot/`, `/simulations/`) get the smaller budget. Over budget → 429 JSON + `Retry-After`. Skipped entirely when disabled. |
| `middleware/audit_log.py` | After the response is produced, if the method was a mutation and the status < 400, logs an `audit_event` with method/path/status/request-id. Failed writes are not audited (they changed nothing). |

Execution order per request (outermost → innermost): CORS → SecurityHeaders → RequestContext →
RateLimit → AuditLog → router.

## Backend — API layer

- `api/deps.py` — re-exports `get_db` (and a future current-user seam). Every router imports it.
- `api/health.py` — `GET /health`: returns status, app name/version, environment, and a
  `database` field from `check_database()` (`ok`/`error`); HTTP 200 when the DB is reachable,
  503 when it is not.
- `api/v1/router.py` — creates `api_v1_router` and `include_router`s the 14 domain routers with
  prefixes + tags; also mounts the PATCH `/recommendations/{rec_code}` handler at the v1 root
  namespace through the overview module.
- `api/v1/*.py` (14 modules) — each is a thin translation layer: declare route + response model,
  inject `get_db` where needed, construct the matching service, call one method, return its
  result. None contain business logic; several AI-only handlers skip the DB entirely
  (simulations run, ELV estimate, workflow run, executive summary).
- `schemas/*.py` (16 modules) — Pydantic v2 contracts: input schemas carry bounds
  (`Field(ge=…, le=…, max_length=…)`, `Literal`, `min_length`); output schemas carry aliases for
  camelCase wire keys; `common.py` holds shared pieces. These are the only objects routers accept
  or return.

## Backend — models (one module per domain)

All models mix in `UUIDPrimaryKeyMixin` + `TimestampMixin` (plus `SoftDeleteMixin` where rows are
user-deletable) unless noted. Every file's class maps 1:1 to the tables listed in Phase 1.

| File | Classes | Notable details |
| ---- | ------- | --------------- |
| `models/enums.py` | 14 `StrEnum`s + `enum_column()` | Values are lowercase DB values; labels live in `utils/display.py` |
| `models/user.py` | `User` | Minimal identity seam |
| `models/reference.py` | `Region`, `VehicleModel` | Natural string PKs, no mixins — pure lookups |
| `models/overview.py` | `Kpi`, `KpiDriver`, `Recommendation` | KPI→drivers relationship; partial index on pending recommendations |
| `models/catalogue.py` | `SolutionBucket`, `Solution` | Bucket→solutions relationship |
| `models/dealer.py` | `Dealer`, `DealerLead` | CASCADE FK; CHECK constraints on percentages |
| `models/finance.py` | `FinanceProduct`, `CustomerTwin` | Twin stores `nba`, `risk_decomposition`, `cross_sell`, `products` as JSONB/string-array |
| `models/collections.py` | `CollectionsAgent`, `CollectionsCase` | Case carries DPD, roll-forward risk, channel, action, modified_action |
| `models/logistics.py` | `LogisticsRoute`, `WarehouseSignal` | `panel` enum scopes signals to three UI panels |
| `models/circularity.py` | `CarbonCredit` | repriced_at / buyer_matched_at audit stamps |
| `models/trust.py` | `TrustDecision`, `ComplianceRule` | `lineage` JSONB list of step dicts |
| `models/agents.py` | `AiAgent`, `XrExperience` | Shared `agent_status` enum with `create_type=False`; `use_areas` string array |
| `models/mobility.py` | `CausalNode`, `CausalEdge`, `MobilityKpi`, `CausalQa` | SVG coords on nodes; unique edge pair; QA category enum |
| `models/poc.py` | `PocItem` | Unique name, soft-delete |
| `models/copilot.py` | `CopilotSession`, `CopilotMessage`, `SuggestedPrompt` | Messages CASCADE with sessions; result JSONB |
| `models/simulation.py` | `SimulationRun` | JSONB inputs/outputs audit trail (write path reserved for future persistence) |

## Backend — repositories & services

Repositories (14 modules + base): each holds an `AsyncSession`, subclasses or mimics
`BaseRepository` behavior (soft-delete filter + `sort_order`), and exposes domain finders
(`get_by_code`, `list_leads`, `list_qa(category)`, `list_buckets(tag)`, …). They execute SQL and
return ORM objects only.

Services (15 modules + base): covered in detail in Phase 2 above. Key cross-cutting patterns:
constructor builds repositories; reads convert models → Pydantic `*Out` with display labels;
writes fetch → validate state → mutate → `commit()` → return the updated `*Out`; missing rows
raise `NotFoundError` with a stable machine code.

## Backend — AI package

Covered in depth in the **AI Layer** section; file list: `ai/copilot/{engine,intents}.py`,
`ai/llm/{provider,registry}.py`, `ai/simulation/{base,auto_sales,dealer_allocation,
collections_sim,logistics_delay,credit_pricing}.py`, `ai/causal/{drivers,qa}.py`,
`ai/scoring/{elv_valuation,emi}.py`, `ai/prompts/{copilot_fallback,dmrv,executive_summary,
finance_explain,rm_script}.py`, `ai/utils.py`.

## Backend — utils & scripts

- `utils/display.py` — the enum→display-label dictionaries (`DEALER_LEAD_STATUS_DISPLAY`,
  `RECOMMENDATION_STATUS_DISPLAY`, `TWIN_APPROVAL_DISPLAY`, `COLLECTIONS_*`, `TRUST_*`,
  `AGENT_STATUS_DISPLAY`). Single source of truth so API strings match the prototype exactly.
- `scripts/seed_db.py` — CLI: opens a session from the configured factory, runs
  `seed_database(session, reset=…)`, prints the report, disposes the engine. Assumes migrations
  are applied.
- `scripts/dev_sqlite_seed.py` — CLI: creates `dev.db` with `Base.metadata.create_all` and seeds
  it — the no-Docker development path (used because Docker was not running on this machine).
- `scripts/smoke_ai.py`, `scripts/smoke_writes.py`, `scripts/load_test.py` — live-server probes
  for AI endpoints, write endpoints, and rate limiting respectively.

## Backend — tests

- `tests/conftest.py` — the test harness: sets `RATE_LIMIT_ENABLED=false` **before** importing
  the app; builds an in-memory SQLite engine with `StaticPool`; fixtures: `db_session` (clears
  read cache, seeds fresh), `client` (httpx `AsyncClient` with `ASGITransport` + `get_db`
  override). All tests share this seam.
- `tests/database/*` — metadata/migration parity (table count, FKs, enums, constraints) and seed
  idempotency/determinism.
- `tests/api/*` — per-domain happy paths plus error cases (404 unknown codes, 409 duplicate PoC,
  409 twin re-approval, 422 invalid recommendation status), AI parity assertions against exact
  prototype outputs, and hardening behavior (429s, headers, request id).
- `tests/core/*` — settings loading and cache TTL semantics.

## Frontend — entry points & infrastructure

### `frontend/src/start.ts`
- **Purpose:** TanStack Start bootstrap. Creates the start instance with one server middleware:
  an error middleware that catches SSR failures and returns the branded HTML error page
  (`renderErrorPage()`), while re-throwing errors that already carry a `statusCode`.

### `frontend/src/server.ts`
- **Purpose:** the Nitro/Cloudflare worker entry. Wraps TanStack's server entry: lazily imports
  it, forwards every request, and normalizes "catastrophic" 500s — h3 sometimes swallows thrown
  errors into a JSON `{"unhandled":true,"message":"HTTPError"}` body, so this file detects that
  shape and swaps in the HTML error page (logging the captured error).

### `frontend/src/router.tsx`
- **Purpose:** builds the router: creates a `QueryClient`, passes it into the router context
  (so the root route can provide it), enables scroll restoration, and wires the generated
  `routeTree`.

### `frontend/src/routeTree.gen.ts` (generated)
- Auto-generated by the TanStack router plugin from the `routes/` folder. Not hand-edited.

### `frontend/src/routes/__root.tsx`
- **Purpose:** the shell around every page.
- **Logic:** `head()` emits meta tags + stylesheet; `RootShell` renders `<html>/<head>/<body>`
  with `HeadContent` and `Scripts`; `RootComponent` wraps the app in `QueryClientProvider` →
  `AppProvider`, then lays out `Sidebar` + `TopBar` + `<Outlet/>` + `CopilotPanel` +
  `DemoOverlay` + `Toaster`. Custom `notFoundComponent` (branded 404) and `errorComponent`
  (retry/home, reports to Lovable).

### `frontend/src/lib/app-context.tsx`
- **Purpose:** global UI state via React context.
- **State:** PoC list (from `usePocQuery()` + `usePocMutations()`), copilot open/messages,
  executive mode toggle, scenario selector, demo-step controls (0–7 walkthrough).
- **Why context:** these values are needed across unrelated components (top bar, catalogue,
  copilot panel, demo overlay) without prop-drilling.

### API layer
- `lib/api/client.ts` — base URL (`VITE_API_BASE_URL` → default `http://localhost:8000/api/v1`),
  SSR guard, `ApiError`, and `apiFetch<T>` (JSON headers, body stringify, envelope parsing,
  204 → `undefined`).
- `lib/api/endpoints.ts` — one typed function per endpoint (~60); the `q()` helper drops
  undefined query params.
- `lib/api/types.ts` — 1:1 mirrors of backend response schemas (camelCase where the backend
  aliases it so).

### `frontend/src/hooks/use-api.ts` (541 lines)
- **Purpose:** every TanStack Query/Mutation in one place, grouped by domain.
- **Key helpers:** `apiQueryOptions` (client-only, `staleTime: Infinity`, `retry: false`),
  `useFireMutation` (on success: invalidate given keys, toast via callers), view types with
  optional `id`/`status` for optimistic UI, `useAskAnswer` (Q&A with bundled fallback on
  failure), `usePocMutations` (optimistic add/remove with rollback).
- Hooks that depend on another query chain safely, e.g. `useCustomerTwin()` fetches the twin
  index first and only fetches the full profile once an id exists.

### Error/robustness helpers
- `lib/error-capture.ts` — installs global capture so SSR errors can be consumed by `server.ts`.
- `lib/error-page.ts` — `renderErrorPage()` branded HTML string for 500s.
- `lib/lovable-error-reporting.ts` — best-effort error reporting hook for the Lovable platform
  (no-op when unavailable).
- `lib/utils.ts` — the standard `cn()` class-name combiner (clsx + tailwind-merge).
- `hooks/use-mobile.tsx` — viewport hook used by responsive pieces.

## Frontend — layout components

| File | Role |
| ---- | ---- |
| `components/layout/sidebar.tsx` | Fixed left nav; the `NAV` array lists all 13 routes with lucide icons; active state comes from `useRouterState`. |
| `components/layout/top-bar.tsx` | Search box, scenario `Select` (Baseline FY26 / Aggressive Growth / Cost Optimization / ESG-First), Executive mode `Switch`, Start Demo button, and the Ask AI Copilot button that opens the panel. |
| `components/layout/copilot-panel.tsx` | Slide-in chat: suggested prompts from `useSuggestedPrompts()`, sends via `chatCopilot()`, pushes user/AI messages into app context, shows typing dots, renders the last full result (confidence, explanation, mini bar chart, SQL, recommended action), and shows a graceful "unreachable" message on network failure. |
| `components/layout/demo-overlay.tsx` | Guided 8-step demo story overlay driven by `demoStep` from app context. |
| `components/executive-summary.tsx` | Dialog rendering the 9-field executive summary from `useExecutiveSummary(useCase, open)`. |
| `components/poc-roadmap.tsx` | PoC shortlist panel: adds/removes items through app context (which calls the API), and shows the generated roadmap dialog (`useRoadmapPlan`). |

## Frontend — the 13 route pages

Every page follows the same recipe: declare a file route with `createFileRoute`, fetch with
domain hooks, render panels/cards/tables, wire action buttons to mutations, and show toasts on
success/failure. Per-page specifics:

| Route | What it shows | Data hooks | Notable interactions |
| ----- | ------------- | ---------- | -------------------- |
| `index.tsx` (Executive Overview) | KPI cards with confidence + sparklines, recommendations table | `useKpis`, `useRecommendations` | Explain dialog per KPI; Approve / Under Review per recommendation (`useUpdateRecommendation`); simulate-execution dialog |
| `catalogue.tsx` | Solution buckets filtered by tag chips | `useBuckets(tag)`, `useCatalogueTags` | Tag filtering refetches with query param; "Add to PoC" buttons feed `poc-roadmap` |
| `simulation.tsx` | 5 simulators with sliders/selects | `useSimulationMeta`, `useCausalDrivers`, `useAutoSalesSim` (+ 4 others) | Results recomputed live as queries keyed by the full input object; Explain Drivers modal; executive summary dialog |
| `mobility-twin.tsx` | SVG causal graph + business KPIs + Ask box | `useMobilityGraph`, `useMobilityKpis` | Ask via `useAskAnswer(askMobilityTwin)` with bundled fallback |
| `dealer.tsx` | Dealer selector → leads table, coach panel | `useDealers`, `useDealerLeads(code)`, `useDealerCoach` | Message / test-drive / convert mutations; pitch dialog via `useLeadPitch` (enabled on open); loading guard for empty list |
| `finance.tsx` | Product portfolio + customer twin panel | `useFinanceProducts`, `useCustomerTwin` | Submit approval (state machine), explain/RM-script/simulate-offer dialogs gated by `enabled` flags |
| `collections.tsx` | Metric tiles, swarm agents, case table | `useCollectionsMetrics`, `useCollectionsAgents`, `useCollectionsCases` | Approve / modify / review per case; trust-trail ledger dialog (`useCaseLedger`) |
| `logistics.tsx` | Route corridor cards + warehouse signals | `useLogisticsRoutes`, `useWarehouseSignals` | Predict delay, reroute, auto-heal (shows the 5-step workflow modal) |
| `circularity.tsx` | Credit marketplace + RVSF tiles + dMRV copilot + ELV estimator | `useCredits`, `useRvsfMetrics`, `useDmrvPrompts`, `useElvEstimate` | Reprice / match-buyer mutations; dMRV ask with fallback; ELV sliders drive a live query |
| `trust.tsx` | Audited decision rows + compliance rules | `useTrustDecisions`, `useComplianceRules` | Approve/reject (with reason)/escalate; lineage dialog fetches the 6 steps |
| `agents.tsx` | Agent registry + staged workflow animation | `useAgents`, `useWorkflowRun` | Run Workflow replays 8 stages at 700 ms intervals from the API response |
| `xr.tsx` | XR experience cards | `useXrExperiences` | Read-only showcase |
| `copilot.tsx` | Full-page copilot experience | `useSuggestedPrompts` + `chatCopilot` | Same chat engine as the panel, full-width analysis view |

## Frontend — UI kit

`components/ui/` contains ~45 shadcn/ui primitives (accordion, alert, dialog, dropdown, table,
tabs, sonner toaster, slider, select, panel helpers…). They are unmodified shadcn components
built on Radix + Tailwind; `panel.tsx` adds project-specific pieces (`Panel`, `SectionTitle`,
`StatPill`, `Sparkline`, `MiniBar`) used across pages. `styles.css` holds the Tailwind 4 theme,
the Mahindra red gradient, and glass effects.

## Config files (frontend)

- `package.json` — scripts (`dev`, `build`, `lint`, `format`), React 19 + TanStack + Radix +
  Tailwind 4 + zod dependencies, bun as the runner.
- `vite.config.ts` — uses `@lovable.dev/vite-tanstack-config` (bundles TanStack Start, React,
  Tailwind, tsconfig paths, Nitro with cloudflare preset); only override: redirect the server
  entry to `src/server.ts`.
- `bunfig.toml`, `bun.lock` — bun package-manager config + lockfile.
- `tsconfig.json` — strict TS, `@/*` path alias.
- `eslint.config.js`, `.prettierrc`, `.prettierignore` — lint/format rules (Prettier enforced
  through ESLint).
- `components.json` — shadcn/ui generator config.
- `AGENTS.md` (frontend) — Lovable connection notice (no force-push / history rewrites).

---

# Backend Working

## How FastAPI starts

1. `uvicorn app.main:app` imports `app/main.py`; the module-level `app = create_app()` runs.
2. `create_app()` → `setup_logging()` → build `FastAPI(...)` → add middleware (in reverse
   execution order) → `register_exception_handlers(app)` → mount routers → return.
3. Uvicorn starts the ASGI lifespan: the startup branch logs "application started"; nothing is
   pre-connected — the engine is created lazily on the first DB access (`get_engine` is cached).
4. On shutdown, the lifespan disposes the engine so pooled connections close cleanly.

## Dependency injection

The only DI is FastAPI's `Depends(get_db)`: each request gets a fresh `AsyncSession` from the
shared session factory. Routers pass that session into service constructors; services construct
their repositories with it. There is no service registry — services are cheap, stateless objects
created per request, which keeps everything request-scoped and thread/task-safe.

## Transactions

- Reads: no commit needed; the session closes when the request ends.
- Writes: the service mutates ORM objects and calls `await self._session.commit()` once, at the
  end of the operation. If anything raises, `get_db` rolls the session back — so a failed write
  never partially persists.
- `expire_on_commit=False` means returned objects are still readable after commit (services build
  Pydantic outputs from them immediately).

## Validation, exceptions, logging

- **Validation:** Pydantic at the edge (schemas) + domain checks in services + CHECK constraints
  in the database — three concentric fences.
- **Exception handling:** services raise typed `AppError`s; handlers convert everything
  (including unexpected crashes) into `{"detail", "code", "request_id"}` JSON with the right
  HTTP status. Internal details are logged, never leaked.
- **Logging:** structlog; every line for a request carries the same `request_id`; successful
  mutations additionally emit an `audit_event`.

## Complete request lifecycle (backend side)

```mermaid
sequenceDiagram
    participant C as Client
    participant CORS as CORS
    participant SH as SecurityHeaders
    participant RC as RequestContext
    participant RL as RateLimit
    participant AL as AuditLog
    participant R as Router
    participant S as Service
    participant DB as Database

    C->>CORS: HTTP request
    CORS->>SH: origin allowed
    SH->>RC: add security headers on the way out
    RC->>RL: bind request_id to logs
    RL->>AL: budget ok? (else 429)
    AL->>R: proceed
    R->>S: validate input, call service method
    S->>DB: repository queries / commit
    DB-->>S: rows
    S-->>R: Pydantic model
    R-->>C: 200 JSON (audit_event logged if mutation)
```

---

# Database

## Architecture & why PostgreSQL

PostgreSQL 16 was chosen because the schema needs features SQLite lacks in production: native
UUID columns, JSONB with GIN indexing, TEXT arrays, real ENUM types, partial indexes, and
TRUNCATE … CASCADE. The code still runs on SQLite (dev/tests) thanks to the portable type
helpers in `database/base.py` — a deliberate test seam, not an accident.

## Connection & session

- Engine: `create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=…, max_overflow=…)`.
- Session factory: `async_sessionmaker(engine, expire_on_commit=False)`.
- Per-request session via `get_db()` (yield → rollback-on-error → close-in-finally).
- Health: `check_database()` executes `SELECT 1`.

## ORM, Alembic & migrations

Models define the schema in Python; Alembic applies the equivalent SQL. The single migration
`0001_initial_schema.py` was hand-written (rather than autogenerated) to control ENUM creation
order and constraint names. `tests/database/test_metadata.py` enforces that ORM metadata and the
migration stay in sync (same tables, columns, FKs).

## Table reference (purpose · key columns · relationships · usage)

| Table | Purpose | Key columns | Relationships | Used by |
| ----- | ------- | ----------- | ------------- | ------- |
| `regions` | Simulator region options | `code` (PK) | — | `/simulations/meta` |
| `vehicle_models` | Simulator model options | `name` (PK) | — | `/simulations/meta` |
| `users` | Future identity | id, email, role | — | reserved |
| `kpis` | Overview KPI cards | code, label, value, trend, trend_up, confidence | has many `kpi_drivers` | `/overview/kpis` |
| `kpi_drivers` | Why a KPI moved | kpi_id FK, driver_text | belongs to `kpis` | `/overview/kpis` |
| `recommendations` | Action recommendations | code, title, impact, confidence, risk ENUM, status ENUM, decided_at | — | `/overview/recommendations`, PATCH |
| `solution_buckets` | Catalogue categories | name, tag | has many `solutions` | `/catalogue/buckets` |
| `solutions` | Catalogue entries | bucket FK, name, problem, solution, differentiator, impact | belongs to buckets | `/catalogue/buckets` |
| `dealers` | Dealer cards | code, name, leads, hot_leads, test_drives_pending, booking_prob, revenue_at_risk, leakage, bay_util | has many `dealer_leads` | `/dealers` |
| `dealer_leads` | Leads per dealer | dealer FK CASCADE, name, vehicle, score, prob, action, revenue, status ENUM | belongs to dealers | `/dealers/{code}/leads`, lead actions |
| `finance_products` | Product portfolio | name, customers, risk, cross_sell, opportunity | — | `/finance/products` |
| `customer_twins` | Customer digital twins | name, location, income_stability, repayment, products[], nba JSONB, risk_decomposition JSONB, cross_sell JSONB, approval_status ENUM | — | `/finance/twins/*` |
| `collections_agents` | Swarm roster | name, status ENUM | — | `/collections/agents` |
| `collections_cases` | Prioritized cases | customer, dpd, outstanding, roll_forward_risk, channel, action, prob, compliance_flag ENUM, status ENUM, modified_action | — | `/collections/cases/*` |
| `logistics_routes` | Freight corridors | name, sla_risk, delay_prob, cost, recommended_action, rerouted, rerouted_at, auto_healed | — | `/logistics/routes/*` |
| `warehouse_signals` | Shared metric tiles | panel ENUM, label, value, tone | — | logistics/collections/circularity tiles |
| `carbon_credits` | Credit marketplace | code, type, price, buyer_match, closure_prob, traceability, repriced_at, buyer_matched_at | — | `/circularity/credits/*` |
| `trust_decisions` | Audited AI decisions | code, use_case, recommendation, data_sources, confidence, approval/risk/audit ENUMs, rejection_reason, lineage JSONB | — | `/trust/*` |
| `compliance_rules` | Rule checks | label, status | — | `/trust/compliance-rules` |
| `ai_agents` | Agent registry | name, role, status ENUM, last_activity, use_areas TEXT[] | — | `/agents` |
| `xr_experiences` | XR cards | code, title, use_case, feature, impact | — | `/xr/experiences` |
| `causal_nodes` | Graph nodes | label, x, y, metric, trend, drivers JSONB, action | has many edges | `/mobility-twin/graph` |
| `causal_edges` | Graph links | source/target FKs CASCADE, unique pair | belongs to nodes | `/mobility-twin/graph` |
| `mobility_kpis` | Mobility KPIs | label, value, trend | — | `/mobility-twin/kpis` |
| `causal_qa` | Q&A bank | category ENUM (mobility/dmrv), question, answer | — | mobility ask, dMRV ask/prompts |
| `poc_items` | PoC shortlist | name UNIQUE, bucket, sort_order, deleted_at | — | `/poc` |
| `copilot_sessions` | Chat threads | title | has many messages | reserved (chat is stateless today) |
| `copilot_messages` | Chat history | session FK CASCADE, role ENUM, content, result JSONB, confidence | belongs to sessions | reserved |
| `suggested_prompts` | Copilot prompt chips | text UNIQUE, sort_order | — | `/copilot/suggested-prompts` |
| `simulation_runs` | Simulation audit | domain ENUM, inputs JSONB, outputs JSONB, confidence | — | reserved audit trail |

Indexes worth knowing: GIN on `ai_agents.use_areas`, partial index on pending recommendations,
composite `(category, question)` on `causal_qa`, `deleted_at` indexes on soft-deleted tables.

---

# Synthetic Data

## Why synthetic data exists

The product is a demo/decision-support platform; there is no live Mahindra production feed to
connect to. The prototype's hardcoded numbers **are** the business story the stakeholders signed
off on. So the backend must serve exactly those numbers — from a real database — to keep the
experience identical and testable. Synthetic data is therefore not "fake filler": it is the
curated demo dataset, ported 1:1.

## Which files generate it & the pipeline

```mermaid
flowchart LR
    A[frontend mocks<br/>historical] -->|verbatim port| B[seed_data.py<br/>constants]
    B --> C[seed.py<br/>uid\(\) UUID5 IDs + merge]
    C -->|PostgreSQL| D1[(prod/dev DB)]
    C -->|SQLite| D2[(dev.db / tests)]
```

1. `seed_data.py` holds the dataset as plain Python constants — no randomness at runtime.
2. `seed.py` converts each constant into ORM rows with deterministic UUID5 IDs
   (`uuid5(SEED_NAMESPACE, "<table>:<key>")`), then `session.merge()` upserts them.
3. `scripts/seed_db.py` runs this against the configured database; `scripts/dev_sqlite_seed.py`
   does the same for a local SQLite file; `tests/conftest.py` does it per-test on in-memory
   SQLite.

## Randomization logic

There is none — deliberately. Determinism is the point: identical IDs across environments make
seeding idempotent, let tests assert exact values, and keep cross-table references stable
(e.g. trust lineage references, causal edges between named nodes). Where the UI needs
"random-looking" decoration (sparklines), the frontend generates it locally.

## Libraries used

Only the standard library (`uuid`, `datetime`) plus SQLAlchemy for insertion. No Faker, no
random generators.

## How the frontend consumes it

Exactly like any API data — it cannot tell the difference. Parity is enforced by backend tests
that compare endpoint JSON against the prototype's original values.

## The seed dataset, domain by domain (all inside `seed_data.py`)

| Block | Mirrors (historical frontend source) | Feeds |
| ----- | ------------------------------------ | ----- |
| Regions + vehicle models | simulation selects | `/simulations/meta` |
| KPIs + drivers + recommendations | overview mock | Executive Overview |
| Solution buckets + solutions + tags | catalogue mock | Catalogue |
| Dealers + leads | dealer mock | Dealer Optimizer |
| Finance products + customer twins (NBA, risk, cross-sell) | finance mock | Financial Services |
| Collections agents + cases + metric tiles | collections mock | Collections Swarm |
| Logistics routes + warehouse signals (3 panels) | logistics mock | Logistics / tiles |
| Carbon credits | circularity mock | Circular Economy |
| Trust decisions + compliance rules | trust mock | Trust Ledger |
| AI agents + XR experiences | agents/xr mock | AI Factory |
| Causal nodes/edges, mobility KPIs, mobility + dMRV Q&A | mobility-twin mock | Mobility Twin / dMRV |
| Suggested copilot prompts | copilot UI | Copilot chips |

**Unused/reserved pieces:** `copilot_sessions`/`copilot_messages` (schema exists, no writes yet),
`simulation_runs` (audit table, write path reserved), `users` (auth seam), `core/security.py`
(auth seam). These are intentional forward-looking structures, not dead code.

---

# AI Layer

## Architecture in one paragraph

The AI layer is a set of **deterministic, dependency-free engines** organized under `app/ai/`.
Each engine is either a pure function (`run(payload)`, `estimate_elv(...)`, `simulate_offer(...)`,
`generate_executive_summary(...)`) or a tiny class behind a Protocol (`CopilotEngine`,
`LlmProvider`). Services call them synchronously — no model loading, no network, no cache needed,
because results are exact math or exact lookups and complete in microseconds. This was a
deliberate choice: the demo must be reproducible, testable offline, and bit-identical to the
prototype; the Protocol seams keep the door open for real LLMs/RAG later.

## Components

- **Copilot** — keyword-intent matching: lowercased question → walk ordered `INTENT_RULES` →
  first rule whose keywords all appear wins → return its payload (answer, explanation, sql,
  python, optional chart/table, action, confidence) → else `COPILOT_FALLBACK` (confidence 70).
- **Recommendation logic** — recommendations are curated rows; approving/routing them updates
  status + `decided_at` and is Trust-ledger friendly. The "intelligence" shown to the user
  (impact, confidence, risk) is stored data, while the copilot explains it.
- **Simulation logic** — five engines, each an exact port of a frontend formula set; inputs
  validated by Pydantic (bounds match slider ranges); outputs mirror frontend key names via
  aliases. `js_round` guarantees JS `Math.round` parity.
- **Q&A (mobility + dMRV)** — `match_answer()` compares the question case-insensitively against
  seeded questions; exact match returns the seeded answer; anything else returns the domain
  fallback text.
- **Scoring** — ELV valuation (`80000 − age×3800 + condition×350 + docs×120`, with recoverable
  value and risk notes) and EMI (`amount/36 + amount×0.006` with risk tiers).
- **LLM integration** — `get_llm_provider()` selects by `AI_PROVIDER`; the rule provider is the
  default and the automatic fallback (with a logged warning). No API key is required to run.
- **RAG/embeddings** — not implemented; listed as future work.

## Inference flow (copilot chat)

```mermaid
sequenceDiagram
    participant FE as CopilotPanel
    participant API as POST /copilot/chat
    participant SVC as CopilotService
    participant ENG as RuleBasedCopilot

    FE->>API: { message }
    API->>SVC: chat(payload)  [1–2000 chars enforced]
    SVC->>ENG: respond(message)
    ENG-->>SVC: intent payload or fallback
    SVC-->>API: CopilotResultOut (exclude_none)
    API-->>FE: answer + explanation + sql + confidence…
```

## Caching & model loading

No model loading exists. The only caching is the generic TTL read cache for DB reads — AI
responses themselves are not cached because they are already O(microseconds) and caching would
only add staleness risk.

---

# API Documentation

All endpoints live under `http://localhost:8000/api/v1` (except `/health` at the root). Every
response is JSON; every error uses the `{"detail", "code", "request_id"}` envelope. In the tables
below: **Validation** = what Pydantic/service checks; **DB** = database effect; **AI** = engine
involved.

## Health

| Method/Route | Purpose | Behavior |
| ------------ | ------- | -------- |
| GET `/health` | Liveness + DB probe | Runs `SELECT 1`; 200 when reachable, 503 otherwise. No auth, no validation. |

## Overview

| Method/Route | Purpose | Validation | DB | Response |
| ------------ | ------- | ---------- | -- | -------- |
| GET `/overview/kpis` | KPI cards | — | SELECT kpis + drivers | `Kpi[]` with drivers |
| GET `/overview/recommendations` | Recommendation rows | — | SELECT recommendations | `Recommendation[]` |
| PATCH `/recommendations/{rec_code}` | Approve / route to review | status must be "Approved" or "Under Review" (422 otherwise) | UPDATE status + decided_at, COMMIT | updated `Recommendation` |

## Catalogue & PoC

| Method/Route | Purpose | Validation | DB | Response |
| ------------ | ------- | ---------- | -- | -------- |
| GET `/catalogue/buckets?tag=` | Buckets with solutions, optional tag filter | tag string | SELECT (cached per tag) | `Bucket[]` |
| GET `/catalogue/tags` | Filter chips | — | none (static superset) | `string[]` |
| GET `/poc` | Shortlist | — | SELECT poc_items | `PocItem[]` |
| POST `/poc` | Add item | name/bucket length; duplicate → 409 | INSERT, COMMIT | 201 `PocItem` |
| DELETE `/poc?name=` | Remove item | name required; missing → 404 | DELETE, COMMIT | 204 empty |
| GET `/poc/roadmap-plan` | Phased rollout plan | — | none (static) | phases + topPocs + optional |

## Dealers

| Method/Route | Purpose | DB | Notes |
| ------------ | ------- | -- | ----- |
| GET `/dealers` | Dealer cards | SELECT | sorted `sort_order` |
| GET `/dealers/{code}/leads` | Leads for dealer | SELECT by FK; 404 unknown code | |
| GET `/dealers/{code}/coach` | Coaching guidance | SELECT dealer | static coach content |
| POST `/dealers/{code}/leads/{lead_id}/pitch` | Generate pitch text | SELECT lead | template expansion (PITCH_TEMPLATE) |
| POST `/dealer-leads/{id}/message` | Message a lead | UPDATE status, COMMIT | |
| POST `/dealer-leads/{id}/test-drive` | Book slot | body `{slot}`, UPDATE | |
| POST `/dealer-leads/{id}/convert` | Convert lead | UPDATE status | |

## Finance

| Method/Route | Purpose | AI | DB |
| ------------ | ------- | -- | -- |
| GET `/finance/products` | Portfolio cards | — | SELECT |
| GET `/finance/twins` | Twin index (id+name) | — | SELECT |
| GET `/finance/customers/{twin_id}/twin` | Full twin | — | SELECT; 404 unknown |
| POST `/finance/twins/{id}/submit-approval` | Draft → Under Review | — | UPDATE; 409 if not Draft |
| POST `/finance/twins/{id}/explain` | NBA bullets | curated prompt text | existence check |
| POST `/finance/twins/{id}/rm-script` | RM pitch | curated template | existence check |
| POST `/finance/twins/{id}/simulate-offer` | EMI for amount | `scoring.emi.simulate_offer` | existence check; amount bounded |

## Collections

| Method/Route | Purpose | DB |
| ------------ | ------- | -- |
| GET `/collections/metrics` | Metric tiles (panel=collections_metrics) | SELECT |
| GET `/collections/agents` | Swarm roster | SELECT |
| GET `/collections/cases` | Case rows | SELECT |
| POST `/collections/cases/{id}/approve` | Approve action | UPDATE status=approved |
| POST `/collections/cases/{id}/modify` | Replace action | body `{action}`; sets modified_action |
| POST `/collections/cases/{id}/review` | Human review | UPDATE status |
| GET `/collections/cases/{id}/ledger` | Trust-trail steps | existence check; static 6 steps |

## Logistics

| Method/Route | Purpose | DB |
| ------------ | ------- | -- |
| GET `/logistics/routes` | Corridor cards | SELECT |
| GET `/logistics/warehouse-signals` | Warehouse tiles (panel=warehouse) | SELECT |
| POST `/logistics/routes/{id}/predict-delay` | Re-score (echoes latest) | SELECT |
| POST `/logistics/routes/{id}/reroute` | Apply reroute | UPDATE rerouted + timestamp |
| POST `/logistics/routes/{id}/auto-heal` | 5-step heal | UPDATE auto_healed; returns steps |

## Circularity

| Method/Route | Purpose | AI | DB |
| ------------ | ------- | -- | -- |
| GET `/circularity/credits` | Marketplace rows | — | SELECT |
| GET `/circularity/rvsf-metrics` | RVSF tiles (panel=rvsf) | — | SELECT |
| GET `/circularity/dmrv/prompts` | Suggested questions | — | SELECT causal_qa (dmrv) |
| POST `/circularity/dmrv/ask` | Ask dMRV copilot | `match_answer` + fallback | SELECT qa |
| POST `/circularity/elv/estimate` | ELV valuation | `scoring.elv_valuation` | none |
| POST `/circularity/credits/{code}/reprice` | Reprice credit | — | UPDATE repriced_at |
| POST `/circularity/credits/{code}/match-buyer` | Match buyer | — | UPDATE buyer_match=100 |

## Trust ledger

| Method/Route | Purpose | DB |
| ------------ | ------- | -- |
| GET `/trust/decisions` | Decision rows | SELECT |
| GET `/trust/compliance-rules` | Rule checks | SELECT (cached) |
| GET `/trust/decisions/{code}/lineage` | 6-step lineage | SELECT; JSONB column |
| POST `/trust/decisions/{code}/approve` | Approve | UPDATE approval |
| POST `/trust/decisions/{code}/reject` | Reject | body `{reason}`; stores reason |
| POST `/trust/decisions/{code}/escalate` | Escalate | UPDATE approval |

## Agents & XR

| Method/Route | Purpose | DB |
| ------------ | ------- | -- |
| GET `/agents` | Registry | SELECT (cached) |
| GET `/agents/{id}` | One agent | SELECT; 404 unknown |
| POST `/agents/workflow/run` | 8-stage flow | none (static; frontend replays at 700 ms) |
| GET `/xr/experiences` | XR cards | SELECT (cached) |

## Mobility twin

| Method/Route | Purpose | AI | DB |
| ------------ | ------- | -- | -- |
| GET `/mobility-twin/graph` | Nodes + label-pair edges | — | SELECT (cached) |
| GET `/mobility-twin/kpis` | Business KPIs | — | SELECT (cached) |
| POST `/mobility-twin/ask` | Ask causal twin | `match_answer` + fallback | SELECT qa |

## Simulations

| Method/Route | Purpose | AI engine | Input bounds |
| ------------ | ------- | --------- | ------------ |
| GET `/simulations/meta` | Regions + models | — | cached reference SELECT |
| GET `/simulations/causal-drivers?domain=` | Driver bullets | domain must be known (404) | none |
| POST `/simulations/auto-sales/run` | Sales simulator | `auto_sales.run` | discount 0–10, bonus 0–75k, campaign 0–5, intensity Low/Medium/High |
| POST `/simulations/dealer-allocation/run` | Allocation simulator | `dealer_allocation.run` | units 20–400, demand 20–100, capacity 30–100, wait 5–45 |
| POST `/simulations/collections/run` | Collections simulator | `collections_sim.run` | risk/channel/offer Literals, field 0–100 |
| POST `/simulations/logistics-delay/run` | Delay simulator | `logistics_delay.run` | warehouse/vehicle/weather 0–100, sla Literal |
| POST `/simulations/credit-pricing/run` | Credit pricing | `credit_pricing.run` | supply/demand/trace/verif 10–100, `type` alias |

Simulation runs are pure functions — no DB writes today; `simulation_runs` exists as the reserved
audit table.

## Copilot & executive summary

| Method/Route | Purpose | Validation | AI |
| ------------ | ------- | ---------- | -- |
| GET `/copilot/suggested-prompts` | Prompt chips | — | cached SELECT |
| POST `/copilot/chat` | Chat | message 1–2000 chars; optional `sessionId` UUID | `RuleBasedCopilot.respond` |
| POST `/executive-summary` | 9-field summary | `useCase` 1–128 chars | template expansion |

---

# Configuration Files

| File | Role | Key contents |
| ---- | ---- | ------------ |
| `backend/.env.example` | Env template (copy to `.env`) | `DATABASE_URL`, `ENVIRONMENT`, `CORS_ORIGINS`, `AI_PROVIDER`, `OPENAI_API_KEY`, `LOG_LEVEL`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, rate-limit + cache toggles |
| `backend/requirements.txt` | Python dependencies | fastapi, uvicorn, sqlalchemy, asyncpg, aiosqlite, alembic, pydantic(-settings), structlog, httpx, pytest family, ruff, mypy |
| `backend/pyproject.toml` | Tooling config | ruff (E/W/F/I/B/UP/S/C4/SIM, line-length 120), mypy strict-ish, pytest `asyncio_mode=auto` |
| `backend/alembic.ini` | Alembic defaults | script location; URL overridden by `env.py` from settings |
| `backend/Dockerfile` | API image | 2-stage python:3.12-slim, non-root user, `/health` healthcheck, uvicorn CMD |
| `backend/docker-compose.yml` | Full stack | `postgres:16-alpine` (pg_isready healthcheck, persistent volume) + `api` built from Dockerfile with `DATABASE_URL` pointing at the service host |
| `frontend/package.json` | Frontend deps/scripts | React 19, TanStack Start/Router/Query, Radix, Tailwind 4, zod; `dev`/`build`/`lint` |
| `frontend/vite.config.ts` | Build config | Lovable TanStack preset; server entry override → `src/server.ts` |
| `frontend/bunfig.toml` | Bun config | package runner settings |
| `frontend/tsconfig.json` | TS config | strict mode, `@/*` alias |
| `frontend/eslint.config.js` + `.prettierrc` | Code style | ESLint 9 flat config + prettier plugin |
| `frontend/components.json` | shadcn config | component generation paths/style |
| Root `AGENTS.md` | Agent guidance | Lovable connection: never rewrite pushed history |

Environment variables that actually change behavior: `DATABASE_URL` (Postgres vs SQLite),
`ENVIRONMENT` (docs off, HSTS on, JSON logs), `CORS_ORIGINS`, `AI_PROVIDER`,
`RATE_LIMIT_ENABLED` + budget knobs, `READ_CACHE_TTL_SECONDS`, `LOG_LEVEL`, and on the frontend
`VITE_API_BASE_URL`.

---

# End-to-End Workflow

One complete user flow: **a user approves an audited AI decision on the Trust Ledger page.**

```mermaid
sequenceDiagram
    participant U as User
    participant P as trust.tsx page
    participant H as useApproveDecision (mutation)
    participant E as endpoints.approveDecision
    participant C as apiFetch
    participant FW as FastAPI middleware
    participant R as api/v1/trust.py
    participant S as TrustService
    participant Rp as TrustRepository
    participant DB as PostgreSQL

    U->>P: clicks "Approve" on row TD-01
    P->>H: mutate("TD-01")
    H->>E: approveDecision("TD-01")
    E->>C: apiFetch("/trust/decisions/TD-01/approve", {method:"POST"})
    C->>FW: POST http://localhost:8000/api/v1/trust/decisions/TD-01/approve
    FW->>FW: CORS → headers → request-id → rate-limit → audit
    FW->>R: route handler
    R->>S: TrustService(db).approve_decision("TD-01")
    S->>Rp: get_by_code("TD-01")
    Rp->>DB: SELECT … WHERE code='TD-01' AND deleted_at IS NULL
    DB-->>Rp: row
    Rp-->>S: TrustDecision
    S->>S: decision.approval = TrustApproval.APPROVED
    S->>DB: COMMIT
    S-->>R: TrustDecisionOut (labels applied)
    R-->>C: 200 JSON
    C-->>H: parsed object
    H->>H: onSuccess → invalidate ["trust","decisions"] + toast
    H->>E: GET /trust/decisions (refetch)
    E-->>P: fresh list
    P-->>U: row now shows "Approved"
```

In words: the click triggers a TanStack mutation, which calls the typed endpoint function, which
uses `apiFetch` to POST against the backend. The middleware stack processes the request, the
router delegates to the service, the service loads the row through the repository, changes one
enum field, commits, and returns a labeled Pydantic model. The mutation hook invalidates the
list's cache key, TanStack Query refetches, and React re-renders the row. The audit middleware
also logs the successful mutation, and the whole exchange is correlated by one `X-Request-ID`.

---

# Dependency Graph

```mermaid
flowchart TB
    subgraph Frontend
        Routes[routes/*.tsx] --> Hooks[hooks/use-api.ts]
        Hooks --> EP[lib/api/endpoints.ts]
        EP --> CL[lib/api/client.ts]
        Layout[layout components] --> Hooks
        Layout --> Ctx[lib/app-context.tsx]
        Ctx --> Hooks
    end

    subgraph Backend
        Main[main.py] --> Core[core/*]
        Main --> MW[middleware/*]
        Main --> HR[api/health.py]
        Main --> V1R[api/v1/router.py]
        V1R --> RTR[v1 routers]
        RTR --> Schemas[schemas/*]
        RTR --> Svc[services/*]
        Svc --> Repos[repositories/*]
        Svc --> AI[ai/*]
        Svc --> Disp[utils/display.py]
        Repos --> Models[models/*]
        Models --> Base[database/base.py]
        Svc --> Sess[database/session.py]
        Seed[database/seed.py] --> SD[database/seed_data.py]
        Seed --> Models
    end

    CL -->|HTTP| V1R
```

Who depends on whom, condensed:

| Depends on… | Depended by |
| ----------- | ----------- |
| `core/config.py` | everything (logging, session, middleware, alembic env) |
| `core/errors.py` | all services; registered by `main.py` |
| `database/base.py` | all models; migration tests |
| `database/session.py` | `api/deps.py`, scripts, health |
| `models/*` | repositories, seed, Alembic env |
| `repositories/*` | services only |
| `services/*` | v1 routers only |
| `ai/*` | services only (never routers) |
| `utils/display.py` | services |
| `lib/api/client.ts` | `endpoints.ts` only |
| `endpoints.ts` | `use-api.ts` + copilot panel |
| `use-api.ts` | every route + app-context |

No cycles exist: arrows point strictly downward (UI → HTTP → router → service → repository →
model) and the AI package only points back up through return values.

---

# Business Logic — Why the Code Is Written This Way

1. **Layering (router → service → repository)** exists so each concern changes independently:
   swapping the database affects only repositories; changing HTTP shapes affects only routers +
   schemas; business rules live in exactly one place per domain.
2. **Services own commits** because a use case is the right unit of atomicity — a lead
   conversion is one transaction, not "one UPDATE per object".
3. **Display labels on the wire** (instead of enum names) keep the UI byte-identical to the
   approved prototype without any frontend translation layer.
4. **Deterministic UUID5 seeding** trades "random-looking IDs" for idempotent, testable,
   cross-environment-stable data — essential when 132 tests and a demo both assert exact values.
5. **Rule-based AI with Protocol seams** gives demo-grade reliability today (no API keys, no
   latency, no nondeterminism) while leaving a documented upgrade path to real LLMs.
6. **`js_round` / INR formatting parity** may look odd in Python, but the requirement was
   bit-identical output with JavaScript; this is the cheapest correct way to guarantee it.
7. **`staleTime: Infinity` + explicit invalidation** matches the product: data changes only
   through this app's own mutations, so refetch-on-mount would be wasted traffic.
8. **Client-only queries (`apiEnabled = !isSsr`)** keep the SSR server stateless and
   backend-free — the Nitro server renders the shell, the browser fetches the data.
9. **One error envelope everywhere** means the frontend needs exactly one error-handling code
   path (`ApiError`) regardless of what failed.
10. **Soft delete + audit timestamps** reflect the compliance theme of the product itself:
    decisions and entities are never silently destroyed.

---

# Common Execution Flow

| Scenario | What happens |
| -------- | ------------ |
| **Application startup** | uvicorn imports `app.main` → `create_app()` → logging → middleware → handlers → routers; lifespan logs startup; DB connects lazily on first query |
| **Database initialization (Postgres)** | `docker compose up -d postgres` → `alembic upgrade head` (0001 migration) → `python scripts/seed_db.py` |
| **Database initialization (no Docker)** | `python scripts/dev_sqlite_seed.py` → creates `dev.db` via `Base.metadata.create_all` → seeds; serve with `DATABASE_URL=sqlite+aiosqlite:///dev.db` |
| **Health check** | GET `/health` → `check_database()` runs `SELECT 1` → 200 `{status:"ok", database:"ok"}` or 503 |
| **Typical API request** | middleware chain → router → service → repository → (commit if write) → Pydantic JSON; audit log on successful mutation |
| **AI request (copilot)** | validate message → `RuleBasedCopilot.respond` → intent match or fallback → JSON with answer/sql/python/confidence |
| **Dashboard load (Overview)** | browser mounts `index.tsx` → `useKpis` + `useRecommendations` fire in parallel → cached forever → cards render; skeletons/empty arrays while pending |
| **Simulation** | slider change → new input object → query key changes → POST `/simulations/{domain}/run` → engine recomputes → result renders live |
| **Recommendation generation** | POST `/executive-summary` with a use case → 9-field template expansion → dialog renders fields |

---

# Interview Explanation

> "Explain your project."

**Problem statement.** We had a visually complete AI command-center demo for the Mahindra Group
— Auto, Finance, Collections, Logistics, Circular Economy, Compliance — but every number and
every "AI" answer was hardcoded in the frontend. My task was to turn it into a real product:
production backend, real persistence, identical UX.

**Architecture.** React 19 + TanStack Start frontend talking JSON to a FastAPI backend with a
strict router → service → repository layering over PostgreSQL 16 (async SQLAlchemy + Alembic).
The AI layer is deterministic rule-based engines behind Protocol seams, ready for real LLM
integration. 132 tests, Dockerized deployment.

**Tech stack.** FastAPI, Pydantic v2, SQLAlchemy 2 async, asyncpg/aiosqlite, Alembic, structlog,
pytest + httpx; React 19, TanStack Router/Query/Start, Tailwind 4, shadcn/ui.

**Backend highlights.** App factory pattern; one error envelope for every failure; request-id
correlation through structured logs; rate limiting with a stricter AI budget; TTL read cache;
audit logging of successful mutations; security headers.

**Database highlights.** 30 tables (28 domain + 2 reference) with ENUMs, CHECK constraints,
CASCADE relationships, JSONB lineage, GIN-indexed arrays, partial indexes; deterministic UUID5
seeding for idempotent provisioning; a portability layer so the same ORM runs on PostgreSQL or
SQLite.

**AI highlights.** Exact-parity ports of the prototype's engines (same rounding semantics as
JavaScript), intent-matching copilot, five simulation engines, Q&A matcher, and an LLM provider
registry that gracefully falls back to rules.

**Frontend highlights.** API-only data flow with SSR-safe guards, typed endpoint functions,
optimistic PoC updates, cache invalidation on mutations, and zero visual regressions.

**Workflow.** Plan phase-by-phase → schema & seed → services → API → AI parity → frontend wiring
→ mock removal → hardening, each phase covered by tests.

**Challenges.** (1) Bit-exact parity with JavaScript math — solved with `js_round` and parity
tests. (2) SSR framework that must never call the backend — solved with client-only queries.
(3) Running everything without Docker — solved with a SQLite seam used by tests and local dev.
(4) Finding and fixing a latent crash (non-null assertion during loading) during cutover.

**Design decisions.** Layering for isolated change; display labels on the wire for UI parity;
deterministic seeds for testability; Protocol seams for future LLMs; one error contract for the
whole frontend.

---

# Summary

| Phase | Completed work |
| ----- | -------------- |
| **Phase 0 — Foundations** | App factory, typed settings, structlog, error envelope + handlers, async session/DI, `/health`, Dockerfile + compose, Alembic async scaffold, quality tooling |
| **Phase 1 — Data model** | 28 domain tables (+2 reference), 14 ENUMs, relationships/CASCADE, CHECK + UNIQUE constraints, soft delete, one hand-written migration, deterministic seed system |
| **Phase 2 — Repos & services** | Generic base repository (soft-delete + ordering), 14 repositories, 15 services with explicit transactions, display-label conversion layer |
| **Phase 3 — REST API v1** | ~60 endpoints across 14 routers, full Pydantic contracts with bounds + camelCase aliases, correct HTTP semantics (201/204/404/409/422) |
| **Phase 4 — AI layer** | Rule-based copilot (7 intents + fallback), LLM provider registry with fallback, 5 simulation engines, Q&A matcher, ELV/EMI scoring, prompt templates, JS-parity utilities |
| **Phase 5 — Frontend wiring** | JSON client, typed endpoints, TS types, ~50 query/mutation hooks, all 13 pages re-wired, API-backed app context |
| **Phase 6 — Mock removal** | Mock files deleted with zero importers, dead code removed, loading-state crash fixed, full verification (lint/typecheck/build/13-route walkthrough/live copilot chat) |
| **Phase 7 — Hardening & docs** | Rate limiting (dual budget), read cache, audit logging, request-id correlation, security headers, 132 tests, ops scripts, README + this document |

## Remaining TODOs

- `backend/README.md` phase checklist is stale (only Phase 0 ticked) — cosmetic only.
- Auth/authentication (`users` table + `core/security.py` seam) is scaffolded but unimplemented.
- `copilot_sessions`/`copilot_messages` persistence and `simulation_runs` audit writes are
  reserved but not yet exercised by endpoints.
- Real LLM provider (`AI_PROVIDER=openai`) and RAG/embeddings are seams only.

## Potential improvements

- Persist copilot conversations and simulation runs (tables already exist).
- Swap `RuleBasedCopilot` for an LLM provider with RAG over seeded domain knowledge.
- Redis-backed cache/rate-limit for multi-instance deployments.
- Pagination on list endpoints as datasets grow; OpenAPI publication in staging.
- WebSocket/SSE for long-running agent workflows.

## Production readiness

The system is **demo-production ready**: every endpoint is validated, tested, rate-limited,
audited, and documented; data survives restarts in PostgreSQL; the frontend is fully API-backed
with graceful loading/error states. For enterprise production it still needs authentication,
real data integrations, an LLM upgrade, and horizontal-scaling infrastructure — all of which
have deliberate seams in place.

---

*Generated from a complete read of the repository. No source file was modified in the making of
this document; `working_details.md` is the only file created.*
