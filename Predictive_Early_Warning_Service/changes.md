# Changes — Predictive Early-Warning Service

Companion to `IMPLEMENTATION_PLAN.md` (written first). This records what
was actually built and verified, in plain English.

## What was built, in one sentence

A working predictive model (one classifier per warning type) that scores
live vehicle telemetry, creates real warning records when risk crosses a
threshold, and — when a warning is opened — runs a real LPCMCI
investigation on that vehicle's history and shows a target-centered
root-cause / upstream / downstream graph on a **separate screen**.

## New folder

```
Mahindra AI Nexus/Predictive_Early_Warning_Service/
```

Sibling to `Live_Data_Formation/` and `Causal_Discovery_Service/`. Reuses
`Causal_Discovery_Service`'s already-built database access, preprocessing,
LPCMCI wiring, and graph conversion directly (a deliberate choice — see
`IMPLEMENTATION_PLAN.md`), rather than duplicating that engine a second
time.

## Files created

| File | What it does |
|---|---|
| `IMPLEMENTATION_PLAN.md` | The plan, written first, with real thresholds/windows measured from the live database rather than the README's illustrative numbers. |
| `pews_config.py` | Warning-type definitions (target metric, threshold, direction), window sizes, risk threshold — all overridable via `PEWS_*` environment variables. Named `pews_config.py`, not `config.py`, to avoid colliding with `Causal_Discovery_Service/config.py` once that folder is added to `sys.path` (a real bug caught during testing — see below). |
| `features.py` | The ONE feature-computation function (mean/min/max/trend per metric), used identically at training time and live-scoring time to avoid train/serve skew. |
| `training_data.py` | Scans historical telemetry and builds labeled (features → did-it-cross-the-threshold-later) rows, entirely from data already in the database — no manual labeling. |
| `train_model.py` | Trains one Random Forest per warning type with a **time-based** train/test split (not random — nearby checkpoints for the same vehicle are correlated, so a random split would leak information). |
| `models/` | Saved trained models (`.joblib`). |
| `scheduler.py` | The live scoring loop — scores active vehicles every 15 minutes (configurable) and creates/updates warnings. |
| `warnings_store.py` | Reads/writes warning records as local JSON files (`warnings/`) — no new database schema yet, same incremental approach used for `Causal_Discovery_Service`'s own output. |
| `investigate.py` | The "explain this warning" step: builds a single-vehicle LPCMCI panel ending exactly at the warning's timestamp, force-includes the target metric, runs LPCMCI, and classifies the graph around the target. |
| `api/main.py` | Separate FastAPI app — `GET /api/warnings`, `GET /api/warnings/{id}`, `POST /api/warnings/{id}/investigate`, `GET /api/investigations/{job_id}`. Investigation runs as a background task (LPCMCI is slow) with the same PENDING→RUNNING→COMPLETED polling pattern already proven in `Causal_Discovery_Service/test_ui`. |
| `ui/warnings-list.html` + `.js` | **Screen 1** — auto-refreshing list of open warnings (polls every 10s). |
| `ui/investigate.html` + `.js` | **Screen 2** — a genuinely separate page/URL (`investigate.html?warning_id=...`), not a modal or inline panel. Clicking "Investigate" on Screen 1 navigates here. |
| `run_service.sh` / `stop_service.sh` | Start/stop both processes, bound to `127.0.0.1` only (ports 8792/8793 by default), same pattern as `Causal_Discovery_Service/test_ui`. |

## Additive changes to `Causal_Discovery_Service/` (nothing existing broken)

| Change | Why |
|---|---|
| **New file** `graph_walker.py` | Classifies every node as `ROOT_CANDIDATE` / `UPSTREAM` / `TARGET` / `DOWNSTREAM` / `UNCERTAIN_LINK` / `UNRELATED` relative to one target node — the piece the README describes (§19-24) that didn't exist yet. Deliberately conservative: only edges with a fully-resolved mark (`-->` or `<--`) drive the hop-walk; anything with a `<->`/`o-o`/etc. mark is reported as "uncertain direction" rather than confidently placed, per the README's own caution (§27). |
| `preprocessing.py`: added optional `protected_columns` parameter to `drop_near_constant_columns()` and `preprocess_panel()` | So a warning's target metric can never be silently dropped by the near-constant filter. **Defaults to `()`** — verified the existing CLI scripts and `test_ui` are unaffected (signature check passed, parameter is purely additive). |

No other file in `Causal_Discovery_Service/`, `Live_Data_Formation/`,
`backend/`, or `frontend/` was touched.

## Real numbers found while building this (not assumed)

Checked directly against the live database before choosing thresholds:

- Live telemetry spans ~4 days (2026-08-28 → 2026-09-01) across 1,346
  vehicles, median 333 rows/vehicle.
- `battery_temperature_c`: p50=30.4°C, p99=33.6°C, max=35.2°C — nowhere
  near the README's illustrative "55°C," so that threshold was replaced
  with a data-derived **33.0°C** (~p97).
- **184 of 1,346 vehicles** show a real rising battery-temperature trend
  (>2°C from the first half to the second half of their observed
  history) — confirming the synthetic generator's degradation scenario is
  genuinely present and learnable, not random noise.

## Training results (real, measured)

```
BATTERY_OVERHEATING : precision 0.989, recall 0.900, F1 0.942, ROC-AUC 0.983
LOW_BATTERY_VOLTAGE  : precision 0.976, recall 0.980, F1 0.978, ROC-AUC 0.998
BATTERY_DEGRADATION  : precision 0.992, recall 1.000, F1 0.996, ROC-AUC 1.000
```

**Honest caveat**: these metrics are unusually clean. That's a property of
this synthetic dataset's smooth, formula-driven generation (values evolve
gradually via autoregressive-style formulas), not necessarily representative
of how well a model would do on real, noisier sensor data. Documented here
rather than presented as if it were a universally strong result.

## End-to-end verification performed

1. **Training**: ran `train_model.py` for real — all three models trained
   successfully (see above), saved to `models/`.
2. **Scoring**: ran one real scoring pass (`scheduler.score_once`) against
   live data — scored 69 (vehicle, warning_type) pairs, created **45 real
   warning records** on disk, including one for `VEHUNIT_SYN_0001275` (the
   same vehicle ID used in the README's own worked example).
3. **Investigation engine** (`investigate.py`, called directly): ran a real
   LPCMCI investigation for `VEHUNIT_SYN_0001275` / `battery_temperature_c`
   — completed in 5.6s, panel shape (97, 17), 37 edges found,
   `battery_temperature_c` correctly classified as `TARGET`.
4. **Full API path**: started `run_service.sh` for real, confirmed both
   `8792` (API) and `8793` (UI) bind to `127.0.0.1` only, confirmed
   `GET /api/warnings` returns the 45 real warnings, confirmed both UI
   pages return HTTP 200, then triggered a real investigation through
   `POST /api/warnings/{id}/investigate` and polled it to completion
   through the actual HTTP API (not just the Python function directly) —
   confirming the FastAPI background-task wiring works end to end.

## A real bug found and fixed during implementation

**Module name collision.** The service's own `config.py` was silently
shadowed the moment `Causal_Discovery_Service/` was added to `sys.path` —
Python resolved `from config import ...` to
*`Causal_Discovery_Service/config.py`* instead of this service's own file,
because that path was inserted at the front of `sys.path`. Caught
immediately via an `ImportError` naming the wrong values. Fixed by
renaming this service's own config module to `pews_config.py` — a unique
name that can't collide with anything in `Causal_Discovery_Service` (which
has no `pews_config.py`). Worth remembering for any future module added to
either service: check for a name collision before assuming `sys.path`
insertion is safe.

## Addendum: reactive minute-level scoring, and a real "new warnings look new" bug fix

A follow-up request pointed out that the warnings list should behave like
a genuine live feed — new warnings appearing as new risk is detected from
fresh minute-level data — not the entire list re-appearing "just now"
every time the scheduler ran. Investigating this surfaced a real bug, not
just a missing feature.

**The bug**: `create_or_update_warning()` reset `warning_timestamp` to
`now()` on every single re-score of an already-open warning. Since the old
scheduler re-scored the same ~50 vehicles every 15 minutes regardless of
whether their data had actually changed, every open warning's timestamp
kept jumping to "just now" — so the list always looked freshly created,
with no way to tell which warnings were genuinely new versus long-standing.

**The fix, three parts:**

1. **`warnings_store.py`**: added a `last_seen_at` field. `warning_timestamp`
   is now set once, at first detection, and never touched again while the
   warning stays open; `last_seen_at` updates on every re-confirmation
   instead. The warnings list already sorted by `warning_timestamp`
   descending, so this alone makes genuinely new detections surface at the
   top and stay there — old ones don't jump the queue anymore.
2. **`scheduler.py`**: rewritten to be reactive. Instead of re-scoring a
   static top-N-by-row-count vehicle list every 15 minutes, each tick now
   asks "which vehicles received a new row since the last tick?" and only
   scores those - still using each vehicle's full trailing 12h window to
   compute features, just triggered by fresh data rather than a fixed
   re-scan. Tick interval dropped from 15 minutes to **60 seconds**
   (`pews_config.SCHEDULER_TICK_SECONDS`), matching `Live_Data_Formation`'s
   own per-minute cadence, so a new risk crossing is detected within about
   a minute of the data that revealed it.
3. **`ui/warnings-list.js`**: now shows "First detected: Xm ago" and "Last
   confirmed: Xm ago" separately, and flags anything detected in the last
   2 minutes with a `NEW` badge.

**Verified against live data** with two real scoring ticks, 70 seconds
apart (the second tick waiting for a genuine new minute of
`Live_Data_Formation` data to land): tick 1 found 3 (vehicle, warning_type)
pairs already open from earlier testing — correctly reported as 0 new.
Tick 2, after real new data arrived, found 54 pairs from the freshly
updated vehicles: 40 genuinely **new** detections, and the original 3
correctly recognized as **still-active** rather than double-counted.
43 total warnings on disk after both ticks (3 + 40 = 43, arithmetic
checks out). The 45 warning records left over from earlier testing (all
created under the old, buggy timestamp behavior) were deleted so the
corrected scheduler could rebuild an accurate set from scratch.

The live scheduler (`scheduler.py`) is now running continuously in the
background (via new `run_scheduler.sh` / `stop_scheduler.sh`, mirroring
`run_service.sh` / `stop_service.sh`'s pattern), so the warnings list keeps
growing with genuinely new detections as `Live_Data_Formation` keeps
inserting new minutes of telemetry.

### A second real bug found while verifying this: silent logging

After starting the scheduler in the background for the first time, its log
file stayed completely empty for 9+ minutes even though the process was
confirmed alive and running ticks correctly. Root cause: Python
block-buffers `stdout` by default when it isn't connected to a terminal
(i.e. whenever redirected to a log file), so `print()` output can sit
unwritten for a long time. Fixed permanently in `scheduler.py` with
`sys.stdout.reconfigure(line_buffering=True)` near the top of the file -
this covers every `print()` call in the file automatically, not just the
ones flushed by hand, and works regardless of how the script is launched
(so a future `python3 scheduler.py` without any special flag still logs
promptly). Verified: after this fix, the very first tick's log line
appeared within seconds of starting the process.

## Addendum 2: genuine forward-looking prediction, and a second dedup bug in the graph

Even after the reactive-scoring fix above, a follow-up observation was
that essentially no *new* warnings ever appeared over an extended period
of watching. Investigating this surfaced two more real, unrelated issues -
one about what the model was actually learning, one about the scoring
pipeline's throughput.

### Issue 1: the model was mostly detecting current state, not forecasting

Checked directly: the target metric's own current-level feature correlated
0.72-0.74 with its own future-crossing label, versus only 0.08-0.29 for its
trend. In other words, "is the temperature already near the threshold"
was doing almost all the work - the model had little reason to learn from
genuine precursor signals (ambient temperature, current draw, speed,
etc.), and a fleet where risk state barely changes minute to minute has
nothing new to detect.

**Fix, two parts:**

1. **`features.py`**: `compute_features()` and `feature_names()` now accept
   `exclude_metrics` - every warning type excludes its OWN target metric
   from its own feature set, forcing the model to infer risk from other
   signals only.
2. **`pews_config.py`**: added `LABEL_GAP_HOURS` (default 3). The label
   window no longer starts at "now" - it starts 3 hours out and runs for
   `LABEL_WINDOW_HOURS` (12h) from there, so a positive label genuinely
   means "hasn't happened yet, but predicted to happen 3-15 hours from
   now," not "may already be happening."

Since each warning type now has a different feature schema (each excludes
a different column), `training_data.py`, `train_model.py`, and
`scheduler.py` were all updated to build a per-warning-type feature vector
rather than one shared vector reused across all three models -
`scheduler.py` now reads the exact feature-column list each model was
trained on directly from its saved `.joblib` bundle, so training and live
scoring can never drift apart.

**Retrained, real results**: `BATTERY_OVERHEATING` and `LOW_BATTERY_VOLTAGE`
held up reasonably (precision still 0.97-0.99, though recall dropped a
little, as expected for a genuinely harder problem).
`BATTERY_DEGRADATION` dropped sharply (F1 0.99 → 0.49, ROC-AUC 1.00 → 0.82) -
an honest result: that metric's future behavior turns out to have little
externally-visible precursor signal in this dataset once the shortcut is
removed, rather than actually being trivially predictable.

### Issue 2: a scoring-throughput bug, unrelated to the above

While verifying the retrained models against live data, found that
`MIN_RAW_ROWS_TO_SCORE` (60) was set *above* the real per-vehicle density
in a 12-hour window. `Live_Data_Formation` samples ~5.6% of the fleet per
minute on average, which yields roughly 40 rows per vehicle in 12 hours -
so a threshold of 60 silently failed the vast majority of vehicles by
sampling variance alone, not genuine data sparsity. Measured directly: out
of 100 actively-sampled vehicles in one tick, only 1 passed the old
threshold. Lowered to 20 (comfortably below the real average). After the
fix, all 100 vehicles were scored, with a healthy, realistic probability
spread (medians of 0.08-0.47 across the three warning types, 8-35%
crossing the alert threshold) instead of the near-universal 90%+ trigger
rate seen before.

### Issue 3: the investigation graph was still showing duplicate edges

`Causal_Discovery_Service/test_ui` already had logic to merge the mirrored
`A->B` / `B->A` edge pairs LPCMCI reports for the same relationship at
lag 0 (see that service's own `changes.md`) - but this fix was never
carried over to `ui/investigate.js` in this service. Fixed the same way:
edges are grouped by `(unordered pair, lag)` and only the stronger
direction is drawn.

### "Uncertain-direction" nodes in the graph, explained

A node classified `UNCERTAIN_LINK` is connected to the target (or to
something on the target's upstream/downstream path) only through an edge
LPCMCI could not fully resolve the direction of (marked `<->`, `o-o`,
`o->`, etc., rather than a clean `-->` or `<--`). Per the README's own
guidance (§27) and `graph_walker.py`'s design, these are deliberately
**not** placed at a specific upstream/downstream hop distance, since doing
so would overstate what LPCMCI actually found - a `<->` mark may reflect a
hidden common cause behind both variables rather than one directly causing
the other.

All warnings from before this fix were cleared (they were computed with
the old, leakage-prone model) and both models were retrained; the
scheduler and API/UI were restarted to pick up all of the above.

## Threshold revision: data-derived → domain-realistic (2026-09-03)

The original `BATTERY_OVERHEATING` (`> 33.0°C`) and `LOW_BATTERY_VOLTAGE`
(`< 400.8V`) thresholds, documented above as "real numbers found while
building this," were derived from this synthetic dataset's own narrow
observed range (p97/p07 of normal operation) rather than from any
real-world failure definition. In practice this meant they sat inside
ordinary operating variation — 33°C is a completely normal battery
temperature, and 400.8V is ~98% state of charge on a standard 400V pack —
so they fired on routine fluctuation, not genuine risk, producing
persistent false warnings.

Replaced with domain-realistic values supplied directly by the user:

| Warning type | Old threshold | New threshold | Basis |
|---|---|---|---|
| `BATTERY_OVERHEATING` | `> 33.0°C` | `> 55.0°C` | Realistic critical warning temperature for a Li-ion EV pack |
| `LOW_BATTERY_VOLTAGE` | `< 400.8V` | `< 315.0V` | ~10-15% SoC (~3.28V/cell) on a standard 96-cell 400V pack |
| `BATTERY_DEGRADATION` | `> 0.0258Ω` | unchanged | Still plausible: ~70% SOH resistance rise from baseline |

Changed in exactly one place, `pews_config.py` (the single source of
truth every other module reads `WARNING_TYPES[*].threshold` from — no
other file hardcodes these numbers). `IMPLEMENTATION_PLAN.md`'s threshold
table was updated to match; this section is a historical record of the
original data-derived reasoning and is left as-is.

**Important consequence, not yet acted on**: `threshold` is only consumed
at *training* time — `training_data.py` uses it to build each row's label
("did the metric cross this threshold within the future label window?"),
and that decision is baked into the already-trained `.joblib` models under
`models/`. At live-scoring time, `scheduler.py` only calls
`model.predict_proba()` — it never re-reads `threshold` directly. So this
config change alone does **not** change what the currently-running models
predict; it only takes effect for warnings once the models are retrained
(`train_model.py`) against the new thresholds. Retraining was not part of
this change — the existing models are still scored (and any already-open
`BATTERY_OVERHEATING`/`LOW_BATTERY_VOLTAGE` warnings still reflect risk
relative to the old thresholds) until that's done separately.

## What's still manual (by design, for this MVP)

- `train_model.py` is run by hand, not on a schedule. Retraining
  automation is future work.
- `scheduler.py` must be started separately from `run_service.sh` — the
  API/UI can browse existing warnings without it running continuously.
- No fleet/model-level consensus graphs (README §29-31) — vehicle-level
  investigation only.
