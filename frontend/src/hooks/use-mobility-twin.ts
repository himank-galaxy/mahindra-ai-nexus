import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiEnabled, apiFetch, ApiError } from "@/lib/api/client";
import type { CausalNode, MobilityCopilotHistory, MobilityNodeDetail } from "@/lib/api/types";

export type Tone = "success" | "danger" | "default";
export type TwinNode = CausalNode & {
  trend_pct: number | null;
  trend_tone: Tone;
  unit: string;
  aggregation: string;
  connection_count: number;
  recent_values?: number[];
};
export type TwinEdge = {
  source: string;
  target: string;
  score: number;
  lag_minutes: number;
  p_value: number;
  q_value: number;
};
export type TwinGraph = {
  nodes: TwinNode[];
  edge_details: TwinEdge[];
  width: number;
  height: number;
  node_width: number;
  node_height: number;
  kpis: { metric_key: string; label: string; value: string; trend: string; trend_tone: Tone }[];
  metadata: {
    snapshot_id: string;
    computed_at: string;
    data_start: string;
    data_end: string;
    source_latest_at: string | null;
    checked_at: string | null;
    next_check_at: string | null;
    observation_count: number;
    effective_observation_count: number;
    segment_count: number;
    sample_stride_hours: number;
    refresh_check_minutes: number;
    max_lag_hours: number;
    significance_threshold: number;
    status: "ready" | "stale";
    refreshing: boolean;
    last_error: string | null;
    warnings: string[];
    excluded_metrics: Record<string, string>;
    data_origins: string[];
    connected_measure_count: number;
    hidden_isolated_measure_count: number;
  };
};
export type TwinDetail = Omit<MobilityNodeDetail, "trend_pct" | "relationships" | "top_drivers"> & {
  snapshot_id: string;
  trend_pct: number | null;
  trend_tone: Tone;
  aggregation: string;
  unit: string;
  relationships: (MobilityNodeDetail["relationships"][number] & { q_value: number })[];
  top_drivers: (MobilityNodeDetail["relationships"][number] & { q_value: number })[];
};
export type TwinViewContext = {
  domain: string;
  focus: boolean;
  visible_metrics: string[];
};

const graphKey = ["mobility-twin", "graph"] as const;
const root = "/mobility-twin";

export function useMobilityGraph() {
  return useQuery({
    queryKey: graphKey,
    queryFn: () => apiFetch<TwinGraph>(`${root}/graph`),
    enabled: apiEnabled,
    staleTime: 0,
    refetchInterval: 5 * 60 * 1000,
    retry: false,
  });
}

export function useMobilityNodeDetail(metric: string | null, snapshotId?: string) {
  const client = useQueryClient();
  return useQuery({
    queryKey: ["mobility-twin", "node", snapshotId, metric],
    enabled: apiEnabled && !!metric && !!snapshotId,
    staleTime: Infinity,
    retry: false,
    queryFn: async () => {
      try {
        return await apiFetch<TwinDetail>(
          `${root}/nodes/${encodeURIComponent(metric!)}?snapshot_id=${encodeURIComponent(snapshotId!)}`,
        );
      } catch (error) {
        if (error instanceof ApiError && error.status === 409)
          void client.invalidateQueries({ queryKey: graphKey });
        throw error;
      }
    },
  });
}

export function useMobilityCopilotHistory(sessionId: string) {
  return useQuery({
    queryKey: ["mobility-twin", "history", sessionId],
    queryFn: () =>
      apiFetch<MobilityCopilotHistory>(
        `${root}/copilot/history?session_id=${encodeURIComponent(sessionId)}`,
      ),
    enabled: apiEnabled,
    staleTime: 0,
    retry: false,
  });
}

export function useMobilityCopilotExplanation(input: {
  snapshotId?: string;
  selectedMetric?: string;
  viewContext: TwinViewContext;
}) {
  return useQuery({
    queryKey: [
      "mobility-twin",
      "explanation",
      input.snapshotId,
      input.selectedMetric,
      input.viewContext.domain,
      input.viewContext.focus,
      input.viewContext.visible_metrics.join("|"),
    ],
    queryFn: () =>
      apiFetch<{ reply: string }>(`${root}/copilot/explain`, {
        method: "POST",
        body: {
          selected_metric: input.selectedMetric,
          snapshot_id: input.snapshotId,
          view_context: input.viewContext,
        },
      }),
    enabled: apiEnabled && !!input.snapshotId && input.viewContext.visible_metrics.length > 0,
    staleTime: Infinity,
    retry: false,
  });
}

export function useMobilityCopilotAsk(sessionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      message: string;
      selectedMetric?: string;
      snapshotId: string;
      viewContext?: TwinViewContext;
    }) =>
      apiFetch<{ reply: string }>(`${root}/copilot/ask`, {
        method: "POST",
        body: {
          session_id: sessionId,
          message: input.message,
          selected_metric: input.selectedMetric,
          snapshot_id: input.snapshotId,
          view_context: input.viewContext,
        },
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["mobility-twin", "history", sessionId] });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409)
        void client.invalidateQueries({ queryKey: graphKey });
    },
  });
}

export function useMobilityCopilotClear(sessionId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch(`${root}/copilot?session_id=${encodeURIComponent(sessionId)}`, { method: "DELETE" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["mobility-twin", "history", sessionId] });
    },
  });
}
