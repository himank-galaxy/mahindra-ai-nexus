"""
The "explain this warning" step: given one warning, build a causal panel
for exactly that vehicle, ending exactly at the warning's own timestamp
(never later - see IMPLEMENTATION_PLAN.md "avoiding future leakage"),
force-including the warning's target metric, run LPCMCI, and classify the
resulting graph around that target using Causal_Discovery_Service's new
graph_walker.py.

Reuses Causal_Discovery_Service's db_reader, preprocessing, tigramite
adapter, LPCMCI runner, graph builder, and graph walker directly - this
service does not reimplement any of that.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

PREW_ROOT = Path(__file__).resolve().parent
CAUSAL_SERVICE_ROOT = PREW_ROOT.parent / "Causal_Discovery_Service"
if str(CAUSAL_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(CAUSAL_SERVICE_ROOT))

from config import (  # noqa: E402
    TELEMATICS_BOOLEAN_COLUMNS,
    TELEMATICS_ENTITY_COLUMN,
    TELEMATICS_NUMERIC_COLUMNS,
)
from db_reader import ReadOnlyDatabaseReader  # noqa: E402
from graph_builder import build_causal_graph, causal_graph_to_dict  # noqa: E402
from graph_walker import classification_to_dict, classify_graph_around_target  # noqa: E402
from lpcmci_runner import run_lpcmci  # noqa: E402
from preprocessing import preprocess_panel  # noqa: E402
from tigramite_adapter import build_tigramite_dataframe  # noqa: E402
from config import DomainCausalConfig  # noqa: E402

from pews_config import (  # noqa: E402
    CAUSAL_LOOKBACK_HOURS,
    CAUSAL_PC_ALPHA,
    CAUSAL_RESAMPLE_MINUTES,
    CAUSAL_TAU_MAX,
)


@dataclass
class InvestigationResult:
    graph: dict[str, Any]
    classifications: list[dict[str, Any]]
    window_start: datetime
    window_end: datetime
    raw_row_count: int
    panel_shape: tuple[int, int]


async def investigate_warning(
    vehicle_id: str, target_metric: str, warning_timestamp: datetime
) -> InvestigationResult:
    """
    Runs the full explain step for one warning. This performs a real
    LPCMCI run - it is slow (see Causal_Discovery_Service/test_ui/README.md
    for measured runtimes) and should be called from a background task,
    never inline in an HTTP request handler.
    """

    window_end = warning_timestamp
    window_start = window_end - timedelta(hours=CAUSAL_LOOKBACK_HOURS)

    target_var_name = f"{vehicle_id}||{target_metric}"

    reader = ReadOnlyDatabaseReader()
    await reader.connect()
    try:
        fetch_columns = (TELEMATICS_ENTITY_COLUMN, "timestamp") + tuple(
            column
            for column in TELEMATICS_NUMERIC_COLUMNS
            if column not in (TELEMATICS_ENTITY_COLUMN, "timestamp")
        )
        raw_rows = await reader.telematics_rows(
            [vehicle_id], window_start, window_end, fetch_columns
        )
    finally:
        await reader.close()

    long_df = pd.DataFrame([dict(row) for row in raw_rows], columns=fetch_columns)

    preprocess_result = preprocess_panel(
        long_df,
        entity_column=TELEMATICS_ENTITY_COLUMN,
        numeric_columns=TELEMATICS_NUMERIC_COLUMNS,
        boolean_columns=TELEMATICS_BOOLEAN_COLUMNS,
        resample_minutes=CAUSAL_RESAMPLE_MINUTES,
        max_gap_bins=3,
        near_constant_std_threshold=1e-6,
        stationarity_pvalue_threshold=0.05,
        protected_columns=(target_var_name,),
    )

    tigramite_input = build_tigramite_dataframe(preprocess_result)

    investigation_config = DomainCausalConfig(
        domain="telematics_investigation",
        tau_min=0,
        tau_max=CAUSAL_TAU_MAX,
        pc_alpha=CAUSAL_PC_ALPHA,
        window_hours=CAUSAL_LOOKBACK_HOURS,
        resample_minutes=CAUSAL_RESAMPLE_MINUTES,
        min_raw_rows=0,
        max_entities=1,
        max_gap_bins_to_interpolate=3,
        near_constant_std_threshold=1e-6,
        stationarity_pvalue_threshold=0.05,
        auto_difference_nonstationary=False,
    )

    lpcmci_result = run_lpcmci(tigramite_input, investigation_config)

    causal_graph = build_causal_graph(
        domain="telematics",
        var_names=lpcmci_result.var_names,
        graph=lpcmci_result.graph,
        val_matrix=lpcmci_result.val_matrix,
        p_matrix=lpcmci_result.p_matrix,
    )

    classifications = classify_graph_around_target(causal_graph, target_var_name)

    return InvestigationResult(
        graph=causal_graph_to_dict(causal_graph),
        classifications=classification_to_dict(classifications),
        window_start=window_start,
        window_end=window_end,
        raw_row_count=len(long_df),
        panel_shape=tigramite_input.shape,
    )
