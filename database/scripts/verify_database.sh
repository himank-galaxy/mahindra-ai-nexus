#!/usr/bin/env bash
# =============================================================================
# verify_database.sh — Mahindra AI Nexus restore verification helper
#
# READ-ONLY checks against a database inside the Docker container:
#   1. Connectivity + server version
#   2. Alembic migration state (alembic_version table)
#   3. Table inventory + per-table row counts
#   4. Optional comparison against a saved <db>_row_counts.txt snapshot
#   5. Foreign-key integrity scan (orphaned references)
#   6. Enum type inventory
#
# Usage:
#   ./verify_database.sh                       # verifies mahindra_ai
#   ./verify_database.sh mahindra_ai_staging   # verifies another DB
#   ./verify_database.sh mahindra_ai database/backups/20260806_120000/mahindra_ai_row_counts.txt
#
# Environment overrides:
#   PG_CONTAINER  (default: mahindra-postgres)
#   PG_USER       (default: mahindra)
# =============================================================================
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-mahindra-postgres}"
PG_USER="${PG_USER:-mahindra}"
TARGET_DB="${1:-mahindra_ai}"
SNAPSHOT="${2:-}"

echo "=== Verification: ${TARGET_DB} @ ${PG_CONTAINER} ==="
echo

# 1. Connectivity
echo "--- 1. Connectivity / version ---"
docker exec "${PG_CONTAINER}" pg_isready -U "${PG_USER}" -d "${TARGET_DB}"
docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${TARGET_DB}" -tAc "SELECT version();"
echo

# 2. Alembic state
echo "--- 2. Alembic migration state ---"
ALEMBIC="$(docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${TARGET_DB}" -tAc \
  "SELECT version_num FROM alembic_version" 2>/dev/null || true)"
if [ -n "${ALEMBIC}" ]; then
  echo "alembic_version = ${ALEMBIC}"
else
  echo "WARN: no alembic_version table (schema may have been created via create_all)."
fi
echo

# 3. Tables + exact row counts (COUNT(*) per table; stats-safe after restarts)
echo "--- 3. Tables + row counts ---"
COUNTS="$(docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${TARGET_DB}" -tA -c \
  "DO \$\$ DECLARE t TEXT; n BIGINT; BEGIN FOR t IN SELECT relname FROM pg_stat_user_tables WHERE relname <> 'alembic_version' ORDER BY 1 LOOP EXECUTE format('SELECT count(*) FROM %I', t) INTO n; RAISE NOTICE '%=%', t, n; END LOOP; END \$\$;" 2>&1 \
  | sed -n 's/^NOTICE:  //p')"
echo "${COUNTS}"
TABLE_TOTAL="$(docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${TARGET_DB}" -tAc \
  "SELECT count(*) FROM pg_stat_user_tables;")"
ROW_TOTAL="$(echo "${COUNTS}" | awk -F= '{s+=$2} END {print s+0}')"
echo "--> ${TABLE_TOTAL} tables, ${ROW_TOTAL} rows total"
echo

# 4. Snapshot comparison
if [ -n "${SNAPSHOT}" ]; then
  echo "--- 4. Comparison against snapshot ${SNAPSHOT} ---"
  if [ ! -f "${SNAPSHOT}" ]; then
    echo "ERROR: snapshot not found: ${SNAPSHOT}" >&2
    exit 1
  fi
  if diff <(sort "${SNAPSHOT}") <(echo "${COUNTS}" | sort); then
    echo "MATCH: row counts identical to backup snapshot."
  else
    echo "DIFFERENCE detected (see diff above). Row counts can legitimately"
    echo "differ from n_live_tup estimates; run ANALYZE and re-check if unsure."
  fi
  echo
fi

# 5. FK integrity — orphaned child rows (checks all declared FK constraints)
echo "--- 5. Foreign-key integrity ---"
ORPHANS="$(docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${TARGET_DB}" -tA -c "
  DO \$\$
  DECLARE r RECORD; bad BIGINT; total BIGINT := 0;
  BEGIN
    FOR r IN
      SELECT tc.table_name AS child, kcu.column_name AS child_col,
             ccu.table_name AS parent, ccu.column_name AS parent_col
      FROM information_schema.table_constraints tc
      JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name
      JOIN information_schema.constraint_column_usage ccu
        ON tc.constraint_name = ccu.constraint_name
      WHERE tc.constraint_type = 'FOREIGN KEY'
    LOOP
      EXECUTE format('SELECT count(*) FROM %I c LEFT JOIN %I p ON c.%I = p.%I WHERE c.%I IS NOT NULL AND p.%I IS NULL',
                     r.child, r.parent, r.child_col, r.parent_col, r.child_col, r.parent_col) INTO bad;
      IF bad > 0 THEN
        RAISE NOTICE 'ORPHANS: %.% -> %.% : %', r.child, r.child_col, r.parent, r.parent_col, bad;
        total := total + bad;
      END IF;
    END LOOP;
    RAISE NOTICE 'FK check complete, % orphaned rows', total;
  END \$\$;" 2>&1 | grep -E 'ORPHANS|FK check' || true)"
echo "${ORPHANS}"
echo

# 6. Enum types
echo "--- 6. Enum types ---"
docker exec "${PG_CONTAINER}" psql -U "${PG_USER}" -d "${TARGET_DB}" -tAc \
  "SELECT t.typname FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid GROUP BY t.typname ORDER BY 1;"
echo
echo "=== Verification finished ==="
