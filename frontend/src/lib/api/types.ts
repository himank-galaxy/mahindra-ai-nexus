// Response types mirroring the backend Pydantic schemas 1:1 (JSON keys).
// Keep in sync with `backend/app/schemas/*` — parity is asserted by the
// backend tests.

// --- Overview -------------------------------------------------------------
export type Kpi = {
  id: string;
  label: string;
  value: string;
  trend: string;
  up: boolean;
  confidence: number;
  drivers: string[];
};

export type Recommendation = {
  id: string;
  title: string;
  impact: string;
  confidence: number;
  risk: string;
  status: string;
};

// --- Catalogue & PoC --------------------------------------------------------
export type Solution = {
  name: string;
  problem: string;
  solution: string;
  diff: string;
  impact: string;
};

export type Bucket = {
  name: string;
  tag: string;
  items: Solution[];
};

export type PocItem = {
  id: string;
  name: string;
  bucket: string;
  addedAt: number;
};

export type RoadmapPhase = {
  p: string;
  t: string;
  w: string;
  d: string;
};

export type RoadmapPlan = {
  phases: RoadmapPhase[];
  topPocs: string[];
  optional: string;
};

// --- Dealers ----------------------------------------------------------------
export type Dealer = {
  id: string;
  name: string;
  leads: number;
  hotLeads: number;
  testDrivesPending: number;
  bookingProb: number;
  revenueAtRisk: string;
  leakage: string;
  bayUtil: string;
};

export type DealerLead = {
  id: string;
  name: string;
  vehicle: string;
  score: number;
  prob: number;
  action: string;
  revenue: string;
  status: string;
};

export type DealerCoach = {
  topAction: string;
  expected: string;
  bestOffer: string;
  bestTime: string;
  risk: string;
};

export type LeadPitch = {
  name: string;
  text: string;
};

// --- Finance ------------------------------------------------------------------
export type FinanceProduct = {
  name: string;
  customers: string;
  risk: string;
  cross: string;
  opp: string;
};

export type TwinSummary = {
  id: string;
  name: string;
};

export type TwinNba = {
  headline: string;
  risk: string;
  expected_margin: string;
  confidence: number;
};

export type CustomerTwin = {
  id: string;
  name: string;
  location: string;
  income_stability: string;
  repayment: string;
  products: string[];
  nba: TwinNba;
  risk_decomposition: Record<string, string>;
  cross_sell: Record<string, string>;
  approval_status: string;
};

export type TwinExplain = {
  bullets: string[];
};

export type RmScript = {
  script: string;
};

export type SimulateOffer = {
  amount: number;
  emi: number;
  risk: string;
};

// --- Collections -----------------------------------------------------------
export type MetricTile = {
  label: string;
  value: string;
  tone: string;
};

export type CollectionsAgent = {
  name: string;
  status: string;
};

export type CollectionsCase = {
  id: string;
  customer: string;
  dpd: number;
  out: string;
  roll: number;
  channel: string;
  action: string;
  prob: number;
  flag: string;
  status: string;
};

// --- Logistics ----------------------------------------------------------------
export type LogisticsRoute = {
  id: string;
  name: string;
  slaRisk: number;
  delayProb: number;
  cost: string;
  action: string;
  rerouted: boolean;
};

export type Signal = {
  label: string;
  value: string;
  tone: string;
};

export type AutoHeal = {
  route: LogisticsRoute;
  steps: string[];
};

// --- Circularity ----------------------------------------------------------------
export type Credit = {
  id: string;
  type: string;
  price: string;
  match: number;
  closure: number;
  trace: number;
};

export type ElvEstimate = {
  price: number;
  recoverable: number;
  risks: string[];
};

export type QaAnswer = {
  question: string;
  answer: string;
};

// --- Trust ledger ---------------------------------------------------------------
export type TrustDecision = {
  id: string;
  use: string;
  rec: string;
  data: string;
  conf: number;
  approval: string;
  risk: string;
  audit: string;
};

export type ComplianceRule = {
  label: string;
  status: string;
};

// --- Agents & XR -------------------------------------------------------------
export type AiAgent = {
  id: string;
  name: string;
  role: string;
  status: string;
  last: string;
  uses: string[];
};

export type XrExperience = {
  id: string;
  title: string;
  use: string;
  feat: string;
  impact: string;
};

export type WorkflowStage = {
  stage: string;
  message: string;
};

export type WorkflowRun = {
  stages: WorkflowStage[];
  intervalMs: number;
};

// --- Mobility twin ----------------------------------------------------------
// Field names below deliberately match the backend's raw JSON (snake_case)
// exactly — this codebase does not camelCase API responses (see e.g.
// WarrantyQualityCausalPathSupport's source_metric/mean_abs_score below).
export type CausalNode = {
  label: string;
  x: number;
  y: number;
  /** Raw metric identifier (e.g. "lead_volume") — use this, not `metric`,
   * to fetch node detail via GET /mobility-twin/nodes/{metric_key}. */
  metric_key: string;
  /** Formatted display value (e.g. "26.1"), NOT the metric key. */
  metric: string;
  trend: string;
  drivers: string[];
  action: string;
};

export type MobilityGraph = {
  nodes: CausalNode[];
  edges: [string, string][];
};

export type MobilityKpi = {
  label: string;
  value: string;
  trend: string;
};

export type MobilityNodeStats = {
  mean: number;
  min: number;
  max: number;
  std: number;
};

export type MobilityNodeHistoryPoint = {
  timestamp: string;
  value: number;
};

export type MobilityNodeRelationship = {
  metric: string;
  label: string;
  direction: "into" | "out_of";
  score: number;
  lag_minutes: number;
  p_value: number;
};

export type MobilityNodeDetail = {
  metric: string;
  label: string;
  current_value: number;
  display_value: string;
  trend_pct: number;
  trend_label: string;
  stats: MobilityNodeStats;
  history: MobilityNodeHistoryPoint[];
  relationships: MobilityNodeRelationship[];
  top_drivers: MobilityNodeRelationship[];
  recommended_action: string;
};

export type MobilityCopilotTurn = {
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type MobilityCopilotHistory = {
  session_id: string;
  turns: MobilityCopilotTurn[];
};

// --- Warranty, Quality & Service early warning -----------------------------

export type WarrantyQualityPriority = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export type WarrantyQualityLineageEvidenceGrade =
  | "EXACT_WINDOW_LINEAGE"
  | "PARTIAL_EXACT_WINDOW_LINEAGE"
  | "NO_EXACT_WINDOW_LINEAGE"
  | "NO_FIELD_LINEAGE";

export type WarrantyQualityExactLineage = {
  machine_id: string;
  production_batch_id: string;
  supplier_lot_id: string;
};

export type WarrantyQualityCausalPathSupport = {
  source_metric: string;
  target_metric: string;

  scope: string;
  consensus_sign: string;

  recurring_machines: number;
  eligible_machines: number;

  recurrence_fraction: number;
  sign_agreement: number;

  mean_abs_score: number;
  best_q_value: number;

  observed_lags: number[];

  overlap_machines: string[];
  overlap_count: number;

  issue_exact_lineage_machine_fraction: number;
  causal_edge_machine_fraction: number;

  exact_lineage_count: number;
  exact_lineage_fraction: number;

  edge_type?: string;
  provenance?: string;
  causal_domain?: string;
  causal_run_id?: string | null;
  observed_lag_minutes?: number[];
  best_p_value?: number | null;
  min_p_value?: number | null;
  max_p_value?: number | null;
  min_q_value?: number | null;
  max_q_value?: number | null;
  median_abs_score?: number | null;
  recurring_vehicles?: number;
  eligible_vehicles?: number;
  supporting_vehicle_ids?: string[];
  overlap_vehicles?: string[];
  overlap_vehicle_count?: number;
  issue_vehicle_fraction?: number;
  causal_edge_vehicle_fraction?: number;
};

export type WarrantyQualityEvidenceGraphNode = {
  node_id: string;
  node_type: string;
  label: string;
  metadata: Record<string, unknown>;
};

export type WarrantyQualityEvidenceGraphEdge = {
  source_node_id: string;
  target_node_id: string;
  edge_type: string;
  provenance: string;
  metadata: Record<string, unknown>;
};

export type WarrantyQualityEvidenceGraph = {
  nodes: WarrantyQualityEvidenceGraphNode[];
  edges: WarrantyQualityEvidenceGraphEdge[];
};

export type WarrantyQualitySupplierHotspot = {
  supplier_id: string;
  supplier_name: string;
  component_category: string;

  claims: number;
  supplier_lots: number;
  batches: number;

  approved_exposure_inr: number;
};

export type WarrantyQualityMarketHotspot = {
  vehicle_model_name: string;
  variant: string;

  region_name: string;
  city_name: string;

  claims: number;
  batches: number;
  supplier_lots: number;

  approved_exposure_inr: number;
};

export type WarrantyQualityWarningCalibration = {
  issue_categories: number;

  complaints_p50: number;
  complaints_p75: number;
  complaints_p90: number;

  claims_p50: number;
  claims_p75: number;
  claims_p90: number;

  approved_exposure_p50: number;
  approved_exposure_p75: number;
  approved_exposure_p90: number;

  batches_p75: number;
  supplier_lots_p75: number;
  cities_p75: number;

  evidence_score_p50: number;
  evidence_score_p75: number;
  evidence_score_p90: number;
};

export type WarrantyQualityWarning = {
  issue_category: string;

  priority: WarrantyQualityPriority;

  /**
   * Transparent empirical evidence index.
   *
   * This is not a probability and must not be rendered as
   * model confidence or causal confidence.
   */
  evidence_score: number;

  service_events: number;
  complaints: number;
  repairs: number;

  warranty_candidates: number;
  warranty_claims: number;

  service_low_events: number;
  service_medium_events: number;
  service_high_events: number;

  affected_machines: number;
  affected_vehicles: number;
  affected_batches: number;
  affected_supplier_lots: number;
  affected_models: number;
  affected_cities: number;

  claim_exposure_inr: number;
  approved_exposure_inr: number;

  field_lineages: number;
  exact_window_lineages: number;
  exact_window_lineage_coverage: number;
  exact_lineage_machines: number;

  lineage_evidence_grade: WarrantyQualityLineageEvidenceGrade;

  machine_ids: string[];

  exact_lineages: WarrantyQualityExactLineage[];

  causal_paths: WarrantyQualityCausalPathSupport[];

  supplier_hotspots: WarrantyQualitySupplierHotspot[];

  market_hotspots: WarrantyQualityMarketHotspot[];

  service_event_ids?: string[];
  warranty_claim_ids?: string[];
  telematics_edges_considered?: number;
  telematics_paths_selected?: number;
  telematics_eligibility_diagnostics?: Record<string, unknown>;
  lifecycle_state?: "NEW" | "ACTIVE" | "ESCALATED" | "DEESCALATED" | "RESOLVED" | "UNCHANGED";
  warning_signature?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  last_transition_at?: string | null;
  evidence_graph?: WarrantyQualityEvidenceGraph;
};

export type WarrantyQualityEarlyWarning = {
  /** UUID serialized by FastAPI as a JSON string. */
  causal_run_id: string;

  causal_signature: string;

  /** ISO-8601 datetime strings serialized by FastAPI. */
  source_from: string;
  source_to: string;
  generated_at: string;

  issue_categories_evaluated: number;
  issue_categories_with_exact_lineage: number;
  warnings_generated: number;

  calibration: WarrantyQualityWarningCalibration;

  warnings: WarrantyQualityWarning[];

  manufacturing_causal_run_id?: string | null;
  telematics_causal_run_id?: string | null;
  telematics_causal_signature?: string | null;
  telematics_source_from?: string | null;
  telematics_source_to?: string | null;
  simulation_as_of?: string | null;
};

export type WarrantyQualityGraphDelta = {
  new_edges: number;
  removed_edges: number;
  unchanged_edges: number;
  strengthened_edges: number;
  weakened_edges: number;
  sign_changed_edges: number;
  previous_run_id?: string | null;
};

export type WarrantyQualityDataFreshness = {
  source: "manufacturing" | "telematics" | "service" | "warranty" | "ingestion" | "warning";
  observed_at?: string | null;
  age_minutes?: number | null;
  status: "AVAILABLE" | "NOT_AVAILABLE";
};

/**
 * Physical ingestion state for one domain's own immutable replay source.
 * `replay_cursor` is how far that domain has been replayed; `runtime_*` are
 * read straight off the runtime table, so they are the physical proof that
 * rows actually landed rather than a restatement of the checkpoint.
 */
export type WarrantyQualityIngestionStatus = {
  domain: "manufacturing" | "telematics" | "service" | "warranty";
  source_table: string;
  status: string;
  source_available_from?: string | null;
  source_available_to?: string | null;
  replay_start?: string | null;
  replay_cursor?: string | null;
  initialized_at?: string | null;
  exhausted_at?: string | null;
  last_tick_at?: string | null;
  tick_count: number;
  last_ingested_timestamp?: string | null;
  last_ingested_rows: number;
  rows_ingested_total: number;
  runtime_row_count: number;
  runtime_max_timestamp?: string | null;
  last_commit_at?: string | null;
  last_error?: string | null;
  diagnostics: Record<string, unknown>;
};

export type WarrantyQualityWarningStatus = {
  status: string;
  evaluation_run_id?: string | null;
  evaluation_signature?: string | null;
  field_evidence_signature?: string | null;
  manufacturing_causal_run_id?: string | null;
  telematics_causal_run_id?: string | null;
  computed_at?: string | null;
  last_evaluated_at?: string | null;
  warning_count: number;
  lifecycle_counts: Record<string, number>;
  runtime_seconds?: number | null;
  last_error?: string | null;
};

export type WarrantyQualityRunStatus = {
  domain: "manufacturing" | "telematics";
  status: string;
  run_id?: string | null;
  signature?: string | null;
  computed_at?: string | null;
  source_from?: string | null;
  source_to?: string | null;
  source_rows?: number | null;
  stable_edge_count?: number | null;
  data_freshness: WarrantyQualityDataFreshness;
  model_freshness?: string | null;
  graph_delta: WarrantyQualityGraphDelta;
  last_refresh_at?: string | null;
  next_refresh_at?: string | null;
  last_error?: string | null;
  diagnostics: Record<string, unknown>;
  active_run_started_at?: string | null;
  active_target_watermark?: string | null;
  pending_refresh?: boolean;
  pending_target_watermark?: string | null;
  last_runtime_seconds?: number | null;
  last_completed_at?: string | null;
};

export type WarrantyQualityCausalStatus = {
  simulation: {
    simulation_as_of: string;
    replay_start: string;
    replay_end: string;
    replay_speed: number;
    paused: boolean;
    status: "RUNNING" | "PAUSED" | "COMPLETE";
    last_tick_at: string;
    tick_count: number;
  };
  data_freshness: WarrantyQualityDataFreshness[];
  ingestion: WarrantyQualityIngestionStatus[];
  manufacturing: WarrantyQualityRunStatus;
  telematics: WarrantyQualityRunStatus;
  warning: WarrantyQualityWarningStatus;
  scheduler: {
    enabled: boolean;
    last_refresh_at?: string | null;
    next_refresh_at?: string | null;
    status: string;
  };
};

// --- Data explorer -------------------------------------------------------------
export type DataColumn = { name: string; data_type: string; nullable: boolean };
export type DataDatasetLink = { module_id: string; relationship_type: string };
export type DataDataset = {
  id: string;
  display_name: string;
  table_name: string;
  description: string;
  timestamp_column?: string | null;
  refresh_mode: string;
  columns: DataColumn[];
  links: DataDatasetLink[];
};
export type DataModule = {
  id: string;
  label: string;
  route?: string | null;
  description: string;
  datasets: DataDataset[];
};
export type DataCatalog = { modules: DataModule[]; generated_from: string };
export type DataMetadata = {
  total_rows: number;
  column_count: number;
  latest_timestamp?: string | null;
  source: string;
  refresh_mode: string;
  live_status: string;
  data_version: string;
  last_refreshed_at: string;
};
export type DataPagination = {
  page_size: number;
  has_next: boolean;
  has_previous: boolean;
  next_cursor?: string | null;
  previous_cursor?: string | null;
};
export type DataRows = {
  dataset: DataDataset;
  columns: DataColumn[];
  rows: Record<string, unknown>[];
  metadata: DataMetadata;
  pagination: DataPagination;
};
export type DataStatus = {
  dataset_id: string;
  total_rows: number;
  latest_timestamp?: string | null;
  refresh_mode: string;
  live_status: string;
  data_version: string;
  last_checked_at: string;
};

// --- Simulations --------------------------------------------------------------
export type RouteOption = {
  id: string;
  label: string;
};

export type SimulationMeta = {
  regions: string[];
  models: string[];
  routes: RouteOption[];
};

export type AutoSalesSimIn = {
  region: string;
  model: string;
  discount: number;
  bonus: number;
  campaign: number;
  intensity: "Low" | "Medium" | "High";
};

export type SimulationRunStatus =
  | "DRAFT"
  | "COMPLETED"
  | "PROPOSED"
  | "APPROVED"
  | "REJECTED"
  | "HUMAN_REVIEW"
  | "EXECUTED";

export type AutoSalesSimOut = {
  run_id: string;
  status: SimulationRunStatus;
  confidence_band: "low" | "medium" | "high";
  confidence_basis: "trained_model" | "calibrated_heuristic";
  uplift: number;
  margin: number;
  cancel: number;
  rev: number;
  conf: number;
  recommendedAction: string;
};

export type SimulationApprovalOut = {
  run_id: string;
  status: SimulationRunStatus;
  decision: "approved" | "rejected";
  decided_at: string;
  actor: string;
};

export type SimulationDriverItem = {
  name: string;
  direction: "positive" | "negative";
  contribution: number;
  source: "trained_model" | "calibrated_heuristic";
  detail: string;
};

export type SimulationCausalEdgeItem = {
  source: string;
  target: string;
  lag_days: number;
  score: number;
  p_value: number;
};

export type SimulationDriversOut = {
  run_id: string;
  domain: string;
  predictive_drivers: SimulationDriverItem[];
  causal_evidence: SimulationCausalEdgeItem[];
  causal_evidence_note: string;
};

export type SimulationSummaryOut = {
  run_id: string;
  scenario: string;
  inputs_summary: string;
  baseline: string;
  predicted_outcome: string;
  major_drivers: string[];
  trade_off: string;
  recommendation: string;
  confidence: string;
  risk: string;
};

export type DealerAllocationSimIn = {
  units: number;
  demand: number;
  capacity: number;
  wait: number;
};

export type DealerAllocationSimOut = {
  run_id: string;
  status: SimulationRunStatus;
  confidence_band: "low" | "medium" | "high";
  confidence_basis: "trained_model" | "calibrated_heuristic";
  delay: number;
  rev: number;
  csat: number;
  suggestedSplit: string;
  conf: number;
  recommendedAction: string;
};

export type CollectionsSimIn = {
  risk: "Low" | "Medium" | "High";
  // Real recorded categories (see app/repositories/collections_simulation.py)
  // — no UI-to-real translation, so every choice trains on genuine
  // historical outcomes.
  channel: "SMS" | "WHATSAPP" | "EMAIL" | "CALL" | "FIELD_VISIT";
  offer: "NONE" | "PAYMENT_REMINDER" | "PARTIAL_PAYMENT_PLAN" | "REPAYMENT_PLAN_DISCUSSION";
  field: number;
};

export type CollectionsSimOut = {
  run_id: string;
  status: SimulationRunStatus;
  confidence_band: "low" | "medium" | "high";
  confidence_basis: "trained_model" | "calibrated_heuristic";
  prob: number;
  cost: number;
  friction: number;
  net: number;
  conf: number;
  recommendedAction: string;
};

export type LogisticsDelaySimIn = {
  // Real route id (see app/repositories/logistics_delay_simulation.py) —
  // GET /simulations/meta lists every active route as {id, label}. No
  // UI-to-real translation, unlike the retired free-text city-pair strings.
  route: string;
  warehouse: number;
  vehicle: number;
  weather: number;
  // Real recorded categories on `shipments.priority` — replaces the
  // retired invented "Low/Medium/High" SLA-priority scale.
  sla: "LOW" | "NORMAL" | "HIGH" | "CRITICAL";
};

export type LogisticsDelaySimOut = {
  run_id: string;
  status: SimulationRunStatus;
  confidence_band: "low" | "medium" | "high";
  confidence_basis: "trained_model" | "calibrated_heuristic";
  delay: number;
  breach: number;
  reroute: string;
  cost: number;
  conf: number;
  recommendedAction: string;
};

export type CreditPricingSimIn = {
  // Real recorded categories on `credit_listings.credit_type` (see
  // app/repositories/credit_pricing_simulation.py) — no UI-to-real
  // translation, unlike the retired invented "Carbon/EPR/SDG/CD" scale.
  type: "MIXED_CIRCULARITY" | "RECYCLING_AVOIDANCE" | "REUSE_AVOIDANCE";
  supply: number;
  demand: number;
  trace: number;
  verif: number;
};

export type CreditPricingSimOut = {
  run_id: string;
  status: SimulationRunStatus;
  confidence_band: "low" | "medium" | "high";
  confidence_basis: "trained_model" | "calibrated_heuristic";
  priceBandLow: number;
  priceBandHigh: number;
  closure: number;
  match: number;
  complianceRisk: string;
  conf: number;
  recommendedAction: string;
};

export type CausalDrivers = {
  domain: string;
  drivers: string[];
};

// --- Copilot & executive summary ----------------------------------------------
export type CopilotChartPoint = {
  label: string;
  value: number;
};

export type CopilotResult = {
  answer: string;
  explanation: string;
  sql: string;
  python: string;
  chart?: CopilotChartPoint[];
  table?: {
    headers: string[];
    rows: string[][];
  };
  action: string;
  confidence: number;
};

export type ExecutiveSummary = {
  problem: string;
  solution: string;
  diff: string;
  impact: string;
  data: string;
  scope: string;
  timeline: string;
  risks: string;
  next: string;
};
