# Causal Discovery Service — Test UI

A separate, local-only testing tool to verify that the causal-discovery
pipeline built in `Causal_Discovery_Service/` actually works end-to-end —
including **really running LPCMCI** (unlike the rest of the service, which
was deliberately built without ever executing it) — and to look at the
resulting causal graph before any of this touches the production
Warranty & Quality screen.

## What this is NOT

- **Not** a change to the existing UI at `http://10.10.90.98:5174/warranty-quality`.
  That page, its code, and its API are completely untouched.
- **Not** deployed anywhere. It only runs as a plain local process bound to
  `127.0.0.1`, started by hand when you want to use it. It is not in
  `docker-compose.yml`, not on any existing server, and not reachable from
  outside the machine it's running on.
- **Not** dependent on the old causal service. It reuses this service's own
  modules (`config.py`, `db_reader.py`, `manufacturing/panel_builder.py`,
  etc.) and nothing from `backend/app/ai/causal`.

## What it is

Two small local processes, plus a browser tab:

1. **A tiny API** (`api/main.py`, FastAPI) — new endpoints, only used by this
   test UI, that actually call `lpcmci_runner.run_lpcmci()` for real.
2. **A static frontend** (`frontend/`) — one plain HTML page, no build step,
   that talks to that API and draws the resulting graph.

## Which sections are here, and why

This mirrors the existing Warranty & Quality screen, but keeps **only** the
sections that genuinely depend on a causal-discovery run:

| Kept | Why |
|---|---|
| Model / Run Freshness | Direct causal-run metadata (run id, `tau_min`/`tau_max`/`pc_alpha`, window, edge count) |
| Panel & Preprocessing Summary | What the engine actually analyzed (entities, panel shape, dropped columns, missing data %) |
| Causal Discovery Graph (canvas) | The literal graph LPCMCI produced |
| Discovered Causal Candidates (table) | The literal edges LPCMCI produced (source, target, lag, sign, strength, p-value) |

Everything else on the real screen — Priority Warnings, Selected Warning
Evidence, Exact Production Lineage, Supplier/Market Hotspots, Empirical
Calibration Baseline, Data/Warning Freshness — reads from
`service_events`/`warranty_claims` or the old replay/watermark system, not
from a causal-discovery run, so none of it is reproduced here.

## Important: LPCMCI is slow — read this before running

This was measured directly against the live database while building this
tool, and it's the reason the default entity count is so small:

| Entities | Variables | `tau_max` | Time to complete |
|---|---|---|---|
| 1 machine | 14 | 2 | ~4 seconds |
| 1 machine | 14 | 3 | ~8 seconds |
| 2 machines | 28 | 2 | still running after several minutes |

LPCMCI's runtime grows very fast with the number of variables — doubling
the entity count did not double the time, it made the run take far longer
than could be waited out during testing. **Start with 1 entity** (the
default), confirm it works, and only increase gradually from there if you
have time to wait.

Because of this, every run happens as a background task on the API side —
the browser polls for status every 2 seconds rather than holding one HTTP
request open, so nothing times out while LPCMCI is thinking.

## How to run it (on any machine with this repo + database access)

```bash
cd Causal_Discovery_Service/test_ui
./run_test_ui.sh
```

This starts:
- the API on `http://127.0.0.1:8790`
- the frontend on `http://127.0.0.1:8791`

Open `http://127.0.0.1:8791` in a browser. Both are bound to `127.0.0.1`
only — nothing here is reachable from another machine, and nothing here
uses a port any existing service uses.

If those two ports happen to be busy on a given machine, override them:

```bash
API_PORT=9001 UI_PORT=9002 ./run_test_ui.sh
```

The script automatically writes the correct API port into
`frontend/config.js` so the page always finds the right API — no manual
edits needed.

### Stopping it

```bash
./stop_test_ui.sh
```

### First-time setup

This reuses `Causal_Discovery_Service/.venv` — the same dedicated virtual
environment the rest of the service uses — with FastAPI and uvicorn added
on top (`test_ui/requirements.txt`). If that environment doesn't exist yet
on a given machine:

```bash
cd Causal_Discovery_Service
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r test_ui/requirements.txt
```

### Database access

The API reads (read-only) from whatever database `MAHINDRA_DATABASE_URL` /
`DATABASE_URL` resolve to, exactly like the rest of `Causal_Discovery_Service`
(see `config.py`). If you're running this on a different machine than the
database, set that environment variable before running `run_test_ui.sh`.

## Using it

1. Pick a domain (Manufacturing or Telematics).
2. Leave "Entities" at 1 for your first run.
3. Optionally override `tau_max` / `pc_alpha` — leave blank to use this
   service's documented defaults (see `../IMPLEMENTATION_PLAN.md` section 9).
4. Click **Run LPCMCI**. The status pill will show `RUNNING` with an
   elapsed-time counter while it works.
5. Once it says `COMPLETED`, the graph, candidate-edges table, and
   panel/preprocessing tiles fill in below.

Example: running Manufacturing with 1 entity typically finds a real,
non-empty set of self-referencing lagged edges (e.g.
`MACHINE_SYN_014||machine_load → MACHINE_SYN_014||machine_temperature_c`,
lag 1-2 steps) — a small but genuine causal graph from that one machine's
own sensor dynamics, confirming the whole pipeline (DB read → preprocessing
→ Tigramite → LPCMCI → graph conversion) works correctly end-to-end.

## Files in this folder

```
test_ui/
├── README.md              <- this file
├── requirements.txt        <- fastapi, uvicorn (installed into ../.venv)
├── run_test_ui.sh          <- starts both processes, 127.0.0.1 only
├── stop_test_ui.sh         <- stops them
├── api/
│   └── main.py              <- new, separate FastAPI app + endpoints
└── frontend/
    ├── index.html
    ├── app.js
    ├── style.css
    └── config.js             <- API port, auto-written by run_test_ui.sh
```
