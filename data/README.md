# data/ — Synthetic Data Pipeline

This folder is the **additive** data layer that prepares the project for a
production FastAPI + PostgreSQL backend. Nothing in the existing frontend is
modified — the CSVs produced here mirror the PostgreSQL schema 1:1 so the
backend can replace frontend mock data with zero UI changes.

## Folder structure

```
data/
├── generators/        # Per-entity Python generators (Faker, en_IN)
│   ├── common.py      # Framework: seeds, pools, business chain, CSV writer
│   ├── run_all.py     # Orchestrator (--scale for volume control)
│   └── *_generator.py # One file per entity / business module
├── synthetic/         # Generated CSVs (schema-locked, deterministic)
├── raw/               # Landing zone for future real Mahindra extracts
├── processed/         # Cleaned/normalized real data before loading
└── README.md
```

## Quick start

```powershell
# from repo root, using the backend virtualenv
backend\.venv\Scripts\python.exe data\generators\run_all.py            # default volume
backend\.venv\Scripts\python.exe data\generators\run_all.py --scale 3  # 3x volume
```

Output is **byte-identical on every run** (fixed seed `20260806` in
`common.py`). Only `--scale` changes the output.

## Datasets (24 CSVs → 28 tables seeded, 2 future)

| Generator | CSV(s) → table(s) | Module |
|---|---|---|
| reference | regions, vehicle_models, users | Master data |
| dealer | dealers, dealer_leads | Dealer Revenue Optimizer |
| customer | customer_twins | Financial Twin |
| finance | finance_products | Finance (loan/insurance cards) |
| collections | collections_agents, collections_cases | Collections Swarm |
| warehouse | warehouse_signals | Inventory/warehouse tiles |
| shipment | logistics_routes | Logistics Control Tower |
| circularity | carbon_credits | Circular Economy |
| trust | trust_decisions, compliance_rules | Compliance Trust Ledger |
| agent | ai_agents, xr_experiences | AI Factory / XR |
| mobility | causal_nodes, causal_edges, mobility_kpis, causal_qa | Auto Mobility Twin |
| overview | kpis, kpi_drivers, recommendations | Executive Dashboard |
| catalogue | solution_buckets, solutions, poc_items | AI Catalogue / PoC |
| copilot | suggested_prompts | AI Copilot |
| simulation | simulation_runs | Simulation Center |
| warranty *(future)* | warranty_claims.csv | No table yet — Phase 2 |
| notification *(future)* | notifications.csv | No table yet — Phase 2 |

## Loading into PostgreSQL

See [`backend/database/seed_database.py`](../backend/database/seed_database.py)
and [`docs/Seeding_Guide.md`](../docs/Seeding_Guide.md). Highlights:
deterministic UUIDs, FK-safe ordering, idempotent reruns, unique-collision
safety checks, `--dry-run` validation.

## Real Mahindra data (future)

`raw/` and `processed/` are reserved for the production cutover: real
extracts land in `raw/`, get normalized into `processed/` using the same
column contracts as `synthetic/`, and load through the same seeder. The
generators can then be retired without any schema change.

See `docs/Data_Model.md`, `docs/Database_Schema.md`,
`docs/Entity_Relationships.md`, `docs/Synthetic_Data_Generation.md` for the
full picture.
