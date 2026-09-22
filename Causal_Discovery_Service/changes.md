# Changes — Causal Discovery Service

This file documents, in plain English, everything that was built for this
task. It's the companion to `IMPLEMENTATION_PLAN.md` (the plan written
*before* any code was written) — this file records what actually happened
while building it, including two real issues that testing caught and fixed.

## What was built, in one sentence

A brand-new, fully self-contained LPCMCI causal-discovery service, in its
own folder with its own Python environment, that reads live manufacturing
and vehicle-telematics data straight from the database, builds a properly
cleaned and resampled analysis panel for each domain, and is wired up to
run ParCorr + LPCMCI — but does not actually run it yet, per the task's
explicit "implement, don't run" instruction.

## Why a new folder instead of extending the existing causal service

Before writing any code, the existing causal-discovery system
(`backend/app/ai/causal/` and friends) was investigated to see whether the
new live data could just plug into it. It couldn't, safely: that system
anchors its manufacturing analysis window on **exact production-batch
lineage** tied to real warranty/service records, and a direct check against
the database showed **900 rows** already inserted by the live
`Live_Data_Formation` pipeline match one of those lineage triples (because
both systems draw from the same finite pool of historical production
batches). Restarting the old scheduler as-is would likely have dragged its
72-hour analysis window away from the dense historical week it was built
for, onto a thin, randomly-sampled recent window.

Given that, the task asked for a completely new, independent service
instead of patching that coupling — which is what this is.

## New folder created

```
Mahindra AI Nexus/Causal_Discovery_Service/
```

Sibling to `backend/`, `data/`, `docs/`, and `Live_Data_Formation/`.

## Files created

| File | What it does |
|---|---|
| `IMPLEMENTATION_PLAN.md` | The plan, written first. Explains every design decision — window sizes, `tau_max`, `pc_alpha`, kept/dropped columns, preprocessing steps — with the reasoning behind each. |
| `changes.md` | This file. |
| `requirements.txt` | Pinned dependencies for this service's own virtual environment. |
| `.env.example` | Every configurable setting, documented, with its default. |
| `.venv/` | A dedicated Python virtual environment, created independently of `backend/.venv-linux`. |
| `config.py` | All settings in one place: two independent dataclasses (`MANUFACTURING_CONFIG`, `TELEMATICS_CONFIG`) holding `tau_min`/`tau_max`/`pc_alpha`/window/resample/entity-selection settings, each overridable via its own environment variable. Also the exact kept/dropped column lists for both tables, and the database-connection resolver. |
| `db_reader.py` | Read-only Postgres access. Every function is a `SELECT`; nothing in this service ever writes to the database. |
| `manufacturing/panel_builder.py` | Selects which machines to analyze ("most data in the window wins"), fetches their raw rows, hands them to preprocessing. |
| `telematics/panel_builder.py` | Same, for vehicles. |
| `preprocessing.py` | The shared cleaning pipeline: pivot to wide format → resample to fixed time bins → reindex onto one shared time axis → interpolate small gaps only → drop near-constant columns → standardize (z-score) → check stationarity (logged, not auto-corrected). |
| `tigramite_adapter.py` | Converts the cleaned panel into Tigramite's `pp.DataFrame` container. |
| `lpcmci_runner.py` | The actual ParCorr + LPCMCI call, fully implemented and verified correct against the installed Tigramite version's real function signatures — but not invoked anywhere in this phase. |
| `graph_builder.py` | Converts LPCMCI's three output matrices (`graph`, `val_matrix`, `p_matrix`) into a JSON-friendly list of nodes and edges. Verified against a small hand-built synthetic example (not real LPCMCI output, since LPCMCI was never run) to confirm the conversion logic is correct. |
| `run_writer.py` | Saves a run's settings and results as local JSON files under `runs/<domain>/<run_id>/`. No database writes. |
| `run_manufacturing_causal_discovery.py` | The command you actually run for manufacturing. |
| `run_telematics_causal_discovery.py` | The command you actually run for telematics. |
| `runs/` | Where each run's output lands. Contains two example runs from testing (see below). |

## How the pipeline actually behaves — verified against live data

Both CLI scripts were run against the real, live database (read-only) to
confirm every stage actually works — this is allowed and was done
deliberately: the instruction was "do not run PCMCI/LPCMCI", and neither
script calls that function. Everything *before* that line was exercised for
real.

### Manufacturing

```
$ .venv/bin/python3 run_manufacturing_causal_discovery.py

Manufacturing causal-discovery pipeline
  window_end        : 2026-08-29T08:39:19+00:00
  window_hours      : 24
  resample_minutes  : 5
  tau_min / tau_max : 0 / 6
  pc_alpha          : 0.05

Entities considered      : 120
Entities excluded (rows) : 0
Entities selected        : 15
Raw rows fetched         : 13939
Panel shape (T, N)       : (289, 210)
Columns dropped (near-constant): 30
Columns with stationarity warning: 169
Missing data % after interpolation: 0.23

LPCMCI was NOT run (implementation-only phase).
```

All 120 machines had enough raw rows in the trailing 24 hours to be
eligible; the 15 with the most data were selected. 210 of the 240 candidate
columns (15 machines × 16 metrics) survived the near-constant filter.
Missing data after interpolation was very low (0.23%) — the live pipeline
has been running continuously long enough that manufacturing data is dense.

### Telematics

```
$ .venv/bin/python3 run_telematics_causal_discovery.py

Telematics causal-discovery pipeline
  window_end        : 2026-08-29T08:39:21+00:00
  window_hours      : 168
  resample_minutes  : 15
  tau_min / tau_max : 0 / 4
  pc_alpha          : 0.05

Entities considered      : 1346
Entities excluded (rows) : 1291
Entities selected        : 15
Raw rows fetched         : 68376
Panel shape (T, N)       : (673, 265)
Columns dropped (near-constant): 20
Columns with stationarity warning: 72
Missing data % after interpolation: 49.09

LPCMCI was NOT run (implementation-only phase).
```

Out of the full 1,346-vehicle live roster, only 55 vehicles had at least
100 raw rows in the trailing 7 days; the 15 with the most data were
selected. Missing data is noticeably higher here (49%) than manufacturing —
this is expected and explained in the implementation plan (§5): the live
pipeline only samples ~5.6% of the vehicle pool per minute on average, so
even the best-covered vehicles have real gaps over a 7-day window this
early in the pipeline's life. This will naturally improve the longer
`Live_Data_Formation` keeps running.

Both runs wrote a `run_metadata.json` file under `runs/<domain>/<run_id>/`,
matching the example shape shown in `IMPLEMENTATION_PLAN.md` §14.

## Two real bugs found and fixed during testing

Testing wasn't just a formality here — it caught two genuine issues before
they could cause wrong results later.

### 1. The default analysis window was picking up stale historical data for telematics

**The problem:** the first version of both CLI scripts defaulted the
rolling window's end-point to `MAX(timestamp)` from the table, on the
assumption that "the newest row in the table" means "now." That's true for
manufacturing (its historical/replayed data stops at 2026-07-31, well in
the past), but **false for telematics** — the original historical
telemetry data runs all the way to 2026-09-07, which is *later* than
today's actual date. So `MAX(timestamp)` on `vehicle_telematics_timeseries`
was silently returning an old historical timestamp, and the very first test
run analyzed the tail end of old replayed data instead of the live feed
from `Live_Data_Formation` — exactly the kind of silent contamination this
whole service was built to avoid.

**The fix:** both scripts now default the window's end-point to the real
wall-clock `datetime.now(timezone.utc)` instead of querying the table for
its newest row. This is correct and safe for both domains, and it's the
only anchor that actually means "the live rolling window ending now" rather
than "whatever the newest row happens to be, historical or not." Re-running
telematics after the fix correctly considered the full 1,346-vehicle live
roster instead of 18 leftover historical vehicles.

### 2. A noisy, harmless statsmodels warning

The stationarity check's underlying `adfuller` call from `statsmodels`
printed a `FutureWarning` about a return-format change in a future release,
once per column tested (dozens of times per run). Fixed by passing
`result_object=False` explicitly, which keeps today's behavior and silences
the warning — a cosmetic fix with no effect on the actual result.

## What was explicitly not done, per the task's instructions

- **LPCMCI was never executed.** `lpcmci_runner.run_lpcmci()` is fully
  written and correct, but nothing in this codebase calls it. Both CLI
  scripts accept a `--run-lpcmci` flag that intentionally raises
  `NotImplementedError` if passed, so there's no accidental way to trigger
  a real run.
- **No UI changes.**
- **No changes anywhere outside `Causal_Discovery_Service/`.** The existing
  causal service, `Live_Data_Formation/`, the database schema, and every
  other part of the project are untouched.
- **No new database tables.** Output is local JSON files under `runs/`
  only.

## Addendum: `test_ui/` — a separate local testing UI that actually runs LPCMCI

A follow-up request asked for a way to verify the pipeline really works,
including actually executing LPCMCI (which the phase above deliberately
never did) and seeing the resulting graph in a browser — but explicitly
**not** on the real Warranty & Quality screen, and not deployed anywhere.

This was built as `Causal_Discovery_Service/test_ui/` — a new, separate
subfolder containing:

- **A new, separate FastAPI app** (`test_ui/api/main.py`) with its own
  endpoints (`POST /api/{domain}/run`, `GET /api/runs/{run_id}`,
  `GET /api/runs`) — not registered with, or reachable through, the
  existing backend's API in any way. It reuses this service's own modules
  (not the old causal service's), and for the first time actually calls
  `lpcmci_runner.run_lpcmci()`.
- **A new, separate static frontend** (`test_ui/frontend/`) — a single
  plain HTML/CSS/JS page (no build tooling, no framework), showing only
  the sections of the real Warranty & Quality screen that are genuinely
  causal-engine-dependent: Model/Run Freshness, Panel & Preprocessing
  Summary, the causal graph itself (rendered with Cytoscape.js), and a
  Discovered Causal Candidates table. Everything warranty/DB-driven from
  the real screen (Priority Warnings, exposure figures, hotspots,
  calibration baseline) was deliberately left out, since none of it comes
  from the causal engine.
- **`run_test_ui.sh` / `stop_test_ui.sh`** — start/stop both processes,
  bound to `127.0.0.1` only, on ports `8790`/`8791` by default
  (overridable). Never bound to `0.0.0.0`, never added to
  `docker-compose.yml`, never touching any existing port or process.

### A real finding from testing this: LPCMCI is very slow

Before wiring up the UI, LPCMCI was actually run against small real panels
to measure feasibility - this had never been executed anywhere in this
codebase before. Measured directly:

| Entities | Variables | `tau_max` | Result |
|---|---|---|---|
| 1 machine | 14 | 2 | completed in ~4s |
| 1 machine | 14 | 3 | completed in ~8s |
| 2 machines | 28 | 2 | still running after several minutes; stopped |

This is why the test UI defaults to **1 entity**, not the larger
production-scale defaults (`config.py`'s 15) — those would likely take
far too long to be usable for interactive testing. This is documented
prominently in `test_ui/README.md` and shown as a warning banner in the UI
itself.

### Verified working end-to-end

A real run was triggered through the actual API (1 manufacturing machine,
`tau_max=2`) and completed successfully in ~8 seconds, producing a
genuine, sensible graph - including physically-reasonable edges like
`cycle_time_seconds -> line_speed_units_per_hour` (lag 0, strength -0.81,
p≈3.8e-66), confirming the entire chain (read live DB rows -> preprocess
-> build Tigramite panel -> run LPCMCI -> convert to graph -> serve to the
browser) works correctly. `run_metadata.json` and `graph.json` were
correctly written under `runs/manufacturing/<run_id>/`.

The test UI was stopped after verification (`./stop_test_ui.sh`) - it is
not left running by default; start it again with `./run_test_ui.sh`
whenever you want to use it.

### What stayed untouched

Confirmed via `git status` in the `Mahindra AI Nexus` repository: only
`Causal_Discovery_Service/` (already untracked from the earlier phase)
shows as new. `docker-compose.yml`, `docker-compose.override.yml`,
`frontend/`, and `backend/app/api/*` show no diff from this work at all.

## Honest gap to flag

`graph_builder.py`'s node metadata currently derives only `entity_id` and
`metric` by splitting each variable name on `||` (e.g.
`"MACHINE_SYN_014||machine_temperature_c"` → entity `MACHINE_SYN_014`,
metric `machine_temperature_c`). It does not yet attach the richer context
columns (plant name, line type, vehicle model, etc.) that `config.py`
already sets aside as metadata. That richer labeling only matters once
LPCMCI actually produces a graph to label — which is out of scope for this
phase — but it's worth doing when this service moves to its next phase.
