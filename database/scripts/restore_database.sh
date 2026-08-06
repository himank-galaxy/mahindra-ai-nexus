#!/usr/bin/env bash
# =============================================================================
# restore_database.sh — Mahindra AI Nexus PostgreSQL restore helper
#
# Restores a dump produced by backup_database.sh into the Docker container.
#
# Usage:
#   ./restore_database.sh <dump_file> [target_db]
#
# Examples:
#   # Full restore (schema + data) into a NEW database (safe, default keeps names)
#   ./restore_database.sh database/backups/20260806_120000/mahindra_ai_full.dump
#
#   # Restore into an explicitly named database
#   ./restore_database.sh .../mahindra_ai_full.dump mahindra_ai_restored
#
#   # Restore schema-only or data-only artifacts the same way
#   ./restore_database.sh .../mahindra_ai_schema_only.dump mahindra_ai_schema
#
# Behaviour:
#   - Target DB name defaults to the name embedded in the dump filename
#     (e.g. mahindra_ai_full.dump -> mahindra_ai).
#   - If the target database already exists the script REFUSES to overwrite
#     it unless DROP_EXISTING=true is set. This protects live data.
#   - For *_data_only.dump targets, the schema must already exist in the
#     target database (run Alembic or the schema-only dump first).
#
# Environment overrides:
#   PG_CONTAINER     (default: mahindra-postgres)
#   PG_USER          (default: mahindra)
#   DROP_EXISTING    (default: false) — set to true to drop+recreate target
# =============================================================================
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-mahindra-postgres}"
PG_USER="${PG_USER:-mahindra}"
DROP_EXISTING="${DROP_EXISTING:-false}"

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <dump_file> [target_db]" >&2
  exit 2
fi

DUMP_FILE="$1"
if [ ! -f "${DUMP_FILE}" ]; then
  echo "ERROR: dump file not found: ${DUMP_FILE}" >&2
  exit 1
fi

# Derive default target db from filename: <db>_full.dump / <db>_schema_only.dump ...
BASE="$(basename "${DUMP_FILE}")"
DEFAULT_DB="${BASE%%_full.dump}"
DEFAULT_DB="${DEFAULT_DB%%_schema_only.dump}"
DEFAULT_DB="${DEFAULT_DB%%_data_only.dump}"
DEFAULT_DB="${DEFAULT_DB%%.dump}"
TARGET_DB="${2:-${DEFAULT_DB}}"

echo "Dump      : ${DUMP_FILE}"
echo "Target DB : ${TARGET_DB}"
echo "Container : ${PG_CONTAINER}"
echo

# Preflight
docker inspect -f '{{.State.Running}}' "${PG_CONTAINER}" 2>/dev/null | grep -q true || {
  echo "ERROR: container '${PG_CONTAINER}' is not running." >&2
  exit 1
}

EXISTS="$(docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='${TARGET_DB}'")"

if [ "${EXISTS}" = "1" ]; then
  if [ "${DROP_EXISTING}" != "true" ]; then
    echo "ERROR: database '${TARGET_DB}' already exists." >&2
    echo "Refusing to overwrite. Re-run with DROP_EXISTING=true to drop+recreate," >&2
    echo "or choose a different target: $0 ${DUMP_FILE} some_other_db" >&2
    exit 1
  fi
  echo "Dropping existing database '${TARGET_DB}' (DROP_EXISTING=true)..."
  docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d postgres -c \
    "DROP DATABASE \"${TARGET_DB}\";"
fi

echo "Creating database '${TARGET_DB}'..."
docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d postgres -c \
  "CREATE DATABASE \"${TARGET_DB}\";"

echo "Restoring dump (this may take a while)..."
docker exec -i "${PG_CONTAINER}" pg_restore -U "${PG_USER}" -d "${TARGET_DB}" \
  --no-owner --no-privileges --exit-on-error < "${DUMP_FILE}"

echo
echo "Restore complete. Verify with:"
echo "  ./verify_database.sh ${TARGET_DB}"
