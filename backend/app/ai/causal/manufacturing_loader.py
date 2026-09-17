"""
Mahindra manufacturing data loader for the
Warranty & Quality Early-Warning Graph.

Purpose
-------
Read canonical manufacturing observations from PostgreSQL and convert them
into the generic long-format contract expected by the causal-discovery layer:

    timestamp
    entity
    metric
    value

For Mahindra:

    entity = machine_id

Example:

    {
        "timestamp": datetime(...),
        "entity": "MACHINE_SYN_001",
        "metric": "vibration_mm_s",
        "value": 2.47,
    }

Mahindra lineage is retained alongside the generic fields so later stages
can explain an early warning through:

    plant
    production line
    machine
    production batch
    supplier lot
    vehicle model

Important
---------
This module reads ONLY runtime operational data.

It must NOT read:
    - data/ground_truth/*
    - manufacturing_causal_edges.csv
    - scenario expectation files

Ground truth remains evaluation-only.

Warranty claims and service events are also deliberately excluded from the
manufacturing PCMCI input. They will be joined later as downstream early-warning
evidence and business-impact enrichment.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.runtime_schema import runtime_tables

# ============================================================================
# RUNTIME TABLE
# ============================================================================

MANUFACTURING_TABLE = runtime_tables[
    "manufacturing_timeseries"
]


# ============================================================================
# CAUSAL INPUT METRICS
#
# Only numeric operational/process variables belong in the PCMCI/LPCMCI
# panel.
#
# IDs, names, statuses and provenance fields remain metadata/lineage.
# ============================================================================

MANUFACTURING_METRICS: tuple[str, ...] = (
    "ambient_temperature_c",
    "ambient_humidity_pct",
    "machine_load",
    "machine_temperature_c",
    "vibration_mm_s",
    "power_kw",
    "line_speed_units_per_hour",
    "cycle_time_seconds",
    "hours_since_maintenance",
    "maintenance_overdue_hours",
    "supplier_lot_quality_score",
    "torque_deviation_nm",
    "paint_booth_temperature_c",
    "paint_booth_humidity_pct",
    "paint_defect_rate",
    "defect_rate",
    "rework_rate",
    "downtime_minutes",
    "quality_score",
)


# ============================================================================
# LINEAGE
#
# These fields are NOT causal variables.
#
# They are retained so that a statistically discovered process relationship
# can later be connected to Mahindra business entities.
# ============================================================================

LINEAGE_COLUMNS: tuple[str, ...] = (
    "plant_id",
    "plant_name",
    "production_line_id",
    "production_line_name",
    "line_type",
    "machine_id",
    "machine_name",
    "production_batch_id",
    "vehicle_model_id",
    "vehicle_model_name",
    "supplier_lot_id",
)


# Legacy row-count baseline. New callers should use DEFAULT_HISTORY_HOURS so
# source cadence cannot silently redefine the business-time window.
DEFAULT_OBSERVATIONS = 500

# A 72-hour rolling window keeps enough 15-minute analytical observations for
# the 19-variable PCMCI family while remaining practical across the established
# manufacturing cohort.
DEFAULT_HISTORY_HOURS = 72.0


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


def _normalise_entities(
    entities: Sequence[str],
) -> set[str]:
    """
    Validate and normalise requested machine IDs.
    """

    machine_ids = {
        str(entity).strip()
        for entity in entities
        if str(entity).strip()
    }

    if not machine_ids:
        raise ValueError(
            "At least one manufacturing machine ID "
            "must be supplied."
        )

    return machine_ids


def _parse_force_include_metrics(
    force_include_metrics: Sequence[str] | None,
) -> tuple[set[str], set[str]]:
    """
    Parse mentor-style force-inclusion identifiers.

    Expected format:

        MACHINE_SYN_001||defect_rate
        MACHINE_SYN_001||vibration_mm_s

    Returns
    -------
    forced_entities:
        Machine IDs referenced in the identifiers.

    forced_metrics:
        Metric names referenced in the identifiers.
    """

    forced_entities: set[str] = set()
    forced_metrics: set[str] = set()

    for item in force_include_metrics or ():
        value = str(item).strip()

        if not value:
            continue

        if "||" not in value:
            raise ValueError(
                "force_include_metrics entries must use "
                "'entity||metric' format. "
                f"Invalid value: {value!r}"
            )

        entity_id, metric_name = value.split(
            "||",
            1,
        )

        entity_id = entity_id.strip()
        metric_name = metric_name.strip()

        if not entity_id:
            raise ValueError(
                "force_include_metrics contains "
                f"an empty entity: {value!r}"
            )

        if not metric_name:
            raise ValueError(
                "force_include_metrics contains "
                f"an empty metric: {value!r}"
            )

        if metric_name not in MANUFACTURING_METRICS:
            raise ValueError(
                "Unsupported Mahindra manufacturing metric "
                f"{metric_name!r}."
            )

        forced_entities.add(
            entity_id
        )

        forced_metrics.add(
            metric_name
        )

    return (
        forced_entities,
        forced_metrics,
    )


def _optional_text(
    value: Any,
) -> str | None:
    """
    Convert lineage values to strings without converting NULL to 'None'.
    """

    if value is None:
        return None

    return str(
        value
    )


def _duration_window_start(
    latest_timestamp: Any,
    history_hours: float,
) -> Any:
    """Return the exclusive start of a trailing wall-clock source window."""

    return latest_timestamp - timedelta(
        hours=float(
            history_hours
        )
    )


# ============================================================================
# PUBLIC EXTRACTION FUNCTION
# ============================================================================


async def fetch_raw_records(
    session: AsyncSession,
    entities: Sequence[str],
    observations: int | None = None,
    force_include_metrics: Sequence[str] | None = None,
    *,
    history_hours: float = DEFAULT_HISTORY_HOURS,
    analysis_end: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    Extract duration-bounded manufacturing observations for causal discovery.

    Parameters
    ----------
    session:
        SQLAlchemy AsyncSession connected to the canonical
        Mahindra PostgreSQL runtime database.

    entities:
        Machine IDs.

        Example:

            [
                "MACHINE_SYN_001",
                "MACHINE_SYN_005",
            ]

    observations:
        Optional legacy row limit per machine. New callers should leave this
        as ``None`` and use ``history_hours`` so cadence changes do not alter
        the real-world source duration.

    history_hours:
        Trailing wall-clock duration to retrieve per machine, anchored to the
        latest timestamp at or before ``analysis_end`` for that machine rather
        than wall-clock now.

    analysis_end:
        Optional timezone-aware upper bound for a historical analysis window.
        When omitted, each machine remains anchored to its latest observation.

    force_include_metrics:
        Optional mentor-style identifiers:

            [
                "MACHINE_SYN_001||defect_rate",
                "MACHINE_SYN_001||vibration_mm_s",
            ]

        Machines referenced here are automatically added to the extraction.

    Returns
    -------
    list[dict[str, Any]]

        Long-format observations.

        Generic causal-discovery fields:

            timestamp
            entity
            metric
            value

        Mahindra lineage fields:

            plant_id
            plant_name
            production_line_id
            production_line_name
            line_type
            machine_id
            machine_name
            production_batch_id
            vehicle_model_id
            vehicle_model_name
            supplier_lot_id

    Example record
    --------------

        {
            "timestamp": ...,
            "entity": "MACHINE_SYN_001",
            "metric": "defect_rate",
            "value": 0.018,

            "plant_id": "PLANT_SYN_001",
            "production_line_id": "LINE_SYN_001",
            "machine_id": "MACHINE_SYN_001",
            "production_batch_id": "BATCH_SYN_0123",
            "vehicle_model_id": "MODEL_SYN_001",
            "supplier_lot_id": "SUPLOT_SYN_0042",
        }

    Runtime isolation
    -----------------
    This function deliberately does NOT read:

        warranty_claims
        service_events
        ground_truth files
        causal ground truth
        scenario expectations

    Manufacturing causal discovery must operate independently.

    Warranty/service evidence is attached later by the
    Warranty & Quality Early-Warning layer.
    """

    if observations is not None:
        if not isinstance(
            observations,
            int,
        ):
            raise TypeError(
                "observations must be an integer or None."
            )

        if observations <= 0:
            raise ValueError(
                "observations must be greater than zero."
            )

    try:
        history_hours_value = float(
            history_hours
        )
    except (TypeError, ValueError) as exc:
        raise TypeError(
            "history_hours must be numeric."
        ) from exc

    if (
        not math.isfinite(history_hours_value)
        or history_hours_value <= 0.0
    ):
        raise ValueError(
            "history_hours must be a finite positive duration."
        )

    analysis_end_value: datetime | None = None

    if analysis_end is not None:
        if not isinstance(
            analysis_end,
            datetime,
        ):
            raise TypeError(
                "analysis_end must be a datetime or None."
            )

        if (
            analysis_end.tzinfo is None
            or analysis_end.utcoffset() is None
        ):
            raise ValueError(
                "analysis_end must be timezone-aware."
            )

        analysis_end_value = analysis_end.astimezone(
            UTC
        )

    # ------------------------------------------------------------------------
    # Requested machines
    # ------------------------------------------------------------------------

    machine_ids = _normalise_entities(
        entities
    )

    (
        forced_entities,
        forced_metrics,
    ) = _parse_force_include_metrics(
        force_include_metrics
    )

    machine_ids.update(
        forced_entities
    )

    ordered_machine_ids = sorted(
        machine_ids
    )

    # ------------------------------------------------------------------------
    # Validate machine IDs against canonical PostgreSQL data.
    # ------------------------------------------------------------------------

    machine_validation_query = (
        select(
            MANUFACTURING_TABLE.c.machine_id
        )
        .where(
            MANUFACTURING_TABLE.c.machine_id.in_(
                ordered_machine_ids
            )
        )
        .distinct()
    )

    validation_result = await session.execute(
        machine_validation_query
    )

    existing_machine_ids = {
        str(machine_id)
        for machine_id
        in validation_result.scalars().all()
    }

    missing_machine_ids = sorted(
        machine_ids
        - existing_machine_ids
    )

    if missing_machine_ids:
        raise ValueError(
            "Unknown Mahindra manufacturing machine ID(s): "
            + ", ".join(
                missing_machine_ids
            )
        )

    # ------------------------------------------------------------------------
    # Metric selection
    #
    # Currently the Warranty & Quality graph considers all canonical
    # manufacturing causal metrics.
    #
    # force_include_metrics remains supported to preserve the mentor
    # pipeline contract and future variable-selection behaviour.
    # ------------------------------------------------------------------------

    selected_metrics = tuple(
        dict.fromkeys(
            (
                *MANUFACTURING_METRICS,
                *sorted(
                    forced_metrics
                ),
            )
        )
    )

    # ------------------------------------------------------------------------
    # Columns needed from PostgreSQL.
    # ------------------------------------------------------------------------

    lineage_sql_columns = tuple(
        MANUFACTURING_TABLE.c[
            column_name
        ]
        for column_name
        in LINEAGE_COLUMNS
    )

    metric_sql_columns = tuple(
        MANUFACTURING_TABLE.c[
            metric_name
        ]
        for metric_name
        in selected_metrics
    )

    # ------------------------------------------------------------------------
    # Rank observations independently for every machine.
    #
    # This guarantees:
    #
    # MACHINE_SYN_001 -> latest 500
    # MACHINE_SYN_005 -> latest 500
    #
    # instead of allowing one machine to consume another machine's window.
    # ------------------------------------------------------------------------

    ranked_observations_query = (
        select(
            MANUFACTURING_TABLE.c.timestamp,
            *lineage_sql_columns,
            *metric_sql_columns,
            func.row_number()
            .over(
                partition_by=(
                    MANUFACTURING_TABLE.c.machine_id
                ),
                order_by=(
                    MANUFACTURING_TABLE.c.timestamp.desc()
                ),
            )
            .label(
                "_observation_rank"
            ),
            func.max(
                MANUFACTURING_TABLE.c.timestamp
            )
            .over(
                partition_by=(
                    MANUFACTURING_TABLE.c.machine_id
                )
            )
            .label(
                "_latest_timestamp"
            ),
        )
        .where(
            MANUFACTURING_TABLE.c.machine_id.in_(
                ordered_machine_ids
            )
        )
    )

    if analysis_end_value is not None:
        ranked_observations_query = ranked_observations_query.where(
            MANUFACTURING_TABLE.c.timestamp
            <= analysis_end_value
        )

    ranked_observations = (
        ranked_observations_query.subquery(
            "ranked_manufacturing_observations"
        )
    )

    # ------------------------------------------------------------------------
    # Retrieve selected window and restore chronological ordering.
    # ------------------------------------------------------------------------

    query_columns = (
        ranked_observations.c.timestamp,
        *(
            ranked_observations.c[
                column_name
            ]
            for column_name
            in LINEAGE_COLUMNS
        ),
        *(
            ranked_observations.c[
                metric_name
            ]
            for metric_name
            in selected_metrics
        ),
    )

    extraction_query = select(
        *query_columns
    )

    if observations is not None:
        extraction_query = extraction_query.where(
            ranked_observations.c._observation_rank
            <= observations
        )
    else:
        # Half-open trailing window: (latest - duration, latest]. At an exact
        # one-minute cadence, 72 hours therefore yields exactly 4,320 rows.
        extraction_query = extraction_query.where(
            ranked_observations.c.timestamp
            > (
                _duration_window_start(
                    ranked_observations.c._latest_timestamp,
                    history_hours_value,
                )
            )
        )

    extraction_query = extraction_query.order_by(
        ranked_observations.c.timestamp,
        ranked_observations.c.machine_id,
    )

    result = await session.execute(
        extraction_query
    )

    rows = result.mappings().all()

    # ------------------------------------------------------------------------
    # Validate observation count PER machine.
    # ------------------------------------------------------------------------

    observation_counts = Counter(
        str(
            row["machine_id"]
        )
        for row in rows
    )

    minimum_required = (
        observations
        if observations is not None
        else 2
    )

    insufficient_history = {
        machine_id: observation_counts.get(
            machine_id,
            0,
        )
        for machine_id
        in ordered_machine_ids
        if observation_counts.get(
            machine_id,
            0,
        )
        < minimum_required
    }

    if insufficient_history:
        details = ", ".join(
            (
                f"{machine_id}="
                f"{count}/{minimum_required}"
            )
            for machine_id, count
            in sorted(
                insufficient_history.items()
            )
        )

        raise ValueError(
            "Insufficient manufacturing history: "
            + details
        )

    # ------------------------------------------------------------------------
    # Wide PostgreSQL rows -> generic long causal records.
    #
    # One PostgreSQL timestamp has many metrics.
    #
    # Example wide row:
    #
    # timestamp | machine | temperature | vibration | defect
    #
    # becomes:
    #
    # timestamp | machine||temperature | value
    # timestamp | machine||vibration   | value
    # timestamp | machine||defect      | value
    # ------------------------------------------------------------------------

    records: list[
        dict[str, Any]
    ] = []

    for row in rows:
        machine_id = str(
            row["machine_id"]
        )

        for metric_name in selected_metrics:
            raw_value = row[
                metric_name
            ]

            # Paint variables are intentionally NULL outside paint lines.
            # NULL is absence of measurement, not zero.
            if raw_value is None:
                continue

            try:
                numeric_value = float(
                    raw_value
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            # Tigramite/ParCorr must not receive NaN or infinity.
            if not math.isfinite(
                numeric_value
            ):
                continue

            records.append(
                {
                    # ========================================================
                    # GENERIC CAUSAL CONTRACT
                    # ========================================================

                    "timestamp": row[
                        "timestamp"
                    ],

                    "entity": machine_id,

                    "metric": metric_name,

                    "value": numeric_value,

                    # ========================================================
                    # MAHINDRA LINEAGE
                    # ========================================================

                    "plant_id": _optional_text(
                        row[
                            "plant_id"
                        ]
                    ),

                    "plant_name": _optional_text(
                        row[
                            "plant_name"
                        ]
                    ),

                    "production_line_id": _optional_text(
                        row[
                            "production_line_id"
                        ]
                    ),

                    "production_line_name": _optional_text(
                        row[
                            "production_line_name"
                        ]
                    ),

                    "line_type": _optional_text(
                        row[
                            "line_type"
                        ]
                    ),

                    "machine_id": machine_id,

                    "machine_name": _optional_text(
                        row[
                            "machine_name"
                        ]
                    ),

                    "production_batch_id": _optional_text(
                        row[
                            "production_batch_id"
                        ]
                    ),

                    "vehicle_model_id": _optional_text(
                        row[
                            "vehicle_model_id"
                        ]
                    ),

                    "vehicle_model_name": _optional_text(
                        row[
                            "vehicle_model_name"
                        ]
                    ),

                    "supplier_lot_id": _optional_text(
                        row[
                            "supplier_lot_id"
                        ]
                    ),
                }
            )

    return records


def detect_raw_frequency_minutes(
    records: Sequence[dict[str, Any]],
) -> float:
    """Infer the modal positive source cadence from runtime observations."""

    timestamps_by_machine: dict[str, set[Any]] = {}

    for record in records:
        machine_id = str(
            record.get("entity", "")
        ).strip()

        timestamp = record.get("timestamp")

        if machine_id and timestamp is not None:
            timestamps_by_machine.setdefault(
                machine_id,
                set(),
            ).add(timestamp)

    cadence_seconds: Counter[float] = Counter()

    for timestamps in timestamps_by_machine.values():
        ordered = sorted(timestamps)

        for previous, current in zip(
            ordered,
            ordered[1:],
            strict=False,
        ):
            delta_seconds = (
                current - previous
            ).total_seconds()

            if delta_seconds > 0.0:
                cadence_seconds[
                    float(delta_seconds)
                ] += 1

    if not cadence_seconds:
        raise ValueError(
            "At least two distinct manufacturing timestamps are required "
            "to detect raw source cadence."
        )

    mode_seconds = min(
        cadence_seconds,
        key=lambda seconds: (
            -cadence_seconds[seconds],
            seconds,
        ),
    )

    return mode_seconds / 60.0
