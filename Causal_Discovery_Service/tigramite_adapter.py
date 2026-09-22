"""
Converts a preprocessed wide panel into Tigramite's pp.DataFrame container.

This is the last step before LPCMCI itself would run. Building this object
does not execute any causal-discovery algorithm - it just packages the data
into the format tigramite expects.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from tigramite import data_processing as pp

from preprocessing import PreprocessResult


@dataclass
class TigramiteInput:
    dataframe: "pp.DataFrame"
    var_names: list[str]
    shape: tuple[int, int]


def build_tigramite_dataframe(result: PreprocessResult) -> TigramiteInput:
    """
    Convert a PreprocessResult into a tigramite pp.DataFrame.

    NOTE on `mask` semantics: tigramite follows the numpy.ma convention -
    mask=True marks an entry as EXCLUDED / not usable. Our missing_mask is
    already True exactly where a value is missing after interpolation, so
    it is passed straight through unchanged. (This convention should be
    re-confirmed against the tigramite version in use the first time this
    pipeline is actually executed - see IMPLEMENTATION_PLAN.md section 10.)
    """

    panel = result.panel
    missing_mask = result.missing_mask

    # Any NaN still present must be replaced with a real float for
    # tigramite's underlying numpy array (the mask, not NaN, is what tells
    # tigramite the value is not usable).
    values = panel.fillna(0.0).to_numpy(dtype=float)
    mask_values = missing_mask.to_numpy(dtype=bool)

    var_names = list(panel.columns)
    timestamps = np.array(
        [pd.Timestamp(ts).isoformat() for ts in panel.index]
    )

    dataframe = pp.DataFrame(
        data=values,
        mask=mask_values,
        var_names=var_names,
        datatime=timestamps,
    )

    return TigramiteInput(
        dataframe=dataframe,
        var_names=var_names,
        shape=values.shape,
    )
