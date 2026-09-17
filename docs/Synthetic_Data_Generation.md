# Synthetic Data Generation

How the deterministic, India-flavoured, business-consistent synthetic dataset
in `data/synthetic/` is produced.

## Framework (`data/generators/common.py`)

| Piece | Purpose |
|---|---|
| `GENERATOR_SEED = 20260806` | Fixed master seed — **never change** (changing it regenerates every dataset) |
| `GenConfig` | All record counts + `--scale` multiplier + `n()` helper |
| `make_faker(seed)` | Deterministic Faker with `en_IN` locale (each generator offsets the seed by +1…+17 so streams never collide) |
| `REGIONS` / `REGION_CITIES` / `VEHICLE_MODELS` | Shared pools matching the backend lookup tables exactly |
| `MODEL_PRICE_LAKH` | Ex-showroom price bands for revenue math |
| `inr(amount)` | Formats amounts like the UI (`₹1.8 Cr`, `₹42 L`) |
| `business_chain_score(rng)` | The interconnection engine (below) |
| `write_csv(name, rows)` | UTF-8 CSV writer with stable column order |
| `jdump(value)` | Compact JSON serialization for JSONB columns |

## The business chain (interconnection guarantee)

```python
quality          = randint(25, 95)                       # lead quality
booking_prob     = clamp(40 + 0.45·quality ± 6)          # ↑ quality → ↑ booking
finance_approval = clamp(35 + 0.55·booking_prob ± 8)     # ↑ booking → ↑ approval
csat             = clamp(55 + 0.35·finance_approval ± 5) # ↑ approval → ↑ CSAT
```

Every module consumes these correlated scores:

- **Dealers**: quality → hot-lead share; `leakage_pct = 100 − quality ± noise`.
- **Leads**: inherit dealer quality; `score ≥ 75 ⇒ hot`, status/timestamps derived consistently.
- **Customer twins**: approval band decides income stability, repayment history, approval_status; NBA confidence = finance_approval; cross-sell propensity = CSAT.
- **Collections**: DPD → roll-forward risk → action/flag → recovery probability.
- **Circularity**: traceability → buyer_match → closure_prob.
- **Trust**: confidence ≥ 85 ⇒ approved/low-risk/complete audit.
- **Executive KPIs**: literally aggregated from the generated dealer funnel (totals, averages, converted counts).

## Generator catalogue

| File | Seed offset | Tables produced | Highlights |
|---|---|---|---|
| `reference_generator.py` | +1 | regions, vehicle_models, users | Fixed pools; demo principal pinned |
| `dealer_generator.py` | +2 | dealers, dealer_leads | `build()` reusable; exposes `region`/`city` context columns |
| `customer_generator.py` | +3 | customer_twins | NBA/risk/cross-sell JSON twins |
| `finance_generator.py` | +4 | finance_products | Loan/insurance/add-on cards |
| `collections_generator.py` | +5 | collections_agents, collections_cases | DPD-driven risk model |
| `warehouse_generator.py` | +6 | warehouse_signals | 3 panels × templates |
| `shipment_generator.py` | +7 | logistics_routes | City-pair corridors, SLA model |
| `circularity_generator.py` | +8 | carbon_credits | RVSF/ELV batch codes |
| `trust_generator.py` | +9 | trust_decisions, compliance_rules | 6-step lineage JSON |
| `agent_generator.py` | +10 | ai_agents, xr_experiences | Agent roster + AR/VR cards |
| `mobility_generator.py` | +11 | causal_nodes, causal_edges, mobility_kpis, causal_qa | Fixed 12-node topology; warranty + dMRV Q&A |
| `overview_generator.py` | +12 | kpis, kpi_drivers, recommendations | Aggregates dealer funnel |
| `catalogue_generator.py` | +13 | solution_buckets, solutions, poc_items | Capability × domain templates |
| `copilot_generator.py` | +14 | suggested_prompts | Templated over shared pools |
| `simulation_generator.py` | +15 | simulation_runs | Inputs/outputs mirror engine schemas |
| `warranty_generator.py` | +16 | *(future)* warranty_claims | Links dealer codes + batch B-2141 |
| `notification_generator.py` | +17 | *(future)* notifications | Events about generated entities |

Determinism was verified: two consecutive `run_all.py` executions produce
**byte-identical** CSVs (MD5 compared).

## Record counts (default scale 1.0)

24 dealers · 151 leads · 48 customer twins · 10 finance products · 8 agents ·
40 collections cases · 18 signals · 12 routes · 20 credits · 20 trust
decisions · 6 compliance rules · 12 AI agents · 6 XR experiences · 12 nodes ·
12 edges · 8 mobility KPIs · 14 Q&A · 6 KPIs · 14 drivers · 8
recommendations · 9 buckets · 36 solutions · 6 PoC items · 10 prompts · 25
simulation runs · 5 users · 4 regions · 5 vehicle models
= **549 seeded rows** (+ 60 warranty claims, 50 notifications as future CSVs).

## Scaling volumes

```powershell
backend\.venv\Scripts\python.exe data\generators\run_all.py --scale 10
```

`--scale` multiplies every count except the fixed causal-graph topology
(12 nodes / 12 edges is a UX layout, not volume). Note: scaling changes the
output; the byte-identical guarantee holds per scale value.

## CSV conventions (contract with the seeder)

- Enums stored lowercase (`hot`, `pending`, `auto_sales`…).
- Booleans as `true`/`false`.
- JSONB/ARRAY columns as compact JSON strings.
- `None` → empty cell.
- Timestamps ISO-8601.
- Extra **context columns** (`dealers.region`, `dealers.city`,
  `collections_cases.product`) and **FK helper columns** (`dealer_code`,
  `kpi_code`, `bucket_name`, `source_label`, `target_label`) are consumed by
  the seeder and never reach PostgreSQL.

## Future replacement with real Mahindra data

1. Extracts land in `data/raw/` (immutable snapshots).
2. Normalization jobs reshape them into `data/processed/<table>.csv` using
   the exact column contracts above (same headers, same encodings).
3. `seed_database.py` loads them unchanged — the UUID strategy switches from
   deterministic-synthetic to source-system keys when available.
4. Generators are retired; the frontend and schema never change.
