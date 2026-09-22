"""
CLI entrypoint: manufacturing causal-discovery pipeline.

Runs every stage up to and including building the Tigramite pp.DataFrame,
then prints a summary and writes run_metadata.json. Does NOT call LPCMCI -
see IMPLEMENTATION_PLAN.md section 11. Passing --run-lpcmci raises
NotImplementedError on purpose; that flag is reserved for a later,
explicitly approved phase.

Usage:
    .venv/bin/python3 run_manufacturing_causal_discovery.py
    .venv/bin/python3 run_manufacturing_causal_discovery.py --window-end 2026-08-29T09:00:00+00:00
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from config import MANUFACTURING_CONFIG
from db_reader import ReadOnlyDatabaseReader
from manufacturing.panel_builder import build_manufacturing_panel
from run_writer import new_run_id, write_run_metadata
from tigramite_adapter import build_tigramite_dataframe


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manufacturing causal-discovery pipeline (ingest -> preprocess -> Tigramite panel)."
    )
    parser.add_argument(
        "--window-end",
        type=str,
        default=None,
        help=(
            "ISO timestamp to anchor the rolling window on (default: the "
            "newest timestamp currently in manufacturing_timeseries)."
        ),
    )
    parser.add_argument(
        "--run-lpcmci",
        action="store_true",
        help=(
            "Reserved for a later phase. Intentionally raises "
            "NotImplementedError in this phase."
        ),
    )
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()

    if args.run_lpcmci:
        raise NotImplementedError(
            "LPCMCI execution is intentionally disabled in this phase. "
            "See Causal_Discovery_Service/IMPLEMENTATION_PLAN.md section 11."
        )

    config = MANUFACTURING_CONFIG
    reader = ReadOnlyDatabaseReader()

    await reader.connect()
    try:
        if args.window_end:
            window_end = datetime.fromisoformat(args.window_end)
        else:
            # Anchor on the real wall-clock "now", not MAX(timestamp) from
            # the table. manufacturing_timeseries can contain old
            # historical/replay rows dated in the past relative to today,
            # so MAX(timestamp) is a safe proxy there - but this service
            # deliberately always anchors on wall-clock time so its
            # behavior is identical and correct across both domains (see
            # telematics, where historical rows are dated INTO the future
            # relative to today and MAX(timestamp) would silently anchor
            # on stale historical data instead of the live feed).
            window_end = datetime.now(timezone.utc)

        print(f"Manufacturing causal-discovery pipeline")
        print(f"  window_end        : {window_end.isoformat()}")
        print(f"  window_hours      : {config.window_hours}")
        print(f"  resample_minutes  : {config.resample_minutes}")
        print(f"  tau_min / tau_max : {config.tau_min} / {config.tau_max}")
        print(f"  pc_alpha          : {config.pc_alpha}")
        print()

        panel_result = await build_manufacturing_panel(
            reader, window_end, config
        )

        preprocess = panel_result.preprocess_result
        selection = panel_result.entity_selection

        tigramite_input = build_tigramite_dataframe(preprocess)

        print(f"Entities considered      : {selection.considered}")
        print(f"Entities excluded (rows) : {selection.excluded_min_rows}")
        print(f"Entities selected        : {len(selection.selected)}")
        print(f"Raw rows fetched         : {panel_result.raw_row_count}")
        print(f"Panel shape (T, N)       : {tigramite_input.shape}")
        print(
            "Columns dropped (near-constant): "
            f"{len(preprocess.columns_dropped_near_constant)}"
        )
        print(
            "Columns with stationarity warning: "
            f"{len(preprocess.columns_with_stationarity_warning)}"
        )
        print(
            "Missing data % after interpolation: "
            f"{preprocess.missing_data_pct_after_interpolation}"
        )
        print()
        print("LPCMCI was NOT run (implementation-only phase).")

        run_id = new_run_id()
        metadata_path = write_run_metadata(
            domain="manufacturing",
            run_id=run_id,
            metadata={
                "domain": "manufacturing",
                "window_start": panel_result.window_start,
                "window_end": panel_result.window_end,
                "resample_minutes": config.resample_minutes,
                "tau_min": config.tau_min,
                "tau_max": config.tau_max,
                "pc_alpha": config.pc_alpha,
                "entities_selected": selection.selected,
                "entities_considered": selection.considered,
                "entities_excluded_min_rows": selection.excluded_min_rows,
                "raw_row_count": panel_result.raw_row_count,
                "panel_shape": list(tigramite_input.shape),
                "final_columns": tigramite_input.var_names,
                "columns_dropped_near_constant": preprocess.columns_dropped_near_constant,
                "columns_with_stationarity_warning": preprocess.columns_with_stationarity_warning,
                "missing_data_pct_after_interpolation": preprocess.missing_data_pct_after_interpolation,
                "lpcmci_executed": False,
            },
        )
        print(f"Run metadata written to: {metadata_path}")

    finally:
        await reader.close()


if __name__ == "__main__":
    asyncio.run(_main())
