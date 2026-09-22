"""
API for the Predictive Early-Warning Service.

Separate FastAPI app, own endpoints, not registered with the existing
backend or with Causal_Discovery_Service's test_ui API. Local-only, meant
to be bound to 127.0.0.1 by run_service.sh - never 0.0.0.0.

Investigating a warning runs a real LPCMCI call, which is slow (same
engine, same measured runtimes as Causal_Discovery_Service/test_ui). Same
pattern used there: the run happens as a background asyncio task, and the
frontend polls a status endpoint rather than blocking one HTTP request.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PREW_ROOT = Path(__file__).resolve().parents[1]
if str(PREW_ROOT) not in sys.path:
    sys.path.insert(0, str(PREW_ROOT))
COPILOT_ROOT = PREW_ROOT / "copilot"
if str(COPILOT_ROOT) not in sys.path:
    sys.path.insert(0, str(COPILOT_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from investigate import investigate_warning
from investigation_store import load_investigation, save_investigation
from warnings_store import (
    attach_causal_run,
    get_warning,
    list_warnings,
    load_impact_ranking,
    set_status,
)

from conversation_store import clear_conversation, load_conversation
from explanation_service import build_explanation
from explanation_store import load_explanation, save_explanation
from llm_client import CopilotNotConfiguredError
from service import ask_copilot

from rag.document_index import build_document_index
from rag.llm_client import RagNotConfiguredError
from rag.service import NoMatchingDocumentsError, ask_warranty_docs
from warranty_predictions_store import load_fleet_ranking, load_vehicle_predictions

app = FastAPI(title="Predictive Early-Warning Service API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Built once at process startup - rebuilding on every request would
# re-read every CSV/re-render every document for no benefit, since the
# underlying data only changes when a refresh script is run (a process
# restart is the natural point to pick that up, same as the model
# loading below).
_DOCUMENT_INDEX = build_document_index()


@dataclass
class InvestigationJob:
    job_id: str
    warning_id: str
    status: str  # PENDING | RUNNING | COMPLETED | FAILED
    started_at: datetime
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


_JOBS: dict[str, InvestigationJob] = {}


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "predictive-early-warning"}


@app.get("/api/warnings")
async def api_list_warnings(status: str | None = None) -> list[dict[str, Any]]:
    return [w.__dict__ for w in list_warnings(status=status)]


@app.get("/api/warnings/impact-ranking")
async def api_impact_ranking(limit: int = 25) -> dict[str, Any]:
    """
    Fleet-wide ranking of currently OPEN live-telematics warnings by total
    expected Mahindra financial impact (probability x typical cost x
    warranty eligibility, summed per warning_type, HIGH-severity issues
    escalated above their raw rupee rank) - see impact_ranking.py. Reads
    what scheduler.py last computed each tick; never recomputes live in
    the request path (same principle as /api/predictions below).

    Registered BEFORE /api/warnings/{warning_id} below - FastAPI matches
    routes in registration order, and a static path segment
    ("impact-ranking") would otherwise be captured by the dynamic
    {warning_id} route ahead of it.
    """
    ranking = load_impact_ranking()
    if ranking is None:
        raise HTTPException(
            status_code=503,
            detail="No impact ranking computed yet - run scheduler.py for at least one tick first.",
        )
    return {
        "computed_at": ranking["computed_at"],
        "ranked_issues": ranking["ranked_issues"][:limit],
    }


@app.get("/api/warnings/{warning_id}")
async def api_get_warning(warning_id: str) -> dict[str, Any]:
    warning = get_warning(warning_id)
    if warning is None:
        raise HTTPException(status_code=404, detail="Unknown warning_id")
    # is_warranty_eligible/eligibility_notes (see warnings_store.py) are
    # plain fields on the Warning dataclass - already included here via
    # __dict__, no separate lookup needed.
    return warning.__dict__


async def _run_investigation(job: InvestigationJob, warning) -> None:
    job.status = "RUNNING"
    try:
        result = await investigate_warning(
            warning.vehicle_id,
            warning.target_metric,
            datetime.fromisoformat(warning.warning_timestamp),
        )
        job.result = {
            "graph": result.graph,
            "classifications": result.classifications,
            "window_start": result.window_start.isoformat(),
            "window_end": result.window_end.isoformat(),
            "raw_row_count": result.raw_row_count,
            "panel_shape": list(result.panel_shape),
            "target_metric": warning.target_metric,
            "vehicle_id": warning.vehicle_id,
        }
        job.status = "COMPLETED"
        attach_causal_run(warning.warning_id, job.job_id)
        # Durable copy: without this, the result only lives in this
        # process's memory (_JOBS) and is lost on restart - the Copilot
        # (and reopening this warning later) both need it to survive that.
        save_investigation(warning.warning_id, job.result)
    except Exception as exc:  # noqa: BLE001
        job.status = "FAILED"
        job.error = str(exc)
    finally:
        job.finished_at = datetime.now(timezone.utc)

    if job.status == "COMPLETED":
        try:
            # build_explanation makes a blocking LLM call - run off the
            # event loop, same fix already applied to the PCMCI call
            # elsewhere in this codebase.
            explanation = await asyncio.to_thread(build_explanation, warning.__dict__, job.result)
            save_explanation(warning.warning_id, explanation)
        except Exception:  # noqa: BLE001
            # The explanation report is a nice-to-have on top of a
            # completed investigation - never let it fail the
            # investigation itself.
            pass


@app.post("/api/warnings/{warning_id}/investigate")
async def api_investigate(warning_id: str) -> dict[str, Any]:
    warning = get_warning(warning_id)
    if warning is None:
        raise HTTPException(status_code=404, detail="Unknown warning_id")

    job_id = uuid.uuid4().hex
    job = InvestigationJob(
        job_id=job_id,
        warning_id=warning_id,
        status="PENDING",
        started_at=datetime.now(timezone.utc),
    )
    _JOBS[job_id] = job

    set_status(warning_id, "INVESTIGATING")

    asyncio.create_task(_run_investigation(job, warning))

    return {"job_id": job_id, "status": job.status}


@app.get("/api/investigations/{job_id}")
async def api_get_investigation(job_id: str) -> dict[str, Any]:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")

    return {
        "job_id": job.job_id,
        "warning_id": job.warning_id,
        "status": job.status,
        "started_at": job.started_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "result": job.result,
        "error": job.error,
    }


@app.get("/api/warnings/{warning_id}/investigation")
async def api_get_durable_investigation(warning_id: str) -> dict[str, Any]:
    """
    Durable lookup by warning_id (not job_id) - survives an API restart,
    unlike /api/investigations/{job_id} above which only reads the
    in-memory _JOBS dict. Used to reload a previously-run investigation's
    graph (e.g. reopening an old warning) and by the Copilot to check
    whether an investigation exists at all.
    """

    warning = get_warning(warning_id)
    if warning is None:
        raise HTTPException(status_code=404, detail="Unknown warning_id")

    result = load_investigation(warning_id)
    return {"warning_id": warning_id, "result": result}


@app.get("/api/warnings/{warning_id}/explanation")
async def api_get_explanation(warning_id: str) -> dict[str, Any]:
    """
    Durable lookup of the auto-generated AI Explanation report, built
    once right after an investigation completes (see _run_investigation
    above). Returns result: null if no investigation has completed yet
    (or the report failed to generate), same shape as the investigation
    endpoint above.
    """

    warning = get_warning(warning_id)
    if warning is None:
        raise HTTPException(status_code=404, detail="Unknown warning_id")

    result = load_explanation(warning_id)
    return {"warning_id": warning_id, "result": result}


# ---------------------------------------------------------------------
# Copilot endpoints
# ---------------------------------------------------------------------


class CopilotAskRequest(BaseModel):
    message: str


@app.get("/api/warnings/{warning_id}/copilot/history")
async def api_copilot_history(warning_id: str) -> dict[str, Any]:
    warning = get_warning(warning_id)
    if warning is None:
        raise HTTPException(status_code=404, detail="Unknown warning_id")

    conversation = load_conversation(warning_id)
    return {
        "warning_id": warning_id,
        "turns": [
            {"role": t.role, "content": t.content, "timestamp": t.timestamp}
            for t in conversation.turns
        ],
    }


@app.post("/api/warnings/{warning_id}/copilot/ask")
async def api_copilot_ask(warning_id: str, request: CopilotAskRequest) -> dict[str, Any]:
    warning = get_warning(warning_id)
    if warning is None:
        raise HTTPException(status_code=404, detail="Unknown warning_id")

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    try:
        reply = ask_copilot(warning.__dict__, request.message.strip())
    except CopilotNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Copilot request failed: {exc}") from exc

    return {"warning_id": warning_id, "reply": reply}


@app.delete("/api/warnings/{warning_id}/copilot")
async def api_copilot_clear(warning_id: str) -> dict[str, Any]:
    clear_conversation(warning_id)
    return {"warning_id": warning_id, "status": "cleared"}


# ---------------------------------------------------------------------
# Warranty predictive service endpoints (merged in from the former
# standalone Warranty_Predictive_Service - see
# docs/Implementation_plan_warranty_predictive_service.md)
# ---------------------------------------------------------------------


@app.get("/api/predictions")
async def api_predictions(limit: int = 25) -> dict[str, Any]:
    """
    Fleet-wide ranked warranty-liability issue list - reads what
    warranty_scheduler.py last computed
    (warranty_predictions/_fleet_ranking.json), never recomputes live (a
    full fleet run takes ~25s; re-aggregating from every per-vehicle
    file on each request measured ~46s - both far too slow for a
    request path).
    """
    ranking = load_fleet_ranking()
    if ranking is None:
        raise HTTPException(
            status_code=503,
            detail="No predictions have been computed yet - run warranty_scheduler.py --once first.",
        )
    return {
        "computed_at": ranking["computed_at"],
        "ranked_issues": ranking["ranked_issues"][:limit],
    }


@app.get("/api/predictions/{vehicle_id}")
async def api_vehicle_predictions(vehicle_id: str) -> dict[str, Any]:
    """Per-vehicle warranty-liability predictions - reads what
    warranty_scheduler.py last computed for this vehicle
    (warranty_predictions/<vehicle_id>.json)."""
    record = load_vehicle_predictions(vehicle_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No predictions found for vehicle_id={vehicle_id!r} - either it doesn't exist, "
            "or warranty_scheduler.py hasn't run yet.",
        )
    return record


class DocsAskRequest(BaseModel):
    question: str
    issue_category: str | None = None
    component_category: str | None = None
    vehicle_id: str | None = None
    claim_id: str | None = None


@app.post("/api/docs/ask")
async def api_docs_ask(request: DocsAskRequest) -> dict[str, Any]:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question cannot be empty")

    try:
        answer = ask_warranty_docs(
            _DOCUMENT_INDEX,
            request.question.strip(),
            issue_category=request.issue_category,
            component_category=request.component_category,
            vehicle_id=request.vehicle_id,
            claim_id=request.claim_id,
        )
    except NoMatchingDocumentsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RagNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"RAG request failed: {exc}") from exc

    return {"question": request.question, "answer": answer}
