# Mahindra AI Command Center — Backend

Production backend for the Mahindra AI Command Center demo platform.
FastAPI + PostgreSQL (SQLAlchemy 2.x async, Alembic migrations, Pydantic v2),
clean layered architecture with a pluggable AI layer.

> Master blueprint: [`implementation_plan.md`](../implementation_plan.md) at the repository root.

## Stack

| Concern     | Choice                                            |
|-------------|---------------------------------------------------|
| API         | FastAPI (async), versioned under `/api/v1`         |
| Database    | PostgreSQL 16 via asyncpg + SQLAlchemy 2.x         |
| Migrations  | Alembic (async, autogenerate against ORM metadata) |
| Validation  | Pydantic v2 + pydantic-settings                    |
| Logging     | structlog (console in dev, JSON in prod)           |
| Tests       | pytest + pytest-asyncio + httpx (ASGI in-process)  |

## Architecture

```
app/
├── main.py              # app factory: middleware, handlers, routers
├── core/                # config, logging, errors, security seam
├── database/            # engine, session, base + mixins (UUID/audit/soft-delete)
├── middleware/          # request-id correlation + timing
├── api/
│   ├── deps.py          # FastAPI dependencies (session, current user)
│   ├── health.py        # GET /health
│   └── v1/router.py     # domain routers mount here
├── schemas/             # Pydantic v2 API contracts
├── models/              # SQLAlchemy ORM models (28-table schema, phased)
├── repositories/        # all SQL access
├── services/            # business logic + transactions
├── ai/                  # pluggable engines behind protocols
└── utils/               # helpers (rounding parity, pagination)
```

Request flow: **router → service → repository → database**; AI engines are
invoked by services only and are swappable (`AI_PROVIDER=rule|openai`).

## Quick start

```powershell
# 1. Full stack (PostgreSQL + API) via Docker
docker compose up --build

# — or run natively —
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env

# 2. Database (start once, reused volume)
docker compose up -d postgres

# 3. Migrations + seed (added in later phases)
alembic upgrade head

# 4. Run the API
uvicorn app.main:app --reload
```

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/health

## Configuration

All settings come from environment variables / `.env` (see `.env.example`):
`DATABASE_URL`, `ENVIRONMENT`, `CORS_ORIGINS`, `AI_PROVIDER`, `LOG_LEVEL`,
pool sizing (`DB_POOL_*`).

## Tests & quality

```powershell
pytest                      # test suite
ruff check app tests        # lint
mypy app                    # type check
```

## Phase status

- [x] Phase 0 — Foundations (app factory, config, logging, errors, DB session, health, Docker, Alembic scaffold)
- [ ] Phase 1 — Data model & migrations (28 tables + seed data)
- [ ] Phase 2 — Repositories & services
- [ ] Phase 3 — REST API v1 endpoints
- [ ] Phase 4 — AI layer (engines + copilot + simulation parity)
- [ ] Phase 5 — Frontend wiring (additive only)
- [ ] Phase 6 — Mock removal & cutover
- [ ] Phase 7 — Docs & hardening
