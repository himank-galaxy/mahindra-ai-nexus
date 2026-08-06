# Environment Replication Guide

How to recreate the **exact** Mahindra AI Nexus development environment on a
fresh Linux VM. This guide covers system requirements, software installation,
project setup (frontend, backend, database, Docker), development and
production modes, and verification steps.

> Master reference: [Project_Replication_Guide.md](./Project_Replication_Guide.md).
> Database specifics: [Database_Setup.md](./Database_Setup.md).
> Docker specifics: [Docker_Setup.md](./Docker_Setup.md).
> AI-agent continuation instructions: [AI_Agent_Handover.md](./AI_Agent_Handover.md).

---

## 1. System Requirements

| Resource | Minimum | Recommended | Notes |
|---|---|---|---|
| OS | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS | Also works on 22.04 LTS |
| CPU | 2 vCPU | 4 vCPU | Vite dev server + uvicorn + Docker |
| RAM | 4 GB | 8 GB | Bun/Vite SSR build is memory-hungry |
| Disk | 20 GB | 40 GB | Docker images (~1 GB), deps, backups |
| Arch | x86_64 | x86_64 | arm64 also works (postgres:16-alpine is multi-arch) |

### Ports

| Port | Service | Direction |
|---|---|---|
| 8080 | Frontend dev server (Vite) | Local / LAN |
| 8000 | FastAPI backend (uvicorn) | Local / LAN |
| 5432 | PostgreSQL (Docker) | Local only — **do not expose publicly** |

### Firewall (ufw)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 8080/tcp   # only if the demo must be reachable on the LAN
sudo ufw allow 8000/tcp   # only if API must be reachable on the LAN
sudo ufw enable
```

Keep **5432 closed** to the outside; PostgreSQL is only needed by the local
backend (and optionally by pgAdmin/DBeaver over an SSH tunnel).

### Network

- Outbound HTTPS (443) required: apt, npm registry, PyPI, Docker Hub, GitHub.
- No inbound requirements for pure local development.

---

## 2. Required Software & Exact Versions

Verified versions from the source machine (target these or newer-compatible):

| Software | Source version | Notes |
|---|---|---|
| Git | 2.53 | any 2.40+ fine |
| Python | 3.13.5 venv (3.12 minimum; Dockerfile uses `python:3.12-slim`) | `requires-python = ">=3.12"` |
| pip | latest | inside venv |
| venv | stdlib | |
| Node.js | v24.18.1 | 20 LTS+ fine |
| npm | 11.16 | ships with Node |
| Bun | 1.3.14 | **required** — frontend uses `bun run dev` and `bun.lock` |
| Docker Engine | 29.4 | Docker Desktop on Windows, docker-ce on Linux |
| Docker Compose | v5.1 (`docker compose` plugin) | v2 syntax-compatible |
| PostgreSQL | 16.14 **via Docker** (`postgres:16-alpine`) | no host install needed |
| Redis | **not used** | — |
| Nginx | **not used in dev** | optional for production TLS (see §8) |

### 2.1 Base packages

```bash
sudo apt update && sudo apt -y upgrade
sudo apt install -y git curl ca-certificates gnupg lsb-release build-essential
```

### 2.2 Python 3.12+

Ubuntu 24.04 ships Python 3.12:

```bash
sudo apt install -y python3 python3-venv python3-pip
python3 --version   # expect 3.12.x
```

### 2.3 Node.js (20+ / 24)

```bash
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt install -y nodejs
node --version && npm --version
```

### 2.4 Bun

```bash
curl -fsSL https://bun.sh/install | bash
exec $SHELL -l       # reload so ~/.bun/bin is on PATH
bun --version
```

### 2.5 Docker Engine + Compose plugin

```bash
# Remove any distro-packaged docker first (optional but recommended)
for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do
  sudo apt-get remove -y $pkg 2>/dev/null || true
done

sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker $USER   # run docker without sudo (re-login to apply)
newgrp docker

docker --version
docker compose version
```

### 2.6 PostgreSQL client tools (optional, host-side)

Only needed if you want `psql`/`pg_dump` directly on the VM instead of
`docker exec`. The helper scripts in `database/scripts/` use `docker exec`
and need **no** host PostgreSQL.

```bash
sudo apt install -y postgresql-client-16
```

---

## 3. Get the Repository

```bash
git clone <repository-url> mahindra-ai-nexus
cd mahindra-ai-nexus
```

If the repo was transferred as an archive instead of a git remote, unpack it
and run `git init` is NOT required — the repository already contains its git
history (initial commit `c686a1a`).

Top-level layout after clone:

```
mahindra-ai-nexus/
├── backend/     # FastAPI app, Alembic, tests, docker-compose.yml, Dockerfile
├── frontend/    # Lovable React app (TanStack Start + Vite + Tailwind 4)
├── data/        # synthetic data generators + generated CSVs
├── database/    # parquet exports + backups/ + scripts/ (backup/restore/verify)
├── docs/        # all documentation incl. this guide
└── .gitignore
```

---

## 4. Database Setup (Docker PostgreSQL)

Full details in [Database_Setup.md](./Database_Setup.md). Quick path:

```bash
# 1. Start PostgreSQL (creates volume, user mahindra/mahindra, db mahindra_ai)
docker compose -f backend/docker-compose.yml up -d postgres

# 2. Wait for healthy, then create schema + curated seed
docker compose -f backend/docker-compose.yml exec postgres pg_isready -U mahindra -d mahindra_ai
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head                # applies 0001_initial_schema
python scripts/seed_db.py           # loads curated demo data (seed_data.py)

# 3. (Optional) staging DB with synthetic data
docker compose -f backend/docker-compose.yml exec postgres \
  psql -U mahindra -d postgres -c "CREATE DATABASE mahindra_ai_staging;"
python database/seed_database.py \
  --database-url "postgresql+asyncpg://mahindra:mahindra@localhost:5432/mahindra_ai_staging" \
  --ensure-schema
```

**Faster alternative — restore the shipped backups** instead of re-seeding:

```bash
bash database/scripts/restore_database.sh database/backups/<timestamp>/mahindra_ai_full.dump
bash database/scripts/restore_database.sh database/backups/<timestamp>/mahindra_ai_staging_full.dump
bash database/scripts/verify_database.sh mahindra_ai
```

---

## 5. Backend Setup (FastAPI)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Environment file (template committed; real .env is git-ignored)
cp .env.example .env                # defaults work for local Docker
```

Key variables (all documented in `backend/.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://mahindra:mahindra@localhost:5432/mahindra_ai` | async SQLAlchemy URL |
| `ENVIRONMENT` / `DEBUG` / `LOG_LEVEL` | development / true / INFO | runtime behaviour |
| `CORS_ORIGINS` | localhost:5173,3000,8080 | frontend origins allowed |
| `AI_PROVIDER` | `rule` | `rule` = deterministic in-repo AI, `openai` = LLM |
| `OPENAI_API_KEY` | empty | only when `AI_PROVIDER=openai` |
| `DB_POOL_*` | 10/20/30/1800 | asyncpg pool tuning |

> **Current production-behaviour note:** on the source machine the backend
> points at the synthetic staging DB via `backend/.env`
> (`DATABASE_URL=…/mahindra_ai_staging`). To replicate that, change only the
> database name in `.env`. Do NOT commit `.env`.

### Run (development)

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
# health check: curl http://localhost:8000/health
```

### Tests / quality

```bash
pytest                    # asyncio_mode=auto, tests/ dir
ruff check .
mypy app
```

### Run (production-style, Docker)

```bash
docker compose -f backend/docker-compose.yml up --build
# builds the API image (python:3.12-slim, non-root) + postgres
```

---

## 6. Frontend Setup (Lovable React)

```bash
cd frontend
bun install               # honours bun.lock — use bun, not npm install
cp .env.example .env.local  # VITE_API_BASE_URL=http://localhost:8000/api/v1
```

### Run (development)

```bash
bun run dev -- --port 8080 --host
# serves http://localhost:8080  (SSR via TanStack Start + nitro)
```

### Build (production)

```bash
bun run build             # nitro build (default target: cloudflare)
bun run preview
```

The frontend is **API-only**: it renders nothing from local mock files in
production mode — every screen fetches from `VITE_API_BASE_URL`.

---

## 7. Synthetic Data Pipeline (optional but recommended)

```bash
# CSVs are already committed under data/synthetic/. Regenerate deterministically:
cd data/generators
python3 -m venv ../../backend/.venv >/dev/null 2>&1 || true   # reuse backend venv
# Faker is required:
pip install faker       # into backend venv
python run_all.py       # writes data/synthetic/*.csv (deterministic seed 20260806)

# Load into any fresh database:
python backend/database/seed_database.py \
  --database-url "postgresql+asyncpg://mahindra:mahindra@localhost:5432/<fresh_db>" \
  --ensure-schema
```

See [Synthetic_Data_Generation.md](./Synthetic_Data_Generation.md) and
[Seeding_Guide.md](./Seeding_Guide.md).

---

## 8. Development vs Production Mode

### Development workflow (what the source machine runs)

| Process | Command | Port |
|---|---|---|
| PostgreSQL | `docker compose -f backend/docker-compose.yml up -d postgres` | 5432 |
| Backend | `uvicorn app.main:app --host 0.0.0.0 --port 8000` (venv active) | 8000 |
| Frontend | `bun run dev -- --port 8080 --host` | 8080 |

### Production mode

There is no single "production deploy" wired yet. The two sanctioned paths:

1. **Docker Compose**: `docker compose -f backend/docker-compose.yml up --build`
   (postgres + API containers). Frontend still needs a host (Vercel/Cloudflare
   via its nitro target, or any static/Node host running `bun run build`).
2. **Reverse proxy** (optional): put nginx in front for TLS:

```nginx
server {
    listen 443 ssl http2;
    server_name nexus.example.com;

    location / {
        proxy_pass http://127.0.0.1:8080;   # frontend
        proxy_set_header Host $host;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:8000;   # FastAPI
        proxy_set_header Host $host;
    }
    location /health {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

Adjust `CORS_ORIGINS` and `VITE_API_BASE_URL` to the public origin.

---

## 9. Verification Steps (run in order)

```bash
# 1. Container + DB
docker ps                                        # mahindra-postgres healthy
docker exec mahindra-postgres pg_isready -U mahindra -d mahindra_ai

# 2. Backend
curl -s http://localhost:8000/health
#    expect: {"status":"ok",..., "database":"up"}
curl -s http://localhost:8000/api/v1/dealers | head -c 300

# 3. Database verification helper
bash database/scripts/verify_database.sh mahindra_ai
bash database/scripts/verify_database.sh mahindra_ai_staging

# 4. Frontend
curl -sI http://localhost:8080 | head -1        # expect HTTP/1.1 200
# open http://<vm-ip>:8080 and click through: Overview, Dealer, Finance,
# Collections, Logistics, Circularity, Trust, Catalogue, Agents,
# Mobility Twin, Simulation, XR, Copilot — every screen must render data.

# 5. Backend test suite
cd backend && pytest -q
```

Expected reference numbers after a restore/seed:

| Database | Tables | Rows | Notes |
|---|---|---|---|
| `mahindra_ai` | 31 | 203 | curated demo data, alembic_version=0001 |
| `mahindra_ai_staging` | 30 | 549+ | synthetic seed (no alembic_version; create_all) |

---

## 10. Startup Sequence (every boot)

```bash
docker start mahindra-postgres        # or: docker compose -f backend/docker-compose.yml up -d postgres
cd backend && source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
cd ../frontend && bun run dev -- --port 8080 --host
```

On the Windows source machine Docker Desktop sometimes **pauses** idle
containers — the equivalent recovery is `docker unpause mahindra-postgres`.
On Linux this does not happen; containers simply stop on reboot and need
`docker start`.
