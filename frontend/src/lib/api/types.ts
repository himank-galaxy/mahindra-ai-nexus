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

export type Bucket = { name: string; tag: string; items: Solution[] };

export type PocItem = { id: string; name: string; bucket: string; addedAt: number };

export type RoadmapPhase = { p: string; t: string; w: string; d: string };

export type RoadmapPlan = { phases: RoadmapPhase[]; topPocs: string[]; optional: string };

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

export type LeadPitch = { name: string; text: string };

// --- Finance ------------------------------------------------------------------
export type FinanceProduct = {
  name: string;
  customers: string;
  risk: string;
  cross: string;
  opp: string;
};

export type TwinSummary = { id: string; name: string };

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

export type TwinExplain = { bullets: string[] };

export type RmScript = { script: string };

export type SimulateOffer = { amount: number; emi: number; risk: string };

// --- Collections -----------------------------------------------------------
export type MetricTile = { label: string; value: string; tone: string };

export type CollectionsAgent = { name: string; status: string };

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

export type Signal = { label: string; value: string; tone: string };

export type AutoHeal = { route: LogisticsRoute; steps: string[] };

// --- Circularity ----------------------------------------------------------------
export type Credit = {
  id: string;
  type: string;
  price: string;
  match: number;
  closure: number;
  trace: number;
};

export type ElvEstimate = { price: number; recoverable: number; risks: string[] };

export type QaAnswer = { question: string; answer: string };

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

export type ComplianceRule = { label: string; status: string };

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

export type WorkflowStage = { stage: string; message: string };

export type WorkflowRun = { stages: WorkflowStage[]; intervalMs: number };

// --- Mobility twin ----------------------------------------------------------
export type CausalNode = {
  label: string;
  x: number;
  y: number;
  metric: string;
  trend: string;
  drivers: string[];
  action: string;
};

export type MobilityGraph = { nodes: CausalNode[]; edges: [string, string][] };

export type MobilityKpi = { label: string; value: string; trend: string };

// --- Simulations --------------------------------------------------------------
export type SimulationMeta = { regions: string[]; models: string[] };

export type AutoSalesSimIn = {
  region: string;
  model: string;
  discount: number;
  bonus: number;
  campaign: number;
  intensity: "Low" | "Medium" | "High";
};

export type AutoSalesSimOut = {
  uplift: number;
  margin: number;
  cancel: number;
  rev: number;
  conf: number;
  recommendedAction: string;
};

export type DealerAllocationSimIn = {
  units: number;
  demand: number;
  capacity: number;
  wait: number;
};

export type DealerAllocationSimOut = {
  delay: number;
  rev: number;
  csat: number;
  suggestedSplit: string;
};

export type CollectionsSimIn = {
  risk: "Low" | "Medium" | "High";
  channel: "Digital" | "Voice" | "Field";
  offer: "Restructure" | "Waiver" | "Settlement" | "None";
  field: number;
};

export type CollectionsSimOut = { prob: number; cost: number; friction: number; net: number };

export type LogisticsDelaySimIn = {
  route: string;
  warehouse: number;
  vehicle: number;
  weather: number;
  sla: "Low" | "Medium" | "High";
};

export type LogisticsDelaySimOut = {
  delay: number;
  breach: number;
  reroute: string;
  cost: number;
};

export type CreditPricingSimIn = {
  type: string;
  supply: number;
  demand: number;
  trace: number;
  verif: number;
};

export type CreditPricingSimOut = {
  priceBandLow: number;
  priceBandHigh: number;
  closure: number;
  match: number;
  complianceRisk: string;
};

export type CausalDrivers = { domain: string; drivers: string[] };

// --- Copilot & executive summary ----------------------------------------------
export type CopilotChartPoint = { label: string; value: number };

export type CopilotResult = {
  answer: string;
  explanation: string;
  sql: string;
  python: string;
  chart?: CopilotChartPoint[];
  table?: { headers: string[]; rows: string[][] };
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
