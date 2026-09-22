"""
Test UI API for the Causal Discovery Service.

This is a SEPARATE FastAPI app, with its own endpoints, built only for this
local testing/verification UI. It is not registered with, imported by, or
reachable through the existing backend (backend/app/api/*) in any way.

It reuses this service's OWN modules (config.py, db_reader.py,
manufacturing/panel_builder.py, telematics/panel_builder.py,
tigramite_adapter.py, lpcmci_runner.py, graph_builder.py, run_writer.py) -
that is expected reuse within Causal_Discovery_Service itself, not a
dependency on the old (backend/app/ai/causal) causal service, which this
app never imports.

Unlike the rest of Causal_Discovery_Service (implemented but deliberately
not executed), THIS app actually calls lpcmci_runner.run_lpcmci() for real,
per the explicit instruction that created this test UI. Because LPCMCI can
take a long time even on a handful of variables, every run happens as a
background asyncio task; the UI polls a status endpoint rather than
blocking on one HTTP request.

Binds to 127.0.0.1 only (see run_test_ui.sh) - never 0.0.0.0 - and is never
added to docker-compose or any existing deployment.
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import MANUFACTURING_CONFIG, TELEMATICS_CONFIG, DomainCausalConfig
from db_reader import ReadOnlyDatabaseReader
from graph_builder import build_causal_graph, causal_graph_to_dict
from lpcmci_runner import run_lpcmci
from manufacturing.panel_builder import build_manufacturing_panel
from telematics.panel_builder import build_telematics_panel
from tigramite_adapter import build_tigramite_dataframe
from run_writer import new_run_id, write_graph, write_run_metadata

import asyncio

app = FastAPI(title="Causal Discovery Service - Test UI API")

# Local-only test tool: the frontend is a plain static page served from a
# different local port (see run_test_ui.sh), so CORS must allow that origin.
# This app is never exposed beyond 127.0.0.1.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Domain = Literal["manufacturing", "telematics"]

# Test-scale default: real production defaults (config.py) use up to 15
# entities, which makes LPCMCI take an extremely long time - measured
# directly against this live database: 1 machine (14 variables) completed
# in ~4-8s, but 2 machines (28 variables) was still running after several
# minutes (see test_ui/README.md for the exact numbers). LPCMCI's runtime
# grows very fast with variable count, so this test UI defaults to the
# smallest useful cohort (1 entity) so a first run reliably finishes
# quickly; the user can still ask for more via the request body, at the
# cost of a much longer wait.
TEST_UI_DEFAULT_MAX_ENTITIES = 1


@dataclass
class RunJob:
    run_id: str
    domain: Domain
    status: str  # PENDING | RUNNING | COMPLETED | FAILED
    started_at: datetime
    finished_at: datetime | None = None
    config_used: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    graph: dict[str, Any] | None = None
    error: str | None = None


# In-memory job store. This is a local, throwaway test tool - runs do not
# need to survive an API restart, and nothing here is written to the shared
# production database.
_JOBS: dict[str, RunJob] = {}


class RunRequest(BaseModel):
    max_entities: int = Field(default=TEST_UI_DEFAULT_MAX_ENTITIES, ge=1, le=30)
    tau_max: int | None = Field(default=None, ge=1, le=20)
    pc_alpha: float | None = Field(default=None, gt=0, lt=1)
    window_hours: int | None = Field(default=None, ge=1)


def _effective_config(domain: Domain, request: RunRequest) -> DomainCausalConfig:
    base = MANUFACTURING_CONFIG if domain == "manufacturing" else TELEMATICS_CONFIG

    return DomainCausalConfig(
        domain=base.domain,
        tau_min=base.tau_min,
        tau_max=request.tau_max if request.tau_max is not None else base.tau_max,
        pc_alpha=request.pc_alpha if request.pc_alpha is not None else base.pc_alpha,
        window_hours=request.window_hours
        if request.window_hours is not None
        else base.window_hours,
        resample_minutes=base.resample_minutes,
        min_raw_rows=base.min_raw_rows,
        max_entities=request.max_entities,
        max_gap_bins_to_interpolate=base.max_gap_bins_to_interpolate,
        near_constant_std_threshold=base.near_constant_std_threshold,
        stationarity_pvalue_threshold=base.stationarity_pvalue_threshold,
        auto_difference_nonstationary=base.auto_difference_nonstationary,
    )


async def _execute_run(job: RunJob, config: DomainCausalConfig) -> None:
    job.status = "RUNNING"

    reader = ReadOnlyDatabaseReader()
    try:
        await reader.connect()
        window_end = datetime.now(timezone.utc)

        if job.domain == "manufacturing":
            panel_result = await build_manufacturing_panel(reader, window_end, config)
        else:
            panel_result = await build_telematics_panel(reader, window_end, config)

        preprocess = panel_result.preprocess_result
        selection = panel_result.entity_selection

        tigramite_input = build_tigramite_dataframe(preprocess)

        job.summary = {
            "window_start": panel_result.window_start.isoformat(),
            "window_end": panel_result.window_end.isoformat(),
            "entities_considered": selection.considered,
            "entities_excluded_min_rows": selection.excluded_min_rows,
            "entities_selected": selection.selected,
            "raw_row_count": panel_result.raw_row_count,
            "panel_shape": list(tigramite_input.shape),
            "final_columns": tigramite_input.var_names,
            "columns_dropped_near_constant": preprocess.columns_dropped_near_constant,
            "columns_with_stationarity_warning": preprocess.columns_with_stationarity_warning,
            "missing_data_pct_after_interpolation": preprocess.missing_data_pct_after_interpolation,
        }

        # LPCMCI is synchronous, CPU-bound, and can be slow - run it in a
        # worker thread so this event loop stays responsive for other
        # requests (in particular, status polling for this same job).
        lpcmci_result = await asyncio.to_thread(run_lpcmci, tigramite_input, config)

        causal_graph = build_causal_graph(
            domain=job.domain,
            var_names=lpcmci_result.var_names,
            graph=lpcmci_result.graph,
            val_matrix=lpcmci_result.val_matrix,
            p_matrix=lpcmci_result.p_matrix,
        )
        graph_dict = causal_graph_to_dict(causal_graph)

        job.graph = graph_dict
        job.status = "COMPLETED"
        job.finished_at = datetime.now(timezone.utc)

        write_run_metadata(
            domain=job.domain,
            run_id=job.run_id,
            metadata={
                "domain": job.domain,
                "source": "test_ui",
                "tau_min": config.tau_min,
                "tau_max": config.tau_max,
                "pc_alpha": config.pc_alpha,
                "lpcmci_executed": True,
                **job.summary,
            },
        )
        write_graph(domain=job.domain, run_id=job.run_id, graph_dict=graph_dict)

    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        job.status = "FAILED"
        job.error = str(exc)
        job.finished_at = datetime.now(timezone.utc)
    finally:
        await reader.close()


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "causal-discovery-test-ui"}


@app.post("/api/{domain}/run")
async def start_run(domain: Domain, request: RunRequest) -> dict[str, Any]:
    config = _effective_config(domain, request)

    run_id = new_run_id()
    job = RunJob(
        run_id=run_id,
        domain=domain,
        status="PENDING",
        started_at=datetime.now(timezone.utc),
        config_used={
            "tau_min": config.tau_min,
            "tau_max": config.tau_max,
            "pc_alpha": config.pc_alpha,
            "window_hours": config.window_hours,
            "resample_minutes": config.resample_minutes,
            "max_entities": config.max_entities,
            "min_raw_rows": config.min_raw_rows,
        },
    )
    _JOBS[run_id] = job

    asyncio.create_task(_execute_run(job, config))

    return {"run_id": run_id, "status": job.status, "domain": domain}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    job = _JOBS.get(run_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown run_id")

    return {
        "run_id": job.run_id,
        "domain": job.domain,
        "status": job.status,
        "started_at": job.started_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "config_used": job.config_used,
        "summary": job.summary,
        "graph": job.graph,
        "error": job.error,
    }


@app.get("/api/runs")
async def list_runs(domain: Domain | None = None) -> list[dict[str, Any]]:
    jobs = sorted(_JOBS.values(), key=lambda j: j.started_at, reverse=True)
    if domain is not None:
        jobs = [job for job in jobs if job.domain == domain]

    return [
        {
            "run_id": job.run_id,
            "domain": job.domain,
            "status": job.status,
            "started_at": job.started_at.isoformat(),
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }
        for job in jobs
    ]
