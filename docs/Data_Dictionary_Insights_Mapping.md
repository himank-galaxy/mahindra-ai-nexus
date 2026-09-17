# Mahindra AI Nexus — Data Dictionary & Insights Mapping

**Scope:** this document covers exactly the **51 datasets** physically present under `/data/Mahindra_AI_Opportunity/Mahindra AI Nexus/data/synthetic/**/*.csv` — the Synthetic Data Factory's canonical output. For each one: its full column list with the primary key called out explicitly, which frontend screen(s) actually use it and how, and whether it feeds a predictive/causal model.

## Methodology & how to read this document

This document was produced by directly reading the backend schema, backend services/routes, and frontend route files — not by re-describing the original product specification (`Mahindra_AI_Nexus_Synthetic_Data_Factory.md`). One thing fell out of that process that materially shapes every entry below:

**These 51 CSVs are mirrored 1:1 into Postgres as the canonical runtime schema** — raw SQLAlchemy Core `Table` objects in `backend/app/database/runtime_schema.py` (`TABLE_SPECS`), one table per CSV, same column names and types. Nearly every screen in the app is served by an `Operational*Service` (or `DealerService`, `FinanceService`, `CollectionsService`, `TrustService`, `AiAgentService`) reading these tables directly via `runtime_tables[...]`. Every table entry below states plainly whether that live path actually reaches the screen it conceptually belongs to, verified by tracing `api/v1/router.py` → the route file → the service it imports → what that service actually queries (not assumed from naming) — and calls out, honestly, where a screen's displayed "AI" output is actually a static string, a client-side-only formula, an unwired endpoint, or a single-factor ratio rather than the evidence-weighted model the product spec describes.

**Out of scope for this document:** the codebase also contains (a) a separate, physically isolated "AI state" schema (`causal_replay_state`, `causal_scheduler_state`, `causal_ingestion_state`, `manufacturing_causal_runs`/`edges`, `telematics_causal_runs`/`edges`, `warranty_quality_evaluation_runs`/`warnings`/`warning_events`) that holds the live *output* of the PCMCI/LPCMCI causal-discovery pipeline and the warranty/quality early-warning engine — real, live, actively read by the Warranty & Quality screen, but not a CSV dataset; and (b) an older declarative ORM layer (`backend/app/models/*.py`, e.g. `Solution`/`SolutionBucket`, `PocItem`, `CopilotSession`/`CopilotMessage`) covering a few application-state features (catalogue, PoC shortlist, copilot chat history) — mostly dead code (defined but never created by any Alembic migration on Postgres, or wired to `return []`/raise-on-write stubs). Neither of these has a corresponding file in `data/synthetic/`, so neither gets its own entry here; where one of the 51 tables below is affected by them (e.g. a screen reading persisted causal-engine output instead of the raw CSV table), that's noted inline.

**Coverage:** 51 datasets across 8 domain groups, matching the platform's frontend routes (`dealer.tsx`, `warranty-quality.tsx`, `mobility-twin.tsx`, `finance.tsx`, `collections.tsx`, `logistics.tsx`, `circularity.tsx`, `xr.tsx`, `trust.tsx`, `agents.tsx`, `simulation.tsx`, `index.tsx`, `copilot.tsx`, `catalogue.tsx`).

## Table of contents

- **Section A — Master / Reference Data** (1–4): Regions, Cities, Vehicle Models, Dealers
- **Section B — Auto Sales & Dealer Funnel** (5–13): Customers, Leads, Followups, Test Drives, Bookings, Cancellations, Finance Applications, Allocations, Deliveries
- **Section C — Manufacturing, Warranty & Quality** (14–22): Plants, Production Lines, Machines, Suppliers, Supplier Lots, Production Batches, Service Events, Warranty Claims, Manufacturing Time-Series
- **Section D — Mobility Twin & Vehicle Telematics Causality** (23–24): Mobility Time Series, Vehicle Telematics Time Series
- **Section E — Finance & Collections** (25–31): Finance Products, Finance Customers, Loan Accounts, Payment History, Cross-Sell Events, Collection Cases, Collection Interactions
- **Section F — Logistics, Circularity & XR** (32–41): Routes, Warehouses, Shipments, Warehouse Events, ELV Assessments, RVSF Job Cards, dMRV Records, Carbon Credit Listings, XR Experiences, XR Sessions
- **Section G — Governance, Trust, Agents & Simulation** (42–49): Trust Decisions, Compliance Checks, Audit Events, Human Reviews, Action Outcomes, Recommendations, Agent Events, Agent Workflow Runs
- **Section H — Copilot** (50–51): Copilot Evaluation Questions, Suggested Prompts

---

# Section A — Master / Reference Data

### 1. Regions — `regions`
* **Description:** Top-level sales-geography master (e.g. North / South / East / West) that every operational record in the platform denormalizes a `region_id`/`region_name` pair against. Source is the Synthetic Data Factory generator (CSV `data/synthetic/master/regions.csv`) imported verbatim into Postgres. Business purpose: defines the geography dimension used for regional grouping/rollups and controls the relative weight the generator uses when distributing synthetic demand across regions.
* **Primary Key:** `region_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| region_id | TEXT (PK) | Stable region code; referenced as a foreign key by `cities`, `dealers`, `customers`, `leads`, `followups`, `test_drives`, `bookings`, `cancellations`, `finance_applications`, `allocations`, `deliveries`, and many other domain tables. |
| region_name | TEXT | Human-readable region label (e.g. "West") shown wherever region is displayed or grouped. |
| generation_weight | DOUBLE | Relative synthetic-generation probability weight for this region; governs how much record volume the Synthetic Data Factory assigns here. Generator-tuning metadata only, not a live business metric. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Simulation Center (`frontend/src/routes/simulation.tsx`, linked from the Executive Overview quick links)
  * **Insight/Metric Displayed:** "Region" scenario-input dropdown for the Auto Sales / Dealer Allocation simulators.
  * **Data Mapping:** `ReferenceRepository.list_regions()` (`backend/app/repositories/reference.py`) reads `regions.region_name` ordered alphabetically, served via `GET /simulations/meta` (`SimulationService.get_meta`), consumed by `useSimulationMeta()`. The simulation formulas themselves (`app/ai/simulation/auto_sales.py`, `dealer_allocation.py`) do not read any other `regions` column — they run on the user-selected region string plus manual numeric inputs.
* Within the Dealer Cockpit (`dealer.tsx`) and Executive Overview (`index.tsx`) specifically: `regions` is not queried directly — those screens read the denormalized `region_id`/`region_name` copies already carried on `dealers`, `leads`, `bookings`, etc.

---

### 2. Cities — `cities`
* **Description:** Second-level geography master (cities within each region) that dealers/customers/leads/etc. denormalize a `city_id`/`city_name` pair against. Source is the Synthetic Data Factory generator (CSV `data/synthetic/master/cities.csv`) imported into Postgres. Business purpose: normalizes city identity and controls the relative weight the generator uses to spread synthetic demand across cities within a region.
* **Primary Key:** `city_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| city_id | TEXT (PK) | Stable city code; referenced as a foreign key by `dealers`, `customers`, `leads`, and every other city-scoped operational table. |
| city_name | TEXT | Human-readable city label. |
| region_id | TEXT (FK → regions.region_id) | Parent region this city belongs to. |
| region_name | TEXT | Denormalized parent region label, avoiding a join back to `regions`. |
| generation_weight_within_region | DOUBLE | Relative synthetic-generation weight for this city among its region's cities. Generator-tuning metadata only. |

#### Screen-by-Screen Insights Mapping
* Not currently surfaced in any frontend screen. No service under `backend/app/services` or `backend/app/ai` queries `runtime_tables["cities"]` directly — the Dealer Cockpit, Executive Overview, and Simulation Center all read the denormalized `city_id`/`city_name` columns already carried on `dealers`, `leads`, `bookings`, etc., so a live join back to the `cities` master table never occurs today.

---

### 3. Vehicle Models — `vehicle_models`
* **Description:** Master catalogue of Mahindra vehicle models (e.g. XUV700, Scorpio-N) with baseline commercial and generator-tuning parameters. Source is the Synthetic Data Factory generator (CSV `data/synthetic/master/vehicle_models.csv`) imported into Postgres. Business purpose: anchors every sales-funnel/manufacturing record's model identity and supplies the reference price used to value leads and bookings.
* **Primary Key:** `vehicle_model_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| vehicle_model_id | TEXT (PK) | Stable model code referenced as a foreign key across the sales-funnel and manufacturing/circularity tables. |
| model_name | TEXT | Human-readable model name (e.g. "XUV700"). |
| segment | TEXT | Vehicle market segment/category classification. |
| base_price | BIGINT | Reference retail base price in INR; used as the vehicle's opportunity/deal value wherever a monetary figure is needed for a lead or booking. |
| currency | TEXT | Currency code for `base_price` (INR). |
| gross_margin_pct | DOUBLE | Typical gross margin percentage for the model; generator/finance-tuning parameter. |
| typical_lead_to_booking_rate | DOUBLE | Baseline lead→booking conversion probability used by the generator to calibrate synthetic funnel outcomes for this model. |
| typical_cancellation_rate | DOUBLE | Baseline booking cancellation probability used by the generator for this model. |
| typical_finance_share | DOUBLE | Baseline share of bookings expected to use finance assistance for this model. |
| production_complexity | DOUBLE | Manufacturing-side complexity/effort index for this model (feeds Manufacturing-domain generation). |
| generation_weight | DOUBLE | Relative synthetic-generation weight controlling how often this model appears across generated records. |
| data_origin | TEXT | Synthetic-data provenance metadata; not surfaced in UI. |
| generator_version | TEXT | Synthetic-data generator/reproducibility version tag; not surfaced in UI. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Dealer Revenue & Customer Journey Optimizer (`dealer.tsx`) — Lead Prioritization table
  * **Insight/Metric Displayed:** "Vehicle" column and "Revenue" (deal value) column per lead.
  * **Data Mapping:** `DealerService.list_leads()` joins `leads.vehicle_model_id = vehicle_models.vehicle_model_id` and reads `vehicle_models.base_price`, formatted to ₹ Cr/L, as the lead's displayed `revenue`; `vehicle_model_name` (denormalized on `leads`) is shown directly as "Vehicle."
* **Screen Name:** Simulation Center (`simulation.tsx`)
  * **Insight/Metric Displayed:** "Model" scenario-input dropdown.
  * **Data Mapping:** `ReferenceRepository.list_vehicle_models()` reads `vehicle_models.model_name` ordered alphabetically, served via `GET /simulations/meta`, consumed by `useSimulationMeta()`.
* `segment`, `currency`, `gross_margin_pct`, `typical_lead_to_booking_rate`, `typical_cancellation_rate`, `typical_finance_share`, `production_complexity`, `generation_weight` are not read by any live Dealer Cockpit / Executive Overview service found in this review — not currently surfaced there.

---

### 4. Dealers — `dealers`
* **Description:** Dealer identity and fixed operating-capacity master; stays stable day-to-day while operational event tables (leads, bookings, etc.) change. Source is the Synthetic Data Factory generator (CSV `data/synthetic/master/dealers.csv`) imported into Postgres. Business purpose: anchors the entire Dealer Revenue Optimizer cockpit — every lead/followup/test-drive/booking/cancellation/finance/allocation/delivery record carries this `dealer_id` as a foreign key.
* **Primary Key:** `dealer_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| dealer_id | TEXT (PK) | Stable dealer code (join key for the entire auto sales funnel). |
| dealer_name | TEXT | Dealership display name. |
| city_id | TEXT (FK → cities.city_id) | City the dealership operates in. |
| city_name | TEXT | Denormalized city label. |
| region_id | TEXT (FK → regions.region_id) | Region the dealership operates in. |
| region_name | TEXT | Denormalized region label. |
| dealer_tier | TEXT | Dealer classification tier (e.g. size/performance banding). |
| monthly_lead_capacity | BIGINT | Baseline monthly lead-intake capacity used by the generator. |
| monthly_test_drive_capacity | BIGINT | Baseline monthly test-drive throughput capacity. |
| monthly_booking_capacity | BIGINT | Baseline monthly booking throughput capacity. |
| sales_consultants | BIGINT | Headcount of sales consultants at the dealership. |
| service_bays | BIGINT | Number of service bays; used as the capacity denominator for the cockpit's bay-utilization KPI. |
| followup_sla_hours | BIGINT | Contractual/target hours within which a lead follow-up should occur. |
| active | BOOLEAN | Whether the dealer is currently active; the live dealer list is filtered to `active = true`. |
| data_origin | TEXT | Synthetic-data provenance metadata; not surfaced in UI. |
| generator_version | TEXT | Synthetic-data generator/reproducibility version tag; not surfaced in UI. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Dealer Revenue & Customer Journey Optimizer (`dealer.tsx`)
  * **Insight/Metric Displayed:** Dealer selector dropdown.
  * **Data Mapping:** `GET /dealers` → `DealerService.list_dealers()`: `SELECT * FROM dealers WHERE active = true ORDER BY dealer_name`; `dealer_id`/`dealer_name` populate the selector.
  * **Insight/Metric Displayed:** KPI tiles "Leads today," "Hot leads," "Test drives pending," "Booking probability," "Revenue at risk," "Follow-up leakage," "Bay utilization."
  * **Data Mapping:** `dealer_name` labels the panel; `dealer_id` is the join key for all the count/sum aggregates over `leads`, `test_drives`, `bookings`, `cancellations`, `service_events` (see those tables' entries); `service_bays` is the capacity denominator for "Bay utilization" = `SUM(service_events.service_duration_hours) / (elapsed_hours × dealers.service_bays) × 100`, capped at 100%.
  * **Insight/Metric Displayed:** "AI Dealer Coach" panel.
  * **Data Mapping:** A real endpoint `GET /dealers/{dealer_code}/coach` (`DealerService.get_coach`) exists and would surface `dealers.revenue_at_risk`-style content built from the top-ranked lead, but the panel in `dealer.tsx` is currently hard-coded static text and never calls this endpoint — **not wired**.
* `dealer_tier`, `monthly_lead_capacity`, `monthly_test_drive_capacity`, `monthly_booking_capacity`, `sales_consultants`, `followup_sla_hours` are stored but not read by the live `DealerService` — not currently surfaced.
* **Legacy ORM note:** `backend/app/models/dealer.py` defines ORM classes `Dealer`/`DealerLead` (wrapped by `DealerRepository` in `backend/app/repositories/dealer.py`) that store a *second synthetic copy* of the dashboard numbers directly as columns (`leads`, `hot_leads`, `booking_prob`, `revenue_at_risk` string, `leakage_pct`, `bay_util_pct`) — exactly the pattern the product spec's non-negotiable rule forbids. `DealerRepository` is exported from `repositories/__init__.py` but is not imported by any API route or service; the live `/dealers` endpoints are served entirely by `DealerService` against `runtime_tables["dealers"]`. **This legacy ORM path is dead code.**

---

# Section B — Auto Sales & Dealer Funnel

### 5. Customers — `customers`
* **Description:** Customer master representing individuals who have engaged with Mahindra's auto sales funnel, with demographic/preference attributes. Source is the Synthetic Data Factory generator (CSV `data/synthetic/auto/customers.csv`) imported into Postgres. Business purpose: captures budget, model preference, finance/exchange intent and purchase horizon, referenced as `customer_id` by `leads`, `followups`, `test_drives`, `bookings`, `cancellations`, `finance_applications`, `allocations`, and `deliveries`.
* **Primary Key:** `customer_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| customer_id | TEXT (PK) | Stable customer code; a customer can generate multiple leads (see `leads.customer_lead_number`). |
| region_id | TEXT (FK → regions.region_id) | Customer's home region. |
| region_name | TEXT | Denormalized region label. |
| city_id | TEXT (FK → cities.city_id) | Customer's home city. |
| city_name | TEXT | Denormalized city label. |
| preferred_vehicle_model_id | TEXT (FK → vehicle_models.vehicle_model_id) | The vehicle model the customer has expressed preference for. |
| preferred_vehicle_model_name | TEXT | Denormalized preferred-model label. |
| budget_band | TEXT | Customer's declared/inferred budget bracket; a driver of the spec's `budget_fit`/`latent_purchase_intent` scoring on `leads`. |
| purchase_horizon_days | BIGINT | Expected number of days until purchase; an urgency signal. |
| finance_required | BOOLEAN | Whether the customer indicated they need financing. |
| exchange_vehicle | BOOLEAN | Whether the customer has a vehicle to exchange/trade in. |
| customer_segment | TEXT | Customer segmentation classification (e.g. persona/value tier). |
| created_at | TIMESTAMPTZ | Customer record creation timestamp. |
| data_origin | TEXT | Synthetic-data provenance metadata; not surfaced in UI. |
| generator_version | TEXT | Synthetic-data generator/reproducibility version tag; not surfaced in UI. |

#### Screen-by-Screen Insights Mapping
* Not currently surfaced in any frontend screen. No service under `backend/app/services` or `backend/app/ai` reads `runtime_tables["customers"]`. The Dealer Cockpit's Lead Prioritization table displays `leads.customer_id` directly as the "Lead" name rather than joining to this customers master, so `budget_band`, `purchase_horizon_days`, `finance_required`, `exchange_vehicle`, `customer_segment` are generated and stored but not exposed anywhere live yet.

---

### 6. Leads — `leads`
* **Description:** Core lead-generation record — one row per sales opportunity, denormalized with dealer/region/city/vehicle context plus the generator's intent-scoring sub-signals. Source is the Synthetic Data Factory generator (CSV `data/synthetic/auto/leads.csv`) imported into Postgres. Business purpose: the seed event for the entire funnel (followups → test drives → bookings) and the primary input to the dealer next-best-action / lead-prioritization logic.
* **Primary Key:** `lead_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| lead_id | TEXT (PK) | Stable lead code. |
| customer_id | TEXT (FK → customers.customer_id) | Customer who generated this lead; also the value shown as the lead's display name in the Dealer Cockpit. |
| customer_lead_number | BIGINT | Sequence number of this lead for the given customer (a customer may generate several leads over time). |
| dealer_id | TEXT (FK → dealers.dealer_id) | Dealer this lead is assigned to. |
| dealer_name | TEXT | Denormalized dealer label. |
| region_id | TEXT (FK → regions.region_id) | Denormalized region of the lead. |
| region_name | TEXT | Denormalized region label. |
| city_id | TEXT (FK → cities.city_id) | Denormalized city of the lead. |
| city_name | TEXT | Denormalized city label. |
| vehicle_model_id | TEXT (FK → vehicle_models.vehicle_model_id) | Vehicle model of interest for this lead. |
| vehicle_model_name | TEXT | Denormalized model label; displayed as "Vehicle" in the Lead Prioritization table. |
| source_channel | TEXT | Lead acquisition channel (Website, Dealer Walk-in, Campaign, Referral, Aggregator, WhatsApp, Call Center, Event per the spec). |
| budget_fit | DOUBLE | Sub-score: how well the customer's budget fits this vehicle's price; one of the five weighted inputs to `latent_purchase_intent`. |
| engagement_score | DOUBLE | Sub-score of customer engagement; displayed directly (×100) as the "Score" column in the Lead Prioritization table. |
| urgency_score | DOUBLE | Sub-score of purchase urgency; one of the weighted inputs to `latent_purchase_intent`. |
| model_interest_score | DOUBLE | Sub-score of interest in the specific model; one of the weighted inputs to `latent_purchase_intent`. |
| source_quality | DOUBLE | Sub-score reflecting the quality of the acquisition channel; one of the weighted inputs to `latent_purchase_intent`. |
| latent_purchase_intent | DOUBLE | Composite intent score (`0.30·budget_fit + 0.20·model_interest + 0.20·engagement + 0.15·source_quality + 0.15·urgency + noise` per the generation spec); the primary ranking key for lead prioritization and the "hot lead" threshold test (≥0.65), and displayed (×100) as "Prob." |
| lead_created_at | TIMESTAMPTZ | Lead creation timestamp; secondary sort key (newest-first) in the Lead Prioritization table. |
| data_origin | TEXT | Synthetic-data provenance metadata; not surfaced in UI. |
| generator_version | TEXT | Synthetic-data generator/reproducibility version tag; not surfaced in UI. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Dealer Revenue & Customer Journey Optimizer (`dealer.tsx`) — Lead Prioritization table
  * **Insight/Metric Displayed:** Full lead list per dealer, with Lead / Vehicle / Score / Prob. / Recommended action / Revenue / Status columns.
  * **Data Mapping:** `GET /dealers/{dealer_code}/leads` → `DealerService.list_leads()`: `SELECT leads.*, vehicle_models.base_price FROM leads JOIN vehicle_models ON leads.vehicle_model_id = vehicle_models.vehicle_model_id WHERE dealer_id = :dealer_code ORDER BY latent_purchase_intent DESC, lead_created_at DESC`. "Lead" = `customer_id`; "Vehicle" = `vehicle_model_name`; "Score" = `ROUND(engagement_score × 100)`; "Prob." = `ROUND(latent_purchase_intent × 100)`; "Revenue" = formatted `vehicle_models.base_price`.
  * **Insight/Metric Displayed:** KPI tiles "Leads today" and "Hot leads."
  * **Data Mapping:** "Leads today" = `COUNT(leads)` grouped by `dealer_id`; "Hot leads" = `COUNT(leads) FILTER (WHERE latent_purchase_intent >= 0.65)` grouped by `dealer_id`.
  * **Insight/Metric Displayed:** KPI tile "Booking probability."
  * **Data Mapping:** `COUNT(bookings)/COUNT(leads) × 100` grouped by `dealer_id` — `leads` is the denominator.
  * **Insight/Metric Displayed:** Row action buttons (Generate Pitch, Send WhatsApp, Schedule Test Drive, Mark Converted).
  * **Data Mapping:** "Generate Pitch" (`POST /dealers/{dealer_code}/leads/{lead_id}/pitch`) returns a canned pitch string templated from `vehicle_model_name`. The other three call real endpoints (`POST /dealer-leads/{lead_id}/message|test-drive|convert`) that intentionally raise `DomainValidationError("unsupported_legacy_dealer_mutation")` — the canonical schema has no lossless column to write a free-text WhatsApp send, slot string, or conversion event onto, so these buttons never mutate `leads` or any funnel table despite the UI showing a success toast.
* `budget_fit`, `urgency_score`, `model_interest_score`, `source_quality`, `source_channel`, `customer_lead_number` feed `latent_purchase_intent` at generation time but are not individually read by `DealerService` — not currently surfaced as discrete fields.

#### Predictive Modeling Mapping
* **Target Variable:** The Lead Prioritization table's row order, `status` label, and `action` (next-best-action) recommendation text.
* **Input Features:**
  * `latent_purchase_intent` (leads) — primary sort key (descending); ranks which leads surface first/highest-priority, and is displayed as "Prob."
  * `lead_created_at` (leads) — secondary sort tiebreaker (newest first).
  * `engagement_score` (leads) — displayed as "Score," driving the UI's success/info tone threshold (>85).
  * `followups.completed` (joined by `lead_id`) — a completed follow-up promotes the lead to status "Follow-up completed" / action "Continue recorded follow-up."
  * `test_drives` row presence and `test_drives.completed` (joined by `lead_id`) — presence promotes to "Test drive requested" / "Confirm scheduled test drive"; `completed = true` promotes to "Test drive completed" / "Follow up after completed test drive."
  * `bookings` row presence (joined by `lead_id`) — highest-priority terminal rule, promoting to status "Converted" / action "Booking recorded."
  * This is a deterministic funnel-stage rule policy over actually recorded evidence (not a trained ML ranker or a stored label), approximating the spec's §36 "Dealer next-best-action ground truth" using genuine downstream records rather than a seeded recommendation string.

---

### 7. Followups — `followups`
* **Description:** One row per dealer follow-up attempt against a lead (call/WhatsApp/email/etc.), tracking SLA adherence and customer response. Source is the Synthetic Data Factory generator (CSV `data/synthetic/auto/followups.csv`) imported into Postgres. Business purpose: evidence base for follow-up-quality signals that flow into `test_drives`/`bookings`/`cancellations` and into the lead-status rule policy.
* **Primary Key:** `followup_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| followup_id | TEXT (PK) | Stable follow-up attempt code. |
| lead_id | TEXT (FK → leads.lead_id) | Lead this follow-up was made against. |
| customer_id | TEXT (FK → customers.customer_id) | Customer being followed up with. |
| dealer_id | TEXT (FK → dealers.dealer_id) | Dealer performing the follow-up. |
| dealer_name | TEXT | Denormalized dealer label. |
| region_id | TEXT (FK → regions.region_id) | Denormalized region. |
| region_name | TEXT | Denormalized region label. |
| city_id | TEXT (FK → cities.city_id) | Denormalized city. |
| city_name | TEXT | Denormalized city label. |
| vehicle_model_id | TEXT (FK → vehicle_models.vehicle_model_id) | Denormalized model of interest. |
| vehicle_model_name | TEXT | Denormalized model label. |
| attempt_number | BIGINT | Sequence number of this follow-up attempt for the lead. |
| channel | TEXT | Follow-up communication channel (call, WhatsApp, email, etc.). |
| scheduled_at | TIMESTAMPTZ | When the follow-up was scheduled. |
| completed | BOOLEAN | Whether the follow-up attempt was completed; used by `DealerService.list_leads()` to detect any completed follow-up per lead. |
| completed_at | TIMESTAMPTZ | When the follow-up was completed. |
| dealer_sla_hours | DOUBLE | The dealer's follow-up SLA target in hours for this attempt. |
| within_sla | BOOLEAN | Whether the follow-up occurred within the SLA window. |
| customer_responded | BOOLEAN | Whether the customer responded to this follow-up. |
| response_time_minutes | DOUBLE | Minutes elapsed before the customer responded. |
| response_at | TIMESTAMPTZ | Timestamp of the customer's response. |
| followup_status | TEXT | Overall status label for the follow-up attempt. |
| data_origin | TEXT | Synthetic-data provenance metadata; not surfaced in UI. |
| generator_version | TEXT | Synthetic-data generator/reproducibility version tag; not surfaced in UI. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Dealer Revenue & Customer Journey Optimizer (`dealer.tsx`) — Lead Prioritization row status/action.
  * **Data Mapping:** `DealerService.list_leads()` checks `followups.completed = true` (filtered to the dealer's `lead_id`s) to detect whether a lead has any completed follow-up (see `leads` → Predictive Modeling Mapping).
* Despite the product name "Follow-up leakage," the `dealer.tsx` KPI tile labeled "Follow-up leakage" is actually computed from `cancellations`/`bookings` counts, **not** from `followups.within_sla` or `followups.completed` — see the `cancellations` entry.
* `attempt_number`, `channel`, `scheduled_at`, `dealer_sla_hours`, `within_sla`, `customer_responded`, `response_time_minutes`, `response_at`, `followup_status` are stored but not individually read by `DealerService` — not currently surfaced as discrete fields.

---

### 8. Test Drives — `test_drives`
* **Description:** One row per requested/completed test drive, denormalized with the originating lead's funnel signals (follow-up counts, intent). Source is the Synthetic Data Factory generator (CSV `data/synthetic/auto/test_drives.csv`) imported into Postgres. Business purpose: the evidence base the spec requires "Test Drive Completion KPI" to be calculated from, and a Dealer Cockpit capacity signal.
* **Primary Key:** `test_drive_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| test_drive_id | TEXT (PK) | Stable test-drive code. |
| lead_id | TEXT (FK → leads.lead_id) | Lead this test drive belongs to. |
| customer_id | TEXT (FK → customers.customer_id) | Customer taking the test drive. |
| dealer_id | TEXT (FK → dealers.dealer_id) | Dealer hosting the test drive; used to compute "Test drives pending." |
| dealer_name | TEXT | Denormalized dealer label. |
| region_id | TEXT (FK → regions.region_id) | Denormalized region. |
| region_name | TEXT | Denormalized region label. |
| city_id | TEXT (FK → cities.city_id) | Denormalized city. |
| city_name | TEXT | Denormalized city label. |
| vehicle_model_id | TEXT (FK → vehicle_models.vehicle_model_id) | Model being test-driven. |
| vehicle_model_name | TEXT | Denormalized model label. |
| latent_purchase_intent | DOUBLE | Denormalized copy of the lead's intent score at test-drive time. |
| request_probability | DOUBLE | Generator-side probability that this lead would request a test drive (generation input, not a live UI value). |
| followup_attempt_count | BIGINT | Number of follow-up attempts recorded for the lead by this point. |
| completed_followup_count | BIGINT | Number of those follow-ups that were completed. |
| responded_followup_count | BIGINT | Number of those follow-ups the customer responded to. |
| any_within_sla_followup | BOOLEAN | Whether any follow-up for the lead met SLA. |
| requested_at | TIMESTAMPTZ | When the test drive was requested. |
| scheduled_at | TIMESTAMPTZ | When the test drive was scheduled. |
| wait_hours | DOUBLE | Hours between request and scheduled slot. |
| reminder_sent | BOOLEAN | Whether a reminder was sent ahead of the test drive. |
| high_intent | BOOLEAN | Generator flag marking this as a high-intent test drive. |
| long_wait | BOOLEAN | Generator flag marking an unusually long wait. |
| completion_probability | DOUBLE | Generator-side probability this test drive would complete (generation input). |
| status | TEXT | Test-drive status: REQUESTED, SCHEDULED, COMPLETED, NO_SHOW, CANCELLED, or RESCHEDULED per the spec. |
| completed | BOOLEAN | Whether the test drive was completed; used in the "Test drives pending" KPI filter. |
| completed_at | TIMESTAMPTZ | Completion timestamp. |
| feedback_score | DOUBLE | Customer feedback score captured after the test drive. |
| rescheduled_for | TIMESTAMPTZ | New slot if the test drive was rescheduled. |
| data_origin | TEXT | Synthetic-data provenance metadata; not surfaced in UI. |
| generator_version | TEXT | Synthetic-data generator/reproducibility version tag; not surfaced in UI. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Dealer Revenue & Customer Journey Optimizer (`dealer.tsx`)
  * **Insight/Metric Displayed:** KPI tile "Test drives pending."
  * **Data Mapping:** `COUNT(test_drives) FILTER (WHERE completed = false AND status != 'NO_SHOW')` grouped by `dealer_id`.
  * **Insight/Metric Displayed:** Lead Prioritization row status ("Test drive requested" / "Test drive completed").
  * **Data Mapping:** Presence of a `test_drives` row for a `lead_id`, and its `completed` flag, feed the status/action rule (see `leads` → Predictive Modeling Mapping).
  * **Insight/Metric Displayed:** "Schedule Test Drive" modal button.
  * **Data Mapping:** `POST /dealer-leads/{lead_id}/test-drive` raises `DomainValidationError("unsupported_legacy_dealer_mutation")` — it does not insert a `test_drives` row; the free-text slot chosen in the UI (e.g. "Sat 11:00") has no canonical timestamp column to map onto.
* `latent_purchase_intent`, `request_probability`, `followup_attempt_count`, `completed_followup_count`, `responded_followup_count`, `any_within_sla_followup`, `requested_at`, `scheduled_at`, `wait_hours`, `reminder_sent`, `high_intent`, `long_wait`, `completion_probability`, `feedback_score`, `rescheduled_for` are generator-computed but not individually read by `DealerService` — not currently surfaced as discrete fields.

---

### 9. Bookings — `bookings`
* **Description:** One row per vehicle booking confirmed from a lead, carrying the funnel-quality signals (test-drive completion, follow-up quality, finance assistance) behind the booking plus commercial amounts and the promised delivery commitment. Source is the Synthetic Data Factory generator (CSV `data/synthetic/auto/bookings.csv`) imported into Postgres. Business purpose: the central conversion fact table for both the Dealer Cockpit and the Executive Overview KPIs.
* **Primary Key:** `booking_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| booking_id | TEXT (PK) | Stable booking code. |
| lead_id | TEXT (FK → leads.lead_id) | Originating lead. |
| customer_id | TEXT (FK → customers.customer_id) | Booking customer. |
| test_drive_id | TEXT (FK → test_drives.test_drive_id) | Test drive that preceded this booking, if any. |
| dealer_id | TEXT (FK → dealers.dealer_id) | Booking dealer; used across most Dealer Cockpit and Overview KPIs. |
| dealer_name | TEXT | Denormalized dealer label. |
| region_id | TEXT (FK → regions.region_id) | Denormalized region. |
| region_name | TEXT | Denormalized region label. |
| city_id | TEXT (FK → cities.city_id) | Denormalized city. |
| city_name | TEXT | Denormalized city label. |
| vehicle_model_id | TEXT (FK → vehicle_models.vehicle_model_id) | Booked model. |
| vehicle_model_name | TEXT | Denormalized model label. |
| vehicle_base_price_inr | BIGINT | Denormalized copy of the model's base price at booking time; summed for the Executive Overview's "Predicted Revenue Uplift" KPI. |
| source_channel | TEXT | Acquisition channel that produced this booking. |
| latent_purchase_intent | DOUBLE | Denormalized copy of the lead's intent score at booking time. |
| completed_test_drive | BOOLEAN | Whether a test drive was completed before this booking; used for the Overview's "Dealer Conversion Uplift" KPI. |
| good_followup | BOOLEAN | Generator flag: whether follow-up quality was assessed as good. |
| finance_assisted | BOOLEAN | Whether the booking used finance assistance. |
| finance_preapproval_signal | BOOLEAN | Whether a finance pre-approval signal was present at booking. |
| exchange_assisted | BOOLEAN | Whether an exchange-vehicle offer assisted the booking. |
| long_test_drive_wait | BOOLEAN | Generator flag: whether the preceding test-drive wait was long. |
| booking_probability | DOUBLE | Generator-side probability this booking would occur (generation input). |
| booking_amount_inr | BIGINT | Actual booking amount collected in INR. |
| booking_timestamp | TIMESTAMPTZ | When the booking was made. |
| promised_delivery_date | TIMESTAMPTZ | Delivery date promised to the customer at booking; the baseline `deliveries.delay_days` is measured against. |
| booking_status | TEXT | Booking status: ACTIVE, CANCELLED, DELIVERED, or EXPIRED per the spec. |
| data_origin | TEXT | Synthetic-data provenance metadata; not surfaced in UI. |
| generator_version | TEXT | Synthetic-data generator/reproducibility version tag; not surfaced in UI. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Dealer Revenue & Customer Journey Optimizer (`dealer.tsx`)
  * **Insight/Metric Displayed:** KPI tile "Booking probability."
  * **Data Mapping:** `COUNT(bookings)/COUNT(leads) × 100` grouped by `dealer_id`.
  * **Insight/Metric Displayed:** KPI tile "Follow-up leakage."
  * **Data Mapping:** `COUNT(cancellations)/COUNT(bookings) × 100` grouped by `dealer_id` — `bookings` is the denominator.
  * **Insight/Metric Displayed:** Lead Prioritization row status "Converted" / action "Booking recorded."
  * **Data Mapping:** Presence of a `bookings` row for the `lead_id` (see `leads` → Predictive Modeling Mapping).
* **Screen Name:** Executive Overview (`index.tsx`) — KPI grid, via `GET /overview/kpis` → `OperationalOverviewService.list_kpis()`
  * **Insight/Metric Displayed:** "Predicted Revenue Uplift."
  * **Data Mapping:** `value = SUM(vehicle_base_price_inr) × 0.075` (a 7.5% scenario multiplier over total booked vehicle value); `confidence` = `(COUNT(bookings) − COUNT(cancellations)) / COUNT(bookings)` retention ratio; drivers cite `COUNT(bookings)` and `SUM(vehicle_base_price_inr)`.
  * **Insight/Metric Displayed:** "Dealer Conversion Uplift."
  * **Data Mapping:** `value = COUNT(bookings) FILTER (WHERE completed_test_drive = true) / COUNT(bookings)`; drivers cite both counts.
* `test_drive_id`, `source_channel`, `latent_purchase_intent`, `good_followup`, `finance_preapproval_signal`, `exchange_assisted`, `long_test_drive_wait`, `booking_probability`, `booking_status`, `promised_delivery_date` are not individually surfaced as discrete fields in either screen — used only implicitly through the aggregates above.

---

### 10. Cancellations — `cancellations`
* **Description:** One row per cancelled booking, carrying the finance/wait-time/follow-up signals behind the cancellation plus refund economics. Source is the Synthetic Data Factory generator (CSV `data/synthetic/auto/cancellations.csv`) imported into Postgres. Business purpose: powers the Dealer Cockpit's "revenue at risk"/"leakage" KPIs and the Executive Overview's leakage-prevented KPI and cancellation-intervention recommendation. Per the spec, cancellation risk is meant to be model-derived rather than a seeded number.
* **Primary Key:** `cancellation_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| cancellation_id | TEXT (PK) | Stable cancellation record code. |
| booking_id | TEXT (FK → bookings.booking_id) | Booking that was cancelled. |
| lead_id | TEXT (FK → leads.lead_id) | Originating lead. |
| customer_id | TEXT (FK → customers.customer_id) | Customer who cancelled. |
| finance_application_id | TEXT (FK → finance_applications.finance_application_id) | Related finance application, if the cancellation involved one. |
| finance_status | TEXT | Denormalized finance-application status at cancellation time. |
| finance_risk_band | TEXT | Denormalized finance risk band. |
| finance_approval_tat_hours | DOUBLE | Denormalized finance approval turnaround time. |
| dealer_id | TEXT (FK → dealers.dealer_id) | Dealer of the cancelled booking; used for "Revenue at risk" and "Follow-up leakage" KPIs. |
| dealer_name | TEXT | Denormalized dealer label. |
| region_id | TEXT (FK → regions.region_id) | Denormalized region. |
| region_name | TEXT | Denormalized region label. |
| city_id | TEXT (FK → cities.city_id) | Denormalized city. |
| city_name | TEXT | Denormalized city label. |
| vehicle_model_id | TEXT (FK → vehicle_models.vehicle_model_id) | Denormalized model. |
| vehicle_model_name | TEXT | Denormalized model label. |
| good_followup | BOOLEAN | Denormalized follow-up-quality flag at cancellation time. |
| long_test_drive_wait | BOOLEAN | Denormalized long-wait flag. |
| promised_delivery_wait_days | DOUBLE | Days the customer was waiting against the promised delivery date at cancellation. |
| cancellation_probability | DOUBLE | Generator-side probability this booking would be cancelled (generation input). |
| cancellation_reason | TEXT | One of FINANCE_REJECTED, FINANCE_TAT, DELIVERY_WAIT, COMPETITOR_OFFER, PRICE, MODEL_CHANGE, DEALER_FOLLOWUP, CUSTOMER_CHANGE, or OTHER per the spec; the Overview's "Address leading cancellation reason" recommendation groups on this column. |
| cancelled_at | TIMESTAMPTZ | Cancellation timestamp. |
| booking_amount_inr | BIGINT | Original booking amount at risk; summed for "Revenue at risk" (Dealer Cockpit) and "Leakage Prevented" (Overview). |
| refund_amount_inr | BIGINT | Amount refunded to the customer. |
| retained_amount_inr | BIGINT | Amount the dealer/OEM retained from the booking. |
| cancellation_status | TEXT | Processing status of the cancellation itself. |
| data_origin | TEXT | Synthetic-data provenance metadata; not surfaced in UI. |
| generator_version | TEXT | Synthetic-data generator/reproducibility version tag; not surfaced in UI. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Dealer Revenue & Customer Journey Optimizer (`dealer.tsx`)
  * **Insight/Metric Displayed:** KPI tile "Revenue at risk."
  * **Data Mapping:** `SUM(booking_amount_inr)` grouped by `dealer_id`, formatted to ₹ Cr/L.
  * **Insight/Metric Displayed:** KPI tile "Follow-up leakage."
  * **Data Mapping:** `COUNT(cancellations)/COUNT(bookings) × 100` grouped by `dealer_id`.
* **Screen Name:** Executive Overview (`index.tsx`), via `OperationalOverviewService`
  * **Insight/Metric Displayed:** "Leakage Prevented" KPI.
  * **Data Mapping:** `value = SUM(booking_amount_inr) × 0.35` (a 35% recoverable-scenario multiplier over cancelled booking value); `confidence` reuses the booking-retention ratio from `bookings`.
  * **Insight/Metric Displayed:** "Address leading cancellation reason: {Reason}" recommendation card.
  * **Data Mapping:** `SELECT cancellation_reason, COUNT(*) FROM cancellations GROUP BY cancellation_reason ORDER BY COUNT(*) DESC LIMIT 1` identifies the leading reason; impact text cites that reason's row count vs. total cancellations and `SUM(booking_amount_inr)` exposed; confidence/risk derive from that reason's share of all cancellations.
* `finance_application_id`, `finance_status`, `finance_risk_band`, `finance_approval_tat_hours`, `good_followup`, `long_test_drive_wait`, `promised_delivery_wait_days`, `cancellation_probability`, `refund_amount_inr`, `retained_amount_inr`, `cancellation_status` are not individually surfaced as discrete fields — used only implicitly through the aggregates above.

---

### 11. Finance Applications (Auto) — `finance_applications`
* **Description:** One row per auto-finance application tied to a booking, capturing the underwriting decision, risk/income banding, and turnaround time. Source is the Synthetic Data Factory generator (CSV `data/synthetic/auto/finance_applications.csv`) imported into Postgres. Business purpose: feeds the Executive Overview's finance-risk KPI and finance-intervention recommendation. (This is the auto-finance path tied to `bookings`; distinct from the standalone retail `finance_customers`/`loan_accounts` domain tables in Section E.)
* **Primary Key:** `finance_application_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| finance_application_id | TEXT (PK) | Stable application code. |
| booking_id | TEXT (FK → bookings.booking_id) | Booking this application is financing. |
| lead_id | TEXT (FK → leads.lead_id) | Originating lead. |
| customer_id | TEXT (FK → customers.customer_id) | Applicant. |
| dealer_id | TEXT (FK → dealers.dealer_id) | Dealer facilitating the application. |
| dealer_name | TEXT | Denormalized dealer label. |
| region_id | TEXT (FK → regions.region_id) | Denormalized region. |
| region_name | TEXT | Denormalized region label. |
| city_id | TEXT (FK → cities.city_id) | Denormalized city. |
| city_name | TEXT | Denormalized city label. |
| vehicle_model_id | TEXT (FK → vehicle_models.vehicle_model_id) | Denormalized model being financed. |
| vehicle_model_name | TEXT | Denormalized model label. |
| submitted_at | TIMESTAMPTZ | Application submission timestamp. |
| decision_at | TIMESTAMPTZ | Underwriting decision timestamp. |
| requested_amount_inr | BIGINT | Loan amount requested. |
| approved_amount_inr | DOUBLE | Loan amount actually approved. |
| status | TEXT | APPROVED, REJECTED, MANUAL_REVIEW, or PENDING per the spec; grouped/counted for the Overview KPI and recommendation. |
| risk_band | TEXT | Underwriting risk classification. |
| income_band | TEXT | Applicant income bracket. |
| bureau_like_score_synthetic | BIGINT | Synthetic credit-bureau-like score used for underwriting simulation. |
| document_completeness | DOUBLE | Completeness score of submitted documentation. |
| approval_tat_hours | DOUBLE | Turnaround time from submission to decision, in hours; averaged for the Overview KPI's driver text and used to flag `>72h` cases. |
| preapproval_signal_at_booking | BOOLEAN | Whether a finance pre-approval signal existed at the time of booking. |
| data_origin | TEXT | Synthetic-data provenance metadata; not surfaced in UI. |
| generator_version | TEXT | Synthetic-data generator/reproducibility version tag; not surfaced in UI. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Executive Overview (`index.tsx`), via `OperationalOverviewService`
  * **Insight/Metric Displayed:** "Financial Risk Reduction" KPI.
  * **Data Mapping:** `value = COUNT(status = 'APPROVED') / COUNT(*) × 100`; driver text cites `COUNT(APPROVED)`, `COUNT(*)`, and `AVG(approval_tat_hours)`.
  * **Insight/Metric Displayed:** "Resolve N non-final finance decision(s)" recommendation card.
  * **Data Mapping:** `COUNT(status IN ('MANUAL_REVIEW','PENDING'))`, split into the two status counts for impact text; confidence/risk from that combined share of all applications.
* Not currently surfaced on the Dealer Cockpit — `dealer.tsx` makes no `finance_applications` query; the cockpit's finance context is limited to booking-level flags like `bookings.finance_assisted`.
* `requested_amount_inr`, `approved_amount_inr`, `risk_band`, `income_band`, `bureau_like_score_synthetic`, `document_completeness`, `preapproval_signal_at_booking`, `submitted_at`, `decision_at` are used only in aggregate counts/averages above — not shown per-application anywhere.

---

### 12. Allocations — `allocations`
* **Description:** One row per vehicle-unit allocation from a manufacturing production batch to a dealer against a booking, bridging the sales side (booking, dealer, demand) to the manufacturing side (plant, production line, supplier lot, quality). Source is the Synthetic Data Factory generator (CSV `data/synthetic/auto/allocations.csv`) imported into Postgres. This is the spec's "Vehicle allocation history" table.
* **Primary Key:** `allocation_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| allocation_id | TEXT (PK) | Stable allocation record code. |
| booking_id | TEXT (FK → bookings.booking_id) | Booking this allocation fulfills. |
| lead_id | TEXT (FK → leads.lead_id) | Originating lead. |
| customer_id | TEXT (FK → customers.customer_id) | Customer receiving the unit. |
| dealer_id | TEXT (FK → dealers.dealer_id) | Receiving dealer. |
| dealer_name | TEXT | Denormalized dealer label. |
| region_id | TEXT (FK → regions.region_id) | Denormalized region. |
| region_name | TEXT | Denormalized region label. |
| city_id | TEXT (FK → cities.city_id) | Denormalized city. |
| city_name | TEXT | Denormalized city label. |
| vehicle_model_id | TEXT (FK → vehicle_models.vehicle_model_id) | Allocated model. |
| vehicle_model_name | TEXT | Denormalized model label. |
| vehicle_id | TEXT | Physical vehicle unit identifier being allocated. |
| production_batch_id | TEXT (FK → production_batches.production_batch_id) | Manufacturing batch the unit came from. |
| plant_id | TEXT (FK → plants.plant_id) | Manufacturing plant. |
| plant_name | TEXT | Denormalized plant label. |
| production_line_id | TEXT (FK → production_lines.production_line_id) | Production line. |
| production_line_name | TEXT | Denormalized production-line label. |
| representative_machine_id | TEXT (FK → machines.machine_id) | Representative machine on the line. |
| representative_machine_name | TEXT | Denormalized machine label. |
| variant | TEXT | Vehicle variant/trim allocated. |
| primary_supplier_id | TEXT (FK → suppliers.supplier_id) | Primary component supplier for the batch. |
| primary_supplier_name | TEXT | Denormalized supplier label. |
| primary_supplier_lot_id | TEXT (FK → supplier_lots.supplier_lot_id) | Specific supplier lot used. |
| supplier_lot_quality_score | DOUBLE | Quality score of the supplier lot. |
| production_quality_score | DOUBLE | Quality score of the production run. |
| finance_application_id | TEXT (FK → finance_applications.finance_application_id) | Related finance application, if allocation was finance-gated. |
| finance_status | TEXT | Denormalized finance status. |
| allocation_date | TIMESTAMPTZ | Date of the allocation event. |
| requested_units | BIGINT | Units requested by the dealer. |
| allocated_units | BIGINT | Units actually allocated. |
| waiting_list | BIGINT | Units still waiting to be allocated. |
| dealer_capacity | BIGINT | Dealer capacity figure used at allocation time. |
| dealer_capacity_source | TEXT | Provenance of the `dealer_capacity` figure used. |
| regional_demand_index | DOUBLE | Regional demand pressure index at allocation time. |
| allocation_priority_score | DOUBLE | Computed priority score used to rank this allocation. |
| allocation_priority | TEXT | Priority tier/classification for this allocation. |
| inventory_before | BIGINT | Dealer inventory level before this allocation. |
| inventory_after | BIGINT | Dealer inventory level after this allocation. |
| production_batch_inventory_before | BIGINT | Batch-level inventory before this allocation. |
| production_batch_inventory_after | BIGINT | Batch-level inventory after this allocation. |
| allocation_wait_hours | DOUBLE | Hours the dealer waited for this allocation. |
| allocation_status | TEXT | Status of the allocation process. |
| data_origin | TEXT | Synthetic-data provenance metadata; not surfaced in UI. |
| generator_version | TEXT | Synthetic-data generator/reproducibility version tag; not surfaced in UI. |

#### Screen-by-Screen Insights Mapping
* Not currently surfaced in any frontend screen. No backend service (`backend/app/services/*`, `backend/app/ai/**`) reads `runtime_tables["allocations"]` — the table is defined and populated, and is referenced as a foreign key by `deliveries`, `service_events`, and `warranty_claims`, but it is not queried directly by the Dealer Cockpit, Executive Overview, or any simulation engine. (`backend/app/ai/simulation/dealer_allocation.py` — despite its name — is a pure user-input formula and does not read this table.)
* **Predictive Modeling Mapping:** Its `evidence_json` fields (`regional_demand_index`, `fulfillment_ratio`, `waiting_list`, `allocation_priority`/`allocation_priority_score`, `dealer_capacity`, `inventory_before`/`inventory_after`, `production_batch_inventory_before`/`after`) DO surface indirectly — see the `recommendations` table (Section G, #47), whose `DEALER_ALLOCATION_OPTIMIZATION` use case is generated from exactly these `allocations` columns as evidence features, even though the live `OperationalOverviewService` never re-derives them at runtime.

---

### 13. Deliveries — `deliveries`
* **Description:** One row per vehicle delivered to a customer, with the full promised-vs-actual timeline (dispatch, transit, handover) and the delay decomposition (transport disruption, quality hold, demand pressure) behind it. Source is the Synthetic Data Factory generator (CSV `data/synthetic/auto/deliveries.csv`) imported into Postgres. Business purpose: implements the spec's rule that delivery delay is `actual_date − promised_date`, computed from the recorded timeline rather than seeded as a dashboard number.
* **Primary Key:** `delivery_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| delivery_id | TEXT (PK) | Stable delivery record code. |
| allocation_id | TEXT (FK → allocations.allocation_id) | Allocation this delivery fulfills. |
| booking_id | TEXT (FK → bookings.booking_id) | Originating booking. |
| lead_id | TEXT (FK → leads.lead_id) | Originating lead. |
| customer_id | TEXT (FK → customers.customer_id) | Receiving customer. |
| vehicle_id | TEXT | Physical vehicle unit delivered; join key used by the vehicle-telematics causal pipeline (Section D). |
| vehicle_model_id | TEXT (FK → vehicle_models.vehicle_model_id) | Delivered model. |
| vehicle_model_name | TEXT | Denormalized model label. |
| variant | TEXT | Delivered variant/trim. |
| dealer_id | TEXT (FK → dealers.dealer_id) | Delivering dealer. |
| dealer_name | TEXT | Denormalized dealer label. |
| region_id | TEXT (FK → regions.region_id) | Denormalized region. |
| region_name | TEXT | Denormalized region label. |
| city_id | TEXT (FK → cities.city_id) | Denormalized city. |
| city_name | TEXT | Denormalized city label. |
| production_batch_id | TEXT (FK → production_batches.production_batch_id) | Source production batch. |
| plant_id | TEXT (FK → plants.plant_id) | Source plant. |
| plant_name | TEXT | Denormalized plant label. |
| production_line_id | TEXT (FK → production_lines.production_line_id) | Source production line. |
| production_line_name | TEXT | Denormalized production-line label. |
| representative_machine_id | TEXT (FK → machines.machine_id) | Representative machine. |
| representative_machine_name | TEXT | Denormalized machine label. |
| primary_supplier_id | TEXT (FK → suppliers.supplier_id) | Primary supplier. |
| primary_supplier_name | TEXT | Denormalized supplier label. |
| primary_supplier_lot_id | TEXT (FK → supplier_lots.supplier_lot_id) | Supplier lot used. |
| supplier_lot_quality_score | DOUBLE | Denormalized supplier-lot quality score. |
| production_quality_score | DOUBLE | Denormalized production quality score. |
| booking_timestamp | TIMESTAMPTZ | Denormalized original booking time. |
| allocation_date | TIMESTAMPTZ | Denormalized allocation date. |
| promised_delivery_date | TIMESTAMPTZ | Date promised to the customer; the anchor for delay calculation. |
| dispatch_at | TIMESTAMPTZ | When the vehicle was dispatched from the plant/dealer pipeline. |
| physical_ready_date | TIMESTAMPTZ | When the physical vehicle was ready. |
| projected_delivery_date | TIMESTAMPTZ | System-projected delivery date given the timeline. |
| actual_delivery_date | TIMESTAMPTZ | Actual delivery/handover date; used as the visibility cutoff for post-delivery vehicle telemetry (see mapping below). |
| dispatch_delay_hours | DOUBLE | Hours of delay at dispatch. |
| base_transit_days | DOUBLE | Expected baseline transit duration in days. |
| transport_disruption | BOOLEAN | Whether a transport disruption occurred. |
| disruption_days | DOUBLE | Extra days added by the disruption. |
| total_transit_days | DOUBLE | Actual total transit duration. |
| regional_demand_index | DOUBLE | Denormalized regional demand pressure at delivery time. |
| allocation_priority | TEXT | Denormalized allocation priority tier. |
| allocation_wait_hours | DOUBLE | Denormalized allocation wait time. |
| demand_pressure | BOOLEAN | Flag: delay attributable to demand pressure. |
| quality_hold | BOOLEAN | Flag: delay attributable to a quality hold. |
| normal_handover_delay | BOOLEAN | Flag: delay attributable to normal handover process time. |
| delivery_variance_days | DOUBLE | Signed variance between projected and actual delivery. |
| delay_days | DOUBLE | Computed delay = `actual_delivery_date − promised_delivery_date` (when late), per the spec's non-seeded-delay rule. |
| early_days | DOUBLE | Computed days early (when delivered ahead of promise). |
| delayed | BOOLEAN | Whether the delivery was delayed overall. |
| delay_reason | TEXT | Attributed reason for the delay. |
| customer_handover_completed | BOOLEAN | Whether the physical handover to the customer was completed. |
| handover_score | DOUBLE | Customer satisfaction/quality score for the handover. |
| delivery_status | TEXT | Overall delivery status. |
| data_origin | TEXT | Synthetic-data provenance metadata; not surfaced in UI. |
| generator_version | TEXT | Synthetic-data generator/reproducibility version tag; not surfaced in UI. |

#### Screen-by-Screen Insights Mapping
* Not surfaced in the Dealer Cockpit or Executive Overview — `dealer.tsx` and `index.tsx` make no query against `deliveries`. It is, however, read live elsewhere in the backend: `backend/app/ai/causal/telematics_loader.py` joins `deliveries.vehicle_id` / `deliveries.actual_delivery_date` against `vehicle_telematics_timeseries` to establish the visibility boundary for the vehicle-telematics causal-discovery pipeline (only telemetry timestamped at or after a vehicle's `actual_delivery_date` is fed to the causal engine) — see Section D, table #24.

---

# Section C — Manufacturing, Warranty & Quality

### 14. Plants — `plants`
* **Description:** Master registry of Mahindra manufacturing plants (one row per physical plant). Source CSV: `data/synthetic/master/plants`. Business purpose: anchors every production line, machine, batch and downstream field record to a physical facility and region.
* **Primary Key:** `plant_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `plant_id` | TEXT (PK) | Unique plant identifier. |
| `plant_name` | TEXT | Human-readable plant name. |
| `city_name` | TEXT | City where the plant is located. |
| `region_name` | TEXT | Sales/ops region the plant belongs to. |
| `plant_type` | TEXT | Plant classification (e.g. vehicle assembly vs. component plant). |
| `daily_capacity_units` | BIGINT | Rated daily production capacity in units. |
| `data_origin` | TEXT | Synthetic-data provenance tag (generator bookkeeping). |
| `generator_version` | TEXT | Version of the synthetic data generator that produced the row. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Manufacturing / Warranty & Quality (`warranty-quality.tsx`)
  * This table is **not surfaced** on the Warranty & Quality screen, and no backend service queries the physical `plants` table anywhere in the codebase. `plant_id`/`plant_name` reach the screen only as already-denormalized columns carried on `manufacturing_timeseries`, `production_batches`, `service_events`, and `warranty_claims` (populated at data-generation time), so a live join back to `plants` is never required.

#### Predictive Modeling Mapping
* Not used by the causal-discovery or early-warning pipelines. No columns of the physical `plants` table are read by `manufacturing_causal.py`, the `app/ai/causal/*` modules, or `warranty_quality_early_warning.py` — only the denormalized `plant_id`/`plant_name` riding on other tables are.

---

### 15. Production Lines — `production_lines`
* **Description:** Master registry of production lines within each plant (e.g. body/paint/assembly lines). Source CSV: `data/synthetic/master/production_lines`. Business purpose: defines the manufacturing process topology (line type, throughput, shift structure) that machines and batches belong to.
* **Primary Key:** `production_line_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `production_line_id` | TEXT (PK) | Unique production-line identifier. |
| `plant_id` | TEXT (FK → `plants.plant_id`) | Owning plant. |
| `line_name` | TEXT | Human-readable line name. |
| `line_type` | TEXT | Process stage the line performs (e.g. `BODY`, `PAINT`, `ASSEMBLY`) — this is the same taxonomy used for PCMCI scope stratification (see Predictive Modeling Mapping on `manufacturing_timeseries`). |
| `units_per_hour` | BIGINT | Rated line throughput. |
| `shift_count` | BIGINT | Number of shifts the line operates. |
| `active` | BOOLEAN | Whether the line is currently operating. |
| `data_origin` | TEXT | Synthetic-data provenance tag. |
| `generator_version` | TEXT | Generator version bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Manufacturing / Warranty & Quality (`warranty-quality.tsx`)
  * Not surfaced directly — the physical `production_lines` table is never queried by any backend service. `production_line_id`/`production_line_name`/`line_type` reach the screen only as denormalized columns already present on `manufacturing_timeseries` and the causal-scheduler's cohort-selection logic (see below).

#### Predictive Modeling Mapping
* **Target Variable:** None directly — the physical table is not queried.
* **Input Features:** None directly. However, its `line_type` taxonomy is mirrored on `manufacturing_timeseries.line_type` and IS used by the PCMCI stability filter (`app/ai/causal/manufacturing_filter.py`) to scope-stratify edges: relationships touching `paint_booth_temperature_c`, `paint_booth_humidity_pct`, or `paint_defect_rate` are scoped `"PAINT"` and evaluated only against paint-capable machines/lines, while all other relationships are scoped `"ALL"` and evaluated against the full machine cohort — this prevents BODY/ASSEMBLY lines (which cannot physically observe paint signals) from diluting paint-specific stability statistics.

---

### 16. Machines — `machines`
* **Description:** Master registry of individual machines/stations on each production line. Source CSV: `data/synthetic/master/machines`. Business purpose: the physical unit that `manufacturing_timeseries` observations are recorded against, and the unit PCMCI causal discovery is run per-machine and aggregated across.
* **Primary Key:** `machine_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `machine_id` | TEXT (PK) | Unique machine identifier. |
| `production_line_id` | TEXT (FK → `production_lines.production_line_id`) | Owning production line. |
| `plant_id` | TEXT (FK → `plants.plant_id`) | Owning plant. |
| `machine_name` | TEXT | Human-readable machine name. |
| `machine_type` | TEXT | Equipment type (e.g. weld robot, paint booth, press). |
| `station_type` | TEXT | Process station classification. |
| `rated_capacity_units_per_hour` | BIGINT | Rated machine throughput. |
| `baseline_load_pct` | DOUBLE | Expected normal-operating load percentage. |
| `maintenance_interval_hours` | BIGINT | Scheduled maintenance cadence. |
| `active` | BOOLEAN | Whether the machine is currently in service. |
| `data_origin` | TEXT | Synthetic-data provenance tag. |
| `generator_version` | TEXT | Generator version bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Manufacturing / Warranty & Quality (`warranty-quality.tsx`)
  * The physical `machines` table is not queried by the warranty-quality API endpoints, and no machine-level attribute (`machine_type`, `baseline_load_pct`, `maintenance_interval_hours`, etc.) is rendered on this screen. Every `machine_id`/`machine_name` shown (Exact Production Lineage table, "Affected Machines" metric, causal-support "machine support" columns) comes from the denormalized copies already carried on `manufacturing_timeseries`, `service_events`, and `warranty_claims`.
  * It IS used **server-side** by the causal scheduler (`backend/app/scheduler/causal_scheduler.py::build_manufacturing_source_plan`): once exact-lineage machines are identified from visible field evidence, `machines.production_line_id` is queried for those machines and then used to pull in every *other* machine sharing that same `production_line_id`, expanding the PCMCI machine cohort so the algorithm has full process context from sibling stations on the same line — this cohort indirectly determines which `manufacturing_causal_edges` rows exist for the graph the screen renders.

#### Predictive Modeling Mapping
* **Target Variable:** N/A (this table is not itself modeled).
* **Input Features:** `machine_id` and `production_line_id` are used purely for **cohort selection** (which machines' time series enter the PCMCI panel), not as PCMCI variables themselves. No other `machines` column is fed to the causal-discovery engine.

---

### 17. Suppliers — `suppliers`
* **Description:** Master registry of component suppliers. Source CSV: `data/synthetic/auto/suppliers`. Business purpose: captures baseline supplier quality/lead-time/capacity characteristics that downstream `supplier_lots`, `production_batches`, and warranty claims are generated to be causally consistent with.
* **Primary Key:** `supplier_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `supplier_id` | TEXT (PK) | Unique supplier identifier. |
| `supplier_name` | TEXT | Supplier company name. |
| `component_category` | TEXT | Broad component category supplied (e.g. electronics, powertrain). |
| `component_group` | TEXT | Finer-grained component grouping. |
| `criticality` | TEXT | Business criticality of the supplied component (e.g. LOW/MEDIUM/HIGH/CRITICAL). |
| `supplier_tier` | TEXT | Supplier tier classification (e.g. Tier 1/2). |
| `city_id` | TEXT (FK → `cities.city_id`) | Supplier's city. |
| `city_name` | TEXT | Denormalized city name. |
| `region_id` | TEXT (FK → `regions.region_id`) | Supplier's region. |
| `region_name` | TEXT | Denormalized region name. |
| `baseline_quality_score` | DOUBLE | Generator-assigned baseline quality score for this supplier. |
| `lead_time_days` | BIGINT | Typical supply lead time. |
| `monthly_capacity_units` | BIGINT | Rated monthly supply capacity. |
| `active` | BOOLEAN | Whether the supplier relationship is currently active. |
| `data_origin` | TEXT | Synthetic-data provenance tag. |
| `generator_version` | TEXT | Generator version bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Manufacturing / Warranty & Quality (`warranty-quality.tsx`)
  * The physical `suppliers` table is not queried anywhere in the backend. The **Supplier Hotspots** panel (`supplier_name`, `component_category`, claim/lot/batch counts, approved exposure) is built entirely from `warranty_claims.primary_supplier_id` / `primary_supplier_name` / `supplier_component_category`, which are denormalized copies of this master data already inlined on the claim row at generation time — not a live join to `suppliers`.

#### Predictive Modeling Mapping
* Not read by the causal-discovery or early-warning pipelines directly. Its `baseline_quality_score`/`criticality` conceptually seed the synthetic generator's supplier-lot quality distribution, but the runtime PCMCI engine and the early-warning evidence scorer never query this table — they consume the already-materialized `supplier_lot_quality_score` / `primary_supplier_lot_id` columns on `manufacturing_timeseries`, `service_events`, and `warranty_claims` instead.

---

### 18. Supplier Lots — `supplier_lots`
* **Description:** One row per received supplier component lot, with inspection/quality outcomes. Source CSV: `data/synthetic/auto/supplier_lots`. Business purpose: the material-quality unit that batches consume from and that warranty defects are generated to correlate with ("warranty defects must not be independent of supplier/batch quality").
* **Primary Key:** `supplier_lot_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `supplier_lot_id` | TEXT (PK) | Unique supplier-lot identifier. |
| `supplier_id` | TEXT (FK → `suppliers.supplier_id`) | Originating supplier. |
| `supplier_name` | TEXT | Denormalized supplier name. |
| `component_category` | TEXT | Denormalized component category. |
| `component_group` | TEXT | Denormalized component group. |
| `criticality` | TEXT | Denormalized component criticality. |
| `lot_sequence` | BIGINT | Sequence number of the lot for that supplier. |
| `received_at` | TIMESTAMPTZ | Timestamp the lot was received at the plant. |
| `lot_size_units` | BIGINT | Total units in the lot. |
| `accepted_units` | BIGINT | Units passing incoming inspection. |
| `rejected_units` | BIGINT | Units failing incoming inspection. |
| `lot_quality_score` | DOUBLE | Composite quality score for the lot (0–1 scale). |
| `inspection_defect_rate` | DOUBLE | Defect rate observed at incoming inspection. |
| `inspection_status` | TEXT | Inspection outcome (e.g. PASSED/FAILED/CONDITIONAL). |
| `usable_for_production` | BOOLEAN | Whether the lot is cleared for use in production. |
| `data_origin` | TEXT | Synthetic-data provenance tag. |
| `generator_version` | TEXT | Generator version bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Manufacturing / Warranty & Quality (`warranty-quality.tsx`)
  * The physical `supplier_lots` table is not queried by any backend service. Every supplier-lot reference on this screen (Exact Production Lineage table's "Supplier Lot" column, "Affected Supplier Lots" metric, supplier hotspot lot counts) is the `supplier_lot_id` foreign key carried directly on `manufacturing_timeseries`, `service_events` (`primary_supplier_lot_id`), and `warranty_claims` (`primary_supplier_lot_id`) — used purely as a join key/identifier for lineage, never joined back to this table's own quality columns (`lot_quality_score`, `inspection_defect_rate`, etc.) at query time.

#### Predictive Modeling Mapping
* Not read directly by PCMCI or the early-warning scorer. Its lot-level `lot_quality_score` is conceptually the origin of the `supplier_lot_quality_score` value that IS materialized onto `manufacturing_timeseries` (and used as a PCMCI candidate variable — see below) and onto `service_events`/`warranty_claims` — but the runtime pipeline reads that materialized value, not this table.

---

### 19. Production Batches — `production_batches`
* **Description:** One row per production batch/run of a vehicle model+variant on a specific plant/line, capturing the full build context (machines, supplier lot consumed, yield/defect/rework/scrap outcomes). Source CSV: `data/synthetic/auto/production_batches`. Business purpose: the central join point for "Supplier → Batch → Plant → Model/Variant → Failure → Warranty" traceability.
* **Primary Key:** `production_batch_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `production_batch_id` | TEXT (PK) | Unique batch identifier. |
| `plant_id` | TEXT (FK → `plants.plant_id`) | Plant that ran the batch. |
| `plant_name` | TEXT | Denormalized plant name. |
| `production_line_id` | TEXT (FK → `production_lines.production_line_id`) | Line that ran the batch. |
| `production_line_name` | TEXT | Denormalized line name. |
| `production_line_type` | TEXT | Denormalized line type. |
| `representative_machine_id` | TEXT (FK → `machines.machine_id`) | Representative/primary machine for this batch — the exact-lineage anchor used by warranty/service linkage. |
| `representative_machine_name` | TEXT | Denormalized machine name. |
| `active_line_count` | BIGINT | Active lines contributing to the batch. |
| `active_machine_count` | BIGINT | Active machines contributing to the batch. |
| `average_machine_load_pct` | DOUBLE | Mean machine load during the batch. |
| `bottleneck_capacity_units_per_hour` | DOUBLE | Constraining throughput for the batch. |
| `vehicle_model_id` | TEXT (FK → `vehicle_models.vehicle_model_id`) | Vehicle model built. |
| `vehicle_model_name` | TEXT | Denormalized model name. |
| `variant` | TEXT | Vehicle variant/trim built. |
| `production_complexity` | DOUBLE | Relative build-complexity score. |
| `primary_supplier_id` | TEXT (FK → `suppliers.supplier_id`) | Primary supplier for the batch's critical component. |
| `primary_supplier_name` | TEXT | Denormalized supplier name. |
| `primary_supplier_lot_id` | TEXT (FK → `supplier_lots.supplier_lot_id`) | Supplier lot consumed by the batch. |
| `supplier_component_category` | TEXT | Denormalized component category of that lot. |
| `supplier_criticality` | TEXT | Denormalized criticality of that component. |
| `supplier_lot_quality_score` | DOUBLE | Quality score of the consumed supplier lot. |
| `supplier_lot_inspection_defect_rate` | DOUBLE | Inspection defect rate of the consumed lot. |
| `supplier_lot_age_days` | DOUBLE | Age of the lot at time of consumption. |
| `supplier_lot_units_consumed` | BIGINT | Units of the lot consumed by this batch. |
| `supplier_lot_remaining_units_after_batch` | BIGINT | Remaining lot units after this batch. |
| `production_date` | DATE | Calendar date of production. |
| `production_start` | TIMESTAMPTZ | Batch start timestamp. |
| `production_end` | TIMESTAMPTZ | Batch end timestamp. |
| `dominant_shift` | TEXT | Shift that produced most of the batch. |
| `scaled_daily_capacity_units` | BIGINT | Plant capacity scaled to the batch context. |
| `planned_units` | BIGINT | Planned unit count. |
| `production_efficiency` | DOUBLE | Actual vs. planned efficiency ratio. |
| `units_produced` | BIGINT | Total units produced. |
| `defect_probability` | DOUBLE | Generator-modeled probability of defect for the batch. |
| `defect_units` | BIGINT | Units flagged defective. |
| `rework_units` | BIGINT | Units sent to rework. |
| `rework_success_units` | BIGINT | Units successfully reworked. |
| `scrap_units` | BIGINT | Units scrapped. |
| `first_pass_good_units` | BIGINT | Units good on first pass (no rework). |
| `final_good_units` | BIGINT | Units good after rework, i.e. shippable. |
| `first_pass_yield` | DOUBLE | `first_pass_good_units` / `units_produced`. |
| `final_yield` | DOUBLE | `final_good_units` / `units_produced`. |
| `quality_inspection_rate` | DOUBLE | Fraction of units quality-inspected. |
| `quality_score` | DOUBLE | Composite batch quality score. |
| `batch_status` | TEXT | Batch lifecycle status (e.g. COMPLETED, IN_PROGRESS). |
| `available_for_allocation_units` | BIGINT | Units available to allocate to dealers/customers. |
| `data_origin` | TEXT | Synthetic-data provenance tag. |
| `generator_version` | TEXT | Generator version bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Manufacturing / Warranty & Quality (`warranty-quality.tsx`)
  * The physical `production_batches` table is **not queried by any backend service**. Every `production_batch_id` shown on this screen (Exact Production Lineage table's "Production Batch" column, "Affected Batches" metric, supplier/market hotspot batch counts) is the foreign-key value carried directly on `manufacturing_timeseries`, `service_events`, and `warranty_claims`, used purely as an identity/lineage key — none of this table's own yield, defect, rework or scrap columns are ever pulled onto the screen.

#### Predictive Modeling Mapping
* Not read directly by PCMCI or the early-warning scorer. `production_batch_id` functions solely as one leg of the exact-lineage triple `(machine_id, production_batch_id, supplier_lot_id)` that the early-warning service (`_load_exact_lineages`) uses to gate which PCMCI-discovered edges are shown as "lineage-aligned" for a given field issue — the batch's own quality metrics (`defect_probability`, `first_pass_yield`, `quality_score`, etc.) are not consumed at runtime by either pipeline.

---

### 20. Service Events — `service_events`
* **Description:** One row per vehicle service visit (routine or issue-driven), carrying the exact manufacturing lineage of the serviced vehicle. Source CSV: `data/synthetic/auto/service_events`. Business purpose: the field-evidence source for complaint/repair volume and severity feeding the early-warning system.
* **Primary Key:** `service_event_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `service_event_id` | TEXT (PK) | Unique service-event identifier. |
| `delivery_id` | TEXT (FK → `deliveries.delivery_id`) | Originating vehicle delivery. |
| `allocation_id` | TEXT (FK → `allocations.allocation_id`) | Originating allocation. |
| `booking_id` | TEXT (FK → `bookings.booking_id`) | Originating sales booking. |
| `customer_id` | TEXT (FK → `customers.customer_id`) | Customer whose vehicle was serviced. |
| `vehicle_id` | TEXT | Serviced vehicle identifier. |
| `vehicle_model_id` | TEXT (FK → `vehicle_models.vehicle_model_id`) | Vehicle model. |
| `vehicle_model_name` | TEXT | Denormalized model name. |
| `variant` | TEXT | Vehicle variant. |
| `service_dealer_id` | TEXT (FK → `dealers.dealer_id`) | Servicing dealer. |
| `service_dealer_name` | TEXT | Denormalized dealer name. |
| `region_id` | TEXT (FK → `regions.region_id`) | Servicing region. |
| `region_name` | TEXT | Denormalized region name. |
| `city_id` | TEXT (FK → `cities.city_id`) | Servicing city. |
| `city_name` | TEXT | Denormalized city name. |
| `production_batch_id` | TEXT (FK → `production_batches.production_batch_id`) | Exact production batch of the vehicle — one leg of the exact-lineage triple. |
| `plant_id` | TEXT (FK → `plants.plant_id`) | Denormalized build plant. |
| `plant_name` | TEXT | Denormalized plant name. |
| `production_line_id` | TEXT (FK → `production_lines.production_line_id`) | Denormalized build line. |
| `production_line_name` | TEXT | Denormalized line name. |
| `representative_machine_id` | TEXT (FK → `machines.machine_id`) | Representative build machine — the second leg of the exact-lineage triple. |
| `representative_machine_name` | TEXT | Denormalized machine name. |
| `primary_supplier_id` | TEXT (FK → `suppliers.supplier_id`) | Denormalized primary supplier. |
| `primary_supplier_name` | TEXT | Denormalized supplier name. |
| `primary_supplier_lot_id` | TEXT (FK → `supplier_lots.supplier_lot_id`) | Supplier lot used — the third leg of the exact-lineage triple. |
| `supplier_component_category` | TEXT | Denormalized component category. |
| `supplier_lot_quality_score` | DOUBLE | Denormalized supplier-lot quality score. |
| `production_quality_score` | DOUBLE | Denormalized batch quality score. |
| `service_type` | TEXT | Type of service visit (e.g. scheduled, breakdown). |
| `service_started_at` | TIMESTAMPTZ | Service start timestamp — the field-evidence "as-of" clock column. |
| `service_completed_at` | TIMESTAMPTZ | Service completion timestamp. |
| `days_since_delivery` | DOUBLE | Vehicle age in days at time of service. |
| `odometer_km` | BIGINT | Odometer reading at service. |
| `complaint_reported` | BOOLEAN | Whether the customer reported a complaint. |
| `issue_category` | TEXT | Categorized issue (e.g. ELECTRICAL, PAINT, ENGINE) — the early-warning system's grouping key; NULL rows are excluded from evidence. |
| `severity` | TEXT | Service severity (LOW/MEDIUM/HIGH). |
| `diagnosis` | TEXT | Free-text/coded diagnosis. |
| `repair_required` | BOOLEAN | Whether a repair was performed. |
| `service_duration_hours` | DOUBLE | Duration of the service. |
| `service_score` | DOUBLE | Composite service-quality score. |
| `warranty_candidate` | BOOLEAN | Whether the event was flagged as a potential warranty claim. |
| `service_status` | TEXT | Lifecycle status of the service event. |
| `data_origin` | TEXT | Synthetic-data provenance tag. |
| `generator_version` | TEXT | Generator version bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Manufacturing / Warranty & Quality (`warranty-quality.tsx`)
  * **Insight/Metric Displayed:** Priority Warnings list and Selected Warning Evidence panel — "Complaints", "Repairs", "N service events" detail, service-severity mix.
    * **Data Mapping:** `warranty_quality_early_warning.py` queries `service_event_id, issue_category, severity, complaint_reported, repair_required, warranty_candidate, representative_machine_id, vehicle_id, production_batch_id, primary_supplier_lot_id, vehicle_model_id, city_id` filtered on `issue_category IS NOT NULL` and `service_started_at <= simulation_as_of`. Per issue category: `complaints` = COUNT where `complaint_reported`; `repairs` = COUNT where `repair_required`; `warranty_candidates` = COUNT where `warranty_candidate`; `service_high_events`/`service_medium_events`/`service_low_events` = COUNT bucketed by `severity`.
  * **Insight/Metric Displayed:** Exact Production Lineage panel ("Field Lineages" count, Machine/Batch/Supplier-Lot table rows).
    * **Data Mapping:** the triple `(representative_machine_id, production_batch_id, primary_supplier_lot_id)` from every matching row forms `issue["field_lineages"]` (a set of distinct lineage triples) — this is intersected against manufacturing-observation lineage (see `manufacturing_timeseries`) to compute "Exact Window" lineages and coverage %.
  * **Insight/Metric Displayed:** "Machines"/"Models"/"Cities" affected-count metric cards.
    * **Data Mapping:** distinct counts of `representative_machine_id`, `vehicle_model_id`, `city_id` across matched rows.
  * **Insight/Metric Displayed:** Empirical Calibration Baseline panel (Complaints P50/P75/P90).
    * **Data Mapping:** continuous percentiles computed in Python over the per-issue-category `complaints` counts across the whole cohort.

#### Predictive Modeling Mapping
* **Target Variable:** `evidence_score` (an integer, empirically-calibrated **rule-based** prioritization index — explicitly documented in code as "NOT probability and NOT AI confidence") and the derived `priority` tier (CRITICAL/HIGH/MEDIUM/LOW), computed per `issue_category`.
* **Input Features:** `complaint_reported` (→ complaint count, tiered against its own P75/P90), `repair_required` (→ repair count), `warranty_candidate` (→ warranty-candidate count), `severity` (→ +2 score if any HIGH-severity event, +1 if any MEDIUM), plus lineage-diversity features `representative_machine_id`, `production_batch_id`, `primary_supplier_lot_id`, `vehicle_model_id`, `city_id` (→ distinct-count features scored against their own P75 thresholds).

---

### 21. Warranty Claims — `warranty_claims`
* **Description:** One row per submitted warranty claim, linked to its originating service event and full manufacturing/supplier lineage. Source CSV: `data/synthetic/auto/warranty_claims`. Business purpose: the financial/quality outcome record that the early-warning system prioritizes issue categories against, and the primary driver of Supplier and Market Hotspots.
* **Primary Key:** `warranty_claim_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `warranty_claim_id` | TEXT (PK) | Unique claim identifier. |
| `service_event_id` | TEXT (FK → `service_events.service_event_id`) | Originating service event. |
| `delivery_id` | TEXT (FK → `deliveries.delivery_id`) | Originating delivery. |
| `allocation_id` | TEXT (FK → `allocations.allocation_id`) | Originating allocation. |
| `booking_id` | TEXT (FK → `bookings.booking_id`) | Originating booking. |
| `customer_id` | TEXT (FK → `customers.customer_id`) | Claimant customer. |
| `vehicle_id` | TEXT | Vehicle covered by the claim. |
| `vehicle_model_id` | TEXT (FK → `vehicle_models.vehicle_model_id`) | Vehicle model. |
| `vehicle_model_name` | TEXT | Denormalized model name — used in Market Hotspots. |
| `variant` | TEXT | Vehicle variant — used in Market Hotspots. |
| `vehicle_age_days` | DOUBLE | Vehicle age at claim time. |
| `odometer_km` | BIGINT | Odometer reading at claim time. |
| `service_dealer_id` | TEXT (FK → `dealers.dealer_id`) | Servicing dealer. |
| `service_dealer_name` | TEXT | Denormalized dealer name. |
| `region_id` | TEXT (FK → `regions.region_id`) | Region. |
| `region_name` | TEXT | Denormalized region name — used in Market Hotspots. |
| `city_id` | TEXT (FK → `cities.city_id`) | City. |
| `city_name` | TEXT | Denormalized city name — used in Market Hotspots. |
| `production_batch_id` | TEXT (FK → `production_batches.production_batch_id`) | Exact production batch — exact-lineage leg. |
| `plant_id` | TEXT (FK → `plants.plant_id`) | Build plant. |
| `plant_name` | TEXT | Denormalized plant name. |
| `production_line_id` | TEXT (FK → `production_lines.production_line_id`) | Build line. |
| `production_line_name` | TEXT | Denormalized line name. |
| `representative_machine_id` | TEXT (FK → `machines.machine_id`) | Representative build machine — exact-lineage leg. |
| `representative_machine_name` | TEXT | Denormalized machine name. |
| `primary_supplier_id` | TEXT (FK → `suppliers.supplier_id`) | Component supplier — drives Supplier Hotspots. |
| `primary_supplier_name` | TEXT | Denormalized supplier name — Supplier Hotspots label. |
| `primary_supplier_lot_id` | TEXT (FK → `supplier_lots.supplier_lot_id`) | Supplier lot used — exact-lineage leg. |
| `supplier_component_category` | TEXT | Denormalized component category — Supplier Hotspots grouping key. |
| `supplier_lot_quality_score` | DOUBLE | Denormalized supplier-lot quality score. |
| `production_quality_score` | DOUBLE | Denormalized batch quality score. |
| `issue_category` | TEXT | Categorized issue — the early-warning grouping key. |
| `failure_code` | TEXT | Coded failure identifier. |
| `severity` | TEXT | Claim severity. |
| `diagnosis` | TEXT | Diagnosis text/code. |
| `service_duration_hours` | DOUBLE | Duration of the underlying service. |
| `claim_probability` | DOUBLE | Generator-modeled probability of a claim — deliberately **excluded** from the early-warning service (documented "does NOT use claim_probability" to avoid leaking generator ground truth into "observed evidence"). |
| `claim_submitted_at` | TIMESTAMPTZ | Claim submission timestamp — the field-evidence "as-of" clock column. |
| `decision_at` | TIMESTAMPTZ | Timestamp the claim was decided. |
| `claim_amount_inr` | DOUBLE | Amount claimed (₹). |
| `approved_amount_inr` | DOUBLE | Amount approved (₹) — the primary exposure metric shown on screen. |
| `claim_status` | TEXT | Claim decision status (e.g. APPROVED/REJECTED/PENDING). |
| `root_cause_domain` | TEXT | Coded root-cause domain — deliberately **excluded** from causal evidence (documented "does NOT use root_cause_domain as causal evidence"). |
| `data_origin` | TEXT | Synthetic-data provenance tag. |
| `generator_version` | TEXT | Generator version bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Manufacturing / Warranty & Quality (`warranty-quality.tsx`)
  * **Insight/Metric Displayed:** Selected Warning Evidence — "Warranty Claims" count, "Affected Vehicles", "Approved Exposure", "Claim exposure".
    * **Data Mapping:** `warranty_claims` = COUNT distinct `warranty_claim_id`; `claim_exposure_inr` = SUM(`claim_amount_inr`); `approved_exposure_inr` = SUM(`approved_amount_inr`), formatted via `formatInr` (₹ Cr / ₹ L), filtered on `claim_submitted_at <= simulation_as_of`.
  * **Insight/Metric Displayed:** Supplier Hotspots panel.
    * **Data Mapping:** grouped by `(primary_supplier_id, primary_supplier_name, supplier_component_category)`; per group: `claims`, `supplier_lots` (distinct `primary_supplier_lot_id`), `batches` (distinct `production_batch_id`), `approved_exposure_inr` = SUM(`approved_amount_inr`). Sorted by exposure desc, top 6 shown.
  * **Insight/Metric Displayed:** Market Hotspots panel.
    * **Data Mapping:** grouped by `(vehicle_model_name, variant, region_name, city_name)`; per group: `claims`, `batches`, `supplier_lots`, `approved_exposure_inr`. Sorted by claims desc, top 6 shown.
  * **Insight/Metric Displayed:** Exact Production Lineage panel and causal-candidate lineage gating.
    * **Data Mapping:** `(representative_machine_id, production_batch_id, primary_supplier_lot_id)` per claim contributes to `issue["field_lineages"]`, unioned with the equivalent set from `service_events`.

#### Predictive Modeling Mapping
* **Target Variable:** Same composite `evidence_score`/`priority` tier described under `service_events` — `warranty_claims` contributes the claim-volume and exposure legs of that score.
* **Input Features:** `warranty_claim_id` count (→ tiered against P75/P90 of claims-per-category), `approved_amount_inr`/`claim_amount_inr` (summed → tiered against P75/P90 of approved exposure), plus lineage-diversity features (`representative_machine_id`, `production_batch_id`, `primary_supplier_lot_id`, `vehicle_model_id`, `city_id`). `claim_probability` and `root_cause_domain` are explicitly excluded by design so the "observed evidence" score never leaks generator causal ground truth.

---

### 22. Manufacturing Time-Series — `manufacturing_timeseries`
* **Description:** Dense per-minute machine-level process telemetry (temperature, vibration, pressure/load, cycle time, weld/paint/torque signals, defect/rework/downtime outcomes), one row per `(timestamp, machine_id)`. Source CSV: `data/synthetic/causal/manufacturing_timeseries`. Business purpose: the raw observational dataset fed to Tigramite PCMCI/LPCMCI to statistically **discover** (never hardcode) causal relationships among manufacturing process variables and quality/downtime outcomes — the flagship predictive/causal-modeling dataset for this domain.
* **Primary Key:** `timestamp`, `machine_id` (composite)

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `timestamp` | TIMESTAMPTZ (PK part) | Observation timestamp (per-minute cadence at the raw source). |
| `plant_id` | TEXT (FK → `plants.plant_id`) | Owning plant (lineage/context field, not a PCMCI variable). |
| `plant_name` | TEXT | Denormalized plant name (lineage). |
| `production_line_id` | TEXT (FK → `production_lines.production_line_id`) | Owning line (lineage). |
| `production_line_name` | TEXT | Denormalized line name (lineage). |
| `line_type` | TEXT | Process type of the line (e.g. BODY/PAINT/ASSEMBLY) — drives PCMCI scope stratification. |
| `machine_id` | TEXT (PK part, FK → `machines.machine_id`) | Machine the observation belongs to — the PCMCI panel unit. |
| `machine_name` | TEXT | Denormalized machine name (lineage). |
| `production_batch_id` | TEXT (FK → `production_batches.production_batch_id`) | Batch in progress at this timestamp — exact-lineage leg. |
| `vehicle_model_id` | TEXT (FK → `vehicle_models.vehicle_model_id`) | Model in production (lineage). |
| `vehicle_model_name` | TEXT | Denormalized model name (lineage). |
| `supplier_lot_id` | TEXT (FK → `supplier_lots.supplier_lot_id`) | Supplier lot in use — exact-lineage leg. |
| `batch_status` | TEXT | Status of the in-progress batch. |
| `ambient_temperature_c` | DOUBLE | Ambient shop-floor temperature — PCMCI candidate variable. |
| `ambient_humidity_pct` | DOUBLE | Ambient humidity — PCMCI candidate variable. |
| `machine_load` | DOUBLE | Machine load percentage — PCMCI candidate variable. |
| `machine_temperature_c` | DOUBLE | Machine operating temperature — PCMCI candidate variable. |
| `vibration_mm_s` | DOUBLE | Machine vibration — PCMCI candidate variable. |
| `power_kw` | DOUBLE | Power consumption — PCMCI candidate variable. |
| `line_speed_units_per_hour` | DOUBLE | Line speed — PCMCI candidate variable. |
| `cycle_time_seconds` | DOUBLE | Cycle time — PCMCI candidate variable. |
| `hours_since_maintenance` | DOUBLE | Hours elapsed since last maintenance — PCMCI candidate variable. |
| `maintenance_overdue_hours` | DOUBLE | Hours overdue on maintenance interval — PCMCI candidate variable. |
| `supplier_lot_quality_score` | DOUBLE | Quality score of the supplier lot in use — PCMCI candidate variable (the causal bridge from `supplier_lots`/`suppliers` into the process panel). |
| `torque_deviation_nm` | DOUBLE | Torque deviation from spec — PCMCI candidate variable. |
| `paint_booth_temperature_c` | DOUBLE | Paint-booth temperature (PAINT lines only) — PCMCI candidate variable, PAINT-scoped. |
| `paint_booth_humidity_pct` | DOUBLE | Paint-booth humidity (PAINT lines only) — PCMCI candidate variable, PAINT-scoped. |
| `paint_defect_rate` | DOUBLE | Paint defect rate (PAINT lines only) — PCMCI candidate variable, PAINT-scoped. |
| `defect_rate` | DOUBLE | Overall defect rate — PCMCI candidate variable / typical downstream outcome node. |
| `rework_rate` | DOUBLE | Rework rate — PCMCI candidate variable / typical downstream outcome node. |
| `downtime_minutes` | DOUBLE | Equipment downtime — PCMCI candidate variable / typical downstream outcome node. |
| `quality_score` | DOUBLE | Composite quality score — PCMCI candidate variable / typical downstream outcome node. |
| `data_origin` | TEXT | Synthetic-data provenance tag. |
| `generator_version` | TEXT | Generator version bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Manufacturing / Warranty & Quality (`warranty-quality.tsx`)
  * **Insight/Metric Displayed:** "Exact Window" lineage count and lineage coverage % (Exact Production Lineage panel).
    * **Data Mapping:** `warranty_quality_early_warning.py::_load_exact_lineages` selects DISTINCT `(machine_id, production_batch_id, supplier_lot_id)` where `machine_id IN (issue's field-evidence machines)` and `timestamp` falls inside the persisted causal run's `[source_from, source_to]` window; intersected with the field-evidence lineage set to compute `exact_window_lineages` and `exact_window_lineage_coverage`.
  * **Insight/Metric Displayed:** "Live pipeline status" → Data freshness (manufacturing) and Model freshness cards.
    * **Data Mapping:** `MAX(timestamp)` (bounded by `simulation_as_of`) = observed data freshness; row/tick counts come from `CausalIngestionState`/`runtime_count()`/`runtime_max()` against this table.
  * The entire "Causal Candidate Support" table and the causal graph are **derived from** this table via the PCMCI pipeline (see Predictive Modeling Mapping) rather than queried live at request time — the screen reads the persisted `manufacturing_causal_edges` rows instead.

#### Predictive Modeling Mapping
* **Target Variable:** None fixed a priori — PCMCI/LPCMCI performs full multivariate causal **discovery** across all 19 metric columns simultaneously (no privileged "label"); `defect_rate`, `rework_rate`, `downtime_minutes`, `quality_score`, and `paint_defect_rate` are the business-relevant *outcome* nodes the spec is oriented around, but structurally the algorithm treats every metric as a potential source and target.
* **Input Features (the 19 `MANUFACTURING_METRICS` candidate variables, `backend/app/ai/causal/manufacturing_loader.py`):** `ambient_temperature_c`, `ambient_humidity_pct`, `machine_load`, `machine_temperature_c`, `vibration_mm_s`, `power_kw`, `line_speed_units_per_hour`, `cycle_time_seconds`, `hours_since_maintenance`, `maintenance_overdue_hours`, `supplier_lot_quality_score`, `torque_deviation_nm`, `paint_booth_temperature_c`, `paint_booth_humidity_pct`, `paint_defect_rate`, `defect_rate`, `rework_rate`, `downtime_minutes`, `quality_score`. Lineage columns (`plant_id`, `machine_id`, `production_batch_id`, `supplier_lot_id`, etc.) are explicitly retained but excluded from the statistical test set.
* **Pipeline (Postgres → PCMCI → persisted edges), per `manufacturing_causal.py`, `manufacturing_panel.py`, `pcmci_engine.py`, `manufacturing_filter.py`:**
  1. **Load:** `fetch_raw_records` pulls a trailing window (default 72h, anchored on the newest ingested observation for the exact machines implicated by visible field evidence) of long-format `(timestamp, entity, metric, value)` rows per machine, cohort-expanded to sibling machines on the same `production_line_id`.
  2. **Panel construction:** resampled to a 15-minute analysis cadence, per-metric aggregation — `mean` for continuous process signals, `last` for slowly-changing state, `sum` for `downtime_minutes`. Requires ≥96 panel rows (24h) and ≥80% data coverage per metric; drops near-constant signals; limited forward-fill (limit=1) only.
  3. **Standardization:** z-scores each variable.
  4. **Causal discovery:** default algorithm **LPCMCI** (PCMCI available as rollback), Tigramite `ParCorr` test, default `tau_max=3`, `pc_alpha=0.05`, run independently per machine.
  5. **Filtering & stability aggregation:** per-edge floor `min_abs_score=0.12`; PAINT-only metrics scoped `"PAINT"`, all other pairs scoped `"ALL"`; a relationship is called cross-machine **stable** only if it recurs in ≥60% of eligible machines (min 2) with 100% sign agreement, minimum lag 1 for PCMCI (LPCMCI may retain lag-0 links).
  6. **Persistence:** stable edges written to `manufacturing_causal_edges`; the run itself to `manufacturing_causal_runs`. Identical source rows + identical analysis config reuse the persisted run instead of recomputing.
  7. **Business-domain separation:** this pipeline is entirely independent of the generic `app/ai/causal/edge_filter.py`/`graph_builder.py`/`preprocessing.py`/`qa.py` modules (used only by the unrelated Auto/Dealer business-funnel causal graph) — the manufacturing domain deliberately does **not** use a predefined-edge whitelist, consistent with "do not hardcode causal graph edges in runtime."

---

# Section D — Mobility Twin & Vehicle Telematics Causality

### 23. Auto Mobility Business Time Series — `mobility_timeseries`
* **Description:** Region-level, time-windowed aggregation of the Auto lifecycle funnel (demand → leads → dealer follow-up → test drives → bookings → finance → allocation → delivery → service/warranty → revenue). Sourced from `data/synthetic/causal/mobility_timeseries.csv`. It is the sole canonical input to the live "Business Mobility Causality" graph (distinct from the manufacturing/quality plant-level causal domain), computed on demand by `OperationalMobilityService` — nothing about this graph is persisted; every request recomputes PCMCI from these raw rows.
* **Primary Key:** `region_id`, `window_start` (composite)

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| region_id | TEXT (PK part, FK → `regions.region_id`) | Sales/service region the window's activity belongs to. Composite primary key with `window_start`. |
| region_name | TEXT | Human-readable region name; used for free-text region matching in the "Ask Causal Twin" feature. |
| window_start | TIMESTAMPTZ (PK part) | Start of the aggregation window (daily bucket). Composite primary key with `region_id`. |
| window_end | TIMESTAMPTZ | End of the aggregation window. |
| lead_count | BIGINT | Number of new leads captured in the window; base of the funnel. |
| avg_lead_engagement_score | DOUBLE | Mean lead engagement/quality score for the window. |
| followup_count / followup_completed_count | BIGINT | Dealer follow-up attempts / completed follow-ups. |
| customer_response_count | BIGINT | Count of customer responses to follow-up outreach. |
| avg_followup_response_minutes | DOUBLE | Mean time-to-response for follow-ups. |
| test_drive_requested_count / test_drive_completed_count / test_drive_no_show_count | BIGINT | Test-drive funnel counts. |
| booking_count | BIGINT | Vehicle bookings confirmed in the window. |
| booking_value_inr | DOUBLE | Total INR value of bookings in the window. |
| finance_application_count / finance_approved_count / finance_rejected_count / finance_manual_review_count | BIGINT | Finance funnel counts. |
| avg_finance_approval_tat_hours | DOUBLE | Mean finance approval turnaround time, in hours. |
| cancellation_count | BIGINT | Bookings cancelled in the window. |
| allocated_vehicle_count | BIGINT | Vehicles allocated against bookings. |
| avg_allocation_wait_hours | DOUBLE | Mean wait time from booking to allocation, in hours. |
| delivered_vehicle_count / delayed_delivery_count | BIGINT | Delivery counts. |
| avg_delivery_delay_days | DOUBLE | Mean delivery delay, in days, among delivered vehicles. |
| service_event_count / unscheduled_repair_count | BIGINT | Post-delivery service counts. |
| warranty_claim_count / warranty_approved_count | BIGINT | Warranty claim counts. |
| warranty_claim_amount_inr | DOUBLE | Total INR value of warranty claims filed. |
| waitlisted_booking_count | BIGINT | Bookings currently on an allocation waitlist. |
| data_origin / generator_version | TEXT | Provenance/generator bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Mobility Twin (`mobility-twin.tsx`)
  * **Insight/Metric Displayed:** "Business Health" KPI rail (5 tiles: Booking Conversion, Finance Approval, Delivery Delay, Cancellation Rate, Revenue) with week-over-week trend.
  * **Data Mapping:** `useMobilityKpis()` → `GET /mobility-twin/kpis` → `OperationalMobilityService.list_kpis()`. Each KPI is a derived metric averaged over the latest 14 windows vs. the prior 14 windows. Trend = `(latest - previous) / |previous| * 100`.
* **Screen Name:** Mobility Twin (`mobility-twin.tsx`)
  * **Insight/Metric Displayed:** "Causal Graph" panel — an SVG node/edge diagram of the PCMCI-discovered, business-validated Auto funnel causal graph (Lead Volume/Engagement → Dealer Follow-up → Test Drive Completion → Booking Conversion → Finance Approval/Vehicle Allocation → Allocation Delay → Delivery Delay → Cancellation Rate → Revenue). Clicking a node shows its current value, trend, and a recommended action.
  * **Data Mapping:** `useMobilityGraph()` → `GET /mobility-twin/graph` → `OperationalMobilityService.get_graph()`. See Predictive Modeling Mapping for the full derivation chain.
* **Screen Name:** Mobility Twin (`mobility-twin.tsx`)
  * **Insight/Metric Displayed:** "Ask Causal Twin" free-text Q&A (e.g. "Why did bookings drop in Pune?").
  * **Data Mapping:** `useAskAnswer(askMobilityTwin)` → `POST /mobility-twin/ask` → `OperationalMobilityService.ask()`. Parses `region_name` out of the question text, re-runs the causal input load scoped to that region, picks one of `delivery_delay_days`/`finance_approval_rate`/`cancellation_rate`/`booking_conversion_rate`/`lead_volume`/`revenue` by keyword match, and reports its latest-7-window average vs. the prior 7 windows.
* Columns `warranty_claim_count`, `warranty_approved_count`, `warranty_claim_amount_inr`, `service_event_count`, `unscheduled_repair_count`, `waitlisted_booking_count`, `customer_response_count`, `avg_followup_response_minutes`, `test_drive_no_show_count`, `finance_rejected_count`, `finance_manual_review_count`, `avg_finance_approval_tat_hours`, `delayed_delivery_count`, `window_end` are stored but **not currently surfaced** — the causal-input loader selects a fixed 11-metric subset (see below) and does not project these fields.

#### Predictive Modeling Mapping
* **Target Variable:** None single-fixed — PCMCI performs full pairwise causal discovery across an 11-variable panel; every variable is simultaneously a potential source and target. `booking_conversion_rate`, `finance_approval_rate`, `delivery_delay_days`, `cancellation_rate`, and `revenue` are the headline "outcome" nodes surfaced.
* **Input Features:** Built by `app/ai/causal/data_loader.load_daily_causal_input`, which aggregates raw rows per `window_start` into 11 derived metrics: `lead_volume` (Σ`lead_count`), `lead_engagement_score`, `dealer_followup_rate` (Σ`followup_completed_count`/Σ`followup_count`), `test_drive_completion_rate`, `booking_conversion_rate` (Σ`booking_count`/Σ`lead_count`), `finance_approval_rate`, `vehicle_allocation_count`, `allocation_delay_days`, `delivery_delay_days`, `cancellation_rate`, `revenue` (Σ`booking_value_inr`). At least 90 distinct time windows are required before PCMCI runs. Values are z-standardized and passed to linear partial-correlation PCMCI (`tau_max=3`, `alpha=0.05` defaults), cached in-process and filtered through a fixed allow-list of 11 operationally-sensible source→target pairs (e.g. `test_drive_completion_rate → booking_conversion_rate`, `delivery_delay_days → cancellation_rate`) before being returned. Raw `warranty_claim_*`, `service_event_count`, and `unscheduled_repair_count` fields are **not** part of this feature set — the implemented pipeline stops the funnel at `revenue`.

---

### 24. Vehicle Telematics Time Series — `vehicle_telematics_timeseries`
* **Description:** Per-vehicle, high-frequency (raw CAN-bus/IoT cadence, resampled to 5-minute analytical buckets) physical sensor stream — battery, transmission, steering, vibration/road, and diagnostic signals — for delivered vehicles. Sourced from `data/synthetic/causal/vehicle_telematics_timeseries.csv`. It is the sole input to an **independent, per-vehicle** PCMCI/LPCMCI causal-discovery pipeline that is architecturally and physically separate from `mobility_timeseries`'s business-funnel graph — it also underlies plant/production lineage tracing (FKs to `production_batches`, `supplier_lots`, `plants`, `production_lines`, `vehicle_models`).
* **Primary Key:** `timestamp`, `vehicle_id` (composite)
* **Important screen-mapping finding:** despite the table name, it is **not read anywhere in `mobility-twin.tsx`** or its backend path. The vehicle-telematics causal graph it feeds is surfaced instead on the **Warranty & Quality Twin** screen (`warranty-quality.tsx`), which reads it via `backend/app/api/v1/warranty_quality.py` and `app/services/telematics_causal.py` as the "telematics" causal domain, alongside the separate manufacturing/quality graph.

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| timestamp | TIMESTAMPTZ (PK part) | Reading timestamp. |
| vehicle_id | TEXT (PK part) | Vehicle identifier (VIN-equivalent). |
| vehicle_model_id / vehicle_model_name / variant | TEXT | Vehicle identity, retained as context metadata (never PCMCI variables). |
| production_batch_id | TEXT (FK → production_batches) | Links telemetry back to the manufacturing lineage. |
| supplier_lot_id | TEXT (FK → supplier_lots) | Supplier lot lineage. |
| plant_id | TEXT (FK → plants) | Build plant. |
| production_line_id | TEXT (FK → production_lines) | Build line. |
| odometer_km | DOUBLE | Cumulative distance. Excluded from causal discovery — monotonic trend, not a candidate causal variable. |
| vehicle_speed_kph | DOUBLE | Instantaneous vehicle speed — PCMCI variable. |
| ambient_temperature_c | DOUBLE | Outside air temperature — PCMCI variable. |
| battery_temperature_c / battery_soc_pct / battery_voltage_v / battery_current_a / battery_internal_resistance_ohm | DOUBLE | Battery physical signals — PCMCI variables; `battery_internal_resistance_ohm` is a degradation proxy. |
| transmission_temperature_c / transmission_slip_ms / torque_converter_slip_rpm | DOUBLE | Transmission/drivetrain physical signals — PCMCI variables. |
| steering_torque_nm / steering_angle_deg | DOUBLE | Steering physical signals — PCMCI variables. |
| vehicle_vibration_mm_s / vertical_acceleration_g / lateral_acceleration_g / road_roughness_index | DOUBLE | Ride/shock physical signals — PCMCI variables. |
| impact_g_force | DOUBLE | Peak impact g-force; aggregated by **max** (not mean) per 5-minute bucket — PCMCI variable. |
| dtc_count | BIGINT | Count of active diagnostic trouble codes. Excluded as "downstream evidence" of faults rather than a candidate cause. |
| warning_flag | BOOLEAN | Whether a dashboard warning is active. Excluded for the same reason as `dtc_count`. |
| data_origin / generator_version | TEXT | Provenance/generator bookkeeping. Excluded from causal input. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Warranty & Quality Twin (`warranty-quality.tsx`) — telematics causal domain, served by `backend/app/api/v1/warranty_quality.py`.
  * **Insight/Metric Displayed:** Per-vehicle "telematics causal" evidence trail on flagged early-warning paths — a persisted set of stable physical-signal → physical-signal causal edges (e.g. `battery_temperature_c → battery_internal_resistance_ohm`), discovered independently per vehicle and required to recur across multiple vehicles before being trusted, shown with lag, sign, and score/q-value provenance.
  * **Data Mapping:** Raw rows come from `telematics_loader.fetch_vehicle_rows`/`fetch_vehicle_records`, restricted to rows at or after the vehicle's `deliveries.actual_delivery_date` (post-delivery telemetry only). The 17 `TELEMATICS_METRICS` columns above become PCMCI/LPCMCI variables; identity columns ride along only as metadata. Discovered, filtered, cross-vehicle-stable edges are persisted into `telematics_causal_runs`/`telematics_causal_edges` (a live AI-state table populated by this pipeline, not one of the 51 CSV-backed synthetic datasets and out of scope for this document), and that is what the screen actually reads — not this table directly on each page load. **Not read by `mobility-twin.tsx`.**

#### Predictive Modeling Mapping
* **Target Variable:** None single-fixed — full pairwise causal discovery over a per-vehicle physical-signal panel (e.g. battery degradation chains, drivetrain slip chains, ride/shock chains feeding downstream DTC risk).
* **Input Features:** `telematics_loader.TELEMATICS_METRICS` (the 17 physical columns above) — one vehicle at a time, never concatenated across vehicles. `telematics_panel.build_telematics_panel` resamples each vehicle's records to 5-minute buckets (mean, except `impact_g_force` = max), requires ≥288 analytical rows (24h) and ≥90% coverage per column, forward-fills 1-step gaps, drops near-constant/low-information/collinear columns, z-score normalizes, and applies ADF/KPSS-based differencing for non-stationary series (capped at 24 variables). `TelematicsCausalService` runs `run_pcmci_tests`/`run_lpcmci_tests` (LPCMCI default: `tau_max=2`/`pc_alpha=0.10`; PCMCI: `tau_max=12`/`pc_alpha=0.05`) per vehicle, then applies an effect-size floor (`min_abs_score=0.12`) and keeps only edges recurring in ≥25% of eligible vehicles (min 2) with ≥75% sign agreement — this cross-vehicle consensus is what makes an edge "stable" enough to persist. `odometer_km`, `dtc_count`, `warning_flag`, `data_origin`, `generator_version` are explicitly excluded from the feature set.

---

# Section E — Finance & Collections

### 25. Finance Products — `finance_products`
* **Description:** Master catalog of Mahindra Finance lending products (vehicle, tractor, commercial vehicle, SME, personal loans), seeded once as static reference/master data — not customer-linked. Source: `data/synthetic/master/finance_products.csv`. Business purpose: defines the product hierarchy, eligibility bounds (loan amount/tenure/LTV) and pricing floor that `loan_accounts`, `payment_history`, `cross_sell_events` and `collection_cases` all denormalize against for reporting. Only 6 lending products are seeded, spanning `AUTO_FINANCE`, `RURAL_FINANCE`, `COMMERCIAL_FINANCE`, `BUSINESS_FINANCE` and `CONSUMER_FINANCE` categories — the original spec's "Insurance Broking > Motor Insurance, Loan Protection" branch of the product hierarchy is **not present** anywhere in the runtime schema or synthetic data; only the vehicle/rural/commercial/business/consumer lending catalog exists.
* **Primary Key:** `finance_product_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| finance_product_id | TEXT (PK) | Unique product identifier, e.g. `FINPROD_SYN_001`. |
| product_code | TEXT | Short mnemonic code (e.g. `AUTO_LOAN_NEW`, `TRACTOR_LOAN`); denormalized onto every downstream table. |
| product_name | TEXT | Display name shown on Finance product cards, e.g. "New Vehicle Loan", "Tractor Finance". |
| product_category | TEXT | Hierarchy grouping: `AUTO_FINANCE`, `RURAL_FINANCE`, `COMMERCIAL_FINANCE`, `BUSINESS_FINANCE`, `CONSUMER_FINANCE`. |
| secured | BOOLEAN | Whether the product is asset-backed/collateralized (drives `asset_value_inr`/`ltv_pct` presence on `loan_accounts`). |
| min_loan_amount_inr / max_loan_amount_inr | BIGINT | Eligible principal range, INR. |
| min_tenure_months / max_tenure_months | BIGINT | Eligible repayment tenure range, months. |
| base_interest_rate_pct | DOUBLE | Reference/floor annual interest rate; individual `loan_accounts.interest_rate_pct` is priced around this. |
| max_ltv_pct | DOUBLE | Maximum loan-to-value ratio permitted; null for unsecured products (SME, Personal Loan). |
| target_segment | TEXT | Intended customer segment, e.g. `RETAIL_AUTO`, `RURAL_AGRI`, `COMMERCIAL_OPERATOR`, `SME`, `RETAIL_CONSUMER`. |
| active | BOOLEAN | Whether the product is currently offered; Finance screen only lists `active = true` products. |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Finance (`finance.tsx`)
  * **Insight/Metric Displayed:** Product portfolio cards grid (name, customers, risk, cross-sell, opportunity) at the top of the screen.
  * **Data Mapping:** `FinanceService.list_products()` selects `finance_products` WHERE `active = true`, ordered by `product_name`. `customers` = `COUNT(loan_accounts.*)` grouped by `loan_accounts.finance_product_id`. `risk` = `COUNT(payment_history WHERE days_past_due_after_event >= 30) / COUNT(payment_history) * 100` grouped by `payment_history.finance_product_id`, rendered as "X.X% 30+ DPD". `cross` = `COUNT(cross_sell_events.*)` grouped by `offered_finance_product_id`. `opp` = `SUM(cross_sell_events.offer_amount_inr)` grouped by `offered_finance_product_id`, formatted to ₹L/₹Cr.
  * **Insight/Metric Displayed:** "Open" button per product card.
  * **Data Mapping:** None — fires a local toast only; not wired to any `finance_products` field or navigation.

---

### 26. Finance Customers — `finance_customers`
* **Description:** One row per financing customer's profile (identity, geography, employment, income & obligations) — the runtime implementation of the spec's "Golden Finance Customer". Source: `data/synthetic/finance/finance_customers.csv`. Business purpose: the identity/affordability substrate joined into `loan_accounts`, `payment_history`, `cross_sell_events`, `collection_cases` and `collection_interactions` to assemble the Customer Financial Twin and the collections risk evidence base.
* **Primary Key:** `finance_customer_id`
* **Note:** the spec's GoldenFinanceCustomer intent lists `product_holdings`, `outstanding_balance`, `repayment_quality`, `cross_sell_needs` as customer attributes — none of these are persisted columns here; they are computed at query time by joining `loan_accounts` (holdings), `payment_history` (repayment status/DPD) and `cross_sell_events` (cross-sell state) in `FinanceService.get_twin()`, consistent with the spec's "runtime risk and cross-sell scores are derived from underlying evidence, not seeded directly."

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| finance_customer_id | TEXT (PK) | Unique customer identifier, e.g. `FINCUST_SYN_000001`; used as the display "Name" on the Twin and as input to a deterministic UUIDv5 twin id. |
| region_id / region_name / city_id / city_name | TEXT | Geography of residence. |
| employment_type | TEXT | e.g. `SME_OWNER`, `SALARIED` — affordability/segment evidence. |
| rural_urban_segment | TEXT | Geography stratification, e.g. `URBAN`, `SEMI_URBAN`. |
| finance_customer_segment | TEXT | Marketing/product segment, e.g. `SME`, `RETAIL_CONSUMER`; aligns to `finance_products.target_segment`. |
| income_stability | TEXT | Categorical income stability band, e.g. `MEDIUM`, `MEDIUM_HIGH` — core risk evidence surfaced directly on the Twin. |
| monthly_income_inr / monthly_obligations_inr | BIGINT | Reported monthly income / debt obligations, INR. |
| obligation_to_income_ratio | DOUBLE | `monthly_obligations_inr / monthly_income_inr` — key affordability/stress ratio shown in the Twin's risk decomposition. |
| customer_since | TIMESTAMPTZ | Relationship/onboarding start date. |
| active | BOOLEAN | Whether the customer record is live; the Twin index only lists `active = true` customers. |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Finance (`finance.tsx`)
  * **Insight/Metric Displayed:** Customer Financial Twin header (Name, Location, Income stability, Repayment).
  * **Data Mapping:** Name = `finance_customer_id`. Location = `city_name + ", " + region_name`. Income stability = `income_stability` (title-cased). Repayment comes from `payment_history`, not this table.
  * **Insight/Metric Displayed:** Risk decomposition block (`incomeStability`, `obligationToIncome`).
  * **Data Mapping:** `incomeStability` = raw `income_stability` value. `obligationToIncome` = `obligation_to_income_ratio * 100`. (Third row, `maxDpd`, is sourced from `payment_history`.)
  * **Insight/Metric Displayed:** Twin identity resolution (`GET /finance/twins`, `GET /finance/customers/{twin_id}/twin`).
  * **Data Mapping:** `list_twin_summaries()` selects `finance_customer_id` WHERE `active = true`; each twin's URL id is `uuid5(TWIN_NAMESPACE, finance_customer_id)` — a deterministic hash, not a stored UUID column.
  * **Insight/Metric Displayed:** "Explain Recommendation" dialog.
  * **Data Mapping:** Live and evidence-based — three bullets built from the already-computed Twin: latest `payment_history.payment_status`, `income_stability`, and max `payment_history.days_past_due_after_event`.
  * **Insight/Metric Displayed:** "Send for Approval" / "Generate RM Script" buttons.
  * **Data Mapping:** Not supported by canonical data. `submit_twin_approval()` and `generate_rm_script()` unconditionally raise `DomainValidationError` — the frontend only shows optimistic local state and a toast; nothing is read from or written to `finance_customers`.

---

### 27. Loan Accounts — `loan_accounts`
* **Description:** One row per originated/disbursed loan, linking a `finance_customer` to a `finance_product` with the commercial terms (principal, tenure, EMI, LTV) agreed at origination. Source: `data/synthetic/finance/loan_accounts.csv`. Business purpose: the book of live credit exposures that `payment_history`, `cross_sell_events` and `collection_cases` all key off. Note: the spec's loan-account intent lists a `risk_segment` column; the actual runtime table carries none — risk/segmentation is computed downstream instead of stored per loan.
* **Primary Key:** `loan_account_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| loan_account_id | TEXT (PK) | Unique loan identifier. |
| finance_customer_id | TEXT (FK → finance_customers) | Borrower. |
| customer_loan_sequence | BIGINT | Ordinal of this loan among the customer's loans. |
| region_id / region_name / city_id / city_name | TEXT | Denormalized geography at origination. |
| finance_product_id | TEXT (FK → finance_products) | Product financed. |
| product_code / product_name / product_category / target_segment | TEXT | Denormalized copy of the product record at origination. |
| secured | BOOLEAN | Denormalized copy of the product's `secured` flag. |
| application_at / disbursed_at / scheduled_maturity_at | TIMESTAMPTZ | Application submission / disbursement / contractual maturity timestamps. |
| principal_inr | DOUBLE | Disbursed principal amount, INR. |
| interest_rate_pct | DOUBLE | Actual priced annual interest rate for this loan. |
| tenure_months | BIGINT | Contractual tenure, months. |
| emi_amount_inr | DOUBLE | Scheduled monthly EMI. |
| asset_value_inr / ltv_pct | DOUBLE | Financed/collateral asset value and loan-to-value at origination; null for unsecured products. |
| debt_service_ratio_at_origination | DOUBLE | Obligation-coverage ratio computed at underwriting time. |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Finance (`finance.tsx`)
  * **Insight/Metric Displayed:** Product card `customers` count.
  * **Data Mapping:** `COUNT(*)` grouped by `finance_product_id`.
  * **Insight/Metric Displayed:** Customer Twin "Products held" chips.
  * **Data Mapping:** Distinct `product_name` across the customer's `loan_accounts`.
  * **Note:** `get_twin()` fetches every loan-level field (`principal_inr`, `emi_amount_inr`, `ltv_pct`, `interest_rate_pct`, etc.) ordered by `disbursed_at`, but only the deduped `product_name` list is ever used — the rest is fetched and discarded.
* **Screen Name:** Collections (`collections.tsx`)
  * **Data Mapping:** `CollectionsService._case_rows()` joins `loan_accounts` to `collection_cases` on `loan_account_id` and selects `principal_inr`, but this joined value is fetched and **never used** in `CollectionsCaseOut` — dead in the current API output.

#### Predictive Modeling Mapping
* **Target Variable:** EMI amount (`emi`) and a risk tier label (`risk`), shown in the Finance screen's "Simulate Offer" dialog.
* **Input Features:** `backend/app/ai/scoring/emi.py::simulate_offer(amount)` computes `emi = round(amount/36 + amount*0.006)` and hardcodes `risk = "Low"` unconditionally. The **only** input is the user-dragged slider `amount` (₹100K–₹1M); tenure is fixed at 36 months. No column from `loan_accounts` (or `finance_customers`/`payment_history`) — actual product `interest_rate_pct`, customer `income_stability`, `obligation_to_income_ratio`, current DPD — is read or used. The risk output never varies, in contrast to the spec's requirement that risk be evidence-derived.

---

### 28. Payment History — `payment_history`
* **Description:** One row per scheduled installment (EMI) event per loan account — the actual-vs-scheduled repayment ledger. Source: `data/synthetic/finance/payment_history.csv`. Business purpose: the ground-truth repayment evidence trail that drives DPD/arrears calculations feeding both the Finance product risk rate and the Collections case triggers/resolution.
* **Primary Key:** `payment_event_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| payment_event_id | TEXT (PK) | Unique installment-event identifier. |
| loan_account_id | TEXT (FK → loan_accounts) | Loan this installment belongs to. |
| finance_customer_id | TEXT (FK → finance_customers) | Borrower. |
| installment_number | BIGINT | Sequence number of this EMI within the loan's schedule. |
| region_id / region_name / city_id / city_name | TEXT | Denormalized geography. |
| finance_product_id / product_code / product_name / product_category | TEXT | Denormalized product identity. |
| payment_due_at | TIMESTAMPTZ | Contractual due date for this installment. |
| scheduled_payment_amount_inr / scheduled_interest_inr / scheduled_principal_inr | DOUBLE | Contractual EMI amount and its interest/principal split. |
| payment_status | TEXT | Outcome category, e.g. `ON_TIME`; surfaces as the Twin's "Repayment" field. |
| actual_payment_at | TIMESTAMPTZ | Timestamp payment was actually received; null if unpaid. |
| actual_payment_amount_inr | DOUBLE | Amount actually collected for this installment. |
| arrears_recovery_amount_inr | DOUBLE | Portion of this payment that cleared prior arrears (vs. the current installment). |
| payment_delay_days | DOUBLE | Days between due date and actual payment for this installment. |
| days_past_due_after_event | BIGINT | Cumulative loan DPD immediately after this event — the canonical DPD signal used for 30+/90+ bucketing. |
| arrears_amount_inr | DOUBLE | Cumulative arrears balance outstanding after this event. |
| contractual_outstanding_principal_inr / outstanding_principal_inr | DOUBLE | Principal that should remain per schedule / actual remaining principal after this event. |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Finance (`finance.tsx`)
  * **Insight/Metric Displayed:** Product card `risk` badge ("X.X% 30+ DPD").
  * **Data Mapping:** `COUNT(days_past_due_after_event >= 30) / COUNT(*) * 100`, grouped by `finance_product_id`.
  * **Insight/Metric Displayed:** Customer Twin "Repayment" field.
  * **Data Mapping:** Most recent (by `payment_due_at`) `payment_status`, title-cased; falls back to "No payment history" if the customer has none.
  * **Insight/Metric Displayed:** Twin risk decomposition, `maxDpd` row.
  * **Data Mapping:** `MAX(days_past_due_after_event)` across the customer's rows (0 if none).
* **Screen Name:** Collections (`collections.tsx`)
  * **Insight/Metric Displayed:** "Scheduled payment realization" metric tile.
  * **Data Mapping:** `min(100, SUM(actual_payment_amount_inr) / SUM(scheduled_payment_amount_inr) * 100)`, computed platform-wide across **all** `payment_history` rows (not filtered to open collections cases).
  * FK linkage only — `collection_cases.trigger_payment_event_id`/`resolution_payment_event_id` and `collection_interactions.payment_after_contact_event_id` all point back here, but no live API call dereferences the referenced row's own fields.

---

### 29. Cross-Sell Events — `cross_sell_events`
* **Description:** One row per cross-sell/upsell offer extended to an existing finance customer off the back of one of their loan accounts, plus the customer's response. Source: `data/synthetic/finance/cross_sell_events.csv`. Business purpose: the evidence trail for cross-sell opportunity reporting on the Finance product cards and the Customer Twin's Next Best Action block.
* **Primary Key:** `cross_sell_event_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| cross_sell_event_id | TEXT (PK) | Unique offer identifier. |
| finance_customer_id | TEXT (FK → finance_customers) | Customer the offer was made to. |
| source_loan_account_id | TEXT (FK → loan_accounts) | Existing loan that qualified/triggered the offer. |
| source_product_code | TEXT | Product code of the source loan. |
| region_id / region_name / city_id / city_name | TEXT | Denormalized geography. |
| offered_finance_product_id | TEXT (FK → finance_products) | Product being cross-sold. |
| offered_product_code / offered_product_name / offered_product_category | TEXT | Denormalized identity of the offered product. |
| offered_at | TIMESTAMPTZ | When the offer was made. |
| offer_channel | TEXT | Channel used, e.g. `CALL`, `WHATSAPP`. |
| offer_amount_inr / offer_interest_rate_pct / offer_tenure_months | DOUBLE/BIGINT | Proposed loan terms. |
| estimated_offer_emi_inr | DOUBLE | Estimated EMI for the offer. |
| customer_response | TEXT | Outcome, e.g. `INTERESTED`, `DECLINED`. |
| responded_at | TIMESTAMPTZ | When the customer responded; null if no response yet. |
| event_version | TEXT | Offer-generation logic version tag, e.g. `FIN_CROSS_SELL_V1`. |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Finance (`finance.tsx`)
  * **Insight/Metric Displayed:** Product card `cross` ("N recorded offers") and `opp` (opportunity value).
  * **Data Mapping:** `cross` = `COUNT(*)` grouped by `offered_finance_product_id`. `opp` = `SUM(offer_amount_inr)` grouped by `offered_finance_product_id`.
  * **Insight/Metric Displayed:** Customer Twin "Next Best Action" card.
  * **Data Mapping:** The customer's most recent (by `offered_at`) row: `nba.product` = `offered_product_name`, `nba.amount` = `offer_amount_inr`, `nba.channel` = `offer_channel`, `nba.response` = `customer_response`. Falls back to a hardcoded placeholder if the customer has no cross-sell events.
  * **Insight/Metric Displayed:** "Cross-sell propensity" list.
  * **Data Mapping:** Same latest row: `{offer, response}` as plain text. **Caveat:** the frontend's static fallback data implies per-product percentage propensity scores, but the live API never returns a percentage here — no propensity-score computation exists anywhere in `FinanceService`.

---

### 30. Collection Cases — `collection_cases`
* **Description:** One row per delinquency case, opened when a loan account's DPD crosses a trigger threshold on a specific `payment_history` event, tracked from creation through peak severity to resolution. Source: `data/synthetic/collections/collection_cases.csv`. Business purpose: the case-management backbone for the Collections & Recovery AI Swarm — prioritization, roll-forward risk, and headline recovery metrics.
* **Primary Key:** `collection_case_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| collection_case_id | TEXT (PK) | Unique case identifier. |
| loan_account_id | TEXT (FK → loan_accounts) | Delinquent loan. |
| finance_customer_id | TEXT (FK → finance_customers) | Borrower. |
| loan_case_sequence | BIGINT | Ordinal of this case among cases opened on the same loan (repeat delinquency). |
| region_id / region_name / city_id / city_name | TEXT | Denormalized geography. |
| finance_product_id / product_code / product_name / product_category | TEXT | Denormalized product identity. |
| case_created_at | TIMESTAMPTZ | When the case was opened. |
| carried_into_generation_window | BOOLEAN | Generator bookkeeping: whether the case predates the generation window; not surfaced by any endpoint. |
| case_trigger_source | TEXT | What triggered case creation, e.g. `PAYMENT_EVENT`. |
| trigger_payment_event_id | TEXT (FK → payment_history) | The specific installment event whose DPD crossed the delinquency threshold. |
| case_trigger_dpd / observed_dpd_at_trigger_event / dpd_at_case_creation | BIGINT | DPD thresholds/observations around case creation. |
| arrears_at_trigger_event_inr | DOUBLE | Arrears balance at the trigger event. |
| priority_at_creation | TEXT | Initial priority tier, e.g. `LOW`. |
| peak_observed_dpd / peak_observed_arrears_inr | BIGINT/DOUBLE | Worst DPD/arrears ever observed on this case. |
| case_status | TEXT | Current lifecycle status, e.g. `OPEN`, `RESOLVED`. |
| current_dpd | BIGINT | Latest/current DPD — the primary live risk driver. |
| current_arrears_inr | DOUBLE | Latest/current arrears balance. |
| resolved_at | TIMESTAMPTZ | Resolution timestamp; null while open. |
| resolution_payment_event_id | TEXT (FK → payment_history) | The payment event that resolved/cured the case. |
| resolution_type | TEXT | How it resolved, e.g. `PAYMENT_CURE`. |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Collections (`collections.tsx`)
  * **Insight/Metric Displayed:** "Customer Prioritization" table rows and their sort order.
  * **Data Mapping:** `CollectionsService._case_rows()` orders by `current_dpd DESC, current_arrears_inr DESC`. Customer = `finance_customer_id`; DPD = `current_dpd`; **Outstanding column = `current_arrears_inr`** — despite the column header, this is the arrears balance, not `loan_accounts.principal_inr` or a true outstanding-principal figure.
  * **Insight/Metric Displayed:** "Compliance" flag column.
  * **Data Mapping:** `"Review"` if `current_dpd >= 90` else `"OK"` — a single hardcoded DPD threshold, not a distinct compliance-checking model.
  * **Insight/Metric Displayed:** Headline metric tiles — "Open collection cases", "Current arrears", "90+ DPD cases", "Resolved cases".
  * **Data Mapping:** `COUNT(case_status='OPEN')`; `SUM(current_arrears_inr)`; `COUNT(current_dpd >= 90)`; `total_cases − open_cases`.
  * **Insight/Metric Displayed:** Approve / Human-review row actions.
  * **Data Mapping:** Not supported by canonical data — `approve_case()`/`review_case()` unconditionally raise `DomainValidationError`; the row only updates local optimistic UI state.
  * `case_status` is returned by `CollectionsCaseOut` but **not rendered anywhere** in `collections.tsx` — a dead field on this screen.

#### Predictive Modeling Mapping
* **Target Variable:** "Roll-fwd risk" (`roll`) percentage shown per case.
* **Input Features:** `min(100, round(current_dpd / 90 * 100))` — a single-feature deterministic ratio of `current_dpd` against a fixed 90-day ceiling. This does **not** implement the multi-factor evidence-weighted stress formula the spec calls for (`stress = 0.30*normalized_dpd + 0.20*missed_payment_ratio + 0.20*obligation_stress − 0.15*prior_response_score − 0.15*payment_recovery_history + noise`) — only the DPD component is live; missed-payment ratio, obligation stress, prior response score and payment-recovery history, though available in `payment_history`/`collection_interactions`/`finance_customers`, are not incorporated. `_case_rows()` also selects `finance_customers.income_stability` but never uses it.

---

### 31. Collection Interactions — `collection_interactions`
* **Description:** One row per individual contact/collection attempt (call, WhatsApp, field visit, etc.) against a `collection_case`, capturing channel, offer presented, customer response and any resulting payment. Source: `data/synthetic/collections/collection_interactions.csv`. Business purpose: per spec, "the learning evidence for the Collections AI Swarm" — the ground truth used to compute observed recovery likelihood and the trust-ledger audit trail.
* **Primary Key:** `collection_interaction_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| collection_interaction_id | TEXT (PK) | Unique interaction identifier. |
| collection_case_id | TEXT (FK → collection_cases) | Case this contact attempt belongs to. |
| loan_account_id | TEXT (FK → loan_accounts) | Loan in delinquency. |
| finance_customer_id | TEXT (FK → finance_customers) | Borrower contacted. |
| interaction_sequence | BIGINT | Ordinal of this contact attempt within the case. |
| interaction_at | TIMESTAMPTZ | Timestamp of the contact. |
| region_id / region_name / city_id / city_name | TEXT | Denormalized geography. |
| finance_product_id / product_code / product_name / product_category | TEXT | Denormalized product identity. |
| channel | TEXT | Contact channel, e.g. `WHATSAPP`, `CALL`. |
| field_visit_flag | BOOLEAN | Whether this interaction was an in-person field visit. |
| contact_success | BOOLEAN | Whether contact was actually made. |
| dpd_at_interaction / arrears_at_interaction_inr / outstanding_principal_at_interaction_inr | BIGINT/DOUBLE | Loan state at the moment of contact. |
| offer_type | TEXT | Treatment offered during the contact, e.g. `REPAYMENT_PLAN_DISCUSSION`, `NONE`. |
| customer_response | TEXT | Customer's reaction, e.g. `PROMISE_TO_PAY`, `NO_CONTACT`. |
| promise_to_pay / promise_date | BOOLEAN/TIMESTAMPTZ | Whether/when the customer committed to a promise-to-pay. |
| payment_after_contact | BOOLEAN | Whether a payment was subsequently observed following this contact. |
| payment_after_contact_event_id | TEXT (FK → payment_history) | The specific follow-up payment event, if any. |
| payment_after_contact_at / payment_after_contact_amount_inr | TIMESTAMPTZ/DOUBLE | Timestamp/amount of that follow-up payment. |
| payment_after_promise | BOOLEAN | Whether a prior promise-to-pay was actually honored. |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Collections (`collections.tsx`)
  * **Insight/Metric Displayed:** "Agent Swarm" panel cards.
  * **Data Mapping:** `CollectionsService.list_agents()` groups `collection_interactions` by `channel` and returns one card per distinct channel, named `"{Channel} workflow"`. **This does not correspond to the 6 named agents hardcoded in `collections.tsx`'s fallback array** (Risk Prediction Agent, Channel Optimization Agent, Offer Recommendation Agent, Field Route Agent, Compliance Guardrail Agent, Human Review Agent) — those only render if the API call fails.
  * **Insight/Metric Displayed:** "Best channel" and "Action" columns in the Customer Prioritization table.
  * **Data Mapping:** "Best channel" = the case's most recent interaction's `channel`. "Action" = if latest `offer_type` ≠ `"NONE"`, show it; else `"Field review"` if `current_dpd >= 90`, `"Structured contact"` if `>= 30`, else `"Digital reminder"`.
  * **Insight/Metric Displayed:** Headline metric tiles — "Payment after contact", "Promise kept".
  * **Data Mapping:** "Payment after contact" = `COUNT(payment_after_contact=True) / COUNT(*) * 100` platform-wide. "Promise kept" = `COUNT(payment_after_promise=True) / COUNT(promise_to_pay=True) * 100`.
  * **Insight/Metric Displayed:** Trust Ledger dialog.
  * **Data Mapping:** One line per interaction on the selected case: `"{interaction_at}: {channel} — {customer_response}"`. Materially simpler than the frontend's static fallback ledger — no structured "Model output / Compliance check / Human decision" narrative is produced live.
  * **Insight/Metric Displayed:** "Modify Action" dialog options.
  * **Data Mapping:** Static UI strings; submitting calls `modify_case()`, which unconditionally raises `DomainValidationError` — nothing persists.

#### Predictive Modeling Mapping
* **Target Variable:** "Prob." (`observed_probability`) — recovery-likelihood percentage shown per case.
* **Input Features:** `round(COUNT(payment_after_contact = True) / COUNT(*) * 100)` across that case's own interactions — an **empirical historical hit-rate**, not a trained/model-estimated probability. Defaults to 0 for cases with zero interactions.
* **Related but screen-detached model:** `backend/app/ai/simulation/collections_sim.py` (`run()`, exposed at `POST /simulations/collections/run`) implements the spec's "Collections Simulation." **Target Variables:** `recovery_probability`, `cost_of_recovery`, `customer_friction_score`, `net_recovery_value`. **Input Features:** `risk_segment` (Low/Medium/High, fixed lookup table), `channel` (Field/Voice/Digital, fixed cost/friction per channel), `offer` type (Settlement applies a 0.7 discount multiplier), `field` = field-visit intensity 0–100. All four outputs are deterministic lookup-table/formula values, **not fitted from `collection_cases`/`collection_interactions` data**, and this simulator is invoked only from the separate Simulation screen (`simulation.tsx`), **not from `collections.tsx`**.

---

# Section F — Logistics, Circularity & XR

> **Live-path note:** every screen in this section is served exclusively by the `operational_*` services reading `runtime_tables[...]`. The following are dead legacy code — imported by nothing reachable from `api/v1/router.py`: `backend/app/services/circularity.py`, `backend/app/services/logistics.py`, `backend/app/services/overview.py`, `backend/app/services/mobility.py`, `backend/app/repositories/circularity.py`, `backend/app/repositories/logistics.py`, `backend/app/repositories/agent.py`, `backend/app/services/merger.py::merge_xr_experiences`, and the declarative ORM classes `CarbonCredit` (`models/circularity.py`), `LogisticsRoute`/`WarehouseSignal` (`models/logistics.py`), `XrExperience` (`models/agents.py`), `ElvAssessment` (`models/operations.py`). XR is served by `backend/app/api/v1/agents.py`'s `xr_router` (mounted at prefix `/xr`), calling `AiAgentService.list_xr()` — there is no dedicated `xr.py` router file.

### 32. Logistics Route Master — `routes`
* **Description:** Canonical freight-corridor master (e.g. Pune→Mumbai, Mumbai→Delhi). One row per lane between an origin and destination warehouse; source of the baseline cost, transit time and SLA window that shipments on that lane are measured against. Feeds the Logistics AI Control Tower's route cards.
* **Primary Key:** `route_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| route_id | TEXT (PK) | Unique route identifier, e.g. `ROUTE_SYN_001`; joined to `shipments.route_id` and `warehouse_events.route_id`. |
| origin_warehouse_id / origin_warehouse_name | TEXT | Dispatching warehouse. |
| origin_city_id / origin_city_name | TEXT | Origin city. |
| origin_region_id / origin_region_name | TEXT | Origin region. |
| destination_warehouse_id / destination_warehouse_name | TEXT | Receiving warehouse. |
| destination_city_id / destination_city_name | TEXT | Destination city. |
| destination_region_id / destination_region_name | TEXT | Destination region. |
| route_type | TEXT | Corridor class — observed values `INTRA_REGION` / `INTER_REGION`. |
| transport_mode | TEXT | Mode of transport (observed data is `ROAD` only). |
| distance_km | DOUBLE | Route distance in kilometers. |
| typical_transit_hours | DOUBLE | Standard/expected transit duration for the lane. |
| sla_hours | BIGINT | Contractual SLA window for deliveries on this route. |
| baseline_cost_inr | DOUBLE | Standard freight cost baseline for the lane; used as a fallback average cost when a route has no shipments yet. |
| baseline_risk_score | DOUBLE | Pre-computed historical disruption-risk score for the lane. Not currently surfaced by any live endpoint. |
| active | BOOLEAN | Whether the route is in service; inactive routes are excluded from all Logistics queries. |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Logistics (`logistics.tsx`)
  * **Insight/Metric Displayed:** Route card name/title (e.g. "Mumbai → Delhi").
  * **Data Mapping:** `f"{origin_city_name} → {destination_city_name}"`, computed in `OperationalLogisticsService._routes()`.
  * **Insight/Metric Displayed:** "Cost" tile on each route card.
  * **Data Mapping:** `COALESCE(AVG(shipments.baseline_cost_inr), routes.baseline_cost_inr)` for shipments on that `route_id`.
  * *(`distance_km`, `typical_transit_hours`, `sla_hours`, `baseline_risk_score` are read into the row object but not currently surfaced on this screen — see denormalized copies on `shipments` for how they actually reach the UI.)*

#### Predictive Modeling Mapping
See the consolidated **Logistics Delay** model under `shipments` (#34) — `routes` supplies the display name and the cost/SLA baseline used as inputs/fallbacks, but is not itself the row source for the SLA-risk or delay-probability figures.

---

### 33. Warehouse Master — `warehouses`
* **Description:** Master list of Mahindra's regional distribution centers / regional warehouses. Provides capacity and baseline-utilization targets that warehouse event telemetry is compared against on the Logistics Control Tower's "Warehouse Signals" panel.
* **Primary Key:** `warehouse_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| warehouse_id | TEXT (PK) | Unique warehouse identifier, e.g. `WH_SYN_001`. |
| warehouse_name | TEXT | Display name, e.g. "Pune Distribution Hub". |
| city_id / city_name | TEXT | City the warehouse sits in. |
| region_id / region_name | TEXT | Region code. |
| warehouse_type | TEXT | Facility class — observed values `REGIONAL_DISTRIBUTION_CENTER` / `REGIONAL_WAREHOUSE`. |
| storage_capacity_units | BIGINT | Maximum storage capacity, in inventory units. |
| baseline_utilization_pct | DOUBLE | Target/standard utilization ratio (0–1); used as the utilization-signal fallback when a warehouse has no events. |
| daily_throughput_capacity | BIGINT | Maximum units the warehouse can process per day. |
| active | BOOLEAN | Whether the warehouse is currently operating; only active warehouses are queried. |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Logistics (`logistics.tsx`) — "Warehouse Signals" panel
  * **Insight/Metric Displayed:** `{warehouse name} utilization` tile.
  * **Data Mapping:** `COALESCE(AVG(warehouse_events.warehouse_utilization_pct), warehouses.baseline_utilization_pct)`, displayed as a percentage; tone = warning if ≥ 85%, else success.
  * *Note:* `storage_capacity_units` and `daily_throughput_capacity` are loaded but not referenced in any live computation or displayed value.

---

### 34. Shipment Records — `shipments`
* **Description:** Completed-shipment transaction log (every observed row has `shipment_status = DELIVERED`) — one row per unit-load moved along a `route`, carrying disruption-cause flags and the already-realized delay outcome. This is the table that actually powers the "SLA risk" and "Delay prob." figures on every Logistics route card.
* **Primary Key:** `shipment_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| shipment_id | TEXT (PK) | Unique shipment identifier. |
| route_id | TEXT (FK → routes) | Route the shipment traveled. |
| route_type / transport_mode | TEXT | Denormalized copy of route attributes at shipment time. |
| origin_warehouse_id/_name, origin_city_id/_name, origin_region_id/_name | TEXT | Denormalized origin. |
| destination_warehouse_id/_name, destination_city_id/_name, destination_region_id/_name | TEXT | Denormalized destination. |
| distance_km / typical_transit_hours | DOUBLE | Denormalized route distance/transit time. |
| sla_hours | DOUBLE | Contractual SLA window applicable to this shipment. |
| baseline_cost_inr | DOUBLE | Standard cost baseline for this shipment's lane; averaged per route for the "Cost" tile. |
| vehicle_id | TEXT | Vehicle assigned to carry the shipment. |
| units | BIGINT | Quantity of units shipped. |
| priority | TEXT | `LOW` / `NORMAL` / `HIGH` / `CRITICAL`. |
| desired_dispatch_time / dispatch_time | TIMESTAMPTZ | Planned/requested vs. actual dispatch time. |
| expected_arrival / sla_deadline / actual_arrival | TIMESTAMPTZ | System ETA at dispatch / contractual deadline / actual delivery timestamp. |
| weather_disruption / vehicle_breakdown / warehouse_delay / port_delay / customs_delay | BOOLEAN | Disruption-cause flags. |
| dispatch_delay_minutes | DOUBLE | Minutes the actual dispatch ran late vs. `desired_dispatch_time`. One of two OR'd conditions for "delayed shipment." |
| actual_transit_hours / arrival_variance_minutes | DOUBLE | Realized transit duration / variance of actual vs. expected arrival. |
| delay_minutes | DOUBLE | Derived total delay in minutes. The other of two OR'd conditions for "delayed shipment." |
| early_arrival_minutes | DOUBLE | Minutes early, when the shipment beat its ETA. |
| sla_breach | BOOLEAN | Derived flag: whether the shipment breached its `sla_deadline` — the numerator of "SLA risk %". |
| shipment_status | TEXT | Lifecycle status (observed data: `DELIVERED` only — a completed-history dataset, not live in-flight state). |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Logistics (`logistics.tsx`)
  * **Insight/Metric Displayed:** "SLA risk {n}%" pill on each route card.
  * **Data Mapping:** `ROUND(COUNT(shipments WHERE sla_breach = TRUE) / COUNT(shipments) * 100)`, grouped by `route_id`.
  * **Insight/Metric Displayed:** "Delay prob. {n}%" tile.
  * **Data Mapping:** `ROUND(COUNT(shipments WHERE delay_minutes > 0 OR dispatch_delay_minutes > 0) / COUNT(shipments) * 100)`.
  * **Insight/Metric Displayed:** "Rec." (recommendation) tile.
  * **Data Mapping:** Rule-based, not a model: `IF sla_risk >= 25 THEN "Reroute next dispatch via alternate carrier" ELSE "Maintain route with ETA monitoring"` — simpler than the spec's evidence example (no alternate-route capacity/cost comparison implemented).
  * **Insight/Metric Displayed:** "Predict Delay" button.
  * **Data Mapping:** `POST /logistics/routes/{id}/predict-delay` simply recomputes the identical historical-ratio query above — **not** a statistical forecast, a deterministic re-aggregation.
  * **Insight/Metric Displayed:** "Recommend Reroute" / Auto-Heal modal.
  * **Data Mapping:** Sets `rerouted=true` and a static action string; auto-heal returns 5 fixed workflow-step strings that don't match the frontend's hardcoded modal steps.

#### Predictive Modeling Mapping
* **Target Variable:** SLA risk % and Delay probability % (a *historical rate*, not a forward prediction, despite the "Predict Delay" button label).
* **Input Features:** `shipments.sla_breach`, `shipments.delay_minutes`/`dispatch_delay_minutes`, denominated by `COUNT(shipments)` per `route_id`. The cause flags (`weather_disruption`, `vehicle_breakdown`, `warehouse_delay`, `port_delay`, `customs_delay`) are stored but **not** read by any live aggregation — no root-cause attribution is computed.
* **Separate, unwired simulator:** `POST /simulations/logistics-delay/run` → `backend/app/ai/simulation/logistics_delay.py::run()` — **not called from `logistics.tsx`**. **Targets:** `delay` (capped 95), `breach` (SLA breach risk %), `reroute` (fixed string), `cost`. **Inputs:** `warehouse`/`weather`/`vehicle` sliders (0–100), `sla` priority. Formula: `delay = min(95, warehouse*0.3 + weather*0.4 + (100-vehicle)*0.2)`; manually-entered values, not live `shipments` rows.

---

### 35. Warehouse Events — `warehouse_events`
* **Description:** Event-level telemetry per warehouse touchpoint of a shipment (inbound receipt / outbound handoff) — dock occupancy, queue depth, wait/handling times. Source of the per-warehouse congestion and dock-wait signals on the Logistics Control Tower.
* **Primary Key:** `warehouse_event_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| warehouse_event_id | TEXT (PK) | Unique event identifier. |
| shipment_id | TEXT (FK → shipments) | Shipment this warehouse touchpoint belongs to. |
| event_sequence | BIGINT | Ordering of this event within the shipment's warehouse-touch history. |
| route_id | TEXT (FK → routes) | Route the shipment is on. |
| vehicle_id | TEXT | Vehicle associated with the event. |
| event_type / direction | TEXT | `INBOUND_RECEIPT`/`OUTBOUND_HANDOFF`; `INBOUND`/`OUTBOUND`. |
| warehouse_id / warehouse_name, city_id/_name, region_id/_name, warehouse_type | TEXT | Denormalized warehouse context. |
| event_at | TIMESTAMPTZ | Event timestamp. |
| units_moved | BIGINT | Quantity of units handled. |
| inventory_delta_units | BIGINT | Change in warehouse inventory caused by the event. |
| priority | TEXT | Shipment priority carried onto the event. |
| dock_id | TEXT | Dock used for the event. |
| warehouse_utilization_pct | DOUBLE | Point-in-time warehouse utilization (0–1); averaged per warehouse for the "utilization" signal tile. |
| dock_queue_depth | BIGINT | Queue length at the dock at event time. |
| dock_wait_minutes | DOUBLE | Minutes waited at the dock; averaged per warehouse for the "dock wait" signal tile. |
| handling_minutes / picking_delay_minutes / putaway_delay_minutes | DOUBLE | Handling/picking/putaway delay times. |
| congestion_flag | BOOLEAN | Derived flag marking a congested event; numerator of the "congestion %" signal tile. |
| event_status | TEXT | Event lifecycle status (observed data: `COMPLETED` only). |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Logistics (`logistics.tsx`) — "Warehouse Signals" panel
  * **Insight/Metric Displayed:** `{warehouse} congestion` tile (tone: danger ≥ 20%).
  * **Data Mapping:** `COUNT(congestion_flag = TRUE) / COUNT(*) * 100`, grouped by `warehouse_id`.
  * **Insight/Metric Displayed:** `{warehouse} dock wait` tile (tone: warning ≥ 30 min).
  * **Data Mapping:** `AVG(dock_wait_minutes)`, grouped by `warehouse_id`.
  * *Note:* `dock_queue_depth`, `handling_minutes`, `picking_delay_minutes`, `putaway_delay_minutes`, `inventory_delta_units`, `units_moved` are **not** referenced by any live computation today; only `warehouse_utilization_pct`, `congestion_flag`, and `dock_wait_minutes` are actually used.

---

### 36. ELV Assessments — `elv_assessments`
* **Description:** End-of-life-vehicle intake assessment records — condition scoring, documentation and traceability status, and recoverable-material estimates captured when a vehicle enters the circularity pipeline. Feeder table for `rvsf_job_cards`.
* **Primary Key:** `elv_assessment_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| elv_assessment_id | TEXT (PK) | Unique assessment identifier. |
| elv_vehicle_id | TEXT | Unique end-of-life vehicle identifier being assessed. |
| vehicle_model_id / model_name / segment | TEXT | Vehicle model assessed. |
| city_id/_name, region_id/_name | TEXT | Assessment location. |
| assessment_at / assessment_status | TIMESTAMPTZ/TEXT | When assessed; status (observed data: `COMPLETED` only). |
| source_channel | TEXT | Intake channel — `AUCTION`/`DEALER_TRADE_IN`/`FLEET_RETIREMENT`/`OWNER_HANDOVER`. |
| manufacture_year / vehicle_age_years / odometer_km | BIGINT | Vehicle age/usage. |
| accident_history_count / major_accident_flag / flood_exposure_flag | BIGINT/BOOLEAN | Damage history. |
| condition_score / body_condition_score / chassis_integrity_score / powertrain_condition_score / interior_condition_score | DOUBLE | Overall and component condition sub-scores. |
| engine_operable | BOOLEAN | Whether the engine is operable. |
| document_completeness / document_status | DOUBLE/TEXT | Documentation completeness; `COMPLETE`/`PARTIAL`/`INCOMPLETE`. |
| traceability_score / traceability_status | DOUBLE/TEXT | Provenance traceability; `VERIFIED`/`PARTIAL`/`LIMITED`. |
| buyer_demand_index | DOUBLE | Demand-side signal for this vehicle profile. |
| estimated_vehicle_mass_kg | DOUBLE | Estimated total vehicle mass. |
| assessed_reusable_parts_pct / assessed_recyclable_material_pct | DOUBLE | Estimated recoverable-material percentages. |
| battery_present / tyre_set_present / catalytic_converter_present / hazardous_fluids_present | BOOLEAN | Component/hazard presence flags. |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

> **Spec vs. implementation gap:** the spec's ground-truth fields `true_recoverable_value`, `true_elv_value_band`, and `market_scrap_index` do **not** exist in the runtime schema. This is exactly why `POST /circularity/elv/estimate` unconditionally raises a `DomainValidationError` after reporting the runtime schema has no monetary valuation fields.

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Circularity (`circularity.tsx`) — ELV Assessment tab
  * **Insight/Metric Displayed:** "Suggested ELV price" and "Recoverable value" metrics, and risk-flag list.
  * **Data Mapping:** **Not actually sourced from `elv_assessments`.** `useElvEstimate()` always errors (see gap above); the component falls back to a **client-side-only** formula: `price = 80000 - age*3800 + condition*350 + docs*120`; `recoverable = price*0.7`. The only live DB touch is a discarded `SELECT COUNT(*)` — none of the table's 30+ real columns reach the screen.

#### Predictive Modeling Mapping
* **Target Variable:** Suggested ELV price (₹), recoverable value (₹), risk flags.
* **Input Features:** `age`, `condition`, `docs` sliders (analogs of `vehicle_age_years`, `condition_score`, `document_completeness`); `vehicleType` is collected but unused.
* `backend/app/ai/scoring/elv_valuation.py::estimate_elv()` is an exact port of this formula but is **orphaned** — no live route calls it. The frontend independently re-implements identical arithmetic in JavaScript, so this "model" only ever runs in the browser against manually-entered slider values.

---

### 37. RVSF Job Cards — `rvsf_job_cards`
* **Description:** Per-processing-stage work orders at Registered Vehicle Scrapping Facilities (RVSF) — de-pollution and dismantling/recovery stages for each intake vehicle, with recovered-material mass, resource consumption, and quality outcomes. Drives the RVSF Operations Intelligence panel.
* **Primary Key:** `rvsf_job_card_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| rvsf_job_card_id | TEXT (PK) | Unique job-card identifier. |
| elv_assessment_id / elv_vehicle_id | TEXT | Source ELV assessment/vehicle. |
| job_sequence | BIGINT | Ordering of this job/stage within the vehicle's processing history. |
| job_type | TEXT | `DEPOLLUTION_AND_SAFETY` / `DISMANTLING_AND_RECOVERY`. |
| vehicle_model_id / model_name / segment / vehicle_age_years / condition_score | — | Denormalized from the assessment. |
| rvsf_facility_id / rvsf_facility_name, city_id/_name, region_id/_name | TEXT | Facility location. |
| intake_source_channel | TEXT | Denormalized intake channel. |
| job_opened_at / processing_started_at / processing_completed_at | TIMESTAMPTZ | Job timeline. |
| processing_duration_minutes | DOUBLE | Total processing time for this job/stage; averaged for the "Average processing time" tile. |
| stage_input_mass_kg | DOUBLE | Mass entering this processing stage. |
| battery_recovered / battery_recovered_mass_kg | BOOLEAN/DOUBLE | Battery recovery outcome/mass. |
| tyre_set_recovered / tyre_recovered_mass_kg | BOOLEAN/DOUBLE | Tyre recovery outcome/mass. |
| catalytic_converter_recovered / catalytic_converter_mass_kg | BOOLEAN/DOUBLE | Catalytic converter recovery outcome/mass. |
| fluid_drain_completed / hazardous_fluid_liters / hazardous_fluid_mass_kg | BOOLEAN/DOUBLE | Hazardous-fluid draining outcome/volume/mass. |
| removed_component_mass_kg | DOUBLE | Mass of components removed in this stage. |
| reusable_parts_mass_kg | DOUBLE | Mass recovered as reusable; summed for the "Recovered reusable mass" tile. |
| recyclable_material_mass_kg | DOUBLE | Mass recovered as recyclable; summed for the "Recovered recyclable mass" tile. |
| residual_waste_mass_kg / transferred_to_next_stage_kg | DOUBLE | Residual waste / mass transferred forward. |
| labor_hours / energy_consumed_kwh / water_consumed_liters | DOUBLE | Resource consumption. |
| quality_check_passed | BOOLEAN | Whether the job passed QC; `FALSE` count drives the "Quality-check failures" tile. |
| weighbridge_ticket_id | TEXT | Reference to the weighbridge measurement ticket. |
| job_status | TEXT | Lifecycle status (observed data: `COMPLETED` only); drives the "Job-card throughput" tile. |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

> **Spec vs. implementation gap:** the spec's per-stage-minute breakdown (`de_pollution_minutes`, `dismantling_minutes`, `material_sorting_minutes`, `queue_wait_minutes`) and `bottleneck_code`/`compliance_status`/`dmrv_completion_pct` fields are not present — the implementation models each stage as a separate job-card row instead.

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Circularity (`circularity.tsx`) — RVSF Operations tab
  * **Insight/Metric Displayed:** "Job-card throughput" tile → `COUNT(job_status='COMPLETED') / COUNT(*)`.
  * **Insight/Metric Displayed:** "Average processing time" tile → `AVG(processing_duration_minutes)`.
  * **Insight/Metric Displayed:** "Quality-check failures" tile → `COUNT(quality_check_passed = FALSE)`.
  * **Insight/Metric Displayed:** "Recovered reusable mass" tile → `SUM(reusable_parts_mass_kg)`.
  * **Insight/Metric Displayed:** "Recovered recyclable mass" tile → `SUM(recyclable_material_mass_kg)`.
  * *Note:* the frontend's fallback tiles (only shown if the API call fails) invent different tiles — "Bottleneck: De-pollution bay", "dMRV completeness", "Compliance risk" — none of which correspond to the real API's 5 tiles.

---

### 38. dMRV Records — `dmrv_records`
* **Description:** Digital Measurement, Reporting & Verification evidence ledger — one row per audit-evidence item captured against an RVSF job card (weighbridge readings, process logs, chain-of-custody attestations), each with an availability flag and up to 7 integrity sub-flags. This table is the sole data source for the dMRV Copilot tab and for the "traceability"/"closure" figures shown on Credit Marketplace rows.
* **Primary Key:** `dmrv_record_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| dmrv_record_id | TEXT (PK) | Unique evidence-record identifier. |
| rvsf_job_card_id / elv_assessment_id / elv_vehicle_id | TEXT | Job card / assessment / vehicle this evidence supports. |
| evidence_sequence | BIGINT | Ordering of evidence items for the job. |
| evidence_type | TEXT | `MATERIAL_MASS_BALANCE_EVIDENCE` / `PROCESS_EXECUTION_EVIDENCE`. |
| job_type, vehicle_model_id/model_name/segment | — | Denormalized from the job card. |
| rvsf_facility_id / rvsf_facility_name | TEXT | Facility; grouping key for the "which facility has lowest evidence availability" copilot answer. |
| city_id/_name, region_id/_name | TEXT | Denormalized location. |
| measurement_period_start / measurement_period_end | TIMESTAMPTZ | Reporting window covered. |
| dmrv_recorded_at / evidence_observed_at | TIMESTAMPTZ | When the evidence record was captured / when the underlying event occurred. |
| evidence_source_system / measurement_basis | TEXT | Originating system / measurement method. |
| source_reference_id | TEXT | Pointer to the underlying source document. |
| evidence_available | BOOLEAN | **Core availability flag** — the numerator for every dMRV coverage % computed across this section. |
| evidence_status / missing_reason_code | TEXT | `CAPTURED`/`MISSING`; reason code when missing. |
| source_reference_present / evidence_attachment_present / timestamp_verified / digital_signature_present / operator_identity_present / chain_of_custody_present / measurement_calibration_present | BOOLEAN | 7 integrity sub-flags. |
| source_job_quality_check_passed | BOOLEAN | Denormalized copy of the source job card's `quality_check_passed`. |
| observed_processing_duration_minutes, observed_labor_hours, observed_energy_consumed_kwh, observed_water_consumed_liters, observed_stage_input_mass_kg, observed_battery_recovered_mass_kg, observed_tyre_recovered_mass_kg, observed_catalytic_converter_mass_kg, observed_hazardous_fluid_liters, observed_hazardous_fluid_mass_kg, observed_removed_component_mass_kg, observed_reusable_parts_mass_kg, observed_recyclable_material_mass_kg, observed_residual_waste_mass_kg, observed_transferred_to_next_stage_kg | DOUBLE | dMRV-observed counterparts to the job card's own metrics — not read by any live query. |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

> **Spec vs. implementation gap:** the spec's simpler carbon-accounting field list (`material_type`, `material_weight`, `recovery_percentage`, `carbon_factor`, `carbon_credit_estimate`, `verification_status`, `audit_status`, `verified_at`) does not exist here — dMRV is instead modeled as an **evidence-completeness/audit-trail ledger**. The carbon-credit quantity/price math lives entirely in `credit_listings`.

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Circularity (`circularity.tsx`) — RVSF Operations tab
  * **Insight/Metric Displayed:** "dMRV evidence coverage" tile (tone: success ≥ 95%, else warning).
  * **Data Mapping:** `COUNT(evidence_available = TRUE) / COUNT(*) * 100` across all `dmrv_records`.
* **Screen Name:** Circularity (`circularity.tsx`) — dMRV Copilot tab
  * **Insight/Metric Displayed:** Answer to "Which facility has the lowest evidence availability?"
  * **Data Mapping:** `GROUP BY rvsf_facility_name`, compute `COUNT(evidence_available=TRUE)/COUNT(*)` per facility, return the minimum.
  * **Insight/Metric Displayed:** Answer to any other free-text question.
  * **Data Mapping:** `COUNT(evidence_available=TRUE)` vs. `COUNT(*)` overall — a generic fallback answer, not genuine NL understanding. Only 3 fixed prompts are ever offered.
  * *Note:* All 15 `observed_*` measurement columns are not read by any live query — only `evidence_available` and `rvsf_facility_name` groupings are actually used.

---

### 39. Carbon Credit Listings — `credit_listings`
* **Description:** Marketplace listing for a carbon/material-recovery credit generated from one or more RVSF jobs — pricing, buyer interest, and the aggregated recovery mass and dMRV-evidence-completeness counts backing the claim. Powers the Credit Marketplace table end-to-end.
* **Primary Key:** `carbon_credit_listing_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| carbon_credit_listing_id | TEXT (PK) | Unique listing identifier; displayed as "Credit ID." |
| elv_assessment_id / elv_vehicle_id | TEXT | Source vehicle assessment. |
| vehicle_model_id/model_name/segment | — | Denormalized vehicle identity. |
| rvsf_facility_id/_name, city_id/_name, region_id/_name | TEXT | Originating facility/location. |
| credit_type | TEXT | `MIXED_CIRCULARITY` / `RECYCLING_AVOIDANCE` / `REUSE_AVOIDANCE`; title-cased for "Type". |
| credit_unit | TEXT | Unit of measure (observed data: `TCO2E` only). |
| claim_basis / claim_basis_version | TEXT | Claim methodology and its version. |
| credit_vintage_start_at / credit_vintage_end_at | TIMESTAMPTZ | Vintage period covered. |
| listing_at | TIMESTAMPTZ | Marketplace listing timestamp; listings sorted by this, descending. |
| listing_status | TEXT | Lifecycle status (observed data: `OPEN` only). |
| seller_claimed_quantity_tco2e / minimum_trade_quantity_tco2e | DOUBLE | Claimed quantity / minimum tradeable lot size. |
| market_reference_price_per_tco2e_inr / seller_ask_price_per_tco2e_inr | DOUBLE | Reference price / seller asking price, displayed as "Price". |
| buyer_inquiry_count / buyer_bid_count | BIGINT | Buyer interest counts. |
| highest_bid_price_per_tco2e_inr | DOUBLE | Top bid price received; numerator of "Buyer match %". |
| source_rvsf_job_count / source_rvsf_quality_pass_count | BIGINT | Number of backing jobs / how many passed QC. |
| reusable_parts_mass_kg, recyclable_material_mass_kg, residual_waste_mass_kg, recovered_component_mass_kg | DOUBLE | Aggregated recovery masses backing the claim. |
| total_process_energy_kwh / total_process_water_liters | DOUBLE | Aggregated resource consumption. |
| source_dmrv_record_count / dmrv_expected_records / dmrv_available_records / dmrv_missing_records | BIGINT | dMRV evidence counts; `available/expected` = "Closure prob. %". |
| dmrv_source_reference_records, dmrv_attachment_records, dmrv_timestamp_verified_records, dmrv_signature_records, dmrv_operator_identity_records, dmrv_chain_of_custody_records, dmrv_calibration_records | BIGINT | 7 integrity-dimension counts summed into "Traceability %". |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

> **Spec vs. implementation gap:** the spec's `quantity`, `price_floor`, `price_ceiling`, `traceability_score`, `verification_readiness`, `buyer_demand_index`, `buyer_match_score`, `closed_at`, `closure_price`, `closure_status` do not exist as stored columns — `traceability_score`, closure %, and buyer-match % are instead **derived in the API layer** from the dMRV counts and ask/bid prices. Every observed row is `OPEN`, so no closure-outcome column is ever actually populated.

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Circularity (`circularity.tsx`) — Credit Marketplace tab
  * **Insight/Metric Displayed:** "Buyer match" column → `min(100, round(highest_bid_price_per_tco2e_inr / seller_ask_price_per_tco2e_inr * 100))`.
  * **Insight/Metric Displayed:** "Closure prob." column → `round(dmrv_available_records / dmrv_expected_records * 100)`.
  * **Insight/Metric Displayed:** "Traceability" column → `round(SUM(the 7 dmrv_*_records) / (dmrv_expected_records * 7) * 100)`.
  * **Insight/Metric Displayed:** "Reprice" / "Match Buyer" buttons.
  * **Data Mapping:** Both fetch the credit (real DB read) then **unconditionally raise** `DomainValidationError`; the frontend shows a success toast optimistically regardless.
  * **Insight/Metric Displayed:** "ESG Report" / "Trace" buttons — no API call, pure client-side toasts.

#### Predictive Modeling Mapping
* **Target Variable:** Buyer match %, Closure probability %, Traceability % — all deterministic ratio calculations over pre-aggregated columns, not a trained model.
* **Separate, unwired simulator:** `POST /simulations/credit-pricing/run` → `backend/app/ai/simulation/credit_pricing.py::run()` — **not wired into the Credit Marketplace tab**. **Targets:** `price` (→ price band ∓60), `closure`, `match`, `compliance_risk`. **Inputs:** `supply`/`demand`/`trace`/`verif` sliders (10–100); `credit_type` label-only. Manually-entered slider values, not live `credit_listings` rows.

---

### 40. XR Experience Catalog — `xr_experiences`
* **Description:** Master catalog of the four AR/VR/XR experience types Mahindra offers (Virtual Showroom, 3D Configurator, AR Repair Guide, VR Sales Training), with device mode, target persona, and supported-feature flags. Source of the XR screen's experience cards.
* **Primary Key:** `experience_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| experience_id | TEXT (PK) | Unique experience identifier, e.g. `XR_EXP_01`. |
| experience_type | TEXT | Experience name (drives the card title). |
| experience_category | TEXT | `CUSTOMER_SALES` / `TECHNICIAN_SUPPORT` / `DEALER_TRAINING`. |
| primary_persona_group | TEXT | `CUSTOMER` / `TECHNICIAN` / `DEALER_SALES`. |
| device_mode | TEXT | `IMMERSIVE_WEB` / `INTERACTIVE_3D` / `AR_MOBILE_OR_HEADSET` / `VR_HEADSET`. |
| supports_ai_assistant / supports_configuration / supports_training_score / supports_repair_steps | BOOLEAN | Feature flags shown as a comma-joined feature line. |
| active | BOOLEAN | Whether the experience is currently offered. |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** XR (`xr.tsx`)
  * **Insight/Metric Displayed:** Experience card title / "use" description / feature line.
  * **Data Mapping:** `AiAgentService.list_xr()`, filtered `active = TRUE`, ordered by `experience_id`; title = `experience_type`; description = `experience_category.title()`; feature line = comma-joined true feature flags.
  * **Insight/Metric Displayed:** Green "impact" line (e.g. "+18% online-to-visit conversion").
  * **Data Mapping:** **Not derived from any data.** The live API always returns the literal string `"No measured impact is available in runtime_0001"` — real numbers only appear in the frontend's static fallback constant when the API call fails/is disabled. Direct gap against the spec's "business impact should be derived from session/outcome statistics" — no live code path computes impact from `xr_sessions`.
  * **Insight/Metric Displayed:** "Launch Demo" dialogs — 100% static client-side content, zero API calls.

---

### 41. XR Session Records — `xr_sessions`
* **Description:** Per-session usage log for each XR experience — engagement duration, AI-assistant interaction count, configuration/training/repair outcomes, and a final conversion or completion outcome label. Defined and populated in the runtime schema but **entirely unused by the live application**.
* **Primary Key:** `session_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| session_id | TEXT (PK) | Unique session identifier. |
| experience_id | TEXT (FK → xr_experiences) | The experience this session belongs to. |
| experience_type / experience_category / device_mode | — | Denormalized from `xr_experiences`. |
| vehicle_model_id/model_name/segment | — | Vehicle model featured in the session. |
| persona | TEXT | e.g. `PROSPECT_CUSTOMER`, `EXISTING_OWNER`, `APPRENTICE_TECHNICIAN`, `SALES_CONSULTANT`. |
| started_at / completed_at | TIMESTAMPTZ | Session timeline. |
| engagement_seconds | BIGINT | Total session duration/engagement. |
| configuration_selected | TEXT | Configuration chosen, for Configurator sessions. |
| assistant_interactions | BIGINT | Count of AI-assistant interactions during the session. |
| training_score | DOUBLE | Training score, for VR Sales Training sessions. |
| repair_steps_completed / repair_steps_total | DOUBLE | Repair-step completion, for AR Repair sessions. |
| conversion_or_completion_outcome | TEXT | `ABANDONED`, `BOOKING_INTENT`, `CONFIGURATION_SAVED`, `ESCALATED_TO_SENIOR_TECHNICIAN`, `EXPERIENCE_COMPLETED`, `REPAIR_COMPLETED`, `REPAIR_PARTIAL`, `TEST_DRIVE_INTENT`. |
| data_origin / generator_version | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** XR (`xr.tsx`) — **genuinely unused.** No service, router, or repository ever selects from this table, and no frontend hook references it. The XR screen's "impact" metrics (which conceptually should be computed from `engagement_seconds`, `training_score`, `repair_steps_completed`/`_total`, and `conversion_or_completion_outcome`) are instead either a static "No measured impact" string (live API) or hardcoded marketing copy (frontend fallback). This table represents a clear, currently-unrealized opportunity to compute real engagement/conversion KPIs.

#### Predictive Modeling Mapping
* Omitted — no model, simulation, or aggregation in the codebase reads this table.

---

# Section G — Governance, Trust, Agents & Simulation

> **How to read this section:** the single biggest finding governing this whole domain: **only two of the eight governance/agent runtime tables are ever read by a live FastAPI endpoint** — `trust_decisions`/`compliance_checks` (via `TrustService`) and `agent_events` (via `AiAgentService`). `audit_events`, `human_reviews`, `action_outcomes`, `agent_workflow_runs`, and — most surprisingly — `recommendations` itself, are fully populated by the synthetic generator (with real FK linkage to each other) but are **never selected by any service, repository, or route**. Where the frontend appears to write governance state (Approve/Reject/Escalate on Trust, Approve/Human-Review on the Executive Overview), the backend explicitly rejects or no-ops the write rather than persisting it — documented per-table below, not assumed.

### 42. Compliance Trust Ledger — `trust_decisions`
* **Description:** One row per governed AI decision — the outcome of running a `recommendations` row through the compliance/human-approval pipeline (APPROVED or REJECTED, via AUTOMATED_POLICY or HUMAN_REVIEW). Denormalizes the source recommendation's confidence/risk for fast listing and rolls up its child `compliance_checks` into pass/warn/fail counts. Source: `data/synthetic/governance/trust_decisions.csv` (2,000 rows). **Live** — the sole data source for the Trust screen's decision table.
* **Primary Key:** `decision_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `decision_id` | TEXT (PK) | Stable decision code, e.g. `DECISION_SYN_0000001`. |
| `recommendation_id` | TEXT (FK → `recommendations`) | The recommendation this decision adjudicates. Not resolved back to the `recommendations` row by any live query. |
| `domain` | TEXT | `AUTO`, `CIRCULARITY`, `COLLECTIONS`, `FINANCE`, `LOGISTICS`. |
| `use_case` | TEXT | e.g. `DEALER_ALLOCATION_OPTIMIZATION`, `COLLECTIONS_RECOVERY`, `ROUTE_SLA_MITIGATION`, `FINANCIAL_CROSS_SELL_FOLLOWUP`, `CREDIT_AND_DMRV_OPTIMIZATION`. Title-cased into the "Use Case" column. |
| `target_entity_type` / `target_entity_id` | TEXT | The affected operational record, e.g. `ALLOCATION` / `ALLOC_SYN_000033`. |
| `recommendation_type` | TEXT | e.g. `RECOMMEND_DEALER_INVENTORY_REBALANCE`. Title-cased into the "Recommendation" column. |
| `recommendation_confidence` | DOUBLE | Model confidence (0–1) copied from `recommendations.confidence`; rendered as a rounded percentage. |
| `recommendation_risk_level` | TEXT | `LOW`/`MEDIUM`/`HIGH`, copied from `recommendations.risk_level`; rendered as the "Risk" pill. |
| `decision_mode` | TEXT | `AUTOMATED_POLICY` or `HUMAN_REVIEW`. Not surfaced in the UI. |
| `decision` | TEXT | `APPROVED` or `REJECTED` — the actual governance outcome. Title-cased into the "Approval" pill. |
| `decided_at` | TIMESTAMPTZ | When the decision was made; ledger rows are ordered newest-first by this column. |
| `compliance_checks_count` / `compliance_pass_count` / `compliance_warn_count` / `compliance_fail_count` / `compliance_review_required_count` | BIGINT | Rolled-up child `compliance_checks` counts; `compliance_fail_count` drives the "Audit" pill to "Failed" when > 0. |
| `human_review_required` | BOOLEAN | Whether this decision needed a human reviewer. |
| `human_review_id` | TEXT (FK → `human_reviews`) | Set only when `human_review_required` is true (300 of 2,000 rows); never resolved back to `human_reviews` by any live query. |
| `review_priority_score` | DOUBLE | 0–1 triage priority for the review backlog. Not surfaced in the UI. |
| `decision_reason_code` | TEXT | e.g. `AUTO_APPROVED_POLICY_PASS`, `HIGH_RISK_LOW_EVIDENCE_CONFIDENCE`, `HUMAN_REVIEW_APPROVED`. Not surfaced in the UI. |
| `data_origin` / `generator_version` | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Trust (`trust.tsx`)
  * **Insight/Metric Displayed:** "Recent AI Decisions" table — Decision ID, Use Case, Recommendation, Confidence, Approval, Risk, Audit columns.
  * **Data Mapping:** `GET /trust/decisions` → `TrustService.list_decisions()` selects every row ordered by `decided_at DESC` (no pagination — all 2,000 rows returned and rendered client-side). `conf = round(recommendation_confidence * 100)`; `audit = "Failed" if compliance_fail_count>0 else "Review Required" if (human_review_required or compliance_review_required_count>0) else "Passed"`.
  * **Insight/Metric Displayed:** "Lineage" modal.
  * **Data Mapping:** **Not backed by any API call.** Built entirely client-side from the already-loaded row plus two hardcoded static lines. The backend does expose `GET /trust/decisions/{code}/lineage` (see `compliance_checks`), but the frontend never calls it — an orphaned endpoint.
  * **Insight/Metric Displayed:** Approve / Reject / Escalate row actions.
  * **Data Mapping:** All three call `POST /trust/decisions/{code}/approve|reject|escalate`, and **all three raise a `DomainValidationError` server-side** — "Canonical trust decisions are immutable audit records" / escalation "must be recorded through canonical human_reviews." No row is ever mutated or created; the UI's local state optimistically flips the pill regardless.

#### Predictive Modeling Mapping
* `recommendation_confidence`/`recommendation_risk_level` are not computed here — a straight copy-through of `recommendations.confidence`/`.risk_level` at decision time. See `recommendations` (#47) for the underlying evidence features.

---

### 43. Compliance Rule Checks — `compliance_checks`
* **Description:** One row per canonical rule evaluated against a `trust_decisions` row (5 rules × 2,000 decisions = 10,000 rows). The actual rule-evaluation evidence backing the ledger's aggregate pass/warn/fail counts. Source: `data/synthetic/governance/compliance_checks.csv`. **Live** — powers the Trust screen's "Compliance Rules" sidebar, and backs an orphaned lineage endpoint.
* **Primary Key:** `compliance_check_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `compliance_check_id` | TEXT (PK) | Row identifier, e.g. `COMPCHK_SYN_00000001`. |
| `decision_id` | TEXT (FK → `trust_decisions`) | The decision this check was evaluated against. |
| `recommendation_id` | TEXT (FK → `recommendations`) | The recommendation under evaluation. |
| `domain` | TEXT | Business domain. |
| `rule_code` | TEXT | The rule identifier actually implemented: `LINEAGE_INTEGRITY`, `EVIDENCE_SUFFICIENCY`, `FAIRNESS_INPUT_SCOPE`, `BUSINESS_POLICY_ALIGNMENT`, `HUMAN_CONTROL_GATE`. **Note:** the product spec names a different canonical set (`CONSENT_CHECK`, `BIAS_FAIRNESS_CHECK`, `REGULATORY_RULE_CHECK`, `BUSINESS_POLICY_CHECK`, `AUDIT_TRAIL_COMPLETE`) — same cardinality (5) and intent, but the implemented codes are authoritative; the spec's names never appear in data or code. |
| `rule_name` | TEXT | Human-readable label, e.g. "Data lineage integrity". What the Trust sidebar actually displays as `label`. |
| `checked_at` | TIMESTAMPTZ | When the check ran; used to order lineage steps. |
| `result` | TEXT | `PASS` or `REVIEW_REQUIRED` in the current data (schema also anticipates `WARN`/`FAIL`, which do not occur in this snapshot). |
| `severity` | TEXT | `INFO`, `MEDIUM`, or `HIGH`. Not surfaced in the UI. |
| `reason` | TEXT | Free-text explanation. Rendered as the `detail` of each lineage step in the orphaned lineage endpoint. |
| `evidence_json` | TEXT | JSON-encoded object with the specific record(s) the rule inspected. Not parsed/surfaced anywhere. |
| `data_origin` / `generator_version` | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Trust (`trust.tsx`)
  * **Insight/Metric Displayed:** "Compliance Rules" sidebar panel (label + status pill).
  * **Data Mapping:** `GET /trust/compliance-rules` selects `rule_code, rule_name, result` for **every** row (all 10,000, not scoped to any single decision), groups by `(rule_code, rule_name)`, and picks the worst-priority `result` across the group's entire history (an all-time worst-case status, not "right now"). When unresolved, `trust.tsx` falls back to a hardcoded `RULES_FALLBACK` array with invented labels that don't correspond to the real `rule_code` vocabulary.
  * **Insight/Metric Displayed:** Six-step decision lineage (orphaned backend capability).
  * **Data Mapping:** `GET /trust/decisions/{code}/lineage` selects all checks for one `decision_id`, ordered by `checked_at`, formatted as `{step, title, detail}`. **Implemented but never called from the frontend.**

#### Predictive Modeling Mapping
* Omitted — records deterministic rule evaluations, not model output.

---

### 44. Immutable Audit Log — `audit_events`
* **Description:** A hash-chained, append-only event log (`previous_event_hash` → `event_hash`) recording every governance milestone for a recommendation/decision — the literal implementation of the spec's "ordered lineage events" concept, though with a narrower event vocabulary than the spec describes. Source: `data/synthetic/governance/audit_events.csv` (10,000 rows). **Confirmed dead in the live backend** — no service, repository, or route reads this table outside its own schema definition.
* **Primary Key:** `audit_event_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `audit_event_id` | TEXT (PK) | Row identifier, e.g. `AUDIT_SYN_00000001`. |
| `recommendation_id` / `decision_id` | TEXT (FK) | The recommendation/decision this event pertains to. |
| `domain` / `use_case` | TEXT | Business domain / use case, same vocabulary as `trust_decisions`. |
| `target_entity_type` / `target_entity_id` | TEXT | The affected operational record. |
| `event_sequence` | BIGINT | Ordinal position of this event within the decision's audit trail. |
| `event_type` | TEXT | `RECOMMENDATION_RECORDED`, `TRUST_DECISION_RECORDED`, `COMPLIANCE_CHECK_RECORDED`, `COMPLIANCE_EVALUATION_COMPLETED`, `HUMAN_REVIEW_REQUESTED`, `HUMAN_REVIEW_COMPLETED`. (Narrower than the spec's 10-stage `DATA_FETCHED…LEARNING_EVENT_CREATED` vocabulary — no action-execution or outcome-capture event types exist here.) |
| `event_at` | TIMESTAMPTZ | When the event occurred. |
| `actor_type` / `actor_id` | TEXT | `SYSTEM`/`HUMAN`; who/what performed it, e.g. `RECOMMENDATION_ENGINE`, `COMPLIANCE_AGENT`, `FINANCIAL_SERVICES_RISK_REVIEWER`. |
| `source_record_type` / `source_record_id` | TEXT | The governance record type/id that generated this event. |
| `event_status` | TEXT | Status label, e.g. `RECORDED`. |
| `event_summary` | TEXT | Human-readable one-liner. |
| `details_json` | TEXT | JSON-encoded payload with supporting fields. |
| `previous_event_hash` / `event_hash` | TEXT | Tamper-evidence hash chain (`GENESIS` for the first event of a decision). |
| `data_origin` / `generator_version` | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Not used anywhere.** No screen surfaces `audit_events` data, and no backend endpoint reads this table. It exists purely as populated synthetic ground truth.

---

### 45. Human Reviews — `human_reviews`
* **Description:** One row per decision that was actually routed to a human reviewer (300 of the 2,000 `trust_decisions`), capturing the reviewer's role and final call — the direct implementation of the spec's human-in-the-loop items. Source: `data/synthetic/governance/human_reviews.csv`. **Confirmed dead in the live backend** — the only occurrence of the string `human_reviews` outside its schema definition is inside an error message in `services/trust.py`.
* **Primary Key:** `review_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `review_id` | TEXT (PK) | Row identifier, e.g. `HREV_SYN_0000001`. |
| `decision_id` / `recommendation_id` | TEXT (FK) | The decision/recommendation reviewed. |
| `reviewer_role` | TEXT | `AUTO_OPERATIONS_REVIEWER`, `COLLECTIONS_GOVERNANCE_REVIEWER`, `ESG_COMPLIANCE_REVIEWER`, `FINANCIAL_SERVICES_RISK_REVIEWER`, `LOGISTICS_CONTROL_TOWER_REVIEWER` — one role per domain. |
| `requested_at` / `completed_at` | TIMESTAMPTZ | Review timeline. |
| `decision` | TEXT | `APPROVED` or `REJECTED` (data does not contain `MODIFIED`/`ESCALATED`, though the spec anticipates them). |
| `reason_code` | TEXT | `HUMAN_REVIEW_APPROVED` or `HIGH_RISK_LOW_EVIDENCE_CONFIDENCE`. |
| `free_text` | TEXT | Reviewer's narrative justification. |
| `data_origin` / `generator_version` | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Not used anywhere.** The Trust screen's "Escalate" button is the closest UI concept, but it raises an error rather than writing a `human_reviews` row (see `trust_decisions`, #42).

---

### 46. Action Outcomes — `action_outcomes`
* **Description:** One row per recommendation that was actually executed (864 rows — a strict subset of the 1,000 `agent_workflow_runs`), recording the execution status and business-outcome capture. The closest implemented artifact to the spec's "Action → Outcome" learning-loop chain, though the current data only captures the immediate execution step, not downstream business outcomes (`business_outcome_observed` is `False` for every observed row). Source: `data/synthetic/governance/action_outcomes.csv`. **Confirmed dead in the live backend.**
* **Primary Key:** `action_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `action_id` | TEXT (PK) | Row identifier, e.g. `ACTION_SYN_0000001`. |
| `workflow_run_id` | TEXT (FK → `agent_workflow_runs`) | The agent workflow run that executed this action. |
| `recommendation_id` / `decision_id` | TEXT (FK) | The recommendation acted on / governing decision. |
| `domain` | TEXT | Business domain. |
| `target_entity_type` / `target_entity_id` | TEXT | The operational record acted on. |
| `action_type` | TEXT | Reuses the `recommendation_type` vocabulary. |
| `action_status` | TEXT | Only `EXECUTED` occurs (rows only exist for executed actions). |
| `outcome_type` / `outcome_value` / `outcome_scope` | TEXT | Only `ACTION_EXECUTION_STATUS`/`EXECUTED`/`IMMEDIATE_EXECUTION` occur — i.e. the "outcome" captured today is execution success, not a business result. |
| `business_outcome_observed` | BOOLEAN | Whether a downstream business result was observed; `False` in every sampled row. |
| `business_outcome_note` | TEXT | Explains the gap, e.g. "Immediate execution evidence only; workflow.py does not infer downstream business impact." |
| `observed_at` | TIMESTAMPTZ | When this outcome record was captured. |
| `data_origin` / `generator_version` | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Not used anywhere.** No screen reads this table and no backend service queries it.

---

### 47. AI Recommendations (Governance) — `recommendations`
* **Description:** The canonical anchor of the entire governance chain — every `trust_decisions`, `compliance_checks`, `human_reviews`, `audit_events`, `agent_events`, `agent_workflow_runs`, and `action_outcomes` row FKs back to a `recommendation_id` here. 2,000 rows, one `evidence_json` blob and `expected_impact` blob per recommendation, matching the spec's recommendation schema almost field-for-field. Source: `data/synthetic/governance/recommendations.csv`. **Confirmed dead as a read path** — the most consequential finding in this domain: **the Executive Overview's "Top AI Recommendations Today" panel (`index.tsx`) does NOT read this table at all**, despite the UI implying an end-to-end governed recommendation feed.
* **Primary Key:** `recommendation_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `recommendation_id` | TEXT (PK) | Row identifier, e.g. `REC_SYN_0000001`. |
| `domain` | TEXT | `AUTO`, `CIRCULARITY`, `COLLECTIONS`, `FINANCE`, `LOGISTICS`. |
| `use_case` | TEXT | One of `DEALER_ALLOCATION_OPTIMIZATION`, `COLLECTIONS_RECOVERY`, `ROUTE_SLA_MITIGATION`, `FINANCIAL_CROSS_SELL_FOLLOWUP`, `CREDIT_AND_DMRV_OPTIMIZATION` — one per domain. |
| `target_entity_type` / `target_entity_id` | TEXT | The operational record the recommendation targets, e.g. `ALLOCATION` / `ALLOC_SYN_000033`. |
| `recommendation_type` | TEXT | The specific recommended action code, e.g. `RECOMMEND_DEALER_INVENTORY_REBALANCE`. |
| `generated_at` | TIMESTAMPTZ | When the recommendation was generated. |
| `evidence_json` | TEXT | JSON-encoded feature snapshot backing the recommendation — see Predictive Modeling Mapping. |
| `expected_impact` | TEXT | JSON-encoded `{basis, direction, metric}`. |
| `confidence` | DOUBLE | 0–1 model/rule confidence; copied downstream into `trust_decisions.recommendation_confidence`. |
| `risk_level` | TEXT | `LOW`/`MEDIUM`/`HIGH`; copied downstream into `trust_decisions.recommendation_risk_level`. |
| `status` | TEXT | Only `PROPOSED` occurs (the spec's `APPROVED`/`HUMAN_REVIEW`/`REJECTED`/`EXECUTED` states live instead on `trust_decisions.decision`/`agent_workflow_runs.action_status`, not here). |
| `data_origin` / `generator_version` | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Executive Overview (`index.tsx`)
  * **Insight/Metric Displayed:** "Top AI Recommendations Today" cards (title, impact, confidence, risk).
  * **Data Mapping:** `GET /overview/recommendations` → `OperationalOverviewService.list_recommendations()` — **this method never touches `recommendations`.** It synthesizes up to four ad-hoc recommendation cards live from operational aggregates instead: a `shipment-intervention` card from `shipments` (SLA breach count/rate), a `finance-intervention` card from `finance_applications` (manual-review + pending count/rate), a `cancellation-intervention` card from `cancellations` (leading cancellation reason share), and a `dmrv-intervention` card from `dmrv_records` (evidence-completeness rate). The governance `recommendations` table's rich `evidence_json`/`expected_impact`/`recommendation_type` content is entirely bypassed.
  * **Data Mapping (Approve / Human Review buttons):** `PATCH /recommendations/{rec_code}` re-runs `list_recommendations()`, finds the matching synthetic card by its slug id (e.g. `"shipment-intervention"`, not a `REC_SYN_*` id), and returns a copy with the new status. The method's own docstring states it "does not fabricate a database recommendation row" — **no `recommendations` row, nor any other table, is ever written**, despite the frontend's success toast implying persistence.

#### Predictive Modeling Mapping
* **Target Variable:** `confidence` (0–1) and `risk_level` (LOW/MEDIUM/HIGH) — though currently unserved to any screen, this is the authoritative scored-output schema for a governed recommendation.
* **Input Features:** Drawn from `evidence_json`, observed on the `DEALER_ALLOCATION_OPTIMIZATION` use case: `derived_dealer_inventory_pressure`, `derived_batch_inventory_pressure`, `derived_demand_component`, `derived_wait_component`, `regional_demand_index`, `fulfillment_ratio`, `waiting_list`, `allocation_priority`/`allocation_priority_score`, `dealer_capacity`, `inventory_before`/`inventory_after`, `production_batch_inventory_before`/`after` — i.e. exactly the `allocations` table columns (see Section B, #12). Each is a named, explainable feature (not an opaque embedding), corroborated by `agent_events` rows where the `Prediction Agent` step is marked `SKIPPED` with `skip_reason: "NO_LINKED_RUNTIME_PREDICTION_ARTIFACT"`, indicating these scores are rule/heuristic-derived from the evidence features rather than a trained ML model's output.

---

### 48. Agent Runtime Events — `agent_events`
* **Description:** One row per stage of a governed decision's multi-agent workflow (10,000 rows — 10 agents × 1,000 workflow runs), each with its own start/complete timestamps, status, and I/O refs. The closest implementation to the spec's "runtime agent activity." Source: `data/synthetic/agents/agent_events.csv`. **Live** — the sole data source for the AI Factory Agent Registry cards.
* **Primary Key:** `agent_run_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `agent_run_id` | TEXT (PK) | Row identifier, e.g. `AGRUN_SYN_00000001`. Not surfaced by the live query. |
| `workflow_run_id` / `recommendation_id` / `decision_id` | TEXT (FK) | Parent workflow run / recommendation / resulting decision. Not surfaced. |
| `domain` | TEXT | `AUTO`, `CIRCULARITY`, `COLLECTIONS`, `FINANCE`, `LOGISTICS`. Aggregated (distinct, sorted) per agent into the agent's "uses" domains. |
| `event_sequence` | BIGINT | Ordinal step within the workflow. Not surfaced. |
| `agent_id` | TEXT | The real agent registry key: `AGENT_DATA`, `AGENT_PREDICTION`, `AGENT_CAUSAL_GRAPH`, `AGENT_SIMULATION`, `AGENT_COMPLIANCE`, `AGENT_HUMAN_REVIEW`, `AGENT_ACTION`, `AGENT_LEARNING`, plus two not in the frontend's hardcoded 8-stage flow arrays: `AGENT_CODE_ANALYTICS`, `AGENT_MEMORY`. Grouping key for the agent list; also deterministically hashed (UUIDv5) into the agent's id; also `removeprefix("AGENT_").title()`'d into `role` (e.g. `AGENT_CAUSAL_GRAPH` → "Causal Graph" — note `role` ≠ `agent_name`, e.g. "Data" vs. "Data Agent"). |
| `agent_name` | TEXT | Display name, e.g. "Data Agent", "Prediction Agent" — surfaced directly as the card name. |
| `started_at` | TIMESTAMPTZ | When the stage began. Not surfaced. |
| `completed_at` | TIMESTAMPTZ | When the stage finished. Rows are queried `ORDER BY completed_at`; the last row per `agent_id` group is treated as that agent's "latest" activity, and its raw ISO timestamp is surfaced as the card's activity line — i.e. it's a **timestamp**, not a decision description. |
| `status` | TEXT | `COMPLETED`, `SKIPPED`, or `BLOCKED` (real vocabulary). Title-cased for the card's status pill. **Note:** the frontend's tone logic only special-cases the literal strings `"Active"`/`"Recommended"` for success/info coloring — neither ever occurs in real data, so every agent card renders the `"warning"` tone regardless of actual status. |
| `input_refs` / `output_refs` | TEXT | JSON-encoded references to this stage's inputs/outputs (e.g. `skip_reason` when `status="SKIPPED"`). Not surfaced. |
| `human_feedback` | TEXT | Free-text human feedback on this stage, when present. Not surfaced. |
| `data_origin` / `generator_version` | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Agents (`agents.tsx`)
  * **Insight/Metric Displayed:** Agent registry cards (name, role, status pill, "last activity" line, domain-use pills).
  * **Data Mapping:** `GET /agents` → `AiAgentService.list_agents()` selects all rows ordered by `completed_at`, groups by `agent_id`, and for each agent's group takes the chronologically-last row as "latest".
  * **Insight/Metric Displayed:** "Inspect Agent" modal — "Inputs", "Outputs", "Guardrails", "Human feedback received", "Learning updates" fields.
  * **Data Mapping:** These modal fields are **hardcoded static strings** in `agents.tsx`, not sourced from `input_refs`/`output_refs`/`human_feedback`.
  * **Insight/Metric Displayed:** "Run Agent Workflow" 8-stage progress animation.
  * **Data Mapping:** `POST /agents/workflow/run` is a static stub that **reads no table** — it returns a hardcoded 8-stage `(stage, message)` tuple with a fixed 700ms interval, independent of any `agent_events`/`agent_workflow_runs` data. The frontend advances through its own hardcoded stage array, showing the API's canned message per stage.

#### Predictive Modeling Mapping
* Omitted — orchestration/telemetry metadata, not a modeling artifact.

---

### 49. Agent Workflow Runs — `agent_workflow_runs`
* **Description:** One row per end-to-end multi-agent run for a single recommendation (1,000 rows — exactly half of the 2,000 `recommendations`; only recommendations that entered the full orchestrated pipeline get a workflow run). Rolls up the run's outcome: final `trust_decision`, whether it needed human review, whether/how it was executed. The real backing table for the spec's "Canonical workflow: Data Agent → … → Learning Agent" concept. Source: `data/synthetic/agents/agent_workflow_runs.csv`. **Confirmed dead in the live backend** — `AiAgentService.run_workflow()` (the endpoint the "Run Agent Workflow" button calls) is a static stub that never reads or writes this table (see #48).
* **Primary Key:** `workflow_run_id`

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `workflow_run_id` | TEXT (PK) | Row identifier, e.g. `WFLOW_SYN_0000001`. |
| `recommendation_id` / `decision_id` | TEXT (FK) | The recommendation driving this run (1:1) / the resulting decision. |
| `domain` / `use_case` | TEXT | Business domain / use case. |
| `target_entity_type` / `target_entity_id` | TEXT | The operational record acted on. |
| `recommendation_type` | TEXT | The recommended action code. |
| `trigger_type` | TEXT | Only `GOVERNANCE_DECISION` occurs — every run is triggered by a governance decision event, not a schedule or manual trigger. |
| `started_at` / `completed_at` | TIMESTAMPTZ | Run timeline. |
| `status` | TEXT | `COMPLETED` or `BLOCKED`. |
| `trust_decision` | TEXT | `APPROVED` or `REJECTED` — copy of the governing decision. |
| `decision_mode` | TEXT | `AUTOMATED_POLICY` or `HUMAN_REVIEW`. |
| `human_review_required` / `human_review_id` | BOOLEAN/TEXT (FK) | Whether a human reviewer was needed (true for 300/1,000 rows, matching `human_reviews` exactly). |
| `action_id` | TEXT (FK → `action_outcomes`) | Set only when the recommendation was executed (864/1,000 rows, matching `action_outcomes` exactly). |
| `action_status` | TEXT | `EXECUTED` or `BLOCKED_BY_REJECTION`. |
| `agent_event_count` | BIGINT | How many `agent_events` rows belong to this run (10 per run in the sampled data). |
| `workflow_priority_score` | DOUBLE | 0–1 priority score for the run. |
| `data_origin` / `generator_version` | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Not used anywhere.** This is the natural backing table for the Agents screen's "Agent Collaboration Flow" panel, but `POST /agents/workflow/run` is a static stub that ignores it entirely.

---

# Section H — Copilot

### 50. Copilot Evaluation Question Bank — `copilot_eval_questions`
* **Description:** A held-out benchmark question set for the Analytics Copilot, generated deterministically by the Synthetic Data Factory (`data/generators/copilot/evaluation_cases.py`) — 10 questions per supported business domain (auto, dealer, manufacturing, warranty, finance, collections, logistics, circularity, compliance, simulation), each tagged with the reasoning skill it exercises and the runtime tables a grounded answer would need to query. One of the 51 canonical runtime-schema tables. **Business purpose:** intended as the "truth" side of a Copilot evaluation harness (groundedness, factual correctness, hallucination rate, correct domain routing) — but no backend or frontend code currently reads this table; it is generated and loaded into Postgres and then sits unused.
* **Primary Key:** `evaluation_case_id`
* **Companion table (not in the runtime schema, for context):** the generator also emits `copilot_eval_ground_truth` (expected_answer, expected_entities, must_include_facts, must_not_invent, source_refs, answerable, evaluation_notes) — deliberately kept **out of** `runtime_tables` so the "runtime" Copilot can never read the hidden answer key. Only the question-and-routing-metadata half (`copilot_eval_questions`) is loaded into the queryable runtime schema.

#### Schema & Field Definitions
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `evaluation_case_id` | TEXT (PK) | Unique identifier for one evaluation case. |
| `domain` | TEXT | Business domain the question targets — `auto`, `dealer`, `manufacturing`, `warranty`, `finance`, `collections`, `logistics`, `circularity`, `compliance`, `simulation`. |
| `case_ordinal` | BIGINT | 1-based position of this case within its domain's fixed 10-question set. |
| `question` | TEXT | The natural-language evaluation question text. |
| `task_type` | TEXT | The reasoning skill under test: `AGGREGATION`, `ENTITY_RANKING`, `LINEAGE`, `GOVERNANCE_REASONING`, `ANTI_HALLUCINATION`, `CAUSAL_RESTRAINT`, `SIMULATION_RESTRAINT`, or `SOURCE_ROUTING`. |
| `difficulty` | TEXT | `EASY`, `MEDIUM`, or `HARD`. |
| `response_type` | TEXT | Expected answer shape: `NUMBER`, `ENTITY`, `ENTITY_AND_METRIC`, `BOOLEAN`, `STRUCTURED`, or `ABSTENTION`. |
| `route_tables_json` | TEXT (JSON) | JSON array of the runtime-schema table name(s) a grounded answer must be sourced from — the ground-truth query-routing target. |
| `generated_at` | TIMESTAMPTZ | Timestamp the synthetic generator stamped the case with. |
| `seed` | BIGINT | RNG seed used to generate this case. |
| `dataset_split` | TEXT | `TRAIN`, `VALIDATION`, or `TEST` — partition label for an eval pipeline. |
| `data_origin` / `generator_version` | TEXT | Provenance/bookkeeping. |

#### Screen-by-Screen Insights Mapping
* **Not used on any screen.** No API route, service, or repository reads it. There is no evaluation dashboard, admin screen, or API endpoint (`backend/app/api/v1/copilot.py` exposes only `GET /suggested-prompts` and `POST /chat`) that surfaces evaluation-case pass/fail, groundedness, or routing-accuracy metrics anywhere in `copilot.tsx`. This directly contradicts the spec's evaluation measures — the eval *data* exists, the eval *harness/measurement* does not.

#### Predictive Modeling Mapping
* **Target Variable:** None trained. If an evaluation harness were wired up, the implicit target would be "does the live Copilot's answer to `question` match the hidden `copilot_eval_ground_truth` row" — but no such comparison is implemented anywhere.
* **Honesty note — the live query router is not a model at all:** the actual production routing logic (`backend/app/ai/copilot/intents.py`) is a **fully deterministic, ordered keyword/substring match** over the lower-cased prompt (e.g. `"booking" in p and "pune" in p` — first match wins). It is not a trained classifier, does not consult `route_tables_json`. Once an intent rule matches, `backend/app/ai/copilot/engine.py::RuleBasedCopilot.respond` returns a **hardcoded, static response payload** (fixed `answer`/`explanation`/`sql`/`python`/`chart`/`table`/`action`/`confidence` strings) — it does not execute the shown SQL, does not touch the database, and does not call an LLM. `CopilotService.chat` never calls `get_llm_provider` at all — it instantiates `RuleBasedCopilot` directly. **No predictive or generative model is in the loop; the "confidence" values shown to users (70–93%) are static numbers hardcoded per intent, not a model output.**

---

### 51. Suggested Prompt — `suggested_prompts`
* **Description:** Configuration data powering the "Suggested prompts" chip list on the Analytics Copilot screen. **Schema collision, resolved:** there are two Python definitions targeting a table literally named `suggested_prompts`. `backend/app/models/copilot.py`'s ORM class is **not created by any Alembic migration** and is dead code; `backend/app/database/runtime_schema.py`'s Core-table definition is physically created by the runtime baseline migration and is the **live table** — `backend/app/repositories/copilot.py` imports `runtime_tables["suggested_prompts"]` directly and never touches the ORM class. The two coexist harmlessly only because they sit on separate `MetaData` objects.
* **Primary Key:** `prompt_id`

#### Schema & Field Definitions (live, runtime-schema shape)
| Column Name | Data Type | Field Definition / Business Meaning |
| :--- | :--- | :--- |
| `prompt_id` | TEXT (PK) | Unique identifier for the prompt chip. |
| `domain` | TEXT | Business domain the prompt is themed around. |
| `prompt_text` | TEXT | The exact chip label / question text shown to the user and sent verbatim as the chat message when clicked. |
| `display_order` | BIGINT | Sort order for rendering the chip list. |
| `enabled` | BOOLEAN | Whether the chip is currently shown; filtered `WHERE enabled IS TRUE`. |
| `data_origin` / `generator_version` | TEXT | Provenance/bookkeeping. |

*(Dead-code ORM shape, for reference only: `id` UUID PK, `text` TEXT unique, `sort_order` INTEGER, `created_at`/`updated_at`.)*

#### Screen-by-Screen Insights Mapping
* **Screen Name:** Analytics Copilot (`copilot.tsx`), "Suggested prompts" panel.
  * **Insight/Metric Displayed:** A vertical list of clickable prompt chips (e.g. "Why did bookings drop in Pune?").
  * **Data Mapping:** `useSuggestedPrompts()` → `GET /copilot/suggested-prompts` → `SELECT prompt_text FROM suggested_prompts WHERE enabled IS TRUE ORDER BY display_order`, de-duplicated client-side. Clicking a chip sends `prompt_text` verbatim as the user's chat message, routed through the same keyword-matching `INTENT_RULES` described in #50.

---

## Appendix — Cross-cutting gaps worth flagging for planning

A few patterns recur across multiple datasets above and are worth calling out once, together, since they cut across domain boundaries:

1. **"Predict"/"Simulate" buttons that re-aggregate history instead of forecasting.** Logistics' "Predict Delay" button, the ELV valuation formula (#36), and the Finance EMI/risk simulator (#27) all either recompute a historical ratio off the `shipments` table (#34) or run a fixed formula on manually-entered slider values, rather than a fitted model reading live data.
2. **Several of the standalone what-if simulators in `backend/app/ai/simulation/` are not wired into their "home" screen.** The Collections (#31) and Credit Pricing (#39) simulation engines, plus the Logistics Delay engine described under `shipments` (#34), are only reachable from the generic Simulation Center (`simulation.tsx`), not from the Collections/Logistics/Circularity screens whose data they conceptually simulate.
3. **Several "Approve / Reject / Escalate"-style governance actions are decorative.** Trust Decisions (#42), Recommendations (#47), and Collections case actions (#30) all show an optimistic success toast on the frontend while the backend either raises a validation error or is a no-op stub — no state is actually persisted in any of these cases today.
4. **The governance domain (Section G) is the most under-utilized part of the schema relative to how richly it's populated.** 5 of its 8 tables — `audit_events` (#44), `human_reviews` (#45), `action_outcomes` (#46), `agent_workflow_runs` (#49), and `recommendations` (#47) itself — are fully generated with real FK linkage across each other but have zero live readers; the Executive Overview and Agents screens instead synthesize their own simpler, live-computed substitutes from other domains' operational tables.
5. **`xr_sessions` (#41), `audit_events` (#44), `human_reviews` (#45), `action_outcomes` (#46), and `agent_workflow_runs` (#49)** are the clearest "ready to wire up" opportunities: real, populated, FK-consistent data sitting behind a screen that currently shows either nothing or a static placeholder for exactly the insight that table would supply.

---

## End of document
