# Causal Discovery Service — Implementation Plan

> **Note:** a follow-up local testing UI that actually executes LPCMCI was
> added afterward at `test_ui/` — see `test_ui/README.md` and the
> "Addendum" section of `changes.md` for what that adds. Everything below
> describes the original phase, in which LPCMCI was deliberately not run.

## 0. What this document is

This is the plan written **before** writing any code for a brand-new, fully
independent LPCMCI causal-discovery service. It explains every design
decision — what data is used, what gets kept vs. dropped, exactly how
`tau_max` and the significance level (`p` / `pc_alpha`) are chosen and
configured, and the full step-by-step pipeline — in plain English, before a
single line of the pipeline itself is written.

This plan lives at `Causal_Discovery_Service/IMPLEMENTATION_PLAN.md`, inside
the same folder as the service it describes.

---

## 1. Why this service exists, and why it's separate

An LPCMCI causal-discovery service **already exists** in this project, at
`backend/app/ai/causal/` (plus `backend/app/services/*causal*.py` and
`backend/app/scheduler/causal_scheduler.py`). It is a mature, deeply
integrated system: it reads from `replay.*` source tables advanced by a
simulated clock, writes to its own `ai_state.*` schema, drives a FastAPI
endpoint, and feeds an existing frontend screen (Warranty & Quality).

That system was investigated for this task and found to have a real,
already-provable conflict with the new live data: it anchors its
manufacturing analysis window on **implicated production lineage**
(exact machine + batch + supplier-lot triples that have a real warranty or
service issue on file). 900 rows already inserted by the live
`Live_Data_Formation` pipeline (see `Live_Data_Formation/README.md`) match
one of those triples, because both systems draw from the same finite pool of
1,484 historical production batches. Restarting the old scheduler today
would very likely drag its 72-hour analysis window away from the dense
historical production week it was built for, onto a thin, sparsely-sampled
recent window — degrading or breaking the graph it currently serves.

Rather than try to patch that coupling, this task builds a **new,
independent** causal-discovery service from scratch:

- New folder: `Causal_Discovery_Service/` (sibling to `backend/`, `data/`,
  `Live_Data_Formation/`, inside `Mahindra AI Nexus/`).
- **Zero imports** from `backend/app/ai/causal`, `backend/app/services/*causal*`,
  `backend/app/scheduler/causal_scheduler.py`, or any other file under
  `backend/app/`.
- **Zero imports** from `Live_Data_Formation/` either — this service only
  reads the two database tables that pipeline writes into
  (`manufacturing_timeseries`, `vehicle_telematics_timeseries`); it does not
  import any of that pipeline's Python modules.
- **Its own dedicated Python virtual environment** (`.venv/` inside this
  folder), separate from `backend/.venv-linux`, so there is no shared
  dependency manifest either — a version upgrade or dependency change in the
  old service's environment can never affect this one, and vice versa.
- **No new tables or schema changes in the existing database.** This phase
  writes its output as local JSON/CSV files under `Causal_Discovery_Service/runs/`,
  not into `ai_state.*` or any other existing schema. (A future phase could
  add dedicated tables under a brand-new schema of its own, but that is out
  of scope here — see §12.)
- **Read-only** against the database. This service never runs `INSERT`,
  `UPDATE`, or `DELETE` against any table. It only ever `SELECT`s from
  `manufacturing_timeseries` and `vehicle_telematics_timeseries`.

The only things this new service intentionally shares with the rest of the
project are: the same Postgres database (read-only), the same general
approach described in `docs/README_LPCMCI_Causal_Discovery.md` (ingest →
preprocess → select variables → ParCorr → LPCMCI → graph), and standard
third-party libraries (`tigramite`, `pandas`, `numpy`, `asyncpg`,
`statsmodels`) — using a shared open-source library is not a code dependency
on the old service.

---

## 2. Scope of this phase

**In scope:**

- A complete, working, independently runnable pipeline for **both** domains:
  manufacturing and vehicle telematics.
- Reads live data straight from `manufacturing_timeseries` and
  `vehicle_telematics_timeseries` in Postgres (the tables
  `Live_Data_Formation` is inserting into every minute).
- Every pipeline stage from the README (ingestion, preprocessing, variable
  selection, Tigramite conversion, ParCorr + LPCMCI wiring, graph
  conversion, output writing) is implemented and unit-testable up to (but
  **not including**) actually invoking `LPCMCI.run_lpcmci(...)`.

**Out of scope for this phase (explicitly, per instructions):**

- Actually **running** PCMCI/LPCMCI against real data to produce a graph.
  The algorithm call is fully implemented and wired up, but this phase does
  not execute it.
- Any UI changes.
- Any change to the existing codebase (`backend/`, `data/`, `frontend/`,
  the old causal service, the database schema).
- Alert-centered backward causal tracing, root-cause ranking, or warranty
  integration — that is the old service's job. This phase only builds
  general causal-graph discovery for the two live datasets.

---

## 3. Where the code lives

```
Mahindra AI Nexus/
└── Causal_Discovery_Service/
    ├── IMPLEMENTATION_PLAN.md      ← this file
    ├── changes.md                   ← written after implementation
    ├── requirements.txt             ← pinned dependencies for this service's own venv
    ├── .env.example                 ← documents every configurable setting
    ├── .venv/                       ← this service's own, dedicated virtual environment
    ├── config.py                    ← ALL settings, including tau_max / pc_alpha per domain
    ├── db_reader.py                 ← read-only Postgres connector (SELECT only)
    ├── manufacturing/
    │   ├── __init__.py
    │   └── panel_builder.py         ← entity selection + wide panel + resampling (manufacturing)
    ├── telematics/
    │   ├── __init__.py
    │   └── panel_builder.py         ← entity selection + wide panel + resampling (telematics)
    ├── preprocessing.py             ← shared: missing values, constant-column drop, stationarity, standardize
    ├── tigramite_adapter.py         ← wide panel → Tigramite pp.DataFrame
    ├── lpcmci_runner.py             ← ParCorr + LPCMCI wrapper (implemented, NOT invoked this phase)
    ├── graph_builder.py             ← LPCMCI output matrices → JSON-friendly nodes/edges
    ├── run_writer.py                ← persists run metadata + graph as local JSON files
    ├── runs/                        ← output folder (created empty)
    ├── run_manufacturing_causal_discovery.py   ← CLI entrypoint (manufacturing)
    └── run_telematics_causal_discovery.py      ← CLI entrypoint (telematics)
```

Two domain subfolders (`manufacturing/`, `telematics/`) mirror the same
domain split used in `Live_Data_Formation/` (`Manufacturing_Timseries/`,
`Vechicle_Telematics/`), for consistency across the project, though spelled
correctly here since this is a fresh naming choice.

---

## 4. Data source

Both domains are read directly from PostgreSQL, live:

| Domain | Table | Columns | Approx. row growth |
|---|---|---|---|
| Manufacturing | `public.manufacturing_timeseries` | 34 | ~50-100 new rows/minute |
| Telematics | `public.vehicle_telematics_timeseries` | 31 | ~50-100 new rows/minute |

Connection resolution follows the same convention already used elsewhere in
this project (`MAHINDRA_DATABASE_URL` → `DATABASE_URL` → a local default),
but the connection code itself is written fresh in `db_reader.py` — it does
not import `Live_Data_Formation/db_writer.py` or any backend database module.
All queries are plain read-only `SELECT`s via `asyncpg`.

---

## 5. Why live-data density forces different designs per domain

This is the most important technical judgment call in this plan, and it is
specific to *this* service because the live generator behaves differently
from the old replay system.

`Live_Data_Formation`'s live pipeline samples a **random** 50–100 entities
out of the full pool, every minute — not all entities every minute. That
random-subset behavior means:

- **Manufacturing** — pool of up to 120 machines. Average per-minute
  inclusion probability ≈ 75 / 120 ≈ **62%**. A machine gets a raw
  observation in roughly 6 out of every 10 minutes.
- **Telematics** — pool of up to ~1,346 vehicles (the live pipeline's full
  delivered-vehicle roster). Average per-minute inclusion probability ≈
  75 / 1,346 ≈ **5.6%**. A vehicle gets a raw observation in roughly 1 out
  of every 18 minutes.

That's a more than 10x difference in density, and it directly drives the
rolling-window size chosen for each domain below — a window long enough for
manufacturing would leave telematics with almost no usable data per vehicle.

---

## 6. Rolling window, resampling, and entity selection — the concrete numbers

### Manufacturing

| Setting | Default | Reasoning |
|---|---|---|
| Rolling window | **24 hours** | At ~62% per-minute inclusion, 24h ≈ 1,440 minutes gives ~900 expected raw rows per machine — comfortably enough. |
| Resample frequency | **5 minutes** | 24h / 5min = 288 panel time-steps per run; each 5-minute bin has, on average, ~3 raw observations to average over. |
| Minimum raw rows to include a machine | **300** (out of ~900 expected) | Filters out machines that were undersampled by bad luck in a given window, so no near-empty column enters the panel. |
| Maximum machines per run | **15** | Keeps the panel to a manageable size (15 machines × up to 16 kept metrics = up to 240 columns before further filtering); the 15 machines with the most raw rows in the window are chosen. |

### Telematics

| Setting | Default | Reasoning |
|---|---|---|
| Rolling window | **7 days (168 hours)** | At ~5.6% per-minute inclusion, 168h ≈ 10,080 minutes gives ~564 expected raw rows per vehicle. |
| Resample frequency | **15 minutes** | 168h / 15min = 672 panel time-steps per run; each 15-minute bin has, on average, ~1.4 raw observations. |
| Minimum raw rows to include a vehicle | **100** (out of ~564 expected) | Same purpose as manufacturing — excludes unlucky, near-empty vehicles. |
| Maximum vehicles per run | **15** | Same reasoning as manufacturing; the 15 vehicles with the most raw rows in the window are chosen. |

Entity selection in both domains is a simple, generic **"most data available
wins"** rule — the N entities (machines or vehicles) with the highest raw
row count inside the window, subject to the minimum-row floor. This is
deliberately simpler than the old service's warranty/lineage-based
eligibility logic (see §1) — this new service has no dependency on that
machinery, and a coverage-based rule is the correct generic default for a
service whose only job right now is general causal-graph discovery, not
alert-triggered investigation.

All of the above are **configuration values**, not hardcoded constants —
see §9.

---

## 7. Columns kept vs. dropped

Every column from both tables is accounted for below. "Context/ID" columns
are never fed into LPCMCI as numeric variables — they're kept alongside the
panel purely as metadata (for labeling graph nodes with which plant/line/
vehicle-model an entity belongs to).

### 7.1 `manufacturing_timeseries` (34 columns total)

**Context / ID — kept as metadata, dropped from the numeric panel (15):**

`timestamp`, `plant_id`, `plant_name`, `production_line_id`,
`production_line_name`, `line_type`, `machine_id`, `machine_name`,
`production_batch_id`, `vehicle_model_id`, `vehicle_model_name`,
`supplier_lot_id`, `batch_status`, `data_origin`, `generator_version`

**Numeric candidates considered for the panel (19):**

`ambient_temperature_c`, `ambient_humidity_pct`, `machine_load`,
`machine_temperature_c`, `vibration_mm_s`, `power_kw`,
`line_speed_units_per_hour`, `cycle_time_seconds`,
`hours_since_maintenance`, `maintenance_overdue_hours`,
`supplier_lot_quality_score`, `torque_deviation_nm`,
`paint_booth_temperature_c`, `paint_booth_humidity_pct`,
`paint_defect_rate`, `defect_rate`, `rework_rate`, `downtime_minutes`,
`quality_score`

**Dropped by design, before preprocessing even runs (3):**

`paint_booth_temperature_c`, `paint_booth_humidity_pct`,
`paint_defect_rate` — these are `NULL` for every machine that is not on a
`PAINT` line. In a mixed cohort (which is the normal case, since entity
selection above picks whichever machines have the most data, regardless of
line type), these columns would be mostly or entirely missing and would
fail the missing-value filter anyway. They are excluded up front rather
than left to be silently dropped later, so the panel's column list is
predictable. (A future paint-line-only run could re-enable them — that is
not built in this phase.)

**Kept, entering preprocessing (16):**

`ambient_temperature_c`, `ambient_humidity_pct`, `machine_load`,
`machine_temperature_c`, `vibration_mm_s`, `power_kw`,
`line_speed_units_per_hour`, `cycle_time_seconds`,
`hours_since_maintenance`, `maintenance_overdue_hours`,
`supplier_lot_quality_score`, `torque_deviation_nm`, `defect_rate`,
`rework_rate`, `downtime_minutes`, `quality_score`

Any of these 16 can still be automatically dropped later, per-run, by the
constant-column filter (§8) if it happens to have near-zero variance for the
specific entities/window of that run — that is a mechanism, not a fixed
list.

### 7.2 `vehicle_telematics_timeseries` (31 columns total)

**Context / ID — kept as metadata, dropped from the numeric panel (11):**

`timestamp`, `vehicle_id`, `vehicle_model_id`, `vehicle_model_name`,
`variant`, `production_batch_id`, `supplier_lot_id`, `plant_id`,
`production_line_id`, `data_origin`, `generator_version`

**Numeric candidates considered for the panel (20):**

`odometer_km`, `vehicle_speed_kph`, `ambient_temperature_c`,
`battery_temperature_c`, `battery_soc_pct`, `battery_voltage_v`,
`battery_current_a`, `battery_internal_resistance_ohm`,
`transmission_temperature_c`, `transmission_slip_ms`,
`torque_converter_slip_rpm`, `steering_torque_nm`, `steering_angle_deg`,
`vehicle_vibration_mm_s`, `vertical_acceleration_g`,
`lateral_acceleration_g`, `road_roughness_index`, `impact_g_force`,
`dtc_count`, `warning_flag`

**Dropped by design (1):**

`odometer_km` — this is a cumulative counter (it only ever goes up), so it
is non-stationary by construction and not appropriate for LPCMCI in its raw
form. It is excluded rather than differenced into a synthetic
"distance-this-bin" column, to keep this phase's scope minimal;
`vehicle_speed_kph` already captures driving-intensity dynamics without
needing a derived feature.

**Kept, entering preprocessing (19), with two type conversions:**

`vehicle_speed_kph`, `ambient_temperature_c`, `battery_temperature_c`,
`battery_soc_pct`, `battery_voltage_v`, `battery_current_a`,
`battery_internal_resistance_ohm`, `transmission_temperature_c`,
`transmission_slip_ms`, `torque_converter_slip_rpm`, `steering_torque_nm`,
`steering_angle_deg`, `vehicle_vibration_mm_s`, `vertical_acceleration_g`,
`lateral_acceleration_g`, `road_roughness_index`, `impact_g_force`,
`dtc_count` (already numeric), `warning_flag` (boolean → cast to `0`/`1`
integer before entering the panel)

Same as manufacturing: any of these 19 can still be auto-dropped per-run by
the constant-column filter — for example, `dtc_count` may legitimately be
constant-zero for a cohort of vehicles with no diagnostic codes in the
window, and would be dropped for that run only.

---

## 8. Preprocessing pipeline (shared logic, `preprocessing.py`)

Applied identically to both domains, in this order:

1. **Fetch** raw rows for the selected entities inside the rolling window
   (one read-only SQL query per domain, per run).
2. **Pivot** into wide format: one row per timestamp, one column per
   `entity_id||metric` (e.g., `MACHINE_SYN_014||machine_temperature_c`).
   Context/ID columns (§7) are set aside as metadata, not pivoted into the
   numeric panel.
3. **Resample** each column to the fixed bin frequency for that domain (5
   minutes for manufacturing, 15 minutes for telematics), using the mean of
   whatever raw observations fall in each bin.
4. **Reindex** every entity onto one shared, complete, regularly-spaced time
   axis spanning the window, so every column has a value (or an explicit
   gap) at the exact same timestamps — this is required before Tigramite
   can treat the columns as one aligned panel.
5. **Fill small gaps**: any run of at most 3 consecutive missing bins is
   linearly interpolated. Larger gaps are left as genuine missing data —
   they are **not** invented by long-range interpolation or filled with a
   fixed value.
6. **Missing-data handling for what interpolation didn't cover**: rather
   than imputing a fake value, remaining gaps are passed to Tigramite using
   its own native missing-data support — the `mask` argument of
   `pp.DataFrame(...)` — so LPCMCI correctly treats those time points as
   absent rather than as a fabricated observation. This is a statistically
   more honest choice than mean-imputation.
7. **Drop near-constant columns**: any column whose standard deviation
   (over the non-missing values) falls below a small threshold
   (default `1e-6`, configurable) is dropped for that run — it carries no
   information a lagged-correlation test could use.
8. **Standardize**: every remaining numeric column is z-scored (mean 0,
   standard deviation 1) across the run's data, so no single metric's raw
   magnitude (e.g., `power_kw` in the hundreds vs. `machine_load` in [0,1])
   dominates the statistical tests purely by scale.
9. **Stationarity check (logged, not auto-corrected)**: an Augmented
   Dickey-Fuller test (via `statsmodels`) is run on every remaining column.
   Columns that fail to reject a unit root (default threshold: ADF
   p-value > 0.05) are logged as "possibly non-stationary" in the run's
   metadata, but are **not** automatically differenced or removed — that
   decision is left for human review, because differencing changes the
   causal interpretation of a variable and should not happen silently. A
   config flag (`auto_difference_nonstationary`, default `False`) exists for
   turning on auto-differencing later, but is off by default in this phase.

---

## 9. `tau_max` and the significance level (`p` / `pc_alpha`) — the actual answer

This section directly answers the specific configuration questions asked.

### What values are used

| Domain | `tau_min` | `tau_max` | What that means in real time | `pc_alpha` |
|---|---|---|---|---|
| Manufacturing | `0` | **`6`** | 6 steps × 5-minute bins = up to **30 minutes** of lag tested | **`0.05`** |
| Telematics | `0` | **`4`** | 4 steps × 15-minute bins = up to **1 hour** of lag tested | **`0.05`** |

`pc_alpha = 0.05` is the standard significance threshold (also the value
used as the "stricter" example in `docs/README_LPCMCI_Causal_Discovery.md`
§13) — permissive enough to find real relationships in a moderate-size
panel, strict enough to avoid a flood of spurious edges. `tau_max` values
are chosen from the density analysis in §5–6: enough lag depth to catch
realistic process/vehicle dynamics (e.g., a load change affecting
temperature within 15–20 minutes; a battery-temperature change affecting
resistance within an hour) without making the search space enormous.

### How `tau_max` and `pc_alpha` are configured, and why they're separate

Both are plain fields on two independent config objects in `config.py` —
one per domain — so changing manufacturing's lag depth can never
accidentally change telematics' significance threshold, or vice versa:

```python
@dataclass
class DomainCausalConfig:
    tau_min: int
    tau_max: int
    pc_alpha: float
    window_hours: int
    resample_minutes: int
    min_raw_rows: int
    max_entities: int

MANUFACTURING_CONFIG = DomainCausalConfig(
    tau_min=0, tau_max=6, pc_alpha=0.05,
    window_hours=24, resample_minutes=5,
    min_raw_rows=300, max_entities=15,
)

TELEMATICS_CONFIG = DomainCausalConfig(
    tau_min=0, tau_max=4, pc_alpha=0.05,
    window_hours=168, resample_minutes=15,
    min_raw_rows=100, max_entities=15,
)
```

Every field can be overridden independently via environment variables,
using a naming convention unique to this service (prefix `CDS_`, for
"Causal Discovery Service", so it can never collide with any environment
variable the old service or `Live_Data_Formation` reads):

```
CDS_MANUFACTURING_TAU_MAX=6
CDS_MANUFACTURING_PC_ALPHA=0.05
CDS_TELEMATICS_TAU_MAX=4
CDS_TELEMATICS_PC_ALPHA=0.05
```

Changing `CDS_MANUFACTURING_TAU_MAX` has no effect on
`CDS_TELEMATICS_TAU_MAX`, and changing either `*_TAU_MAX` has no effect on
the corresponding `*_PC_ALPHA` — they are read as two entirely separate
environment variables into two entirely separate dataclass fields. This is
what "configured and set separately" means concretely in this codebase.

All of these are documented with their defaults in `.env.example`.

---

## 10. Tigramite wiring (`tigramite_adapter.py`, `lpcmci_runner.py`)

1. **`tigramite_adapter.py`** converts the preprocessed wide panel into
   Tigramite's `pp.DataFrame`:

   ```python
   pp.DataFrame(
       data=values,              # numpy array, shape (T, N)
       mask=missing_mask,        # True where a value is missing
       var_names=column_labels,  # ["MACHINE_SYN_014||machine_temperature_c", ...]
       datatime=timestamps,      # actual bin timestamps, for traceability
   )
   ```

2. **`lpcmci_runner.py`** wraps the actual algorithm call:

   ```python
   cond_ind_test = ParCorr(significance="analytic")
   lpcmci = LPCMCI(dataframe=pp_dataframe, cond_ind_test=cond_ind_test)
   results = lpcmci.run_lpcmci(
       tau_min=domain_config.tau_min,
       tau_max=domain_config.tau_max,
       pc_alpha=domain_config.pc_alpha,
   )
   # results["graph"], results["val_matrix"], results["p_matrix"]
   ```

   These exact parameter names (`tau_min`, `tau_max`, `pc_alpha`,
   `link_assumptions`, and the constructor's `dataframe`/`cond_ind_test`)
   were confirmed against the installed `tigramite` package's real function
   signatures before writing this plan, so the wrapper is correct even
   though it is not executed in this phase.

3. This function is fully implemented, unit-testable for its input/output
   shape handling, but **is not called** by any script or test in this
   phase — per the explicit instruction not to run LPCMCI yet. The CLI
   entrypoints (§11) run every stage up to and including building the
   `pp.DataFrame`, then stop and print a summary instead of calling
   `run_lpcmci`.

---

## 11. Graph conversion, output, and the CLI entrypoints

- **`graph_builder.py`** would convert the three LPCMCI output matrices into
  a JSON-friendly structure of nodes (`entity_id`, `metric`, `domain`) and
  edges (`source`, `target`, `lag`, `edge_mark`, `strength`, `p_value`) —
  same shape as described in `docs/README_LPCMCI_Causal_Discovery.md`
  §15–16 and §24. This module is implemented but has nothing to convert
  yet, since LPCMCI is not run in this phase.
- **`run_writer.py`** persists a run's metadata (window, entity list,
  final column list, config used, row counts, timestamps, and — once
  actually run — the graph) as JSON files under
  `Causal_Discovery_Service/runs/<domain>/<run_id>/`. No database writes.
- **`run_manufacturing_causal_discovery.py`** and
  **`run_telematics_causal_discovery.py`** are the CLI entrypoints. Each:
  1. loads that domain's config;
  2. connects read-only to Postgres;
  3. selects entities and pulls the rolling window;
  4. builds and preprocesses the panel;
  5. builds the Tigramite `pp.DataFrame`;
  6. prints a summary (entities selected, final columns, panel shape,
     missing-data %, stationarity warnings) and writes that summary to
     `runs/<domain>/<run_id>/run_metadata.json`;
  7. stops — does **not** call `lpcmci_runner.run(...)`.

  A `--run-lpcmci` flag exists in the argument parser for future use, but
  in this phase it is intentionally left unimplemented (calling it raises
  `NotImplementedError("LPCMCI execution intentionally disabled in this phase")`)
  so there is no accidental way to trigger a real run from this codebase yet.

---

## 12. What is deliberately deferred (not part of this phase)

- Actually running LPCMCI and inspecting real output.
- Persisting results to a database table (would need a new, dedicated
  schema — proposed name `causal_discovery_v2` — created only when this
  phase is approved to go further).
- Any API endpoint or UI surface for this service's output.
- Alert-centered backward tracing / root-cause ranking.
- Auto-differencing non-stationary columns.
- Handling the paint-line-only cohort (currently paint-specific columns are
  simply excluded — see §7.1).

---

## 13. Dependencies (`requirements.txt`) and the dedicated virtual environment

This service gets its own `.venv/` inside `Causal_Discovery_Service/`,
created independently of `backend/.venv-linux`, with its own pinned
`requirements.txt`:

```
tigramite==<pinned version present in the environment at build time>
numpy
pandas
statsmodels
asyncpg
python-dotenv
```

No dependency on the backend's `requirements.txt` or its lock file — this
service could be deleted, copied elsewhere, or upgraded independently
without touching `backend/` at all.

---

## 14. Example: what one manufacturing run's summary will look like

Purely illustrative — this is what `run_metadata.json` will contain once
the CLI entrypoint is executed manually (still without invoking LPCMCI):

```json
{
  "domain": "manufacturing",
  "window_start": "2026-08-28T09:00:00+00:00",
  "window_end": "2026-08-29T09:00:00+00:00",
  "resample_minutes": 5,
  "tau_min": 0,
  "tau_max": 6,
  "pc_alpha": 0.05,
  "entities_selected": ["MACHINE_SYN_014", "MACHINE_SYN_057", "..."],
  "entities_considered": 63,
  "entities_excluded_min_rows": 12,
  "panel_shape": [288, 214],
  "columns_dropped_paint_only": 3,
  "columns_dropped_near_constant": ["MACHINE_SYN_057||downtime_minutes"],
  "columns_with_stationarity_warning": ["MACHINE_SYN_014||quality_score"],
  "missing_data_pct_after_interpolation": 4.1,
  "lpcmci_executed": false
}
```

---

## 15. Summary

A brand-new, self-contained causal-discovery service is added under
`Causal_Discovery_Service/`, with its own virtual environment, its own
config, and zero code-level dependency on the existing causal service or on
`Live_Data_Formation`. It reads live rows straight from
`manufacturing_timeseries` and `vehicle_telematics_timeseries`, builds a
properly preprocessed, resampled, standardized panel per domain (24h/5min
window for manufacturing, 168h/15min window for telematics — chosen from the
live pipeline's actual sampling density), and wires up ParCorr + LPCMCI with
independently configurable `tau_max` (6 steps / 30 min for manufacturing, 4
steps / 1 hour for telematics) and `pc_alpha` (0.05 for both, independently
overridable). Everything up to — but not including — the actual LPCMCI
execution is implemented and runnable in this phase.
