# Data Model

The complete enterprise data model behind the Mahindra AI Command Center.
Source of truth: the SQLAlchemy ORM models in `backend/app/models/` — this
document describes them module by module, including business rules, lookup vs
master vs transactional classification, and required synthetic volume.

## Entity classification

| Class | Tables |
|---|---|
| **Lookup / reference** | `regions`, `vehicle_models` (natural string PKs) |
| **Master** | `dealers`, `users`, `finance_products`, `solution_buckets`, `causal_nodes`, `collections_agents`, `ai_agents` |
| **Transactional / event** | `dealer_leads`, `collections_cases`, `carbon_credits`, `trust_decisions`, `recommendations`, `simulation_runs`, `copilot_messages` |
| **Analytical / derived** | `kpis`, `kpi_drivers`, `mobility_kpis`, `causal_qa`, `warehouse_signals`, `causal_edges`, `solutions`, `poc_items`, `customer_twins`, `xr_experiences`, `compliance_rules`, `suggested_prompts` |
| **Runtime (not seeded)** | `copilot_sessions`, `copilot_messages` (created by live chat traffic) |

---

## 1. Reference & master

### regions (lookup)
| Column | Type | Notes |
|---|---|---|
| `code` | String(32) PK | `West`, `North`, `South`, `East` — drives simulation dropdowns |

### vehicle_models (lookup)
| Column | Type | Notes |
|---|---|---|
| `name` | String(64) PK | `XUV700`, `Scorpio-N`, `Thar`, `Bolero`, `XUV 3XO` |

### users (master)
| Column | Type | Rules |
|---|---|---|
| `id` | UUID PK | deterministic uuid5 for synthetic rows |
| `email` | String(256) UNIQUE | natural identity |
| `full_name` | String(128) | |
| `is_active` | Boolean, default true | |

**Business rule:** demo principal `demo@mahindra.ai` is always present and active.

## 2. Dealer Revenue Optimizer (Auto)

### dealers (master)
`code` (UNIQUE, natural key), `name`, `leads`, `hot_leads`, `test_drives_pending`,
`booking_prob` (0–100 CHECK), `revenue_at_risk` (INR display string),
`leakage_pct` (0–100), `bay_util_pct` (0–100), `sort_order`.

### dealer_leads (transactional — the booking funnel)
`dealer_id` FK → dealers (CASCADE), `name`, `vehicle` (from vehicle_models pool),
`score` (0–100), `prob` (0–100), `action` (NBA text), `revenue` (INR string),
`status` enum `hot|warm|cool|message_sent|converted`, `test_drive_slot`,
`message_sent_at`, `converted_at`, `sort_order`; soft-delete enabled.

**Business rules**
- `score ≥ 75` ⇒ `hot`; `55–74` ⇒ `warm/message_sent/converted`; below ⇒ `cool/warm`.
- `prob` derives from `score` (`30 + 0.6·score ± 5`).
- `message_sent_at` set only for `message_sent`/`converted`; `converted_at` only for `converted`.
- Dealer `leakage_pct` inversely correlates with lead quality.

## 3. Financial Twin (Finance)

### customer_twins (analytical — one twin per customer)
`name`, `location`, `income_stability` (High/Medium/Low), `repayment`,
`products` (JSON list), `nba` (JSON: action, expected_uplift_pct, confidence),
`risk_decomposition` (JSON: credit/income/behaviour/market),
`cross_sell` (JSON: product, propensity_pct, annual_income_lakh),
`approval_status` enum `draft|under_review|approved`.

### finance_products (master — loan/insurance/add-on cards)
`name` UNIQUE, `customers` (e.g. `34K`), `risk` (display string),
`cross_sell` (e.g. `+8.4%`), `opportunity`, `sort_order`.

### collections_agents / collections_cases (Collections Swarm)
Agent: `name` UNIQUE, `status` enum `active|reviewing|recommended`.
Case: `customer`, `dpd`, `outstanding` (INR string), `roll_forward_risk`
(0–100), `channel`, `action`, `prob` (0–100), `compliance_flag` enum
`ok|review|escalate`, `status` enum `pending|approved|human_review|modified`,
`modified_action` (human override), `sort_order`.

**Business rules**
- `roll_forward_risk = f(dpd)`; risk ≥ 70 ⇒ restructure + review/escalate flag.
- `prob = 95 − roll_forward_risk ± 10` (recovery probability).
- High DPD ⇒ field/tele channels; low DPD ⇒ digital nudges.

## 4. Logistics Control Tower

### logistics_routes (transactional-ish master)
`name` UNIQUE (`Origin → Destination`), `sla_risk` & `delay_prob` (0–100),
`cost` (INR string), `recommended_action`, `rerouted` (bool), `rerouted_at`,
`auto_healed` (bool), `sort_order`.

### warehouse_signals (analytical tiles — the "inventory" dataset)
`panel` enum `warehouse|collections_metrics|rvsf`, `label`, `value`,
`tone` (`success|warning|danger|default`), `sort_order`. One table serves
three UI panels via the `panel` discriminator.

**Business rule:** `sla_risk ≈ delay_prob ± noise`; risk ≥ 75 forces an
active mitigation action (air split).

## 5. Circular Economy

### carbon_credits (transactional marketplace rows)
`code` UNIQUE, `type` (Carbon/EPR/SDG/CD), `price` (₹ string),
`buyer_match`, `closure_prob`, `traceability` (all 0–100), `repriced_at`,
`buyer_matched_at`, `sort_order`.

**Business rule:** `traceability → buyer_match → closure_prob` (monotone
chain); low traceability credits are repricing candidates.

## 6. Compliance Trust Ledger

### trust_decisions (transactional audit trail)
`code` UNIQUE, `use_case`, `recommendation`, `data_sources`, `confidence`
(0–100), `approval` enum `approved|human_review|pending|rejected|escalated`,
`risk` enum, `audit` enum `complete|pending`, `rejection_reason`,
`lineage` (JSON array of 6 steps), `sort_order`.

### compliance_rules
`label` UNIQUE, `status`, `sort_order`.

**Business rule:** confidence ≥ 85 ⇒ approved + low risk + complete audit;
below 70 ⇒ human review / pending with medium-high risk.

## 7. AI Factory / XR

### ai_agents
`name` UNIQUE, `role`, `status` enum (shares `agent_status` PG type with
collections agents), `last_activity`, `use_areas` (TEXT[] / JSON list),
`sort_order`.

### xr_experiences
`code` UNIQUE, `title`, `use_case`, `feature`, `impact`, `sort_order`.

## 8. Auto Mobility Causal Twin

### causal_nodes (master — fixed UX topology)
`label` UNIQUE, `x`/`y` (SVG coords, Float), `metric`, `trend`,
`drivers` (JSON list), `action`, `sort_order`.

### causal_edges
`source_node_id` / `target_node_id` FKs → causal_nodes (CASCADE),
UNIQUE pair constraint, `sort_order`.

### mobility_kpis / causal_qa
KPIs: `label` UNIQUE, `value`, `trend`. Q&A: `category` enum
`mobility|dmrv`, `question`, `answer` — powers "Ask Causal Twin" and the
dMRV copilot lookups (warranty narratives live here today).

## 9. Executive Dashboard

### kpis / kpi_drivers / recommendations
KPI: `code` UNIQUE, `label`, `value`, `trend`, `trend_up` (bool),
`confidence` (0–100). Driver: `kpi_id` FK (CASCADE), `driver_text`.
Recommendation: `code` UNIQUE, `title`, `impact`, `confidence`,
`risk` enum, `status` enum `pending|approved|under_review`, `decided_at`.

**Business rule:** executive KPIs are aggregates of the dealer funnel
(total leads, hot leads, avg booking prob) — they are computed, not invented.

## 10. AI Catalogue / PoC / Copilot / Simulation

- `solution_buckets` (`name` UNIQUE, `tag`) 1—N `solutions` (`bucket_id` FK RESTRICT, `name` UNIQUE).
- `poc_items`: shortlist referencing bucket names (`name` UNIQUE).
- `suggested_prompts`: `text` UNIQUE chips for the copilot UI.
- `simulation_runs`: `domain` enum (`auto_sales|dealer_allocation|collections|logistics_delay|credit_pricing`), `inputs`/`outputs` JSON, `confidence` (0–100 or NULL).
- Runtime: `copilot_sessions` 1—N `copilot_messages` (`role` enum user/assistant, `result` JSON payload).

---

## Synthetic volume requirements (defaults)

| Entity | Count | Scaling |
|---|---|---|
| dealers | 24 | `--scale` |
| dealer_leads | 4–8 per dealer (~151) | `--scale` |
| customer_twins | 48 | `--scale` |
| finance_products | 10 | `--scale` |
| collections agents / cases | 8 / 40 | `--scale` |
| warehouse_signals | 6 per panel × 3 | `--scale` |
| logistics_routes | 12 | `--scale` |
| carbon_credits | 20 | `--scale` |
| trust_decisions / rules | 20 / 6 | `--scale` |
| ai_agents / xr | 12 / 6 | `--scale` |
| causal nodes/edges | 12 / 12 (fixed topology) | fixed |
| mobility KPIs / QA | 8 / 14 | `--scale` |
| kpis / drivers / recs | 6 / 14 / 8 | `--scale` |
| buckets / solutions / poc | 9 / 3–5 each / 6 | `--scale` |
| prompts / sim runs / users | 10 / 25 / 5 | `--scale` |
| warranty claims *(future)* | 60 | `--scale` |
| notifications *(future)* | 50 | `--scale` |

Total seeded today: **549 rows across 28 tables** (+ 2 future CSVs).

## Assumptions

1. Currency is stored as display strings (`₹1.8 Cr`) because the UI renders them directly; a future phase can add numeric columns for analytics.
2. The causal graph topology is UX layout, not data — it stays fixed.
3. Warranty exists today as causal-graph nodes + Q&A; a dedicated `warranty_claims` table is planned (CSV already generated).
4. Notifications have no UI/table yet; the CSV contract is defined for Phase 2.
