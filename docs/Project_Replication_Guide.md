# Project Replication Guide — MASTER DOCUMENT

**Mahindra AI Nexus / Mahindra AI Command Center**

This is the master reference for reproducing the project end-to-end on a
fresh Linux VM using only this repository and the `docs/` folder. Detailed
companions:

| Document | Scope |
|---|---|
| [Environment_Replication_Guide.md](./Environment_Replication_Guide.md) | System requirements + install commands + setup steps |
| [Database_Setup.md](./Database_Setup.md) | DB creation, backup/restore, migrations |
| [Docker_Setup.md](./Docker_Setup.md) | Containers, volumes, lifecycle |
| [AI_Agent_Handover.md](./AI_Agent_Handover.md) | Continuing development (conventions, priorities) |
| [Codebase_Data_Analysis.md](./Codebase_Data_Analysis.md) | File-by-file analysis of every screen/module |
| [Data_Model.md](./Data_Model.md) / [Database_Schema.md](./Database_Schema.md) / [Entity_Relationships.md](./Entity_Relationships.md) | Data architecture |
| [Synthetic_Data_Generation.md](./Synthetic_Data_Generation.md) / [Seeding_Guide.md](./Seeding_Guide.md) | Synthetic pipeline + seeder |

---

## 1. Project Overview

An enterprise **AI Command Center** demo/prototype for Mahindra covering:
Auto Sales & Dealer Optimization, Financial Twin, Collections, Logistics,
Circular Economy (ELV/RVSF/carbon credits/dMRV), Trust & Compliance,
Auto Mobility Twin (causal graph), What-if Simulation, XR, and an AI Copilot.

Architecture: a **frozen Lovable React frontend** (API-only contract) served
by a **FastAPI + PostgreSQL backend**. All intelligence is deterministic
in-repo "rule" logic by default (`AI_PROVIDER=rule`) with an optional OpenAI
path. A synthetic-data pipeline produces realistic, interlinked Indian
business data (549 rows / 28 tables) for staging.

Current state: **fully working local development stack** (verified
end-to-end on 2026-08-06), backend currently pointed at the synthetic
staging database.

## 2. Folder Structure

```
mahindra-ai-nexus/
├── frontend/                  # React app (TanStack Start + Vite 8 + Tailwind 4 + shadcn/ui)
│   ├── src/routes/            # 13 file-based routes (one per module screen)
│   ├── src/components/        # layout + ui (shadcn) + feature components
│   ├── src/lib/api/           # endpoints.ts (typed API surface), types.ts, client.ts
│   ├── .env.example           # VITE_API_BASE_URL template
│   └── bun.lock               # LOCKED dependency resolution — use bun install
├── backend/                   # FastAPI app
│   ├── app/
│   │   ├── api/v1/            # routers (one per module) + router.py aggregator
│   │   ├── models/            # SQLAlchemy 2.0 ORM (17 files, 28 tables) + enums
│   │   ├── schemas/           # pydantic response/request contracts (camelCase aliases)
│   │   ├── repositories/      # DB access layer
│   │   ├── services/          # business logic layer
│   │   ├── ai/                # rule-based AI: prompts, scoring, causal, providers
│   │   ├── middleware/        # request_context, rate_limit, audit_log, security_headers
│   │   ├── core/              # config (pydantic-settings), errors, logging
│   │   └── database/          # base.py (portable types), seed_data.py (curated)
│   ├── alembic/               # migrations (0001_initial_schema)
│   ├── database/seed_database.py   # CSV -> PostgreSQL seeder
│   ├── scripts/               # seed_db.py, dev_sqlite_seed.py, smoke_* , load_test
│   ├── tests/                 # pytest (asyncio_mode=auto; SQLite in tests)
│   ├── docker-compose.yml     # postgres + api services
│   ├── Dockerfile             # two-stage python:3.12-slim, non-root
│   ├── requirements.txt       # pinned-ranges dependencies
│   └── pyproject.toml         # ruff/mypy/pytest config
├── data/
│   ├── generators/            # 17 deterministic generators + common.py + run_all.py
│   ├── synthetic/             # 30 generated CSVs (committed)
│   ├── raw/ , processed/      # landing zones for future real Mahindra data
├── database/
│   ├── *.parquet              # analytics exports of curated seed
│   ├── backups/               # pg_dump artifacts (full/schema/data/counts/SHA256)
│   └── scripts/               # backup_database.sh, restore_database.sh, verify_database.sh
├── docs/                      # this documentation set
└── .env.example               # consolidated env-var reference (root)
```

## 3. Technology Stack

| Layer | Technology | Version verified |
|---|---|---|
| Frontend framework | React 19 + TanStack Start/Router | react 19.2, @tanstack/react-start 1.168 |
| Frontend build | Vite 8 + nitro + `@lovable.dev/vite-tanstack-config` | vite 8.0.16 |
| UI kit | shadcn/ui (Radix) + Tailwind CSS 4 | tailwindcss 4.2 |
| FE package manager | **Bun** (bun.lock authoritative) | 1.3.14 |
| Backend | FastAPI + uvicorn + pydantic 2 / pydantic-settings | fastapi >=0.115,<1.0 |
| ORM | SQLAlchemy 2.0 async + asyncpg | sqlalchemy >=2.0.30,<2.1 |
| Migrations | Alembic | >=1.13 |
| Database | PostgreSQL 16 (`postgres:16-alpine` in Docker) | 16.14 |
| Structured logging | structlog | >=24.1 |
| Tests | pytest + pytest-asyncio + httpx + aiosqlite | pytest >=8.2 |
| Quality | ruff (line-length 120, py312) + mypy | ruff >=0.5 |
| Data generation | Faker (en_IN locale), deterministic seeds | via backend venv |
| Containers | Docker Engine + Compose plugin | 29.4 / v5.1 |
| Runtime | Python 3.12+ (venv 3.13.5 on source), Node 20+, Bun | — |

**Not used:** Redis, Nginx (dev), Kubernetes, external queues.

## 4. Development Workflow

Three processes, one Docker container:

1. `docker compose -f backend/docker-compose.yml up -d postgres`
2. `cd backend && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000`
3. `cd frontend && bun run dev -- --port 8080 --host`

Loop: edit code → uvicorn reloads manually (restart it; `--reload` optional)
→ Vite HMR handles frontend → verify at `http://localhost:8080`.

Commit discipline: small logical commits; never rewrite pushed history
(Lovable-synced branch constraint in `frontend/AGENTS.md`).

## 5. Frontend Setup

```bash
cd frontend
bun install                          # MUST be bun (bun.lock is authoritative)
cp .env.example .env.local           # VITE_API_BASE_URL=http://localhost:8000/api/v1
bun run dev -- --port 8080 --host
```

Screens (routes): `/` (overview), `/dealer`, `/finance`, `/collections`,
`/logistics`, `/circularity`, `/trust`, `/catalogue`, `/agents`,
`/mobility-twin`, `/simulation`, `/xr`, `/copilot`.

The frontend is **API-only**: `src/lib/api/endpoints.ts` defines the full
typed surface under `/api/v1`. SSR fallbacks exist, but live screens need the
backend up. **The frontend is frozen** — see §21/Handover for the rule.

## 6. Backend Setup

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Layering (enforced by convention): `api/v1/*` routers → `services/*`
(business logic) → `repositories/*` (queries) → `models/*` (ORM). Pydantic
`schemas/*` are the wire contract and use **camelCase aliases** for the
frontend.

Health: `GET /health` → `{"status":"ok","database":"up"}` (note: `/health`,
NOT `/api/v1/health`).

## 7. PostgreSQL Setup

See [Database_Setup.md](./Database_Setup.md). Two databases:

- `mahindra_ai` — curated demo data (31 tables, 203 rows, alembic 0001)
- `mahindra_ai_staging` — synthetic seed (30 tables, 549+ rows, create_all)

Fastest replication on a VM: restore the committed dumps in
`database/backups/` with `database/scripts/restore_database.sh`.

## 8. Docker Setup

See [Docker_Setup.md](./Docker_Setup.md). Dev = postgres-only from
`backend/docker-compose.yml`; full-stack = `up --build` (postgres + API
image, non-root, healthchecked).

## 9. Environment Variables

Full catalog with explanations: root [`.env.example`](../.env.example).
Components read their own files: `backend/.env` (from `backend/.env.example`)
and `frontend/.env.local` (from `frontend/.env.example`). Secrets are never
committed; `.env*` (except `.env.example`) is git-ignored.

## 10. Database Restore

```bash
bash database/scripts/restore_database.sh database/backups/<ts>/mahindra_ai_full.dump
bash database/scripts/restore_database.sh database/backups/<ts>/mahindra_ai_staging_full.dump
bash database/scripts/verify_database.sh mahindra_ai database/backups/<ts>/mahindra_ai_row_counts.txt
```

Restore refuses to overwrite existing databases unless `DROP_EXISTING=true`.

## 11. Startup Sequence

```
1. docker start mahindra-postgres            (or compose up -d postgres)
2. backend:  uvicorn app.main:app --host 0.0.0.0 --port 8000   (venv active)
3. frontend: bun run dev -- --port 8080 --host
```

Order matters only for the first request: the backend needs PG up; the
frontend needs the backend for live data (SSR fallbacks mask brief gaps).

## 12. Verification Checklist

- [ ] `docker ps` shows `mahindra-postgres` healthy
- [ ] `curl localhost:8000/health` → `status ok`, `database up`
- [ ] `curl localhost:8000/api/v1/dealers` returns JSON rows
- [ ] `bash database/scripts/verify_database.sh mahindra_ai` → 31 tables / 203 rows, 0 orphans, snapshot MATCH
- [ ] `verify_database.sh mahindra_ai_staging` → 30 tables / 549+ rows
- [ ] `curl -I localhost:8080` → 200; all 13 screens render data in a browser
- [ ] Write path: `POST /api/v1/dealer-leads/{id}/message` flips status and persists
- [ ] `cd backend && pytest -q` green

## 13. Common Issues

| Symptom | Resolution |
|---|---|
| `asyncpg ConnectionRefusedError` | PG container not started/paused → `docker start mahindra-postgres` |
| `/api/v1/health` returns 404 | health endpoint is `/health` |
| `ModuleNotFoundError: sqlalchemy` | venv not activated; run backend only inside `backend/.venv` |
| CORS error on one endpoint only | Usually a 500 beneath it (error responses bypass CORS headers) — read uvicorn traceback |
| `can't subtract offset-naive and offset-aware datetimes` | datetime column declared naive while service writes `datetime.now(UTC)` — align model to `DateTime(timezone=True)` (fixed for all current columns) |
| Frontend shows fallback/empty data | Backend down or `VITE_API_BASE_URL` wrong |
| `bun` command missing on VM | Install bun (§2.4 of Environment guide) — npm install is NOT equivalent |
| Parquet scripts fail | `pip install pyarrow` explicitly |
| Alembic `DuplicateObject` on enum | Migration re-created an existing `CREATE TYPE` — see Handover pitfalls |

## 14. Troubleshooting

Deeper playbook: backend logs (`structlog` JSON), `docker logs
mahindra-postgres`, `alembic current` vs `alembic history`, and the seeder's
`--dry-run` (validates CSVs without a DB). For UI regressions use the browser
devtools network tab against `endpoints.ts` types — response shapes are the
contract. Reference: `docs/Codebase_Data_Analysis.md` maps every screen to
its endpoints and tables.

## 15. Architecture

```
Browser (React 19 SSR+CSR, port 8080)
   │  fetch JSON (camelCase)
   ▼
FastAPI (port 8000)
   ├─ middleware: request_context → security_headers → rate_limit → audit_log → CORS
   ├─ api/v1 routers (thin) ── validate with pydantic schemas
   ├─ services (business rules, display mapping)
   ├─ repositories (async SQLAlchemy queries)
   ├─ ai/ (rule providers: prompts, scoring, causal graph) — pluggable via AI_PROVIDER
   └─ models → PostgreSQL 16 (asyncpg), Alembic-managed schema
```

Cross-cutting: deterministic rule-AI keeps demos reproducible; structured
logging + request IDs; soft-delete and timestamp mixins on every table.

## 16. Request Flow (example: lead conversion)

```
UI dealer.tsx → POST /api/v1/dealer-leads/{id}/convert
 → dealers.py router → DealerService.convert_lead()
 → TwinRepository/LeadRepository load row (FK dealer verified)
 → status=converted, converted_at=now(UTC) → commit
 → LeadOut (camelCase) → UI updates panel
```

## 17. Data Flow

```
data/generators (Faker, seed 20260806) ──run_all.py──▶ data/synthetic/*.csv
        backend/database/seed_database.py (validate → coerce → FK-resolve → upsert)
                ▼
   PostgreSQL mahindra_ai_staging (549 rows / 28 tables)
                ▲
curated path: backend/app/database/seed_data.py → scripts/seed_db.py → mahindra_ai
analytics:    database/*.parquet (pyarrow exports of curated seed)
future real:  data/raw → normalize → data/processed → same seeder contracts
```

## 18. AI Layer

- `app/ai/prompts/*` — curated text (RM scripts, explanations, copilot prompts)
- `app/ai/scoring/*` — deterministic scoring (EMI simulation etc.)
- `app/ai/causal/*` — causal graph + driver lists for the mobility twin/simulators
- `app/ai/providers/*` — `AI_PROVIDER=rule` (default) vs `openai`
- Copilot sessions/messages persist in `copilot_sessions`/`copilot_messages`
  (runtime tables, empty on a fresh restore — accrue from usage)

## 19. Synthetic Data Pipeline

Deterministic (`GENERATOR_SEED=20260806`, per-generator offsets), Indian
locale, business-chain correlated (lead quality → booking prob → finance
approval → CSAT). 17 generators → 30 CSVs; seeder maps CSV → 28 tables with
uuid5 deterministic IDs (namespace
`7c3e9a1d-52b8-4e06-9f41-d2a8b6c0e517`), FK resolution by natural keys,
unique-collision guard, idempotent upserts, `--reset-synthetic`. Two CSVs
(`notifications`, `warranty_claims`) are Phase-2 datasets without tables yet.
Full docs: Synthetic_Data_Generation.md + Seeding_Guide.md.

## 20. Current Project Status (2026-08-06)

| Area | Status |
|---|---|
| Frontend (13 screens) | ✅ complete, frozen, verified rendering against staging data |
| Backend API (~60 endpoints) | ✅ complete, all reads+writes verified |
| PostgreSQL live `mahindra_ai` | ✅ 203 rows curated, alembic 0001, backup committed |
| Staging `mahindra_ai_staging` | ✅ 549+ synthetic rows; **backend currently points here** via `backend/.env` |
| Synthetic pipeline | ✅ deterministic, documented |
| Backup/restore/verify scripts | ✅ created & executed (artifacts in `database/backups/`) |
| Git | ✅ local repo, initial commit `c686a1a`, clean tree |
| Production deploy | ⏳ not wired (compose path available; no CI/CD) |

## 21. Pending Tasks

1. **Phase-2 datasets**: add `warranty_claims` + `notifications` tables
   (models + Alembic revision + seeder `TableSpec`) — CSVs already generated.
2. **Real-data ingestion**: normalize Mahindra extracts into `data/processed/`
   matching CSV contracts; point seeder `--data-dir` there.
3. **OpenAI integration test** with a real key (`AI_PROVIDER=openai`).
4. **CI/CD + production deploy**: nginx/TLS, secrets management, proper CORS
   origins, `ENVIRONMENT=production`, `DEBUG=false`, DB credentials rotation.
5. **Optional**: pgAdmin/DBeaver documentation for analysts; load-test
   results refresh (`backend/scripts/load_test.py`).

## 22. Known Limitations

- AI layer is rule-based/deterministic by design — no real ML models yet.
- Copilot has no auth; rate limiting is in-memory (single process).
- `backend/dev.db`/`smoke.db` SQLite files are dev/test leftovers (git-ignored).
- Frontend SSR hydration warnings (`data-tsd-source`) are benign dev noise.
- `n_live_tup` stats reset after PG restart — verification scripts use exact
  `COUNT(*)` for this reason.
- Source machine is Windows/PowerShell; all scripts in `database/scripts/`
  are POSIX bash (run natively on the target Linux VM).

## 23. Deployment Flow (target architecture)

```
[Linux VM]
 nginx :443 (TLS) ──▶ frontend (bun run build output / node host) :8080
                └──▶ /api + /health → uvicorn/gunicorn :8000 (or mahindra-api container)
 Docker: mahindra-postgres (:5432 internal only, pgdata volume)
 Backups: cron + database/scripts/backup_database.sh → offsite copy
```

Steps: provision VM (§Environment guide) → clone repo → restore backups →
`alembic upgrade head` → set production `.env` (DEBUG=false, real CORS,
strong DB password) → `docker compose up -d --build` or uvicorn+nginx →
verify §12 checklist → point DNS.

---

*Generated 2026-08-06 as part of the Linux-VM migration preparation. No
existing code, config or data was modified while producing this document.*
