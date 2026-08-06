# database/backups/

Point-in-time PostgreSQL dumps produced by `database/scripts/backup_database.sh`.

Layout: one folder per run, named `<YYYYMMDD_HHMMSS>`:

```
<timestamp>/
├── <db>_full.dump            pg_dump -Fc (schema + data)        -> pg_restore
├── <db>_full.sql             pg_dump plain SQL (schema + data)  -> psql
├── <db>_schema_only.dump     DDL only
├── <db>_data_only.dump       rows only (schema must pre-exist)
├── <db>_row_counts.txt       exact COUNT(*) per table
└── SHA256SUMS                checksums of every artifact above
```

## Usage

```bash
# Create a fresh backup set (read-only against the running database)
bash database/scripts/backup_database.sh

# Restore into the Docker container (refuses to overwrite existing DBs)
bash database/scripts/restore_database.sh <timestamp>/mahindra_ai_full.dump

# Verify a database, optionally against a saved row-count snapshot
bash database/scripts/verify_database.sh mahindra_ai <timestamp>/mahindra_ai_row_counts.txt

# Integrity check after transferring backups to another machine
cd <timestamp> && sha256sum -c SHA256SUMS
```

Full documentation: `docs/Database_Setup.md`.

## Retention policy (manual)

There is no automatic pruning. After confirming a newer backup verifies
cleanly, older timestamped folders may be deleted. Keep at least one
verified full backup of **each** database (`mahindra_ai`,
`mahindra_ai_staging`) in the repository at all times.

## Shipped baseline

The folder committed with the repository contains the baseline backup taken
on the source machine (Windows, Docker Desktop, PostgreSQL 16.14) on
2026-08-06 — sufficient to reproduce both databases exactly on a fresh VM.
