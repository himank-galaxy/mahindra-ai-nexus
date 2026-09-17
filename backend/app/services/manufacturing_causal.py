"""Manufacturing causal-discovery orchestration and persistence.

This service powers the derived causal state behind the Mahindra
Warranty, Quality & Service Early-Warning Graph.

Pipeline
--------
PostgreSQL manufacturing observations
    ->
per-machine manufacturing panel
    ->
Tigramite PCMCI complete hypothesis family
    ->
Benjamini-Hochberg / effect-size / scope filtering
    ->
cross-machine stability aggregation
    ->
deterministic source/configuration signature
    ->
ai_state persistence

Important boundaries
--------------------
This service deliberately does NOT:

- read causal ground truth,
- read scenario ground truth,
- hardcode causal graph edges,
- interpret PCMCI scores as causal probabilities,
- attach warranty/service evidence,
- generate user-facing warnings.

Warranty claims, service events, supplier/batch lineage and operational
early-warning evidence are attached in a later layer.

Identical source observations + identical analysis configuration produce
the same signature and reuse persisted derived state rather than rerunning
PCMCI.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

import pandas as pd
from pandas.tseries.frequencies import to_offset
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.ai.causal.manufacturing_filter import (
    DEFAULT_MANUFACTURING_FILTER_CONFIG,
    ManufacturingFilterConfig,
    ManufacturingFilterResult,
    ManufacturingStableEdge,
    aggregate_manufacturing_stability,
    best_edge_per_pair,
    filter_manufacturing_tests,
)
from app.ai.causal.manufacturing_loader import (
    DEFAULT_HISTORY_HOURS,
    MANUFACTURING_METRICS,
    detect_raw_frequency_minutes,
    fetch_raw_records,
)
from app.ai.causal.manufacturing_panel import (
    DEFAULT_MANUFACTURING_PANEL_CONFIG,
    MANUFACTURING_METRIC_AGGREGATIONS,
    ManufacturingPanelConfig,
    build_manufacturing_panel,
)
from app.ai.causal.pcmci_engine import (
    pcmci_tests_as_causal_discovery_tests,
    run_lpcmci_tests,
    run_pcmci_tests,
)
from app.core.logging import get_logger
from app.models.manufacturing_causal_state import (
    ManufacturingCausalEdge,
    ManufacturingCausalRun,
)
from app.services.base import BaseService

logger = get_logger(__name__)

# ============================================================================
# ANALYSIS CONTRACT
# ============================================================================

ORCHESTRATOR_VERSION = "2.0.0"

CausalAlgorithm = Literal["lpcmci", "pcmci"]

DEFAULT_ALGORITHM: CausalAlgorithm = "lpcmci"

DEFAULT_TEST_CONTEMPORANEOUS = True


def _algorithm_label(
    algorithm: CausalAlgorithm,
) -> str:
    """Persisted-run algorithm string, keyed off the actual engine used."""

    prefix = (
        "LPCMCI"
        if algorithm == "lpcmci"
        else "PCMCI"
    )

    return (
        f"{prefix}-ParCorr+BH-FDR+cross-machine-stability"
    )


DEFAULT_TAU_MIN = 1

DEFAULT_CAUSAL_HORIZON_MINUTES = 180

# --- Algorithm-specific tau_max/pc_alpha defaults ---------------------------
#
# PCMCI (rollback/comparison): the original, established production values.
# Preserved exactly -- changing these would silently alter rollback
# behavior, defeating its purpose as a like-for-like comparison baseline.
PCMCI_DEFAULT_TAU_MAX = 12

PCMCI_DEFAULT_PC_ALPHA = 0.05

# LPCMCI (production default): matches the reference standalone pipeline's
# configuration (max_lag=2, pc_alpha=0.10). LPCMCI's ancestral/non-ancestral
# search cost grows far faster with tau_max than PCMCI's single PC-stable
# pass -- running LPCMCI in production with PCMCI's tau_max=12 window is
# what made the first live cutover attempt exceed 45 minutes without a
# single machine finishing.
LPCMCI_DEFAULT_TAU_MAX = 2

LPCMCI_DEFAULT_PC_ALPHA = 0.10

# Backward-compatible aliases: pre-existing callers/tests reference these
# unqualified names directly, and they have always meant "PCMCI's default"
# (LPCMCI did not exist when they were introduced).
DEFAULT_TAU_MAX = PCMCI_DEFAULT_TAU_MAX

DEFAULT_PC_ALPHA = PCMCI_DEFAULT_PC_ALPHA


def effective_tau_max(
    algorithm: CausalAlgorithm,
    tau_max: int | None,
) -> int:
    """
    Resolve the tau_max actually used for one analysis.

    An explicitly supplied ``tau_max`` (not None) is always honored
    unchanged, regardless of algorithm -- algorithm-specific values are
    defaults only, never a silent override of a caller's explicit choice.
    """

    if tau_max is not None:
        return tau_max

    return (
        LPCMCI_DEFAULT_TAU_MAX
        if algorithm == "lpcmci"
        else PCMCI_DEFAULT_TAU_MAX
    )


def effective_pc_alpha(
    algorithm: CausalAlgorithm,
    pc_alpha: float | None,
) -> float:
    """Resolve the pc_alpha actually used for one analysis. See effective_tau_max."""

    if pc_alpha is not None:
        return pc_alpha

    return (
        LPCMCI_DEFAULT_PC_ALPHA
        if algorithm == "lpcmci"
        else PCMCI_DEFAULT_PC_ALPHA
    )


def effective_tau_min(
    algorithm: CausalAlgorithm,
    test_contemporaneous: bool,
) -> int:
    """
    Resolve the true minimum lag tested for one analysis.

    LPCMCI with test_contemporaneous=True tests lag 0 (contemporaneous
    links) in addition to lagged ones -- this is LPCMCI's whole reason for
    existing over PCMCI (see run_lpcmci_tests' docstring). Persisting a
    fixed tau_min=1 regardless of algorithm was a correctness bug: it
    understated what LPCMCI actually tested and, since tau_min feeds the
    signature, meant two runs that tested genuinely different lag ranges
    could otherwise be mistaken for identical configurations.

        LPCMCI + test_contemporaneous=True  -> 0
        LPCMCI + test_contemporaneous=False -> 1
        PCMCI                                -> 1 (never tests lag 0)
    """

    if algorithm == "lpcmci" and test_contemporaneous:
        return 0

    return 1


# These lineage fields affect persisted evidence and therefore participate
# in the deterministic source signature.
SIGNATURE_LINEAGE_FIELDS = (
    "plant_id",
    "plant_name",
    "production_line_id",
    "production_line_name",
    "line_type",
    "machine_id",
    "machine_name",
    "production_batch_id",
    "vehicle_model_id",
    "vehicle_model_name",
    "supplier_lot_id",
)


# ============================================================================
# PUBLIC RESULT MODELS
# ============================================================================


@dataclass(frozen=True)
class ManufacturingCausalEdgeResult:
    """One persisted cross-machine stable causal candidate."""

    source_metric: str
    target_metric: str

    scope: str

    consensus_sign: str

    edge_orientation: str
    consensus_edge_mark: str
    mark_agreement: float

    eligible_machines: int
    recurring_machines: int

    recurrence_fraction: float
    sign_agreement: float

    mean_abs_score: float
    median_abs_score: float

    best_q_value: float

    observed_lags: tuple[int, ...]
    observed_lag_minutes: tuple[int, ...]
    machine_ids: tuple[str, ...]

    evidence: tuple[
        dict[str, Any],
        ...,
    ]


@dataclass(frozen=True)
class ManufacturingCausalAnalysisResult:
    """Persisted result of one manufacturing causal-analysis window."""

    run_id: uuid.UUID

    signature: str

    reused: bool

    source_from: datetime
    source_to: datetime

    source_rows: int

    raw_frequency_minutes: float
    analysis_frequency_minutes: int
    analysis_window_hours: float

    analytical_rows: int
    variables_used: int

    tau_min: int
    tau_max: int
    maximum_lag_minutes: int

    machines_requested: int
    machines_evaluated: int

    candidate_pairs: int
    stable_edge_count: int

    algorithm: str
    algorithm_version: str | None

    parameters: dict[str, Any]

    machine_ids: tuple[str, ...]

    computed_at: datetime

    edges: tuple[
        ManufacturingCausalEdgeResult,
        ...,
    ]


@dataclass(frozen=True)
class _MachineAnalysis:
    """Filtered machine result plus panel/runtime diagnostics."""

    filtered: ManufacturingFilterResult

    analytical_rows: int
    variables_used: tuple[str, ...]

    dropped_metrics: dict[str, str]
    missing_intervals: dict[str, int]
    transformed_metrics: tuple[str, ...]

    duplicate_records_removed: int

    panel_runtime_seconds: float
    pcmci_runtime_seconds: float


# ============================================================================
# TIMESTAMP / VERSION HELPERS
# ============================================================================


def _normalise_timestamp(
    value: Any,
) -> datetime:
    """Convert source timestamps to timezone-aware UTC datetimes."""

    timestamp = pd.Timestamp(
        value
    )

    if pd.isna(
        timestamp
    ):
        raise ValueError(
            "Manufacturing source contains an invalid timestamp."
        )

    timestamp = (
        timestamp.tz_localize(
            "UTC"
        )
        if timestamp.tzinfo is None
        else timestamp.tz_convert(
            "UTC"
        )
    )

    return timestamp.to_pydatetime()


def _timestamp_text(
    value: Any,
) -> str:
    """Canonical timestamp representation for hashing."""

    return _normalise_timestamp(
        value
    ).isoformat()


def _package_version(
    package_name: str,
) -> str:
    """Return installed package version without weakening runtime startup."""

    try:
        return version(
            package_name
        )
    except PackageNotFoundError:
        return "unknown"


def _algorithm_version() -> str:
    """Version string persisted beside each causal run."""

    return (
        f"orchestrator={ORCHESTRATOR_VERSION};"
        f"tigramite={_package_version('tigramite')}"
    )


def _analysis_frequency_minutes(
    value: str,
) -> int:
    """Convert a configured analytical interval to whole minutes."""

    try:
        duration = to_offset(
            value
        )
        minutes = (
            duration.nanos
            / 60_000_000_000
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "analysis_frequency must be a valid pandas duration."
        ) from exc

    if (
        minutes <= 0.0
        or not minutes.is_integer()
    ):
        raise ValueError(
            "analysis_frequency must be a positive whole-minute duration."
        )

    return int(
        minutes
    )


# ============================================================================
# SOURCE CONTRACT
# ============================================================================


def _group_records_by_machine(
    records: Sequence[
        dict[str, Any]
    ],
) -> dict[
    str,
    list[
        dict[str, Any]
    ],
]:
    """Group generic causal records by manufacturing machine."""

    grouped: dict[
        str,
        list[
            dict[str, Any]
        ],
    ] = defaultdict(
        list
    )

    for record in records:
        machine_id = str(
            record.get(
                "entity",
                "",
            )
        ).strip()

        if not machine_id:
            raise ValueError(
                "Manufacturing causal record is missing entity."
            )

        record_machine_id = str(
            record.get(
                "machine_id",
                "",
            )
        ).strip()

        if (
            record_machine_id
            and record_machine_id
            != machine_id
        ):
            raise ValueError(
                "Manufacturing causal record entity/machine_id mismatch: "
                f"entity={machine_id!r}, "
                f"machine_id={record_machine_id!r}"
            )

        grouped[
            machine_id
        ].append(
            record
        )

    return dict(
        grouped
    )


def _source_row_keys(
    records: Sequence[
        dict[str, Any]
    ],
) -> set[
    tuple[
        str,
        str,
    ]
]:
    """Return canonical wide-row grain: machine x timestamp."""

    return {
        (
            str(
                record["entity"]
            ),
            _timestamp_text(
                record["timestamp"]
            ),
        )
        for record in records
    }


def _source_window(
    records: Sequence[
        dict[str, Any]
    ],
) -> tuple[
    datetime,
    datetime,
]:
    """Return earliest/latest source observation timestamps."""

    if not records:
        raise ValueError(
            "No manufacturing causal source records were loaded."
        )

    timestamps = [
        _normalise_timestamp(
            record[
                "timestamp"
            ]
        )
        for record in records
    ]

    return (
        min(
            timestamps
        ),
        max(
            timestamps
        ),
    )


# ============================================================================
# SIGNATURE
# ============================================================================


def _analysis_parameters(
    *,
    machine_ids: Sequence[str],
    observations: int | None,
    history_hours: float,
    raw_frequency_minutes: float,
    tau_max: int,
    pc_alpha: float,
    force_include_metrics: Sequence[str] | None,
    panel_config: ManufacturingPanelConfig,
    filter_config: ManufacturingFilterConfig,
    analysis_end: datetime | None = None,
    algorithm: CausalAlgorithm = DEFAULT_ALGORITHM,
    test_contemporaneous: bool = DEFAULT_TEST_CONTEMPORANEOUS,
    algorithm_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create JSON-safe configuration persisted with each causal run.

    ``algorithm``/``test_contemporaneous``/``algorithm_config`` participate
    in the returned dict (and therefore the source signature computed from
    it) specifically so switching algorithm always produces a fresh run
    rather than reusing a persisted run computed under a different engine.
    """

    return {
        "orchestrator_version": ORCHESTRATOR_VERSION,
        "algorithm": algorithm,
        "test_contemporaneous": (
            test_contemporaneous
            if algorithm == "lpcmci"
            else None
        ),
        "algorithm_config": dict(
            algorithm_config or {}
        ),
        "machine_ids": sorted(
            {
                str(
                    machine_id
                )
                for machine_id
                in machine_ids
            }
        ),
        "source_table": "manufacturing_timeseries",
        "raw_frequency_minutes": raw_frequency_minutes,
        "analysis_frequency": (
            panel_config.analysis_frequency
        ),
        "analysis_frequency_minutes": (
            _analysis_frequency_minutes(
                panel_config.analysis_frequency
            )
        ),
        "analysis_window_hours": history_hours,
        "analysis_end": (
            _timestamp_text(analysis_end)
            if analysis_end is not None else None
        ),
        "legacy_observations_per_machine": observations,
        "tau_min": effective_tau_min(
            algorithm,
            test_contemporaneous,
        ),
        "tau_max": tau_max,
        "maximum_lag_minutes": (
            tau_max
            * _analysis_frequency_minutes(
                panel_config.analysis_frequency
            )
        ),
        "causal_metrics": list(
            MANUFACTURING_METRICS
        ),
        "metric_aggregations": dict(
            MANUFACTURING_METRIC_AGGREGATIONS
        ),
        "pc_alpha": pc_alpha,
        "force_include_metrics": sorted(
            {
                str(
                    metric
                )
                for metric
                in (
                    force_include_metrics
                    or ()
                )
            }
        ),
        "panel": asdict(
            panel_config
        ),
        "filter": asdict(
            filter_config
        ),
    }


def _record_signature_key(
    record: dict[str, Any],
) -> tuple[
    str,
    str,
    str,
]:
    """Stable source-record ordering for deterministic hashing."""

    return (
        _timestamp_text(
            record[
                "timestamp"
            ]
        ),
        str(
            record[
                "entity"
            ]
        ),
        str(
            record[
                "metric"
            ]
        ),
    )


def _source_signature(
    records: Sequence[
        dict[str, Any]
    ],
    *,
    parameters: dict[str, Any],
) -> str:
    """Hash actual observations, lineage and analysis configuration."""

    digest = sha256()

    configuration_json = json.dumps(
        parameters,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        allow_nan=False,
    )

    digest.update(
        configuration_json.encode(
            "utf-8"
        )
    )

    digest.update(
        b"\n"
    )

    for record in sorted(
        records,
        key=_record_signature_key,
    ):
        try:
            value = float(
                record[
                    "value"
                ]
            )
        except (
            TypeError,
            ValueError,
            KeyError,
        ) as exc:
            raise ValueError(
                "Manufacturing causal source contains "
                "a non-numeric metric value."
            ) from exc

        parts = [
            _timestamp_text(
                record[
                    "timestamp"
                ]
            ),
            str(
                record[
                    "entity"
                ]
            ),
            str(
                record[
                    "metric"
                ]
            ),

            # Exact deterministic float representation.
            value.hex(),
        ]

        parts.extend(
            ""
            if record.get(
                field
            ) is None
            else str(
                record.get(
                    field
                )
            )
            for field
            in SIGNATURE_LINEAGE_FIELDS
        )

        digest.update(
            "\x1f".join(
                parts
            ).encode(
                "utf-8"
            )
        )

        digest.update(
            b"\n"
        )

    return digest.hexdigest()


# ============================================================================
# MACHINE-LEVEL ANALYSIS
# ============================================================================


def _analyse_machine(
    machine_id: str,
    records: Sequence[
        dict[str, Any]
    ],
    *,
    algorithm: CausalAlgorithm,
    tau_max: int,
    pc_alpha: float,
    test_contemporaneous: bool,
    algorithm_config: dict[str, Any] | None,
    panel_config: ManufacturingPanelConfig,
    filter_config: ManufacturingFilterConfig,
) -> _MachineAnalysis:
    """Build one machine panel, run PCMCI/LPCMCI and apply domain filtering."""

    panel_started = time.perf_counter()

    panel_result = build_manufacturing_panel(
        records,
        config=panel_config,
    )

    panel = panel_result.panel

    if panel.empty:
        raise ValueError(
            "Manufacturing panel is empty after preprocessing "
            f"for machine {machine_id}."
        )

    if len(
        panel.columns
    ) < 2:
        raise ValueError(
            "Manufacturing PCMCI requires at least two "
            "surviving variables after preprocessing for "
            f"machine {machine_id}. "
            f"Surviving={len(panel.columns)}, "
            f"dropped={len(panel_result.dropped_metrics)}"
        )

    if len(
        panel.index
    ) <= tau_max:
        raise ValueError(
            "Manufacturing panel does not contain enough "
            "observations for configured tau_max. "
            f"machine={machine_id}, "
            f"rows={len(panel.index)}, "
            f"tau_max={tau_max}"
        )

    if (
        len(panel.index)
        < panel_config.min_panel_observations
    ):
        raise ValueError(
            "Manufacturing panel does not meet the configured "
            "minimum analytical duration. "
            f"machine={machine_id}, "
            f"rows={len(panel.index)}, "
            "minimum="
            f"{panel_config.min_panel_observations}"
        )

    panel_runtime_seconds = (
        time.perf_counter()
        - panel_started
    )

    causal_discovery_started = time.perf_counter()

    column_names = tuple(
        str(column)
        for column in panel.columns
    )

    if algorithm == "lpcmci":
        effective_tau_min_value = (
            0
            if test_contemporaneous
            else 1
        )

        logger.info(
            "causal_lpcmci_input_ready",
            domain="manufacturing",
            asset_id=machine_id,
            analytical_rows=len(
                panel_result.panel
            ),
            variables_used=len(
                column_names
            ),
            variable_names=list(
                column_names
            ),
            tau_min=effective_tau_min_value,
            tau_max=tau_max,
            pc_alpha=pc_alpha,
            test_contemporaneous=test_contemporaneous,
            effective_algorithm_config=dict(
                algorithm_config or {}
            ),
            panel_runtime_seconds=round(
                panel_runtime_seconds,
                3,
            ),
            matrix_shape=(
                f"{len(panel_result.panel)}x{len(column_names)}"
            ),
        )

        tests = run_lpcmci_tests(
            panel.to_numpy(
                dtype=float
            ),
            column_names,
            tau_max=tau_max,
            pc_alpha=pc_alpha,
            test_contemporaneous=test_contemporaneous,
            **(algorithm_config or {}),
        )

        causal_discovery_runtime_seconds = (
            time.perf_counter()
            - causal_discovery_started
        )

        logger.info(
            "causal_lpcmci_discovery_completed",
            domain="manufacturing",
            asset_id=machine_id,
            analytical_rows=len(
                panel_result.panel
            ),
            variables_used=len(
                column_names
            ),
            discovery_runtime_seconds=round(
                causal_discovery_runtime_seconds,
                3,
            ),
            raw_pag_relationship_count=len(
                tests
            ),
        )

        effective_min_lag = effective_tau_min_value
    else:
        raw_tests = run_pcmci_tests(
            panel.to_numpy(
                dtype=float
            ),
            column_names,
            tau_max=tau_max,
            pc_alpha=pc_alpha,
        )

        tests = pcmci_tests_as_causal_discovery_tests(
            raw_tests
        )

        causal_discovery_runtime_seconds = (
            time.perf_counter()
            - causal_discovery_started
        )

        effective_min_lag = 1

    if not tests:
        raise ValueError(
            "Causal discovery returned no finite non-self tests "
            f"for machine {machine_id}."
        )

    filtered = filter_manufacturing_tests(
        tests,
        panel_result.metadata,
        config=replace(
            filter_config,
            min_lag=effective_min_lag,
            # PCMCI (rollback/comparison) reproduces prior production
            # behavior exactly, including BH-FDR over its complete tested
            # family. LPCMCI's tests are already algorithm-selected (see
            # filter_manufacturing_tests' apply_fdr_correction docstring),
            # so the production default path never applies it.
            apply_fdr_correction=(algorithm == "pcmci"),
        ),
    )

    return _MachineAnalysis(
        filtered=filtered,
        analytical_rows=len(
            panel.index
        ),
        variables_used=tuple(
            str(column)
            for column in panel.columns
        ),
        dropped_metrics=dict(
            panel_result.dropped_metrics
        ),
        missing_intervals=dict(
            panel_result.missing_intervals
        ),
        transformed_metrics=tuple(
            panel_result.transformed_metrics
        ),
        duplicate_records_removed=(
            panel_result.duplicate_records_removed
        ),
        panel_runtime_seconds=(
            panel_runtime_seconds
        ),
        pcmci_runtime_seconds=(
            causal_discovery_runtime_seconds
        ),
    )


# ============================================================================
# STABLE-EDGE EVIDENCE
# ============================================================================


def _stable_edge_evidence(
    stable_edge: ManufacturingStableEdge,
    machine_results: Sequence[
        ManufacturingFilterResult
    ],
    *,
    analysis_frequency_minutes: int,
) -> list[
    dict[str, Any]
]:
    """Build machine-level audit evidence behind one stable edge."""

    pair = (
        stable_edge.source_metric,
        stable_edge.target_metric,
    )

    supporting_machine_ids = set(
        stable_edge.machine_ids
    )

    evidence: list[
        dict[str, Any]
    ] = []

    for machine_result in sorted(
        machine_results,
        key=lambda result: result.machine_id,
    ):
        if (
            machine_result.machine_id
            not in supporting_machine_ids
        ):
            continue

        best_edges = best_edge_per_pair(
            machine_result.accepted_edges
        )

        edge = best_edges.get(
            pair
        )

        if edge is None:
            raise RuntimeError(
                "Stable manufacturing edge references a machine "
                "without corresponding filtered evidence. "
                f"machine={machine_result.machine_id}, "
                f"pair={pair}"
            )

        evidence.append(
            {
                "machine_id": edge.machine_id,

                "plant_id": edge.plant_id,
                "plant_name": edge.plant_name,

                "production_line_id": (
                    edge.production_line_id
                ),

                "production_line_name": (
                    edge.production_line_name
                ),

                "line_type": edge.line_type,

                "lag": int(
                    edge.lag
                ),

                "lag_steps": int(
                    edge.lag
                ),

                "lag_minutes": int(
                    edge.lag
                    * analysis_frequency_minutes
                ),

                "score": float(
                    edge.score
                ),

                "p_value": float(
                    edge.p_value
                ),

                "q_value": float(
                    edge.q_value
                ),

                "sign": edge.sign,

                "edge_mark": edge.edge_mark,

                "edge_orientation": edge.edge_orientation,
            }
        )

    if (
        len(
            evidence
        )
        != stable_edge.recurring_machines
    ):
        raise RuntimeError(
            "Stable manufacturing edge evidence count mismatch: "
            f"expected={stable_edge.recurring_machines}, "
            f"actual={len(evidence)}, "
            f"pair={pair}"
        )

    return evidence


# ============================================================================
# ORM -> PUBLIC RESULT
# ============================================================================


def _edge_result(
    row: ManufacturingCausalEdge,
    *,
    analysis_frequency_minutes: int,
) -> ManufacturingCausalEdgeResult:
    """Convert persisted ORM state to an immutable service result."""

    return ManufacturingCausalEdgeResult(
        source_metric=row.source_metric,
        target_metric=row.target_metric,

        scope=row.scope,

        consensus_sign=row.consensus_sign,

        edge_orientation=row.edge_orientation,

        consensus_edge_mark=row.consensus_edge_mark,

        mark_agreement=float(
            row.mark_agreement
        ),

        eligible_machines=(
            row.eligible_machines
        ),

        recurring_machines=(
            row.recurring_machines
        ),

        recurrence_fraction=float(
            row.recurrence_fraction
        ),

        sign_agreement=float(
            row.sign_agreement
        ),

        mean_abs_score=float(
            row.mean_abs_score
        ),

        median_abs_score=float(
            row.median_abs_score
        ),

        best_q_value=float(
            row.best_q_value
        ),

        observed_lags=tuple(
            int(
                lag
            )
            for lag
            in row.observed_lags
        ),

        observed_lag_minutes=tuple(
            int(lag)
            * analysis_frequency_minutes
            for lag
            in row.observed_lags
        ),

        machine_ids=tuple(
            str(
                machine_id
            )
            for machine_id
            in row.machine_ids
        ),

        evidence=tuple(
            dict(
                item
            )
            for item
            in row.evidence
        ),
    )


def _analysis_result(
    run: ManufacturingCausalRun,
    edges: Sequence[
        ManufacturingCausalEdge
    ],
    *,
    reused: bool,
) -> ManufacturingCausalAnalysisResult:
    """Convert persisted run + edges into the public service contract."""

    parameters = dict(
        run.parameters
    )

    panel_parameters = dict(
        parameters.get(
            "panel",
            {},
        )
    )

    analysis_frequency = parameters.get(
        "analysis_frequency"
    ) or panel_parameters.get(
        "analysis_frequency"
    ) or panel_parameters.get(
        "resample_interval",
        "1h",
    )

    analysis_minutes = int(
        parameters.get(
            "analysis_frequency_minutes",
            _analysis_frequency_minutes(
                str(analysis_frequency)
            ),
        )
    )

    raw_minutes = float(
        parameters.get(
            "raw_frequency_minutes",
            analysis_minutes,
        )
    )

    tau_min = int(
        parameters.get(
            "tau_min",
            DEFAULT_TAU_MIN,
        )
    )

    tau_max = int(
        parameters.get(
            "tau_max",
            DEFAULT_TAU_MAX,
        )
    )

    diagnostics = dict(
        parameters.get(
            "diagnostics",
            {},
        )
    )

    observations = parameters.get(
        "observations_per_machine"
    ) or parameters.get(
        "legacy_observations_per_machine"
    )

    default_window_hours = (
        float(observations)
        * raw_minutes
        / 60.0
        if observations
        else DEFAULT_HISTORY_HOURS
    )

    return ManufacturingCausalAnalysisResult(
        run_id=run.id,

        signature=run.signature,

        reused=reused,

        source_from=run.source_from,
        source_to=run.source_to,

        source_rows=run.source_rows,

        raw_frequency_minutes=raw_minutes,
        analysis_frequency_minutes=(
            analysis_minutes
        ),
        analysis_window_hours=float(
            parameters.get(
                "analysis_window_hours",
                default_window_hours,
            )
        ),

        analytical_rows=int(
            diagnostics.get(
                "analytical_rows_per_machine",
                0,
            )
        ),
        variables_used=int(
            diagnostics.get(
                "maximum_variables_used",
                0,
            )
        ),

        tau_min=tau_min,
        tau_max=tau_max,
        maximum_lag_minutes=int(
            parameters.get(
                "maximum_lag_minutes",
                tau_max
                * analysis_minutes,
            )
        ),

        machines_requested=(
            run.machines_requested
        ),

        machines_evaluated=(
            run.machines_evaluated
        ),

        candidate_pairs=(
            run.candidate_pairs
        ),

        stable_edge_count=(
            run.stable_edge_count
        ),

        algorithm=run.algorithm,

        algorithm_version=(
            run.algorithm_version
        ),

        parameters=parameters,

        machine_ids=tuple(
            str(
                machine_id
            )
            for machine_id
            in run.machine_ids
        ),

        computed_at=run.computed_at,

        edges=tuple(
            _edge_result(
                edge,
                analysis_frequency_minutes=(
                    analysis_minutes
                ),
            )
            for edge
            in edges
        ),
    )


# ============================================================================
# SERVICE
# ============================================================================


class ManufacturingCausalService(
    BaseService
):
    """Run, reuse and read persisted manufacturing causal evidence."""

    async def _load_run_edges(
        self,
        run: ManufacturingCausalRun,
        *,
        reused: bool,
    ) -> ManufacturingCausalAnalysisResult:
        """Load persisted stable edges for one causal run."""

        edge_rows = (
            await self._session.execute(
                select(
                    ManufacturingCausalEdge
                )
                .where(
                    ManufacturingCausalEdge.run_id
                    == run.id
                )
                .order_by(
                    ManufacturingCausalEdge
                    .recurrence_fraction
                    .desc(),

                    ManufacturingCausalEdge
                    .sign_agreement
                    .desc(),

                    ManufacturingCausalEdge
                    .mean_abs_score
                    .desc(),

                    ManufacturingCausalEdge
                    .best_q_value
                    .asc(),

                    ManufacturingCausalEdge
                    .source_metric
                    .asc(),

                    ManufacturingCausalEdge
                    .target_metric
                    .asc(),
                )
            )
        ).scalars().all()

        return _analysis_result(
            run,
            edge_rows,
            reused=reused,
        )

    async def _load_by_signature(
        self,
        signature: str,
        *,
        reused: bool,
    ) -> ManufacturingCausalAnalysisResult | None:
        """Load a previously persisted run by deterministic signature."""

        run = (
            await self._session.execute(
                select(
                    ManufacturingCausalRun
                )
                .where(
                    ManufacturingCausalRun.signature
                    == signature
                )
            )
        ).scalar_one_or_none()

        if run is None:
            return None

        return await self._load_run_edges(
            run,
            reused=reused,
        )

    async def get_latest(
        self,
    ) -> ManufacturingCausalAnalysisResult | None:
        """Return the most recently computed manufacturing causal state."""

        run = (
            await self._session.execute(
                select(
                    ManufacturingCausalRun
                )
                .order_by(
                    ManufacturingCausalRun
                    .computed_at
                    .desc(),
                    ManufacturingCausalRun
                    .id
                    .desc(),
                )
                .limit(
                    1
                )
            )
        ).scalar_one_or_none()

        if run is None:
            return None

        return await self._load_run_edges(
            run,
            reused=True,
        )

    async def get_or_run(
        self,
        machine_ids: Sequence[str],
        *,
        observations: int | None = None,
        history_hours: float = DEFAULT_HISTORY_HOURS,
        analysis_end: datetime | None = None,
        tau_max: int | None = None,
        pc_alpha: float | None = None,
        force_include_metrics: Sequence[str] | None = None,
        panel_config: ManufacturingPanelConfig = (
            DEFAULT_MANUFACTURING_PANEL_CONFIG
        ),
        filter_config: ManufacturingFilterConfig = (
            DEFAULT_MANUFACTURING_FILTER_CONFIG
        ),
        algorithm: CausalAlgorithm = DEFAULT_ALGORITHM,
        test_contemporaneous: bool = DEFAULT_TEST_CONTEMPORANEOUS,
        algorithm_config: dict[str, Any] | None = None,
    ) -> ManufacturingCausalAnalysisResult:
        """Return cached causal state or execute a new manufacturing analysis.

        ``algorithm`` selects LPCMCI (production default, handles latent
        confounders and contemporaneous links) or PCMCI (rollback/
        comparison only). Algorithm choice participates in the source
        signature, so switching it always triggers a fresh run.

        ``tau_max``/``pc_alpha`` default to None, which resolves to the
        algorithm-specific production default (see effective_tau_max/
        effective_pc_alpha) -- LPCMCI's is deliberately much cheaper
        (tau_max=2, pc_alpha=0.10, matching the reference pipeline) than
        PCMCI rollback's established legacy values (tau_max=12,
        pc_alpha=0.05), since LPCMCI's search cost grows far faster with
        tau_max. An explicitly supplied value is always honored as-is
        regardless of algorithm -- these defaults never silently override
        a caller's explicit choice.
        """

        if algorithm not in (
            "lpcmci",
            "pcmci",
        ):
            raise ValueError(
                "algorithm must be 'lpcmci' or 'pcmci'."
            )

        tau_max = effective_tau_max(
            algorithm,
            tau_max,
        )

        pc_alpha = effective_pc_alpha(
            algorithm,
            pc_alpha,
        )

        job_started = time.perf_counter()

        if not isinstance(
            tau_max,
            int,
        ):
            raise TypeError(
                "tau_max must be an integer."
            )

        if tau_max < 1:
            raise ValueError(
                "tau_max must be at least 1."
            )

        try:
            history_hours_value = float(
                history_hours
            )
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "history_hours must be numeric."
            ) from exc

        if (
            history_hours_value <= 0.0
            or not math.isfinite(
                history_hours_value
            )
        ):
            raise ValueError(
                "history_hours must be a finite positive duration."
            )

        analysis_minutes = (
            _analysis_frequency_minutes(
                panel_config.analysis_frequency
            )
        )

        if not (
            0.0
            < pc_alpha
            <= 1.0
        ):
            raise ValueError(
                "pc_alpha must lie in (0, 1]."
            )

        # --------------------------------------------------------------------
        # PostgreSQL is the only runtime source.
        # --------------------------------------------------------------------

        records = await fetch_raw_records(
            self._session,
            entities=machine_ids,
            observations=observations,
            force_include_metrics=(
                force_include_metrics
            ),
            history_hours=(
                history_hours_value
            ),
            analysis_end=analysis_end,
        )

        if not records:
            raise ValueError(
                "No manufacturing observations were loaded."
            )

        raw_frequency_minutes = (
            detect_raw_frequency_minutes(
                records
            )
        )

        raw_steps_per_analysis_bucket = (
            analysis_minutes
            / raw_frequency_minutes
        )

        if (
            raw_steps_per_analysis_bucket < 1.0
            or not math.isclose(
                raw_steps_per_analysis_bucket,
                round(
                    raw_steps_per_analysis_bucket
                ),
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        ):
            raise ValueError(
                "analysis_frequency must be an integer multiple of "
                "the detected raw manufacturing cadence. "
                f"raw_minutes={raw_frequency_minutes}, "
                f"analysis_minutes={analysis_minutes}"
            )

        records_by_machine = (
            _group_records_by_machine(
                records
            )
        )

        effective_machine_ids = tuple(
            sorted(
                records_by_machine
            )
        )

        if not effective_machine_ids:
            raise ValueError(
                "No manufacturing machines were available "
                "for causal discovery."
            )

        # --------------------------------------------------------------------
        # Verify canonical wide-row source grain.
        # --------------------------------------------------------------------

        source_rows = len(
            _source_row_keys(
                records
            )
        )

        if observations is not None:
            expected_source_rows = (
                len(
                    effective_machine_ids
                )
                * observations
            )

            if (
                source_rows
                != expected_source_rows
            ):
                raise RuntimeError(
                    "Manufacturing source-row contract mismatch. "
                    f"expected={expected_source_rows}, "
                    f"actual={source_rows}"
                )

        source_from, source_to = (
            _source_window(
                records
            )
        )

        # --------------------------------------------------------------------
        # Deterministic cache key.
        # --------------------------------------------------------------------

        parameters = _analysis_parameters(
            machine_ids=(
                effective_machine_ids
            ),
            observations=observations,
            history_hours=history_hours_value,
            raw_frequency_minutes=(
                raw_frequency_minutes
            ),
            tau_max=tau_max,
            pc_alpha=pc_alpha,
            force_include_metrics=(
                force_include_metrics
            ),
            panel_config=panel_config,
            filter_config=filter_config,
            analysis_end=analysis_end,
            algorithm=algorithm,
            test_contemporaneous=test_contemporaneous,
            algorithm_config=algorithm_config,
        )

        signature = _source_signature(
            records,
            parameters=parameters,
        )

        existing = await self._load_by_signature(
            signature,
            reused=True,
        )

        if existing is not None:
            return existing

        # --------------------------------------------------------------------
        # Independent causal-discovery analysis per machine.
        #
        # CPU-heavy Tigramite work runs outside the async event-loop thread.
        # Machines are intentionally processed sequentially here; execution
        # policy/parallelism belongs in the later worker/scheduler layer.
        # --------------------------------------------------------------------

        machine_analyses: list[
            _MachineAnalysis
        ] = []

        asset_total = len(
            effective_machine_ids
        )

        successful_assets = 0

        domain_loop_started = time.perf_counter()

        for asset_index, machine_id in enumerate(
            effective_machine_ids,
            start=1,
        ):
            logger.info(
                "causal_asset_started",
                domain="manufacturing",
                algorithm=algorithm,
                asset_id=machine_id,
                asset_index=asset_index,
                asset_total=asset_total,
                tau_max=tau_max,
                pc_alpha=pc_alpha,
            )

            asset_started = time.perf_counter()

            result = await asyncio.to_thread(
                _analyse_machine,
                machine_id,
                records_by_machine[
                    machine_id
                ],
                algorithm=algorithm,
                tau_max=tau_max,
                pc_alpha=pc_alpha,
                test_contemporaneous=test_contemporaneous,
                algorithm_config=algorithm_config,
                panel_config=panel_config,
                filter_config=filter_config,
            )

            machine_analyses.append(
                result
            )

            successful_assets += 1

            logger.info(
                "causal_asset_completed",
                domain="manufacturing",
                algorithm=algorithm,
                asset_id=machine_id,
                asset_index=asset_index,
                asset_total=asset_total,
                runtime_seconds=round(
                    time.perf_counter()
                    - asset_started,
                    3,
                ),
                variables_used=len(
                    result.variables_used
                ),
                analytical_rows=result.analytical_rows,
                edge_count=len(
                    result.filtered.accepted_edges
                ),
            )

        logger.info(
            "causal_domain_completed",
            domain="manufacturing",
            algorithm=algorithm,
            asset_total=asset_total,
            successful_assets=successful_assets,
            total_runtime_seconds=round(
                time.perf_counter()
                - domain_loop_started,
                3,
            ),
            tau_max=tau_max,
            pc_alpha=pc_alpha,
        )

        if (
            len(
                machine_analyses
            )
            != len(
                effective_machine_ids
            )
        ):
            raise RuntimeError(
                "Manufacturing causal analysis did not evaluate "
                "every requested machine."
            )

        machine_results = [
            analysis.filtered
            for analysis
            in machine_analyses
        ]

        # --------------------------------------------------------------------
        # Cross-machine stability.
        # --------------------------------------------------------------------

        stability = (
            aggregate_manufacturing_stability(
                machine_results,
                config=filter_config,
            )
        )

        if (
            stability.machines_evaluated
            != len(
                effective_machine_ids
            )
        ):
            raise RuntimeError(
                "Manufacturing stability machine-count mismatch. "
                f"expected={len(effective_machine_ids)}, "
                f"actual={stability.machines_evaluated}"
            )

        computed_at = datetime.now(
            UTC
        )

        analytical_row_counts = [
            analysis.analytical_rows
            for analysis
            in machine_analyses
        ]

        variable_counts = [
            len(
                analysis.variables_used
            )
            for analysis
            in machine_analyses
        ]

        diagnostics = {
            "raw_rows_considered": source_rows,
            "raw_long_records_loaded": len(records),
            "analytical_rows_total": sum(
                analytical_row_counts
            ),
            "analytical_rows_per_machine": min(
                analytical_row_counts
            ),
            "maximum_analytical_rows_per_machine": max(
                analytical_row_counts
            ),
            "minimum_variables_used": min(
                variable_counts
            ),
            "maximum_variables_used": max(
                variable_counts
            ),
            "machine_panels": {
                machine_id: {
                    "analytical_rows": (
                        analysis.analytical_rows
                    ),
                    "variables_used": list(
                        analysis.variables_used
                    ),
                    "dropped_metrics": dict(
                        analysis.dropped_metrics
                    ),
                    "missing_intervals": dict(
                        analysis.missing_intervals
                    ),
                    "transformed_metrics": list(
                        analysis.transformed_metrics
                    ),
                    "duplicate_records_removed": (
                        analysis
                        .duplicate_records_removed
                    ),
                    "panel_runtime_seconds": round(
                        analysis.panel_runtime_seconds,
                        6,
                    ),
                    # Algorithm-neutral name; pcmci_runtime_seconds below
                    # is kept as a backward-compatible alias for existing
                    # consumers/tests (both hold the identical value).
                    "causal_discovery_runtime_seconds": round(
                        analysis.pcmci_runtime_seconds,
                        6,
                    ),
                    "pcmci_runtime_seconds": round(
                        analysis.pcmci_runtime_seconds,
                        6,
                    ),
                }
                for machine_id, analysis
                in zip(
                    effective_machine_ids,
                    machine_analyses,
                    strict=True,
                )
            },
            "causal_discovery_runtime_seconds": round(
                sum(
                    analysis.pcmci_runtime_seconds
                    for analysis
                    in machine_analyses
                ),
                6,
            ),
            "pcmci_runtime_seconds": round(
                sum(
                    analysis.pcmci_runtime_seconds
                    for analysis
                    in machine_analyses
                ),
                6,
            ),
            "panel_runtime_seconds": round(
                sum(
                    analysis.panel_runtime_seconds
                    for analysis
                    in machine_analyses
                ),
                6,
            ),
            "causal_job_runtime_before_persistence_seconds": round(
                time.perf_counter()
                - job_started,
                6,
            ),
        }

        persisted_parameters = {
            **parameters,
            "diagnostics": diagnostics,
        }

        run_id = uuid.uuid4()

        # --------------------------------------------------------------------
        # Race-safe run insertion.
        #
        # A concurrent worker may finish the identical signature first.
        # The unique signature constraint makes that case deterministic:
        # reuse its state instead of duplicating the run.
        # --------------------------------------------------------------------

        run_table = (
            ManufacturingCausalRun.__table__
        )

        insert_run = (
            pg_insert(
                run_table
            )
            .values(
                id=run_id,

                signature=signature,

                source_from=source_from,
                source_to=source_to,

                source_rows=source_rows,

                machines_requested=len(
                    effective_machine_ids
                ),

                machines_evaluated=(
                    stability.machines_evaluated
                ),

                candidate_pairs=(
                    stability.candidate_pairs
                ),

                stable_edge_count=len(
                    stability.stable_edges
                ),

                algorithm=_algorithm_label(
                    algorithm
                ),

                algorithm_version=(
                    _algorithm_version()
                ),

                parameters=persisted_parameters,

                machine_ids=list(
                    effective_machine_ids
                ),

                computed_at=computed_at,
            )
            .on_conflict_do_nothing(
                constraint=(
                    "uq_ai_mfg_runs_signature"
                )
            )
            .returning(
                run_table.c.id
            )
        )

        inserted_run_id = (
            await self._session.execute(
                insert_run
            )
        ).scalar_one_or_none()

        # Another transaction already persisted this exact source/config run.
        if inserted_run_id is None:
            raced = await self._load_by_signature(
                signature,
                reused=True,
            )

            if raced is None:
                raise RuntimeError(
                    "Manufacturing causal run signature conflicted "
                    "but the persisted run could not be reloaded."
                )

            return raced

        # --------------------------------------------------------------------
        # Persist only cross-machine stable discovered evidence.
        # --------------------------------------------------------------------

        persisted_edges: list[
            ManufacturingCausalEdge
        ] = []

        for stable_edge in (
            stability.stable_edges
        ):
            evidence = _stable_edge_evidence(
                stable_edge,
                machine_results,
                analysis_frequency_minutes=(
                    analysis_minutes
                ),
            )

            persisted_edges.append(
                ManufacturingCausalEdge(
                    run_id=inserted_run_id,

                    source_metric=(
                        stable_edge.source_metric
                    ),

                    target_metric=(
                        stable_edge.target_metric
                    ),

                    scope=(
                        stable_edge.scope
                    ),

                    consensus_sign=(
                        stable_edge.consensus_sign
                    ),

                    edge_orientation=(
                        stable_edge.consensus_edge_orientation
                    ),

                    consensus_edge_mark=(
                        stable_edge.consensus_edge_mark
                    ),

                    mark_agreement=float(
                        stable_edge.mark_agreement
                    ),

                    eligible_machines=(
                        stable_edge.eligible_machines
                    ),

                    recurring_machines=(
                        stable_edge.recurring_machines
                    ),

                    recurrence_fraction=float(
                        stable_edge.recurrence_fraction
                    ),

                    sign_agreement=float(
                        stable_edge.sign_agreement
                    ),

                    mean_abs_score=float(
                        stable_edge.mean_abs_score
                    ),

                    median_abs_score=float(
                        stable_edge.median_abs_score
                    ),

                    best_q_value=float(
                        stable_edge.best_q_value
                    ),

                    observed_lags=list(
                        stable_edge.observed_lags
                    ),

                    machine_ids=list(
                        stable_edge.machine_ids
                    ),

                    evidence=evidence,
                )
            )

        if persisted_edges:
            self._session.add_all(
                persisted_edges
            )

        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        persisted = await self._load_by_signature(
            signature,
            reused=False,
        )

        if persisted is None:
            raise RuntimeError(
                "Manufacturing causal state committed but "
                "could not be reloaded."
            )

        if (
            persisted.stable_edge_count
            != len(
                persisted.edges
            )
        ):
            raise RuntimeError(
                "Persisted manufacturing causal edge count mismatch. "
                f"run_count={persisted.stable_edge_count}, "
                f"edge_rows={len(persisted.edges)}"
            )

        return persisted
