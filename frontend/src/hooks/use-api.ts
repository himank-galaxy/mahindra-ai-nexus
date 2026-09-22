// TanStack Query hooks bridging the UI to the FastAPI backend.
//
// Queries run client-side only and resolve against the API; while loading,
// list hooks return an empty array so the layout never crashes. Mutations
// are fire-and-forget with optional cache invalidation.

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiEnabled } from "@/lib/api/client";
import * as api from "@/lib/api/endpoints";
import type {
  AiAgent,
  AutoSalesSimIn,
  Bucket,
  CausalDrivers,
  CollectionsCase,
  CollectionsChannel,
  CollectionsOffer,
  CollectionsSimIn,
  Credit,
  CreditPricingSimIn,
  CustomerTwin,
  Dealer,
  DealerAllocationSimIn,
  DealerLead,
  ElvEstimate,
  ExecutiveSummary,
  FinanceProduct,
  Kpi,
  LogisticsAction,
  LogisticsDelaySimIn,
  LogisticsRoute,
  MetricTile,
  MobilityGraph,
  MobilityKpi,
  PocItem,
  QaAnswer,
  Recommendation,
  ReviewerRole,
  RmScript,
  RoadmapPlan,
  Signal,
  SimulateOffer,
  SimulationMeta,
  TrustDecision,
  TwinExplain,
  WorkflowRun,
  XrExperience,
} from "@/lib/api/types";

/** Shared query options: client-only, cached forever, no retry storms. */
function apiQueryOptions<T>(key: readonly unknown[], fn: () => Promise<T>, enabled = true) {
  return {
    queryKey: key,
    queryFn: fn,
    enabled: apiEnabled && enabled,
    staleTime: Infinity,
    retry: false,
  };
}

// View types: API rows carry extra fields (`id`, `status`) that some
// consumers ignore, so those are optional in the merged view.
export type RecommendationView = Pick<
  Recommendation,
  "id" | "title" | "impact" | "confidence" | "risk"
> &
  Partial<Pick<Recommendation, "status">>;

export type DealerLeadView = Omit<DealerLead, "id"> & Partial<Pick<DealerLead, "id">>;

export type CollectionsCaseView = Pick<
  CollectionsCase,
  | "customer"
  | "dpd"
  | "out"
  | "roll"
  | "channel"
  | "action"
  | "best_action"
  | "prob"
  | "flag"
  | "case_id"
  | "governance_track"
  | "decision_code"
  | "category"
  | "priority"
  | "priority_reason"
  | "scored_at"
  | "model_version"
> &
  Partial<Pick<CollectionsCase, "id" | "status">>;

export type AiAgentView = Omit<AiAgent, "id"> & Partial<Pick<AiAgent, "id">>;

/** Fire-and-forget mutation with optional cache invalidation. */
function useFireMutation<TArgs extends unknown[], T>(
  fn: (...args: TArgs) => Promise<T>,
  invalidateKey?: readonly unknown[],
) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (args: TArgs) => fn(...args),
    onSuccess: () => {
      if (invalidateKey) void queryClient.invalidateQueries({ queryKey: invalidateKey });
    },
  });
  return (...args: TArgs) => {
    if (apiEnabled) mutation.mutate(args);
  };
}

// --- Overview --------------------------------------------------------------

export function useKpis(): Kpi[] {
  return useQuery(apiQueryOptions(["overview", "kpis"], api.fetchKpis)).data ?? [];
}

export function useRecommendations(): RecommendationView[] {
  return (
    useQuery(apiQueryOptions(["overview", "recommendations"], api.fetchRecommendations)).data ?? []
  );
}

export function useUpdateRecommendation() {
  return useFireMutation(
    (recCode: string, status: "Approved" | "Under Review") =>
      api.updateRecommendation(recCode, status),
    ["overview", "recommendations"],
  );
}

// --- Catalogue & PoC --------------------------------------------------------

export function useSolutionBuckets(): Bucket[] {
  return useQuery(apiQueryOptions(["catalogue", "buckets"], () => api.fetchBuckets())).data ?? [];
}

export function useSolutionTags(): readonly string[] {
  return useQuery(apiQueryOptions(["catalogue", "tags"], api.fetchCatalogueTags)).data ?? [];
}

export function usePocQuery() {
  return useQuery(apiQueryOptions(["poc"], api.fetchPocs));
}

export function useRoadmapPlan(): RoadmapPlan | undefined {
  return useQuery(apiQueryOptions(["poc", "roadmap-plan"], api.fetchRoadmapPlan)).data;
}

// --- Dealers ------------------------------------------------------------------

export function useDealers(): Dealer[] {
  return useQuery(apiQueryOptions(["dealers"], api.fetchDealers)).data ?? [];
}

export function useDealerLeads(dealerCode: string | undefined): DealerLeadView[] {
  return (
    useQuery(
      apiQueryOptions(
        ["dealer-leads", dealerCode ?? ""],
        () => api.fetchDealerLeads(dealerCode as string),
        !!dealerCode,
      ),
    ).data ?? []
  );
}

export function useMessageLead() {
  return useFireMutation((leadId: string) => api.messageLead(leadId));
}

export function useConvertLead() {
  return useFireMutation((leadId: string) => api.convertLead(leadId));
}

export function useScheduleTestDrive() {
  return useFireMutation((leadId: string, slot: string) => api.scheduleTestDrive(leadId, slot));
}

export function useLeadPitch(
  dealerCode: string | undefined,
  leadId: string | undefined,
  enabled: boolean,
) {
  return useQuery(
    apiQueryOptions(
      ["dealer-lead-pitch", dealerCode ?? "", leadId ?? ""],
      () => api.fetchLeadPitch(dealerCode as string, leadId as string),
      !!dealerCode && !!leadId && enabled,
    ),
  ).data;
}

// --- Finance ------------------------------------------------------------------

export function useFinanceProducts(): FinanceProduct[] {
  return useQuery(apiQueryOptions(["finance", "products"], api.fetchFinanceProducts)).data ?? [];
}

/** First seeded customer twin (id + full profile) driving the twin panel. */
export function useCustomerTwin(): { twinId?: string; twin?: CustomerTwin } {
  const summaries = useQuery(apiQueryOptions(["finance", "twins"], api.fetchTwinSummaries)).data;
  const twinId = summaries?.[0]?.id;
  const twin = useQuery(
    apiQueryOptions(
      ["finance", "twin", twinId ?? ""],
      () => api.fetchCustomerTwin(twinId as string),
      !!twinId,
    ),
  ).data;
  return { twinId, twin };
}

export function useTwinExplain(twinId: string | undefined, enabled: boolean) {
  return useQuery(
    apiQueryOptions(
      ["finance", "explain", twinId ?? ""],
      () => api.explainTwin(twinId as string),
      !!twinId && enabled,
    ),
  ).data as TwinExplain | undefined;
}

export function useRmScript(twinId: string | undefined, enabled: boolean) {
  return useQuery(
    apiQueryOptions(
      ["finance", "rm-script", twinId ?? ""],
      () => api.generateRmScript(twinId as string),
      !!twinId && enabled,
    ),
  ).data as RmScript | undefined;
}

export function useSimulateOffer(
  twinId: string | undefined,
  amount: number,
  enabled: boolean,
): SimulateOffer | undefined {
  return useQuery(
    apiQueryOptions(
      ["finance", "simulate-offer", twinId ?? "", amount],
      () => api.simulateOffer(twinId as string, amount),
      !!twinId && enabled,
    ),
  ).data;
}

export function useSubmitTwinApproval() {
  return useFireMutation((twinId: string) => api.submitTwinApproval(twinId), ["finance"]);
}

// --- Collections -----------------------------------------------------------------

export function useCollectionsMetrics(): MetricTile[] {
  return (
    useQuery(apiQueryOptions(["collections", "metrics"], api.fetchCollectionsMetrics)).data ?? []
  );
}

export function useCollectionsAgents(): { name: string; status: string }[] {
  return (
    useQuery(apiQueryOptions(["collections", "agents"], api.fetchCollectionsAgents)).data ?? []
  );
}

/** Cross-cutting like the Trust Ledger's decisions list: a case's
 * governance state can change from an action taken on this same screen,
 * so refetch on every mount rather than trusting a previous visit's
 * cache (see useTrustDecisions below for the identical rationale). */
export function useCollectionsCases(): CollectionsCaseView[] {
  return (
    useQuery({
      ...apiQueryOptions(["collections", "cases"], api.fetchCollectionsCases),
      staleTime: 0,
      refetchOnMount: "always",
    }).data ?? []
  );
}

export function useApproveCase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (caseId: string) => api.approveCase(caseId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["collections", "cases"] }),
  });
}

export function useModifyCase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: {
      caseId: string;
      channel: CollectionsChannel;
      offer: CollectionsOffer;
      reason: string;
    }) => api.modifyCase(variables.caseId, variables.channel, variables.offer, variables.reason),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["collections", "cases"] }),
  });
}

export function useReviewCase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { caseId: string; reviewerRole: ReviewerRole; reason: string }) =>
      api.reviewCase(variables.caseId, variables.reviewerRole, variables.reason),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["collections", "cases"] }),
  });
}

/** Real per-case compliance/approval/outcome state — only fetched once a
 * row's Trust Ledger dialog is open. */
export function useCaseTrustLedger(caseId: string | undefined) {
  return useQuery(
    apiQueryOptions(
      ["collections", "ledger", caseId ?? ""],
      () => api.fetchCaseTrustLedger(caseId as string),
      !!caseId,
    ),
  );
}

// --- Logistics ----------------------------------------------------------------------

/** Cross-cutting like the Trust Ledger's decisions list: a route's own
 * status/priority can change from an action taken on this same screen
 * (Approve/Modify/Review/Auto-Heal on one of its shipments), so refetch
 * on every mount rather than trusting a previous visit's cache (see
 * useCollectionsCases above for the identical rationale). */
export function useLogisticsRoutes(): LogisticsRoute[] {
  return (
    useQuery({
      ...apiQueryOptions(["logistics", "routes"], api.fetchRoutes),
      staleTime: 0,
      refetchOnMount: "always",
    }).data ?? []
  );
}

export function useWarehouseSignals(): Signal[] {
  return useQuery(apiQueryOptions(["logistics", "signals"], api.fetchWarehouseSignals)).data ?? [];
}

export function usePredictDelay() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (routeId: string) => api.predictDelay(routeId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["logistics", "routes"] }),
  });
}

export function useReroute() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (routeId: string) => api.rerouteRoute(routeId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["logistics", "routes"] }),
  });
}

export function useAutoHeal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (routeId: string) => api.autoHealRoute(routeId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["logistics", "routes"] });
      void queryClient.invalidateQueries({ queryKey: ["logistics", "shipments"] });
    },
  });
}

export function useRouteSlaReport(routeId: string | undefined, enabled: boolean) {
  return useQuery(
    apiQueryOptions(
      ["logistics", "sla-report", routeId ?? ""],
      () => api.fetchRouteSlaReport(routeId as string),
      !!routeId && enabled,
    ),
  );
}

/** Real per-shipment governance state can change from actions taken on
 * this same drill-down, so always refetch on mount rather than trusting
 * a previous visit's cache. */
export function useRouteShipments(routeId: string | undefined, enabled: boolean) {
  return useQuery({
    ...apiQueryOptions(
      ["logistics", "shipments", routeId ?? ""],
      () => api.fetchRouteShipments(routeId as string),
      !!routeId && enabled,
    ),
    staleTime: 0,
    refetchOnMount: "always",
  });
}

function invalidateShipmentQueries(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["logistics", "shipments"] });
  void queryClient.invalidateQueries({ queryKey: ["logistics", "routes"] });
}

export function useApproveShipment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (shipmentId: string) => api.approveShipment(shipmentId),
    onSuccess: () => invalidateShipmentQueries(queryClient),
  });
}

export function useModifyShipment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: {
      shipmentId: string;
      action: LogisticsAction;
      routeId: string | null;
      reason: string;
    }) =>
      api.modifyShipment(
        variables.shipmentId,
        variables.action,
        variables.routeId,
        variables.reason,
      ),
    onSuccess: () => invalidateShipmentQueries(queryClient),
  });
}

export function useReviewShipment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { shipmentId: string; reviewerRole: ReviewerRole; reason: string }) =>
      api.reviewShipment(variables.shipmentId, variables.reviewerRole, variables.reason),
    onSuccess: () => invalidateShipmentQueries(queryClient),
  });
}

/** Real per-shipment compliance/approval/outcome state — only fetched
 * once a row's Trust Ledger dialog is open. */
export function useShipmentLedger(shipmentId: string | undefined) {
  return useQuery(
    apiQueryOptions(
      ["logistics", "ledger", shipmentId ?? ""],
      () => api.fetchShipmentLedger(shipmentId as string),
      !!shipmentId,
    ),
  );
}

// --- Circularity ----------------------------------------------------------------------

export function useCredits(): Credit[] {
  return useQuery(apiQueryOptions(["circularity", "credits"], api.fetchCredits)).data ?? [];
}

export function useRvsfMetrics(): MetricTile[] | undefined {
  return useQuery(apiQueryOptions(["circularity", "rvsf"], api.fetchRvsfMetrics)).data;
}

export function useElvEstimate(payload: {
  vehicleType: string;
  age: number;
  condition: number;
  docs: number;
}): ElvEstimate | undefined {
  return useQuery({
    ...apiQueryOptions(
      ["circularity", "elv", payload.vehicleType, payload.age, payload.condition, payload.docs],
      () => api.estimateElv(payload),
    ),
  }).data;
}

export function useDmrvPrompts(): string[] | undefined {
  return useQuery(apiQueryOptions(["circularity", "dmrv-prompts"], api.fetchDmrvPrompts)).data;
}

export function useRepriceCredit() {
  return useFireMutation(
    (creditCode: string) => api.repriceCredit(creditCode),
    ["circularity", "credits"],
  );
}

export function useMatchCreditBuyer() {
  return useFireMutation(
    (creditCode: string) => api.matchCreditBuyer(creditCode),
    ["circularity", "credits"],
  );
}

// --- Trust ledger ----------------------------------------------------------------------

/** Unlike most screens, this list changes from actions taken on a
 * completely different screen (approving/rejecting/escalating a run in
 * Simulation Center) — the default app-wide `staleTime: Infinity` would
 * keep showing stale data until a hard refresh, so this query always
 * refetches on mount instead of trusting a previous visit's cache. */
export function useTrustDecisions(): TrustDecision[] {
  return (
    useQuery({
      ...apiQueryOptions(["trust", "decisions"], api.fetchTrustDecisions),
      staleTime: 0,
      refetchOnMount: "always",
    }).data ?? []
  );
}

/** Real per-decision lineage — only fetched once a row's lineage modal is open. */
export function useTrustDecisionLineage(code: string | undefined, enabled: boolean) {
  return useQuery(
    apiQueryOptions(
      ["trust", "lineage", code ?? ""],
      () => api.fetchTrustDecisionLineage(code as string),
      !!code && enabled,
    ),
  );
}

/** Real per-decision compliance checks — never a global aggregate across
 * every decision. Only fetched once a row is selected. */
export function useTrustDecisionCompliance(code: string | undefined, enabled: boolean) {
  return useQuery(
    apiQueryOptions(
      ["trust", "compliance", code ?? ""],
      () => api.fetchTrustDecisionCompliance(code as string),
      !!code && enabled,
    ),
  );
}

/** Why this recommendation was made — grounded in the decision's own
 * persisted drivers/evidence, only fetched once its modal is open. */
export function useTrustDecisionExplanation(code: string | undefined, enabled: boolean) {
  return useQuery(
    apiQueryOptions(
      ["trust", "explanation", code ?? ""],
      () => api.fetchTrustDecisionExplanation(code as string),
      !!code && enabled,
    ),
  );
}

/** Real, chronological, append-only decision history — only fetched
 * once its modal is open. */
export function useTrustDecisionEvents(code: string | undefined, enabled: boolean) {
  return useQuery(
    apiQueryOptions(
      ["trust", "events", code ?? ""],
      () => api.fetchTrustDecisionEvents(code as string),
      !!code && enabled,
    ),
  );
}

/** Real observed/expected outcome, or an honest pending state — only
 * fetched once its modal is open. */
export function useTrustDecisionOutcome(code: string | undefined, enabled: boolean) {
  return useQuery(
    apiQueryOptions(
      ["trust", "outcome", code ?? ""],
      () => api.fetchTrustDecisionOutcome(code as string),
      !!code && enabled,
    ),
  );
}

// Approve/Reject/Escalate are real mutations (not fire-and-forget): the
// caller must know whether the backend actually accepted the decision —
// e.g. an already-decided run correctly 409s — before updating any
// on-screen approval state, never before.
export function useApproveDecision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (code: string) => api.approveDecision(code),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["trust", "decisions"] }),
  });
}

export function useRejectDecision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { code: string; reason: string }) =>
      api.rejectDecision(variables.code, variables.reason),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["trust", "decisions"] }),
  });
}

export function useEscalateDecision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { code: string; reviewerRole: ReviewerRole; reason: string }) =>
      api.escalateDecision(variables.code, variables.reviewerRole, variables.reason),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["trust", "decisions"] }),
  });
}

// --- Agents & XR ----------------------------------------------------------------------

export function useAgents(): AiAgentView[] {
  return useQuery(apiQueryOptions(["agents"], api.fetchAgents)).data ?? [];
}

/** Runs the staged workflow on the backend; resolves null on failure. */
export function useWorkflowRun(): () => Promise<WorkflowRun | null> {
  const mutation = useMutation({ mutationFn: api.runWorkflow });
  return async () => {
    if (!apiEnabled) return null;
    try {
      return await mutation.mutateAsync();
    } catch {
      return null;
    }
  };
}

export function useXrExperiences(): XrExperience[] | undefined {
  return useQuery(apiQueryOptions(["xr", "experiences"], api.fetchXrExperiences)).data;
}

// --- Mobility twin ----------------------------------------------------------------------
//
// The backend recomputes the causal graph on its own ~60-minute background
// cycle (see docs/Implementation_plan_mobility_causal.md §4) — there's no
// per-request computation and no signature/version to key off like
// Warranty & Quality, so a plain polling interval is enough to pick up a
// new result promptly without hammering the endpoint.
const MOBILITY_REFETCH_INTERVAL_MS = 5 * 60 * 1000;

export function useMobilityKpis(): MobilityKpi[] | undefined {
  return useQuery({
    ...apiQueryOptions(["mobility", "kpis"], api.fetchMobilityKpis),
    staleTime: 0,
    refetchInterval: MOBILITY_REFETCH_INTERVAL_MS,
  }).data;
}

export function useMobilityGraph(): MobilityGraph | undefined {
  return useQuery({
    ...apiQueryOptions(["mobility", "graph"], api.fetchMobilityGraph),
    staleTime: 0,
    refetchInterval: MOBILITY_REFETCH_INTERVAL_MS,
  }).data;
}

/** Node detail for whichever node is currently selected; disabled (no
 * fetch) while nothing is selected. */
export function useMobilityNodeDetail(metricKey: string | null) {
  return useQuery({
    ...apiQueryOptions(
      ["mobility", "node", metricKey ?? ""],
      () => api.fetchMobilityNodeDetail(metricKey as string),
      metricKey !== null,
    ),
  });
}

export function useMobilityCopilotHistory(sessionId: string) {
  return useQuery(
    apiQueryOptions(["mobility", "copilot", "history", sessionId], () =>
      api.fetchMobilityCopilotHistory(sessionId),
    ),
  );
}

export function useMobilityCopilotAsk(sessionId: string) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (variables: { message: string; selectedMetric?: string }) =>
      api.askMobilityCopilot(sessionId, variables.message, variables.selectedMetric),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mobility", "copilot", "history", sessionId] });
    },
  });
  return mutation;
}

export function useMobilityCopilotClear(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.clearMobilityCopilot(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mobility", "copilot", "history", sessionId] });
    },
  });
}

// --- Warranty, Quality & Service early warning ------------------------------------------

/**
 * Full query result is returned intentionally so the dedicated screen can
 * render loading, error, empty, and successful API states independently.
 */
export function useWarrantyQualityCausalStatus() {
  return useQuery({
    ...apiQueryOptions(["warranty-quality", "causal-status"], api.fetchWarrantyQualityCausalStatus),
    staleTime: 0,
    refetchInterval: 10_000,
  });
}

/**
 * The early-warning payload carries the whole causal graph and every evidence
 * block, so it is deliberately NOT polled on a timer. Instead, `snapshotVersion`
 * (a composite of the warning evaluation run id/signature and the manufacturing
 * and telematics causal run ids, computed by the caller from the lightweight
 * causal-status query) IS the query key. A version the client has not seen
 * before is a cache miss, so React Query fetches it automatically the moment
 * the caller passes a new value in — no manual invalidation required. The
 * request itself always asks the API for the latest snapshot; the version
 * string only controls *when* that request re-runs.
 *
 * `placeholderData: keepPreviousData` keeps the previous snapshot on screen
 * while the new version loads, so a version change refreshes the graph in
 * place instead of flashing a loading state.
 */
export function useWarrantyQualityEarlyWarnings(snapshotVersion?: string) {
  return useQuery({
    ...apiQueryOptions(["warranty-quality", "early-warnings", snapshotVersion ?? "initial"], () =>
      api.fetchWarrantyQualityEarlyWarnings(),
    ),
    placeholderData: keepPreviousData,
  });
}

// --- Q&A (mobility + dMRV): ask with a local fallback answer -------------------------------

/**
 * Answers a suggested question via the backend; falls back to the bundled
 * answer when the request fails.
 */
export function useAskAnswer(apiCall: (question: string) => Promise<QaAnswer>) {
  const mutation = useMutation({ mutationFn: (question: string) => apiCall(question) });
  return (question: string, fallback: string, onAnswer: (answer: string) => void) => {
    if (!apiEnabled) {
      onAnswer(fallback);
      return;
    }
    mutation.mutate(question, {
      onSuccess: (data) => onAnswer(data.answer),
      onError: () => onAnswer(fallback),
    });
  };
}

// --- Simulations -----------------------------------------------------------------------------

export function useSimulationMeta(): SimulationMeta | undefined {
  return useQuery(apiQueryOptions(["simulations", "meta"], api.fetchSimulationMeta)).data;
}

export function useCausalDrivers(domain: string, enabled: boolean): CausalDrivers | undefined {
  return useQuery(
    apiQueryOptions(
      ["simulations", "drivers", domain],
      () => api.fetchCausalDrivers(domain),
      enabled,
    ),
  ).data;
}

/**
 * Auto Sales is a mutation, not a query: the backend is the source of
 * truth and persists a run (with a `run_id`) on every click, so nothing
 * should fire automatically while the user is still dragging sliders. See
 * docs/simulation_centre_implementation.md §9.
 */
export function useRunAutoSalesSim() {
  return useMutation({ mutationFn: (inputs: AutoSalesSimIn) => api.runAutoSalesSim(inputs) });
}

export function useApproveSimulationRun() {
  return useMutation({
    mutationFn: (variables: { runId: string; reason?: string }) =>
      api.approveSimulationRun(variables.runId, variables.reason),
  });
}

export function useRejectSimulationRun() {
  return useMutation({
    mutationFn: (variables: { runId: string; reason?: string }) =>
      api.rejectSimulationRun(variables.runId, variables.reason),
  });
}

/** Explain Drivers for a specific persisted run — real feature importance
 * plus causal evidence, kept separate (see docs/simulation_centre_implementation.md §11). */
export function useSimulationRunDrivers(runId: string | undefined, enabled: boolean) {
  return useQuery(
    apiQueryOptions(
      ["simulations", "drivers", runId ?? ""],
      () => api.fetchSimulationRunDrivers(runId as string),
      !!runId && enabled,
    ),
  );
}

/** Executive summary grounded in one run's own persisted evidence. */
export function useGenerateSimulationRunSummary(runId: string | undefined, enabled: boolean) {
  return useQuery(
    apiQueryOptions(
      ["simulations", "summary", runId ?? ""],
      () => api.generateSimulationRunSummary(runId as string),
      !!runId && enabled,
    ),
  );
}

/** Mutation, not a query — same rationale as Auto Sales (§9): the backend
 * persists a run with a `run_id` on every click, so nothing should fire
 * automatically while the user is still dragging sliders. */
export function useRunDealerAllocationSim() {
  return useMutation({
    mutationFn: (inputs: DealerAllocationSimIn) => api.runDealerAllocationSim(inputs),
  });
}

/** Mutation, not a query — same rationale as Auto Sales/Dealer Allocation
 * (§9): the backend persists a run with a `run_id` on every click. */
export function useRunCollectionsSim() {
  return useMutation({ mutationFn: (inputs: CollectionsSimIn) => api.runCollectionsSim(inputs) });
}

/** Mutation, not a query — same rationale as Auto Sales/Dealer Allocation/
 * Collections (§9): the backend persists a run with a `run_id` on every click. */
export function useRunLogisticsDelaySim() {
  return useMutation({
    mutationFn: (inputs: LogisticsDelaySimIn) => api.runLogisticsDelaySim(inputs),
  });
}

/** Mutation, not a query — same rationale as Auto Sales/Dealer Allocation/
 * Collections/Logistics Delay (§9): the backend persists a run with a
 * `run_id` on every click. */
export function useRunCreditPricingSim() {
  return useMutation({
    mutationFn: (inputs: CreditPricingSimIn) => api.runCreditPricingSim(inputs),
  });
}

// --- Copilot & executive summary ---------------------------------------------------------------

export function useSuggestedPrompts(): string[] {
  return useQuery(apiQueryOptions(["copilot", "prompts"], api.fetchSuggestedPrompts)).data ?? [];
}

export function useExecutiveSummary(useCase: string, open: boolean): ExecutiveSummary | undefined {
  return useQuery(
    apiQueryOptions(
      ["executive-summary", useCase],
      () => api.generateExecutiveSummaryApi(useCase),
      open && useCase.length > 0,
    ),
  ).data;
}

// --- PoC roadmap mutations (used by the app context) -----------------------------------------------

export function usePocMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["poc"] });
  const add = useMutation({
    mutationFn: (item: { name: string; bucket: string }) => api.addPoc(item.name, item.bucket),
    onMutate: async (item) => {
      await queryClient.cancelQueries({ queryKey: ["poc"] });
      const previous = queryClient.getQueryData<PocItem[]>(["poc"]);
      queryClient.setQueryData<PocItem[]>(["poc"], (old) =>
        old && !old.find((p) => p.name === item.name)
          ? [...old, { id: "", addedAt: Date.now(), ...item }]
          : old,
      );
      return { previous };
    },
    onError: (_err, _item, context) => {
      if (context?.previous) queryClient.setQueryData(["poc"], context.previous);
    },
    onSettled: invalidate,
  });
  const remove = useMutation({
    mutationFn: (name: string) => api.removePoc(name),
    onMutate: async (name) => {
      await queryClient.cancelQueries({ queryKey: ["poc"] });
      const previous = queryClient.getQueryData<PocItem[]>(["poc"]);
      queryClient.setQueryData<PocItem[]>(["poc"], (old) =>
        old ? old.filter((p) => p.name !== name) : old,
      );
      return { previous };
    },
    onError: (_err, _name, context) => {
      if (context?.previous) queryClient.setQueryData(["poc"], context.previous);
    },
    onSettled: invalidate,
  });
  return {
    addPoc: (item: { name: string; bucket: string }) => {
      if (apiEnabled) add.mutate(item);
    },
    removePoc: (name: string) => {
      if (apiEnabled) remove.mutate(name);
    },
  };
}
