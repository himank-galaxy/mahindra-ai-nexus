"""
Mahindra AI Nexus
Synthetic Data Factory - Deterministic CSV Export

============================================================
PURPOSE
============================================================

Export the validated in-memory registry produced by:

    data/scripts/generate_all.py

to deterministic CSV artifacts under:

    data/synthetic/
    data/ground_truth/

and write:

    data/dataset_manifest.json


============================================================
RESPONSIBILITIES
============================================================

This module:

    - generates the complete registry in memory
    - validates that same registry before writing
    - maps registry paths to fixed filesystem paths
    - writes one CSV per registered DataFrame
    - preserves runtime / ground-truth separation
    - validates every temporary CSV before commit
    - computes SHA-256 checksums
    - writes a deterministic dataset manifest
    - respects overwrite_existing_csv
    - safely skips already-identical files
    - avoids partial writes when conflicts are detected


============================================================
THIS MODULE DOES NOT
============================================================

    - contain synthetic business logic
    - modify frozen generators
    - modify DataFrames
    - import PostgreSQL
    - duplicate ground-truth datasets
    - place evaluator truth inside runtime folders


============================================================
EXPECTED V1 EXPORT
============================================================

58 CSV files total

    data/synthetic/       51 CSV files
    data/ground_truth/     7 CSV files

plus:

    data/dataset_manifest.json


============================================================
NON-DESTRUCTIVE EXPORT POLICY
============================================================

If overwrite_existing_csv = False:

    existing file + identical SHA-256
        -> SKIP safely

    existing file + different SHA-256
        -> FAIL before changing any destination files

If overwrite_existing_csv = True:

    existing identical file
        -> SKIP

    existing different file
        -> atomically replace


============================================================
GROUND-TRUTH RULE
============================================================

Runtime:

    data/synthetic/causal/

contains only observable runtime data:

    manufacturing_timeseries.csv
    mobility_timeseries.csv
    vehicle_telematics_timeseries.csv

Evaluator-only truth remains under:

    data/ground_truth/
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================
# CONFIG
# ============================================================

from data.generators.common.helpers import (
    load_distribution_config,
    load_generation_config,
    load_scenario_config,
)


# ============================================================
# ORCHESTRATION + VALIDATION
# ============================================================

from data.scripts.generate_all import (
    generate_all,
)

from data.scripts.validate_all import (
    validate_all,
)


# ============================================================
# CONSTANTS
# ============================================================

EXPECTED_DATASET_COUNT = 58

EXPECTED_SYNTHETIC_DATASET_COUNT = 51

EXPECTED_GROUND_TRUTH_DATASET_COUNT = 7

CSV_ENCODING = "utf-8"

CSV_LINE_TERMINATOR = "\n"


# ============================================================
# TYPES
# ============================================================

DatasetRegistry = Mapping[
    str,
    Any,
]


# ============================================================
# BASIC HELPERS
# ============================================================


def _flatten_registry(
    node: Mapping[str, Any],
    prefix: str = "",
) -> dict[
    str,
    pd.DataFrame,
]:
    """
    Flatten:

        registry["synthetic"]["master"]["regions"]

    into:

        synthetic/master/regions -> DataFrame
    """

    result: dict[
        str,
        pd.DataFrame,
    ] = {}

    for name, value in node.items():

        path = (
            f"{prefix}/{name}"
            if prefix
            else str(
                name
            )
        )

        if isinstance(
            value,
            pd.DataFrame,
        ):

            if path in result:

                raise ValueError(
                    f"Duplicate registry path: {path}"
                )

            result[
                path
            ] = value

            continue

        if isinstance(
            value,
            Mapping,
        ):

            child = _flatten_registry(
                value,
                path,
            )

            overlap = (
                set(
                    result
                )
                &
                set(
                    child
                )
            )

            if overlap:

                raise ValueError(
                    "Duplicate registry paths found: "
                    +
                    ", ".join(
                        sorted(
                            overlap
                        )
                    )
                )

            result.update(
                child
            )

            continue

        raise TypeError(
            f"Registry leaf {path} must be a pandas DataFrame. "
            f"Actual type={type(value).__name__}"
        )

    return result


def _sha256_file(
    path: Path,
) -> str:
    """
    Compute SHA-256 without loading entire file into memory.
    """

    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as handle:

        while True:

            block = handle.read(
                1024 * 1024
            )

            if not block:
                break

            digest.update(
                block
            )

    return digest.hexdigest()


def _safe_relative_components(
    logical_path: str,
) -> tuple[
    str,
    tuple[str, ...],
]:
    """
    Parse one registry path safely.

    Example:

        synthetic/auto/warranty_claims

    returns:

        ("synthetic", ("auto", "warranty_claims"))
    """

    components = tuple(
        component
        for component
        in logical_path.split(
            "/"
        )
        if component
    )

    if len(
        components
    ) < 2:

        raise ValueError(
            f"Invalid registry path: {logical_path}"
        )

    if any(
        component
        in {
            ".",
            "..",
        }
        for component
        in components
    ):

        raise ValueError(
            f"Unsafe registry path: {logical_path}"
        )

    storage_class = components[
        0
    ]

    if storage_class not in {
        "synthetic",
        "ground_truth",
    }:

        raise ValueError(
            f"Unsupported registry storage class "
            f"{storage_class!r} in {logical_path}"
        )

    return (
        storage_class,
        components[
            1:
        ],
    )


# ============================================================
# OUTPUT CONFIG
# ============================================================


def _output_config(
    generation: Mapping[str, Any],
) -> Mapping[str, Any]:

    output = generation.get(
        "output"
    )

    if not isinstance(
        output,
        Mapping,
    ):

        raise TypeError(
            "generation.output must be a mapping"
        )

    return output


def _configured_roots(
    generation: Mapping[str, Any],
) -> tuple[
    Path,
    Path,
]:
    """
    Resolve configured synthetic / ground-truth roots.
    """

    output = _output_config(
        generation
    )

    synthetic_root_value = output.get(
        "synthetic_root"
    )

    ground_truth_root_value = output.get(
        "ground_truth_root"
    )

    if not synthetic_root_value:

        raise KeyError(
            "output.synthetic_root"
        )

    if not ground_truth_root_value:

        raise KeyError(
            "output.ground_truth_root"
        )

    synthetic_root = Path(
        str(
            synthetic_root_value
        )
    )

    ground_truth_root = Path(
        str(
            ground_truth_root_value
        )
    )

    return (
        synthetic_root,
        ground_truth_root,
    )


def _configured_manifest_path(
    generation: Mapping[str, Any],
) -> Path:
    """
    Place the manifest at the common data root.

    Current configuration:

        data/synthetic
        data/ground_truth

    therefore gives:

        data/dataset_manifest.json
    """

    output = _output_config(
        generation
    )

    manifest_filename = str(
        output.get(
            "manifest_filename",
            "dataset_manifest.json",
        )
    )

    if Path(
        manifest_filename
    ).name != manifest_filename:

        raise ValueError(
            "output.manifest_filename must be a filename, "
            "not a path"
        )

    (
        synthetic_root,
        ground_truth_root,
    ) = _configured_roots(
        generation
    )

    synthetic_parent = (
        synthetic_root
        .resolve()
        .parent
    )

    ground_truth_parent = (
        ground_truth_root
        .resolve()
        .parent
    )

    if (
        synthetic_parent
        !=
        ground_truth_parent
    ):

        raise ValueError(
            "synthetic_root and ground_truth_root must share "
            "the same parent so the manifest has one canonical "
            "data root"
        )

    return (
        synthetic_root.parent
        /
        manifest_filename
    )


def _overwrite_enabled(
    generation: Mapping[str, Any],
) -> bool:

    output = _output_config(
        generation
    )

    return bool(
        output.get(
            "overwrite_existing_csv",
            False,
        )
    )


def _csv_enabled(
    generation: Mapping[str, Any],
) -> bool:

    output = _output_config(
        generation
    )

    return bool(
        output.get(
            "csv_enabled",
            False,
        )
    )


def _manifest_enabled(
    generation: Mapping[str, Any],
) -> bool:

    output = _output_config(
        generation
    )

    return bool(
        output.get(
            "write_manifest",
            True,
        )
    )


# ============================================================
# LOGICAL -> PHYSICAL PATH MAPPING
# ============================================================


def _target_path(
    logical_path: str,
    synthetic_root: Path,
    ground_truth_root: Path,
) -> Path:
    """
    Convert registry path to canonical CSV path.

    Examples:

        synthetic/master/regions

            -> data/synthetic/master/regions.csv

        ground_truth/causal/manufacturing_causal_edges

            -> data/ground_truth/causal/
               manufacturing_causal_edges.csv
    """

    (
        storage_class,
        components,
    ) = _safe_relative_components(
        logical_path
    )

    if storage_class == "synthetic":

        root = synthetic_root

    else:

        root = ground_truth_root

    destination = root.joinpath(
        *components
    )

    destination = destination.with_suffix(
        ".csv"
    )

    return destination


# ============================================================
# CSV TEMP WRITE + VALIDATION
# ============================================================


def _write_dataframe_temp(
    dataframe: pd.DataFrame,
    destination: Path,
) -> Path:
    """
    Write a DataFrame to a temporary file in the same directory
    as its final destination.

    Final destination is NOT modified here.
    """

    if dataframe.columns.duplicated().any():

        duplicates = (
            dataframe.columns[
                dataframe.columns.duplicated(
                    keep=False
                )
            ]
            .astype(
                str
            )
            .tolist()
        )

        raise ValueError(
            f"{destination}: duplicate DataFrame columns: "
            f"{duplicates}"
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_handle = (
        tempfile.NamedTemporaryFile(
            mode="w",
            encoding=CSV_ENCODING,
            newline="",
            prefix=
                f".{destination.name}.",

            suffix=
                ".tmp",

            dir=
                destination.parent,

            delete=False,
        )
    )

    temp_path = Path(
        temp_handle.name
    )

    try:

        with temp_handle:

            dataframe.to_csv(
                temp_handle,
                index=False,
                encoding=CSV_ENCODING,
                lineterminator=
                    CSV_LINE_TERMINATOR,
            )

    except Exception:

        if temp_path.exists():

            temp_path.unlink()

        raise

    return temp_path


def _validate_temp_csv(
    temp_path: Path,
    dataframe: pd.DataFrame,
) -> None:
    """
    Verify:

        - CSV exists
        - file is non-empty
        - header exactly matches DataFrame columns
        - CSV data row count matches DataFrame row count

    csv.reader is used instead of physical line counting because
    quoted text could legally contain line breaks.
    """

    if not temp_path.exists():

        raise FileNotFoundError(
            temp_path
        )

    if temp_path.stat().st_size <= 0:

        raise ValueError(
            f"Empty CSV artifact: {temp_path}"
        )

    with temp_path.open(
        "r",
        encoding=CSV_ENCODING,
        newline="",
    ) as handle:

        reader = csv.reader(
            handle
        )

        header = next(
            reader,
            None,
        )

        if header is None:

            raise ValueError(
                f"CSV contains no header: {temp_path}"
            )

        expected_header = [
            str(
                column
            )
            for column
            in dataframe.columns
        ]

        if header != expected_header:

            raise ValueError(
                f"{temp_path}: CSV header mismatch.\n"
                f"Expected={expected_header}\n"
                f"Actual={header}"
            )

        row_count = sum(
            1
            for _ in reader
        )

    if row_count != len(
        dataframe
    ):

        raise ValueError(
            f"{temp_path}: CSV row-count mismatch. "
            f"Expected={len(dataframe)}, "
            f"actual={row_count}"
        )


# ============================================================
# EXPORT RECORD
# ============================================================


def _build_export_record(
    logical_path: str,
    dataframe: pd.DataFrame,
    destination: Path,
    temp_path: Path,
) -> dict[str, Any]:
    """
    Build deterministic metadata for one CSV.
    """

    (
        storage_class,
        _,
    ) = _safe_relative_components(
        logical_path
    )

    return {
        "logical_path":
            logical_path,

        "storage_class":
            storage_class,

        "file":
            destination.as_posix(),

        "rows":
            int(
                len(
                    dataframe
                )
            ),

        "columns":
            int(
                len(
                    dataframe.columns
                )
            ),

        "column_names":
            [
                str(
                    column
                )
                for column
                in dataframe.columns
            ],

        "dtypes":
            {
                str(
                    column
                ):
                str(
                    dtype
                )
                for column, dtype
                in dataframe.dtypes.items()
            },

        "bytes":
            int(
                temp_path.stat().st_size
            ),

        "sha256":
            _sha256_file(
                temp_path
            ),
    }


# ============================================================
# MANIFEST
# ============================================================


def _registry_signature(
    records: list[
        dict[str, Any]
    ],
) -> str:
    """
    Deterministic signature over the complete exported registry.
    """

    digest = hashlib.sha256()

    for record in sorted(
        records,
        key=lambda item:
            item[
                "logical_path"
            ],
    ):

        payload = (
            f"{record['logical_path']}\0"
            f"{record['rows']}\0"
            f"{record['columns']}\0"
            f"{record['sha256']}\n"
        )

        digest.update(
            payload.encode(
                "utf-8"
            )
        )

    return digest.hexdigest()


def _build_manifest(
    generation: Mapping[str, Any],
    records: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    """
    Build deterministic manifest.

    No wall-clock generated_at timestamp is included because that
    would make identical synthetic worlds produce different
    manifests.
    """

    synthetic_count = sum(
        1
        for record
        in records
        if record[
            "storage_class"
        ] == "synthetic"
    )

    ground_truth_count = sum(
        1
        for record
        in records
        if record[
            "storage_class"
        ] == "ground_truth"
    )

    total_rows = sum(
        int(
            record[
                "rows"
            ]
        )
        for record
        in records
    )

    provenance = generation.get(
        "provenance",
        {}
    )

    time_config = generation.get(
        "time",
        {}
    )

    manifest = {
        "manifest_version":
            "1.0.0",

        "project":
            "Mahindra AI Nexus",

        "data_factory":
            "Synthetic Data Factory",

        "config_version":
            str(
                generation.get(
                    "config_version",
                    ""
                )
            ),

        "generator_version":
            str(
                generation.get(
                    "generator_version",
                    ""
                )
            ),

        "seed":
            int(
                generation[
                    "seed"
                ]
            ),

        "data_origin":
            str(
                provenance.get(
                    "data_origin",
                    ""
                )
            ),

        "contains_real_customer_pii":
            bool(
                provenance.get(
                    "contains_real_customer_pii",
                    False,
                )
            ),

        "scenario_version":
            str(
                provenance.get(
                    "scenario_version",
                    ""
                )
            ),

        "generation_window": {
            "start_date":
                str(
                    time_config.get(
                        "start_date",
                        ""
                    )
                ),

            "end_date":
                str(
                    time_config.get(
                        "end_date",
                        ""
                    )
                ),

            "timezone":
                str(
                    time_config.get(
                        "timezone",
                        ""
                    )
                ),
        },

        "csv_format": {
            "encoding":
                CSV_ENCODING,

            "index_written":
                False,

            "line_terminator":
                "\\n",
        },

        "dataset_count":
            int(
                len(
                    records
                )
            ),

        "synthetic_dataset_count":
            int(
                synthetic_count
            ),

        "ground_truth_dataset_count":
            int(
                ground_truth_count
            ),

        "total_rows":
            int(
                total_rows
            ),

        "registry_sha256":
            _registry_signature(
                records
            ),

        "datasets":
            sorted(
                records,
                key=lambda item:
                    item[
                        "logical_path"
                    ],
            ),
    }

    return manifest


def _write_manifest_temp(
    manifest: Mapping[str, Any],
    destination: Path,
) -> Path:
    """
    Write deterministic JSON manifest to temporary file.
    """

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_handle = (
        tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=
                f".{destination.name}.",

            suffix=
                ".tmp",

            dir=
                destination.parent,

            delete=False,
        )
    )

    temp_path = Path(
        temp_handle.name
    )

    try:

        with temp_handle:

            json.dump(
                manifest,
                temp_handle,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )

            temp_handle.write(
                "\n"
            )

    except Exception:

        if temp_path.exists():

            temp_path.unlink()

        raise

    return temp_path


# ============================================================
# EXISTING FILE POLICY
# ============================================================


def _existing_file_action(
    destination: Path,
    temp_path: Path,
    overwrite: bool,
) -> str:
    """
    Decide how one artifact should be committed.

    Returns:

        WRITE
        REPLACE
        SKIP_IDENTICAL

    Raises:

        FileExistsError if destination differs and overwrite=False.
    """

    if not destination.exists():

        return "WRITE"

    existing_hash = _sha256_file(
        destination
    )

    candidate_hash = _sha256_file(
        temp_path
    )

    if existing_hash == candidate_hash:

        return "SKIP_IDENTICAL"

    if not overwrite:

        raise FileExistsError(
            f"Existing artifact differs from deterministic export "
            f"and overwrite_existing_csv=False:\n"
            f"  {destination}\n"
            f"Existing SHA-256: {existing_hash}\n"
            f"Candidate SHA-256: {candidate_hash}"
        )

    return "REPLACE"


# ============================================================
# CLEANUP
# ============================================================


def _cleanup_temp_paths(
    paths: list[
        Path
    ],
) -> None:

    for path in paths:

        try:

            if path.exists():

                path.unlink()

        except OSError:

            pass


def _managed_csv_files(
    root: Path,
) -> set[
    Path
]:
    """
    Return regular CSV files physically contained under one
    configured generated-data root.

    Symlinks are intentionally ignored so cleanup can never
    follow a link outside the managed tree.
    """

    if not root.exists():

        return set()

    root_resolved = root.resolve()

    result: set[
        Path
    ] = set()

    for candidate in root.rglob(
        "*.csv"
    ):

        if (
            candidate.is_symlink()
            or
            not candidate.is_file()
        ):

            continue

        resolved = candidate.resolve()

        try:

            resolved.relative_to(
                root_resolved
            )

        except ValueError as exc:

            raise ValueError(
                "Managed CSV resolved outside configured root: "
                f"{candidate}"
            ) from exc

        result.add(
            resolved
        )

    return result


def _stale_managed_csvs(
    *,
    synthetic_root: Path,
    ground_truth_root: Path,
    expected_destinations: set[
        Path
    ],
) -> list[
    Path
]:
    """
    Find generated CSV artifacts that physically exist under the
    configured roots but no longer correspond to the registry.
    """

    expected = {
        path.resolve()
        for path
        in expected_destinations
    }

    existing = (
        _managed_csv_files(
            synthetic_root
        )
        |
        _managed_csv_files(
            ground_truth_root
        )
    )

    return sorted(
        existing
        -
        expected,
        key=lambda path:
            path.as_posix(),
    )


def _remove_stale_managed_csvs(
    paths: list[
        Path
    ],
) -> int:
    """
    Delete only stale CSV files already proven to be physically
    inside configured generated-data roots.
    """

    removed = 0

    for path in paths:

        if not path.exists():

            continue

        if path.is_symlink():

            raise ValueError(
                "Refusing to delete symlink during "
                "stale CSV cleanup: "
                f"{path}"
            )

        path.unlink()

        removed += 1

    return removed


def _verify_exact_managed_csv_set(
    *,
    synthetic_root: Path,
    ground_truth_root: Path,
    expected_destinations: set[
        Path
    ],
) -> None:
    """
    Verify managed CSV storage contains exactly the registry
    destinations after commit and stale-artifact cleanup.
    """

    expected = {
        path.resolve()
        for path
        in expected_destinations
    }

    actual = (
        _managed_csv_files(
            synthetic_root
        )
        |
        _managed_csv_files(
            ground_truth_root
        )
    )

    missing = sorted(
        expected
        -
        actual,
        key=lambda path:
            path.as_posix(),
    )

    extra = sorted(
        actual
        -
        expected,
        key=lambda path:
            path.as_posix(),
    )

    if missing:

        raise AssertionError(
            "Managed CSV verification missing "
            "registry artifacts: "
            +
            ", ".join(
                path.as_posix()
                for path
                in missing
            )
        )

    if extra:

        raise AssertionError(
            "Managed CSV verification found "
            "stale artifacts: "
            +
            ", ".join(
                path.as_posix()
                for path
                in extra
            )
        )


# ============================================================
# CORE EXPORT
# ============================================================


def export_registry_to_csv(
    registry: DatasetRegistry,
    generation: Mapping[str, Any],
    *,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Export an already-generated and validated registry.

    Uses a two-phase process:

        Phase A
            write + verify ALL temporary artifacts

        Phase B
            inspect ALL destination conflicts

        Phase C
            atomically commit artifacts

    Therefore a differing existing file with overwrite=False is
    detected before destination CSVs are modified.
    """

    if not _csv_enabled(
        generation
    ):

        raise RuntimeError(
            "CSV export is disabled by output.csv_enabled"
        )

    (
        synthetic_root,
        ground_truth_root,
    ) = _configured_roots(
        generation
    )

    manifest_path = _configured_manifest_path(
        generation
    )

    overwrite = _overwrite_enabled(
        generation
    )

    write_manifest = _manifest_enabled(
        generation
    )

    flattened = _flatten_registry(
        registry
    )

    # ========================================================
    # HARD REGISTRY CONTRACT
    # ========================================================

    if len(
        flattened
    ) != EXPECTED_DATASET_COUNT:

        raise AssertionError(
            "CSV export expected "
            f"{EXPECTED_DATASET_COUNT} DataFrames, "
            f"received {len(flattened)}"
        )

    synthetic_count = sum(
        1
        for path
        in flattened
        if path.startswith(
            "synthetic/"
        )
    )

    ground_truth_count = sum(
        1
        for path
        in flattened
        if path.startswith(
            "ground_truth/"
        )
    )

    if (
        synthetic_count
        !=
        EXPECTED_SYNTHETIC_DATASET_COUNT
    ):

        raise AssertionError(
            "Expected "
            f"{EXPECTED_SYNTHETIC_DATASET_COUNT} "
            "synthetic DataFrames, "
            f"received {synthetic_count}"
        )

    if (
        ground_truth_count
        !=
        EXPECTED_GROUND_TRUTH_DATASET_COUNT
    ):

        raise AssertionError(
            "Expected "
            f"{EXPECTED_GROUND_TRUTH_DATASET_COUNT} "
            "ground-truth DataFrames, "
            f"received {ground_truth_count}"
        )

    # ========================================================
    # BUILD TARGET MAP
    # ========================================================

    targets: dict[
        str,
        Path,
    ] = {}

    for logical_path in sorted(
        flattened
    ):

        destination = _target_path(
            logical_path=
                logical_path,

            synthetic_root=
                synthetic_root,

            ground_truth_root=
                ground_truth_root,
        )

        if destination in targets.values():

            raise ValueError(
                f"Multiple registry paths map to {destination}"
            )

        targets[
            logical_path
        ] = destination

    expected_destinations = {
        path.resolve()
        for path
        in targets.values()
    }

    stale_csvs = _stale_managed_csvs(
        synthetic_root=
            synthetic_root,

        ground_truth_root=
            ground_truth_root,

        expected_destinations=
            expected_destinations,
    )

    # --------------------------------------------------------
    # Non-destructive mode must not silently leave obsolete
    # generated CSVs beside the current registry.
    # --------------------------------------------------------

    if (
        stale_csvs
        and
        not overwrite
    ):

        raise FileExistsError(
            "Stale managed CSV artifacts exist but "
            "overwrite_existing_csv=False. "
            "No destination files were changed.\n"
            +
            "\n".join(
                f"  {path.as_posix()}"
                for path
                in stale_csvs
            )
        )

    # ========================================================
    # PHASE A:
    # WRITE + VERIFY ALL TEMP CSV FILES
    # ========================================================

    if verbose:

        print(
            "\n"
            "============================================================\n"
            "CSV EXPORT - PREPARING TEMPORARY ARTIFACTS\n"
            "============================================================"
        )

    temporary_paths: list[
        Path
    ] = []

    prepared: list[
        dict[str, Any]
    ] = []

    try:

        for index, logical_path in enumerate(
            sorted(
                flattened
            ),
            start=1,
        ):

            dataframe = flattened[
                logical_path
            ]

            destination = targets[
                logical_path
            ]

            temp_path = _write_dataframe_temp(
                dataframe=
                    dataframe,

                destination=
                    destination,
            )

            temporary_paths.append(
                temp_path
            )

            _validate_temp_csv(
                temp_path=
                    temp_path,

                dataframe=
                    dataframe,
            )

            record = _build_export_record(
                logical_path=
                    logical_path,

                dataframe=
                    dataframe,

                destination=
                    destination,

                temp_path=
                    temp_path,
            )

            prepared.append(
                {
                    "logical_path":
                        logical_path,

                    "destination":
                        destination,

                    "temp_path":
                        temp_path,

                    "record":
                        record,
                }
            )

            if verbose:

                print(
                    f"[{index:02d}/{len(flattened):02d}] "
                    f"READY  "
                    f"{logical_path:<65} "
                    f"rows={len(dataframe):>7}"
                )

        # ====================================================
        # BUILD MANIFEST FROM VERIFIED TEMP FILES
        # ====================================================

        records = [
            item[
                "record"
            ]
            for item
            in prepared
        ]

        manifest = _build_manifest(
            generation=
                generation,

            records=
                records,
        )

        _assert_manifest_contract(
            manifest
        )

        manifest_temp_path: Path | None = None

        if write_manifest:

            manifest_temp_path = (
                _write_manifest_temp(
                    manifest=
                        manifest,

                    destination=
                        manifest_path,
                )
            )

            temporary_paths.append(
                manifest_temp_path
            )

        # ====================================================
        # PHASE B:
        # CHECK ALL DESTINATION CONFLICTS BEFORE COMMIT
        # ====================================================

        if verbose:

            print(
                "\n"
                "============================================================\n"
                "CSV EXPORT - PREFLIGHT\n"
                "============================================================"
            )

            print(
                "overwrite_existing_csv:",
                overwrite,
            )

            print(
                "stale_managed_csvs:",
                len(
                    stale_csvs
                ),
            )

            for stale_path in stale_csvs:

                print(
                    "STALE          "
                    f"{stale_path.as_posix()}"
                )

        for item in prepared:

            action = _existing_file_action(
                destination=
                    item[
                        "destination"
                    ],

                temp_path=
                    item[
                        "temp_path"
                    ],

                overwrite=
                    overwrite,
            )

            item[
                "action"
            ] = action

        manifest_action: str | None = None

        if (
            write_manifest
            and
            manifest_temp_path is not None
        ):

            manifest_action = _existing_file_action(
                destination=
                    manifest_path,

                temp_path=
                    manifest_temp_path,

                overwrite=
                    overwrite,
            )

        # ====================================================
        # PHASE C:
        # COMMIT
        # ====================================================

        if verbose:

            print(
                "\n"
                "============================================================\n"
                "CSV EXPORT - COMMIT\n"
                "============================================================"
            )

        written = 0
        replaced = 0
        skipped = 0

        for item in prepared:

            destination = item[
                "destination"
            ]

            temp_path = item[
                "temp_path"
            ]

            action = item[
                "action"
            ]

            if action == "SKIP_IDENTICAL":

                temp_path.unlink()

                skipped += 1

            elif action == "WRITE":

                os.replace(
                    temp_path,
                    destination,
                )

                written += 1

            elif action == "REPLACE":

                os.replace(
                    temp_path,
                    destination,
                )

                replaced += 1

            else:

                raise RuntimeError(
                    f"Unknown export action: {action}"
                )

            if verbose:

                print(
                    f"{action:<16} "
                    f"{destination.as_posix()}"
                )

        # ====================================================
        # MANIFEST COMMIT LAST
        # ====================================================

        manifest_status = "DISABLED"

        if (
            write_manifest
            and
            manifest_temp_path is not None
            and
            manifest_action is not None
        ):

            if (
                manifest_action
                ==
                "SKIP_IDENTICAL"
            ):

                manifest_temp_path.unlink()

                manifest_status = (
                    "SKIP_IDENTICAL"
                )

            elif manifest_action in {
                "WRITE",
                "REPLACE",
            }:

                os.replace(
                    manifest_temp_path,
                    manifest_path,
                )

                manifest_status = (
                    manifest_action
                )

            else:

                raise RuntimeError(
                    "Unknown manifest action: "
                    f"{manifest_action}"
                )

        # ====================================================
        # POST-COMMIT VERIFICATION
        # ====================================================

        for item in prepared:

            destination = item[
                "destination"
            ]

            expected_hash = item[
                "record"
            ][
                "sha256"
            ]

            if not destination.exists():

                raise FileNotFoundError(
                    destination
                )

            actual_hash = _sha256_file(
                destination
            )

            if actual_hash != expected_hash:

                raise ValueError(
                    f"Post-commit checksum mismatch: "
                    f"{destination}"
                )

        if write_manifest:

            if not manifest_path.exists():

                raise FileNotFoundError(
                    manifest_path
                )

        # ====================================================
        # STALE MANAGED CSV CLEANUP
        #
        # Important:
        #
        # Cleanup happens only AFTER all current registry CSVs
        # have been committed and checksum-verified.
        # ====================================================

        stale_removed = 0

        if stale_csvs:

            stale_removed = (
                _remove_stale_managed_csvs(
                    stale_csvs
                )
            )

            if verbose:

                print(
                    "\n"
                    "============================================================\n"
                    "CSV EXPORT - STALE ARTIFACT CLEANUP\n"
                    "============================================================"
                )

                for stale_path in stale_csvs:

                    print(
                        "REMOVED        "
                        f"{stale_path.as_posix()}"
                    )

        # ====================================================
        # FINAL EXACT FILESET VERIFICATION
        # ====================================================

        _verify_exact_managed_csv_set(
            synthetic_root=
                synthetic_root,

            ground_truth_root=
                ground_truth_root,

            expected_destinations=
                expected_destinations,
        )

        result = {
            "status":
                "PASS",

            "dataset_count":
                len(
                    prepared
                ),

            "synthetic_dataset_count":
                synthetic_count,

            "ground_truth_dataset_count":
                ground_truth_count,

            "total_rows":
                int(
                    sum(
                        len(
                            dataframe
                        )
                        for dataframe
                        in flattened.values()
                    )
                ),

            "written":
                written,

            "replaced":
                replaced,

            "skipped_identical":
                skipped,

            "stale_csvs_removed":
                stale_removed,

            "manifest_status":
                manifest_status,

            "manifest_path":
                (
                    manifest_path.as_posix()
                    if write_manifest
                    else None
                ),

            "registry_sha256":
                manifest[
                    "registry_sha256"
                ],

            "datasets":
                records,
        }

        return result

    except Exception:

        _cleanup_temp_paths(
            temporary_paths
        )

        raise


# ============================================================
# MANIFEST CONTRACT
# ============================================================


def _assert_manifest_contract(
    manifest: Mapping[str, Any],
) -> None:
    """
    Protect the known current registry separation.
    """

    dataset_count = int(
        manifest[
            "dataset_count"
        ]
    )

    synthetic_count = int(
        manifest[
            "synthetic_dataset_count"
        ]
    )

    ground_truth_count = int(
        manifest[
            "ground_truth_dataset_count"
        ]
    )

    if dataset_count != EXPECTED_DATASET_COUNT:

        raise AssertionError(
            f"Manifest dataset count mismatch: "
            f"{dataset_count}"
        )

    if (
        synthetic_count
        !=
        EXPECTED_SYNTHETIC_DATASET_COUNT
    ):

        raise AssertionError(
            f"Manifest synthetic dataset count mismatch: "
            f"{synthetic_count}"
        )

    if (
        ground_truth_count
        !=
        EXPECTED_GROUND_TRUTH_DATASET_COUNT
    ):

        raise AssertionError(
            f"Manifest ground-truth dataset count mismatch: "
            f"{ground_truth_count}"
        )

    logical_paths = {
        record[
            "logical_path"
        ]
        for record
        in manifest[
            "datasets"
        ]
    }

    required_runtime_causal = {
        "synthetic/causal/manufacturing_timeseries",
        "synthetic/causal/mobility_timeseries",
        "synthetic/causal/vehicle_telematics_timeseries",
    }

    required_causal_truth = {
        "ground_truth/causal/manufacturing_causal_edges",
        "ground_truth/causal/mobility_causal_edges",
    }

    required_simulation_truth = {
        "ground_truth/simulations/"
        "manufacturing_scenario_events",

        "ground_truth/simulations/"
        "manufacturing_scenario_expectations",

        "ground_truth/simulations/"
        "mobility_scenario_events",

        "ground_truth/simulations/"
        "mobility_scenario_expectations",
    }

    required_copilot_truth = {
        "ground_truth/copilot/"
        "copilot_eval_ground_truth",
    }

    required_paths = (
        required_runtime_causal
        |
        required_causal_truth
        |
        required_simulation_truth
        |
        required_copilot_truth
    )

    missing = (
        required_paths
        -
        logical_paths
    )

    if missing:

        raise AssertionError(
            "Manifest missing protected datasets: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    forbidden_runtime_truth_paths = {
        "synthetic/causal/manufacturing_causal_edges",
        "synthetic/causal/mobility_causal_edges",

        "synthetic/causal/manufacturing_scenario_events",
        "synthetic/causal/manufacturing_scenario_expectations",

        "synthetic/causal/mobility_scenario_events",
        "synthetic/causal/mobility_scenario_expectations",

        "synthetic/copilot/copilot_eval_ground_truth",
    }

    leaked_paths = (
        logical_paths
        &
        forbidden_runtime_truth_paths
    )

    if leaked_paths:

        raise AssertionError(
            "Evaluator truth leaked into runtime export paths: "
            +
            ", ".join(
                sorted(
                    leaked_paths
                )
            )
        )


# ============================================================
# FULL GENERATE -> VALIDATE -> EXPORT
# ============================================================


def export_all(
    *,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Complete CSV workflow:

        load config
            ->
        generate registry
            ->
        validate SAME registry
            ->
        export CSV
            ->
        write manifest

    PostgreSQL is not touched.
    """

    generation = (
        load_generation_config()
    )

    distributions = (
        load_distribution_config()
    )

    scenarios = (
        load_scenario_config()
    )

    if verbose:

        print(
            "\n"
            "============================================================\n"
            "MAHINDRA AI NEXUS - CSV EXPORT\n"
            "============================================================"
        )

        print(
            "Seed:",
            generation.get(
                "seed"
            ),
        )

        print(
            "Config version:",
            generation.get(
                "config_version"
            ),
        )

        print(
            "Generator version:",
            generation.get(
                "generator_version"
            ),
        )

        print(
            "CSV enabled:",
            _csv_enabled(
                generation
            ),
        )

        print(
            "Overwrite existing CSV:",
            _overwrite_enabled(
                generation
            ),
        )

    # ========================================================
    # GENERATE ONCE
    # ========================================================

    if verbose:

        print(
            "\n[1/3] Generating complete registry in memory..."
        )

    registry = generate_all(
        generation=
            generation,

        distributions=
            distributions,

        scenarios=
            scenarios,

        verbose=False,
    )

    if verbose:

        print(
            "PASS - registry generated"
        )

    # ========================================================
    # VALIDATE SAME REGISTRY
    # ========================================================

    if verbose:

        print(
            "\n[2/3] Validating registry before export..."
        )

    validation_report = validate_all(
        registry=
            registry,

        generation=
            generation,

        distributions=
            distributions,

        scenarios=
            scenarios,

        verbose=False,
    )

    if (
        validation_report.get(
            "status"
        )
        !=
        "PASS"
    ):

        raise RuntimeError(
            "Validation did not return PASS"
        )

    if verbose:

        print(
            "PASS -",
            validation_report[
                "registered_dataframes"
            ],
            "DataFrames /",
            validation_report[
                "registered_rows"
            ],
            "rows validated",
        )

    # ========================================================
    # EXPORT
    # ========================================================

    if verbose:

        print(
            "\n[3/3] Exporting validated registry..."
        )

    export_report = export_registry_to_csv(
        registry=
            registry,

        generation=
            generation,

        verbose=
            verbose,
    )

    export_report[
        "validation_status"
    ] = validation_report[
        "status"
    ]

    return export_report


# ============================================================
# REPORT
# ============================================================


def print_export_report(
    report: Mapping[str, Any],
) -> None:

    print(
        "\n"
        "============================================================\n"
        "CSV EXPORT SUMMARY\n"
        "============================================================"
    )

    print(
        "Validation status:",
        report[
            "validation_status"
        ],
    )

    print(
        "CSV datasets:",
        report[
            "dataset_count"
        ],
    )

    print(
        "Synthetic CSVs:",
        report[
            "synthetic_dataset_count"
        ],
    )

    print(
        "Ground-truth CSVs:",
        report[
            "ground_truth_dataset_count"
        ],
    )

    print(
        "Total exported rows:",
        report[
            "total_rows"
        ],
    )

    print(
        "New files written:",
        report[
            "written"
        ],
    )

    print(
        "Files replaced:",
        report[
            "replaced"
        ],
    )

    print(
        "Identical files skipped:",
        report[
            "skipped_identical"
        ],
    )

    print(
        "Stale CSVs removed:",
        report[
            "stale_csvs_removed"
        ],
    )

    print(
        "Manifest status:",
        report[
            "manifest_status"
        ],
    )

    print(
        "Manifest:",
        report[
            "manifest_path"
        ],
    )

    print(
        "Registry SHA-256:",
        report[
            "registry_sha256"
        ],
    )

    print(
        "\n"
        "============================================================\n"
        "EXPORT CSV: PASS\n"
        "============================================================"
    )

    print(
        "Validated DataFrames were exported deterministically."
    )

    print(
        "Runtime and evaluator ground truth remain separated."
    )

    print(
        "No PostgreSQL writes were performed."
    )

    print(
        "\nNext stage: validate exported CSV artifacts."
    )


# ============================================================
# CLI
# ============================================================


def main() -> None:

    report = export_all(
        verbose=True,
    )

    print_export_report(
        report
    )


if __name__ == "__main__":
    main()