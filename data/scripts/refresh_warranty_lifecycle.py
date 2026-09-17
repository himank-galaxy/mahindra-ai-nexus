"""Refresh the focused warning -> service -> warranty lifecycle.

This command regenerates only the auto service/warranty leaves from the
existing deterministic seed and canonical delivery/telematics inputs. It
leaves telematics, manufacturing, mobility, and all unrelated CSVs alone.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pandas as pd

from data.generators.auto.service import (
    generate_service_events,
    generate_telemetry_evidence_service_events,
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
DELIVERY_PATH = SYNTHETIC_ROOT / "auto" / "deliveries.csv"
TELEMETRY_PATH = (
    SYNTHETIC_ROOT
    / "causal"
    / "vehicle_telematics_timeseries.csv"
)

SERVICE_LOGICAL_PATH = "synthetic/auto/service_events"
WARRANTY_LOGICAL_PATH = "synthetic/auto/warranty_claims"
DATE_COLUMNS = {
    "service_started_at",
    "service_completed_at",
    "claim_submitted_at",
    "decision_at",
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


def _assert_same_frame(
    name: str,
    expected: pd.DataFrame,
    actual: pd.DataFrame,
) -> None:
    expected = _normalise_dates(expected[actual.columns])
    actual = _normalise_dates(actual)
    pd.testing.assert_frame_equal(
        expected.reset_index(drop=True),
        actual.reset_index(drop=True),
        check_dtype=False,
        check_exact=True,
    )
    print(f"BASE_MATCH {name}: {len(actual)} rows")


def _stage_csv(dataframe: pd.DataFrame, destination: Path) -> Path:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            dataframe.to_csv(
                handle,
                index=False,
                lineterminator="\n",
            )
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
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{MANIFEST_PATH.name}.",
            suffix=".tmp",
            dir=MANIFEST_PATH.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(
                manifest,
                handle,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            handle.write("\n")
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    assert temporary_path is not None
    return temporary_path


def _update_manifest(
    service_events: pd.DataFrame,
    warranty_claims: pd.DataFrame,
    service_temp: Path,
    warranty_temp: Path,
) -> Path:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    by_path = {
        item["logical_path"]: item
        for item in manifest["datasets"]
    }
    changed = {
        SERVICE_LOGICAL_PATH: (service_events, service_temp),
        WARRANTY_LOGICAL_PATH: (warranty_claims, warranty_temp),
    }

    for logical_path, (dataframe, temporary_path) in changed.items():
        if logical_path not in by_path:
            raise KeyError(f"Manifest entry missing: {logical_path}")
        record = by_path[logical_path]
        record.update(
            {
                "rows": len(dataframe),
                "columns": len(dataframe.columns),
                "column_names": [str(column) for column in dataframe.columns],
                "dtypes": {
                    str(column): str(dtype)
                    for column, dtype in dataframe.dtypes.items()
                },
                "bytes": int(temporary_path.stat().st_size),
                "sha256": _sha256(temporary_path),
            }
        )

    manifest["total_rows"] = int(
        sum(int(item["rows"]) for item in manifest["datasets"])
    )
    signature = hashlib.sha256()
    for record in sorted(
        manifest["datasets"],
        key=lambda item: item["logical_path"],
    ):
        signature.update(
            (
                f"{record['logical_path']}\0"
                f"{record['rows']}\0"
                f"{record['columns']}\0"
                f"{record['sha256']}\n"
            ).encode()
        )
    manifest["registry_sha256"] = signature.hexdigest()
    return _stage_manifest(manifest)


def main() -> int:
    generation = load_generation_config()
    deliveries = pd.read_csv(DELIVERY_PATH)
    telemetry = pd.read_csv(TELEMETRY_PATH)
    existing_service = pd.read_csv(SERVICE_PATH)
    existing_warranty = pd.read_csv(WARRANTY_PATH)

    base_service = generate_service_events(
        deliveries=deliveries,
        generation=generation,
    )
    base_service_ids = set(base_service["service_event_id"])
    stored_base_service = existing_service[
        existing_service["service_event_id"].isin(base_service_ids)
    ].copy()
    _assert_same_frame(
        "service_events",
        stored_base_service,
        base_service,
    )

    base_warranty = generate_warranty_claims(
        service_events=base_service,
        generation=generation,
    )
    base_warranty_ids = set(base_warranty["warranty_claim_id"])
    stored_base_warranty = existing_warranty[
        existing_warranty["warranty_claim_id"].isin(base_warranty_ids)
    ].copy()
    _assert_same_frame(
        "warranty_claims",
        stored_base_warranty,
        base_warranty,
    )

    service_events = generate_telemetry_evidence_service_events(
        deliveries=deliveries,
        service_events=base_service,
        telemetry_timeseries=telemetry,
        generation=generation,
    )
    warranty_claims = generate_warranty_claims(
        service_events=service_events,
        generation=generation,
    )

    timezone = generation["time"]["timezone"]
    generation_end = pd.Timestamp(
        generation["iot"]["end_date"],
        tz=timezone,
    )
    validate_service_events(
        service_events=service_events,
        deliveries=deliveries,
        generation_end=generation_end,
    )
    validate_warranty_claims(
        warranty_claims=warranty_claims,
        service_events=service_events,
        generation_end=generation_end,
    )

    service_temp = _stage_csv(service_events, SERVICE_PATH)
    warranty_temp = _stage_csv(warranty_claims, WARRANTY_PATH)
    manifest_temp: Path | None = None
    try:
        manifest_temp = _update_manifest(
            service_events=service_events,
            warranty_claims=warranty_claims,
            service_temp=service_temp,
            warranty_temp=warranty_temp,
        )
        os.replace(service_temp, SERVICE_PATH)
        os.replace(warranty_temp, WARRANTY_PATH)
        os.replace(manifest_temp, MANIFEST_PATH)
        manifest_temp = None
    finally:
        service_temp.unlink(missing_ok=True)
        warranty_temp.unlink(missing_ok=True)
        if manifest_temp is not None:
            manifest_temp.unlink(missing_ok=True)

    new_service = service_events.iloc[len(base_service):]
    new_claims = warranty_claims[
        ~warranty_claims["warranty_claim_id"].isin(base_warranty_ids)
    ]
    print(f"SERVICE_EVENTS {len(base_service)} -> {len(service_events)}")
    print(f"WARRANTY_CLAIMS {len(base_warranty)} -> {len(warranty_claims)}")
    print(
        "NEW_SERVICE_IDS "
        + ",".join(new_service["service_event_id"].astype(str))
    )
    print(
        "NEW_CLAIM_IDS "
        + ",".join(new_claims["warranty_claim_id"].astype(str))
    )
    print(f"SERVICE_SHA256 {_sha256(SERVICE_PATH)}")
    print(f"WARRANTY_SHA256 {_sha256(WARRANTY_PATH)}")
    print("STATUS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
