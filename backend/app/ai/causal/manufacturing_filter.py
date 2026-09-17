"""
Mahindra manufacturing causal edge filtering and stability aggregation.

Purpose
-------
This module converts the complete hypothesis family returned by
pcmci_engine.run_pcmci_tests() into statistically defensible manufacturing
causal candidates for the Warranty & Quality Early-Warning Graph.

Pipeline
--------

    PCMCI complete hypothesis family
        ->
    Benjamini-Hochberg FDR correction
        ->
    minimum effect-size filtering
        ->
    manufacturing scope validation
        ->
    per-machine accepted causal candidates
        ->
    cross-machine recurrence / sign stability

Important
---------
This module does NOT:

- query PostgreSQL
- run PCMCI
- read synthetic causal ground truth
- hardcode causal source->target edges
- manufacture confidence values
- infer warranty cost exposure
- generate early-warning recommendations

Ground truth remains evaluation-only.

The statistical graph is discovered from runtime manufacturing observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Mapping, Sequence

import numpy as np

from app.ai.causal.pcmci_engine import (
    CausalDiscoveryTest,
    edge_orientation_for_mark,
)


# ============================================================================
# MANUFACTURING SEMANTIC SCOPE
# ============================================================================


PAINT_ONLY_METRICS = frozenset(
    {
        "paint_booth_temperature_c",
        "paint_booth_humidity_pct",
        "paint_defect_rate",
    }
)


# ============================================================================
# CONFIGURATION
# ============================================================================


@dataclass(frozen=True)
class ManufacturingFilterConfig:
    """
    Statistical and stability filtering configuration.

    apply_fdr_correction
        Whether to apply Benjamini-Hochberg correction at all. Defaults to
        False (the LPCMCI-appropriate reference-style behavior: rely on the
        algorithm's own selection plus an effect-size floor, no post-hoc
        p-value gate). Set True only for PCMCI rollback/comparison runs,
        where ``tests`` genuinely is PCMCI's complete tested hypothesis
        family and BH-FDR is the statistically correct correction. See the
        comment above the q_values computation in filter_manufacturing_tests
        for the full reasoning.

    fdr_alpha
        Benjamini-Hochberg false-discovery-rate threshold. Only consulted
        when apply_fdr_correction=True.

    min_abs_score
        Minimum absolute PCMCI partial-correlation effect size.

    min_recurrence_fraction
        Required fraction of eligible machines where a relationship
        must recur before it can be called cross-machine stable.

    min_recurrence_count
        Absolute recurrence floor.

        This is intentionally 2 rather than 3 because PAINT-specific
        relationships currently have only two representative PAINT lines.

    min_sign_agreement
        Required fraction of recurring machines that must agree on
        effect direction.

    min_lag
        Minimum lag a hypothesis test must have to be considered. PCMCI
        tests never carry lag 0 (never raises below 1). LPCMCI can
        legitimately carry lag 0 (contemporaneous) tests when the caller
        requested them; pass min_lag=0 in that case.

    min_mark_agreement
        Required fraction of recurring machines that must agree on
        coarse edge orientation (DIRECTED/BIDIRECTED/PARTIALLY_ORIENTED/
        AMBIGUOUS) before a
        pair counts as stable. Defaults to 0.0 (reported, not gated):
        forcing unanimous mark agreement in addition to unanimous sign
        agreement would likely make cross-machine LPCMCI stability nearly
        unreachable, since contemporaneous-link orientation is inherently
        harder to identify consistently across independent short panels
        than a plain lagged directed link. Raise this once real
        cross-machine mark stability has been observed empirically.
    """

    apply_fdr_correction: bool = False

    fdr_alpha: float = 0.05

    min_abs_score: float = 0.12

    min_recurrence_fraction: float = 0.60

    min_recurrence_count: int = 2

    min_sign_agreement: float = 1.0

    min_lag: int = 1

    min_mark_agreement: float = 0.0


DEFAULT_MANUFACTURING_FILTER_CONFIG = (
    ManufacturingFilterConfig()
)


# ============================================================================
# RESULT MODELS
# ============================================================================


@dataclass(frozen=True)
class ManufacturingFilteredEdge:
    """
    One per-machine causal candidate surviving statistical filtering.
    """

    source: str
    target: str

    source_metric: str
    target_metric: str

    lag: int

    score: float
    p_value: float
    q_value: float

    sign: str

    edge_mark: str
    edge_orientation: str

    machine_id: str

    plant_id: str | None
    plant_name: str | None

    production_line_id: str | None
    production_line_name: str | None

    line_type: str | None


@dataclass(frozen=True)
class ManufacturingFilterResult:
    """
    Statistical-filter result for one machine-level causal run.
    """

    machine_id: str

    plant_id: str | None
    plant_name: str | None

    production_line_id: str | None
    production_line_name: str | None

    line_type: str | None

    total_tests: int

    fdr_significant_tests: int

    effect_size_significant_tests: int

    scope_rejected_tests: int

    accepted_edges: tuple[
        ManufacturingFilteredEdge,
        ...,
    ]


@dataclass(frozen=True)
class ManufacturingStableEdge:
    """
    Cross-machine stability summary for one source->target metric pair.
    """

    source_metric: str
    target_metric: str

    eligible_machines: int
    recurring_machines: int

    recurrence_fraction: float

    consensus_sign: str
    sign_agreement: float

    consensus_edge_mark: str
    consensus_edge_orientation: str
    mark_agreement: float

    mean_abs_score: float
    median_abs_score: float

    best_q_value: float

    observed_lags: tuple[int, ...]

    machine_ids: tuple[str, ...]

    scope: str


@dataclass(frozen=True)
class ManufacturingStabilityResult:
    """
    Cross-machine stability aggregation result.
    """

    machines_evaluated: int

    candidate_pairs: int

    stable_edges: tuple[
        ManufacturingStableEdge,
        ...,
    ]


# ============================================================================
# BASIC HELPERS
# ============================================================================


def metric_name(
    variable: str,
) -> str:
    """
    Convert:

        MACHINE_SYN_001||defect_rate

    into:

        defect_rate
    """

    if "||" in variable:
        return variable.split(
            "||",
            1,
        )[1]

    return variable


def _optional_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    text = str(
        value
    ).strip()

    return text or None


def _normalise_line_type(
    value: Any,
) -> str | None:
    text = _optional_text(
        value
    )

    if text is None:
        return None

    return text.upper()


def _edge_sign(
    score: float,
) -> str:
    return (
        "+"
        if score > 0
        else "-"
    )


# ============================================================================
# BENJAMINI-HOCHBERG
# ============================================================================


def benjamini_hochberg_q_values(
    p_values: Sequence[float],
) -> np.ndarray:
    """
    Calculate Benjamini-Hochberg adjusted q-values.

    Correction is performed across the complete supplied hypothesis family.

    The output preserves the original p-value ordering.

    No hypotheses are discarded before correction.
    """

    if not p_values:
        return np.asarray(
            [],
            dtype=float,
        )

    values = np.asarray(
        p_values,
        dtype=float,
    )

    if values.ndim != 1:
        raise ValueError(
            "Benjamini-Hochberg p-values "
            "must be one-dimensional."
        )

    if not np.isfinite(
        values
    ).all():
        raise ValueError(
            "Benjamini-Hochberg received "
            "non-finite p-values."
        )

    if (
        (values < 0.0).any()
        or (values > 1.0).any()
    ):
        raise ValueError(
            "Benjamini-Hochberg p-values "
            "must lie in [0, 1]."
        )

    hypothesis_count = len(
        values
    )

    order = np.argsort(
        values,
        kind="stable",
    )

    adjusted = np.empty(
        hypothesis_count,
        dtype=float,
    )

    running_minimum = 1.0

    # Work backwards so adjusted q-values are monotonic
    # with increasing raw p-value.
    for ordered_index in range(
        hypothesis_count - 1,
        -1,
        -1,
    ):
        original_index = int(
            order[
                ordered_index
            ]
        )

        rank = (
            ordered_index
            + 1
        )

        candidate = (
            values[
                original_index
            ]
            * hypothesis_count
            / rank
        )

        running_minimum = min(
            running_minimum,
            candidate,
        )

        adjusted[
            original_index
        ] = min(
            running_minimum,
            1.0,
        )

    return adjusted


# ============================================================================
# METADATA / SCOPE VALIDATION
# ============================================================================


def _require_metadata(
    variable: str,
    metadata: Mapping[
        str,
        Mapping[str, Any],
    ],
) -> Mapping[str, Any]:
    """
    Require metadata for every PCMCI variable.

    Silent metadata loss is unacceptable because later Warranty & Quality
    lineage depends on the manufacturing context.
    """

    if variable not in metadata:
        raise ValueError(
            "Missing manufacturing metadata "
            f"for PCMCI variable: {variable}"
        )

    return metadata[
        variable
    ]


def _validate_same_machine_context(
    source: str,
    target: str,
    metadata: Mapping[
        str,
        Mapping[str, Any],
    ],
) -> tuple[
    Mapping[str, Any],
    Mapping[str, Any],
]:
    """
    Current production design performs independent causal discovery
    per manufacturing machine.

    Prevent accidental interpretation of a future cross-machine panel as
    if it represented the current validated discovery contract.
    """

    source_metadata = _require_metadata(
        source,
        metadata,
    )

    target_metadata = _require_metadata(
        target,
        metadata,
    )

    source_machine = _optional_text(
        source_metadata.get(
            "machine_id"
        )
    )

    target_machine = _optional_text(
        target_metadata.get(
            "machine_id"
        )
    )

    if (
        source_machine is not None
        and target_machine is not None
        and source_machine
        != target_machine
    ):
        raise ValueError(
            "Manufacturing causal filtering currently "
            "requires source and target variables "
            "to belong to the same machine."
        )

    return (
        source_metadata,
        target_metadata,
    )


def _scope_is_valid(
    source_metric: str,
    target_metric: str,
    *,
    line_type: str | None,
) -> bool:
    """
    Enforce domain scope without hardcoding graph edges.

    Paint-booth variables are physically meaningful only on PAINT lines.
    """

    contains_paint_metric = (
        source_metric
        in PAINT_ONLY_METRICS
        or target_metric
        in PAINT_ONLY_METRICS
    )

    if not contains_paint_metric:
        return True

    return (
        line_type
        == "PAINT"
    )


# ============================================================================
# PER-MACHINE STATISTICAL FILTERING
# ============================================================================


def filter_manufacturing_tests(
    tests: Sequence[
        CausalDiscoveryTest
    ],
    metadata: Mapping[
        str,
        Mapping[str, Any],
    ],
    config: ManufacturingFilterConfig = (
        DEFAULT_MANUFACTURING_FILTER_CONFIG
    ),
) -> ManufacturingFilterResult:
    """
    Apply significance, effect-size and manufacturing-scope filtering.

    IMPORTANT
    ---------
    When ``config.apply_fdr_correction=True`` (PCMCI rollback path),
    ``tests`` must be the COMPLETE finite hypothesis family returned by
    ``run_pcmci_tests()`` -- do not pass the already-filtered output of
    ``run_pcmci()`` here, since BH-FDR needs the full family to correct
    correctly.

    When ``config.apply_fdr_correction=False`` (LPCMCI default), ``tests``
    is expected to already be algorithm-selected (i.e. the output of
    ``run_lpcmci_tests()``, which only returns PAG-surviving edges) and no
    complete-family assumption applies.
    """

    if not (
        0.0
        < config.fdr_alpha
        <= 1.0
    ):
        raise ValueError(
            "fdr_alpha must lie in (0, 1]."
        )

    if config.min_abs_score < 0.0:
        raise ValueError(
            "min_abs_score cannot be negative."
        )

    if not tests:
        raise ValueError(
            "No PCMCI hypothesis tests were supplied."
        )

    # ------------------------------------------------------------------------
    # Validate complete test objects before FDR correction.
    # ------------------------------------------------------------------------

    seen_keys: set[
        tuple[str, str, int]
    ] = set()

    for test in tests:
        if test.source == test.target:
            raise ValueError(
                "Manufacturing PCMCI test family "
                "must not contain self-links."
            )

        if test.lag < config.min_lag:
            raise ValueError(
                "Manufacturing causal-discovery tests "
                f"must have lag >= {config.min_lag}."
            )

        if not (
            np.isfinite(
                test.p_value
            )
            and np.isfinite(
                test.score
            )
        ):
            raise ValueError(
                "Manufacturing PCMCI test family "
                "contains non-finite statistics."
            )

        if not (
            0.0
            <= test.p_value
            <= 1.0
        ):
            raise ValueError(
                "PCMCI p-value lies outside [0, 1]."
            )

        key = (
            test.source,
            test.target,
            test.lag,
        )

        if key in seen_keys:
            raise ValueError(
                "Duplicate PCMCI hypothesis test: "
                f"{key}"
            )

        seen_keys.add(
            key
        )

    # ------------------------------------------------------------------------
    # Significance correction: algorithm-dependent.
    #
    # BH-FDR is statistically appropriate ONLY when ``tests`` is the
    # COMPLETE hypothesis family the underlying algorithm tested -- which is
    # true for PCMCI (run_pcmci_tests() returns every non-self lagged pair
    # regardless of significance) but NOT true for LPCMCI
    # (run_lpcmci_tests() already returns only the edges LPCMCI's own
    # iterative, pc_alpha-controlled PAG construction retained). Applying a
    # second complete-family correction on top of an already-selected
    # subset is either a no-op or statistically wrong (the classic
    # "select-then-correct-on-the-selected-subset" error), so
    # config.apply_fdr_correction gates it: PCMCI rollback/comparison runs
    # set it True (reproducing prior production behavior exactly); LPCMCI
    # runs leave it False and rely on LPCMCI's own internal significance
    # testing plus the reference-style min_abs_score effect-size floor
    # below -- q_value is then simply the raw, uncorrected p_value.
    # ------------------------------------------------------------------------

    q_values = (
        benjamini_hochberg_q_values(
            [
                test.p_value
                for test in tests
            ]
        )
        if config.apply_fdr_correction
        else np.asarray(
            [
                test.p_value
                for test in tests
            ],
            dtype=float,
        )
    )

    fdr_significant_tests = 0
    effect_size_significant_tests = 0
    scope_rejected_tests = 0

    accepted_edges: list[
        ManufacturingFilteredEdge
    ] = []

    run_machine_id: str | None = None
    run_plant_id: str | None = None
    run_plant_name: str | None = None
    run_line_id: str | None = None
    run_line_name: str | None = None
    run_line_type: str | None = None

    for test, q_value_raw in zip(
        tests,
        q_values,
        strict=True,
    ):
        q_value = float(
            q_value_raw
        )

        source_metadata, target_metadata = (
            _validate_same_machine_context(
                test.source,
                test.target,
                metadata,
            )
        )

        source_metric = metric_name(
            test.source
        )

        target_metric = metric_name(
            test.target
        )

        machine_id = (
            _optional_text(
                source_metadata.get(
                    "machine_id"
                )
            )
            or _optional_text(
                target_metadata.get(
                    "machine_id"
                )
            )
        )

        if machine_id is None:
            raise ValueError(
                "Manufacturing metadata does not "
                "contain machine_id."
            )

        plant_id = (
            _optional_text(
                source_metadata.get(
                    "plant_id"
                )
            )
            or _optional_text(
                target_metadata.get(
                    "plant_id"
                )
            )
        )

        plant_name = (
            _optional_text(
                source_metadata.get(
                    "plant_name"
                )
            )
            or _optional_text(
                target_metadata.get(
                    "plant_name"
                )
            )
        )

        production_line_id = (
            _optional_text(
                source_metadata.get(
                    "production_line_id"
                )
            )
            or _optional_text(
                target_metadata.get(
                    "production_line_id"
                )
            )
        )

        production_line_name = (
            _optional_text(
                source_metadata.get(
                    "production_line_name"
                )
            )
            or _optional_text(
                target_metadata.get(
                    "production_line_name"
                )
            )
        )

        line_type = (
            _normalise_line_type(
                source_metadata.get(
                    "line_type"
                )
            )
            or _normalise_line_type(
                target_metadata.get(
                    "line_type"
                )
            )
        )

        # Establish/validate one-machine run context.
        if run_machine_id is None:
            run_machine_id = (
                machine_id
            )

            run_plant_id = (
                plant_id
            )

            run_plant_name = (
                plant_name
            )

            run_line_id = (
                production_line_id
            )

            run_line_name = (
                production_line_name
            )

            run_line_type = (
                line_type
            )

        elif machine_id != run_machine_id:
            raise ValueError(
                "filter_manufacturing_tests() "
                "received tests from multiple machines. "
                "Run independent machine-level filtering first."
            )

        # ------------------------------------------------------------------
        # Stage 1: FDR (PCMCI rollback only; a no-op for LPCMCI -- see the
        # comment above the q_values computation).
        # ------------------------------------------------------------------

        if (
            config.apply_fdr_correction
            and q_value
            > config.fdr_alpha
        ):
            continue

        fdr_significant_tests += 1

        # ------------------------------------------------------------------
        # Stage 2: effect size.
        # ------------------------------------------------------------------

        if (
            abs(
                test.score
            )
            < config.min_abs_score
        ):
            continue

        effect_size_significant_tests += 1

        # ------------------------------------------------------------------
        # Stage 3: physical manufacturing scope.
        # ------------------------------------------------------------------

        if not _scope_is_valid(
            source_metric,
            target_metric,
            line_type=line_type,
        ):
            scope_rejected_tests += 1
            continue

        accepted_edges.append(
            ManufacturingFilteredEdge(
                source=test.source,
                target=test.target,

                source_metric=source_metric,
                target_metric=target_metric,

                lag=test.lag,

                score=float(
                    test.score
                ),

                p_value=float(
                    test.p_value
                ),

                q_value=q_value,

                sign=_edge_sign(
                    test.score
                ),

                edge_mark=test.edge_mark,
                edge_orientation=test.edge_orientation,

                machine_id=machine_id,

                plant_id=plant_id,
                plant_name=plant_name,

                production_line_id=(
                    production_line_id
                ),

                production_line_name=(
                    production_line_name
                ),

                line_type=line_type,
            )
        )

    if run_machine_id is None:
        raise ValueError(
            "Unable to determine manufacturing "
            "machine context."
        )

    accepted_edges.sort(
        key=lambda edge: (
            edge.q_value,
            -abs(
                edge.score
            ),
            edge.lag,
            edge.source_metric,
            edge.target_metric,
        )
    )

    return ManufacturingFilterResult(
        machine_id=run_machine_id,

        plant_id=run_plant_id,
        plant_name=run_plant_name,

        production_line_id=(
            run_line_id
        ),

        production_line_name=(
            run_line_name
        ),

        line_type=run_line_type,

        total_tests=len(
            tests
        ),

        fdr_significant_tests=(
            fdr_significant_tests
        ),

        effect_size_significant_tests=(
            effect_size_significant_tests
        ),

        scope_rejected_tests=(
            scope_rejected_tests
        ),

        accepted_edges=tuple(
            accepted_edges
        ),
    )


# ============================================================================
# BEST LAG PER MACHINE / PAIR
# ============================================================================


def best_edge_per_pair(
    edges: Sequence[
        ManufacturingFilteredEdge
    ],
) -> dict[
    tuple[str, str],
    ManufacturingFilteredEdge,
]:
    """
    Select one representative lag per source->target pair.

    Selection priority:

        1. lowest FDR q-value
        2. largest absolute effect size
        3. shorter lag

    This prevents multiple lag copies of the same pair from artificially
    inflating cross-machine recurrence.
    """

    best: dict[
        tuple[str, str],
        ManufacturingFilteredEdge,
    ] = {}

    for edge in edges:
        pair = (
            edge.source_metric,
            edge.target_metric,
        )

        existing = best.get(
            pair
        )

        if existing is None:
            best[
                pair
            ] = edge

            continue

        candidate_key = (
            edge.q_value,
            -abs(
                edge.score
            ),
            edge.lag,
        )

        existing_key = (
            existing.q_value,
            -abs(
                existing.score
            ),
            existing.lag,
        )

        if candidate_key < existing_key:
            best[
                pair
            ] = edge

    return best


# ============================================================================
# CROSS-MACHINE STABILITY
# ============================================================================


def _pair_scope(
    source_metric: str,
    target_metric: str,
) -> str:
    if (
        source_metric
        in PAINT_ONLY_METRICS
        or target_metric
        in PAINT_ONLY_METRICS
    ):
        return "PAINT"

    return "ALL"


def aggregate_manufacturing_stability(
    machine_results: Sequence[
        ManufacturingFilterResult
    ],
    config: ManufacturingFilterConfig = (
        DEFAULT_MANUFACTURING_FILTER_CONFIG
    ),
) -> ManufacturingStabilityResult:
    """
    Aggregate statistically accepted per-machine edges.

    A relationship is considered stable only when:

    - it recurs across enough ELIGIBLE machines, and
    - its sign agrees across the required fraction.

    Scope-aware denominator
    -----------------------
    Generic process relationships are evaluated against all supplied machines.

    PAINT-specific relationships are evaluated only against PAINT machines.

    This prevents legitimate paint relationships from being penalized simply
    because BODY and ASSEMBLY machines cannot physically observe paint signals.
    """

    if not (
        0.0
        < config.min_recurrence_fraction
        <= 1.0
    ):
        raise ValueError(
            "min_recurrence_fraction "
            "must lie in (0, 1]."
        )

    if config.min_recurrence_count < 1:
        raise ValueError(
            "min_recurrence_count "
            "must be at least 1."
        )

    if not (
        0.0
        < config.min_sign_agreement
        <= 1.0
    ):
        raise ValueError(
            "min_sign_agreement "
            "must lie in (0, 1]."
        )

    if not machine_results:
        return ManufacturingStabilityResult(
            machines_evaluated=0,
            candidate_pairs=0,
            stable_edges=(),
        )

    machine_ids = [
        result.machine_id
        for result in machine_results
    ]

    if len(
        set(
            machine_ids
        )
    ) != len(machine_ids):
        raise ValueError(
            "Cross-machine stability input "
            "contains duplicate machine results."
        )

    per_machine_best: dict[
        str,
        dict[
            tuple[str, str],
            ManufacturingFilteredEdge,
        ],
    ] = {
        result.machine_id: (
            best_edge_per_pair(
                result.accepted_edges
            )
        )
        for result in machine_results
    }

    all_pairs: set[
        tuple[str, str]
    ] = set()

    for pair_map in (
        per_machine_best.values()
    ):
        all_pairs.update(
            pair_map.keys()
        )

    stable_edges: list[
        ManufacturingStableEdge
    ] = []

    for source_metric, target_metric in sorted(
        all_pairs
    ):
        scope = _pair_scope(
            source_metric,
            target_metric,
        )

        if scope == "PAINT":
            eligible_results = [
                result
                for result
                in machine_results
                if (
                    _normalise_line_type(
                        result.line_type
                    )
                    == "PAINT"
                )
            ]
        else:
            eligible_results = list(
                machine_results
            )

        eligible_count = len(
            eligible_results
        )

        if eligible_count == 0:
            continue

        observations: list[
            ManufacturingFilteredEdge
        ] = []

        pair = (
            source_metric,
            target_metric,
        )

        for result in (
            eligible_results
        ):
            edge = (
                per_machine_best[
                    result.machine_id
                ].get(
                    pair
                )
            )

            if edge is not None:
                observations.append(
                    edge
                )

        recurring_count = len(
            observations
        )

        required_count = max(
            config.min_recurrence_count,
            int(
                ceil(
                    eligible_count
                    * config.min_recurrence_fraction
                )
            ),
        )

        # Cannot require more machines than are physically eligible.
        required_count = min(
            required_count,
            eligible_count,
        )

        if (
            recurring_count
            < required_count
        ):
            continue

        positive_count = sum(
            edge.score > 0
            for edge
            in observations
        )

        negative_count = sum(
            edge.score < 0
            for edge
            in observations
        )

        consensus_count = max(
            positive_count,
            negative_count,
        )

        sign_agreement = (
            consensus_count
            / recurring_count
        )

        if (
            sign_agreement
            < config.min_sign_agreement
        ):
            continue

        consensus_sign = (
            "+"
            if positive_count
            > negative_count
            else "-"
        )

        # Mark agreement: reported alongside sign agreement, not gating by
        # default (see ManufacturingFilterConfig.min_mark_agreement). Ties
        # broken deterministically and alphabetically by mark string.
        mark_counts: dict[str, int] = {}

        for edge in observations:
            mark_counts[
                edge.edge_mark
            ] = (
                mark_counts.get(
                    edge.edge_mark,
                    0,
                )
                + 1
            )

        consensus_edge_mark = max(
            sorted(mark_counts),
            key=lambda mark: mark_counts[mark],
        )

        mark_agreement = (
            mark_counts[consensus_edge_mark]
            / recurring_count
        )

        if (
            mark_agreement
            < config.min_mark_agreement
        ):
            continue

        consensus_edge_orientation = (
            edge_orientation_for_mark(
                consensus_edge_mark
            )
        )

        absolute_scores = np.asarray(
            [
                abs(
                    edge.score
                )
                for edge
                in observations
            ],
            dtype=float,
        )

        stable_edges.append(
            ManufacturingStableEdge(
                source_metric=(
                    source_metric
                ),

                target_metric=(
                    target_metric
                ),

                eligible_machines=(
                    eligible_count
                ),

                recurring_machines=(
                    recurring_count
                ),

                recurrence_fraction=(
                    recurring_count
                    / eligible_count
                ),

                consensus_sign=(
                    consensus_sign
                ),

                sign_agreement=(
                    sign_agreement
                ),

                consensus_edge_mark=(
                    consensus_edge_mark
                ),

                consensus_edge_orientation=(
                    consensus_edge_orientation
                ),

                mark_agreement=(
                    mark_agreement
                ),

                mean_abs_score=float(
                    np.mean(
                        absolute_scores
                    )
                ),

                median_abs_score=float(
                    np.median(
                        absolute_scores
                    )
                ),

                best_q_value=min(
                    edge.q_value
                    for edge
                    in observations
                ),

                observed_lags=tuple(
                    sorted(
                        {
                            edge.lag
                            for edge
                            in observations
                        }
                    )
                ),

                machine_ids=tuple(
                    sorted(
                        edge.machine_id
                        for edge
                        in observations
                    )
                ),

                scope=scope,
            )
        )

    stable_edges.sort(
        key=lambda edge: (
            -edge.recurrence_fraction,
            -edge.sign_agreement,
            -edge.mean_abs_score,
            edge.best_q_value,
            edge.source_metric,
            edge.target_metric,
        )
    )

    return ManufacturingStabilityResult(
        machines_evaluated=len(
            machine_results
        ),

        candidate_pairs=len(
            all_pairs
        ),

        stable_edges=tuple(
            stable_edges
        ),
    )