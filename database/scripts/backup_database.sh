#!/usr/bin/env bash
# =============================================================================
# backup_database.sh — Mahindra AI Nexus PostgreSQL backup helper
#
# Produces, per database, inside ./database/backups/<timestamp>/ :
#   <db>_full.dump          custom format (schema + data)  -> pg_restore
#   <db>_full.sql           plain SQL   (schema + data)    -> psql
#   <db>_schema_only.dump   custom format, schema only
#   <db>_data_only.dump     custom format, data only (--data-only)
#   <db>_row_counts.txt     per-table row counts (restore verification aid)
# Plus SHA256SUMS for every artifact.
#
# READ-ONLY against the running database (pg_dump never writes).
#
# Usage:
#   ./backup_database.sh                 # back up all DBS listed below
#   ./backup_database.sh mahindra_ai    # back up a single database
#
# Environment overrides:
#   PG_CONTAINER  (default: mahindra-postgres)
#   PG_USER       (default: mahindra)
#   BACKUP_DIR    (default: database/backups relative to repo root)
# =============================================================================
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-mahindra-postgres}"
PG_USER="${PG_USER:-mahindra}"

# Resolve repo root (script lives in <repo>/database/scripts)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/database/backups}"

DEFAULT_DBS=(mahindra_ai mahindra_ai_staging)
if [ "$#" -gt 0 ]; then
  DBS=("$@")
else
  DBS=("${DEFAULT_DBS[@]}")
fi

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="${BACKUP_DIR}/${TIMESTAMP}"
mkdir -p "${OUT_DIR}"

echo "Container : ${PG_CONTAINER}"
echo "User      : ${PG_USER}"
echo "Databases : ${DBS[*]}"
echo "Output    : ${OUT_DIR}"
echo

# Preflight: container must be running and reachable
if ! docker inspect -f '{{.State.Running}}' "${PG_CONTAINER}" 2>/dev/null | grep -q true; then
  echo "ERROR: container '${PG_CONTAINER}' is not running." >&2
  echo "Start it with: docker compose -f backend/docker-compose.yml up -d postgres" >&2
  exit 1
fi
docker exec "${PG_CONTAINER}" pg_isready -U "${PG_USER}" -q

for DB in "${DBS[@]}"; do
  # Skip databases that do not exist in this container
  if ! docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d postgres -tAc \
       "SELECT 1 FROM pg_database WHERE datname='${DB}'" | grep -q 1; then
    echo "WARN: database '${DB}' does not exist — skipping." >&2
    continue
  fi

  echo "==> Backing up ${DB}"

  # 1. Full backup — custom format (recommended for pg_restore)
  docker exec "${PG_CONTAINER}" pg_dump -U "${PG_USER}" -d "${DB}" \
    -Fc --no-owner --no-privileges > "${OUT_DIR}/${DB}_full.dump"

  # 2. Full backup — plain SQL (human readable, restorable with psql)
  docker exec "${PG_CONTAINER}" pg_dump -U "${PG_USER}" -d "${DB}" \
    --no-owner --no-privileges > "${OUT_DIR}/${DB}_full.sql"

  # 3. Schema-only backup
  docker exec "${PG_CONTAINER}" pg_dump -U "${PG_USER}" -d "${DB}" \
    -Fc --schema-only --no-owner --no-privileges > "${OUT_DIR}/${DB}_schema_only.dump"

  # 4. Data-only backup
  docker exec "${PG_CONTAINER}" pg_dump -U "${PG_USER}" -d "${DB}" \
    -Fc --data-only --no-owner --no-privileges > "${OUT_DIR}/${DB}_data_only.dump"

  # 5. Exact row counts snapshot (used later by verify_database.sh).
  #    Uses COUNT(*) via dynamic SQL — pg_stat n_live_tup is unreliable
  #    right after a server restart (stats reset).
  docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${DB}" -tA -c \
    "DO \$\$ DECLARE t TEXT; n BIGINT; BEGIN FOR t IN SELECT relname FROM pg_stat_user_tables WHERE relname <> 'alembic_version' ORDER BY 1 LOOP EXECUTE format('SELECT count(*) FROM %I', t) INTO n; RAISE NOTICE '%=%', t, n; END LOOP; END \$\$;" \
    2>&1 | sed -n 's/^NOTICE:  //p' > "${OUT_DIR}/${DB}_row_counts.txt"

  echo "    full / sql / schema-only / data-only / row-counts written."
done

# Checksums for integrity verification after transfer to the VM
cd "${OUT_DIR}"
sha256sum ./* > SHA256SUMS
echo
echo "Done. Artifacts:"
ls -lh "${OUT_DIR}"
