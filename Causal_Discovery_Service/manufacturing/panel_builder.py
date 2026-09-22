"""
Manufacturing entity selection and panel assembly.

Reads live rows for the selected machines out of manufacturing_timeseries
and hands them to the shared preprocessing pipeline. See
IMPLEMENTATION_PLAN.md sections 6-8 for the reasoning behind every default.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from config import (
    DomainCausalConfig,
    MANUFACTURING_CONTEXT_COLUMNS,
    MANUFACTURING_ENTITY_COLUMN,
    MANUFACTURING_NUMERIC_COLUMNS,
)
from db_reader import ReadOnlyDatabaseReader, compute_window
from preprocessing import PreprocessResult, preprocess_panel


@dataclass
class EntitySelection:
    selected: list[str]
    considered: int
    excluded_min_rows: int
    row_counts: dict[str, int]


async def select_machines(
    reader: ReadOnlyDatabaseReader,
    window_start: datetime,
    window_end: datetime,
    config: DomainCausalConfig,
) -> EntitySelection:
    """
    "Most data available wins": rank machines by raw row count inside the
    window, keep only those meeting the minimum-row floor, then take the
    top `max_entities`.
    """

    row_counts = await reader.manufacturing_row_counts(
        window_start, window_end
    )

    eligible = {
        machine_id: count
        for machine_id, count in row_counts.items()
        if count >= config.min_raw_rows
    }

    ranked = sorted(eligible.items(), key=lambda item: item[1], reverse=True)
    selected = [machine_id for machine_id, _ in ranked[: config.max_entities]]

    return EntitySelection(
        selected=selected,
        considered=len(row_counts),
        excluded_min_rows=len(row_counts) - len(eligible),
        row_counts=row_counts,
    )


@dataclass
class ManufacturingPanelResult:
    preprocess_result: PreprocessResult
    entity_selection: EntitySelection
    window_start: datetime
    window_end: datetime
    raw_row_count: int


async def build_manufacturing_panel(
    reader: ReadOnlyDatabaseReader,
    window_end: datetime,
    config: DomainCausalConfig,
) -> ManufacturingPanelResult:
    """
    End-to-end: select machines, fetch their raw rows, preprocess into a
    standardized wide panel ready for tigramite_adapter.
    """

    window_start, window_end = compute_window(window_end, config.window_hours)

    entity_selection = await select_machines(
        reader, window_start, window_end, config
    )

    fetch_columns = (MANUFACTURING_ENTITY_COLUMN, "timestamp") + tuple(
        column
        for column in MANUFACTURING_NUMERIC_COLUMNS
        if column not in (MANUFACTURING_ENTITY_COLUMN, "timestamp")
    )

    raw_rows = await reader.manufacturing_rows(
        entity_selection.selected, window_start, window_end, fetch_columns
    )

    long_df = pd.DataFrame(
        [dict(row) for row in raw_rows], columns=fetch_columns
    )

    preprocess_result = preprocess_panel(
        long_df,
        entity_column=MANUFACTURING_ENTITY_COLUMN,
        numeric_columns=MANUFACTURING_NUMERIC_COLUMNS,
        boolean_columns=(),
        resample_minutes=config.resample_minutes,
        max_gap_bins=config.max_gap_bins_to_interpolate,
        near_constant_std_threshold=config.near_constant_std_threshold,
        stationarity_pvalue_threshold=config.stationarity_pvalue_threshold,
    )

    return ManufacturingPanelResult(
        preprocess_result=preprocess_result,
        entity_selection=entity_selection,
        window_start=window_start,
        window_end=window_end,
        raw_row_count=len(long_df),
    )


__all__ = [
    "EntitySelection",
    "ManufacturingPanelResult",
    "select_machines",
    "build_manufacturing_panel",
    "MANUFACTURING_CONTEXT_COLUMNS",
]
