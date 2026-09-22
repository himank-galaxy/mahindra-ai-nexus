import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState, useMemo } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { Panel, SectionTitle } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useMobilityCopilotAsk,
  useMobilityCopilotClear,
  useMobilityCopilotExplanation,
  useMobilityCopilotHistory,
  useMobilityGraph,
  useMobilityNodeDetail,
} from "@/hooks/use-mobility-twin";
import type { Tone } from "@/hooks/use-mobility-twin";

import {
  ReactFlow,
  Background,
  MiniMap,
  Controls,
  ReactFlowProvider,
  useReactFlow,
  Handle,
  Position,
  MarkerType,
} from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import ELK from "elkjs/lib/elk.bundled.js";
import "@xyflow/react/dist/style.css";

export const Route = createFileRoute("/mobility-twin")({
  ssr: false,
  head: () => ({ meta: [{ title: "Auto Mobility Twin · Mahindra AI Command Center" }] }),
  component: () => (
    <ReactFlowProvider>
      <MobilityTwin />
    </ReactFlowProvider>
  ),
});

const SUGGESTED_QUESTIONS = [
  "What relationships have you found in the graph right now?",
  "What changed since the last refresh?",
  "What are the strongest drivers for the selected node?",
  "What should we investigate for this metric?",
];
const toneClass: Record<Tone, string> = {
  success: "text-emerald-300",
  danger: "text-red-300",
  default: "text-muted-foreground",
};
const sparkToneClass: Record<Tone, string> = {
  success: "text-emerald-400",
  danger: "text-red-400",
  default: "text-sky-400",
};
function trendDirection(trend: string): "up" | "down" | null {
  const trimmed = trend.trim();
  if (trimmed.startsWith("+")) return "up";
  if (trimmed.startsWith("-")) return "down";
  return null;
}

function sessionId() {
  const create = () =>
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `mobility-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  if (typeof window === "undefined") return "server";
  try {
    const key = "mobility-copilot-session-id";
    const id = window.localStorage.getItem(key) || create();
    window.localStorage.setItem(key, id);
    return id;
  } catch {
    return create();
  }
}

function dateText(value?: string | null) {
  return value
    ? new Date(value).toLocaleString("en-GB", { timeZone: "UTC" }) + " UTC"
    : "Unavailable";
}

function formatLag(minutes: number) {
  const [value, unit] =
    minutes % 1440 === 0
      ? [minutes / 1440, "day"]
      : minutes % 60 === 0
        ? [minutes / 60, "hour"]
        : [minutes, "minute"];
  return `${value} ${unit}${value === 1 ? "" : "s"}`;
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "The request could not be completed.";
}

function CopilotText({ content }: { content: string }) {
  return (
    <div className="space-y-1 text-xs leading-relaxed text-slate-300">
      {content.split("\n").map((rawLine, index) => {
        const line = rawLine.trim();
        if (!line) return <div className="h-2" key={index} />;
        if (line.startsWith("### "))
          return (
            <h3 className="pt-2 text-sm font-semibold text-white" key={index}>
              {line.slice(4)}
            </h3>
          );
        const bold = line.match(/^\*\*(.+)\*\*$/);
        if (bold)
          return (
            <p className="pt-1 font-semibold text-sky-200" key={index}>
              {bold[1]}
            </p>
          );
        const listed = line.match(/^(\d+\.|[-•])\s+(.+)$/);
        if (listed)
          return (
            <p className="pl-3" key={index}>
              <span className="mr-1 text-sky-400">{listed[1]}</span>
              {listed[2]}
            </p>
          );
        return <p key={index}>{line}</p>;
      })}
    </div>
  );
}

const colors = { root: "#f87171", intermediate: "#10b981", target: "#00baff", outcome: "#fbbf24" };
function domain(key: string) {
  if (/finance/.test(key)) return "Finance";
  if (/warranty/.test(key)) return "Warranty";
  if (/service|repair/.test(key)) return "Service";
  if (/deliver|allocat/.test(key)) return "Delivery";
  return /lead|followup|booking|test_drive|customer_response|cancellation/.test(key)
    ? "Sales"
    : "Other";
}
function Sparkline({ values = [], tone = "default" }: { values?: number[]; tone?: Tone }) {
  if (values.length < 2) return null;
  const low = Math.min(...values),
    span = Math.max(...values) - low || 1;
  return (
    <svg
      viewBox="0 0 100 24"
      role="img"
      aria-label="Recent sampled trend"
      className={"mt-2 h-6 w-24 " + sparkToneClass[tone]}
    >
      <polyline
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        points={values
          .map((v, i) => `${(i * 100) / (values.length - 1)},${22 - ((v - low) * 20) / span}`)
          .join(" ")}
      />
    </svg>
  );
}
function MetricNode({ data }: NodeProps) {
  return (
    <div
      style={{
        borderColor: String(data.color),
        boxShadow: data.active ? `0 0 20px ${data.color}55` : undefined,
      }}
      className="w-[220px] rounded-lg border bg-[#071721] p-3 text-white"
    >
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <div className="text-xs font-semibold">{String(data.label)}</div>
      <div className="mt-1 text-[10px] text-slate-400">
        {String(data.domain)} · {String(data.role)}
      </div>
      <div className="mt-2 text-lg font-semibold">{String(data.metric)}</div>
      <div className="text-[10px] text-slate-300">{String(data.trend)}</div>
      <Sparkline values={data.recent_values as number[] | undefined} />
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  );
}
const nodeTypes = { metric: MetricNode };
const elk = new ELK();
function MobilityTwin() {
  const graphQuery = useMobilityGraph(),
    graph = graphQuery.data,
    metadata = graph?.metadata;
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [filter, setFilter] = useState("All Measures"),
    [search, setSearch] = useState(""),
    [focus, setFocus] = useState(false),
    [assistant, setAssistant] = useState(true);
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});
  const flow = useReactFlow();
  const [session] = useState(sessionId),
    [input, setInput] = useState("");
  const historyQuery = useMobilityCopilotHistory(session),
    askMutation = useMobilityCopilotAsk(session),
    clearMutation = useMobilityCopilotClear(session);
  const endRef = useRef<HTMLDivElement | null>(null);
  const resolvedSelectedKey = graph?.nodes.some((node) => node.metric_key === selectedKey)
    ? selectedKey
    : null;
  const subset = useMemo(() => {
    const nodes = graph?.nodes ?? [],
      edges = graph?.edge_details ?? [];
    const chain = new Set<string>(resolvedSelectedKey ? [resolvedSelectedKey] : []);
    if (focus && resolvedSelectedKey) {
      for (const direction of ["up", "down"]) {
        const seen = new Set([resolvedSelectedKey]),
          queue = [resolvedSelectedKey];
        while (queue.length) {
          const key = queue.shift();
          for (const e of edges) {
            const next =
              direction === "up"
                ? e.target === key
                  ? e.source
                  : null
                : e.source === key
                  ? e.target
                  : null;
            if (next && !seen.has(next)) {
              seen.add(next);
              chain.add(next);
              queue.push(next);
            }
          }
        }
      }
    }
    const eligible = new Set(
      nodes
        .filter(
          (n) =>
            (filter === "All Measures" || domain(n.metric_key) === filter) &&
            (!focus || chain.has(n.metric_key)),
        )
        .map((n) => n.metric_key),
    );
    const visibleEdges = edges.filter((e) => eligible.has(e.source) && eligible.has(e.target));
    const connected = new Set(visibleEdges.flatMap((e) => [e.source, e.target]));
    return { nodes: nodes.filter((n) => connected.has(n.metric_key)), edges: visibleEdges };
  }, [graph, filter, focus, resolvedSelectedKey]);
  const signature =
    subset.nodes.map((n) => n.metric_key).join("|") +
    "::" +
    subset.edges.map((e) => e.source + ">" + e.target).join("|");
  const viewContext = {
    domain: filter,
    focus,
    visible_metrics: subset.nodes.map((node) => node.metric_key),
  };
  const visibleSelectedKey = subset.nodes.some((node) => node.metric_key === resolvedSelectedKey)
    ? (resolvedSelectedKey ?? undefined)
    : undefined;
  const activeNode = subset.nodes.find((node) => node.metric_key === visibleSelectedKey);
  const detailQuery = useMobilityNodeDetail(activeNode?.metric_key ?? null, metadata?.snapshot_id);
  const detail =
    detailQuery.data?.snapshot_id === metadata?.snapshot_id ? detailQuery.data : undefined;
  const explanationQuery = useMobilityCopilotExplanation({
    snapshotId: metadata?.snapshot_id,
    selectedMetric: visibleSelectedKey,
    viewContext,
  });
  useEffect(() => {
    let cancelled = false;
    elk
      .layout({
        id: "root",
        layoutOptions: {
          "elk.algorithm": "layered",
          "elk.direction": "RIGHT",
          "elk.spacing.nodeNode": "32",
          "elk.layered.spacing.nodeNodeBetweenLayers": "90",
        },
        children: subset.nodes.map((n) => ({ id: n.metric_key, width: 220, height: 155 })),
        edges: subset.edges.map((e, i) => ({
          id: String(i),
          sources: [e.source],
          targets: [e.target],
        })),
      })
      .then((result) => {
        if (!cancelled) {
          setPositions(
            Object.fromEntries(
              (result.children ?? []).map((n) => [n.id, { x: n.x ?? 0, y: n.y ?? 0 }]),
            ),
          );
          requestAnimationFrame(() => void flow.fitView({ padding: 0.15, duration: 300 }));
        }
      })
      .catch(() => {
        if (!cancelled)
          setPositions(
            Object.fromEntries(subset.nodes.map((n) => [n.metric_key, { x: n.x, y: n.y }])),
          );
      });
    return () => {
      cancelled = true;
    };
    // Layout depends on topology, not changing values or selection styling.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);
  const nodes = subset.nodes.map((n) => {
    const incoming = subset.edges.some((e) => e.target === n.metric_key),
      outgoing = subset.edges.some((e) => e.source === n.metric_key);
    const role =
      n.metric_key === visibleSelectedKey
        ? "target"
        : !incoming
          ? "root"
          : outgoing
            ? "intermediate"
            : "outcome";
    return {
      id: n.metric_key,
      type: "metric",
      position: positions[n.metric_key] ?? { x: n.x, y: n.y },
      data: {
        ...n,
        domain: domain(n.metric_key),
        role,
        color: colors[role],
        active: n.metric_key === visibleSelectedKey,
      },
      style: {
        opacity: search && !n.label.toLowerCase().includes(search.toLowerCase()) ? 0.25 : 1,
      },
    };
  });
  const edges = subset.edges.map((e) => ({
    id: e.source + ">" + e.target,
    source: e.source,
    target: e.target,
    type: "default",
    markerEnd: { type: MarkerType.ArrowClosed, color: e.score >= 0 ? "#38bdf8" : "#f87171" },
    style: {
      stroke: e.score >= 0 ? "#38bdf8" : "#f87171",
      strokeWidth: 1 + Math.abs(e.score) * 3,
      strokeDasharray: e.score < 0 ? "6 4" : undefined,
      opacity:
        !visibleSelectedKey ||
        focus ||
        e.source === visibleSelectedKey ||
        e.target === visibleSelectedKey
          ? 1
          : 0.3,
    },
    label:
      e.source === visibleSelectedKey || e.target === visibleSelectedKey
        ? `${formatLag(e.lag_minutes)} · ${e.score.toFixed(2)}`
        : undefined,
    labelStyle: { fill: "#cbd5e1", fontSize: 10 },
    labelBgStyle: { fill: "#071721" },
  }));
  function sendMessage(message: string) {
    if (!message.trim() || askMutation.isPending || !metadata) return;
    askMutation.mutate(
      {
        message: message.trim(),
        selectedMetric: visibleSelectedKey,
        snapshotId: metadata.snapshot_id,
        viewContext,
      },
      { onSuccess: () => setInput("") },
    );
  }
  const notices = (metadata?.warnings ?? []).filter((w) => !/synthetic|pcmci/i.test(w));
  return (
    <div className="space-y-4" data-testid="mobility-workspace">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionTitle
          title="Auto Mobility Causal Decision Twin"
          subtitle="Explore relationships across sales, finance, delivery, service and warranty."
        />
        <div className="text-xs text-slate-400">
          Last computed
          <br />
          {dateText(metadata?.computed_at)}
        </div>
      </div>
      <details className="rounded-lg border border-sky-500/20 bg-sky-500/5 p-3 text-xs">
        <summary className="cursor-pointer text-sky-400">How to read this causal graph</summary>
        <p className="mt-3">
          Nodes represent measured business activity. Red roots have no discovered incoming
          relationship; green nodes are intermediate drivers; amber marks terminal outcomes. A node
          turns blue when you select it. These roles describe the observed graph, not proven root
          causes. Blue solid arrows show positive associations and red dashed arrows show negative
          associations at the indicated lag. Neither colour means good or bad performance.
          Relationships do not establish an intervention's effect.
        </p>
      </details>
      <Panel title="Business Health" subtitle="Key measures in the current analysis">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          {graph?.kpis.map((k) => (
            <button
              key={k.metric_key}
              onClick={() => setSelectedKey(k.metric_key)}
              className="rounded-lg border border-white/10 bg-[#0b1b25] p-3 text-left"
            >
              <p className="text-xs text-slate-400">{k.label}</p>
              <p className="my-1 text-xl font-semibold">{k.value}</p>
              <p className={"flex items-center gap-1 text-xs " + toneClass[k.trend_tone]}>
                {trendDirection(k.trend) === "up" && <ArrowUp className="h-3 w-3" />}
                {trendDirection(k.trend) === "down" && <ArrowDown className="h-3 w-3" />}
                {k.trend}
              </p>
              <Sparkline
                values={graph.nodes.find((n) => n.metric_key === k.metric_key)?.recent_values}
                tone={k.trend_tone}
              />
            </button>
          ))}
        </div>
      </Panel>
      <div
        className={`grid items-start gap-3 ${assistant ? "xl:grid-cols-[minmax(0,1fr)_380px]" : ""}`}
      >
        <div className="min-w-0 rounded-xl border border-sky-900/40 bg-[#06131c] p-3">
          <div className="mb-3 flex flex-wrap justify-between gap-2">
            <div>
              <h2 className="font-semibold">Global Causal Graph — All Regions</h2>
              <p className="text-xs text-slate-400">
                {graph?.nodes.length ?? 0} connected measures · {graph?.edge_details.length ?? 0}{" "}
                relationships · {metadata?.effective_observation_count ?? 0} usable observations ·
                Data through {dateText(metadata?.data_end)}
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void graphQuery.refetch()}
              disabled={graphQuery.isFetching}
            >
              {graphQuery.isFetching ? "Checking…" : "Check for updates"}
            </Button>
          </div>
          {graphQuery.isError && (
            <p role="alert" className="p-3 text-red-300">
              {errorText(graphQuery.error)}
            </p>
          )}
          {metadata?.status === "stale" && (
            <p role="status" className="mb-2 text-xs text-amber-300">
              Analysis is stale. {metadata.last_error}
            </p>
          )}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {["All Measures", "Sales", "Finance", "Delivery", "Service", "Warranty", "Other"].map(
              (d) => (
                <Button
                  key={d}
                  size="sm"
                  variant={filter === d ? "default" : "outline"}
                  onClick={() => setFilter(d)}
                >
                  {d}
                </Button>
              ),
            )}
            <Input
              className="w-48"
              placeholder="Search measure…"
              aria-label="Search measure"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setFilter("All Measures");
                setSearch("");
                setFocus(false);
                setSelectedKey(null);
                void flow.fitView({ duration: 300 });
              }}
            >
              Reset
            </Button>
            <Button
              size="sm"
              variant={focus ? "default" : "outline"}
              disabled={!visibleSelectedKey}
              onClick={() => setFocus(!focus)}
            >
              {focus ? "Clear Focus" : "Active Chains"}
            </Button>
            <Button
              size="sm"
              variant={assistant ? "default" : "outline"}
              className="border border-sky-400"
              onClick={() => setAssistant((open) => !open)}
            >
              {assistant ? "Hide AI Copilot" : "AI Copilot"}
            </Button>
          </div>
          {search && (
            <div className="mb-2 flex flex-wrap gap-2">
              {graph?.nodes
                .filter((n) => n.label.toLowerCase().includes(search.toLowerCase()))
                .map((n) => (
                  <button
                    key={n.metric_key}
                    className="rounded border border-sky-800 p-2 text-xs"
                    onClick={() => {
                      setSelectedKey(n.metric_key);
                      setFilter("All Measures");
                      setSearch("");
                      setFocus(false);
                      const pos = positions[n.metric_key];
                      if (pos)
                        void flow.setCenter(pos.x + 110, pos.y + 60, { zoom: 1, duration: 300 });
                    }}
                  >
                    {n.label} · Reveal
                  </button>
                ))}
            </div>
          )}
          <div
            className="h-[560px] min-w-0 overflow-hidden rounded-lg border border-white/10"
            style={{ overscrollBehavior: "contain" }}
          >
            {graphQuery.isPending ? (
              <p className="p-8 text-sm">Loading analysis…</p>
            ) : nodes.length === 0 ? (
              <p className="p-8 text-sm text-slate-400">
                No connected measures in this view. Clear filters or check for updates.
              </p>
            ) : (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                onNodeClick={(_, n) => setSelectedKey(n.id)}
                nodesDraggable
                onNodeDrag={(_, node) => {
                  setPositions((previous) => ({ ...previous, [node.id]: node.position }));
                }}
                onNodeDragStop={(_, node) => {
                  setPositions((previous) => ({ ...previous, [node.id]: node.position }));
                }}
                nodesConnectable={false}
                edgesReconnectable={false}
                deleteKeyCode={null}
                minZoom={0.2}
                maxZoom={2}
                fitView
                preventScrolling
                colorMode="dark"
              >
                <Background color="#173342" gap={18} />
                <Controls showInteractive={false} />
                <MiniMap
                  pannable
                  zoomable
                  nodeColor={(n) => String(n.data.color)}
                  style={{ background: "#071721" }}
                />
              </ReactFlow>
            )}
          </div>
          <div className="mt-3 flex flex-wrap justify-between gap-3 text-xs">
            <div className="flex flex-wrap gap-4">
              {Object.entries(colors)
                .filter(([role]) => role !== "target" || visibleSelectedKey)
                .map(([role, color]) => (
                  <span key={role} style={{ color }}>
                    ●{" "}
                    {role === "root"
                      ? "Upstream roots"
                      : role === "intermediate"
                        ? "Intermediate drivers"
                        : role === "target"
                          ? "Selected target"
                          : "Terminal outcomes"}
                  </span>
                ))}
            </div>
            <span className="text-slate-400">
              Showing {nodes.length} of {graph?.nodes.length ?? 0} nodes · {edges.length}{" "}
              relationships{focus ? " · Chain focus active" : ""}
            </span>
          </div>
        </div>
        {assistant && (
          <aside className="flex max-h-[680px] min-h-[620px] min-w-0 flex-col rounded-xl border border-sky-500/30 bg-[#071721] p-4 shadow-[0_0_30px_rgba(14,165,233,0.08)]">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold text-sky-200">AI Copilot</h2>
                <p className="mt-1 text-[11px] text-slate-400">
                  Explains the graph and selected metric currently on screen.
                </p>
              </div>
              <Button
                size="sm"
                variant="ghost"
                aria-label="Close AI Copilot"
                onClick={() => setAssistant(false)}
              >
                ×
              </Button>
            </div>
            <div
              className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-white/10 bg-black/10 p-3"
              aria-live="polite"
              data-testid="mobility-default-explanation"
            >
              {explanationQuery.isPending ? (
                <p className="text-xs text-slate-400">Analyzing the current graph…</p>
              ) : explanationQuery.isError ? (
                <div className="space-y-2 text-xs text-red-300" role="alert">
                  <p>{errorText(explanationQuery.error)}</p>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void explanationQuery.refetch()}
                  >
                    Retry explanation
                  </Button>
                </div>
              ) : explanationQuery.data?.reply ? (
                <CopilotText content={explanationQuery.data.reply} />
              ) : (
                <p className="text-xs text-slate-400">
                  No connected relationship is available in this view.
                </p>
              )}
            </div>

            <details className="mt-3 rounded-lg border border-white/10 p-2">
              <summary className="cursor-pointer text-xs font-medium text-sky-300">
                Suggested follow-up questions
              </summary>
              <div className="mt-2 grid gap-2">
                {SUGGESTED_QUESTIONS.map((question) => (
                  <Button
                    key={question}
                    variant="outline"
                    size="sm"
                    disabled={askMutation.isPending || !metadata}
                    onClick={() => sendMessage(question)}
                    className="h-auto justify-start py-2 text-left text-[11px] font-normal whitespace-normal"
                  >
                    {question}
                  </Button>
                ))}
              </div>
            </details>

            {!!historyQuery.data?.turns.length && (
              <div className="mt-3 max-h-44 space-y-2 overflow-y-auto rounded-lg border border-white/10 p-2">
                {historyQuery.data.turns.map((turn, index) => (
                  <div
                    key={index}
                    className={`rounded-lg p-2 text-xs whitespace-pre-wrap ${
                      turn.role === "user"
                        ? "ml-4 bg-primary/10 text-right"
                        : "mr-4 bg-white/[0.03]"
                    }`}
                  >
                    {turn.role === "assistant" ? (
                      <CopilotText content={turn.content} />
                    ) : (
                      turn.content
                    )}
                  </div>
                ))}
                {askMutation.isPending && <p className="text-xs italic">Thinking…</p>}
                <div ref={endRef} />
              </div>
            )}
            {!historyQuery.data?.turns.length && askMutation.isPending && (
              <p className="mt-2 text-xs italic">Thinking…</p>
            )}
            {[historyQuery.error, askMutation.error, clearMutation.error]
              .filter(Boolean)
              .map((error, index) => (
                <p key={index} role="alert" className="mt-2 text-xs text-red-300">
                  {errorText(error)}
                </p>
              ))}
            <form
              className="mt-3 flex gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                sendMessage(input);
              }}
            >
              <Input
                aria-label="Ask the mobility twin"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Ask about this graph…"
                maxLength={2000}
                disabled={askMutation.isPending || !metadata}
              />
              <Button
                type="submit"
                size="sm"
                disabled={askMutation.isPending || !input.trim() || !metadata}
              >
                Send
              </Button>
            </form>
            {!!historyQuery.data?.turns.length && (
              <Button
                variant="ghost"
                size="sm"
                className="mt-1 w-full"
                onClick={() => clearMutation.mutate()}
                disabled={clearMutation.isPending || askMutation.isPending}
              >
                Clear chat
              </Button>
            )}
          </aside>
        )}
      </div>
      {detailQuery.isError && (
        <p role="alert" className="text-red-300">
          {errorText(detailQuery.error)}{" "}
          <button onClick={() => void detailQuery.refetch()}>Retry detail</button>
        </p>
      )}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Panel title="Node Description">
          <p className="font-semibold">{activeNode?.label ?? "Select a measure"}</p>
          <p className="mt-2 text-xs text-slate-400">
            {activeNode
              ? `${activeNode.label} measured as a ${activeNode.aggregation}, in ${activeNode.unit}.`
              : "Select a node to inspect its observed relationships."}
          </p>
          <p className="my-3 text-2xl">{detail?.display_value ?? activeNode?.metric ?? "—"}</p>
          <p className="text-xs">{activeNode?.trend}</p>
          <p className="mt-3 text-xs text-slate-400">
            Business domain: {activeNode ? domain(activeNode.metric_key) : "—"}
          </p>
          {detailQuery.isFetching && <p className="text-xs">Loading evidence…</p>}
        </Panel>
        <Panel title="Top Drivers (Incoming)">
          <div className="space-y-2">
            {detail?.top_drivers.map((d) => (
              <button
                className="w-full rounded-lg border border-white/10 p-2 text-left text-xs"
                key={d.metric}
                onClick={() => setSelectedKey(d.metric)}
              >
                <b>{d.label}</b>
                <p className="mt-1 text-slate-400">
                  Lag: {formatLag(d.lag_minutes)} · Strength: {d.score.toFixed(2)} · Adjusted q:{" "}
                  {d.q_value.toExponential(2)}
                </p>
              </button>
            ))}
            {detail && !detail.top_drivers.length && (
              <p className="text-xs text-slate-400">No retained incoming driver.</p>
            )}
          </div>
        </Panel>
        <Panel title="Recommended Investigations">
          <p className="text-xs leading-relaxed text-slate-300">
            {detail?.recommended_action ??
              "Select a measure to load its evidence-based investigation."}
          </p>
          <p className="mt-4 text-xs text-slate-500">
            Validate these associations before changing business operations. No action impact has
            been estimated.
          </p>
        </Panel>
        <Panel title="Data & Causal Evidence">
          <div className="space-y-3 text-xs text-slate-400">
            <p>{detail?.relationships.length ?? 0} relationships for selected measure</p>
            <p>Sampling interval: {metadata?.sample_stride_hours ?? "—"} hours</p>
            <p>{metadata?.effective_observation_count ?? "—"} usable observations</p>
            <p>Adjusted q threshold: {metadata?.significance_threshold ?? "—"}</p>
            <details>
              <summary className="cursor-pointer text-sky-400">
                Data coverage and interpretation ({notices.length} notices)
              </summary>
              <p className="mt-2">
                {dateText(metadata?.data_start)} — {dateText(metadata?.data_end)}
              </p>
              <p>
                Source checked through {dateText(metadata?.source_latest_at)}. Analysis checks every{" "}
                {metadata?.refresh_check_minutes} minutes.
              </p>
              {notices.map((n) => (
                <p className="mt-2" key={n}>
                  {n}
                </p>
              ))}
            </details>
            <details>
              <summary className="cursor-pointer text-sky-400">Downstream relationships</summary>
              {detail?.relationships
                .filter((r) => r.direction === "out_of")
                .map((r) => (
                  <p key={r.metric} className="mt-2">
                    {r.label}: {r.score.toFixed(2)} · {formatLag(r.lag_minutes)}
                  </p>
                ))}
            </details>
          </div>
        </Panel>
      </div>
    </div>
  );
}
