// Typed fetch functions — one per backend endpoint under `/api/v1`.

import { apiFetch } from "@/lib/api/client";
import type {
  AiAgent,
  AutoHeal,
  AutoSalesSimIn,
  AutoSalesSimOut,
  Bucket,
  CausalDrivers,
  CollectionsAgent,
  CollectionsCase,
  CollectionsSimIn,
  CollectionsSimOut,
  ComplianceRule,
  CopilotResult,
  Credit,
  CreditPricingSimIn,
  CreditPricingSimOut,
  CustomerTwin,
  Dealer,
  DealerAllocationSimIn,
  DealerAllocationSimOut,
  DealerCoach,
  DealerLead,
  ElvEstimate,
  ExecutiveSummary,
  FinanceProduct,
  Kpi,
  LeadPitch,
  LogisticsDelaySimIn,
  LogisticsDelaySimOut,
  LogisticsRoute,
  MetricTile,
  MobilityGraph,
  MobilityKpi,
  PocItem,
  QaAnswer,
  Recommendation,
  RmScript,
  RoadmapPlan,
  Signal,
  SimulateOffer,
  SimulationMeta,
  TrustDecision,
  TwinExplain,
  TwinSummary,
  WorkflowRun,
  XrExperience,
} from "@/lib/api/types";

const q = (params: Record<string, string | number | undefined>) => {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined);
  if (!entries.length) return "";
  return `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString()}`;
};

// --- Overview -----------------------------------------------------------------
export const fetchKpis = () => apiFetch<Kpi[]>("/overview/kpis");
export const fetchRecommendations = () => apiFetch<Recommendation[]>("/overview/recommendations");
export const updateRecommendation = (recCode: string, status: "Approved" | "Under Review") =>
  apiFetch<Recommendation>(`/recommendations/${recCode}`, {
    method: "PATCH",
    body: { status },
  });

// --- Catalogue & PoC --------------------------------------------------------------
export const fetchBuckets = (tag?: string | null) =>
  apiFetch<Bucket[]>(`/catalogue/buckets${q({ tag: tag ?? undefined })}`);
export const fetchCatalogueTags = () => apiFetch<string[]>("/catalogue/tags");
export const fetchPocs = () => apiFetch<PocItem[]>("/poc");
export const addPoc = (name: string, bucket: string) =>
  apiFetch<PocItem>("/poc", { method: "POST", body: { name, bucket } });
export const removePoc = (name: string) =>
  apiFetch<void>(`/poc${q({ name })}`, { method: "DELETE" });
export const fetchRoadmapPlan = () => apiFetch<RoadmapPlan>("/poc/roadmap-plan");

// --- Dealers ------------------------------------------------------------------------
export const fetchDealers = () => apiFetch<Dealer[]>("/dealers");
export const fetchDealerLeads = (dealerCode: string) =>
  apiFetch<DealerLead[]>(`/dealers/${dealerCode}/leads`);
export const fetchDealerCoach = (dealerCode: string) =>
  apiFetch<DealerCoach>(`/dealers/${dealerCode}/coach`);
export const fetchLeadPitch = (dealerCode: string, leadId: string) =>
  apiFetch<LeadPitch>(`/dealers/${dealerCode}/leads/${leadId}/pitch`, { method: "POST" });
export const messageLead = (leadId: string) =>
  apiFetch<DealerLead>(`/dealer-leads/${leadId}/message`, { method: "POST" });
export const scheduleTestDrive = (leadId: string, slot: string) =>
  apiFetch<DealerLead>(`/dealer-leads/${leadId}/test-drive`, {
    method: "POST",
    body: { slot },
  });
export const convertLead = (leadId: string) =>
  apiFetch<DealerLead>(`/dealer-leads/${leadId}/convert`, { method: "POST" });

// --- Finance ---------------------------------------------------------------------------
export const fetchFinanceProducts = () => apiFetch<FinanceProduct[]>("/finance/products");
export const fetchTwinSummaries = () => apiFetch<TwinSummary[]>("/finance/twins");
export const fetchCustomerTwin = (twinId: string) =>
  apiFetch<CustomerTwin>(`/finance/customers/${twinId}/twin`);
export const submitTwinApproval = (twinId: string) =>
  apiFetch<CustomerTwin>(`/finance/twins/${twinId}/submit-approval`, { method: "POST" });
export const explainTwin = (twinId: string) =>
  apiFetch<TwinExplain>(`/finance/twins/${twinId}/explain`, { method: "POST" });
export const generateRmScript = (twinId: string) =>
  apiFetch<RmScript>(`/finance/twins/${twinId}/rm-script`, { method: "POST" });
export const simulateOffer = (twinId: string, amount: number) =>
  apiFetch<SimulateOffer>(`/finance/twins/${twinId}/simulate-offer`, {
    method: "POST",
    body: { amount },
  });

// --- Collections -----------------------------------------------------------------------
export const fetchCollectionsMetrics = () => apiFetch<MetricTile[]>("/collections/metrics");
export const fetchCollectionsAgents = () => apiFetch<CollectionsAgent[]>("/collections/agents");
export const fetchCollectionsCases = () => apiFetch<CollectionsCase[]>("/collections/cases");
export const approveCase = (caseId: string) =>
  apiFetch<CollectionsCase>(`/collections/cases/${caseId}/approve`, { method: "POST" });
export const modifyCase = (caseId: string, action: string) =>
  apiFetch<CollectionsCase>(`/collections/cases/${caseId}/modify`, {
    method: "POST",
    body: { action },
  });
export const reviewCase = (caseId: string) =>
  apiFetch<CollectionsCase>(`/collections/cases/${caseId}/review`, { method: "POST" });
export const fetchCaseLedger = (caseId: string) =>
  apiFetch<string[]>(`/collections/cases/${caseId}/ledger`);

// --- Logistics ----------------------------------------------------------------------------
export const fetchRoutes = () => apiFetch<LogisticsRoute[]>("/logistics/routes");
export const fetchWarehouseSignals = () => apiFetch<Signal[]>("/logistics/warehouse-signals");
export const predictDelay = (routeId: string) =>
  apiFetch<LogisticsRoute>(`/logistics/routes/${routeId}/predict-delay`, { method: "POST" });
export const rerouteRoute = (routeId: string) =>
  apiFetch<LogisticsRoute>(`/logistics/routes/${routeId}/reroute`, { method: "POST" });
export const autoHealRoute = (routeId: string) =>
  apiFetch<AutoHeal>(`/logistics/routes/${routeId}/auto-heal`, { method: "POST" });

// --- Circularity ------------------------------------------------------------------------
export const fetchCredits = () => apiFetch<Credit[]>("/circularity/credits");
export const fetchRvsfMetrics = () => apiFetch<MetricTile[]>("/circularity/rvsf-metrics");
export const fetchDmrvPrompts = () => apiFetch<string[]>("/circularity/dmrv/prompts");
export const askDmrv = (question: string) =>
  apiFetch<QaAnswer>("/circularity/dmrv/ask", { method: "POST", body: { question } });
export const estimateElv = (payload: {
  vehicleType: string;
  age: number;
  condition: number;
  docs: number;
}) => apiFetch<ElvEstimate>("/circularity/elv/estimate", { method: "POST", body: payload });
export const repriceCredit = (creditCode: string) =>
  apiFetch<Credit>(`/circularity/credits/${creditCode}/reprice`, { method: "POST" });
export const matchCreditBuyer = (creditCode: string) =>
  apiFetch<Credit>(`/circularity/credits/${creditCode}/match-buyer`, { method: "POST" });

// --- Trust ledger ---------------------------------------------------------------------------
export const fetchTrustDecisions = () => apiFetch<TrustDecision[]>("/trust/decisions");
export const fetchComplianceRules = () => apiFetch<ComplianceRule[]>("/trust/compliance-rules");
export const approveDecision = (decisionCode: string) =>
  apiFetch<TrustDecision>(`/trust/decisions/${decisionCode}/approve`, { method: "POST" });
export const rejectDecision = (decisionCode: string, reason: string) =>
  apiFetch<TrustDecision>(`/trust/decisions/${decisionCode}/reject`, {
    method: "POST",
    body: { reason },
  });
export const escalateDecision = (decisionCode: string) =>
  apiFetch<TrustDecision>(`/trust/decisions/${decisionCode}/escalate`, { method: "POST" });

// --- Agents & XR -----------------------------------------------------------------------
export const fetchAgents = () => apiFetch<AiAgent[]>("/agents");
export const runWorkflow = () => apiFetch<WorkflowRun>("/agents/workflow/run", { method: "POST" });
export const fetchXrExperiences = () => apiFetch<XrExperience[]>("/xr/experiences");

// --- Mobility twin ----------------------------------------------------------------------------
export const fetchMobilityGraph = () => apiFetch<MobilityGraph>("/mobility-twin/graph");
export const fetchMobilityKpis = () => apiFetch<MobilityKpi[]>("/mobility-twin/kpis");
export const askMobilityTwin = (question: string) =>
  apiFetch<QaAnswer>("/mobility-twin/ask", { method: "POST", body: { question } });

// --- Simulations ----------------------------------------------------------------------------
export const fetchSimulationMeta = () => apiFetch<SimulationMeta>("/simulations/meta");
export const fetchCausalDrivers = (domain: string) =>
  apiFetch<CausalDrivers>(`/simulations/causal-drivers${q({ domain })}`);
export const runAutoSalesSim = (payload: AutoSalesSimIn) =>
  apiFetch<AutoSalesSimOut>("/simulations/auto-sales/run", { method: "POST", body: payload });
export const runDealerAllocationSim = (payload: DealerAllocationSimIn) =>
  apiFetch<DealerAllocationSimOut>("/simulations/dealer-allocation/run", {
    method: "POST",
    body: payload,
  });
export const runCollectionsSim = (payload: CollectionsSimIn) =>
  apiFetch<CollectionsSimOut>("/simulations/collections/run", { method: "POST", body: payload });
export const runLogisticsDelaySim = (payload: LogisticsDelaySimIn) =>
  apiFetch<LogisticsDelaySimOut>("/simulations/logistics-delay/run", {
    method: "POST",
    body: payload,
  });
export const runCreditPricingSim = (payload: CreditPricingSimIn) =>
  apiFetch<CreditPricingSimOut>("/simulations/credit-pricing/run", {
    method: "POST",
    body: payload,
  });

// --- Copilot & executive summary ---------------------------------------------------------
export const fetchSuggestedPrompts = () => apiFetch<string[]>("/copilot/suggested-prompts");
export const chatCopilot = (message: string) =>
  apiFetch<CopilotResult>("/copilot/chat", { method: "POST", body: { message } });
export const generateExecutiveSummaryApi = (useCase: string) =>
  apiFetch<ExecutiveSummary>("/executive-summary", { method: "POST", body: { useCase } });
