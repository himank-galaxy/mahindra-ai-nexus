"""
Telematics entity selection and panel assembly.

Reads live rows for the selected vehicles out of
vehicle_telematics_timeseries and hands them to the shared preprocessing
pipeline. See IMPLEMENTATION_PLAN.md sections 6-8 for the reasoning behind
every default.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from config import (
    DomainCausalConfig,
    TELEMATICS_BOOLEAN_COLUMNS,
    TELEMATICS_CONTEXT_COLUMNS,
    TELEMATICS_ENTITY_COLUMN,
    TELEMATICS_NUMERIC_COLUMNS,
)
from db_reader import ReadOnlyDatabaseReader, compute_window
from preprocessing import PreprocessResult, preprocess_panel


@dataclass
class EntitySelection:
    selected: list[str]
    considered: int
    excluded_min_rows: int
    row_counts: dict[str, int]


async def select_vehicles(
    reader: ReadOnlyDatabaseReader,
    window_start: datetime,
    window_end: datetime,
    config: DomainCausalConfig,
) -> EntitySelection:
    """
    Same "most data available wins" rule as manufacturing (see
    manufacturing/panel_builder.py select_machines), applied to vehicles.
    """

    row_counts = await reader.telematics_row_counts(window_start, window_end)

    eligible = {
        vehicle_id: count
        for vehicle_id, count in row_counts.items()
        if count >= config.min_raw_rows
    }

    ranked = sorted(eligible.items(), key=lambda item: item[1], reverse=True)
    selected = [vehicle_id for vehicle_id, _ in ranked[: config.max_entities]]

    return EntitySelection(
        selected=selected,
        considered=len(row_counts),
        excluded_min_rows=len(row_counts) - len(eligible),
        row_counts=row_counts,
    )


@dataclass
class TelematicsPanelResult:
    preprocess_result: PreprocessResult
    entity_selection: EntitySelection
    window_start: datetime
    window_end: datetime
    raw_row_count: int


async def build_telematics_panel(
    reader: ReadOnlyDatabaseReader,
    window_end: datetime,
    config: DomainCausalConfig,
) -> TelematicsPanelResult:
    """
    End-to-end: select vehicles, fetch their raw rows, preprocess into a
    standardized wide panel ready for tigramite_adapter.
    """

    window_start, window_end = compute_window(window_end, config.window_hours)

    entity_selection = await select_vehicles(
        reader, window_start, window_end, config
    )

    fetch_columns = (TELEMATICS_ENTITY_COLUMN, "timestamp") + tuple(
        column
        for column in TELEMATICS_NUMERIC_COLUMNS
        if column not in (TELEMATICS_ENTITY_COLUMN, "timestamp")
    )

    raw_rows = await reader.telematics_rows(
        entity_selection.selected, window_start, window_end, fetch_columns
    )

    long_df = pd.DataFrame(
        [dict(row) for row in raw_rows], columns=fetch_columns
    )

    preprocess_result = preprocess_panel(
        long_df,
        entity_column=TELEMATICS_ENTITY_COLUMN,
        numeric_columns=TELEMATICS_NUMERIC_COLUMNS,
        boolean_columns=TELEMATICS_BOOLEAN_COLUMNS,
        resample_minutes=config.resample_minutes,
        max_gap_bins=config.max_gap_bins_to_interpolate,
        near_constant_std_threshold=config.near_constant_std_threshold,
        stationarity_pvalue_threshold=config.stationarity_pvalue_threshold,
    )

    return TelematicsPanelResult(
        preprocess_result=preprocess_result,
        entity_selection=entity_selection,
        window_start=window_start,
        window_end=window_end,
        raw_row_count=len(long_df),
    )


__all__ = [
    "EntitySelection",
    "TelematicsPanelResult",
    "select_vehicles",
    "build_telematics_panel",
    "TELEMATICS_CONTEXT_COLUMNS",
]
