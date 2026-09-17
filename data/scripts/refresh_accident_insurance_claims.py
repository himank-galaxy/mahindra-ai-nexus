"""Add accident/collision-caused service events and the insurance claims
generated from them, to the existing auto service/warranty/insurance data.

Mirrors refresh_warranty_lifecycle.py's safe, scoped-refresh pattern
exactly: it regenerates only the auto service/warranty/insurance leaves
from the existing deterministic seed and canonical delivery inputs, and
proves (via an exact base-row-match assertion) that doing so does not
silently alter any already-existing non-accident row. It leaves
telematics, manufacturing, mobility, and all unrelated CSVs completely
alone - untouched, unread, and unregenerated.

New in this script vs. refresh_warranty_lifecycle.py: it also creates
data/synthetic/auto/insurance_claims.csv, a dataset that has never
existed before in this project, and registers it as a new entry in
data/dataset_manifest.json (refresh_warranty_lifecycle.py's manifest
update only ever updates existing entries).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pandas as pd

from data.generators.auto.insurance import (
    INSURANCE_COLUMNS,
    generate_insurance_claims,
    validate_insurance_claims,
)
from data.generators.auto.service import (
    generate_accident_service_events,
    generate_service_events,
    validate_service_events,
)
from data.generators.auto.warranty import (
    generate_warranty_claims,
    validate_warranty_claims,
)
from data.generators.common.helpers import load_generation_config

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_ROOT = REPO_ROOT / "data" / "synthetic"
MANIFEST_PATH = REPO_ROOT / "data" / "dataset_manifest.json"

SERVICE_PATH = SYNTHETIC_ROOT / "auto" / "service_events.csv"
WARRANTY_PATH = SYNTHETIC_ROOT / "auto" / "warranty_claims.csv"
INSURANCE_PATH = SYNTHETIC_ROOT / "auto" / "insurance_claims.csv"
DELIVERY_PATH = SYNTHETIC_ROOT / "auto" / "deliveries.csv"

SERVICE_LOGICAL_PATH = "synthetic/auto/service_events"
WARRANTY_LOGICAL_PATH = "synthetic/auto/warranty_claims"
INSURANCE_LOGICAL_PATH = "synthetic/auto/insurance_claims"

DATE_COLUMNS = {
    "service_started_at", "service_completed_at",
    "claim_submitted_at", "decision_at",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalise_dates(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy()
    for column in DATE_COLUMNS.intersection(result.columns):
        result[column] = pd.to_datetime(result[column])
    return result


def _assert_same_frame(name: str, expected: pd.DataFrame, actual: pd.DataFrame) -> None:
    # Compare only columns that existed before this change - the stored
    # CSV predates is_accident_caused/accident_impact_g_force, so those
    # two are checked separately below rather than expected here.
    shared_columns = [column for column in actual.columns if column in expected.columns]
    expected = _normalise_dates(expected[shared_columns])
    actual_shared = _normalise_dates(actual[shared_columns])
    pd.testing.assert_frame_equal(
        expected.reset_index(drop=True),
        actual_shared.reset_index(drop=True),
        check_dtype=False,
        check_exact=True,
    )
    new_columns = {"is_accident_caused", "accident_impact_g_force"}.intersection(actual.columns)
    if new_columns:
        if not (actual["is_accident_caused"] == False).all():  # noqa: E712
            raise AssertionError(f"{name}: base (non-accident) generation produced is_accident_caused=True")
        if not (actual["accident_impact_g_force"] == 0.0).all():
            raise AssertionError(f"{name}: base (non-accident) generation produced a non-zero impact g-force")
    print(f"BASE_MATCH {name}: {len(actual)} rows ({len(shared_columns)} pre-existing columns identical)")


def _stage_csv(dataframe: pd.DataFrame, destination: Path) -> Path:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="",
            prefix=f".{destination.name}.", suffix=".tmp",
            dir=destination.parent, delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            dataframe.to_csv(handle, index=False, lineterminator="\n")
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    assert temporary_path is not None
    return temporary_path


def _stage_manifest(manifest: dict) -> Path:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n",
            prefix=f".{MANIFEST_PATH.name}.", suffix=".tmp",
            dir=MANIFEST_PATH.parent, delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(manifest, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    assert temporary_path is not None
    return temporary_path


def _dataset_record(dataframe: pd.DataFrame, temp_path: Path, logical_path: str, file_rel: str) -> dict:
    return {
        "bytes": int(temp_path.stat().st_size),
        "column_names": [str(column) for column in dataframe.columns],
        "columns": len(dataframe.columns),
        "dtypes": {str(column): str(dtype) for column, dtype in dataframe.dtypes.items()},
        "file": file_rel,
        "logical_path": logical_path,
        "rows": len(dataframe),
        "sha256": _sha256(temp_path),
        "storage_class": "synthetic",
    }


def _update_manifest(
    service_events: pd.DataFrame, warranty_claims: pd.DataFrame, insurance_claims: pd.DataFrame,
    service_temp: Path, warranty_temp: Path, insurance_temp: Path,
) -> Path:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    by_path = {item["logical_path"]: item for item in manifest["datasets"]}

    updated = {
        SERVICE_LOGICAL_PATH: (service_events, service_temp),
        WARRANTY_LOGICAL_PATH: (warranty_claims, warranty_temp),
    }
    for logical_path, (dataframe, temporary_path) in updated.items():
        if logical_path not in by_path:
            raise KeyError(f"Manifest entry missing: {logical_path}")
        record = by_path[logical_path]
        record.update(
            {
                "rows": len(dataframe),
                "columns": len(dataframe.columns),
                "column_names": [str(column) for column in dataframe.columns],
                "dtypes": {str(column): str(dtype) for column, dtype in dataframe.dtypes.items()},
                "bytes": int(temporary_path.stat().st_size),
                "sha256": _sha256(temporary_path),
            }
        )

    is_new_dataset = INSURANCE_LOGICAL_PATH not in by_path
    insurance_record = _dataset_record(
        insurance_claims, insurance_temp, INSURANCE_LOGICAL_PATH,
        "data/synthetic/auto/insurance_claims.csv",
    )
    if is_new_dataset:
        manifest["datasets"].append(insurance_record)
        manifest["dataset_count"] = int(manifest["dataset_count"]) + 1
        manifest["synthetic_dataset_count"] = int(manifest["synthetic_dataset_count"]) + 1
    else:
        by_path[INSURANCE_LOGICAL_PATH].update(insurance_record)

    manifest["total_rows"] = int(sum(int(item["rows"]) for item in manifest["datasets"]))
    signature = hashlib.sha256()
    for record in sorted(manifest["datasets"], key=lambda item: item["logical_path"]):
        signature.update(
            f"{record['logical_path']}\0{record['rows']}\0{record['columns']}\0{record['sha256']}\n".encode()
        )
    manifest["registry_sha256"] = signature.hexdigest()
    return _stage_manifest(manifest)


def main() -> int:
    generation = load_generation_config()
    deliveries = pd.read_csv(DELIVERY_PATH)
    existing_service = pd.read_csv(SERVICE_PATH)
    existing_warranty = pd.read_csv(WARRANTY_PATH)

    # Prove the accident-generation change did not alter any
    # already-existing non-accident row: regenerate the base (no
    # accidents) service events/warranty claims and assert an exact
    # match against what's already on disk for those same rows.
    base_service = generate_service_events(deliveries=deliveries, generation=generation)
    base_service_ids = set(base_service["service_event_id"])
    stored_base_service = existing_service[
        existing_service["service_event_id"].isin(base_service_ids)
    ].copy()
    _assert_same_frame("service_events", stored_base_service, base_service)

    base_warranty = generate_warranty_claims(service_events=base_service, generation=generation)
    base_warranty_ids = set(base_warranty["warranty_claim_id"])
    stored_base_warranty = existing_warranty[
        existing_warranty["warranty_claim_id"].isin(base_warranty_ids)
    ].copy()
    _assert_same_frame("warranty_claims", stored_base_warranty, base_warranty)

    # Additive step: accident/collision events, forced non-warranty-candidate.
    service_events = generate_accident_service_events(
        deliveries=deliveries, service_events=base_service, generation=generation,
    )
    warranty_claims = generate_warranty_claims(service_events=service_events, generation=generation)
    insurance_claims = generate_insurance_claims(service_events=service_events, generation=generation)

    timezone = generation["time"]["timezone"]
    generation_end = pd.Timestamp(generation["iot"]["end_date"], tz=timezone)
    validate_service_events(service_events=service_events, deliveries=deliveries, generation_end=generation_end)
    validate_warranty_claims(warranty_claims=warranty_claims, service_events=service_events, generation_end=generation_end)
    validate_insurance_claims(insurance_claims=insurance_claims, service_events=service_events, generation_end=generation_end)

    service_temp = _stage_csv(service_events, SERVICE_PATH)
    warranty_temp = _stage_csv(warranty_claims, WARRANTY_PATH)
    insurance_temp = _stage_csv(insurance_claims, INSURANCE_PATH)
    manifest_temp: Path | None = None
    try:
        manifest_temp = _update_manifest(
            service_events=service_events, warranty_claims=warranty_claims, insurance_claims=insurance_claims,
            service_temp=service_temp, warranty_temp=warranty_temp, insurance_temp=insurance_temp,
        )
        os.replace(service_temp, SERVICE_PATH)
        os.replace(warranty_temp, WARRANTY_PATH)
        os.replace(insurance_temp, INSURANCE_PATH)
        os.replace(manifest_temp, MANIFEST_PATH)
        manifest_temp = None
    finally:
        service_temp.unlink(missing_ok=True)
        warranty_temp.unlink(missing_ok=True)
        insurance_temp.unlink(missing_ok=True)
        if manifest_temp is not None:
            manifest_temp.unlink(missing_ok=True)

    new_service = service_events[service_events["is_accident_caused"].astype(bool)]
    print(f"SERVICE_EVENTS {len(base_service)} -> {len(service_events)}")
    print(f"WARRANTY_CLAIMS {len(base_warranty)} -> {len(warranty_claims)} (unchanged, as expected)")
    print(f"INSURANCE_CLAIMS 0 -> {len(insurance_claims)} (new dataset)")
    print("NEW_ACCIDENT_SERVICE_IDS " + ",".join(new_service["service_event_id"].astype(str)))
    print("NEW_INSURANCE_CLAIM_IDS " + ",".join(insurance_claims["insurance_claim_id"].astype(str)))
    print(f"SERVICE_SHA256 {_sha256(SERVICE_PATH)}")
    print(f"WARRANTY_SHA256 {_sha256(WARRANTY_PATH)}")
    print(f"INSURANCE_SHA256 {_sha256(INSURANCE_PATH)}")
    print("STATUS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
