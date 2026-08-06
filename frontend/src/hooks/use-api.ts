// TanStack Query hooks bridging the UI to the FastAPI backend.
//
// Queries run client-side only and resolve against the API; while loading,
// list hooks return an empty array so the layout never crashes. Mutations
// are fire-and-forget with optional cache invalidation.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiEnabled } from "@/lib/api/client";
import * as api from "@/lib/api/endpoints";
import type {
  AiAgent,
  AutoSalesSimIn,
  AutoSalesSimOut,
  Bucket,
  CausalDrivers,
  CollectionsCase,
  CollectionsSimIn,
  CollectionsSimOut,
  ComplianceRule,
  Credit,
  CreditPricingSimIn,
  CreditPricingSimOut,
  CustomerTwin,
  Dealer,
  DealerAllocationSimIn,
  DealerAllocationSimOut,
  DealerLead,
  ElvEstimate,
  ExecutiveSummary,
  FinanceProduct,
  Kpi,
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
  "customer" | "dpd" | "out" | "roll" | "channel" | "action" | "prob" | "flag"
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

export function useCollectionsMetrics(): MetricTile[] | undefined {
  return useQuery(apiQueryOptions(["collections", "metrics"], api.fetchCollectionsMetrics)).data;
}

export function useCollectionsAgents(): { name: string; status: string }[] | undefined {
  return useQuery(apiQueryOptions(["collections", "agents"], api.fetchCollectionsAgents)).data;
}

export function useCollectionsCases(): CollectionsCaseView[] {
  return useQuery(apiQueryOptions(["collections", "cases"], api.fetchCollectionsCases)).data ?? [];
}

export function useApproveCase() {
  return useFireMutation((caseId: string) => api.approveCase(caseId), ["collections", "cases"]);
}

export function useModifyCase() {
  return useFireMutation(
    (caseId: string, action: string) => api.modifyCase(caseId, action),
    ["collections", "cases"],
  );
}

export function useReviewCase() {
  return useFireMutation((caseId: string) => api.reviewCase(caseId), ["collections", "cases"]);
}

export function useCaseLedger(caseId: string | undefined): string[] | undefined {
  return useQuery(
    apiQueryOptions(
      ["collections", "ledger", caseId ?? ""],
      () => api.fetchCaseLedger(caseId as string),
      !!caseId,
    ),
  ).data;
}

// --- Logistics ----------------------------------------------------------------------

/** Route card view: `id`/`rerouted` are optional until the API responds. */
export type RouteView = Pick<LogisticsRoute, "name" | "slaRisk" | "delayProb" | "cost" | "action"> &
  Partial<Pick<LogisticsRoute, "id" | "rerouted">>;

export function useLogisticsRoutes(): RouteView[] {
  return useQuery(apiQueryOptions(["logistics", "routes"], api.fetchRoutes)).data ?? [];
}

export function useWarehouseSignals(): MetricTile[] | undefined {
  return useQuery(apiQueryOptions(["logistics", "signals"], api.fetchWarehouseSignals)).data;
}

export function usePredictDelay() {
  return useFireMutation((routeId: string) => api.predictDelay(routeId), ["logistics", "routes"]);
}

export function useReroute() {
  return useFireMutation((routeId: string) => api.rerouteRoute(routeId), ["logistics", "routes"]);
}

export function useAutoHeal() {
  return useFireMutation((routeId: string) => api.autoHealRoute(routeId), ["logistics", "routes"]);
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

export function useTrustDecisions(): TrustDecision[] {
  return useQuery(apiQueryOptions(["trust", "decisions"], api.fetchTrustDecisions)).data ?? [];
}

export function useComplianceRules(): ComplianceRule[] | undefined {
  return useQuery(apiQueryOptions(["trust", "rules"], api.fetchComplianceRules)).data;
}

export function useApproveDecision() {
  return useFireMutation((code: string) => api.approveDecision(code), ["trust", "decisions"]);
}

export function useRejectDecision() {
  return useFireMutation(
    (code: string, reason: string) => api.rejectDecision(code, reason),
    ["trust", "decisions"],
  );
}

export function useEscalateDecision() {
  return useFireMutation((code: string) => api.escalateDecision(code), ["trust", "decisions"]);
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

export function useMobilityKpis(): MobilityKpi[] | undefined {
  return useQuery(apiQueryOptions(["mobility", "kpis"], api.fetchMobilityKpis)).data;
}

export function useMobilityGraph(): MobilityGraph | undefined {
  return useQuery(apiQueryOptions(["mobility", "graph"], api.fetchMobilityGraph)).data;
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

export function useAutoSalesSim(inputs: AutoSalesSimIn): AutoSalesSimOut | undefined {
  return useQuery({
    ...apiQueryOptions(["simulations", "auto-sales", inputs], () => api.runAutoSalesSim(inputs)),
  }).data;
}

export function useDealerAllocationSim(
  inputs: DealerAllocationSimIn,
): DealerAllocationSimOut | undefined {
  return useQuery({
    ...apiQueryOptions(["simulations", "dealer-allocation", inputs], () =>
      api.runDealerAllocationSim(inputs),
    ),
  }).data;
}

export function useCollectionsSim(inputs: CollectionsSimIn): CollectionsSimOut | undefined {
  return useQuery({
    ...apiQueryOptions(["simulations", "collections", inputs], () => api.runCollectionsSim(inputs)),
  }).data;
}

export function useLogisticsDelaySim(
  inputs: LogisticsDelaySimIn,
): LogisticsDelaySimOut | undefined {
  return useQuery({
    ...apiQueryOptions(["simulations", "logistics-delay", inputs], () =>
      api.runLogisticsDelaySim(inputs),
    ),
  }).data;
}

export function useCreditPricingSim(inputs: CreditPricingSimIn): CreditPricingSimOut | undefined {
  return useQuery({
    ...apiQueryOptions(["simulations", "credit-pricing", inputs], () =>
      api.runCreditPricingSim(inputs),
    ),
  }).data;
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
