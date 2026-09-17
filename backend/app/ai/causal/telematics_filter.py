"""Statistical filtering and cross-vehicle stability for telemetry tests."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.ai.causal.pcmci_engine import CausalDiscoveryTest, edge_orientation_for_mark


@dataclass(frozen=True)
class TelematicsFilterConfig:
    # See ManufacturingFilterConfig.apply_fdr_correction for full rationale:
    # False (default) is the LPCMCI-appropriate reference-style behavior
    # (algorithm's own selection + effect-size floor, no post-hoc p-value
    # gate); True reproduces prior PCMCI-rollback behavior exactly, and
    # requires `tests` to be PCMCI's complete hypothesis family.
    apply_fdr_correction: bool = False
    fdr_alpha: float = 0.05
    min_abs_score: float = 0.12
    min_recurrence_fraction: float = 0.25
    min_recurrence_count: int = 2
    min_sign_agreement: float = 0.75
    # See ManufacturingFilterConfig.min_lag / min_mark_agreement for
    # rationale — identical semantics here.
    min_lag: int = 1
    min_mark_agreement: float = 0.0


DEFAULT_TELEMATICS_FILTER_CONFIG = TelematicsFilterConfig()


@dataclass(frozen=True)
class TelematicsFilteredEdge:
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
    vehicle_id: str


@dataclass(frozen=True)
class TelematicsFilterResult:
    vehicle_id: str
    total_tests: int
    fdr_significant_tests: int
    effect_size_significant_tests: int
    accepted_edges: tuple[TelematicsFilteredEdge, ...]
    candidate_pairs: int = 0


@dataclass(frozen=True)
class TelematicsStableEdge:
    source_metric: str
    target_metric: str
    eligible_vehicles: int
    recurring_vehicles: int
    recurrence_fraction: float
    consensus_sign: str
    sign_agreement: float
    consensus_edge_mark: str
    consensus_edge_orientation: str
    mark_agreement: float
    mean_abs_score: float
    median_abs_score: float
    best_q_value: float
    min_p_value: float
    max_p_value: float
    min_q_value: float
    max_q_value: float
    observed_lags: tuple[int, ...]
    observed_lag_minutes: tuple[int, ...]
    vehicle_ids: tuple[str, ...]
    evidence: tuple[dict[str, Any], ...]
    scope: str = "ALL_VEHICLES"


@dataclass(frozen=True)
class TelematicsStabilityResult:
    vehicles_evaluated: int
    candidate_pairs: int
    stable_edges: tuple[TelematicsStableEdge, ...]


def metric_name(variable: str) -> str:
    return variable.split("||", 1)[1] if "||" in variable else variable


def benjamini_hochberg_q_values(p_values: Sequence[float]) -> np.ndarray:
    values = np.asarray(p_values, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
        raise ValueError("p_values must be a finite one-dimensional sequence in [0, 1].")
    if not len(values):
        return np.asarray([], dtype=float)
    order = np.argsort(values, kind="stable")
    adjusted = np.empty(len(values), dtype=float)
    running = 1.0
    for index in range(len(values) - 1, -1, -1):
        original = int(order[index])
        running = min(running, float(values[original]) * len(values) / (index + 1))
        adjusted[original] = min(running, 1.0)
    return adjusted


def _metadata(variable: str, metadata: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any]:
    if variable not in metadata:
        raise ValueError(f"Missing telematics metadata for PCMCI variable: {variable}")
    return metadata[variable]


def filter_telematics_tests(
    tests: Sequence[CausalDiscoveryTest],
    metadata: Mapping[str, Mapping[str, Any]],
    config: TelematicsFilterConfig = DEFAULT_TELEMATICS_FILTER_CONFIG,
) -> TelematicsFilterResult:
    """Apply BH-FDR and effect-size filtering to a complete vehicle family."""

    if not 0.0 < config.fdr_alpha <= 1.0:
        raise ValueError("fdr_alpha must lie in (0, 1].")
    if config.min_abs_score < 0.0:
        raise ValueError("min_abs_score cannot be negative.")
    if not tests:
        raise ValueError("No PCMCI hypothesis tests were supplied.")

    keys: set[tuple[str, str, int]] = set()
    vehicles: set[str] = set()
    for test in tests:
        if test.source == test.target or test.lag < config.min_lag:
            raise ValueError(
                f"Telematics test family must contain non-self lag>={config.min_lag} hypotheses."
            )
        if not np.isfinite(test.score) or not np.isfinite(test.p_value) or not 0 <= test.p_value <= 1:
            raise ValueError("Telematics test family contains invalid statistics.")
        key = (test.source, test.target, test.lag)
        if key in keys:
            raise ValueError(f"Duplicate PCMCI hypothesis: {key}")
        keys.add(key)
        source_meta = _metadata(test.source, metadata)
        target_meta = _metadata(test.target, metadata)
        source_vehicle = str(source_meta.get("vehicle_id") or source_meta.get("entity") or "").strip()
        target_vehicle = str(target_meta.get("vehicle_id") or target_meta.get("entity") or "").strip()
        if not source_vehicle or source_vehicle != target_vehicle:
            raise ValueError("Telematics PCMCI variables must belong to one vehicle panel.")
        vehicles.add(source_vehicle)
    if len(vehicles) != 1:
        raise ValueError("A telematics test family must belong to exactly one vehicle.")

    # See ManufacturingFilterConfig.apply_fdr_correction for the full
    # rationale: BH-FDR is only statistically valid over a COMPLETE tested
    # hypothesis family (true for PCMCI, not for LPCMCI's already
    # PAG-selected output), so it's opt-in via config.apply_fdr_correction.
    q_values = (
        benjamini_hochberg_q_values([test.p_value for test in tests])
        if config.apply_fdr_correction
        else np.asarray([test.p_value for test in tests], dtype=float)
    )
    fdr_count = 0
    effect_count = 0
    accepted: list[TelematicsFilteredEdge] = []
    for test, q_value_raw in zip(tests, q_values, strict=True):
        q_value = float(q_value_raw)
        if q_value <= config.fdr_alpha:
            fdr_count += 1
        if abs(test.score) >= config.min_abs_score:
            effect_count += 1
        fdr_rejected = config.apply_fdr_correction and q_value > config.fdr_alpha
        if fdr_rejected or abs(test.score) < config.min_abs_score:
            continue
        vehicle_id = next(iter(vehicles))
        accepted.append(
            TelematicsFilteredEdge(
                source=test.source,
                target=test.target,
                source_metric=metric_name(test.source),
                target_metric=metric_name(test.target),
                lag=int(test.lag),
                score=float(test.score),
                p_value=float(test.p_value),
                q_value=q_value,
                sign="+" if test.score >= 0 else "-",
                edge_mark=test.edge_mark,
                edge_orientation=test.edge_orientation,
                vehicle_id=vehicle_id,
            )
        )
    return TelematicsFilterResult(
        vehicle_id=next(iter(vehicles)),
        total_tests=len(tests),
        fdr_significant_tests=fdr_count,
        effect_size_significant_tests=effect_count,
        accepted_edges=tuple(accepted),
        candidate_pairs=len({(test.source, test.target) for test in tests}),
    )


def best_edge_per_pair(result: TelematicsFilterResult) -> dict[tuple[str, str], TelematicsFilteredEdge]:
    best: dict[tuple[str, str], TelematicsFilteredEdge] = {}
    for edge in result.accepted_edges:
        key = (edge.source_metric, edge.target_metric)
        current = best.get(key)
        if current is None or (edge.q_value, -abs(edge.score), edge.p_value, edge.lag) < (
            current.q_value,
            -abs(current.score),
            current.p_value,
            current.lag,
        ):
            best[key] = edge
    return best


def aggregate_telematics_stability(
    results: Sequence[TelematicsFilterResult],
    *,
    analysis_frequency_minutes: int = 5,
    config: TelematicsFilterConfig = DEFAULT_TELEMATICS_FILTER_CONFIG,
    candidate_pairs: int | None = None,
) -> TelematicsStabilityResult:
    """Require recurrence and directional agreement across independent vehicles."""

    if not results:
        raise ValueError("At least one eligible vehicle result is required.")
    eligible = len(results)
    if config.min_recurrence_count < 1 or not 0 < config.min_recurrence_fraction <= 1:
        raise ValueError("Invalid telematics recurrence configuration.")
    if not 0 < config.min_sign_agreement <= 1:
        raise ValueError("min_sign_agreement must lie in (0, 1].")

    by_pair: dict[tuple[str, str], dict[str, TelematicsFilteredEdge]] = defaultdict(dict)
    all_candidate_pairs: set[tuple[str, str]] = set()
    for result in results:
        all_candidate_pairs.update((edge.source_metric, edge.target_metric) for edge in result.accepted_edges)
        for pair, edge in best_edge_per_pair(result).items():
            by_pair[pair][result.vehicle_id] = edge

    stable: list[TelematicsStableEdge] = []
    for (source_metric, target_metric), vehicle_edges in by_pair.items():
        recurring = len(vehicle_edges)
        fraction = recurring / eligible
        if recurring < config.min_recurrence_count or fraction < config.min_recurrence_fraction:
            continue
        signs = [edge.sign for edge in vehicle_edges.values()]
        plus = signs.count("+")
        minus = signs.count("-")
        consensus = "+" if plus >= minus else "-"
        sign_agreement = max(plus, minus) / recurring
        if sign_agreement < config.min_sign_agreement:
            continue

        # Mark agreement: reported alongside sign agreement, not gating by
        # default (see TelematicsFilterConfig.min_mark_agreement).
        marks = [edge.edge_mark for edge in vehicle_edges.values()]
        mark_counts: dict[str, int] = {}
        for mark in marks:
            mark_counts[mark] = mark_counts.get(mark, 0) + 1
        consensus_edge_mark = max(sorted(mark_counts), key=lambda mark: mark_counts[mark])
        mark_agreement = mark_counts[consensus_edge_mark] / recurring
        if mark_agreement < config.min_mark_agreement:
            continue
        consensus_edge_orientation = edge_orientation_for_mark(consensus_edge_mark)

        edges = sorted(vehicle_edges.values(), key=lambda edge: edge.vehicle_id)
        lags = tuple(sorted({edge.lag for edge in edges}))
        evidence = tuple(
            {
                "vehicle_id": edge.vehicle_id,
                "lag": edge.lag,
                "lag_minutes": edge.lag * analysis_frequency_minutes,
                "score": edge.score,
                "p_value": edge.p_value,
                "q_value": edge.q_value,
                "sign": edge.sign,
            }
            for edge in edges
        )
        stable.append(
            TelematicsStableEdge(
                source_metric=source_metric,
                target_metric=target_metric,
                eligible_vehicles=eligible,
                recurring_vehicles=recurring,
                recurrence_fraction=fraction,
                consensus_sign=consensus,
                sign_agreement=sign_agreement,
                consensus_edge_mark=consensus_edge_mark,
                consensus_edge_orientation=consensus_edge_orientation,
                mark_agreement=mark_agreement,
                mean_abs_score=float(np.mean([abs(edge.score) for edge in edges])),
                median_abs_score=float(np.median([abs(edge.score) for edge in edges])),
                best_q_value=min(edge.q_value for edge in edges),
                min_p_value=min(edge.p_value for edge in edges),
                max_p_value=max(edge.p_value for edge in edges),
                min_q_value=min(edge.q_value for edge in edges),
                max_q_value=max(edge.q_value for edge in edges),
                observed_lags=lags,
                observed_lag_minutes=tuple(lag * analysis_frequency_minutes for lag in lags),
                vehicle_ids=tuple(edge.vehicle_id for edge in edges),
                evidence=evidence,
            )
        )
    stable.sort(
        key=lambda edge: (
            -edge.recurrence_fraction,
            -edge.sign_agreement,
            edge.best_q_value,
            edge.source_metric,
            edge.target_metric,
        )
    )
    return TelematicsStabilityResult(
        vehicles_evaluated=eligible,
        candidate_pairs=candidate_pairs if candidate_pairs is not None else len(all_candidate_pairs),
        stable_edges=tuple(stable),
    )


__all__ = [
    "DEFAULT_TELEMATICS_FILTER_CONFIG",
    "TelematicsFilterConfig",
    "TelematicsFilterResult",
    "TelematicsFilteredEdge",
    "TelematicsStableEdge",
    "TelematicsStabilityResult",
    "aggregate_telematics_stability",
    "benjamini_hochberg_q_values",
    "best_edge_per_pair",
    "filter_telematics_tests",
    "metric_name",
]
