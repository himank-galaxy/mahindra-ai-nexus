"""Deterministic PostgreSQL importer for the Mahindra AI Nexus data factory.

Responsibilities
----------------
1. Read ``data/dataset_manifest.json``.
2. Validate all 50 runtime CSV artifacts before touching PostgreSQL.
3. Explicitly exclude all evaluator ground-truth datasets.
4. Verify the PostgreSQL runtime schema contract:
   - Alembic revision ``runtime_0001``
   - exactly 50 runtime tables
   - exactly 50 primary keys
   - exactly 205 foreign keys
   - exact runtime table names
   - exact CSV/database column contracts
   - exact primary-key contracts
5. Derive an FK-safe import order from PostgreSQL metadata.
6. COPY each CSV into a temporary staging table.
7. Idempotently UPSERT current rows in FK-safe forward order.
8. Avoid rewriting rows whose values are already identical.
9. Delete stale target rows in reverse FK order.
10. Verify exact target row counts before transaction commit.
11. Roll back the complete import if any table fails.
12. Never import evaluator ground truth.

The importer intentionally does not create or migrate tables.
Alembic owns schema creation; this script owns runtime data loading.

Recommended execution environment
---------------------------------
    backend/.venv-linux/bin/python -m data.scripts.import_postgres --dry-run

Then, after validation:

    backend/.venv-linux/bin/python -m data.scripts.import_postgres
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg


# ---------------------------------------------------------------------------
# Static runtime contract
# ---------------------------------------------------------------------------

EXPECTED_ALEMBIC_REVISION = "runtime_0003"

EXPECTED_TOTAL_DATASETS = 58
EXPECTED_RUNTIME_DATASETS = 51
EXPECTED_GROUND_TRUTH_DATASETS = 7

EXPECTED_RUNTIME_TABLES = 51
EXPECTED_PRIMARY_KEYS = 51
EXPECTED_FOREIGN_KEYS = 210

ADVISORY_LOCK_NAME = "mahindra_ai_runtime_synthetic_import_v1"

DEFAULT_DATABASE_URL = (
    "postgresql://mahindra:mahindra@127.0.0.1:5432/mahindra_ai"
)


# ---------------------------------------------------------------------------
# Repository paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_MANIFEST_PATH = (
    REPO_ROOT
    / "data"
    / "dataset_manifest.json"
)

SYNTHETIC_ROOT = (
    REPO_ROOT
    / "data"
    / "synthetic"
).resolve()


# ---------------------------------------------------------------------------
# Validated PK contract
# ---------------------------------------------------------------------------

COMPOSITE_PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "manufacturing_timeseries": (
        "timestamp",
        "machine_id",
    ),
    "mobility_timeseries": (
        "region_id",
        "window_start",
    ),
    "vehicle_telematics_timeseries": (
        "timestamp",
        "vehicle_id",
    ),
}


# ---------------------------------------------------------------------------
# CSV configuration
# ---------------------------------------------------------------------------

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    # Some platforms expose a C-long smaller than Python's sys.maxsize.
    csv.field_size_limit(2**31 - 1)


# ---------------------------------------------------------------------------
# Exceptions / data classes
# ---------------------------------------------------------------------------


class ImportContractError(RuntimeError):
    """Raised when data or database state violates the import contract."""


@dataclass(frozen=True)
class DatasetSpec:
    """One runtime dataset declared by the deterministic manifest."""

    logical_path: str
    table_name: str
    csv_path: Path
    rows: int
    sha256: str
    bytes: int
    columns: tuple[str, ...]


@dataclass(frozen=True)
class ManifestContract:
    """Validated runtime/evaluator split extracted from the manifest."""

    runtime: tuple[DatasetSpec, ...]
    runtime_rows: int
    total_datasets: int
    ground_truth_datasets: int
    registry_sha256: str | None


@dataclass(frozen=True)
class DatabaseContract:
    """Runtime schema information retrieved from PostgreSQL."""

    database: str
    user: str
    revision: str
    table_names: tuple[str, ...]
    primary_keys: dict[str, tuple[str, ...]]
    columns: dict[str, tuple[str, ...]]
    foreign_key_count: int
    dependency_order: tuple[str, ...]
    existing_rows: dict[str, int]


@dataclass(frozen=True)
class ImportResult:
    """Summary for one committed exact-snapshot synchronization."""

    changed_rows: dict[str, int]
    deleted_rows: dict[str, int]
    final_rows: dict[str, int]


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def quote_identifier(value: str) -> str:
    """Safely quote a PostgreSQL identifier."""

    return '"' + value.replace('"', '""') + '"'


def normalize_database_url(url: str) -> str:
    """Convert SQLAlchemy async URLs into asyncpg-compatible DSNs."""

    value = url.strip()

    if value.startswith("postgresql+asyncpg://"):
        return (
            "postgresql://"
            + value[len("postgresql+asyncpg://") :]
        )

    if value.startswith("postgres://"):
        return (
            "postgresql://"
            + value[len("postgres://") :]
        )

    return value


def resolve_database_url(cli_value: str | None) -> str:
    """Resolve database URL without requiring backend application imports."""

    raw = (
        cli_value
        or os.getenv("MAHINDRA_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )

    return normalize_database_url(raw)


def manifest_field(
    item: dict[str, Any],
    *names: str,
) -> Any:
    """Return the first available manifest field from a set of aliases."""

    for name in names:
        if name in item:
            return item[name]

    raise ImportContractError(
        "Manifest entry is missing required field. "
        f"Expected one of: {names}"
    )


def sha256_file(path: Path) -> str:
    """Return deterministic SHA-256 for a file."""

    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def expected_primary_key(
    spec: DatasetSpec,
) -> tuple[str, ...]:
    """Return the validated PK contract for one runtime table."""

    if spec.table_name in COMPOSITE_PRIMARY_KEYS:
        return COMPOSITE_PRIMARY_KEYS[
            spec.table_name
        ]

    id_columns = [
        column
        for column in spec.columns
        if column.endswith("_id")
    ]

    if not id_columns:
        raise ImportContractError(
            "Unable to derive validated primary key for "
            f"{spec.table_name}"
        )

    return (id_columns[0],)


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------


def load_manifest(
    manifest_path: Path,
) -> ManifestContract:
    """Load and validate the deterministic dataset manifest."""

    manifest_path = manifest_path.resolve()

    if not manifest_path.exists():
        raise ImportContractError(
            f"Manifest does not exist: {manifest_path}"
        )

    try:
        payload = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError as exc:
        raise ImportContractError(
            f"Invalid JSON manifest: {manifest_path}"
        ) from exc

    datasets = payload.get("datasets")

    if not isinstance(datasets, list):
        raise ImportContractError(
            "Manifest must contain a 'datasets' list."
        )

    if len(datasets) != EXPECTED_TOTAL_DATASETS:
        raise ImportContractError(
            "Dataset count mismatch: "
            f"expected={EXPECTED_TOTAL_DATASETS}, "
            f"actual={len(datasets)}"
        )

    runtime_entries: list[dict[str, Any]] = []
    ground_truth_entries: list[dict[str, Any]] = []

    unexpected_paths: list[str] = []

    for item in datasets:
        if not isinstance(item, dict):
            raise ImportContractError(
                "Every manifest dataset entry must be an object."
            )

        logical_path = str(
            manifest_field(
                item,
                "logical_path",
            )
        )

        if logical_path.startswith("synthetic/"):
            runtime_entries.append(item)

        elif logical_path.startswith("ground_truth/"):
            ground_truth_entries.append(item)

        else:
            unexpected_paths.append(
                logical_path
            )

    if unexpected_paths:
        raise ImportContractError(
            "Manifest contains datasets outside the allowed "
            "synthetic/ and ground_truth/ roots: "
            f"{unexpected_paths}"
        )

    if len(runtime_entries) != EXPECTED_RUNTIME_DATASETS:
        raise ImportContractError(
            "Runtime dataset count mismatch: "
            f"expected={EXPECTED_RUNTIME_DATASETS}, "
            f"actual={len(runtime_entries)}"
        )

    if (
        len(ground_truth_entries)
        != EXPECTED_GROUND_TRUTH_DATASETS
    ):
        raise ImportContractError(
            "Ground-truth dataset count mismatch: "
            f"expected={EXPECTED_GROUND_TRUTH_DATASETS}, "
            f"actual={len(ground_truth_entries)}"
        )

    specs: list[DatasetSpec] = []

    seen_logical_paths: set[str] = set()
    seen_tables: set[str] = set()
    seen_files: set[Path] = set()

    for item in sorted(
        runtime_entries,
        key=lambda entry: str(
            entry["logical_path"]
        ),
    ):
        logical_path = str(
            manifest_field(
                item,
                "logical_path",
            )
        )

        table_name = logical_path.rsplit(
            "/",
            1,
        )[-1]

        file_value = str(
            manifest_field(
                item,
                "file",
            )
        )

        candidate = Path(file_value)

        if candidate.is_absolute():
            csv_path = candidate.resolve()
        else:
            csv_path = (
                REPO_ROOT
                / candidate
            ).resolve()

        if not csv_path.is_relative_to(
            SYNTHETIC_ROOT
        ):
            raise ImportContractError(
                "Runtime CSV escaped data/synthetic: "
                f"{logical_path} -> {csv_path}"
            )

        rows = int(
            manifest_field(
                item,
                "rows",
            )
        )

        expected_bytes = int(
            manifest_field(
                item,
                "bytes",
                "size_bytes",
            )
        )

        expected_sha256 = str(
            manifest_field(
                item,
                "sha256",
                "sha_256",
                "sha256_hex",
            )
        ).lower()

        raw_columns = manifest_field(
            item,
            "column_names",
        )

        if not isinstance(raw_columns, list):
            raise ImportContractError(
                f"{logical_path}: column_names must be a list."
            )

        columns = tuple(
            str(column)
            for column in raw_columns
        )

        declared_column_count = item.get(
            "columns"
        )

        if (
            declared_column_count is not None
            and int(declared_column_count)
            != len(columns)
        ):
            raise ImportContractError(
                f"{logical_path}: manifest column count mismatch."
            )

        if not columns:
            raise ImportContractError(
                f"{logical_path}: dataset has no columns."
            )

        if logical_path in seen_logical_paths:
            raise ImportContractError(
                "Duplicate runtime logical path: "
                f"{logical_path}"
            )

        if table_name in seen_tables:
            raise ImportContractError(
                "Duplicate PostgreSQL table mapping: "
                f"{table_name}"
            )

        if csv_path in seen_files:
            raise ImportContractError(
                "Multiple datasets map to the same CSV file: "
                f"{csv_path}"
            )

        seen_logical_paths.add(
            logical_path
        )
        seen_tables.add(
            table_name
        )
        seen_files.add(
            csv_path
        )

        specs.append(
            DatasetSpec(
                logical_path=logical_path,
                table_name=table_name,
                csv_path=csv_path,
                rows=rows,
                sha256=expected_sha256,
                bytes=expected_bytes,
                columns=columns,
            )
        )

    runtime_rows = sum(
        spec.rows
        for spec in specs
    )

    registry_sha256 = (
        payload.get("registry_sha256")
        or payload.get("registry_sha_256")
    )

    if registry_sha256 is not None:
        registry_sha256 = str(
            registry_sha256
        )

    return ManifestContract(
        runtime=tuple(specs),
        runtime_rows=runtime_rows,
        total_datasets=len(datasets),
        ground_truth_datasets=len(
            ground_truth_entries
        ),
        registry_sha256=registry_sha256,
    )


# ---------------------------------------------------------------------------
# Physical CSV validation
# ---------------------------------------------------------------------------


def validate_csv_artifact(
    spec: DatasetSpec,
) -> None:
    """Validate one physical runtime CSV against the manifest."""

    if not spec.csv_path.exists():
        raise ImportContractError(
            f"Missing CSV: {spec.csv_path}"
        )

    if not spec.csv_path.is_file():
        raise ImportContractError(
            f"CSV path is not a file: {spec.csv_path}"
        )

    actual_bytes = (
        spec.csv_path.stat().st_size
    )

    if actual_bytes != spec.bytes:
        raise ImportContractError(
            f"{spec.logical_path}: byte-size mismatch: "
            f"manifest={spec.bytes}, actual={actual_bytes}"
        )

    actual_sha256 = sha256_file(
        spec.csv_path
    )

    if actual_sha256.lower() != spec.sha256.lower():
        raise ImportContractError(
            f"{spec.logical_path}: SHA-256 mismatch: "
            f"manifest={spec.sha256}, "
            f"actual={actual_sha256}"
        )

    with spec.csv_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.reader(
            handle
        )

        try:
            header = next(
                reader
            )
        except StopIteration as exc:
            raise ImportContractError(
                f"{spec.logical_path}: empty CSV."
            ) from exc

        if tuple(header) != spec.columns:
            raise ImportContractError(
                f"{spec.logical_path}: CSV header mismatch."
            )

        actual_rows = sum(
            1
            for _ in reader
        )

    if actual_rows != spec.rows:
        raise ImportContractError(
            f"{spec.logical_path}: CSV row-count mismatch: "
            f"manifest={spec.rows}, actual={actual_rows}"
        )


def validate_runtime_artifacts(
    contract: ManifestContract,
) -> None:
    """Validate all 51 runtime artifacts before database access."""

    print()
    print("=" * 76)
    print("POSTGRES IMPORT - VALIDATING RUNTIME CSV ARTIFACTS")
    print("=" * 76)

    total = len(
        contract.runtime
    )

    for index, spec in enumerate(
        contract.runtime,
        start=1,
    ):
        validate_csv_artifact(
            spec
        )

        print(
            f"[{index:02d}/{total:02d}] PASS "
            f"{spec.logical_path:<58} "
            f"rows={spec.rows:>7}"
        )

    print()
    print(
        "Runtime CSV artifact validation: PASS"
    )


# ---------------------------------------------------------------------------
# PostgreSQL introspection
# ---------------------------------------------------------------------------


async def read_primary_keys(
    conn: asyncpg.Connection,
) -> dict[str, tuple[str, ...]]:
    """Read public-schema primary keys in ordinal order."""

    records = await conn.fetch(
        """
        SELECT
            tc.table_name,
            kcu.column_name,
            kcu.ordinal_position
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.constraint_schema = kcu.constraint_schema
        WHERE tc.table_schema = 'public'
          AND tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_name <> 'alembic_version'
        ORDER BY
            tc.table_name,
            kcu.ordinal_position
        """
    )

    grouped: dict[
        str,
        list[tuple[int, str]],
    ] = {}

    for record in records:
        grouped.setdefault(
            str(record["table_name"]),
            [],
        ).append(
            (
                int(
                    record["ordinal_position"]
                ),
                str(
                    record["column_name"]
                ),
            )
        )

    return {
        table_name: tuple(
            column
            for _, column in sorted(
                values
            )
        )
        for table_name, values
        in grouped.items()
    }


async def read_table_columns(
    conn: asyncpg.Connection,
) -> dict[str, tuple[str, ...]]:
    """Read public runtime columns in physical ordinal order."""

    records = await conn.fetch(
        """
        SELECT
            table_name,
            column_name,
            ordinal_position
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name <> 'alembic_version'
        ORDER BY
            table_name,
            ordinal_position
        """
    )

    grouped: dict[
        str,
        list[tuple[int, str]],
    ] = {}

    for record in records:
        grouped.setdefault(
            str(record["table_name"]),
            [],
        ).append(
            (
                int(
                    record["ordinal_position"]
                ),
                str(
                    record["column_name"]
                ),
            )
        )

    return {
        table_name: tuple(
            column
            for _, column in sorted(
                values
            )
        )
        for table_name, values
        in grouped.items()
    }


async def read_fk_dependencies(
    conn: asyncpg.Connection,
) -> tuple[
    int,
    dict[str, set[str]],
]:
    """Read FK count and child->parent table dependencies."""

    records = await conn.fetch(
        """
        SELECT
            tc.table_name AS child_table,
            ccu.table_name AS parent_table
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.constraint_schema = tc.constraint_schema
        WHERE tc.table_schema = 'public'
          AND tc.constraint_type = 'FOREIGN KEY'
        ORDER BY
            tc.table_name,
            ccu.table_name,
            tc.constraint_name
        """
    )

    dependencies: dict[
        str,
        set[str],
    ] = {}

    for record in records:
        child = str(
            record["child_table"]
        )
        parent = str(
            record["parent_table"]
        )

        dependencies.setdefault(
            child,
            set(),
        ).add(
            parent
        )

    return (
        len(records),
        dependencies,
    )


async def read_table_counts(
    conn: asyncpg.Connection,
    table_names: tuple[str, ...],
) -> dict[str, int]:
    """Read exact row counts for all runtime tables."""

    result: dict[
        str,
        int,
    ] = {}

    for table_name in table_names:
        count = await conn.fetchval(
            "SELECT COUNT(*)::bigint "
            f"FROM public.{quote_identifier(table_name)}"
        )

        result[
            table_name
        ] = int(
            count
        )

    return result


# ---------------------------------------------------------------------------
# FK topological ordering
# ---------------------------------------------------------------------------


def build_dependency_order(
    table_names: set[str],
    dependencies: dict[str, set[str]],
) -> tuple[str, ...]:
    """Topologically sort runtime tables by FK dependency."""

    graph: dict[
        str,
        set[str],
    ] = {
        table_name: set()
        for table_name in table_names
    }

    for child, parents in dependencies.items():
        if child not in table_names:
            raise ImportContractError(
                "FK child is outside runtime table set: "
                f"{child}"
            )

        for parent in parents:
            if parent not in table_names:
                raise ImportContractError(
                    "FK parent is outside runtime table set: "
                    f"{child} -> {parent}"
                )

            if child == parent:
                continue

            graph[
                child
            ].add(
                parent
            )

    order: list[str] = []

    remaining = {
        table_name: set(parents)
        for table_name, parents
        in graph.items()
    }

    while remaining:
        ready = sorted(
            table_name
            for table_name, parents
            in remaining.items()
            if not parents
        )

        if not ready:
            cycle_description = {
                table_name: sorted(
                    parents
                )
                for table_name, parents
                in remaining.items()
            }

            raise ImportContractError(
                "Runtime FK dependency cycle detected: "
                f"{cycle_description}"
            )

        for table_name in ready:
            order.append(
                table_name
            )

            remaining.pop(
                table_name
            )

        ready_set = set(
            ready
        )

        for parents in remaining.values():
            parents.difference_update(
                ready_set
            )

    if len(order) != len(table_names):
        raise ImportContractError(
            "Topological import order does not cover "
            "all runtime tables."
        )

    return tuple(
        order
    )


# ---------------------------------------------------------------------------
# Database preflight
# ---------------------------------------------------------------------------


async def validate_database_contract(
    conn: asyncpg.Connection,
    manifest: ManifestContract,
) -> DatabaseContract:
    """Validate the physical PostgreSQL schema before data loading."""

    database = str(
        await conn.fetchval(
            "SELECT current_database()"
        )
    )

    user = str(
        await conn.fetchval(
            "SELECT current_user"
        )
    )

    revision = await conn.fetchval(
        """
        SELECT version_num
        FROM alembic_version
        """
    )

    if revision is None:
        raise ImportContractError(
            "Database has no Alembic revision."
        )

    revision = str(
        revision
    )

    if revision != EXPECTED_ALEMBIC_REVISION:
        raise ImportContractError(
            "Alembic revision mismatch: "
            f"expected={EXPECTED_ALEMBIC_REVISION}, "
            f"actual={revision}"
        )

    table_records = await conn.fetch(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
          AND table_name <> 'alembic_version'
        ORDER BY table_name
        """
    )

    database_tables = tuple(
        str(
            record["table_name"]
        )
        for record in table_records
    )

    if (
        len(database_tables)
        != EXPECTED_RUNTIME_TABLES
    ):
        raise ImportContractError(
            "Runtime table count mismatch: "
            f"expected={EXPECTED_RUNTIME_TABLES}, "
            f"actual={len(database_tables)}"
        )

    expected_tables = {
        spec.table_name
        for spec in manifest.runtime
    }

    actual_tables = set(
        database_tables
    )

    missing_tables = sorted(
        expected_tables
        - actual_tables
    )

    unexpected_tables = sorted(
        actual_tables
        - expected_tables
    )

    if missing_tables or unexpected_tables:
        raise ImportContractError(
            "Runtime table-set mismatch. "
            f"missing={missing_tables}, "
            f"unexpected={unexpected_tables}"
        )

    database_columns = await read_table_columns(
        conn
    )

    for spec in manifest.runtime:
        actual_columns = database_columns.get(
            spec.table_name
        )

        if actual_columns is None:
            raise ImportContractError(
                "Missing database column metadata for "
                f"{spec.table_name}"
            )

        if actual_columns != spec.columns:
            raise ImportContractError(
                f"{spec.table_name}: database/CSV column mismatch.\n"
                f"expected={spec.columns}\n"
                f"actual={actual_columns}"
            )

    primary_keys = await read_primary_keys(
        conn
    )

    if (
        len(primary_keys)
        != EXPECTED_PRIMARY_KEYS
    ):
        raise ImportContractError(
            "Primary-key count mismatch: "
            f"expected={EXPECTED_PRIMARY_KEYS}, "
            f"actual={len(primary_keys)}"
        )

    for spec in manifest.runtime:
        expected_pk = expected_primary_key(
            spec
        )

        actual_pk = primary_keys.get(
            spec.table_name
        )

        if actual_pk != expected_pk:
            raise ImportContractError(
                f"{spec.table_name}: PK mismatch: "
                f"expected={expected_pk}, actual={actual_pk}"
            )

    (
        foreign_key_count,
        dependencies,
    ) = await read_fk_dependencies(
        conn
    )

    if (
        foreign_key_count
        != EXPECTED_FOREIGN_KEYS
    ):
        raise ImportContractError(
            "Foreign-key count mismatch: "
            f"expected={EXPECTED_FOREIGN_KEYS}, "
            f"actual={foreign_key_count}"
        )

    dependency_order = build_dependency_order(
        expected_tables,
        dependencies,
    )

    existing_rows = await read_table_counts(
        conn,
        tuple(
            dependency_order
        ),
    )

    return DatabaseContract(
        database=database,
        user=user,
        revision=revision,
        table_names=database_tables,
        primary_keys=primary_keys,
        columns=database_columns,
        foreign_key_count=foreign_key_count,
        dependency_order=dependency_order,
        existing_rows=existing_rows,
    )


# ---------------------------------------------------------------------------
# UPSERT SQL
# ---------------------------------------------------------------------------


def build_upsert_sql(
    spec: DatasetSpec,
    stage_table: str,
    primary_key: tuple[str, ...],
) -> str:
    """Build deterministic PostgreSQL UPSERT SQL for one runtime table."""

    target_table_sql = (
        "public."
        + quote_identifier(
            spec.table_name
        )
    )

    stage_table_sql = quote_identifier(
        stage_table
    )

    columns_sql = ", ".join(
        quote_identifier(
            column
        )
        for column in spec.columns
    )

    conflict_sql = ", ".join(
        quote_identifier(
            column
        )
        for column in primary_key
    )

    non_pk_columns = [
        column
        for column in spec.columns
        if column not in primary_key
    ]

    if not non_pk_columns:
        return f"""
            WITH changed AS (
                INSERT INTO {target_table_sql}
                    AS target ({columns_sql})
                SELECT {columns_sql}
                FROM {stage_table_sql}
                ON CONFLICT ({conflict_sql})
                DO NOTHING
                RETURNING 1
            )
            SELECT COUNT(*)::bigint
            FROM changed
        """

    set_sql = ",\n".join(
        (
            f"                    {quote_identifier(column)} "
            f"= EXCLUDED.{quote_identifier(column)}"
        )
        for column in non_pk_columns
    )

    target_values = ", ".join(
        (
            "target."
            + quote_identifier(
                column
            )
        )
        for column in non_pk_columns
    )

    excluded_values = ", ".join(
        (
            "EXCLUDED."
            + quote_identifier(
                column
            )
        )
        for column in non_pk_columns
    )

    return f"""
        WITH changed AS (
            INSERT INTO {target_table_sql}
                AS target ({columns_sql})
            SELECT {columns_sql}
            FROM {stage_table_sql}
            ON CONFLICT ({conflict_sql})
            DO UPDATE
            SET
{set_sql}
            WHERE
                ({target_values})
                IS DISTINCT FROM
                ({excluded_values})
            RETURNING 1
        )
        SELECT COUNT(*)::bigint
        FROM changed
    """


# ---------------------------------------------------------------------------
# Runtime import
# ---------------------------------------------------------------------------


def stage_table_name(
    phase: str,
    index: int,
    table_name: str,
) -> str:
    """Return a deterministic temporary staging-table name."""

    return (
        f"_mahindra_{phase}_{index:02d}_"
        f"{table_name}"
    )


async def load_stage_table(
    conn: asyncpg.Connection,
    spec: DatasetSpec,
    primary_key: tuple[str, ...],
    stage_table: str,
) -> None:
    """
    Create, COPY, validate, and index one temporary staging table.

    The staging table is transaction-local and never persists after
    transaction completion.
    """

    stage_sql = quote_identifier(
        stage_table
    )

    target_sql = (
        "public."
        +
        quote_identifier(
            spec.table_name
        )
    )

    await conn.execute(
        f"""
        CREATE TEMP TABLE {stage_sql}
        (
            LIKE {target_sql}
        )
        ON COMMIT DROP
        """
    )

    with spec.csv_path.open(
        "rb"
    ) as source:

        await conn.copy_to_table(
            stage_table,
            source=source,
            columns=list(
                spec.columns
            ),
            format="csv",
            header=True,
        )

    staged_rows = int(
        await conn.fetchval(
            "SELECT COUNT(*)::bigint "
            f"FROM {stage_sql}"
        )
    )

    if staged_rows != spec.rows:

        raise ImportContractError(
            f"{spec.table_name}: staging row mismatch: "
            f"expected={spec.rows}, "
            f"actual={staged_rows}"
        )

    primary_key_sql = ", ".join(
        quote_identifier(
            column
        )
        for column in primary_key
    )

    # --------------------------------------------------------
    # A unique staging index:
    #
    # 1. catches duplicate CSV primary keys
    # 2. accelerates stale-row anti-joins
    #
    # This matters particularly for the 610k-row manufacturing
    # time-series snapshot.
    # --------------------------------------------------------

    await conn.execute(
        f"""
        CREATE UNIQUE INDEX
        ON {stage_sql} ({primary_key_sql})
        """
    )


async def drop_stage_table(
    conn: asyncpg.Connection,
    stage_table: str,
) -> None:
    """Drop one temporary staging table."""

    await conn.execute(
        "DROP TABLE IF EXISTS "
        +
        quote_identifier(
            stage_table
        )
    )


async def upsert_one_table(
    conn: asyncpg.Connection,
    spec: DatasetSpec,
    primary_key: tuple[str, ...],
    index: int,
) -> tuple[
    int,
    int,
]:
    """
    UPSERT the complete current CSV snapshot for one table.

    Exact equality is intentionally NOT required yet because stale
    historical rows may still exist until Phase 2.
    """

    stage_table = stage_table_name(
        "upsert",
        index,
        spec.table_name,
    )

    target_sql = (
        "public."
        +
        quote_identifier(
            spec.table_name
        )
    )

    try:

        await load_stage_table(
            conn=conn,
            spec=spec,
            primary_key=primary_key,
            stage_table=stage_table,
        )

        upsert_sql = build_upsert_sql(
            spec,
            stage_table,
            primary_key,
        )

        changed_rows = int(
            await conn.fetchval(
                upsert_sql
            )
        )

        target_rows = int(
            await conn.fetchval(
                "SELECT COUNT(*)::bigint "
                f"FROM {target_sql}"
            )
        )

        # Every current CSV PK must exist after UPSERT.
        # Additional rows are allowed temporarily because they may
        # be stale rows awaiting Phase 2 cleanup.

        if target_rows < spec.rows:

            raise ImportContractError(
                f"{spec.table_name}: UPSERT did not "
                "materialize the complete current snapshot: "
                f"expected_at_least={spec.rows}, "
                f"actual={target_rows}"
            )

        return (
            changed_rows,
            target_rows,
        )

    finally:

        await drop_stage_table(
            conn,
            stage_table,
        )


def build_delete_stale_sql(
    spec: DatasetSpec,
    stage_table: str,
    primary_key: tuple[str, ...],
) -> str:
    """
    Build stale-row reconciliation SQL.

    Any target PK absent from the current CSV stage is obsolete.

    Caller MUST execute tables in reverse FK dependency order.
    """

    target_sql = (
        "public."
        +
        quote_identifier(
            spec.table_name
        )
    )

    stage_sql = quote_identifier(
        stage_table
    )

    key_match_sql = (
        "\n                AND "
        .join(
            (
                f"stage.{quote_identifier(column)} "
                f"= target.{quote_identifier(column)}"
            )
            for column in primary_key
        )
    )

    return f"""
        WITH deleted AS (
            DELETE FROM {target_sql} AS target
            WHERE NOT EXISTS (
                SELECT 1
                FROM {stage_sql} AS stage
                WHERE
                    {key_match_sql}
            )
            RETURNING 1
        )
        SELECT COUNT(*)::bigint
        FROM deleted
    """


async def delete_stale_one_table(
    conn: asyncpg.Connection,
    spec: DatasetSpec,
    primary_key: tuple[str, ...],
    index: int,
) -> tuple[
    int,
    int,
]:
    """
    Delete target rows that no longer exist in the current CSV.

    This function is called only after all current rows have already
    been UPSERTed.

    Tables are processed in reverse FK dependency order so children
    are reconciled before parents.
    """

    stage_table = stage_table_name(
        "delete",
        index,
        spec.table_name,
    )

    target_sql = (
        "public."
        +
        quote_identifier(
            spec.table_name
        )
    )

    try:

        await load_stage_table(
            conn=conn,
            spec=spec,
            primary_key=primary_key,
            stage_table=stage_table,
        )

        delete_sql = (
            build_delete_stale_sql(
                spec=spec,
                stage_table=stage_table,
                primary_key=primary_key,
            )
        )

        deleted_rows = int(
            await conn.fetchval(
                delete_sql
            )
        )

        target_rows = int(
            await conn.fetchval(
                "SELECT COUNT(*)::bigint "
                f"FROM {target_sql}"
            )
        )

        # ----------------------------------------------------
        # Exact snapshot contract.
        #
        # At this point:
        #
        # - every current row was already UPSERTed
        # - every stale PK has now been deleted
        #
        # Therefore exact equality is mandatory.
        # ----------------------------------------------------

        if target_rows != spec.rows:

            raise ImportContractError(
                f"{spec.table_name}: exact runtime "
                "row-count verification failed after "
                "stale-row cleanup: "
                f"expected={spec.rows}, "
                f"actual={target_rows}. "
                "The complete transaction will be rolled back."
            )

        return (
            deleted_rows,
            target_rows,
        )

    finally:

        await drop_stage_table(
            conn,
            stage_table,
        )


async def import_runtime_data(
    conn: asyncpg.Connection,
    manifest: ManifestContract,
    database: DatabaseContract,
) -> ImportResult:
    """
    Synchronize PostgreSQL to the exact validated CSV snapshot.

    PHASE 1
        UPSERT all current rows in FK-safe forward order.

    PHASE 2
        DELETE obsolete rows in reverse FK order.

    PHASE 3
        Verify exact table and runtime totals.

    The complete operation runs inside one PostgreSQL transaction.
    Any failure rolls back both the UPSERT and stale-row cleanup.
    """

    specs_by_table = {
        spec.table_name:
            spec

        for spec in manifest.runtime
    }

    changed_rows: dict[
        str,
        int,
    ] = {}

    deleted_rows: dict[
        str,
        int,
    ] = {}

    final_rows: dict[
        str,
        int,
    ] = {}

    print()

    print(
        "=" * 76
    )

    print(
        "POSTGRES IMPORT - EXACT SNAPSHOT TRANSACTION"
    )

    print(
        "=" * 76
    )

    async with conn.transaction():

        # ----------------------------------------------------
        # Prevent concurrent synthetic snapshot imports.
        # ----------------------------------------------------

        await conn.fetchval(
            """
            SELECT pg_advisory_xact_lock(
                hashtext($1)::bigint
            )
            """,
            ADVISORY_LOCK_NAME,
        )

        await conn.execute(
            "SET LOCAL lock_timeout = '30s'"
        )

        await conn.execute(
            "SET LOCAL statement_timeout = 0"
        )

        forward_order = tuple(
            database.dependency_order
        )

        reverse_order = tuple(
            reversed(
                database.dependency_order
            )
        )

        total = len(
            forward_order
        )

        # ====================================================
        # PHASE 1
        # UPSERT CURRENT WORLD
        # ====================================================

        print()

        print(
            "PHASE 1/2 - UPSERT CURRENT SNAPSHOT"
        )

        print(
            "-" * 76
        )

        for index, table_name in enumerate(
            forward_order,
            start=1,
        ):

            spec = specs_by_table[
                table_name
            ]

            primary_key = database.primary_keys[
                table_name
            ]

            (
                changed,
                interim_count,
            ) = await upsert_one_table(
                conn=conn,
                spec=spec,
                primary_key=primary_key,
                index=index,
            )

            changed_rows[
                table_name
            ] = changed

            print(
                f"[{index:02d}/{total:02d}] "
                f"UPSERT {table_name:<32} "
                f"snapshot={spec.rows:>7} "
                f"db_now={interim_count:>7} "
                f"changed={changed:>7}"
            )

        # ====================================================
        # PHASE 2
        # DELETE STALE ROWS
        # ====================================================
        #
        # Important sequencing:
        #
        # We do NOT delete stale parent rows before Phase 1.
        #
        # A surviving child row may have changed its FK from an
        # old parent to a new parent. Phase 1 first updates that
        # child to its current FK. Only then can the obsolete
        # old parent safely be deleted.
        #
        # Reverse dependency order then ensures stale children
        # are removed before stale parents.
        # ====================================================

        print()

        print(
            "PHASE 2/2 - DELETE STALE ROWS"
        )

        print(
            "-" * 76
        )

        for index, table_name in enumerate(
            reverse_order,
            start=1,
        ):

            spec = specs_by_table[
                table_name
            ]

            primary_key = database.primary_keys[
                table_name
            ]

            (
                deleted,
                final_count,
            ) = await delete_stale_one_table(
                conn=conn,
                spec=spec,
                primary_key=primary_key,
                index=index,
            )

            deleted_rows[
                table_name
            ] = deleted

            final_rows[
                table_name
            ] = final_count

            print(
                f"[{index:02d}/{total:02d}] "
                f"SYNC   {table_name:<32} "
                f"rows={final_count:>7} "
                f"deleted={deleted:>7}"
            )

        # ====================================================
        # TRANSACTION-WIDE EXACT ROW CONTRACT
        # ====================================================

        total_rows = sum(
            final_rows.values()
        )

        if total_rows != manifest.runtime_rows:

            raise ImportContractError(
                "Transactional runtime row total mismatch: "
                f"expected={manifest.runtime_rows}, "
                f"actual={total_rows}"
            )

        # Transaction context commits ONLY if every operation and
        # verification above succeeds.

    return ImportResult(
        changed_rows=changed_rows,
        deleted_rows=deleted_rows,
        final_rows=final_rows,
    )


# ---------------------------------------------------------------------------
# Post-commit verification
# ---------------------------------------------------------------------------


async def verify_post_commit(
    conn: asyncpg.Connection,
    manifest: ManifestContract,
    database: DatabaseContract,
) -> dict[str, int]:
    """Verify exact runtime counts after transaction commit."""

    counts = await read_table_counts(
        conn,
        database.dependency_order,
    )

    specs = {
        spec.table_name: spec
        for spec in manifest.runtime
    }

    failures: list[str] = []

    for table_name, actual_rows in counts.items():
        expected_rows = specs[
            table_name
        ].rows

        if actual_rows != expected_rows:
            failures.append(
                f"{table_name}: "
                f"expected={expected_rows}, "
                f"actual={actual_rows}"
            )

    total_rows = sum(
        counts.values()
    )

    if total_rows != manifest.runtime_rows:
        failures.append(
            "runtime total: "
            f"expected={manifest.runtime_rows}, "
            f"actual={total_rows}"
        )

    if failures:
        raise ImportContractError(
            "Post-commit verification failed:\n"
            + "\n".join(
                failures
            )
        )

    return counts


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_manifest_summary(
    contract: ManifestContract,
) -> None:
    """Print validated manifest/runtime isolation summary."""

    print()
    print("=" * 76)
    print("MAHINDRA AI NEXUS - POSTGRES IMPORT")
    print("=" * 76)

    print(
        "Manifest datasets:",
        contract.total_datasets,
    )

    print(
        "Runtime datasets:",
        len(contract.runtime),
    )

    print(
        "Ground-truth datasets:",
        contract.ground_truth_datasets,
    )

    print(
        "Runtime rows:",
        contract.runtime_rows,
    )

    print(
        "Ground-truth import:",
        "DISABLED",
    )

    if contract.registry_sha256:
        print(
            "Registry SHA-256:",
            contract.registry_sha256,
        )


def print_database_summary(
    contract: DatabaseContract,
) -> None:
    """Print PostgreSQL preflight result."""

    print()
    print("=" * 76)
    print("POSTGRES RUNTIME SCHEMA PREFLIGHT")
    print("=" * 76)

    print(
        "Database:",
        contract.database,
    )

    print(
        "User:",
        contract.user,
    )

    print(
        "Alembic revision:",
        contract.revision,
    )

    print(
        "Runtime tables:",
        len(contract.table_names),
    )

    print(
        "Primary keys:",
        len(contract.primary_keys),
    )

    print(
        "Foreign keys:",
        contract.foreign_key_count,
    )

    print(
        "FK-safe import order:",
        len(contract.dependency_order),
        "tables",
    )

    print(
        "Existing runtime rows:",
        sum(
            contract.existing_rows.values()
        ),
    )


def print_dry_run_summary(
    manifest: ManifestContract,
    database: DatabaseContract,
) -> None:
    """Print dry-run completion."""

    print()
    print("=" * 76)
    print("POSTGRES IMPORT DRY-RUN SUMMARY")
    print("=" * 76)

    print("Manifest validation: PASS")
    print("CSV artifact validation: PASS")
    print("Runtime/ground-truth isolation: PASS")
    print("Database connectivity: PASS")
    print("Alembic revision: PASS")
    print("Runtime table contract: PASS")
    print("Primary-key contract: PASS")
    print("Foreign-key contract: PASS")
    print("Database column contract: PASS")

    print(
        "Runtime datasets:",
        len(manifest.runtime),
    )

    print(
        "Runtime rows expected:",
        manifest.runtime_rows,
    )

    print(
        "Ground-truth datasets excluded:",
        manifest.ground_truth_datasets,
    )

    print(
        "Existing runtime rows:",
        sum(
            database.existing_rows.values()
        ),
    )

    print()
    print("=" * 76)
    print("POSTGRES IMPORT DRY RUN: PASS")
    print("=" * 76)
    print("No PostgreSQL rows were written.")


def print_import_summary(
    manifest: ManifestContract,
    database: DatabaseContract,
    result: ImportResult,
    post_commit_counts: dict[str, int],
) -> None:
    """Print committed import summary."""

    changed_total = sum(
        result.changed_rows.values()
    )

    deleted_total = sum(
        result.deleted_rows.values()
    )

    final_total = sum(
        post_commit_counts.values()
    )

    print()
    print("=" * 76)
    print("POSTGRES IMPORT SUMMARY")
    print("=" * 76)

    print("Validation status: PASS")
    print("Transaction status: COMMITTED")

    print(
        "Alembic revision:",
        database.revision,
    )

    print(
        "Runtime tables:",
        len(result.final_rows),
    )

    print(
        "Runtime datasets:",
        len(manifest.runtime),
    )

    print(
        "Ground-truth datasets imported:",
        0,
    )

    print(
        "Expected runtime rows:",
        manifest.runtime_rows,
    )

    print(
        "Verified runtime rows:",
        final_total,
    )

    print(
        "Rows inserted/updated this run:",
        changed_total,
    )

    print(
        "Stale rows deleted this run:",
        deleted_total,
    )

    print(
        "Unchanged final rows:",
        final_total - changed_total,
    )

    print(
        "Foreign keys:",
        database.foreign_key_count,
    )

    print()
    print("=" * 76)
    print("IMPORT POSTGRES: PASS")
    print("=" * 76)
    print(
        "Runtime PostgreSQL now matches the validated "
        "synthetic CSV contract."
    )
    print(
        "Evaluator ground truth was not imported."
    )


# ---------------------------------------------------------------------------
# Async execution
# ---------------------------------------------------------------------------


async def run_import(
    args: argparse.Namespace,
    manifest: ManifestContract,
) -> None:
    """Connect, preflight, optionally import, and verify."""

    database_url = resolve_database_url(
        args.database_url
    )

    try:
        conn = await asyncpg.connect(
            dsn=database_url,
            timeout=args.connect_timeout,
        )
    except Exception as exc:
        raise ImportContractError(
            "Unable to connect to PostgreSQL."
        ) from exc

    try:
        database = await validate_database_contract(
            conn,
            manifest,
        )

        print_database_summary(
            database
        )

        if args.dry_run:
            print_dry_run_summary(
                manifest,
                database,
            )
            return

        result = await import_runtime_data(
            conn,
            manifest,
            database,
        )

        post_commit_counts = await verify_post_commit(
            conn,
            manifest,
            database,
        )

        print_import_summary(
            manifest,
            database,
            result,
            post_commit_counts,
        )

    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Validate and import Mahindra AI Nexus runtime CSVs "
            "into PostgreSQL."
        )
    )

    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help=(
            "Path to dataset_manifest.json. "
            f"Default: {DEFAULT_MANIFEST_PATH}"
        ),
    )

    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "PostgreSQL DSN. If omitted, uses "
            "MAHINDRA_DATABASE_URL, then DATABASE_URL, "
            "then the local development default."
        ),
    )

    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=30.0,
        help="Database connection timeout in seconds.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate manifest, CSV artifacts, and PostgreSQL "
            "schema without writing any rows."
        ),
    )

    return parser


def main() -> int:
    """CLI entry point."""

    parser = build_parser()
    args = parser.parse_args()

    try:
        manifest = load_manifest(
            args.manifest
        )

        print_manifest_summary(
            manifest
        )

        validate_runtime_artifacts(
            manifest
        )

        asyncio.run(
            run_import(
                args,
                manifest,
            )
        )

    except KeyboardInterrupt:
        print()
        print("IMPORT POSTGRES: CANCELLED")
        return 130

    except Exception as exc:
        print()
        print("=" * 76)
        print("IMPORT POSTGRES: FAIL")
        print("=" * 76)
        print(
            f"{type(exc).__name__}: {exc}"
        )

        cause = exc.__cause__

        if cause is not None:
            print(
                "Caused by:",
                f"{type(cause).__name__}: {cause}",
            )

        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
