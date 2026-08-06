# AI Agent Handover

You are receiving this repository with no other context. This document tells
you what the system is, how it is built, what you may and may not touch, and
what to work on next. Read this first, then
[Project_Replication_Guide.md](./Project_Replication_Guide.md), then the
module docs as needed.

---

## 1. What This Project Is

**Mahindra AI Command Center** — an enterprise AI decision-support demo:
13 dashboard screens (Overview, Dealer, Finance, Collections, Logistics,
Circularity, Trust, Catalogue, Agents, Mobility Twin, Simulation, XR,
Copilot) backed by FastAPI + PostgreSQL with deterministic rule-based AI.

Two hard facts shape every task:

1. **The frontend is frozen.** It was built on Lovable and is the source of
   truth for the API contract. You work on the backend/data side to serve it.
2. **The repo is local-git-tracked** (initial commit `c686a1a`). Make small,
   logical commits. Never rewrite pushed history (Lovable sync constraint).

## 2. Architecture (60-second version)

```
frontend/ (React 19 + TanStack Start, port 8080, bun)
   └─ src/lib/api/endpoints.ts = the typed API contract (~60 endpoints)
backend/  (FastAPI, port 8000)
   api/v1 (routers) → services (logic) → repositories (queries) → models (ORM)
   schemas/ = pydantic wire contracts (camelCase aliases)
   ai/ = rule-based providers (prompts, scoring, causal) — AI_PROVIDER=rule|openai
PostgreSQL 16 in Docker (mahindra-postgres, volume pgdata)
   mahindra_ai = curated live data (alembic 0001, 203 rows)
   mahindra_ai_staging = synthetic data (549+ rows) ← backend currently points here
data/     synthetic pipeline (generators → CSVs → seed_database.py)
database/ parquet exports + backups/ + scripts/ (backup/restore/verify)
```

Request example: UI → `POST /api/v1/dealer-leads/{id}/convert` → router →
`DealerService` → repository → ORM row update → camelCase JSON back.

## 3. Coding Conventions

### Backend (Python 3.12+)
- Layering is strict: routers stay thin; business logic in `services/`;
  SQL access only in `repositories/`. Never query from a router.
- Pydantic schemas for every request/response; response models use
  **camelCase aliases** (`by_alias=True`) because the frontend expects them.
- Enums: SQLAlchemy `Enum(..., values_callable=lambda e: [m.value for m in e])`
  → stored lowercase; display labels mapped in `app/utils/display.py`.
- All datetime writes use timezone-aware `datetime.now(UTC)`; datetime
  columns must be `DateTime(timezone=True)` (a naive/aware mismatch crashes
  asyncpg — this bug was fixed once; do not regress it).
- IDs: UUIDs (`uuid_pk()`); JSON columns via `JSONType`; string arrays via
  `string_array()` (portable PG/SQLite helpers in `app/database/base.py`).
- Errors: raise `NotFoundError`/`ConflictError` from `app/core/errors.py`;
  the global handler returns `{"detail", "code", "request_id"}`.
- Logging: structlog, one line per request via middleware; keep request_id.
- Quality gates: `ruff check .` (line-length 120), `mypy app`, `pytest`.
  Tests run on SQLite (aiosqlite) — keep models portable.

### Frontend (do not modify — but read it)
- TanStack Start file-based routing; API layer in `src/lib/api/`.
- `types.ts` + `endpoints.ts` define exactly what the backend must return.
  When an endpoint changes shape, the frontend type IS the spec.

### Naming
- Python: snake_case files/functions, PascalCase classes, SCREAMING enums.
- Tables: plural snake_case (`dealer_leads`); columns snake_case.
- API paths: kebab-case segments (`/mobility-twin`), camelCase JSON keys.
- Synthetic codes: `syn-*` (dealers), `REC-SYN-*`, `SYN-Plant-*`, etc.

## 4. Database Conventions

- Alembic is the schema authority for `mahindra_ai`; hand-written migrations.
  **Never re-`CREATE TYPE` an enum that already exists** (known pitfall:
  causes `DuplicateObject` on `alembic upgrade`).
- Every table: UUID PK + `created_at`/`updated_at` (server-side now()) +
  soft-delete `deleted_at` where the mixin is applied.
- Staging DBs built by the seeder use `create_all` — they have no
  `alembic_version`; that is expected, not an error.
- Before any schema change: backup (`database/scripts/backup_database.sh`),
  write the migration, test on a throwaway DB, then apply.

## 5. Docker Workflow

- Dev: only `postgres` runs in Docker; uvicorn + vite run natively.
- `docker compose -f backend/docker-compose.yml up -d postgres`
- Never `down -v` without a fresh verified backup.
- Full-stack test: `up --build`, then exec alembic/seed into the api
  container (it does not auto-migrate).

## 6. Synthetic Data Workflow

- Regenerate: `python data/generators/run_all.py` (deterministic; byte-identical).
- Seed: `python backend/database/seed_database.py --database-url <fresh-db> --ensure-schema`
- The seeder is idempotent (uuid5 deterministic IDs), validates all CSVs
  before writing, refuses to collide with non-synthetic unique values, and
  supports `--reset-synthetic` / `--dry-run`.
- JSON payload columns must match the frontend's pydantic schema types
  exactly (e.g. `customer_twins.cross_sell` = `{product: "NN%"}` string map;
  `nba` = `headline/risk/expected_margin/confidence`). A shape mismatch 500s
  the API — this was fixed once; keep it fixed.
- Adding a dataset: generator + CSV + model + Alembic migration + seeder
  `TableSpec` entry (see `warranty_claims`/`notifications` as the template
  of "CSV exists, table pending").

## 7. Project Priorities (implementation order)

1. **Keep the verified stack green**: health, 13 screens, write endpoints,
   `verify_database.sh` snapshot MATCH. This is the acceptance bar for
   everything else.
2. **Phase-2 datasets**: `warranty_claims` + `notifications` tables →
   models → migration → seeder specs → endpoints if/when the frontend adds
   screens for them (it currently does not — do not invent UI).
3. **Real-data path**: define normalization for `data/raw` → `data/processed`
   matching existing CSV contracts; seeder needs zero changes.
4. **OpenAI provider**: wire + test `AI_PROVIDER=openai` paths (copilot,
   explanations) without altering rule-mode outputs.
5. **Production hardening**: secrets rotation, CORS origins, DEBUG=false,
   nginx/TLS, CI (lint+tests+build), backup cron.

## 8. Things That Must NEVER Be Modified

| Protected item | Reason |
|---|---|
| `frontend/**` (routes, components, hooks, styles, lib) | Frozen Lovable UI; it defines the API contract |
| Existing API response shapes (`schemas/*` field names/aliases) | Frontend types depend on them |
| Curated `backend/app/database/seed_data.py` values | Business-approved demo content |
| `SYNTHETIC_NAMESPACE` / uuid5 scheme in the seeder | Rerun idempotency depends on stable IDs |
| `GENERATOR_SEED = 20260806` & per-generator offsets | Determinism / reproducibility |
| `data/synthetic/*.csv` by hand | They are generated artifacts — change the generator and regenerate |
| Published git history | Lovable sync |
| Live `mahindra_ai` data during experiments | Use staging/throwaway DBs |

Additive work (new files, new endpoints, new tables) is always allowed;
modification of the protected list requires explicit human approval.

## 9. Environment Quick Facts

- Backend runs ONLY inside `backend/.venv` (create: `python3 -m venv .venv`).
- Frontend deps install with `bun install` (never `npm install` — bun.lock is
  authoritative and `@lovable.dev/vite-tanstack-config` matters).
- Health endpoint: `GET /health` (not `/api/v1/health`).
- Backend currently reads `backend/.env` → `DATABASE_URL=…mahindra_ai_staging`
  (the cutover). Rollback = swap DB name + restart (see Seeding_Guide.md).
- Ports: 8080 frontend, 8000 backend, 5432 PG. CORS must include `http://localhost:8080`.

## 10. Verification Ritual (run after any change)

```bash
curl -s localhost:8000/health                                   # database: up
bash database/scripts/verify_database.sh mahindra_ai_staging    # counts + FK orphans
cd backend && pytest -q && ruff check .                         # tests + lint
# browser: the 13 screens render; console clean (hydration notices are benign)
```

## 11. Known Pitfalls (learned the hard way)

1. **Naive vs aware datetimes** — ORM column naive + `datetime.now(UTC)` =
   asyncpg `DataError`. Always `DateTime(timezone=True)` for app-written stamps.
2. **Alembic enum duplication** — hand-written migrations must not re-create
   existing enum types.
3. **pg_stat counters reset** after PG restart — verify with `COUNT(*)`
   (the verify script already does).
4. **PowerShell on the source machine** mangles object property access in
   the Node fallback shell — use Python one-liners for API tests there.
   Irrelevant on the Linux VM.
5. **500s strip CORS headers** — a "CORS error" in the browser usually means
   the endpoint itself crashed; read the traceback first.
6. **`pyarrow` is not installed by default** — needed for `database/*.parquet`.
7. **Frontend null-safety** — screens assume fields exist; never return
   `null` where the type says `string`/number.

## 12. Where Things Live (cheat sheet)

| Need | Location |
|---|---|
| API endpoint list | `frontend/src/lib/api/endpoints.ts` + `backend/app/api/v1/router.py` |
| Table definitions | `backend/app/models/*.py`, migration `backend/alembic/versions/0001_initial_schema.py` |
| Curated demo data | `backend/app/database/seed_data.py` |
| Synthetic CSVs | `data/synthetic/` (generators in `data/generators/`) |
| Seeder | `backend/database/seed_database.py` |
| Backups & scripts | `database/backups/`, `database/scripts/` |
| Screen-by-screen analysis | `docs/Codebase_Data_Analysis.md` |
| Everything else | `docs/Project_Replication_Guide.md` |

---

*If a requested change conflicts with §8, stop and surface the conflict
instead of proceeding. The stack you received is verified green — keep it
that way.*
