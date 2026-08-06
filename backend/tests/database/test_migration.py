"""Migration sanity: module loads and exposes the expected revision."""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from types import ModuleType

MIGRATION_PATH = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0001_initial_schema.py"


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0001", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_initial_migration_imports() -> None:
    module = _load_migration()
    assert module.revision == "0001"
    assert module.down_revision is None
    assert callable(module.upgrade)
    assert callable(module.downgrade)


def test_migration_covers_every_table() -> None:
    """All 30 planned tables must be created by migration 0001."""
    from app.database.base import Base
    from app.models import User  # noqa: F401 — registers metadata

    source = inspect.getsource(_load_migration().upgrade)
    for table_name in Base.metadata.tables:
        assert f'"{table_name}"' in source, f"table {table_name} missing from upgrade()"
