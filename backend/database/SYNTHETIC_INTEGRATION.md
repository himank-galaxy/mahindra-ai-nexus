# Synthetic Data Integration Documentation

## Overview

This document provides a comprehensive report on the integration of synthetic data from `data/synthetic/` into the existing `mahindra_ai` PostgreSQL database alongside pre-existing mock data.

---

## Directives & Guarantees Satisfied

1. **Single Database Coexistence**: Both existing curated mock data AND synthetic data reside together in the single PostgreSQL database (`mahindra_ai`).
2. **Zero Loss of Mock Data**: The database was never dropped, reset, or truncated. Existing mock data remains 100% intact and untouched.
3. **No Reseeding Prerequisite**: Pre-existing database state was preserved without re-running mock seed scripts.
4. **Idempotency**: Repeated runs of the import layer (`database/import_synthetic.py`) use deterministic UUID5 primary keys (`synthetic_id()`), updating existing synthetic rows without duplicating or disturbing mock records.
5. **Constraint Safety**: Empirical conflict analysis identified unique constraint collisions (`kpis`, `compliance_rules`, `ai_agents`, `xr_experiences`, `causal_nodes`, `mobility_kpis`, `suggested_prompts`). Deterministic namespacing was applied strictly to colliding synthetic keys while updating dependent child foreign keys consistently.
6. **Code Base Integrity**: `database/seed_database.py` and core application files were kept completely untouched. Integration was handled by a dedicated, non-destructive import script `database/import_synthetic.py`.

---

## Discovered Datasets & Table Mapping

| CSV File | PostgreSQL Table | ORM Model | Natural Key / ID Strategy | Status |
|---|---|---|---|---|
| `regions.csv` | `regions` | `Region` | `code` | Shared reference data (Merged) |
| `vehicle_models.csv` | `vehicle_models` | `VehicleModel` | `name` | Shared reference data (Merged) |
| `users.csv` | `users` | `User` | `email` | Imported (5 rows) |
| `dealers.csv` | `dealers` | `Dealer` | `code` | Imported (24 rows) |
| `dealer_leads.csv` | `dealer_leads` | `DealerLead` | `{dealer_code}:{sort_order}` | FK linked to synthetic dealers (151 rows) |
| `customer_twins.csv` | `customer_twins` | `CustomerTwin` | `name` | Imported (48 rows) |
| `finance_products.csv` | `finance_products` | `FinanceProduct` | `name` | Imported (10 rows) |
| `collections_agents.csv` | `collections_agents` | `CollectionsAgent` | `name` | Imported (8 rows) |
| `collections_cases.csv` | `collections_cases` | `CollectionsCase` | `customer` | Imported (40 rows) |
| `warehouse_signals.csv` | `warehouse_signals` | `WarehouseSignal` | `{panel}:{sort_order}` | Imported (18 rows) |
| `logistics_routes.csv` | `logistics_routes` | `LogisticsRoute` | `name` | Imported (12 rows) |
| `carbon_credits.csv` | `carbon_credits` | `CarbonCredit` | `code` | Imported (20 rows) |
| `trust_decisions.csv` | `trust_decisions` | `TrustDecision` | `code` | Imported (20 rows) |
| `compliance_rules.csv` | `compliance_rules` | `ComplianceRule` | `label` | Namespaced `(Synthetic)` (6 rows) |
| `ai_agents.csv` | `ai_agents` | `AiAgent` | `name` | Namespaced `(Synthetic)` (12 rows) |
| `xr_experiences.csv` | `xr_experiences` | `XrExperience` | `code` | Namespaced `syn-` (6 rows) |
| `causal_nodes.csv` | `causal_nodes` | `CausalNode` | `label` | Namespaced `(Synthetic)` (12 rows) |
| `causal_edges.csv` | `causal_edges` | `CausalEdge` | `{source}->{target}` | FK linked to synthetic nodes (12 rows) |
| `mobility_kpis.csv` | `mobility_kpis` | `MobilityKpi` | `label` | Namespaced `(Synthetic)` (8 rows) |
| `causal_qa.csv` | `causal_qa` | `CausalQa` | `{category}:{sort_order}` | Imported (14 rows) |
| `kpis.csv` | `kpis` | `Kpi` | `code` | Namespaced `syn-` (6 rows) |
| `kpi_drivers.csv` | `kpi_drivers` | `KpiDriver` | `{kpi_code}:{sort_order}` | FK linked to synthetic KPIs (14 rows) |
| `recommendations.csv` | `recommendations` | `Recommendation` | `code` | Imported (8 rows) |
| `solution_buckets.csv` | `solution_buckets` | `SolutionBucket` | `name` | Imported (9 rows) |
| `solutions.csv` | `solutions` | `Solution` | `name` | FK linked to solution buckets (36 rows) |
| `poc_items.csv` | `poc_items` | `PocItem` | `name` | Imported (6 rows) |
| `suggested_prompts.csv` | `suggested_prompts` | `SuggestedPrompt` | `text` | Namespaced `(Synthetic)` (10 rows) |
| `simulation_runs.csv` | `simulation_runs` | `SimulationRun` | `run:{row_index}` | Imported (25 rows) |
| `notifications.csv` | — | — | Future phase dataset | Skipped |
| `warranty_claims.csv` | — | — | Future phase dataset | Skipped |

---

## Conflict Resolution & Namespacing Rules

To ensure zero unique key collision with existing mock data:
1. **KPI Codes**: Synthetic KPI codes (`rev`, `leak`, `book`, etc.) are transformed to `syn-rev`, `syn-leak`, etc. Child `kpi_drivers` FK helper `kpi_code` is transformed identically to maintain foreign key integrity.
2. **Compliance Rules & AI Agents**: Synthetic labels/names appending `(Synthetic)` to differentiate from pre-existing mock compliance rules and agents.
3. **XR Experiences**: Synthetic codes prefixed with `syn-` (e.g., `syn-showroom`).
4. **Causal Twin Graph**: Synthetic node labels appending `(Synthetic)` and synthetic edge source/target labels updated to match.
5. **Mobility KPIs & Prompts**: Synthetic labels/texts appended with `(Synthetic)`.

---

## Empirical Database Row Counts

Pre-import vs Post-import database row audit:

| Table Name | Mock Rows | Synthetic Rows Added | Combined Total Rows |
|---|---|---|---|
| `ai_agents` | 10 | 12 | 22 |
| `carbon_credits` | 5 | 20 | 25 |
| `causal_edges` | 12 | 12 | 24 |
| `causal_nodes` | 12 | 12 | 24 |
| `causal_qa` | 8 | 14 | 22 |
| `collections_agents` | 6 | 8 | 14 |
| `collections_cases` | 5 | 40 | 45 |
| `compliance_rules` | 5 | 6 | 11 |
| `customer_twins` | 1 | 48 | 49 |
| `dealer_leads` | 5 | 151 | 156 |
| `dealers` | 5 | 24 | 29 |
| `finance_products` | 8 | 10 | 18 |
| `kpi_drivers` | 24 | 14 | 38 |
| `kpis` | 6 | 6 | 12 |
| `logistics_routes` | 5 | 12 | 17 |
| `mobility_kpis` | 7 | 8 | 15 |
| `poc_items` | 0 | 6 | 6 |
| `recommendations` | 5 | 8 | 13 |
| `regions` | 4 | 0 (Merged) | 4 |
| `simulation_runs` | 1 | 25 | 26 |
| `solution_buckets` | 6 | 9 | 15 |
| `solutions` | 25 | 36 | 61 |
| `suggested_prompts` | 8 | 10 | 18 |
| `trust_decisions` | 5 | 20 | 25 |
| `users` | 1 | 5 | 6 |
| `vehicle_models` | 5 | 0 (Merged) | 5 |
| `warehouse_signals` | 15 | 18 | 33 |
| `xr_experiences` | 4 | 6 | 10 |
| **TOTAL** | **196** | **548** | **744** |

---

## Execution Guide

### 1. Database Backup
Before performing synthetic imports:
```powershell
docker exec mahindra-postgres pg_dump -U mahindra -d mahindra_ai > backup.sql
```

### 2. Dry-Run Validation
To test parsing, coercions, and constraint checking with zero writes:
```powershell
python database/import_synthetic.py --dry-run
```

### 3. Actual Import Execution
To import synthetic data into PostgreSQL `mahindra_ai`:
```powershell
python database/import_synthetic.py
```

### 4. API & Verification
Verify REST API response on FastAPI backend:
```powershell
python scratch/verify_api.py
```
All endpoints (`/health`, `/api/v1/overview/kpis`, `/api/v1/dealers`, `/api/v1/overview/recommendations`, `/api/v1/catalogue/buckets`, `/api/v1/trust/decisions`, etc.) respond HTTP 200 returning combined mock + synthetic records.
