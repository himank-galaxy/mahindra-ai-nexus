# Live Data Formation

## What this folder is

This folder makes two datasets feel "live" — as if data was streaming in
continuously, once every minute — while still being 100% synthetic (fake,
generated) data, just like the rest of this project:

1. **Manufacturing sensor data** — machine readings from the factory floor.
2. **Vehicle telematics data** — connected-vehicle sensor readings from
   delivered vehicles.

It does **not** touch or change anything inside the main `data/` folder. It
only reads from it (borrowing the existing generator logic, formulas, and
master-data setup) and writes its own new files here.

## Why it exists

The original data generators
(`data/generators/causal/manufacturing_timeseries.py` and
`data/generators/causal/vehicle_telematics_timeseries.py`) each work in one
big batch: you run them once, they create a fixed window of minute-by-minute
history in one go, and then they stop. That's fine for a one-time historical
dataset, but it doesn't behave like real sensors sending in new readings
continuously.

This folder solves that. A single pipeline runs forever as a systemd
service, and once every minute, it manufactures a fresh set of readings for
**both** datasets — one row per selected machine, and one row per selected
vehicle — just like new data arriving live from the factory floor and from
vehicles on the road. Every minute's readings are saved as a Parquet file
**and** inserted straight into the same PostgreSQL tables the historical
data already lives in, so the database keeps growing in real time too.

## The files that do the work

### Manufacturing pipeline — files live in `Manufacturing_Timseries/`

#### `Manufacturing_Timseries/master_data.py` — the "who and where" for machines

Before any sensor reading can be generated, the pipeline needs to know what
plants, production lines, machines, vehicle models, suppliers, and production
batches exist. This file builds all of that, once, when the pipeline starts.

Important: it does this by calling the **same, unmodified generator
functions** that the rest of this project already uses. It doesn't invent a
second copy of plants or machines — it reuses the real ones (7 plants, ~20
production lines, 120 machines).

One extra thing this file handles: the existing production-batch data only
covers a fixed historical window (January to July 2026). But the live
pipeline runs on today's actual date, which falls outside that window. So
this file "wraps around" — it reuses each plant's historical batch calendar
on a cycle, so every live row still gets linked to a real, sensible vehicle
model and supplier batch instead of just showing blank/default values every
day.

#### `Manufacturing_Timseries/live_row_generator.py` — the machine sensor-reading calculator

This is the formula engine for manufacturing data. For one machine at one
point in time, it calculates realistic values for things like:

- Ambient temperature and humidity
- Machine temperature, vibration, power draw
- Line speed, cycle time
- Maintenance status
- Defect rate, rework rate, downtime, quality score
- Paint-specific readings (only for paint lines)

These are the exact same formulas and column names used by the original
historical generator, so the live data "looks and behaves" identically to the
historical data — same 34 columns, same realistic ranges.

The key difference: this version **remembers each machine's last reading** in
memory. So when it calculates this minute's temperature, it nudges slightly
away from last minute's temperature rather than picking a brand new random
value from scratch. That's what keeps the numbers moving smoothly and
realistically instead of jumping around erratically minute to minute —
exactly how a real sensor would behave.

### Vehicle telematics pipeline — files live in `Vechicle_Telematics/`

#### `Vechicle_Telematics/telematics_master_data.py` — the "who's driving" for vehicles

Vehicle telemetry only makes sense for vehicles that have actually been
delivered to a customer, with a full lineage back to the plant/line/batch/
supplier that built them. This file builds that entire lineage once, at
startup, by calling the same chain of unmodified generator functions the rest
of the project already uses: customers → leads → follow-ups → test drives →
bookings → finance applications → cancellations → allocations → deliveries
(plus the plant/machine/supplier/batch master data those deliveries link
back to).

From that, it keeps only the vehicles whose `delivery_status` is
`DELIVERED` — giving a roster of roughly 1,300+ real, fully-lineaged vehicles
(varied across vehicle models, variants, and plants) to generate live
telemetry for.

#### `Vechicle_Telematics/live_telematics_generator.py` — the vehicle sensor-reading calculator

This is the formula engine for telematics data, mirroring
`data/generators/causal/vehicle_telematics_timeseries.py` exactly — same 31
columns, same formulas, same clipping ranges. For one vehicle at one point in
time, it calculates realistic values for things like:

- Vehicle speed, odometer
- Battery temperature, state of charge, voltage, current, internal resistance
- Transmission temperature and slip
- Steering torque/angle, vibration, acceleration, road roughness, impacts
- Diagnostic trouble code (DTC) count and warning flag

Just like the manufacturing generator, this version **remembers each
vehicle's last reading** (speed, ambient temperature, road roughness,
odometer, and its progress along a slow background "wear" curve) in memory
between ticks, so consecutive minutes move smoothly instead of resetting to a
cold start every time.

### `db_writer.py` (lives at the `Live_Data_Formation/` root) — saves live data into the database

This is what pushes every minute's freshly generated rows into the same
PostgreSQL tables the historical data already lives in:

- Manufacturing rows go into the **`manufacturing_timeseries`** table.
- Vehicle telematics rows go into the **`vehicle_telematics_timeseries`**
  table.

It connects using plain `INSERT` statements against those tables **exactly
as they already exist** — same columns, same column order, same data types,
same primary keys, same foreign keys. It does not create, alter, drop, or
migrate anything. If a table's schema ever changes in the future, that has to
happen through the project's normal migration process, not through this file.

It uses the same database-connection resolution as the project's existing
`data/scripts/import_postgres.py`: it checks the `MAHINDRA_DATABASE_URL`
environment variable first, then `DATABASE_URL`, and falls back to a local
default (`mahindra:mahindra@127.0.0.1:5432/mahindra_ai`) if neither is set.

If the database happens to be unreachable at the moment a tick runs (for
example, PostgreSQL isn't running), that tick doesn't crash — its Parquet
file and log line are still written as normal, and only the database part of
that one tick is skipped and clearly marked as `failed` or `skipped` in
`pipeline.log`, so nothing else about the pipeline is affected.

### `live_pipeline.py` (lives at the `Live_Data_Formation/` root) — the scheduler that ties everything together

This file uses both datasets' modules, so it lives at the top level of
`Live_Data_Formation/` alongside the other shared/common files (`README.md`,
`pipeline.log`, `db_writer.py`), rather than inside either dataset-specific
folder. This is the script the `live-data-formation.service` systemd unit
runs. When it starts, it:

1. Logs a `SERVICE_STARTED` line to `pipeline.log`.
2. Builds the manufacturing master data once (plants, lines, machines,
   batches).
3. Builds the vehicle-telematics master data once (the delivered-vehicle
   roster).
4. Connects to the database once (see `db_writer.py` above).
5. Enters a loop that runs forever, once per minute:
   - For **manufacturing**: randomly picks somewhere between 50 and 100
     machines out of the available 120 (a different mix each time), generates
     one fresh sensor reading for each, saves that minute's batch as one
     Parquet file, **and inserts those same rows into the
     `manufacturing_timeseries` table**.
   - For **vehicle telematics**: randomly picks somewhere between 50 and 100
     vehicles out of the delivered roster (a different mix each time),
     generates one fresh telemetry reading for each, saves that minute's
     batch as one Parquet file, **and inserts those same rows into the
     `vehicle_telematics_timeseries` table**.
   - Writes one log line per dataset to `pipeline.log` recording what just
     happened, including whether the database insert succeeded.
6. Waits until the next minute mark, then repeats — indefinitely, until the
   service is stopped.
7. When stopped (via `systemctl --user stop`, a crash-triggered restart, or
   shutdown), logs a `SERVICE_STOPPED` line to `pipeline.log` before exiting.

Both datasets tick on the same 60-second clock, so every minute produces one
new manufacturing file, one new telematics file, one new batch of database
rows for each table, all side by side.

## How to run it

The pipeline runs as a **systemd user service** named
`live-data-formation.service`. systemd keeps it running indefinitely in the
background, automatically restarts it if it ever crashes, and (with
lingering enabled for this user) brings it back up automatically after a VM
reboot — without needing anyone logged in.

### Start it

```bash
systemctl --user start live-data-formation.service
```

Note: on first startup it takes about a minute to build both master-data
rosters (manufacturing master data plus the delivered-vehicle lineage) before
the first tick appears — this is normal.

### Stop it

```bash
systemctl --user stop live-data-formation.service
```

### Restart it

```bash
systemctl --user restart live-data-formation.service
```

### Check whether it's running

```bash
systemctl --user status live-data-formation.service
```

You can also confirm start/stop just by reading `pipeline.log` (see below) —
every start and stop is recorded there as its own line, so you don't need
terminal/systemd access to know whether the service is currently running.

### Manual alternative (for quick, one-off tests only)

You can also run it in the foreground directly without going through
systemd:

```bash
python3 live_pipeline.py
```

In this mode it keeps running in your terminal until you press Ctrl+C. Avoid
running this at the same time as the systemd service, since that would start
two pipelines writing to the same files/database at once.

## Where the data ends up

### `Manufacturing_Timseries/Data_Parquet/` — live manufacturing data

Files are organized in three levels of folders, so it's easy to browse by
date and time:

```
Manufacturing_Timseries/
└── Data_Parquet/
    └── 2026-08-27/              ← one folder per calendar date (IST)
        └── 13/                  ← one folder per hour of that date (24-hour format)
            ├── 13-09.parquet    ← one file per minute, named HH-MM
            ├── 13-10.parquet
            └── 13-11.parquet
```

Each `.parquet` file contains that single minute's batch of new sensor
readings — somewhere between 50 and 100 rows, one row per machine that was
sampled that minute. Every row has the same 34 columns as the historical
dataset (plant, line, machine, sensor readings, quality/defect metrics, etc.),
so it can be read, combined, or analyzed the exact same way.

### `Vechicle_Telematics/Data_Parquet/` — live vehicle telematics data

Same folder structure as manufacturing, just under the telematics folder:

```
Vechicle_Telematics/
└── Data_Parquet/
    └── 2026-08-27/
        └── 13/
            ├── 13-09.parquet
            ├── 13-10.parquet
            └── 13-11.parquet
```

Each `.parquet` file contains that single minute's batch of new telemetry
readings — somewhere between 50 and 100 rows, one row per vehicle that was
sampled that minute. Every row has the same 31 columns as the historical
`vehicle_telematics_timeseries.csv` dataset (vehicle/model/plant lineage,
battery/transmission/steering sensor readings, DTC count, etc.).

### `manufacturing_timeseries` and `vehicle_telematics_timeseries` — the same PostgreSQL tables the historical data already uses

Every minute's batch of new rows is also inserted directly into the existing
database, into the exact same tables that already hold the historical CSVs:

- Live manufacturing rows → `manufacturing_timeseries` table
- Live vehicle telematics rows → `vehicle_telematics_timeseries` table

Nothing about those tables was changed to make this work — same columns,
same column order, same data types, same primary key
(`timestamp` + `machine_id` for manufacturing, `timestamp` + `vehicle_id` for
telematics), same foreign keys pointing at plants/machines/production
lines/batches/supplier lots/vehicle models. The live rows simply sit
alongside the historical rows in the same tables, distinguishable only by
their more recent `timestamp` values.

### `pipeline.log` — the activity tracker for both datasets, and for the service itself

Every minute, two lines are appended here (one per dataset) so you can see
the pipeline is alive, how much data each dataset is producing, and whether
that data made it into the database:

```
2026-08-28 13:15:51 IST | dataset=manufacturing_timeseries | new_rows_generated=95 | db_insert=ok(95)
2026-08-28 13:15:51 IST | dataset=vehicle_telematics_timeseries | new_rows_generated=97 | db_insert=ok(97)
2026-08-28 13:16:51 IST | dataset=manufacturing_timeseries | new_rows_generated=72 | db_insert=ok(72)
2026-08-28 13:16:51 IST | dataset=vehicle_telematics_timeseries | new_rows_generated=91 | db_insert=ok(91)
```

Each line shows the exact time (in IST, Indian Standard Time) the batch was
generated, which dataset it belongs to, how many new rows were created in
that minute, and the database result for that minute:

- `db_insert=ok(N)` — all `N` rows were successfully inserted into the table.
- `db_insert=failed` — the insert was attempted but hit an error (see
  `pipeline_stdout.log` for the exact error message); the Parquet file for
  that minute was still written normally.
- `db_insert=skipped` — no database connection was available for that tick
  (for example, PostgreSQL wasn't reachable when the pipeline started); the
  Parquet file for that minute was still written normally.

**Start/stop confirmation.** Every time the service actually starts or
stops, one extra line is written here too, so you can confirm the service's
state just by opening this file — no terminal or `systemctl` access needed:

```
2026-08-28 21:44:48 IST | event=SERVICE_STARTED
2026-08-28 21:45:10 IST | event=SERVICE_STOPPED
```

- `event=SERVICE_STARTED` — written the moment the pipeline process comes up
  (before it starts building master data), whether that happened via
  `systemctl --user start`, an automatic restart after a crash, or a reboot.
- `event=SERVICE_STOPPED` — written right before the process exits, whether
  that happened via `systemctl --user stop` or the process being killed by
  systemd for any other reason.

Because these are the last lines written before/after every run, scrolling
to the bottom of `pipeline.log` always tells you: whether the service is
currently up (most recent event line says `SERVICE_STARTED` and normal
per-minute tick lines are still following it), or currently down (most
recent event line says `SERVICE_STOPPED` with no tick lines after it).

## Folder layout at a glance

Each dataset's own Python files live inside that dataset's folder (outside of
`Data_Parquet/`, which is reserved for generated data only). Only the files
that are genuinely shared between both datasets — the scheduler, the
database writer, the log, and this README — live at the top level.

```
Live_Data_Formation/
├── Manufacturing_Timseries/
│   ├── Data_Parquet/                ← live manufacturing sensor data (generated files only)
│   ├── master_data.py               ← manufacturing plants/lines/machines/batches setup
│   └── live_row_generator.py        ← manufacturing sensor-reading formulas
├── Vechicle_Telematics/
│   ├── Data_Parquet/                ← live vehicle telematics data (generated files only)
│   ├── telematics_master_data.py    ← delivered-vehicle roster/lineage setup
│   └── live_telematics_generator.py ← vehicle sensor-reading formulas
├── live_pipeline.py                 ← the scheduler (drives both datasets; common to both)
├── db_writer.py                     ← inserts live rows into the existing DB tables (common to both)
├── pipeline.log                     ← one line per dataset per minute (timestamp + row count + DB status), plus SERVICE_STARTED/SERVICE_STOPPED lines
├── pipeline_stdout.log              ← raw console output from the service (for debugging failures)
└── README.md                        ← this file (common)
```

The systemd unit file that manages the service itself lives outside this
folder, at `~/.config/systemd/user/live-data-formation.service` — it just
points at `live_pipeline.py` above and keeps it running.

## What stays the same as before

- **No existing files were changed.** Everything in `data/` (generators,
  config, the historical Parquet/CSV files, the Postgres import script) is
  untouched. This folder only reads from it.
- **No database schema changes.** The `manufacturing_timeseries` and
  `vehicle_telematics_timeseries` tables were not created, altered, or
  migrated by this feature — they already existed from the historical import,
  with exactly the same columns, types, primary keys, and foreign keys as
  before. This pipeline only runs plain `INSERT` statements against them.
- **Same schema for both datasets.** Every column, its meaning, and its
  realistic value range matches each original historical generator exactly —
  nothing about the underlying "database shape" was altered.
- **Still synthetic.** This is still fake, artificially generated data for
  demo/testing purposes — it just now arrives continuously instead of as one
  big historical dump.

## Quick recap in one sentence

Running as a systemd service that logs every start and stop to
`pipeline.log`, this pipeline manufactures 50-100 new, realistic
manufacturing sensor readings AND 50-100 new, realistic vehicle telematics
readings every 60 seconds, saves each as its own neatly dated/timed Parquet
file, inserts that same data straight into the existing
`manufacturing_timeseries` and `vehicle_telematics_timeseries` database
tables (without touching their schema), and logs exactly when, how many
rows, and whether the database insert succeeded for each dataset —
simulating two live data feeds, backed by a live-growing database, without
changing anything in the existing project.
