"""Response schemas for the read-only Data explorer."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class DataColumnOut(BaseModel):
    name: str
    data_type: str
    nullable: bool


class DataDatasetLinkOut(BaseModel):
    module_id: str
    relationship_type: str


class DataDatasetOut(BaseModel):
    id: str
    display_name: str
    table_name: str
    description: str
    timestamp_column: str | None
    refresh_mode: str
    columns: tuple[DataColumnOut, ...]
    links: tuple[DataDatasetLinkOut, ...]


class DataModuleOut(BaseModel):
    id: str
    label: str
    route: str | None
    description: str
    datasets: tuple[DataDatasetOut, ...]


class DataCatalogOut(BaseModel):
    modules: tuple[DataModuleOut, ...]
    generated_from: str


class DataMetadataOut(BaseModel):
    total_rows: int = Field(ge=0)
    column_count: int = Field(ge=0)
    latest_timestamp: date | datetime | None = None
    source: str = "PostgreSQL runtime"
    refresh_mode: str
    live_status: str
    data_version: str
    last_refreshed_at: datetime


class DataPaginationOut(BaseModel):
    page_size: int = Field(ge=1)
    has_next: bool
    has_previous: bool
    next_cursor: str | None = None
    previous_cursor: str | None = None


class DataRowsOut(BaseModel):
    dataset: DataDatasetOut
    columns: tuple[DataColumnOut, ...]
    rows: list[dict[str, Any]]
    metadata: DataMetadataOut
    pagination: DataPaginationOut


class DataStatusOut(BaseModel):
    dataset_id: str
    total_rows: int = Field(ge=0)
    latest_timestamp: date | datetime | None = None
    refresh_mode: str
    live_status: str
    data_version: str
    last_checked_at: datetime
