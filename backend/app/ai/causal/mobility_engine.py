"""Mobility-only PCMCI: unrestricted lagged directions and full-family FDR control."""

from dataclasses import dataclass

import numpy as np

from app.ai.causal.data_loader import CausalInput
from app.ai.causal.pcmci_engine import PcmciEdge
from app.ai.causal.preprocessing import standardize


@dataclass(frozen=True)
class MobilityEdge(PcmciEdge):
    q_value: float


def adjusted_pvalues(pvalues: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg over every tested non-self lag, before effect filtering."""
    pvalues = np.where(np.isfinite(pvalues), pvalues, 1.0)
    order = np.argsort(pvalues)
    adjusted = np.minimum.accumulate((pvalues[order] * len(order) / np.arange(1, len(order) + 1))[::-1])[::-1]
    result = np.empty(len(order))
    result[order] = np.clip(adjusted, 0, 1)
    return result


def discover_edges(source: CausalInput, *, tau_max: int, alpha: float) -> tuple[MobilityEdge, ...]:
    from tigramite import data_processing as pp
    from tigramite.independence_tests.parcorr import ParCorr
    from tigramite.pcmci import PCMCI

    values = standardize(source.values)
    panels = {index: values[start:end] for index, (start, end) in enumerate(source.segments)}
    frame = pp.DataFrame(panels, analysis_mode="multiple", var_names=list(source.metrics))
    result = PCMCI(dataframe=frame, cond_ind_test=ParCorr(significance="analytic"), verbosity=0).run_pcmci(
        tau_min=1,
        tau_max=tau_max,
        pc_alpha=alpha,
    )
    hypotheses = [
        (i, j, lag)
        for i in range(len(source.metrics))
        for j in range(len(source.metrics))
        if i != j
        for lag in range(1, tau_max + 1)
    ]
    qvalues = adjusted_pvalues(np.array([result["p_matrix"][index] for index in hypotheses]))
    edges = []
    for index, qvalue in zip(hypotheses, qvalues, strict=True):
        i, j, lag = index
        score, pvalue = float(result["val_matrix"][index]), float(result["p_matrix"][index])
        if np.isfinite(score) and np.isfinite(pvalue) and qvalue <= alpha and abs(score) >= 0.12:
            edges.append(MobilityEdge(source.metrics[i], source.metrics[j], lag, score, pvalue, float(qvalue)))
    return tuple(sorted(edges, key=lambda edge: (-abs(edge.score), edge.source, edge.target, edge.lag)))
