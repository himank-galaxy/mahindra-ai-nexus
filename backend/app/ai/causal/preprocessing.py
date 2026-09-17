"""Deterministic preprocessing for PCMCI input."""

from __future__ import annotations

import numpy as np


def standardize(values: np.ndarray) -> np.ndarray:
    """Replace non-finite values and z-score each metric without random imputation."""
    clean = np.asarray(values, dtype=float).copy()
    for column in range(clean.shape[1]):
        series = clean[:, column]
        finite = np.isfinite(series)
        if not finite.any():
            raise ValueError(f"causal input column {column} contains no finite values")
        series[~finite] = float(np.nanmean(series[finite]))
        deviation = float(series.std())
        if deviation == 0:
            raise ValueError(f"causal input column {column} is constant and cannot be tested")
        clean[:, column] = (series - float(series.mean())) / deviation
    return clean
