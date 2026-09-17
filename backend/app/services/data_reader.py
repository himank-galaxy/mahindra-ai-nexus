"""Safe, server-side PostgreSQL reads for the Data explorer."""

from __future__ import annotations

import base64
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.schema import Column
from sqlalchemy.sql.sqltypes import DateTime

from app.core.errors import BadRequestError, NotFoundError
from app.database.runtime_schema import runtime_tables
from app.schemas.data import (
    DataCatalogOut,
    DataColumnOut,
    DataDatasetLinkOut,
    DataDatasetOut,
    DataMetadataOut,
    DataModuleOut,
    DataPaginationOut,
    DataRowsOut,
    DataStatusOut,
)
from app.services.data_catalog import DATASET_BY_ID, MODULES, DatasetSpec, datasets_for_module

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def _now() -> datetime:
    return datetime.now(UTC)


def _type_name(column: Column[Any]) -> str:
    value = str(column.type).upper()
    if isinstance(column.type, DateTime):
        return "TIMESTAMPTZ" if getattr(column.type, "timezone", False) else "TIMESTAMP"
    return value


def _columns(spec: DatasetSpec) -> tuple[DataColumnOut, ...]:
    table = runtime_tables[spec.table_name]
    return tuple(
        DataColumnOut(name=column.name, data_type=_type_name(column), nullable=bool(column.nullable))
        for column in table.columns
    )


def _dataset_out(spec: DatasetSpec) -> DataDatasetOut:
    return DataDatasetOut(
        id=spec.id,
        display_name=spec.display_name,
        table_name=spec.table_name,
        description=spec.description,
        timestamp_column=spec.timestamp_column,
        refresh_mode=spec.refresh_mode,
        columns=_columns(spec),
        links=tuple(
            DataDatasetLinkOut(module_id=link.module_id, relationship_type=link.relationship_type)
            for link in spec.links
        ),
    )


def _primary_sort_columns(spec: DatasetSpec) -> tuple[Column[Any], ...]:
    table = runtime_tables[spec.table_name]
    primary_key = tuple(table.primary_key.columns)
    if spec.timestamp_column:
        timestamp = table.c[spec.timestamp_column]
        remainder = tuple(column for column in primary_key if column.name != spec.timestamp_column)
        return (timestamp, *remainder)
    return primary_key


def _cursor_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _encode_cursor(spec: DatasetSpec, row: dict[str, Any], sort_columns: tuple[Column[Any], ...]) -> str:
    payload = {"dataset": spec.id, "values": [_cursor_value(row[column.name]) for column in sort_columns]}
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def _decode_cursor(spec: DatasetSpec, token: str, sort_columns: tuple[Column[Any], ...]) -> list[Any]:
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if payload.get("dataset") != spec.id or not isinstance(payload.get("values"), list):
            raise ValueError
        values = payload["values"]
        if len(values) != len(sort_columns):
            raise ValueError
        return [_parse_cursor_value(column, value) for column, value in zip(sort_columns, values, strict=True)]
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeError) as exc:
        raise BadRequestError("Invalid pagination cursor.", code="invalid_data_cursor") from exc


def _parse_cursor_value(column: Column[Any], value: Any) -> Any:
    if value is None:
        return None
    python_type = getattr(column.type, "python_type", str)
    if python_type is datetime:
        return datetime.fromisoformat(str(value))
    if python_type is date:
        return date.fromisoformat(str(value))
    if python_type is bool:
        return bool(value)
    if python_type is int:
        return int(value)
    if python_type is float:
        return float(value)
    return str(value)


def _cursor_predicate(sort_columns: tuple[Column[Any], ...], values: list[Any], *, before: bool) -> Any:
    clauses = []
    prefix = []
    for column, value in zip(sort_columns, values, strict=True):
        comparison = column > value if before else column < value
        clauses.append(and_(*prefix, comparison))
        prefix.append(column == value)
    return or_(*clauses)


def _rows_as_dicts(result: Any) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in result]


def _live_status(spec: DatasetSpec, total_rows: int, latest: date | datetime | None) -> str:
    if spec.refresh_mode == "STATIC":
        return "STATIC"
    if total_rows == 0 or latest is None:
        return "NOT_READY"
    if isinstance(latest, datetime):
        observed = latest if latest.tzinfo is not None else latest.replace(tzinfo=UTC)
    else:
        observed = datetime.combine(latest, datetime.min.time(), tzinfo=UTC)
    age_seconds = (_now() - observed).total_seconds()
    if age_seconds <= 180:
        return "LIVE"
    if age_seconds <= 600:
        return "STALE"
    return "PAUSED"


class DataReader:
    """Query service backed only by the validated runtime table registry."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _get_dataset(dataset_id: str) -> DatasetSpec:
        try:
            return DATASET_BY_ID[dataset_id]
        except KeyError as exc:
            raise NotFoundError(f"Dataset '{dataset_id}' was not found.", code="dataset_not_found") from exc

    async def catalog(self) -> DataCatalogOut:
        modules: list[DataModuleOut] = []
        for module in MODULES:
            datasets = tuple(_dataset_out(dataset) for dataset in datasets_for_module(module.id))
            modules.append(
                DataModuleOut(
                    id=module.id,
                    label=module.label,
                    route=module.route,
                    description=module.description,
                    datasets=datasets,
                )
            )
        return DataCatalogOut(modules=tuple(modules), generated_from="docs/Data_Dictionary.docx")

    async def _summary(self, spec: DatasetSpec) -> tuple[int, date | datetime | None]:
        table = runtime_tables[spec.table_name]
        total = int((await self._session.execute(select(func.count()).select_from(table))).scalar_one())
        latest = None
        if spec.timestamp_column:
            latest = (
                await self._session.execute(select(func.max(table.c[spec.timestamp_column])))
            ).scalar_one_or_none()
        return total, latest

    async def status(self, dataset_id: str) -> DataStatusOut:
        spec = self._get_dataset(dataset_id)
        total, latest = await self._summary(spec)
        version = f"{total}:{latest.isoformat() if latest is not None else 'empty'}"
        return DataStatusOut(
            dataset_id=spec.id,
            total_rows=total,
            latest_timestamp=latest,
            refresh_mode=spec.refresh_mode,
            live_status=_live_status(spec, total, latest),
            data_version=version,
            last_checked_at=_now(),
        )

    async def rows(
        self,
        dataset_id: str,
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
        before: str | None = None,
    ) -> DataRowsOut:
        spec = self._get_dataset(dataset_id)
        if page_size < 1 or page_size > MAX_PAGE_SIZE:
            raise BadRequestError(f"page_size must be between 1 and {MAX_PAGE_SIZE}.", code="invalid_page_size")
        if cursor and before:
            raise BadRequestError("Use either cursor or before, not both.", code="invalid_pagination")

        table = runtime_tables[spec.table_name]
        table_columns = tuple(table.columns)
        sort_columns = _primary_sort_columns(spec)
        sort_values: list[Any] | None = None
        is_before = before is not None
        if cursor:
            sort_values = _decode_cursor(spec, cursor, sort_columns)
        elif before:
            sort_values = _decode_cursor(spec, before, sort_columns)

        statement = select(*table_columns)
        if sort_values is not None:
            statement = statement.where(_cursor_predicate(sort_columns, sort_values, before=is_before))
        if is_before:
            statement = statement.order_by(*(column.asc() for column in sort_columns))
        else:
            statement = statement.order_by(*(column.desc() for column in sort_columns))
        result = await self._session.execute(statement.limit(page_size + 1))
        rows = _rows_as_dicts(result)
        has_more = len(rows) > page_size
        rows = rows[:page_size]
        if is_before:
            rows.reverse()

        total, latest = await self._summary(spec)
        first_cursor = _encode_cursor(spec, rows[0], sort_columns) if rows else None
        last_cursor = _encode_cursor(spec, rows[-1], sort_columns) if rows else None
        has_previous = cursor is not None or before is not None
        return DataRowsOut(
            dataset=_dataset_out(spec),
            columns=_columns(spec),
            rows=rows,
            metadata=DataMetadataOut(
                total_rows=total,
                column_count=len(table_columns),
                latest_timestamp=latest,
                refresh_mode=spec.refresh_mode,
                live_status=_live_status(spec, total, latest),
                data_version=f"{total}:{latest.isoformat() if latest is not None else 'empty'}",
                last_refreshed_at=_now(),
            ),
            pagination=DataPaginationOut(
                page_size=page_size,
                has_next=has_more,
                has_previous=has_previous,
                next_cursor=last_cursor if has_more else None,
                previous_cursor=first_cursor if has_previous else None,
            ),
        )


__all__ = ["DEFAULT_PAGE_SIZE", "MAX_PAGE_SIZE", "DataReader"]
