"""Focused tests for the LPCMCI engine addition to pcmci_engine.py."""

from __future__ import annotations

import numpy as np
import pytest
from app.ai.causal.pcmci_engine import (
    ORIENTATION_AMBIGUOUS,
    ORIENTATION_BIDIRECTED,
    ORIENTATION_DIRECTED,
    ORIENTATION_PARTIALLY_ORIENTED,
    CausalDiscoveryTest,
    PcmciTest,
    canonicalize_edge,
    edge_orientation_for_mark,
    pcmci_tests_as_causal_discovery_tests,
    run_lpcmci_tests,
    run_pcmci_tests,
)

ALL_ORIENTATIONS = (
    ORIENTATION_DIRECTED,
    ORIENTATION_BIDIRECTED,
    ORIENTATION_PARTIALLY_ORIENTED,
    ORIENTATION_AMBIGUOUS,
)


def _synthetic_chain(n: int = 300, seed: int = 42) -> tuple[np.ndarray, tuple[str, ...]]:
    """A -> B -> C causal chain, matching the reference pipeline's self-test."""
    rng = np.random.default_rng(seed)
    a = rng.normal(0, 1, n)
    b = np.zeros(n)
    c = np.zeros(n)
    for t in range(2, n):
        b[t] = 0.6 * a[t - 1] + rng.normal(0, 0.5)
        c[t] = 0.6 * b[t - 1] + rng.normal(0, 0.5)
    values = np.column_stack([a, b, c])
    return values, ("metric_a", "metric_b", "metric_c")


def test_edge_orientation_for_mark_buckets_all_four_orientations() -> None:
    assert edge_orientation_for_mark("-->") == ORIENTATION_DIRECTED
    assert edge_orientation_for_mark("<--") == ORIENTATION_DIRECTED
    assert edge_orientation_for_mark("<->") == ORIENTATION_BIDIRECTED
    assert edge_orientation_for_mark("o->") == ORIENTATION_PARTIALLY_ORIENTED
    assert edge_orientation_for_mark("<-o") == ORIENTATION_PARTIALLY_ORIENTED
    assert edge_orientation_for_mark("o-o") == ORIENTATION_AMBIGUOUS
    # An unrecognised future Tigramite mark defaults to ambiguous, never raises.
    assert edge_orientation_for_mark("x-x") == ORIENTATION_AMBIGUOUS
    assert edge_orientation_for_mark("") == ORIENTATION_AMBIGUOUS


def test_canonicalize_edge_forward_marks_pass_through_unchanged() -> None:
    for mark in ("-->", "<->", "o->", "o-o"):
        source, target, canonical_mark = canonicalize_edge(mark, "A", "B")
        assert (source, target, canonical_mark) == ("A", "B", mark)


def test_canonicalize_edge_reversed_marks_swap_and_mirror() -> None:
    # "<--" at (A, B): arrowhead at A means B is the true cause -- must
    # swap to source=B, target=A with the mirrored forward mark "-->", so
    # the persisted triple reads "B --> A" (correct), never "A <-- B"
    # (also correct but not how downstream code reads directed edges) and
    # never source=A/target=B with the raw "<--" (would silently assert
    # the WRONG direction to any consumer reading "source [mark] target").
    source, target, canonical_mark = canonicalize_edge("<--", "A", "B")
    assert (source, target, canonical_mark) == ("B", "A", "-->")

    source, target, canonical_mark = canonicalize_edge("<-o", "A", "B")
    assert (source, target, canonical_mark) == ("B", "A", "o->")


_MIRROR_OF = {
    "-->": "<--",
    "<--": "-->",
    "<->": "<->",
    "o->": "<-o",
    "<-o": "o->",
    "o-o": "o-o",
}


def test_canonicalize_edge_is_consistent_from_either_reading_order() -> None:
    # For marks with a genuine resolved direction (-->/<--/o->/<-o), the
    # SAME physical edge read as (A, B) with its raw mark, or read as
    # (B, A) with that mark's mirror, must canonicalize to the identical
    # (source, target, mark) triple -- proving canonicalization doesn't
    # depend on which arbitrary index order the caller happened to read it
    # from. This does NOT hold for the self-mirrored marks (<->/o-o) --
    # those have no preferred direction, so reading them from (A, B) vs.
    # (B, A) legitimately yields different (equally valid) source/target
    # labels; that is expected, not a bug.
    for mark in ("-->", "<--", "o->", "<-o"):
        forward = canonicalize_edge(mark, "A", "B")
        reversed_reading = canonicalize_edge(_MIRROR_OF[mark], "B", "A")
        assert forward == reversed_reading


def test_canonicalize_edge_never_persists_a_reversed_raw_mark() -> None:
    # After canonicalization, the reversed raw marks must never appear in
    # the returned mark string -- only their mirrors do.
    for mark in ("-->", "<--", "<->", "o->", "<-o", "o-o"):
        _, _, canonical_mark = canonicalize_edge(mark, "A", "B")
        assert canonical_mark not in ("<--", "<-o")


def test_run_lpcmci_tests_reversed_mark_is_canonicalized_end_to_end(monkeypatch) -> None:
    # Force a controlled graph/p/val matrix (bypassing real Tigramite
    # statistics, which we cannot reliably coerce into a specific mark) to
    # prove run_lpcmci_tests() canonicalizes a genuine reversed "<--" cell
    # read at (i=0 "a_metric", j=1 "z_metric") into source="z_metric",
    # target="a_metric", mark="-->" -- i.e. it does NOT persist source=
    # "a_metric", target="z_metric" with the raw reversed mark.
    import app.ai.causal.pcmci_engine as engine

    n_vars = 2
    tau_max = 0
    graph = np.full((n_vars, n_vars, tau_max + 1), "", dtype="<U3")
    graph[0, 1, 0] = "<--"  # arrowhead at index 0 ("a_metric"): z_metric causes a_metric
    p_matrix = np.full((n_vars, n_vars, tau_max + 1), 0.01)
    val_matrix = np.full((n_vars, n_vars, tau_max + 1), 0.6)

    def _fake_run_lpcmci_matrices(values, metrics, *, tau_min, tau_max, pc_alpha, lpcmci_kwargs):
        return p_matrix, val_matrix, graph

    monkeypatch.setattr(engine, "_run_lpcmci_matrices", _fake_run_lpcmci_matrices)

    values = np.zeros((20, n_vars))
    tests = engine.run_lpcmci_tests(
        values,
        ["a_metric", "z_metric"],
        tau_max=tau_max,
        test_contemporaneous=True,
    )

    assert len(tests) == 1
    test = tests[0]
    assert test.source == "z_metric"
    assert test.target == "a_metric"
    assert test.edge_mark == "-->"
    assert test.edge_orientation == ORIENTATION_DIRECTED


def test_pcmci_tests_as_causal_discovery_tests_adapts_to_plain_directed() -> None:
    tests = [
        PcmciTest(source="a", target="b", lag=1, score=0.5, p_value=0.01),
        PcmciTest(source="b", target="a", lag=2, score=-0.3, p_value=0.04),
    ]
    adapted = pcmci_tests_as_causal_discovery_tests(tests)

    assert len(adapted) == 2
    for original, converted in zip(tests, adapted, strict=True):
        assert isinstance(converted, CausalDiscoveryTest)
        assert converted.source == original.source
        assert converted.target == original.target
        assert converted.lag == original.lag
        assert converted.score == original.score
        assert converted.p_value == original.p_value
        assert converted.edge_mark == "-->"
        assert converted.edge_orientation == ORIENTATION_DIRECTED


def test_run_lpcmci_tests_recovers_known_synthetic_chain() -> None:
    values, metrics = _synthetic_chain()

    tests = run_lpcmci_tests(
        values,
        metrics,
        tau_max=2,
        pc_alpha=0.1,
        test_contemporaneous=True,
    )

    assert tests, "LPCMCI should discover at least one edge in a strong synthetic chain"

    by_pair_lag = {(test.source, test.target, test.lag): test for test in tests}

    a_to_b = by_pair_lag.get(("metric_a", "metric_b", 1))
    b_to_c = by_pair_lag.get(("metric_b", "metric_c", 1))

    assert a_to_b is not None, f"expected metric_a->metric_b at lag 1, got {list(by_pair_lag)}"
    assert b_to_c is not None, f"expected metric_b->metric_c at lag 1, got {list(by_pair_lag)}"
    assert abs(a_to_b.score) > 0.2
    assert abs(b_to_c.score) > 0.2

    for test in tests:
        assert test.edge_mark
        assert test.edge_orientation in ALL_ORIENTATIONS
        assert np.isfinite(test.score)
        assert np.isfinite(test.p_value)


def test_run_lpcmci_tests_lag0_dedup_never_emits_mirrored_pair() -> None:
    values, metrics = _synthetic_chain()

    tests = run_lpcmci_tests(values, metrics, tau_max=1, pc_alpha=0.2, test_contemporaneous=True)

    lag0_pairs = {(test.source, test.target) for test in tests if test.lag == 0}
    for source, target in lag0_pairs:
        # The mirrored pair must never also appear at lag 0.
        assert (target, source) not in lag0_pairs


def test_run_lpcmci_tests_lag_gt_0_keeps_both_directions_independent() -> None:
    # A strongly asymmetric chain: only a->b at lag 1 is real, b->a at lag 1
    # is not expected to be planted, but both directions are independently
    # eligible to be tested/emitted (not collapsed like lag 0 is).
    values, metrics = _synthetic_chain()

    tests = run_lpcmci_tests(values, metrics, tau_max=2, pc_alpha=0.3, test_contemporaneous=False)

    # With test_contemporaneous=False, no lag-0 test should ever appear.
    assert all(test.lag >= 1 for test in tests)


def test_run_lpcmci_tests_test_contemporaneous_false_never_returns_lag0() -> None:
    values, metrics = _synthetic_chain()

    tests = run_lpcmci_tests(values, metrics, tau_max=2, pc_alpha=0.1, test_contemporaneous=False)

    assert all(test.lag >= 1 for test in tests)


def test_run_lpcmci_tests_rejects_invalid_tau_max() -> None:
    values, metrics = _synthetic_chain(n=20)

    with pytest.raises(ValueError):
        run_lpcmci_tests(values, metrics, tau_max=-1)


def test_lpcmci_and_pcmci_share_the_same_test_contract_shape() -> None:
    values, metrics = _synthetic_chain()

    lpcmci_tests = run_lpcmci_tests(values, metrics, tau_max=2, pc_alpha=0.1, test_contemporaneous=False)
    pcmci_tests = pcmci_tests_as_causal_discovery_tests(run_pcmci_tests(values, metrics, tau_max=2, pc_alpha=0.1))

    for test in (*lpcmci_tests, *pcmci_tests):
        assert isinstance(test, CausalDiscoveryTest)
        assert isinstance(test.edge_mark, str)
        assert test.edge_orientation in ALL_ORIENTATIONS
