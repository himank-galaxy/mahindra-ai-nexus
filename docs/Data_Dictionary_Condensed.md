# Mahindra AI Nexus — Data Dictionary (Condensed)

One section per `data/synthetic/<folder>/` directory; one entry per CSV file in that folder, in file order. For each: primary key, full column list with definitions, and which screen(s) actually use it. Covers exactly the **51 CSV datasets** under `data/synthetic/**/*.csv` — the Synthetic Data Factory's canonical output, verified column-for-column against the actual files (headers diffed against `backend/app/database/runtime_schema.py`, and every declared primary key checked for row-level uniqueness in the real data) and cross-checked against backend services/frontend code, not just the product spec. "Dead" = table exists and is populated but no live code path reads/writes it. Not covered here (no corresponding CSV file): a separate, physically isolated "AI state" schema holding live PCMCI/causal-engine output, and a legacy application-state ORM layer (mostly dead code).

---

# `data/synthetic/agents/`

*AI Factory agent registry activity — governed-decision workflow orchestration events.*

## 1. Agent Runtime Events — `agent_events`
**Columns:** `agent_run_id` (PK) · `workflow_run_id`/`recommendation_id`/`decision_id` (FK) · `domain` · `event_sequence` · `agent_id` (10 agents incl. AGENT_DATA, AGENT_PREDICTION, AGENT_CAUSAL_GRAPH, AGENT_SIMULATION, AGENT_COMPLIANCE, AGENT_HUMAN_REVIEW, AGENT_ACTION, AGENT_LEARNING, AGENT_CODE_ANALYTICS, AGENT_MEMORY) · `agent_name` · `started_at`/`completed_at` · `status` (COMPLETED/SKIPPED/BLOCKED) · `input_refs`/`output_refs` (JSON) · `human_feedback`.
**Used in:** Agents screen — registry cards (name, role, status, "last activity" = raw `completed_at` timestamp, domain-use pills). "Inspect Agent" modal fields (Inputs/Outputs/Guardrails/etc.) are hardcoded, not read from `input_refs`/`output_refs`.

## 2. Agent Workflow Runs — `agent_workflow_runs` (dead)
**Columns:** `workflow_run_id` (PK) · `recommendation_id`/`decision_id` (FK) · `domain`/`use_case` · `target_entity_type`/`target_entity_id` · `recommendation_type` · `trigger_type` · `started_at`/`completed_at` · `status` · `trust_decision`/`decision_mode` · `human_review_required`/`human_review_id` · `action_id`/`action_status` · `agent_event_count` · `workflow_priority_score`.
**Used in:** Not used — the "Run Agent Workflow" animation on the Agents screen is a static 8-stage stub that never reads this table.

---

# `data/synthetic/auto/`

*Auto sales & dealer funnel, plus the manufacturing/warranty lineage tables generated alongside it.*

## 3. Allocations — `allocations`
**Columns:** `allocation_id` (PK) · `booking_id`/`lead_id`/`customer_id`/`dealer_id` (FK) · `vehicle_model_id`/`vehicle_id` · `production_batch_id`/`plant_id`/`production_line_id`/`representative_machine_id` · `variant` · `primary_supplier_id`/`primary_supplier_lot_id` · `supplier_lot_quality_score`/`production_quality_score` · `finance_application_id`/`finance_status` · `allocation_date` · `requested_units`/`allocated_units`/`waiting_list` · `dealer_capacity`/`dealer_capacity_source` · `regional_demand_index` · `allocation_priority_score`/`allocation_priority` · `inventory_before`/`inventory_after` · `production_batch_inventory_before`/`after` · `allocation_wait_hours` · `allocation_status`.
**Used in:** Not used by any live screen directly (only as an FK on `deliveries`/`service_events`/`warranty_claims`). Its evidence fields (`regional_demand_index`, `waiting_list`, `allocation_priority_score`, inventory before/after) are what feed the *synthetic* `recommendations` table's `DEALER_ALLOCATION_OPTIMIZATION` evidence — see #36 — though the live overview service doesn't re-derive them.

## 4. Bookings — `bookings`
**Columns:** `booking_id` (PK) · `lead_id`/`customer_id`/`test_drive_id`/`dealer_id` (FK) · `vehicle_model_id`/`name` · `vehicle_base_price_inr` · `source_channel` · `latent_purchase_intent` · `completed_test_drive` · `good_followup` · `finance_assisted`/`finance_preapproval_signal` · `exchange_assisted` · `long_test_drive_wait` · `booking_probability` · `booking_amount_inr` · `booking_timestamp` · `promised_delivery_date` · `booking_status`.
**Used in:** Dealer Cockpit — "Booking probability" (numerator), "Follow-up leakage" (denominator), lead "Converted" status. Executive Overview — "Predicted Revenue Uplift" (`SUM(vehicle_base_price_inr) × 0.075`), "Dealer Conversion Uplift" (`completed_test_drive` share).

## 5. Cancellations — `cancellations`
**Columns:** `cancellation_id` (PK) · `booking_id`/`lead_id`/`customer_id` (FK) · `finance_application_id`/`finance_status`/`finance_risk_band`/`finance_approval_tat_hours` · `dealer_id`/`name` · `vehicle_model_id`/`name` · `good_followup`/`long_test_drive_wait` · `promised_delivery_wait_days` · `cancellation_probability` · `cancellation_reason` · `cancelled_at` · `booking_amount_inr` · `refund_amount_inr`/`retained_amount_inr` · `cancellation_status`.
**Used in:** Dealer Cockpit — "Revenue at risk" (`SUM(booking_amount_inr)`), "Follow-up leakage" (`COUNT/COUNT(bookings)`). Executive Overview — "Leakage Prevented" (`SUM(booking_amount_inr) × 0.35`), "Address leading cancellation reason" card (`GROUP BY cancellation_reason`).

## 6. Customers — `customers`
**Columns:** `customer_id` (PK) · `region_id`/`name` · `city_id`/`name` · `preferred_vehicle_model_id`/`name` · `budget_band` · `purchase_horizon_days` · `finance_required` · `exchange_vehicle` · `customer_segment` · `created_at`.
**Used in:** Not used — no service queries this table; Dealer Cockpit shows `leads.customer_id` directly instead of joining here.

## 7. Deliveries — `deliveries`
**Columns:** `delivery_id` (PK) · `allocation_id`/`booking_id`/`lead_id`/`customer_id`/`vehicle_id` (FK) · `vehicle_model_id`/`name`/`variant` · `dealer_id`/`name` · `production_batch_id`/`plant_id`/`production_line_id`/`representative_machine_id` · `primary_supplier_id`/`primary_supplier_lot_id` · `supplier_lot_quality_score`/`production_quality_score` · `booking_timestamp`/`allocation_date`/`promised_delivery_date` · `dispatch_at`/`physical_ready_date`/`projected_delivery_date`/`actual_delivery_date` · `dispatch_delay_hours` · `base_transit_days`/`transport_disruption`/`disruption_days`/`total_transit_days` · `regional_demand_index`/`allocation_priority`/`allocation_wait_hours` · `demand_pressure`/`quality_hold`/`normal_handover_delay` · `delivery_variance_days`/`delay_days`/`early_days`/`delayed`/`delay_reason` · `customer_handover_completed`/`handover_score` · `delivery_status`.
**Used in:** Not surfaced on any screen directly. Used server-side by the telematics causal pipeline (`vehicle_id`, `actual_delivery_date`) to gate which vehicle telemetry is visible (see #19).

---

## 8. Finance Applications (Auto) — `finance_applications`
**Columns:** `finance_application_id` (PK) · `booking_id`/`lead_id`/`customer_id`/`dealer_id` (FK) · `vehicle_model_id`/`name` · `submitted_at`/`decision_at` · `requested_amount_inr`/`approved_amount_inr` · `status` · `risk_band`/`income_band` · `bureau_like_score_synthetic` · `document_completeness` · `approval_tat_hours` · `preapproval_signal_at_booking`.
**Used in:** Executive Overview — "Financial Risk Reduction" (`APPROVED` share), "Resolve N non-final finance decisions" card (`MANUAL_REVIEW`+`PENDING` counts). Not used on Dealer Cockpit.

## 9. Followups — `followups`
**Columns:** `followup_id` (PK) · `lead_id`/`customer_id`/`dealer_id` (FK) · `attempt_number` · `channel` · `scheduled_at` · `completed` · `completed_at` · `dealer_sla_hours` · `within_sla` · `customer_responded` · `response_time_minutes` · `response_at` · `followup_status`.
**Used in:** Dealer Cockpit — only `completed` flag is read, to promote a lead's status/action. Note: the "Follow-up leakage" KPI is actually computed from `cancellations`/`bookings`, not this table.

## 10. Leads — `leads`
**Columns:** `lead_id` (PK) · `customer_id` (FK) · `customer_lead_number` · `dealer_id`/`name` · `region_id`/`name` · `city_id`/`name` · `vehicle_model_id`/`name` · `source_channel` · `budget_fit`, `engagement_score`, `urgency_score`, `model_interest_score`, `source_quality` — intent sub-scores · `latent_purchase_intent` — composite ranking score · `lead_created_at`.
**Used in:** Dealer Cockpit — Lead Prioritization table (all core columns), "Leads today"/"Hot leads" KPIs (`latent_purchase_intent >= 0.65`), "Booking probability" (denominator). Status/action rule joins `followups.completed`, `test_drives.completed`, `bookings` presence.

## 11. Production Batches — `production_batches`
**Columns:** `production_batch_id` (PK) · `plant_id`/`production_line_id`/`representative_machine_id` (FK) · `active_line_count`/`active_machine_count`/`average_machine_load_pct`/`bottleneck_capacity_units_per_hour` · `vehicle_model_id`/`name`/`variant` · `production_complexity` · `primary_supplier_id`/`primary_supplier_lot_id`/`supplier_component_category`/`supplier_criticality`/`supplier_lot_quality_score`/`inspection_defect_rate`/`age_days`/`units_consumed`/`remaining_units_after_batch` · `production_date`/`start`/`end` · `dominant_shift` · `scaled_daily_capacity_units`/`planned_units`/`production_efficiency`/`units_produced` · `defect_probability`/`defect_units`/`rework_units`/`rework_success_units`/`scrap_units` · `first_pass_good_units`/`final_good_units`/`first_pass_yield`/`final_yield` · `quality_inspection_rate`/`quality_score` · `batch_status` · `available_for_allocation_units`.
**Used in:** Not queried directly — `production_batch_id` is used purely as an FK/lineage identifier on `manufacturing_timeseries`/`service_events`/`warranty_claims`; none of this table's own yield/defect columns are pulled onto any screen.

## 12. Service Events — `service_events`
**Columns:** `service_event_id` (PK) · `delivery_id`/`allocation_id`/`booking_id`/`customer_id`/`vehicle_id` (FK) · `vehicle_model_id`/`name`/`variant` · `service_dealer_id`/`name` · `region`/`city` · `production_batch_id`/`plant_id`/`production_line_id`/`representative_machine_id` — exact-lineage legs · `primary_supplier_id`/`primary_supplier_lot_id`/`supplier_component_category`/`supplier_lot_quality_score`/`production_quality_score` · `service_type` · `service_started_at`/`service_completed_at` · `days_since_delivery`/`odometer_km` · `complaint_reported` · `issue_category` — early-warning grouping key · `severity`/`diagnosis` · `repair_required` · `service_duration_hours` · `service_score` · `warranty_candidate` · `service_status`.
**Used in:** Warranty & Quality screen — Priority Warnings / Selected Warning Evidence (`complaint_reported`, `repair_required`, `warranty_candidate`, `severity` counts by `issue_category`), Exact Production Lineage (`representative_machine_id`+`production_batch_id`+`primary_supplier_lot_id` triple), Affected Machines/Models/Cities counts, Empirical Calibration percentiles.

## 13. Supplier Lots — `supplier_lots`
**Columns:** `supplier_lot_id` (PK) · `supplier_id` (FK) · `supplier_name` · `component_category`/`group` · `criticality` · `lot_sequence` · `received_at` · `lot_size_units`/`accepted_units`/`rejected_units` · `lot_quality_score` · `inspection_defect_rate` · `inspection_status` · `usable_for_production`.
**Used in:** Not queried directly — used purely as a join-key/lineage identifier via `primary_supplier_lot_id` on other tables, never joined back to this table's own quality columns.

## 14. Suppliers — `suppliers`
**Columns:** `supplier_id` (PK) · `supplier_name` · `component_category`/`component_group` · `criticality` · `supplier_tier` · `city_id`/`name`, `region_id`/`name` · `baseline_quality_score` · `lead_time_days` · `monthly_capacity_units` · `active`.
**Used in:** Not queried directly — Warranty & Quality's Supplier Hotspots panel uses denormalized `primary_supplier_id`/`primary_supplier_name`/`supplier_component_category` off `warranty_claims` instead.

## 15. Test Drives — `test_drives`
**Columns:** `test_drive_id` (PK) · `lead_id`/`customer_id`/`dealer_id` (FK) · `vehicle_model_id`/`name` · `latent_purchase_intent` · `request_probability` · `followup_attempt_count`, `completed_followup_count`, `responded_followup_count`, `any_within_sla_followup` · `requested_at`/`scheduled_at`/`wait_hours` · `reminder_sent` · `high_intent`/`long_wait` · `completion_probability` · `status` · `completed`/`completed_at` · `feedback_score` · `rescheduled_for`.
**Used in:** Dealer Cockpit — "Test drives pending" KPI (`completed=false AND status!='NO_SHOW'`), lead status rule (`completed` flag). Most other columns unused.

## 16. Warranty Claims — `warranty_claims`
**Columns:** `warranty_claim_id` (PK) · `service_event_id`/`delivery_id`/`allocation_id`/`booking_id`/`customer_id`/`vehicle_id` (FK) · `vehicle_model_id`/`name`/`variant` · `vehicle_age_days`/`odometer_km` · `service_dealer_id`/`name` · `region`/`city` · `production_batch_id`/`plant_id`/`production_line_id`/`representative_machine_id` · `primary_supplier_id`/`name`/`primary_supplier_lot_id`/`supplier_component_category`/`supplier_lot_quality_score`/`production_quality_score` · `issue_category`/`failure_code`/`severity`/`diagnosis` · `service_duration_hours` · `claim_probability` (excluded from evidence by design) · `claim_submitted_at`/`decision_at` · `claim_amount_inr`/`approved_amount_inr` · `claim_status` · `root_cause_domain` (excluded from evidence by design).
**Used in:** Warranty & Quality screen — Selected Warning Evidence ("Warranty Claims" count, "Approved Exposure" = `SUM(approved_amount_inr)`), Supplier Hotspots (grouped by supplier), Market Hotspots (grouped by model/variant/region/city), Exact Production Lineage triples.

---

# `data/synthetic/causal/`

*Raw time-series observations feeding the three PCMCI/LPCMCI causal-discovery pipelines (manufacturing, mobility business-funnel, vehicle telematics).*

## 17. Manufacturing Time-Series — `manufacturing_timeseries`
**Columns:** `timestamp`+`machine_id` (composite PK) · `plant_id`/`name`, `production_line_id`/`name`/`line_type`, `machine_name` — lineage · `production_batch_id`/`vehicle_model_id`/`name`/`supplier_lot_id`/`batch_status` — lineage · **PCMCI variables:** `ambient_temperature_c`, `ambient_humidity_pct`, `machine_load`, `machine_temperature_c`, `vibration_mm_s`, `power_kw`, `line_speed_units_per_hour`, `cycle_time_seconds`, `hours_since_maintenance`, `maintenance_overdue_hours`, `supplier_lot_quality_score`, `torque_deviation_nm`, `paint_booth_temperature_c`, `paint_booth_humidity_pct`, `paint_defect_rate`, `defect_rate`, `rework_rate`, `downtime_minutes`, `quality_score`.
**Used in:** Warranty & Quality screen — "Exact Window" lineage/coverage, data-freshness cards. The 19 PCMCI variables above feed the LPCMCI/PCMCI causal-discovery engine whose output populates the persisted `manufacturing_causal_runs`/`manufacturing_causal_edges` tables (live AI-state tables, not CSV datasets, out of scope here) — the screen reads those, not this one, on each page load.

## 18. Auto Mobility Business Time Series — `mobility_timeseries`
**Columns:** `region_id`+`window_start` (composite PK) · `region_name`/`window_end` · `lead_count`/`avg_lead_engagement_score` · `followup_count`/`followup_completed_count`/`customer_response_count`/`avg_followup_response_minutes` · `test_drive_requested_count`/`completed_count`/`no_show_count` · `booking_count`/`booking_value_inr` · `finance_application_count`/`approved_count`/`rejected_count`/`manual_review_count`/`avg_finance_approval_tat_hours` · `cancellation_count` · `allocated_vehicle_count`/`avg_allocation_wait_hours` · `delivered_vehicle_count`/`delayed_delivery_count`/`avg_delivery_delay_days` · `service_event_count`/`unscheduled_repair_count` · `warranty_claim_count`/`warranty_approved_count`/`warranty_claim_amount_inr` · `waitlisted_booking_count`.
**Used in:** Mobility Twin — "Business Health" KPI rail (5 derived metrics from an 11-metric subset), Causal Graph panel (PCMCI-discovered funnel graph), "Ask Causal Twin" Q&A. Many columns above (warranty/service/waitlist) are stored but not read by the causal-input loader.

## 19. Vehicle Telematics Time Series — `vehicle_telematics_timeseries`
**Columns:** `timestamp`+`vehicle_id` (composite PK) · `vehicle_model_id`/`name`/`variant`, `production_batch_id`/`supplier_lot_id`/`plant_id`/`production_line_id` — lineage · `odometer_km` (excluded from PCMCI — monotonic) · **PCMCI variables:** `vehicle_speed_kph`, `ambient_temperature_c`, `battery_temperature_c`, `battery_soc_pct`, `battery_voltage_v`, `battery_current_a`, `battery_internal_resistance_ohm`, `transmission_temperature_c`, `transmission_slip_ms`, `torque_converter_slip_rpm`, `steering_torque_nm`, `steering_angle_deg`, `vehicle_vibration_mm_s`, `vertical_acceleration_g`, `lateral_acceleration_g`, `road_roughness_index`, `impact_g_force` · `dtc_count`/`warning_flag` (excluded — downstream evidence, not cause).
**Used in:** **Not read by Mobility Twin despite the name.** Read by Warranty & Quality screen's "telematics" causal domain — per-vehicle PCMCI/LPCMCI discovery, output persisted to `telematics_causal_runs`/`telematics_causal_edges` (a live AI-state table, not a CSV dataset, out of scope here).

---

# `data/synthetic/circularity/`

*ELV intake, RVSF processing, dMRV evidence and carbon-credit marketplace records.*

## 20. Carbon Credit Listings — `credit_listings`
**Columns:** `carbon_credit_listing_id` (PK) · `elv_assessment_id`/`elv_vehicle_id` · vehicle/facility denorm · `credit_type`/`credit_unit` · `claim_basis`/`claim_basis_version` · `credit_vintage_start_at`/`_end_at` · `listing_at`/`listing_status` · `seller_claimed_quantity_tco2e`/`minimum_trade_quantity_tco2e` · `market_reference_price_per_tco2e_inr`/`seller_ask_price_per_tco2e_inr` · `buyer_inquiry_count`/`buyer_bid_count`/`highest_bid_price_per_tco2e_inr` · `source_rvsf_job_count`/`source_rvsf_quality_pass_count` · recovery mass columns (`reusable_parts_mass_kg` etc.) · `total_process_energy_kwh`/`total_process_water_liters` · `source_dmrv_record_count`/`dmrv_expected_records`/`dmrv_available_records`/`dmrv_missing_records` · 7 `dmrv_*_records` integrity counts.
**Used in:** Circularity screen (Marketplace tab) — "Buyer match %" (bid/ask ratio), "Closure prob. %" (dMRV available/expected), "Traceability %" (7 integrity counts summed). "Reprice"/"Match Buyer" buttons always error server-side.

## 21. dMRV Records — `dmrv_records`
**Columns:** `dmrv_record_id` (PK) · `rvsf_job_card_id`/`elv_assessment_id`/`elv_vehicle_id`/`evidence_sequence` (FK) · `evidence_type` · job/facility denorm · `measurement_period_start`/`_end` · `dmrv_recorded_at`/`evidence_observed_at` · `evidence_source_system`/`measurement_basis`/`source_reference_id` · `evidence_available` — core flag · `evidence_status`/`missing_reason_code` · 7 integrity flags: `source_reference_present`, `evidence_attachment_present`, `timestamp_verified`, `digital_signature_present`, `operator_identity_present`, `chain_of_custody_present`, `measurement_calibration_present` · `source_job_quality_check_passed` · 15 `observed_*` mass/resource columns (unused).
**Used in:** Circularity screen — dMRV evidence-coverage tile (`evidence_available` share), dMRV Copilot answers (facility with lowest coverage; overall coverage %). Also feeds `credit_listings`' traceability/closure % (#20).

## 22. ELV Assessments — `elv_assessments`
**Columns:** `elv_assessment_id`/`elv_vehicle_id` (PK) · `vehicle_model_id`/`name`/`segment` · `city`/`region` · `assessment_at`/`assessment_status` · `source_channel` · `manufacture_year`/`vehicle_age_years`/`odometer_km` · `accident_history_count`/`major_accident_flag`/`flood_exposure_flag` · `condition_score`/`body_condition_score`/`chassis_integrity_score`/`powertrain_condition_score`/`interior_condition_score` · `engine_operable` · `document_completeness`/`document_status` · `traceability_score`/`traceability_status` · `buyer_demand_index` · `estimated_vehicle_mass_kg` · `assessed_reusable_parts_pct`/`assessed_recyclable_material_pct` · `battery_present`/`tyre_set_present`/`catalytic_converter_present`/`hazardous_fluids_present`.
**Used in:** Circularity screen (ELV tab) — **not actually used.** "Suggested ELV price"/"Recoverable value" are computed by a client-side-only formula from slider inputs (`age`, `condition`, `docs`), not from this table (the backend endpoint always errors — no monetary valuation columns exist here).

## 23. RVSF Job Cards — `rvsf_job_cards`
**Columns:** `rvsf_job_card_id` (PK) · `elv_assessment_id`/`elv_vehicle_id`/`job_sequence` (FK) · `job_type` · vehicle/facility denorm · `job_opened_at`/`processing_started_at`/`processing_completed_at`/`processing_duration_minutes` · `stage_input_mass_kg` · `battery_recovered`/`_mass_kg`, `tyre_set_recovered`/`_mass_kg`, `catalytic_converter_recovered`/`_mass_kg` · `fluid_drain_completed`/`hazardous_fluid_liters`/`_mass_kg` · `removed_component_mass_kg`/`reusable_parts_mass_kg`/`recyclable_material_mass_kg`/`residual_waste_mass_kg`/`transferred_to_next_stage_kg` · `labor_hours`/`energy_consumed_kwh`/`water_consumed_liters` · `quality_check_passed` · `weighbridge_ticket_id` · `job_status`.
**Used in:** Circularity screen (RVSF tab) — throughput (`job_status='COMPLETED'`), avg processing time, QC-failure count, recovered reusable/recyclable mass sums.

---

# `data/synthetic/collections/`

*Delinquency case management and collector-customer contact history.*

## 24. Collection Cases — `collection_cases`
**Columns:** `collection_case_id` (PK) · `loan_account_id`/`finance_customer_id`/`loan_case_sequence` (FK) · `region`/`city`/`product` (denorm) · `case_created_at`/`carried_into_generation_window` · `case_trigger_source`/`trigger_payment_event_id`/`case_trigger_dpd`/`observed_dpd_at_trigger_event`/`dpd_at_case_creation` · `arrears_at_trigger_event_inr` · `priority_at_creation` · `peak_observed_dpd`/`peak_observed_arrears_inr` · `case_status` · `current_dpd` · `current_arrears_inr` · `resolved_at`/`resolution_payment_event_id`/`resolution_type`.
**Used in:** Collections screen — Customer Prioritization table (sorted by `current_dpd`/`current_arrears_inr`; "Outstanding" column is actually `current_arrears_inr`, not principal), "Compliance" flag (`current_dpd>=90`), 4 headline metric tiles.

## 25. Collection Interactions — `collection_interactions`
**Columns:** `collection_interaction_id` (PK) · `collection_case_id`/`loan_account_id`/`finance_customer_id`/`interaction_sequence` (FK) · `interaction_at` · `region`/`city`/`product` (denorm) · `channel` · `field_visit_flag`/`contact_success` · `dpd_at_interaction`/`arrears_at_interaction_inr`/`outstanding_principal_at_interaction_inr` · `offer_type` · `customer_response` · `promise_to_pay`/`promise_date` · `payment_after_contact`/`payment_after_contact_event_id`/`_at`/`_amount_inr` · `payment_after_promise`.
**Used in:** Collections screen — "Agent Swarm" cards (grouped by `channel`), "Best channel"/"Action" columns, "Payment after contact"/"Promise kept" tiles, "Prob." recovery-likelihood column (`payment_after_contact` hit-rate), Trust Ledger dialog lines.

---

---

# `data/synthetic/copilot/`

*Analytics Copilot configuration/evaluation data.*

## 26. Copilot Evaluation Question Bank — `copilot_eval_questions`
**Columns:** `evaluation_case_id` (PK) · `domain` (10 values) · `case_ordinal` · `question` · `task_type` (AGGREGATION/ENTITY_RANKING/LINEAGE/GOVERNANCE_REASONING/ANTI_HALLUCINATION/CAUSAL_RESTRAINT/SIMULATION_RESTRAINT/SOURCE_ROUTING) · `difficulty` · `response_type` · `route_tables_json` · `generated_at`/`seed` · `dataset_split`.
**Used in:** Not used — no evaluation harness reads it. The live Copilot query router (`intents.py`) is pure keyword matching, not a model, and doesn't consult this table.

## 27. Suggested Prompt — `suggested_prompts`
**Columns:** `prompt_id` (PK) · `domain` · `prompt_text` · `display_order` · `enabled`.
**Used in:** Copilot screen — "Suggested prompts" chip list (`prompt_text` where `enabled=true`, ordered by `display_order`).

---

## End of document

---

# `data/synthetic/finance/`

*Retail/SME lending book: customers, loans, repayments, cross-sell.*

## 28. Cross-Sell Events — `cross_sell_events`
**Columns:** `cross_sell_event_id` (PK) · `finance_customer_id`/`source_loan_account_id`/`source_product_code` (FK) · `region`/`city` · `offered_finance_product_id`/`code`/`name`/`category` · `offered_at`/`offer_channel` · `offer_amount_inr`/`offer_interest_rate_pct`/`offer_tenure_months`/`estimated_offer_emi_inr` · `customer_response`/`responded_at` · `event_version`.
**Used in:** Finance screen — product card `cross`/`opp`, Twin "Next Best Action" card, "Cross-sell propensity" list (single latest offer, not a scored percentage despite UI implying one).

## 29. Finance Customers — `finance_customers`
**Columns:** `finance_customer_id` (PK) · `region_id`/`name`, `city_id`/`name` · `employment_type` · `rural_urban_segment` · `finance_customer_segment` · `income_stability` · `monthly_income_inr`/`monthly_obligations_inr` · `obligation_to_income_ratio` · `customer_since` · `active`.
**Used in:** Finance screen — Customer Financial Twin header (Name=`finance_customer_id`, Location, `income_stability`), risk decomposition (`obligation_to_income_ratio`).

## 30. Loan Accounts — `loan_accounts`
**Columns:** `loan_account_id` (PK) · `finance_customer_id`/`customer_loan_sequence` (FK) · `region`/`city` · `finance_product_id`/`product_code`/`name`/`category`/`target_segment` · `secured` · `application_at`/`disbursed_at`/`scheduled_maturity_at` · `principal_inr` · `interest_rate_pct` · `tenure_months` · `emi_amount_inr` · `asset_value_inr`/`ltv_pct` · `debt_service_ratio_at_origination`.
**Used in:** Finance screen — product card `customers` count, Twin "Products held" chips (`product_name` only — most fetched columns are discarded). Collections screen — joined but `principal_inr` result unused (dead read).

## 31. Payment History — `payment_history`
**Columns:** `payment_event_id` (PK) · `loan_account_id`/`finance_customer_id` (FK) · `installment_number` · `region`/`city`/`product` (denorm) · `payment_due_at` · `scheduled_payment_amount_inr`/`scheduled_interest_inr`/`scheduled_principal_inr` · `payment_status` · `actual_payment_at`/`actual_payment_amount_inr` · `arrears_recovery_amount_inr` · `payment_delay_days` · `days_past_due_after_event` — DPD signal · `arrears_amount_inr` · `contractual_outstanding_principal_inr`/`outstanding_principal_inr`.
**Used in:** Finance screen — product card `risk` (30+DPD %), Twin "Repayment"/`maxDpd`. Collections screen — "Scheduled payment realization" tile (platform-wide).

---

# `data/synthetic/governance/`

*AI recommendation → trust decision → compliance check → human review → action → outcome chain.*

## 32. Action Outcomes — `action_outcomes` (dead)
**Columns:** `action_id` (PK) · `workflow_run_id`/`recommendation_id`/`decision_id` (FK) · `domain` · `target_entity_type`/`target_entity_id` · `action_type` · `action_status` · `outcome_type`/`outcome_value`/`outcome_scope` · `business_outcome_observed`/`business_outcome_note` · `observed_at`.
**Used in:** Not used anywhere.

## 33. Immutable Audit Log — `audit_events` (dead)
**Columns:** `audit_event_id` (PK) · `recommendation_id`/`decision_id` (FK) · `domain`/`use_case` · `target_entity_type`/`target_entity_id` · `event_sequence` · `event_type` (6 values) · `event_at` · `actor_type`/`actor_id` · `source_record_type`/`source_record_id` · `event_status`/`event_summary`/`details_json` · `previous_event_hash`/`event_hash` (hash chain).
**Used in:** Not used anywhere — no screen or endpoint reads it.

## 34. Compliance Rule Checks — `compliance_checks`
**Columns:** `compliance_check_id` (PK) · `decision_id`/`recommendation_id` (FK) · `domain` · `rule_code` (LINEAGE_INTEGRITY / EVIDENCE_SUFFICIENCY / FAIRNESS_INPUT_SCOPE / BUSINESS_POLICY_ALIGNMENT / HUMAN_CONTROL_GATE) · `rule_name` · `checked_at` · `result` · `severity` · `reason` · `evidence_json`.
**Used in:** Trust screen — "Compliance Rules" sidebar (worst-ever `result` per rule, all-time not current). Lineage endpoint exists but is never called by the frontend.

## 35. Human Reviews — `human_reviews` (dead)
**Columns:** `review_id` (PK) · `decision_id`/`recommendation_id` (FK) · `reviewer_role` · `requested_at`/`completed_at` · `decision` · `reason_code` · `free_text`.
**Used in:** Not used anywhere — Trust screen's "Escalate" button errors instead of writing here.

## 36. AI Recommendations (Governance) — `recommendations` (dead as a read path)
**Columns:** `recommendation_id` (PK) · `domain`/`use_case` · `target_entity_type`/`target_entity_id` · `recommendation_type` · `generated_at` · `evidence_json` — full feature snapshot (e.g. for allocation: `regional_demand_index`, `fulfillment_ratio`, `waiting_list`, `allocation_priority_score`, inventory before/after) · `expected_impact` (JSON) · `confidence`/`risk_level` · `status`.
**Used in:** Executive Overview — "Top AI Recommendations Today" **does not read this table at all**; it synthesizes 4 substitute cards live from `shipments`/`finance_applications`/`cancellations`/`dmrv_records` aggregates instead. Approve/Human-Review buttons never write anywhere.

## 37. Compliance Trust Ledger — `trust_decisions`
**Columns:** `decision_id` (PK) · `recommendation_id` (FK) · `domain`/`use_case` · `target_entity_type`/`target_entity_id` · `recommendation_type` · `recommendation_confidence`/`recommendation_risk_level` (copied from `recommendations`) · `decision_mode` · `decision` (APPROVED/REJECTED) · `decided_at` · `compliance_checks_count`/`pass_count`/`warn_count`/`fail_count`/`review_required_count` · `human_review_required`/`human_review_id` · `review_priority_score` · `decision_reason_code`.
**Used in:** Trust screen — "Recent AI Decisions" table (all columns, all 2,000 rows, no pagination). Approve/Reject/Escalate buttons always error server-side ("immutable audit records").

---

# `data/synthetic/logistics/`

*Freight shipment transactions and warehouse-touchpoint telemetry.*

## 38. Shipment Records — `shipments`
**Columns:** `shipment_id` (PK) · `route_id`/`route_type`/`transport_mode` (FK) · origin/destination warehouse-city-region (denorm) · `distance_km`/`typical_transit_hours`/`sla_hours`/`baseline_cost_inr` (denorm) · `vehicle_id`/`units`/`priority` · `desired_dispatch_time`/`dispatch_time` · `expected_arrival`/`sla_deadline`/`actual_arrival` · `weather_disruption`/`vehicle_breakdown`/`warehouse_delay`/`port_delay`/`customs_delay` · `dispatch_delay_minutes`/`actual_transit_hours`/`arrival_variance_minutes` · `delay_minutes`/`early_arrival_minutes` · `sla_breach` · `shipment_status`.
**Used in:** Logistics screen — "SLA risk %" (`sla_breach` share), "Delay prob. %" (`delay_minutes>0 OR dispatch_delay_minutes>0`), "Predict Delay" button (re-runs same query — not a forecast), route card "Cost" tile (`AVG(baseline_cost_inr)`). Disruption-cause flags stored but never aggregated.

## 39. Warehouse Events — `warehouse_events`
**Columns:** `warehouse_event_id` (PK) · `shipment_id`/`event_sequence`/`route_id`/`vehicle_id` (FK) · `event_type`/`direction` · `warehouse_id`/`name`/`city`/`region`/`warehouse_type` (denorm) · `event_at` · `units_moved`/`inventory_delta_units` · `priority` · `dock_id` · `warehouse_utilization_pct` · `dock_queue_depth`/`dock_wait_minutes` · `handling_minutes`/`picking_delay_minutes`/`putaway_delay_minutes` · `congestion_flag` · `event_status`.
**Used in:** Logistics screen — "Warehouse Signals" congestion tile (`congestion_flag` share) and dock-wait tile (`AVG(dock_wait_minutes)`). Most other columns (queue depth, handling/picking/putaway delays, inventory delta) unused.

---

# `data/synthetic/master/`

*Stable reference/master data (geography, vehicle models, dealers, plants, warehouses, finance products) that operational tables denormalize against.*

## 40. Cities — `cities`
**Columns:** `city_id` (PK) · `city_name` · `region_id` (FK) · `region_name` · `generation_weight_within_region`.
**Used in:** Not used — every screen reads denormalized `city_id`/`city_name` off other tables instead.

## 41. Dealers — `dealers`
**Columns:** `dealer_id` (PK) · `dealer_name` · `city_id`/`city_name` · `region_id`/`region_name` · `dealer_tier` · `monthly_lead_capacity` · `monthly_test_drive_capacity` · `monthly_booking_capacity` · `sales_consultants` · `service_bays` — capacity denominator for bay-utilization KPI · `followup_sla_hours` · `active`.
**Used in:** Dealer Cockpit — dealer selector (`dealer_id`/`dealer_name`), `service_bays` for "Bay utilization" KPI. Legacy ORM `Dealer`/`DealerLead` (dead, duplicates dashboard numbers as columns).

---

## 42. Finance Products — `finance_products`
**Columns:** `finance_product_id` (PK) · `product_code`/`product_name` · `product_category` · `secured` · `min_max_loan_amount_inr` · `min_max_tenure_months` · `base_interest_rate_pct` · `max_ltv_pct` · `target_segment` · `active`.
**Used in:** Finance screen — product portfolio cards: `customers` = COUNT(loan_accounts), `risk` = 30+DPD share, `cross` = COUNT(cross_sell_events), `opp` = SUM(offer_amount_inr).

## 43. Machines — `machines`
**Columns:** `machine_id` (PK) · `production_line_id`/`plant_id` (FK) · `machine_name` · `machine_type`/`station_type` · `rated_capacity_units_per_hour` · `baseline_load_pct` · `maintenance_interval_hours` · `active`.
**Used in:** Not queried for display. Used server-side by the causal scheduler to expand the PCMCI machine cohort to sibling machines on the same `production_line_id`.

## 44. Plants — `plants`
**Columns:** `plant_id` (PK) · `plant_name` · `city_name`/`region_name` · `plant_type` · `daily_capacity_units`.
**Used in:** Not queried directly — Warranty & Quality screen reads `plant_id`/`plant_name` denormalized off `manufacturing_timeseries`/`production_batches`/`service_events`/`warranty_claims` instead.

## 45. Production Lines — `production_lines`
**Columns:** `production_line_id` (PK) · `plant_id` (FK) · `line_name` · `line_type` (BODY/PAINT/ASSEMBLY) · `units_per_hour` · `shift_count` · `active`.
**Used in:** Not queried directly. Its `line_type` taxonomy (mirrored on `manufacturing_timeseries`) drives PAINT-vs-ALL scope stratification in the PCMCI stability filter.

## 46. Regions — `regions`
**Columns:** `region_id` (PK) — region code · `region_name` — display name · `generation_weight` — generator tuning only.
**Used in:** Simulation Center — region dropdown (`region_name`). Not queried directly by Dealer Cockpit/Overview (they use denormalized copies on other tables).

## 47. Logistics Route Master — `routes`
**Columns:** `route_id` (PK) · `origin_warehouse_id`/`name`, `origin_city_id`/`name`, `origin_region_id`/`name` · `destination_warehouse_id`/`name`, `destination_city_id`/`name`, `destination_region_id`/`name` · `route_type`/`transport_mode` · `distance_km`/`typical_transit_hours`/`sla_hours` · `baseline_cost_inr`/`baseline_risk_score` · `active`.
**Used in:** Logistics screen — route card title (`origin_city_name → destination_city_name`), "Cost" tile fallback.

## 48. Vehicle Models — `vehicle_models`
**Columns:** `vehicle_model_id` (PK) · `model_name` · `segment` · `base_price` (INR) · `currency` · `gross_margin_pct` · `typical_lead_to_booking_rate` · `typical_cancellation_rate` · `typical_finance_share` · `production_complexity` · `generation_weight`.
**Used in:** Dealer Cockpit — `base_price` (lead "Revenue"), `model_name`. Simulation Center — `model_name` dropdown.

## 49. Warehouse Master — `warehouses`
**Columns:** `warehouse_id` (PK) · `warehouse_name` · `city_id`/`name`, `region_id`/`name` · `warehouse_type` · `storage_capacity_units` · `baseline_utilization_pct` · `daily_throughput_capacity` · `active`.
**Used in:** Logistics screen — "Warehouse Signals" utilization tile fallback (`baseline_utilization_pct`).

---

# `data/synthetic/xr/`

*AR/VR/XR experience catalogue and session usage log.*

## 50. XR Experience Catalog — `xr_experiences`
**Columns:** `experience_id` (PK) · `experience_type` · `experience_category` · `primary_persona_group` · `device_mode` · `supports_ai_assistant`/`supports_configuration`/`supports_training_score`/`supports_repair_steps` · `active`.
**Used in:** XR screen — card title/description/feature line. "Impact" line always returns a static "no measured impact" string — never derived from `xr_sessions`.

## 51. XR Session Records — `xr_sessions`
**Columns:** `session_id` (PK) · `experience_id`/`type`/`category`/`device_mode` (FK) · `vehicle_model_id`/`name`/`segment` · `persona` · `started_at`/`completed_at` · `engagement_seconds` · `configuration_selected` · `assistant_interactions` · `training_score` · `repair_steps_completed`/`repair_steps_total` · `conversion_or_completion_outcome`.
**Used in:** Not used anywhere — no service/route reads this table at all, despite being the natural source for XR's currently-static "impact" metrics.

---

## End of document