# Database Setup

PostgreSQL 16 runs **exclusively in Docker** (`postgres:16-alpine`, container
`mahindra-postgres`). No host PostgreSQL installation is required.

Reference facts (source machine):

| Item | Value |
|---|---|
| Image | `postgres:16-alpine` (server reports PostgreSQL 16.14) |
| Container name | `mahindra-postgres` |
| User / password | `mahindra` / `mahindra` (dev defaults in `backend/docker-compose.yml`) |
| Port | `5432:5432` |
| Volume | named volume `pgdata` → `/var/lib/postgresql/data` |
| Databases | `mahindra_ai` (curated live), `mahindra_ai_staging` (synthetic) |
| Schema source | Alembic `backend/alembic/versions/0001_initial_schema.py` (31 tables, 14 enum types) |

---

## 1. Database & User Creation

### Automatic (compose)

`backend/docker-compose.yml` creates the user and the first database on
first start of the empty volume:

```bash
docker compose -f backend/docker-compose.yml up -d postgres
```

Equivalent manual SQL (run inside the container):

```bash
docker exec -it mahindra-postgres psql -U mahindra -d postgres
```

```sql
CREATE USER mahindra WITH PASSWORD 'mahindra';      -- already exists via compose
CREATE DATABASE mahindra_ai OWNER mahindra;
CREATE DATABASE mahindra_ai_staging OWNER mahindra; -- optional staging DB
```

### Permissions model

Single non-superuser role `mahindra` owns everything it creates. The app
connects as the same role, so no extra GRANTs are needed for development.
For production hardening, split into `app_rw` (DML) and `migrator` (DDL)
roles — out of scope for replication.

---

## 2. Schema & Seed (from scratch)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

alembic upgrade head          # creates 31 tables + enum types, stamps alembic_version=0001
python scripts/seed_db.py     # curated demo rows (backend/app/database/seed_data.py)
```

Staging/synthetic database (optional):

```bash
docker exec mahindra-postgres psql -U mahindra -d postgres -c "CREATE DATABASE mahindra_ai_staging;"
python database/seed_database.py \
  --database-url "postgresql+asyncpg://mahindra:mahindra@localhost:5432/mahindra_ai_staging" \
  --ensure-schema
# -> 549 rows across 28 tables (see docs/Seeding_Guide.md)
```

## 3. Restore From Backup (recommended on a fresh VM)

Committed backups live in `database/backups/<timestamp>/`. Scripts in
`database/scripts/`:

```bash
# Full restore (schema + data) — refuses to overwrite an existing DB
bash database/scripts/restore_database.sh database/backups/<ts>/mahindra_ai_full.dump
bash database/scripts/restore_database.sh database/backups/<ts>/mahindra_ai_staging_full.dump

# Overwrite an existing target explicitly (DESTRUCTIVE for that DB only)
DROP_EXISTING=true bash database/scripts/restore_database.sh <dump> <target_db>

# Schema-only or data-only artifacts restore the same way
bash database/scripts/restore_database.sh database/backups/<ts>/mahindra_ai_schema_only.dump mahindra_ai_schema
```

Under the hood these run:

```bash
docker exec mahindra-postgres psql -U mahindra -d postgres -c "CREATE DATABASE <db>;"
docker exec -i mahindra-postgres pg_restore -U mahindra -d <db> --no-owner --no-privileges --exit-on-error < dump
# plain-SQL alternative:
docker exec -i mahindra-postgres psql -U mahindra -d <db> < mahindra_ai_full.sql
```

> Note: dumps made with `--schema-only`/default pg_dump do NOT include
> `CREATE DATABASE` — the restore script creates the database first.

---

## 4. Backup

```bash
bash database/scripts/backup_database.sh                 # both databases
bash database/scripts/backup_database.sh mahindra_ai     # single database
```

Per database it writes into `database/backups/<YYYYMMDD_HHMMSS>/`:

| Artifact | Content | Restore tool |
|---|---|---|
| `<db>_full.dump` | schema + data, custom format | `pg_restore` |
| `<db>_full.sql` | schema + data, plain SQL | `psql` |
| `<db>_schema_only.dump` | DDL only | `pg_restore` |
| `<db>_data_only.dump` | rows only (schema must exist) | `pg_restore` |
| `<db>_row_counts.txt` | exact `COUNT(*)` per table | verification aid |
| `SHA256SUMS` | integrity checksums of all artifacts | `sha256sum -c` |

All operations are read-only (`pg_dump` never writes). After copying backups
to another machine, verify integrity first:

```bash
cd database/backups/<ts> && sha256sum -c SHA256SUMS
```

---

## 5. Verification

```bash
bash database/scripts/verify_database.sh                       # mahindra_ai
bash database/scripts/verify_database.sh mahindra_ai_staging
bash database/scripts/verify_database.sh mahindra_ai database/backups/<ts>/mahindra_ai_row_counts.txt
```

Checks performed: connectivity/version, `alembic_version`, per-table exact
row counts, diff against backup snapshot, FK orphan scan, enum inventory.

Reference results (source machine, 2026-08-06):

| Database | Tables | Rows | alembic_version |
|---|---|---|---|
| `mahindra_ai` | 31 | 203 | `0001` |
| `mahindra_ai_staging` | 30 | 551 | none (created via `create_all`) |

---

## 6. Connection Strings

| Purpose | URL |
|---|---|
| Backend (SQLAlchemy/asyncpg) | `postgresql+asyncpg://mahindra:mahindra@localhost:5432/mahindra_ai` |
| Staging variant | same, database `mahindra_ai_staging` |
| Container-internal (API container in compose) | `postgresql+asyncpg://mahindra:mahindra@postgres:5432/mahindra_ai` |
| psql | `docker exec -it mahindra-postgres psql -U mahindra -d mahindra_ai` |
| pgAdmin/DBeaver (from host) | host `localhost`, port `5432`, user/pass `mahindra`/`mahindra` |

---

## 7. Migration Process (Alembic)

```bash
cd backend && source .venv/bin/activate

alembic current               # show applied revision (expect 0001)
alembic history               # list revisions
alembic upgrade head          # apply pending migrations
alembic revision --autogenerate -m "change description"   # author a new one
alembic downgrade -1          # roll back one revision
```

Conventions (see `docs/Database_Schema.md`):

- Enums are PostgreSQL `CREATE TYPE ... AS ENUM` with lowercase values;
  ORM uses `values_callable` to store lowercase.
- Portable column types live in `backend/app/database/base.py` (`JSONType`,
  `string_array()`, `uuid_pk()`), so models work on PG and SQLite (tests).
- Hand-written migrations must NOT duplicate `CREATE TYPE` for existing
  enums (known pitfall — see AI_Agent_Handover.md).

---

## 8. Docker Commands Cheat-Sheet

```bash
docker compose -f backend/docker-compose.yml up -d postgres   # start
docker compose -f backend/docker-compose.yml stop postgres    # stop (data kept in volume)
docker compose -f backend/docker-compose.yml down             # stop container (volume kept)
docker compose -f backend/docker-compose.yml down -v          # DESTROYS DATA (volume removed)
docker logs mahindra-postgres                                  # server logs
docker exec -it mahindra-postgres psql -U mahindra -d mahindra_ai
```

> ⚠ Never run `down -v` unless you intend to erase all data — and take a
> backup first (`backup_database.sh`).
