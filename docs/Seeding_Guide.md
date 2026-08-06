# Seeding Guide

How to load `data/synthetic/*.csv` into PostgreSQL using
`backend/database/seed_database.py`.

## Prerequisites

- PostgreSQL 16 running (Docker in this project):
  ```powershell
  docker compose -f backend/docker-compose.yml up -d postgres   # or your compose file
  ```
- Backend virtualenv (contains SQLAlchemy, asyncpg, Faker):
  `backend\.venv\Scripts\python.exe`
- Generated CSVs in `data/synthetic/` (run `data/generators/run_all.py` first).

## Recommended flow

```powershell
# 1. Validate everything without touching any database
backend\.venv\Scripts\python.exe backend\database\seed_database.py --dry-run

# 2. Seed a FRESH database (schema + data in one shot)
backend\.venv\Scripts\python.exe backend\database\seed_database.py `
    --database-url "postgresql+asyncpg://mahindra:mahindra@localhost:5432/mahindra_ai_seedtest" `
    --ensure-schema

# 3. Rerun anytime — fully idempotent (0 inserted, N updated)
backend\.venv\Scripts\python.exe backend\database\seed_database.py `
    --database-url "postgresql+asyncpg://mahindra:mahindra@localhost:5432/mahindra_ai_seedtest"

# 4. Wipe only the synthetic rows, then reload
backend\.venv\Scripts\python.exe backend\database\seed_database.py `
    --database-url "postgresql+asyncpg://mahindra:mahindra@localhost:5432/mahindra_ai_seedtest" `
    --reset-synthetic
```

## CLI reference

| Flag | Effect |
|---|---|
| `--database-url` | Async SQLAlchemy URL. Default: backend settings (`DATABASE_URL` / `.env`). |
| `--data-dir` | CSV directory. Default: `data/synthetic`. |
| `--dry-run` | Validate headers, required columns, enums, JSON and types. No writes, no connection needed. |
| `--ensure-schema` | Run `Base.metadata.create_all` first (fresh databases only). |
| `--reset-synthetic` | Delete rows whose deterministic UUIDs match the current CSVs, then reload. Never touches other rows. |

## Safety model

1. **Deterministic UUIDs.** Every synthetic row id is
   `uuid5(SYNTHETIC_NAMESPACE, "synthetic:<table>:<natural-key>")` with a
   namespace dedicated to synthetic data. Reruns hit the same PKs → updates,
   never duplicates.
2. **Unique-collision guard.** Before any write, the seeder checks every
   UNIQUE column against existing rows. If a value already belongs to a
   non-synthetic row, the run aborts — protecting curated/live data.
3. **FK-safe order.** Parents load before children; FK UUIDs are recomputed
   from natural keys, so no lookup queries and no orphans.
4. **Fail-fast validation.** All 24 CSVs are validated before the first
   insert; a bad row never produces a partial load (single transaction commit
   at the end).
5. **Shared lookups preserved.** `--reset-synthetic` skips `regions` and
   `vehicle_models` (natural-PK reference rows shared with curated data).

> **Never run the seeder against the live `mahindra_ai` demo database.**
> The synthetic dataset intentionally mirrors curated business values (same
> KPI codes, agent names, bucket names) and would collide with curated rows.
> Always target a fresh or staging database.

## Validation record (executed in this repository)

| Step | Result |
|---|---|
| `--dry-run` | 24 CSVs / 549 rows validated, 0 writes |
| Fresh DB `--ensure-schema` + seed | 549 inserted across 28 tables |
| Rerun (idempotency) | 0 inserted, 549 updated |
| `--reset-synthetic` + reseed | 540 removed → 540 inserted + 9 lookup updates |
| FK integrity joins | dealer_leads 151/151, kpi_drivers 14/14, causal_edges 12/12, solutions 36/36 |

Verified against a throwaway database `mahindra_ai_seedtest` (dropped
afterwards). The live `mahindra_ai` database and the running application were
never touched.

## Skipping behaviour

`notifications.csv` and `warranty_claims.csv` are generated for Phase 2 but
have no tables yet — the seeder reports them as skipped future datasets.
Add the tables to `backend/app/models/` and a `TableSpec` entry in the
seeder registry to activate them.

## Replacing synthetic with real data

Point `--data-dir` at `data/processed/` once real Mahindra extracts are
normalized to the same CSV contracts. Nothing else changes.

## Live cutover — FastAPI now serves the staging database (2026-08-06)

The backend was pointed at a synthetic-seeded staging database so the UI
exercises realistic data volumes without touching the curated demo rows.

| Item | Value |
|---|---|
| Staging database | `mahindra_ai_staging` (same Docker container `mahindra-postgres`) |
| Config change | `backend/.env` → `DATABASE_URL=postgresql+asyncpg://mahindra:mahindra@localhost:5432/mahindra_ai_staging` |
| Seeded | 549 rows / 28 tables via `seed_database.py --ensure-schema` |
| Frontend | **Untouched** — same routes, components and API contract |
| Live `mahindra_ai` | **Untouched** — retained as instant rollback |

Post-cutover fixes discovered by verification (backend-only, additive):

- `dealer_leads.message_sent_at` / `converted_at`, `carbon_credits.repriced_at` /
  `buyer_matched_at`, `recommendations.decided_at` were declared naive
  `DateTime` in the ORM while services write `datetime.now(UTC)` — changed to
  `DateTime(timezone=True)` to match the Alembic migration; staging columns
  altered to `TIMESTAMPTZ`.
- `customer_twins.nba` / `cross_sell` JSON now matches the frontend contract
  (`headline/risk/expected_margin/confidence`, product → `"NN%"` string map).

### Rollback (30 seconds)

```powershell
# 1. Swap the two DATABASE_URL lines in backend\.env back to mahindra_ai
# 2. Restart the backend
Set-Location 'd:\Mahindra AI Nexus\backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Re-seeding the staging database

```powershell
backend\.venv\Scripts\python.exe data\generators\run_all.py
backend\.venv\Scripts\python.exe backend\database\seed_database.py `
    --database-url "postgresql+asyncpg://mahindra:mahindra@localhost:5432/mahindra_ai_staging"
```

Note: re-seeding overwrites any UI-driven demo changes (converted leads,
approved recommendations, rerouted shipments, etc.) with the fresh synthetic
baseline — this is intentional.
