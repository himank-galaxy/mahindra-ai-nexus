# Predictive Early-Warning Service — Implementation Plan

Builds the left-hand half of `docs/README_Predictive_Early_Warning_with_LPCMCI.md`
(the predictive model + warning) and connects it to the causal engine already
built in `Causal_Discovery_Service/` for the "Investigate" step.

## Design principle (from the README, kept exactly)

> The predictive model generates the warning. LPCMCI explains the warning.

This service owns *prediction*. It reuses `Causal_Discovery_Service/`'s
already-built data-reading, preprocessing, and LPCMCI modules for
*explanation* rather than rebuilding them — that reuse is intentional (see
`changes.md`), unlike `Causal_Discovery_Service`'s own relationship to the
old backend causal service, which was required to have zero dependency.

## Real data used to calibrate this plan (not the README's example numbers)

The README's own thresholds (e.g. "battery temperature > 55°C") are
illustrative, not calibrated to this project's actual synthetic data.
Checked directly against the live `vehicle_telematics_timeseries` table
before writing any code:

| Fact checked | Result |
|---|---|
| Live data span | ~4 days (2026-08-28 07:45 → 2026-09-01 11:05) |
| Rows per vehicle | median 333, p90 355, max 395 — every vehicle has enough |
| `battery_temperature_c` range | p50=30.4°C, p90=32.3°C, p99=33.6°C, max=35.2°C |
| `battery_voltage_v` range | p50=401.7V, p05=400.7V |
| `battery_internal_resistance_ohm` | p50=0.0233Ω, p95=0.0258Ω |
| Vehicles with a real rising temperature trend (>2°C, first half vs second half of their history) | 184 of 1,346 |

That last row matters most: it confirms the live data genuinely contains
vehicles on a degrading trajectory (the synthetic generator's
`BATTERY_DEGRADATION` scenario family), so there is real signal to learn
from — this isn't a random dataset with no pattern to find.

## Warning types and target metrics

| Warning type | Target metric | Threshold | Direction |
|---|---|---|---|
| `BATTERY_OVERHEATING` | `battery_temperature_c` | `> 55.0` (domain-realistic Li-ion critical temp) | rising = risk |
| `LOW_BATTERY_VOLTAGE` | `battery_voltage_v` | `< 315.0` (domain-realistic, ~10-15% SoC) | falling = risk |
| `BATTERY_DEGRADATION` | `battery_internal_resistance_ohm` | `> 0.0258` (~p95, data-derived) | rising = risk |

Only these three to start (the ones with clean signal confirmed above).
More can be added the same way once these are validated.

**Revised from the original data-derived values** (`> 33.0`, `< 400.8` —
see the "Real data used to calibrate this plan" table above) to the
domain-realistic values shown here. The original two were derived from
this synthetic dataset's own narrow observed range (normal operation
tops out around 33-35C, never approaches a real thermal-runaway
temperature), which meant they fired on ordinary operating variation
rather than genuine risk. See `changes.md` for the full record of this
revision, including its effect on the already-trained models.

## Window sizes (adapted to ~4 days of real history, not the README's 48h/24h)

- **Feature window**: trailing **12 hours** of telemetry (not 48h — with
  only ~4 days of live history total, a 48h feature window plus a 24h label
  window would leave very few usable training examples per vehicle).
- **Label window**: following **12 hours** ("did the threshold get crossed
  in the next 12 hours?").
- These will be revisited once `Live_Data_Formation` has been running
  longer and more history is available — the code makes both configurable,
  not hardcoded.

## Files

```
Predictive_Early_Warning_Service/
├── IMPLEMENTATION_PLAN.md
├── changes.md                    <- written after implementation
├── requirements.txt              <- scikit-learn, joblib, fastapi, uvicorn (installed into Causal_Discovery_Service/.venv)
├── config.py                     <- warning types, thresholds, window sizes
├── features.py                   <- ONE feature-computation function, used identically at training time and live-scoring time
├── training_data.py              <- scans historical data, builds labeled (features, label) rows
├── train_model.py                <- trains + saves one classifier per warning type
├── models/                       <- saved model files (.joblib)
├── scheduler.py                  <- live scoring loop (creates/updates warnings)
├── warnings_store.py             <- reads/writes warning JSON records + lifecycle status
├── warnings/                     <- warning records live here (local files, not a new DB schema yet)
├── api/
│   └── main.py                   <- new endpoints: list warnings, get one, investigate one
└── ui/
    ├── warnings-list.html/js     <- Screen 1: continuously-updating alert list
    └── investigate.html/js       <- Screen 2: target-centered causal graph for one warning
```

Plus one small, additive extension to the existing service:

```
Causal_Discovery_Service/
└── graph_walker.py               <- NEW file: classifies nodes as ROOT_CANDIDATE / UPSTREAM / TARGET / DOWNSTREAM relative to one target node
```

And one small, backward-compatible change to `Causal_Discovery_Service/preprocessing.py`:
an optional `protected_columns` parameter (default: none) on the near-constant
filter, so a warning's target metric can never be dropped during
preprocessing even if it would otherwise look near-constant. Existing
callers that don't pass it behave exactly as before.

## Avoiding future leakage (README section 43, kept as a hard rule)

- Training labels only ever look forward from a past point using data that
  has *already arrived* by the time the code runs — never using data past
  "today" that doesn't exist yet.
- When a warning is investigated, the causal window is capped at the
  warning's own timestamp — the LPCMCI panel never includes data from after
  the warning was created.

## What's deliberately out of scope for this first pass

- Fleet/model-level consensus graphs (README §29-31) — vehicle-level only
  for now.
- A dedicated Postgres schema for warnings — local JSON files first,
  matching how `Causal_Discovery_Service` started with file-based `runs/`
  output before considering a DB schema.
- Model retraining automation — `train_model.py` is run manually for now.
