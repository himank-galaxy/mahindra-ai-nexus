// Typed fetch functions — one per backend endpoint under `/api/v1`.

import { apiFetch } from "@/lib/api/client";
import type {
  AiAgent,
  AuditEvent,
  AutoHeal,
  AutoSalesSimIn,
  AutoSalesSimOut,
  Bucket,
  CausalDrivers,
  DataCatalog,
  DataRows,
  DataStatus,
  CaseTrustLedger,
  CollectionsAgent,
  CollectionsCase,
  CollectionsChannel,
  CollectionsOffer,
  CollectionsSimIn,
  CollectionsSimOut,
  ComplianceCheck,
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
  Explanation,
  FinanceProduct,
  Kpi,
  LeadPitch,
  LogisticsDelaySimIn,
  LogisticsDelaySimOut,
  LogisticsAction,
  LogisticsRoute,
  LogisticsShipment,
  MetricTile,
  MobilityCopilotHistory,
  MobilityGraph,
  MobilityKpi,
  MobilityNodeDetail,
  Outcome,
  PocItem,
  QaAnswer,
  Recommendation,
  RmScript,
  RoadmapPlan,
  Signal,
  ShipmentTrustLedger,
  SimulateOffer,
  SlaReport,
  SimulationApprovalOut,
  SimulationDriversOut,
  ReviewerRole,
  SimulationMeta,
  SimulationSummaryOut,
  TrustDecision,
  TrustLineageStep,
  TwinExplain,
  TwinSummary,
  WarrantyQualityCausalStatus,
  WarrantyQualityEarlyWarning,
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

// --- Catalogue & PoC ----------------------------------------------------------

export const fetchBuckets = (tag?: string | null) =>
  apiFetch<Bucket[]>(
    `/catalogue/buckets${q({
      tag: tag ?? undefined,
    })}`,
  );

export const fetchCatalogueTags = () => apiFetch<string[]>("/catalogue/tags");

export const fetchPocs = () => apiFetch<PocItem[]>("/poc");

export const addPoc = (name: string, bucket: string) =>
  apiFetch<PocItem>("/poc", {
    method: "POST",
    body: {
      name,
      bucket,
    },
  });

export const removePoc = (name: string) =>
  apiFetch<void>(`/poc${q({ name })}`, {
    method: "DELETE",
  });

export const fetchRoadmapPlan = () => apiFetch<RoadmapPlan>("/poc/roadmap-plan");

// --- Dealers ------------------------------------------------------------------

export const fetchDealers = () => apiFetch<Dealer[]>("/dealers");

export const fetchDealerLeads = (dealerCode: string) =>
  apiFetch<DealerLead[]>(`/dealers/${dealerCode}/leads`);

export const fetchDealerCoach = (dealerCode: string) =>
  apiFetch<DealerCoach>(`/dealers/${dealerCode}/coach`);

export const fetchLeadPitch = (dealerCode: string, leadId: string) =>
  apiFetch<LeadPitch>(`/dealers/${dealerCode}/leads/${leadId}/pitch`, {
    method: "POST",
  });

export const messageLead = (leadId: string) =>
  apiFetch<DealerLead>(`/dealer-leads/${leadId}/message`, {
    method: "POST",
  });

export const scheduleTestDrive = (leadId: string, slot: string) =>
  apiFetch<DealerLead>(`/dealer-leads/${leadId}/test-drive`, {
    method: "POST",
    body: { slot },
  });

export const convertLead = (leadId: string) =>
  apiFetch<DealerLead>(`/dealer-leads/${leadId}/convert`, {
    method: "POST",
  });

// --- Finance ------------------------------------------------------------------

export const fetchFinanceProducts = () => apiFetch<FinanceProduct[]>("/finance/products");

export const fetchTwinSummaries = () => apiFetch<TwinSummary[]>("/finance/twins");

export const fetchCustomerTwin = (twinId: string) =>
  apiFetch<CustomerTwin>(`/finance/customers/${twinId}/twin`);

export const submitTwinApproval = (twinId: string) =>
  apiFetch<CustomerTwin>(`/finance/twins/${twinId}/submit-approval`, {
    method: "POST",
  });

export const explainTwin = (twinId: string) =>
  apiFetch<TwinExplain>(`/finance/twins/${twinId}/explain`, {
    method: "POST",
  });

export const generateRmScript = (twinId: string) =>
  apiFetch<RmScript>(`/finance/twins/${twinId}/rm-script`, {
    method: "POST",
  });

export const simulateOffer = (twinId: string, amount: number) =>
  apiFetch<SimulateOffer>(`/finance/twins/${twinId}/simulate-offer`, {
    method: "POST",
    body: { amount },
  });

// --- Collections --------------------------------------------------------------

export const fetchCollectionsMetrics = () => apiFetch<MetricTile[]>("/collections/metrics");

export const fetchCollectionsAgents = () => apiFetch<CollectionsAgent[]>("/collections/agents");

export const fetchCollectionsCases = () => apiFetch<CollectionsCase[]>("/collections/cases");

export const approveCase = (caseId: string) =>
  apiFetch<CollectionsCase>(`/collections/cases/${caseId}/approve`, {
    method: "POST",
  });

export const modifyCase = (
  caseId: string,
  channel: CollectionsChannel,
  offer: CollectionsOffer,
  reason: string,
) =>
  apiFetch<CollectionsCase>(`/collections/cases/${caseId}/modify`, {
    method: "POST",
    body: { channel, offer, reason },
  });

export const reviewCase = (caseId: string, reviewerRole: ReviewerRole, reason: string) =>
  apiFetch<CollectionsCase>(`/collections/cases/${caseId}/review`, {
    method: "POST",
    body: { reviewer_role: reviewerRole, reason },
  });

export const fetchCaseTrustLedger = (caseId: string) =>
  apiFetch<CaseTrustLedger>(`/collections/cases/${caseId}/ledger`);

// --- Logistics ----------------------------------------------------------------

export const fetchRoutes = () => apiFetch<LogisticsRoute[]>("/logistics/routes");

export const fetchWarehouseSignals = () => apiFetch<Signal[]>("/logistics/warehouse-signals");

export const predictDelay = (routeId: string) =>
  apiFetch<LogisticsRoute>(`/logistics/routes/${routeId}/predict-delay`, {
    method: "POST",
  });

export const rerouteRoute = (routeId: string) =>
  apiFetch<LogisticsRoute>(`/logistics/routes/${routeId}/reroute`, {
    method: "POST",
  });

export const autoHealRoute = (routeId: string) =>
  apiFetch<AutoHeal>(`/logistics/routes/${routeId}/auto-heal`, {
    method: "POST",
  });

export const fetchRouteSlaReport = (routeId: string) =>
  apiFetch<SlaReport>(`/logistics/routes/${routeId}/sla-report`);

export const fetchRouteShipments = (routeId: string) =>
  apiFetch<LogisticsShipment[]>(`/logistics/routes/${routeId}/shipments`);

export const approveShipment = (shipmentId: string) =>
  apiFetch<LogisticsShipment>(`/logistics/shipments/${shipmentId}/approve`, {
    method: "POST",
  });

export const modifyShipment = (
  shipmentId: string,
  action: LogisticsAction,
  routeId: string | null,
  reason: string,
) =>
  apiFetch<LogisticsShipment>(`/logistics/shipments/${shipmentId}/modify`, {
    method: "POST",
    body: { action, route_id: routeId, reason },
  });

export const reviewShipment = (shipmentId: string, reviewerRole: ReviewerRole, reason: string) =>
  apiFetch<LogisticsShipment>(`/logistics/shipments/${shipmentId}/review`, {
    method: "POST",
    body: { reviewer_role: reviewerRole, reason },
  });

export const fetchShipmentLedger = (shipmentId: string) =>
  apiFetch<ShipmentTrustLedger>(`/logistics/shipments/${shipmentId}/ledger`);

// --- Circularity --------------------------------------------------------------

export const fetchCredits = () => apiFetch<Credit[]>("/circularity/credits");

export const fetchRvsfMetrics = () => apiFetch<MetricTile[]>("/circularity/rvsf-metrics");

export const fetchDmrvPrompts = () => apiFetch<string[]>("/circularity/dmrv/prompts");

export const askDmrv = (question: string) =>
  apiFetch<QaAnswer>("/circularity/dmrv/ask", {
    method: "POST",
    body: { question },
  });

export const estimateElv = (payload: {
  vehicleType: string;
  age: number;
  condition: number;
  docs: number;
}) =>
  apiFetch<ElvEstimate>("/circularity/elv/estimate", {
    method: "POST",
    body: payload,
  });

export const repriceCredit = (creditCode: string) =>
  apiFetch<Credit>(`/circularity/credits/${creditCode}/reprice`, {
    method: "POST",
  });

export const matchCreditBuyer = (creditCode: string) =>
  apiFetch<Credit>(`/circularity/credits/${creditCode}/match-buyer`, {
    method: "POST",
  });

// --- Trust ledger -------------------------------------------------------------

export const fetchTrustDecisions = () => apiFetch<TrustDecision[]>("/trust/decisions");

export const fetchTrustDecisionLineage = (decisionCode: string) =>
  apiFetch<TrustLineageStep[]>(`/trust/decisions/${encodeURIComponent(decisionCode)}/lineage`);

export const fetchTrustDecisionCompliance = (decisionCode: string) =>
  apiFetch<ComplianceCheck[]>(`/trust/decisions/${encodeURIComponent(decisionCode)}/compliance`);

export const fetchTrustDecisionExplanation = (decisionCode: string) =>
  apiFetch<Explanation>(`/trust/decisions/${encodeURIComponent(decisionCode)}/explanation`);

export const fetchTrustDecisionEvents = (decisionCode: string) =>
  apiFetch<AuditEvent[]>(`/trust/decisions/${encodeURIComponent(decisionCode)}/events`);

export const fetchTrustDecisionOutcome = (decisionCode: string) =>
  apiFetch<Outcome>(`/trust/decisions/${encodeURIComponent(decisionCode)}/outcome`);

export const approveDecision = (decisionCode: string) =>
  apiFetch<TrustDecision>(`/trust/decisions/${encodeURIComponent(decisionCode)}/approve`, {
    method: "POST",
  });

export const rejectDecision = (decisionCode: string, reason: string) =>
  apiFetch<TrustDecision>(`/trust/decisions/${encodeURIComponent(decisionCode)}/reject`, {
    method: "POST",
    body: { reason },
  });

export const escalateDecision = (
  decisionCode: string,
  reviewerRole: ReviewerRole,
  reason: string,
) =>
  apiFetch<TrustDecision>(`/trust/decisions/${encodeURIComponent(decisionCode)}/escalate`, {
    method: "POST",
    body: { reviewer_role: reviewerRole, reason },
  });

// --- Agents & XR ---------------------------------------------------------------

export const fetchAgents = () => apiFetch<AiAgent[]>("/agents");

export const runWorkflow = () =>
  apiFetch<WorkflowRun>("/agents/workflow/run", {
    method: "POST",
  });

export const fetchXrExperiences = () => apiFetch<XrExperience[]>("/xr/experiences");

// --- Mobility twin -------------------------------------------------------------

export const fetchMobilityGraph = () => apiFetch<MobilityGraph>("/mobility-twin/graph");

export const fetchMobilityKpis = () => apiFetch<MobilityKpi[]>("/mobility-twin/kpis");

export const fetchMobilityNodeDetail = (metricKey: string) =>
  apiFetch<MobilityNodeDetail>(`/mobility-twin/nodes/${encodeURIComponent(metricKey)}`);

export const askMobilityCopilot = (sessionId: string, message: string, selectedMetric?: string) =>
  apiFetch<{ reply: string }>("/mobility-twin/copilot/ask", {
    method: "POST",
    body: { session_id: sessionId, message, selected_metric: selectedMetric },
  });

export const fetchMobilityCopilotHistory = (sessionId: string) =>
  apiFetch<MobilityCopilotHistory>(`/mobility-twin/copilot/history${q({ session_id: sessionId })}`);

export const clearMobilityCopilot = (sessionId: string) =>
  apiFetch<{ session_id: string; status: string }>(
    `/mobility-twin/copilot${q({ session_id: sessionId })}`,
    {
      method: "DELETE",
    },
  );

// --- Warranty, Quality & Service early warning --------------------------------

export const fetchWarrantyQualityEarlyWarnings = (runId?: string, telematicsRunId?: string) =>
  apiFetch<WarrantyQualityEarlyWarning>(
    `/warranty-quality/early-warnings${q({
      run_id: runId,
      telematics_run_id: telematicsRunId,
    })}`,
  );

export const fetchWarrantyQualityCausalStatus = () =>
  apiFetch<WarrantyQualityCausalStatus>("/warranty-quality/causal-status");

// --- Data explorer ------------------------------------------------------------

export const fetchDataCatalog = () => apiFetch<DataCatalog>("/data/catalog");
export const fetchDataRows = (
  datasetId: string,
  pageSize: number,
  cursor?: string,
  before?: string,
) =>
  apiFetch<DataRows>(
    `/data/datasets/${encodeURIComponent(datasetId)}/rows${q({ page_size: pageSize, cursor, before })}`,
  );
export const fetchDataStatus = (datasetId: string) =>
  apiFetch<DataStatus>(`/data/datasets/${encodeURIComponent(datasetId)}/status`);

// --- Simulations ---------------------------------------------------------------

export const fetchSimulationMeta = () => apiFetch<SimulationMeta>("/simulations/meta");

export const fetchCausalDrivers = (domain: string) =>
  apiFetch<CausalDrivers>(
    `/simulations/causal-drivers${q({
      domain,
    })}`,
  );

export const runAutoSalesSim = (payload: AutoSalesSimIn) =>
  apiFetch<AutoSalesSimOut>("/simulations/auto-sales/run", {
    method: "POST",
    body: payload,
  });

export const approveSimulationRun = (runId: string, reason?: string) =>
  apiFetch<SimulationApprovalOut>(`/simulations/${encodeURIComponent(runId)}/approve`, {
    method: "POST",
    body: { reason },
  });

export const rejectSimulationRun = (runId: string, reason?: string) =>
  apiFetch<SimulationApprovalOut>(`/simulations/${encodeURIComponent(runId)}/reject`, {
    method: "POST",
    body: { reason },
  });

export const fetchSimulationRunDrivers = (runId: string) =>
  apiFetch<SimulationDriversOut>(`/simulations/${encodeURIComponent(runId)}/drivers`);

export const generateSimulationRunSummary = (runId: string) =>
  apiFetch<SimulationSummaryOut>(`/simulations/${encodeURIComponent(runId)}/summary`, {
    method: "POST",
  });

export const runDealerAllocationSim = (payload: DealerAllocationSimIn) =>
  apiFetch<DealerAllocationSimOut>("/simulations/dealer-allocation/run", {
    method: "POST",
    body: payload,
  });

export const runCollectionsSim = (payload: CollectionsSimIn) =>
  apiFetch<CollectionsSimOut>("/simulations/collections/run", {
    method: "POST",
    body: payload,
  });

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

// --- Copilot & executive summary ----------------------------------------------

export const fetchSuggestedPrompts = () => apiFetch<string[]>("/copilot/suggested-prompts");

export const chatCopilot = (message: string) =>
  apiFetch<CopilotResult>("/copilot/chat", {
    method: "POST",
    body: { message },
  });

export const generateExecutiveSummaryApi = (useCase: string) =>
  apiFetch<ExecutiveSummary>("/executive-summary", {
    method: "POST",
    body: { useCase },
  });
