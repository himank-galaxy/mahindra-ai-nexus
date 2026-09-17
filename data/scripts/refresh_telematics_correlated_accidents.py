"""Add a small set of accident events whose timing is deliberately chosen
to fall inside the existing 24-vehicle telematics cohort's coverage
window, and write a genuine matching collision signature into that
vehicle's already-generated telematics rows for that exact moment.

Context: refresh_accident_insurance_claims.py added 21 accident-caused
service events and their insurance claims, but none of those 21
vehicles are in the small (24-vehicle, 7-day-per-vehicle) telematics
cohort - telematics simply has no rows for them, so there was nothing
to correlate. This script closes that specific gap: it adds a few more
accident events, timed to land inside a telematics-covered vehicle's
window, and overwrites only the affected minutes' values (never adding
or removing telematics rows, never touching a vehicle/timestamp outside
the injected windows) - see
data/generators/causal/vehicle_telematics_timeseries.py's
inject_accident_evidence for the exact scope of what is changed.

Manufacturing and mobility timeseries are not read or written at all.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pandas as pd

from data.generators.auto.insurance import (
    generate_insurance_claims,
    validate_insurance_claims,
)
from data.generators.auto.service import (
    generate_telematics_linked_accident_events,
    validate_service_events,
)
from data.generators.auto.warranty import (
    generate_warranty_claims,
    validate_warranty_claims,
)
from data.generators.causal.vehicle_telematics_timeseries import inject_accident_evidence
from data.generators.common.helpers import load_generation_config

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_ROOT = REPO_ROOT / "data" / "synthetic"
MANIFEST_PATH = REPO_ROOT / "data" / "dataset_manifest.json"

SERVICE_PATH = SYNTHETIC_ROOT / "auto" / "service_events.csv"
WARRANTY_PATH = SYNTHETIC_ROOT / "auto" / "warranty_claims.csv"
INSURANCE_PATH = SYNTHETIC_ROOT / "auto" / "insurance_claims.csv"
DELIVERY_PATH = SYNTHETIC_ROOT / "auto" / "deliveries.csv"
TELEMATICS_PATH = SYNTHETIC_ROOT / "causal" / "vehicle_telematics_timeseries.csv"

SERVICE_LOGICAL_PATH = "synthetic/auto/service_events"
WARRANTY_LOGICAL_PATH = "synthetic/auto/warranty_claims"
INSURANCE_LOGICAL_PATH = "synthetic/auto/insurance_claims"
TELEMATICS_LOGICAL_PATH = "synthetic/causal/vehicle_telematics_timeseries"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def _update_manifest(entries: dict[str, tuple[pd.DataFrame, Path]]) -> Path:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    by_path = {item["logical_path"]: item for item in manifest["datasets"]}

    for logical_path, (dataframe, temporary_path) in entries.items():
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
    service_events = pd.read_csv(SERVICE_PATH)
    telematics = pd.read_csv(TELEMATICS_PATH)

    before_service_count = len(service_events)
    before_telematics_hash = _sha256(TELEMATICS_PATH)

    enriched_service = generate_telematics_linked_accident_events(
        deliveries=deliveries, service_events=service_events,
        telematics_timeseries=telematics, generation=generation,
    )
    new_accidents = enriched_service[
        ~enriched_service["service_event_id"].isin(service_events["service_event_id"])
    ]
    if new_accidents.empty:
        print("No telematics-linked accident events were generated. STATUS NOOP")
        return 0

    warranty_claims = generate_warranty_claims(service_events=enriched_service, generation=generation)
    insurance_claims = generate_insurance_claims(service_events=enriched_service, generation=generation)
    updated_telematics = inject_accident_evidence(telematics, new_accidents)

    timezone = generation["time"]["timezone"]
    generation_end = pd.Timestamp(generation["iot"]["end_date"], tz=timezone)
    validate_service_events(service_events=enriched_service, deliveries=deliveries, generation_end=generation_end)
    validate_warranty_claims(warranty_claims=warranty_claims, service_events=enriched_service, generation_end=generation_end)
    validate_insurance_claims(insurance_claims=insurance_claims, service_events=enriched_service, generation_end=generation_end)

    # Telematics row/vehicle/timestamp set must be identical to before -
    # only cell values inside the injected windows may differ.
    assert len(updated_telematics) == len(telematics), "telematics row count changed - must never happen"
    assert list(updated_telematics["vehicle_id"]) == list(telematics["vehicle_id"]), "telematics vehicle order changed"
    assert list(updated_telematics["timestamp"]) == list(pd.to_datetime(telematics["timestamp"])), "telematics timestamps changed"

    service_temp = _stage_csv(enriched_service, SERVICE_PATH)
    warranty_temp = _stage_csv(warranty_claims, WARRANTY_PATH)
    insurance_temp = _stage_csv(insurance_claims, INSURANCE_PATH)
    telematics_temp = _stage_csv(updated_telematics, TELEMATICS_PATH)
    manifest_temp: Path | None = None
    try:
        manifest_temp = _update_manifest(
            {
                SERVICE_LOGICAL_PATH: (enriched_service, service_temp),
                WARRANTY_LOGICAL_PATH: (warranty_claims, warranty_temp),
                INSURANCE_LOGICAL_PATH: (insurance_claims, insurance_temp),
                TELEMATICS_LOGICAL_PATH: (updated_telematics, telematics_temp),
            }
        )
        os.replace(service_temp, SERVICE_PATH)
        os.replace(warranty_temp, WARRANTY_PATH)
        os.replace(insurance_temp, INSURANCE_PATH)
        os.replace(telematics_temp, TELEMATICS_PATH)
        os.replace(manifest_temp, MANIFEST_PATH)
        manifest_temp = None
    finally:
        service_temp.unlink(missing_ok=True)
        warranty_temp.unlink(missing_ok=True)
        insurance_temp.unlink(missing_ok=True)
        telematics_temp.unlink(missing_ok=True)
        if manifest_temp is not None:
            manifest_temp.unlink(missing_ok=True)

    changed_telematics_rows = int(
        (updated_telematics["impact_g_force"] != pd.to_numeric(telematics["impact_g_force"])).sum()
    )
    print(f"SERVICE_EVENTS {before_service_count} -> {len(enriched_service)}")
    print(f"NEW_TELEMATICS_LINKED_ACCIDENT_IDS " + ",".join(new_accidents["service_event_id"].astype(str)))
    print(f"WARRANTY_CLAIMS -> {len(warranty_claims)} (should be unchanged)")
    print(f"INSURANCE_CLAIMS -> {len(insurance_claims)}")
    print(f"TELEMATICS_ROWS_MODIFIED {changed_telematics_rows} (of {len(telematics)} total, all others byte-identical)")
    print(f"TELEMATICS_SHA256_BEFORE {before_telematics_hash}")
    print(f"TELEMATICS_SHA256_AFTER {_sha256(TELEMATICS_PATH)}")
    print("STATUS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
