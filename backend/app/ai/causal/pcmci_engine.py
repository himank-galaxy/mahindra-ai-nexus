"""Thin real Tigramite PCMCI/LPCMCI runner; it never invents edges."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np


# ============================================================================
# RESULT MODELS
# ============================================================================


@dataclass(frozen=True)
class PcmciTest:
    """
    One lagged PCMCI hypothesis test.

    Unlike PcmciEdge, this object is NOT significance-filtered.

    It exists so downstream domain-specific filtering can perform proper
    multiple-testing correction across the complete hypothesis family rather
    than correcting only already-significant edges.
    """

    source: str
    target: str
    lag: int
    score: float
    p_value: float


@dataclass(frozen=True)
class PcmciEdge:
    """
    Backward-compatible statistically filtered PCMCI edge.
    """

    source: str
    target: str
    lag: int
    score: float
    p_value: float


@dataclass(frozen=True)
class CausalDiscoveryTest:
    """
    One algorithm-agnostic lagged/contemporaneous causal-discovery hypothesis
    test.

    Unlike PcmciTest, ``lag`` may be 0 (contemporaneous) and the test carries
    Tigramite's raw PAG edge mark plus a coarse orientation bucket, so that
    downstream filtering can be shared between the PCMCI and LPCMCI engines.
    """

    source: str
    target: str
    lag: int
    score: float
    p_value: float
    edge_mark: str
    edge_orientation: str


# ============================================================================
# EDGE-MARK CLASSIFICATION
#
# Tigramite/PAG edge-mark semantics (Zhang 2008 FCI convention): each 3-char
# mark string encodes one symbol per endpoint. A tail ("-") at an endpoint
# means that variable IS an ancestor of the other; an arrowhead (">"/"<")
# means it is NOT; a circle ("o") means undetermined. Reading a mark
# left-to-right describes the edge from the LEFT (source) variable's
# perspective to the RIGHT (target) variable's perspective:
#
#   "-->"  tail@source,  arrow@target  -> source is an ancestor of target:
#          fully DIRECTED, source causes target.
#   "<--"  arrow@source, tail@target   -> target is an ancestor of source:
#          fully DIRECTED, but REVERSED relative to naive (i, j) order.
#   "<->"  arrow@source, arrow@target  -> neither is an ancestor of the
#          other: BIDIRECTED (implies an unobserved common driver).
#   "o->"  circle@source, arrow@target -> target is not caused by source's
#          side is unresolved, but target does NOT cause source:
#          PARTIALLY_ORIENTED (one endpoint resolved, one uncertain).
#   "<-o"  arrow@source, circle@target -> mirror of "o->": PARTIALLY_ORIENTED,
#          but REVERSED relative to naive (i, j) order.
#   "o-o"  circle@source, circle@target -> nothing resolved: AMBIGUOUS.
# ============================================================================


_DIRECTED_MARKS = frozenset({"-->", "<--"})
_BIDIRECTED_MARKS = frozenset({"<->"})
_PARTIALLY_ORIENTED_MARKS = frozenset({"o->", "<-o"})
_AMBIGUOUS_MARKS = frozenset({"o-o"})

# Marks whose arrowhead points at the (i, j)-order SOURCE rather than the
# target -- i.e. the true causal direction is reversed relative to naive
# (i, j) index order and must be canonicalized before persistence.
_REVERSED_MARKS = frozenset({"<--", "<-o"})

ORIENTATION_DIRECTED = "DIRECTED"
ORIENTATION_BIDIRECTED = "BIDIRECTED"
ORIENTATION_PARTIALLY_ORIENTED = "PARTIALLY_ORIENTED"
ORIENTATION_AMBIGUOUS = "AMBIGUOUS"


def edge_orientation_for_mark(mark: str) -> str:
    """
    Bucket a raw Tigramite PAG edge mark into one of four coarse
    orientations: DIRECTED, BIDIRECTED, PARTIALLY_ORIENTED, AMBIGUOUS.

    Any mark this repo does not yet recognise (e.g. a future Tigramite
    selection-bias mark) defaults to AMBIGUOUS rather than raising, since an
    unrecognised mark is by definition not confidently resolved.
    """

    if mark in _DIRECTED_MARKS:
        return ORIENTATION_DIRECTED

    if mark in _BIDIRECTED_MARKS:
        return ORIENTATION_BIDIRECTED

    if mark in _PARTIALLY_ORIENTED_MARKS:
        return ORIENTATION_PARTIALLY_ORIENTED

    return ORIENTATION_AMBIGUOUS


# Endpoint-symbol translation for mirroring a mark: the SAME endpoint kind
# (arrowhead/tail/circle) is spelled differently depending on which side of
# the mark string it appears on ("<" = arrowhead-on-left, ">" =
# arrowhead-on-right); "o" and "-" are spelled the same on either side. A
# naive string reversal (mark[::-1]) is WRONG here -- it would turn "<--"
# into "--<", not "-->" -- because it swaps character POSITIONS without
# translating "<" to ">".
_ENDPOINT_MIRROR = {"<": ">", ">": "<", "o": "o", "-": "-"}


def _mirror_mark(mark: str) -> str:
    """Mirror a 3-char PAG mark: swap which endpoint each symbol describes."""

    left, middle, right = mark[0], mark[1], mark[2]
    return (
        _ENDPOINT_MIRROR[right]
        + middle
        + _ENDPOINT_MIRROR[left]
    )


def canonicalize_edge(
    mark: str,
    left_name: str,
    right_name: str,
) -> tuple[str, str, str]:
    """
    Resolve a raw Tigramite mark read at (i, j) into a self-consistent
    (source, target, mark) triple.

    Tigramite's graph[i, j, tau] mark describes the edge as read FROM i TO
    j. When that mark's arrowhead actually points at i (i.e. mark is "<--"
    or "<-o"), the true causal direction is j -> i, the OPPOSITE of naive
    (i, j) assignment. Persisting source=i, target=j with that raw mark
    unmodified would silently assert the wrong direction to every
    downstream consumer that reads "source [mark] target" left-to-right
    (graph rendering, scope validation, the API contract).

    This swaps source/target AND mirrors the mark (translating which
    endpoint each symbol describes, NOT a naive string reversal) so the
    returned triple always reads correctly left-to-right, and the reversed
    raw marks "<--"/"<-o" never appear in what gets persisted -- only their
    mirrors "-->"/"o->" do, attached to the swapped (source, target).

    Self-mirrored marks ("<->", "o-o") and forward marks ("-->", "o->")
    pass through with left_name/right_name unchanged, since no direction
    correction is needed (a bidirected/fully-ambiguous mark has no
    preferred direction to get wrong either way).
    """

    if mark in _REVERSED_MARKS:
        return right_name, left_name, _mirror_mark(mark)

    return left_name, right_name, mark


def pcmci_tests_as_causal_discovery_tests(
    tests: Sequence[PcmciTest],
) -> list[CausalDiscoveryTest]:
    """
    Adapt PCMCI's plain directed tests onto the algorithm-agnostic contract
    shared with LPCMCI, so filter modules can depend on one test type
    regardless of which engine produced it.

    PCMCI never tests contemporaneous links and never reports anything but a
    plain directed relationship, so every adapted test is marked "-->" /
    DIRECTED.
    """

    return [
        CausalDiscoveryTest(
            source=test.source,
            target=test.target,
            lag=test.lag,
            score=test.score,
            p_value=test.p_value,
            edge_mark="-->",
            edge_orientation=ORIENTATION_DIRECTED,
        )
        for test in tests
    ]


# ============================================================================
# VALIDATION
# ============================================================================


def _validate_inputs(
    values: np.ndarray,
    metrics: Sequence[str],
    tau_max: int,
) -> tuple[np.ndarray, tuple[str, ...]]:
    """
    Validate the matrix contract before handing data to Tigramite.
    """

    matrix = np.asarray(
        values,
        dtype=float,
    )

    metric_names = tuple(
        str(metric)
        for metric in metrics
    )

    if matrix.ndim != 2:
        raise ValueError(
            "PCMCI values must be a 2-dimensional matrix."
        )

    if matrix.shape[1] != len(
        metric_names
    ):
        raise ValueError(
            "PCMCI matrix column count does not match "
            "the number of metric names."
        )

    if matrix.shape[0] < 2:
        raise ValueError(
            "PCMCI requires at least two observations."
        )

    if len(metric_names) < 2:
        raise ValueError(
            "PCMCI requires at least two variables."
        )

    if len(
        set(metric_names)
    ) != len(metric_names):
        raise ValueError(
            "PCMCI metric names must be unique."
        )

    if tau_max < 1:
        raise ValueError(
            "PCMCI tau_max must be at least 1."
        )

    if tau_max >= matrix.shape[0]:
        raise ValueError(
            "PCMCI tau_max must be smaller than "
            "the number of observations."
        )

    if not np.isfinite(
        matrix
    ).all():
        raise ValueError(
            "PCMCI input matrix contains NaN or infinite values."
        )

    return (
        matrix,
        metric_names,
    )


# ============================================================================
# TIGRAMITE EXECUTION
# ============================================================================


def _run_pcmci_matrices(
    values: np.ndarray,
    metrics: tuple[str, ...],
    *,
    tau_max: int,
    pc_alpha: float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Execute real Tigramite PCMCI and return its p-value/value matrices.

    This function performs no post-hoc business filtering.
    """

    try:
        from tigramite import (
            data_processing as pp,
        )
        from tigramite.independence_tests.parcorr import (
            ParCorr,
        )
        from tigramite.pcmci import (
            PCMCI,
        )
    except ImportError as exc:
        # Defensive:
        # callers must return an error, never a fake graph.
        raise RuntimeError(
            "Tigramite is not installed; "
            "PCMCI output is unavailable."
        ) from exc

    frame = pp.DataFrame(
        values,
        var_names=list(
            metrics
        ),
    )

    pcmci = PCMCI(
        dataframe=frame,
        cond_ind_test=ParCorr(
            significance="analytic"
        ),
        verbosity=0,
    )

    result = pcmci.run_pcmci(
        tau_max=tau_max,
        pc_alpha=pc_alpha,
    )

    p_matrix = np.asarray(
        result["p_matrix"],
        dtype=float,
    )

    val_matrix = np.asarray(
        result["val_matrix"],
        dtype=float,
    )

    return (
        p_matrix,
        val_matrix,
    )


# ============================================================================
# COMPLETE HYPOTHESIS FAMILY
# ============================================================================


def run_pcmci_tests(
    values: np.ndarray,
    metrics: Sequence[str],
    *,
    tau_max: int = 3,
    pc_alpha: float = 0.05,
) -> list[PcmciTest]:
    """
    Run PCMCI and return every finite non-self lagged hypothesis test.

    IMPORTANT
    ---------
    No p-value threshold is applied here.
    No effect-size threshold is applied here.
    No FDR correction is applied here.

    For N variables and tau_max=L, the expected number of non-self tests is:

        N * (N - 1) * L

    provided Tigramite returns finite statistics for every tested link.

    This complete family is what domain-specific filtering should use for
    Benjamini-Hochberg/FDR correction.
    """

    matrix, metric_names = _validate_inputs(
        values,
        metrics,
        tau_max,
    )

    p_matrix, val_matrix = (
        _run_pcmci_matrices(
            matrix,
            metric_names,
            tau_max=tau_max,
            pc_alpha=pc_alpha,
        )
    )

    tests: list[
        PcmciTest
    ] = []

    for source_index, source in enumerate(
        metric_names
    ):
        for target_index, target in enumerate(
            metric_names
        ):
            # The business causal graph does not expose
            # autoregressive self-links.
            if source == target:
                continue

            for lag in range(
                1,
                tau_max + 1,
            ):
                p_value = float(
                    p_matrix[
                        source_index,
                        target_index,
                        lag,
                    ]
                )

                score = float(
                    val_matrix[
                        source_index,
                        target_index,
                        lag,
                    ]
                )

                # Never convert invalid numerical output into an edge/test.
                if not (
                    np.isfinite(
                        p_value
                    )
                    and np.isfinite(
                        score
                    )
                ):
                    continue

                tests.append(
                    PcmciTest(
                        source=source,
                        target=target,
                        lag=lag,
                        score=score,
                        p_value=p_value,
                    )
                )

    return sorted(
        tests,
        key=lambda test: (
            test.p_value,
            -abs(
                test.score
            ),
            test.lag,
            test.source,
            test.target,
        ),
    )


# ============================================================================
# BACKWARD-COMPATIBLE FILTERED API
# ============================================================================


def run_pcmci(
    values: np.ndarray,
    metrics: Sequence[str],
    *,
    tau_max: int = 3,
    alpha: float = 0.05,
) -> list[PcmciEdge]:
    """
    Run linear partial-correlation PCMCI and retain tested edges.

    This preserves the original Mahindra behavior:

        raw p-value <= alpha
        AND
        absolute PCMCI score >= 0.12

    It intentionally does NOT perform FDR correction.

    New Warranty & Quality code should use run_pcmci_tests() first and apply
    domain-specific multiple-testing correction in manufacturing_filter.py.
    """

    if not (
        0.0
        < alpha
        <= 1.0
    ):
        raise ValueError(
            "PCMCI alpha must be in the interval (0, 1]."
        )

    tests = run_pcmci_tests(
        values,
        metrics,
        tau_max=tau_max,
        pc_alpha=alpha,
    )

    edges = [
        PcmciEdge(
            source=test.source,
            target=test.target,
            lag=test.lag,
            score=test.score,
            p_value=test.p_value,
        )
        for test in tests
        if (
            test.p_value <= alpha
            and abs(
                test.score
            ) >= 0.12
        )
    ]

    return sorted(
        edges,
        key=lambda edge: (
            edge.p_value,
            -abs(
                edge.score
            ),
            edge.lag,
            edge.source,
            edge.target,
        ),
    )


# ============================================================================
# LPCMCI VALIDATION
# ============================================================================


def _validate_lpcmci_inputs(
    values: np.ndarray,
    metrics: Sequence[str],
    tau_max: int,
) -> tuple[np.ndarray, tuple[str, ...]]:
    """
    Validate the matrix contract before handing data to LPCMCI.

    Identical to _validate_inputs() except tau_max may be 0, since LPCMCI's
    entire purpose includes resolving contemporaneous (lag-0) relationships.
    """

    matrix = np.asarray(
        values,
        dtype=float,
    )

    metric_names = tuple(
        str(metric)
        for metric in metrics
    )

    if matrix.ndim != 2:
        raise ValueError(
            "LPCMCI values must be a 2-dimensional matrix."
        )

    if matrix.shape[1] != len(
        metric_names
    ):
        raise ValueError(
            "LPCMCI matrix column count does not match "
            "the number of metric names."
        )

    if matrix.shape[0] < 2:
        raise ValueError(
            "LPCMCI requires at least two observations."
        )

    if len(metric_names) < 2:
        raise ValueError(
            "LPCMCI requires at least two variables."
        )

    if len(
        set(metric_names)
    ) != len(metric_names):
        raise ValueError(
            "LPCMCI metric names must be unique."
        )

    if tau_max < 0:
        raise ValueError(
            "LPCMCI tau_max must be at least 0."
        )

    if tau_max >= matrix.shape[0]:
        raise ValueError(
            "LPCMCI tau_max must be smaller than "
            "the number of observations."
        )

    if not np.isfinite(
        matrix
    ).all():
        raise ValueError(
            "LPCMCI input matrix contains NaN or infinite values."
        )

    return (
        matrix,
        metric_names,
    )


# ============================================================================
# LPCMCI EXECUTION
# ============================================================================


def _run_lpcmci_matrices(
    values: np.ndarray,
    metrics: tuple[str, ...],
    *,
    tau_min: int,
    tau_max: int,
    pc_alpha: float,
    lpcmci_kwargs: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Execute real Tigramite LPCMCI and return its p-value/value/graph
    matrices.

    This function performs no post-hoc business filtering. Unlike PCMCI's
    val_matrix/p_matrix-only contract, LPCMCI's ``graph`` matrix of PAG edge
    marks (e.g. "-->", "<->", "o-o") is also returned, since it is the only
    place the discovered edge orientation is recorded.
    """

    try:
        from tigramite import (
            data_processing as pp,
        )
        from tigramite.independence_tests.parcorr import (
            ParCorr,
        )
        from tigramite.lpcmci import (
            LPCMCI,
        )
    except ImportError as exc:
        # Defensive:
        # callers must return an error, never a fake graph.
        raise RuntimeError(
            "Tigramite is not installed; "
            "LPCMCI output is unavailable."
        ) from exc

    frame = pp.DataFrame(
        values,
        var_names=list(
            metrics
        ),
    )

    lpcmci = LPCMCI(
        dataframe=frame,
        cond_ind_test=ParCorr(
            significance="analytic"
        ),
        verbosity=0,
    )

    result = lpcmci.run_lpcmci(
        tau_min=tau_min,
        tau_max=tau_max,
        pc_alpha=pc_alpha,
        **lpcmci_kwargs,
    )

    p_matrix = np.asarray(
        result["p_matrix"],
        dtype=float,
    )

    val_matrix = np.asarray(
        result["val_matrix"],
        dtype=float,
    )

    graph = np.asarray(
        result["graph"]
    )

    return (
        p_matrix,
        val_matrix,
        graph,
    )


# ============================================================================
# LPCMCI ALGORITHM-SELECTED RELATIONSHIPS
#
# Unlike run_pcmci_tests() (which reports the COMPLETE tested hypothesis
# family regardless of significance), this function returns only the
# non-empty cells of Tigramite's PAG (graph[i, j, tau] != ""): the subset
# LPCMCI's own iterative, pc_alpha-controlled constraint testing already
# selected. There is no "complete LPCMCI hypothesis family" to report --
# every discarded (i, j, tau) combination is discarded WITHIN the
# algorithm, not afterward, so downstream callers must not treat this
# output as eligible for a second complete-family correction (e.g.
# Benjamini-Hochberg FDR) the way run_pcmci_tests()'s output is. See
# manufacturing_filter.ManufacturingFilterConfig.apply_fdr_correction for
# where that distinction is enforced.
# ============================================================================


def run_lpcmci_tests(
    values: np.ndarray,
    metrics: Sequence[str],
    *,
    tau_max: int = 3,
    pc_alpha: float = 0.05,
    test_contemporaneous: bool = True,
    **lpcmci_kwargs: Any,
) -> list[CausalDiscoveryTest]:
    """
    Run LPCMCI and return every finite non-self relationship LPCMCI's own
    PAG construction retained, including Tigramite's discovered edge mark.

    IMPORTANT
    ---------
    This is NOT a complete tested hypothesis family (contrast with
    run_pcmci_tests()) -- only non-empty PAG cells are returned.

    No additional p-value threshold is applied here.
    No effect-size threshold is applied here.
    No FDR correction is applied here.

    ``test_contemporaneous`` controls whether lag-0 (contemporaneous) links
    are tested (tau_min=0) in addition to lagged ones. This defaults to True
    because resolving contemporaneous/latent-confounding ambiguity is
    LPCMCI's whole reason for existing over PCMCI; running it with
    tau_min=1 would make it functionally indistinguishable from PCMCI.

    Lag-0 dedup
    -----------
    Tigramite's graph is symmetric at lag 0 — graph[i,j,0] and graph[j,i,0]
    encode the SAME hypothesis (mirrored PAG marks), not two independent
    ones. Only (i,j,0) for i < j is emitted. Lag > 0 entries ARE independent
    hypotheses (does i-at-t-tau affect j-at-t, vs the reverse) and are never
    collapsed this way — both (i,j,tau) and (j,i,tau) are emitted.

    ``**lpcmci_kwargs`` are forwarded verbatim to
    ``tigramite.lpcmci.LPCMCI.run_lpcmci()`` (e.g. n_preliminary_iterations,
    max_cond_px, max_p_global, max_p_non_ancestral, max_q_global,
    max_pds_set, ...).
    """

    matrix, metric_names = _validate_lpcmci_inputs(
        values,
        metrics,
        tau_max,
    )

    tau_min = 0 if test_contemporaneous else 1

    p_matrix, val_matrix, graph = (
        _run_lpcmci_matrices(
            matrix,
            metric_names,
            tau_min=tau_min,
            tau_max=tau_max,
            pc_alpha=pc_alpha,
            lpcmci_kwargs=lpcmci_kwargs,
        )
    )

    tests: list[
        CausalDiscoveryTest
    ] = []

    for source_index, source in enumerate(
        metric_names
    ):
        for target_index, target in enumerate(
            metric_names
        ):
            # The business causal graph does not expose
            # autoregressive self-links.
            if source == target:
                continue

            for lag in range(
                tau_min,
                tau_max + 1,
            ):
                if (
                    lag == 0
                    and source_index
                    > target_index
                ):
                    # Symmetric PAG mirror of an already-emitted lag-0
                    # hypothesis; not an independent test.
                    continue

                mark = str(
                    graph[
                        source_index,
                        target_index,
                        lag,
                    ]
                ).strip()

                # No discovered edge at this lag for this pair.
                if mark in (
                    "",
                    "None",
                ):
                    continue

                p_value = float(
                    p_matrix[
                        source_index,
                        target_index,
                        lag,
                    ]
                )

                score = float(
                    val_matrix[
                        source_index,
                        target_index,
                        lag,
                    ]
                )

                # Never convert invalid numerical output into an edge/test.
                if not (
                    np.isfinite(
                        p_value
                    )
                    and np.isfinite(
                        score
                    )
                ):
                    continue

                # Canonicalize BEFORE persistence: a "<--"/"<-o" mark's
                # arrowhead points at `source`, meaning the true direction
                # is target -> source. Swap + mirror so the stored triple
                # always reads correctly left-to-right (score/p_value are
                # a symmetric partial-correlation statistic between the two
                # variables and do not depend on which is labelled source).
                (
                    canonical_source,
                    canonical_target,
                    canonical_mark,
                ) = canonicalize_edge(
                    mark,
                    source,
                    target,
                )

                tests.append(
                    CausalDiscoveryTest(
                        source=canonical_source,
                        target=canonical_target,
                        lag=lag,
                        score=score,
                        p_value=p_value,
                        edge_mark=canonical_mark,
                        edge_orientation=(
                            edge_orientation_for_mark(
                                canonical_mark
                            )
                        ),
                    )
                )

    return sorted(
        tests,
        key=lambda test: (
            test.p_value,
            -abs(
                test.score
            ),
            test.lag,
            test.source,
            test.target,
        ),
    )