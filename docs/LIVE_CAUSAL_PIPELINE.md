# Live Warranty & Quality causal pipeline

How the Warranty & Quality Early-Warning system gets from immutable synthetic
source records to a refreshing production causal graph, and how to operate it.

```
data/synthetic/**.csv                     reproducibility artifacts
        │  (loaded once)
        ▼
replay.manufacturing_timeseries           immutable per-domain source
replay.vehicle_telematics_timeseries
replay.service_events
replay.warranty_claims
        │  every 60 real seconds, per-domain watermark
        ▼
public.manufacturing_timeseries           runtime operational tables
public.vehicle_telematics_timeseries      (physical INSERT, append-only)
public.service_events
public.warranty_claims
        │  rolling SQL windows
        ▼
Manufacturing PCMCI          Telematics PCMCI      independent, single-flight
        │                            │
        ▼                            ▼
ai_state.manufacturing_causal_runs/_edges
ai_state.telematics_causal_runs/_edges
        │
        ▼
warranty_quality_evaluation (automatic)   lifecycle + warning.causal_paths
        │
        ▼
FastAPI  /api/v1/warranty-quality/{early-warnings,causal-status}
        │
        ▼
Warranty & Quality screen · graph · Node Inspector · Edge Inspector
```

## Why every domain has its own watermark

Manufacturing minute observations and vehicle telematics do **not** share a
source window. Production observations cover the production week; telemetry
starts after each vehicle is delivered and runs for seven days. In this dataset
the two windows do not overlap at all:

| Source | Window (UTC) | Rows | Entities |
| --- | --- | --- | --- |
| `replay.manufacturing_timeseries` | 2026-07-24 18:30 → 2026-07-31 18:29 | 1,209,600 | 120 machines |
| `replay.vehicle_telematics_timeseries` | 2026-08-08 18:56 → 2026-09-07 05:19 | 241,920 | 24 vehicles |
| `replay.service_events` | 2026-03-03 → 2026-09-14 | 1,116 | — |
| `replay.warranty_claims` | 2026-03-22 → 2026-09-09 | 55 | — |

A single global watermark therefore cannot make both time-series streams
physically ingest at the same simulated minute: whichever domain the clock is
not inside is always incomplete, and the whole tick rolls back. Each domain now
carries its own `replay_start` and `replay_cursor` in
`ai_state.causal_ingestion_state` and advances independently.

`replay_cursor` is how far a domain has been replayed and always advances.
`last_ingested_timestamp` is the newest row physically inserted and only
advances when the source actually had rows due — a sparse field-evidence
stream can pass a minute without pretending it produced evidence.

The shared business clock (`ai_state.causal_replay_state.simulation_as_of`)
follows the **field** domains only (telematics, service, warranty).
Manufacturing replays an earlier production window and must never drag the
business clock back into the production past.

When a cursor reaches its source maximum the domain reports
`SOURCE_EXHAUSTED`. That is a fact about the source, not an ingestion failure:
no rows are due, so no rows are inserted, and the panel says so.

## The cutover

`app/scripts/replay_cutover.py` has three explicit, separate operations.

```bash
# 1. Read-only comparison of replay.* against public.*
python -m app.scripts.replay_cutover --validate-only

# 2. Additively populate replay.* from public.* (ON CONFLICT DO NOTHING)
python -m app.scripts.replay_cutover --copy-current

# 3. The cutover itself — requires a backup reference
python -m app.scripts.replay_cutover \
  --initialize-runtime \
  --backup-reference database/backups/<stamp>/runtime_timeseries_and_ai_state.dump \
  --field-start "2026-08-29T21:56:00+00:00"
```

Validation checks, per domain: replay source present, no natural-key
duplicates, no orphan lineage columns, and every runtime row covered by the
replay source. `--initialize-runtime` refuses to run unless validation passes.

The cutover deletes runtime rows strictly **after** each domain's replay start,
backfills anything at or before it, and seeds the checkpoints. Deletes run in
reverse dependency order (`warranty_claims` before `service_events`) and
backfills in forward order, because `warranty_claims.service_event_id` is a
foreign key. It refuses to re-run over an already-advanced pipeline unless
`--force-reinitialize` is given, so it is safe to invoke repeatedly.

Take the backup first:

```bash
docker exec mahindra-postgres pg_dump -U mahindra -d mahindra_ai -Fc \
  -t public.manufacturing_timeseries -t public.vehicle_telematics_timeseries \
  -t public.service_events -t public.warranty_claims -n ai_state \
  > database/backups/<stamp>/runtime_timeseries_and_ai_state.dump
```

### Replay anchors

Anchors are derived so both PCMCI engines have their full validated rolling
history on the very first tick rather than warming up blind:

* manufacturing — `source_from + 72 h`
* telematics / service / warranty — the current business clock, or
  `telematics source_from + 168 h` on a fresh install

## Rolling windows

Ingestion is **append-only**. The causal window is never made by deleting the
oldest minute; PCMCI selects a rolling window in SQL and simply ignores older
rows, which remain stored.

| Domain | Raw history | Analytical resample | Minimum raw rows |
| --- | --- | --- | --- |
| Manufacturing | 72 h | 15 min | 1,440 (96 panel observations) |
| Telematics | 168 h post-delivery | 5 min | 1,440 (288 panel observations) |

If storage retention becomes necessary, prefer PostgreSQL partitions plus a
periodic partition drop **outside** the ingestion critical path. Do not add a
delete to the tick.

### Manufacturing window anchoring

The manufacturing window is anchored on the **implicated production**, not on
the replay clock. A field failure is caused by the production run that built
that vehicle, so a window that slides past that production would silently swap
the evidence for an unrelated later shift.

```
lineage = exact (machine, batch, supplier lot) triples carrying visible
          service/warranty evidence
window  = [lineage_from, lineage_from + 72 h], never ending before lineage_to,
          and never beyond what has been physically ingested
cohort  = the production lines that built those vehicles, all of their machines
```

The signature still moves while the pipeline runs: it changes when new field
evidence implicates a different batch or lot, and while the implicated
production window is still being ingested. Once that window is complete and the
field evidence is stable, the plan legitimately reports `REUSED` — a manufacturing
causal graph that changed every minute would not be tracking production truth.

### Telematics cohort

Cohort membership is an **eligibility** decision, never a recency decision. The
previous planner required telemetry within the last ten minutes, which silently
excluded every warning vehicle that had finished its post-delivery window — the
cause of `Telematics Paths = 0`.

A vehicle is eligible when it was actually delivered, its telemetry is at or
after delivery, and it has enough raw and analytical rows inside the current
168 h window. Eligible vehicles carrying visible field evidence are admitted
first; eligible background vehicles fill the remaining cohort budget
(`TELEMATICS_CAUSAL_MAX_VEHICLES`, default 12).

Every field-relevant vehicle that cannot join gets a factual reason persisted
in the scheduler diagnostics and surfaced on the warning:

`not_delivered` · `insufficient_raw_history` · `insufficient_analytical_rows` ·
`outside_source_window` · `no_supported_metric_family` ·
`no_supported_metric_intersection`

The `supporting_vehicle_ids ∩ warning_vehicles` validation in the warning layer
is unchanged. Warning vehicle ids are derived from runtime evidence tables on
every pass and are never hard-coded.

## Scheduling

The source-change check runs every poll. A causal run starts only when the
domain's deterministic source signature actually changes — never because a
timer fired.

At most one run per domain may be active. A PostgreSQL advisory lock
(`mahindra-ai-causal:<domain>`) enforces single flight. A tick arriving while a
run is active records a coalesced `pending_target_watermark` instead of
queueing another job; when the active run finishes, exactly one follow-up
executes against the newest data. There is no unbounded backlog.

The two domains never block each other: different advisory locks, different
sessions, and separate containers (`causal-scheduler`,
`causal-scheduler-telematics`).

## Warning evaluation

`warning-evaluator` re-evaluates every 60 s, and each causal scheduler also
triggers an evaluation when it produces a new run. Nothing waits for a browser
to open `GET /early-warnings`.

An evaluation is identified by what it was derived from — manufacturing
signature, telematics signature and field-evidence version — deliberately **not**
by the clock. Keying on time would mint a fresh evaluation every minute even
when nothing moved. Warnings are keyed by issue category, so an unchanged
evaluation updates the existing row (`UNCHANGED`) instead of creating a
duplicate. Lifecycle transitions are recorded in
`ai_state.warranty_quality_warning_events`.

Only the newest `EVALUATION_RETENTION` (200) evaluation snapshots are kept. The
per-warning lifecycle rows and transition events are the durable record and are
never pruned.

## Failure safety

* Ingestion failure rolls the domain's minute back and does not advance its
  checkpoint; other domains keep their committed minutes.
* PCMCI failure leaves the previous completed run as the served graph — the
  scheduler's `last_run_id` is only updated on success.
* Warning-evaluation failure leaves the previous valid warnings and graph in
  place.
* The last valid graph is never replaced with an empty graph because a refresh
  failed.

## Operating

```bash
docker compose up -d                 # backend, both schedulers, ingestor, evaluator, frontend
docker compose logs -f replay-ingestor
curl -s localhost:8002/api/v1/warranty-quality/causal-status | jq
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `SIMULATION_MINUTES_PER_REAL_MINUTE` | `10` | Replay speed. At 60 the production source is fully replayed in about an hour; 10 keeps both streams live for a working day. |
| `SIMULATION_TICK_INTERVAL_SECONDS` | `60` | Real seconds between physical ingestion ticks. |
| `CAUSAL_SCHEDULER_POLL_SECONDS` | `60` | Source-signature check cadence per domain. |
| `TELEMATICS_CAUSAL_MAX_VEHICLES` | `12` | Background cohort ceiling; field-relevant eligible vehicles are always admitted. |

Backend and database timestamps are UTC throughout. The frontend renders
`Asia/Kolkata` through `Intl.DateTimeFormat` in `src/lib/formatters.ts`; no code
adds a manual offset.
