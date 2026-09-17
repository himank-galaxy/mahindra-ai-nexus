# Docker Setup

Everything containerized in this project is defined in
[`backend/docker-compose.yml`](../backend/docker-compose.yml) plus the API
image recipe [`backend/Dockerfile`](../backend/Dockerfile).

## 1. Stack Overview

| Service | Image / build | Container name | Ports | Purpose |
|---|---|---|---|---|
| `postgres` | `postgres:16-alpine` | `mahindra-postgres` | 5432:5432 | Primary datastore |
| `api` | build from `backend/Dockerfile` | `mahindra-api` | 8000:8000 | FastAPI (production-style) |

The **development workflow** normally runs only the `postgres` service in
Docker while uvicorn + Vite run natively on the host. Running the full
compose stack (`up --build`) is the production-like path.

## 2. Installation

See [Environment_Replication_Guide.md §2.5](./Environment_Replication_Guide.md)
for the full Docker Engine + Compose plugin installation on Ubuntu. Verify:

```bash
docker --version            # 29.x+
docker compose version      # v5.x (plugin; `docker-compose` v2 syntax-compatible)
docker run --rm hello-world
```

## 3. Compose File Walkthrough

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: mahindra-postgres
    environment:
      POSTGRES_USER: mahindra
      POSTGRES_PASSWORD: mahindra      # dev default — change for any shared env
      POSTGRES_DB: mahindra_ai
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck:                        # pg_isready every 5s, 10 retries
      ...
  api:
    build: .                            # backend/Dockerfile
    depends_on:
      postgres: { condition: service_healthy }
    environment:
      DATABASE_URL: postgresql+asyncpg://mahindra:mahindra@postgres:5432/mahindra_ai
      ENVIRONMENT: development
      DEBUG: "true"
      LOG_LEVEL: INFO
      CORS_ORIGINS: http://localhost:5173,http://localhost:3000
      AI_PROVIDER: rule
    ports: ["8000:8000"]
volumes:
  pgdata:
```

### Volumes

- `pgdata` — named volume holding ALL database data. Survives `down`,
  container removal and rebuilds. Only `docker compose down -v` deletes it.
- Inspect: `docker volume ls`, `docker volume inspect backend_pgdata`
  (compose prefixes the project directory name).

### Networks

Compose creates one default bridge network per project
(`backend_default`); services resolve each other by service name — the API
reaches postgres at hostname `postgres`, NOT `localhost`.

### Environment variables

Postgres reads `POSTGRES_USER/PASSWORD/DB` only on **first init of an empty
volume**. Changing them later has no effect unless the volume is recreated.
The API service variables mirror `backend/.env.example`.

## 4. Lifecycle Commands

All commands run from the repo root (compose file lives in `backend/`):

```bash
# --- Startup ---------------------------------------------------------------
docker compose -f backend/docker-compose.yml up -d postgres      # DB only (dev)
docker compose -f backend/docker-compose.yml up -d --build       # full stack

# --- Shutdown --------------------------------------------------------------
docker compose -f backend/docker-compose.yml stop                # stop, keep everything
docker compose -f backend/docker-compose.yml down                # remove containers (volume kept)
docker compose -f backend/docker-compose.yml down -v             # ⚠ DESTROYS DATA

# --- Restart / rebuild -----------------------------------------------------
docker compose -f backend/docker-compose.yml restart api
docker compose -f backend/docker-compose.yml up -d --build api   # rebuild image after code changes
docker compose -f backend/docker-compose.yml build --no-cache api

# --- Single-container ops (when only postgres matters) ----------------------
docker start mahindra-postgres
docker stop mahindra-postgres
docker restart mahindra-postgres

# --- Logs -------------------------------------------------------------------
docker compose -f backend/docker-compose.yml logs -f postgres
docker logs -f mahindra-api --tail 100
```

## 5. The API Image (Dockerfile)

Two-stage build:

1. `builder` (`python:3.12-slim`): `pip install --prefix=/install -r requirements.txt`
2. runtime (`python:3.12-slim`): copies the install prefix, `app/`, `alembic/`,
   `scripts/`, `alembic.ini`; runs as non-root `appuser`;
   `HEALTHCHECK` polls `/health` every 30 s.

Entry: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

Note: migrations are **not** auto-run by the container. After `up --build`
on a fresh volume, apply schema + seed from the host venv (or exec into the
container):

```bash
docker compose -f backend/docker-compose.yml exec api alembic upgrade head
docker compose -f backend/docker-compose.yml exec api python scripts/seed_db.py
```

## 6. Verification

```bash
docker ps                                                   # both containers Up/healthy
docker exec mahindra-postgres pg_isready -U mahindra -d mahindra_ai
curl -s http://localhost:8000/health                        # {"status":"ok",...,"database":"up"}
bash database/scripts/verify_database.sh mahindra_ai        # full DB audit
```

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `port is already allocated` on 5432 | Host PostgreSQL running — stop it (`sudo systemctl stop postgresql`) or remap the port |
| Container starts then exits | Check `docker logs mahindra-postgres`; usually corrupt volume after hard power-off → backup, then `down -v` and re-init |
| API container unhealthy | DB not ready yet (wait for `service_healthy`) or wrong `DATABASE_URL` hostname (must be `postgres` inside compose) |
| Permission errors on Linux | User not in `docker` group — `sudo usermod -aG docker $USER` + re-login |
| Image pull slow/fails | Registry access — configure mirror in `/etc/docker/daemon.json` |
| Stale code in API container | Image cached — `up -d --build api` |

## 8. Source-Machine Quirk (Windows only)

Docker Desktop on the source machine auto-pauses idle containers; recovery is
`docker unpause mahindra-postgres`. Linux VMs do not exhibit this — after a
reboot simply `docker start mahindra-postgres` (or use compose).
