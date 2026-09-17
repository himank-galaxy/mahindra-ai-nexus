"""Sample actual mobility business columns without bridging missing time periods."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import MetaData, Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.causal.mobility_features import MobilityFeature, aggregate_feature, discover_features

_BUCKET_EPOCH = datetime(2000, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class CausalInput:
    dates: tuple[datetime, ...]
    metrics: tuple[str, ...]
    values: np.ndarray
    features: tuple[MobilityFeature, ...]
    segments: tuple[tuple[int, int], ...]
    excluded: dict[str, str]
    warnings: tuple[str, ...]
    source_latest_at: datetime | None
    data_origins: tuple[str, ...]
    source_dates: tuple[datetime, ...]


def assemble_panel(
    rows: list[dict],
    features: tuple[MobilityFeature, ...],
    *,
    stride_hours: int,
    min_observations: int,
    tau_max: int,
    source_latest_at: datetime | None,
    expected_regions: set[str],
) -> CausalInput:
    stride = timedelta(hours=stride_hours)
    windows: dict[datetime, list[dict]] = {}
    for row in rows:
        windows.setdefault(row["window_start"], []).append(row)
    samples = []
    skipped = 0
    for timestamp, group in sorted(windows.items()):
        bucket_end = _BUCKET_EPOCH + (((timestamp - _BUCKET_EPOCH) // stride) + 1) * stride
        if {row["region_id"] for row in group} != expected_regions or bucket_end - timestamp > timedelta(minutes=5):
            skipped += 1
            continue
        samples.append((bucket_end, timestamp, group))
    runs: list[list[tuple]] = []
    for sample in samples:
        if not runs or sample[0] - runs[-1][-1][0] != stride:
            runs.append([])
        runs[-1].append(sample)
    # PCMCI discards the first 2*tau_max observations of EACH segment.
    short_count = sum(len(run) for run in runs if len(run) < 2 * tau_max + 3)
    runs = [run for run in runs if len(run) >= 2 * tau_max + 3]
    samples = [sample for run in runs for sample in run]
    usable = sum(len(run) - 2 * tau_max for run in runs)
    if usable < min_observations:
        raise ValueError(
            f"Mobility analysis needs {min_observations} usable observations after time gaps and lag warm-up; "
            f"found {usable}. Waiting for more complete history."
        )
    values = np.array([[aggregate_feature(feature, group) for feature in features] for _, _, group in samples])
    excluded: dict[str, str] = {}
    keep = []
    for index, feature in enumerate(features):
        column = values[:, index]
        if not np.isfinite(column).all():
            excluded[feature.key] = "Missing or non-finite observations"
        elif np.std(column) <= 1e-12:
            excluded[feature.key] = "No variation in the analysis window"
        else:
            keep.append(index)
    if len(keep) < 2:
        raise ValueError("Mobility analysis needs at least two varying numeric business measures.")
    features = tuple(features[index] for index in keep)
    segments = []
    offset = 0
    for run in runs:
        segments.append((offset, offset + len(run)))
        offset += len(run)
    warnings = []
    if len(runs) > 1:
        warnings.append(
            f"History contains gaps: {len(runs)} continuous segments analysed separately; no lag crosses a gap."
        )
    if skipped or short_count:
        warnings.append(
            f"Excluded {skipped} incomplete sampling periods and {short_count} observations in short segments."
        )
    origins = tuple(sorted({str(row.get("data_origin", "UNKNOWN")) for _, _, group in samples for row in group}))
    if "SYNTHETIC" in origins:
        warnings.append(
            "Synthetic data: relationships describe the generated dataset and require validation on business data."
        )
    return CausalInput(
        dates=tuple(sample[0] for sample in samples),
        source_dates=tuple(sample[1] for sample in samples),
        metrics=tuple(feature.key for feature in features),
        values=values[:, keep],
        features=features,
        segments=tuple(segments),
        excluded=excluded,
        warnings=tuple(warnings),
        source_latest_at=source_latest_at,
        data_origins=origins,
    )


async def load_daily_causal_input(
    session: AsyncSession,
    *,
    region_name: str | None = None,
    window_days: int = 90,
    stride_hours: int = 12,
    min_observations: int = 50,
    tau_max: int = 2,
) -> CausalInput:
    if stride_hours < 12:
        raise ValueError("Sampling must be at least 12 hours because source measures are trailing 12-hour rollups.")
    connection = await session.connection()
    # Reflect the fixed live table so new numeric measures need no graph-registry edit.
    table = await connection.run_sync(lambda conn: Table("mobility_timeseries", MetaData(), autoload_with=conn))
    features = discover_features(table)
    now = datetime.now(UTC)
    stride = timedelta(hours=stride_hours)
    boundary = _BUCKET_EPOCH + ((now - _BUCKET_EPOCH) // stride) * stride
    filters = [table.c.window_start >= now - timedelta(days=window_days), table.c.window_start <= now]
    if region_name is not None:
        filters.append(table.c.region_name == region_name)
    source_latest = await session.scalar(select(func.max(table.c.window_start)).where(*filters))
    regions = set((await session.execute(select(table.c.region_id).where(*filters).distinct())).scalars().all())
    bucket = func.date_bin(stride, table.c.window_start, _BUCKET_EPOCH)
    ticks = (
        select(func.max(table.c.window_start).label("tick"))
        .where(
            *filters,
            table.c.window_start < boundary,
        )
        .group_by(bucket)
        .cte("representative_ticks")
    )
    statement = select(table).join(ticks, table.c.window_start == ticks.c.tick).where(*filters)
    rows = [dict(row) for row in (await session.execute(statement.order_by(table.c.window_start))).mappings()]
    return assemble_panel(
        rows,
        features,
        stride_hours=stride_hours,
        min_observations=min_observations,
        tau_max=tau_max,
        source_latest_at=source_latest,
        expected_regions=regions,
    )
