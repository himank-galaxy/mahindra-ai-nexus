import { GitBranch, Maximize2, Minus, Plus, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Panel } from "@/components/ui/panel";
import { WarrantyQualityNodeInspector } from "@/components/warranty-quality-node-inspector";
import { formatIstDateTime } from "@/lib/formatters";
import type { WarrantyQualityCausalPathSupport, WarrantyQualityWarning } from "@/lib/api/types";

type GraphDomain = "manufacturing" | "telematics" | "unknown";

type GraphNode = {
  id: string;
  x: number;
  y: number;
  domain: GraphDomain;
  kind: "metric" | "warning";
};

/** A real, persisted PCMCI candidate — source_metric -> target_metric. */
type GraphEdge = {
  id: string;
  source: string;
  target: string;
  path: WarrantyQualityCausalPathSupport;
};

/**
 * NOT a causal edge. Ties a domain's terminal (sink) metric to the selected
 * warning so the two independently-discovered subgraphs read as one
 * investigation canvas without implying manufacturing metrics cause
 * telematics metrics or vice versa.
 */
type SupportEdge = {
  id: string;
  source: string;
  target: string;
  domain: GraphDomain;
};

type GraphPoint = { x: number; y: number };

type EdgeGeometry = {
  source: GraphPoint;
  control1: GraphPoint;
  control2: GraphPoint;
  target: GraphPoint;
};

type LabeledEdge = { id: string; source: string; target: string; text: string };

type EdgeLabelLayout = {
  x: number;
  y: number;
  text: string;
};

type CausalGraphProps = {
  warning: WarrantyQualityWarning;
  manufacturingRunId?: string | null;
  telematicsRunId?: string | null;
  simulationAsOf?: string | null;
  generatedAt?: string | null;
};

const GRAPH_WIDTH = 1100;
const GRAPH_HEIGHT = 640;
const NODE_WIDTH = 150;
const NODE_HEIGHT = 46;
const WARNING_NODE_WIDTH = 196;
const WARNING_NODE_HEIGHT = 66;
const MIN_ZOOM = 0.4;
const MAX_ZOOM = 2.4;
const ROW_SPACING = 92;
const MARGIN_X = 120;
const MARGIN_TOP = 60;
const WARNING_GAP = 90;
const WARNING_ID = "__selected_warning__";

function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function metricLines(metric: string) {
  const words = humanize(metric).split(" ");
  if (words.length <= 2) return [words.join(" ")];
  const midpoint = Math.ceil(words.length / 2);
  return [words.slice(0, midpoint).join(" "), words.slice(midpoint).join(" ")];
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function domainLabel(path: WarrantyQualityCausalPathSupport) {
  if (path.causal_domain === "manufacturing") return "MANUFACTURING";
  if (path.causal_domain === "telematics") return "TELEMATICS";
  return "UNKNOWN";
}

function domainChip(domain: GraphDomain) {
  if (domain === "manufacturing") return "MFG";
  if (domain === "telematics") return "TEL";
  return "—";
}

function domainColor(domain: GraphDomain) {
  if (domain === "telematics") return "oklch(0.78 0.16 190)";
  if (domain === "manufacturing") return "oklch(0.72 0.22 27)";
  return "oklch(0.7 0 0)";
}

function formatScore(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value) ? "—" : value.toFixed(3);
}

function formatQValue(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  return value < 0.001 ? value.toExponential(2) : value.toFixed(4);
}

function formatPercent(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "—"
    : `${(value * 100).toFixed(1)}%`;
}

function formatObservedLag(path: WarrantyQualityCausalPathSupport) {
  const minutes = path.observed_lag_minutes?.filter((lag) => Number.isFinite(lag)) ?? [];
  if (minutes.length > 0) return `${minutes.join(" / ")} min`;
  const steps = path.observed_lags.filter((lag) => Number.isFinite(lag));
  return steps.length > 0 ? `${steps.join(" / ")} lag steps` : "—";
}

function formatEdgeAnnotation(path: WarrantyQualityCausalPathSupport) {
  const domain = path.causal_domain === "telematics" ? "TEL" : "MFG";
  const sign = path.consensus_sign || "—";
  const minutes = path.observed_lag_minutes?.filter((lag) => Number.isFinite(lag)) ?? [];
  const lag = minutes.length
    ? `${minutes.join(" / ")}m`
    : path.observed_lags.length
      ? `${path.observed_lags.filter((lag) => Number.isFinite(lag)).join(" / ")} steps`
      : "—";
  return `${domain} • ${sign} • ${lag}`;
}

function formatRunId(value: string | null | undefined) {
  return value ? value.slice(0, 12) : "—";
}

function edgeIdentity(path: WarrantyQualityCausalPathSupport, index: number) {
  return [
    path.source_metric,
    path.target_metric,
    path.causal_domain ?? "unknown",
    path.consensus_sign,
    (path.observed_lag_minutes ?? []).join("/"),
    path.causal_run_id ?? "unknown-run",
    index,
  ].join("::");
}

function pathDomain(path: WarrantyQualityCausalPathSupport): GraphDomain {
  if (path.causal_domain === "manufacturing") return "manufacturing";
  if (path.causal_domain === "telematics") return "telematics";
  return "unknown";
}

/**
 * Deterministic topological levels via Kahn's algorithm. Direction- and
 * orientation-agnostic: callers decide whether a level maps to x or y.
 */
function layerMetrics(
  metrics: string[],
  edges: { source: string; target: string }[],
): { levels: Map<string, number>; maxLevel: number; degree: Map<string, number> } {
  const incoming = new Map(metrics.map((metric) => [metric, 0]));
  const outgoing = new Map(metrics.map((metric) => [metric, [] as string[]]));
  edges.forEach((edge) => {
    incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1);
    outgoing.get(edge.source)?.push(edge.target);
  });

  const remaining = new Map(incoming);
  const levels = new Map(metrics.map((metric) => [metric, 0]));
  const queue = metrics.filter((metric) => (remaining.get(metric) ?? 0) === 0);
  const processed = new Set<string>();

  while (queue.length > 0) {
    const source = queue.shift();
    if (!source) break;
    processed.add(source);
    const sourceLevel = levels.get(source) ?? 0;
    for (const target of outgoing.get(source) ?? []) {
      levels.set(target, Math.max(levels.get(target) ?? 0, sourceLevel + 1));
      const next = (remaining.get(target) ?? 0) - 1;
      remaining.set(target, next);
      if (next === 0) queue.push(target);
    }
  }

  let maxLevel = Math.max(0, ...levels.values());
  metrics
    .filter((metric) => !processed.has(metric))
    .forEach((metric) => {
      const inDegree = incoming.get(metric) ?? 0;
      const outDegree = outgoing.get(metric)?.length ?? 0;
      levels.set(
        metric,
        outDegree > inDegree
          ? 0
          : inDegree > outDegree
            ? Math.max(2, maxLevel)
            : Math.max(1, Math.floor(maxLevel / 2)),
      );
    });
  maxLevel = Math.max(0, ...levels.values());

  if (new Set(levels.values()).size === 1 && metrics.length > 1) {
    [...metrics]
      .sort(
        (a, b) =>
          (outgoing.get(b)?.length ?? 0) -
            (incoming.get(b) ?? 0) -
            ((outgoing.get(a)?.length ?? 0) - (incoming.get(a) ?? 0)) || a.localeCompare(b),
      )
      .forEach((metric, index) => {
        const fraction = index / Math.max(1, metrics.length - 1);
        levels.set(metric, fraction < 0.34 ? 0 : fraction < 0.67 ? 1 : 2);
      });
    maxLevel = 2;
  }

  const degree = new Map(
    metrics.map((metric) => [
      metric,
      (incoming.get(metric) ?? 0) + (outgoing.get(metric)?.length ?? 0),
    ]),
  );
  return { levels, maxLevel, degree };
}

/**
 * Lays one domain's metrics out as a horizontal layered DAG within its own
 * region: level -> x (source metrics on the left, sinks on the right),
 * same-level metrics stacked and centered vertically within the band. Bands
 * themselves still stack top to bottom around the warning anchor; only the
 * within-band orientation is horizontal.
 */
function layoutBand(
  metrics: string[],
  edges: { source: string; target: string }[],
  domain: GraphDomain,
  top: number,
) {
  const { levels, maxLevel, degree } = layerMetrics(metrics, edges);
  const columns = new Map<number, string[]>();
  metrics.forEach((metric) => {
    const level = levels.get(metric) ?? 0;
    const group = columns.get(level) ?? [];
    group.push(metric);
    columns.set(level, group);
  });

  const tallestColumn = Math.max(1, ...Array.from(columns.values(), (group) => group.length));
  const bandHeight = (tallestColumn - 1) * ROW_SPACING;
  const usableWidth = GRAPH_WIDTH - MARGIN_X * 2;

  const nodes: GraphNode[] = [];
  Array.from(columns.entries())
    .sort(([a], [b]) => a - b)
    .forEach(([level, columnMetrics]) => {
      const x = maxLevel === 0 ? GRAPH_WIDTH / 2 : MARGIN_X + (level / maxLevel) * usableWidth;
      const sorted = [...columnMetrics].sort(
        (a, b) => (degree.get(b) ?? 0) - (degree.get(a) ?? 0) || a.localeCompare(b),
      );
      const columnHeight = (sorted.length - 1) * ROW_SPACING;
      const offset = top + (bandHeight - columnHeight) / 2;
      sorted.forEach((metric, index) => {
        nodes.push({ id: metric, x, y: offset + index * ROW_SPACING, domain, kind: "metric" });
      });
    });

  const outDegree = new Map(metrics.map((metric) => [metric, 0]));
  edges.forEach((edge) => outDegree.set(edge.source, (outDegree.get(edge.source) ?? 0) + 1));
  // Sinks: metrics that this domain's own edges never point away from. These
  // are the metrics most proximal to the field defect, so they carry the
  // dashed "supports warning" association.
  const sinkIds = metrics.filter((metric) => (outDegree.get(metric) ?? 0) === 0);

  return { nodes, height: bandHeight, sinkIds };
}

function buildGraph(paths: WarrantyQualityCausalPathSupport[]) {
  const causalEdges: GraphEdge[] = paths.map((path, index) => ({
    id: edgeIdentity(path, index),
    source: path.source_metric,
    target: path.target_metric,
    path,
  }));

  const byDomain = (domain: GraphDomain) =>
    causalEdges.filter((edge) => pathDomain(edge.path) === domain);
  const mfgEdges = byDomain("manufacturing");
  const telEdges = byDomain("telematics");
  const otherEdges = byDomain("unknown");

  const metricsOf = (edges: GraphEdge[]) =>
    Array.from(new Set(edges.flatMap((edge) => [edge.source, edge.target]))).sort();
  const mfgMetrics = metricsOf(mfgEdges);
  const telMetrics = metricsOf(telEdges);
  const otherMetrics = metricsOf(otherEdges);

  if (mfgMetrics.length === 0 && telMetrics.length === 0 && otherMetrics.length === 0) {
    return { nodes: [] as GraphNode[], edges: causalEdges, supportEdges: [] as SupportEdge[] };
  }

  let cursor = MARGIN_TOP;
  const mfgBand =
    mfgMetrics.length > 0 ? layoutBand(mfgMetrics, mfgEdges, "manufacturing", cursor) : null;
  if (mfgBand) cursor += mfgBand.height + WARNING_GAP;

  const warningY = cursor;
  cursor += WARNING_GAP;

  const telBand =
    telMetrics.length > 0 ? layoutBand(telMetrics, telEdges, "telematics", cursor) : null;
  if (telBand) cursor += telBand.height + WARNING_GAP;

  const otherBand =
    otherMetrics.length > 0 ? layoutBand(otherMetrics, otherEdges, "unknown", cursor) : null;

  const warningNode: GraphNode = {
    id: WARNING_ID,
    x: GRAPH_WIDTH / 2,
    y: warningY,
    domain: "unknown",
    kind: "warning",
  };

  const nodes: GraphNode[] = [
    ...(mfgBand?.nodes ?? []),
    warningNode,
    ...(telBand?.nodes ?? []),
    ...(otherBand?.nodes ?? []),
  ];

  // Every sink in a domain's own subgraph gets ONE dashed association into
  // the warning anchor. This is evidence bookkeeping, never a discovered
  // causal edge, and it never crosses manufacturing metrics into telematics
  // metrics or vice versa.
  const supportEdges: SupportEdge[] = [
    ...(mfgBand?.sinkIds ?? []).map((id) => ({
      id: `support::manufacturing::${id}`,
      source: id,
      target: WARNING_ID,
      domain: "manufacturing" as const,
    })),
    ...(telBand?.sinkIds ?? []).map((id) => ({
      id: `support::telematics::${id}`,
      source: id,
      target: WARNING_ID,
      domain: "telematics" as const,
    })),
    ...(otherBand?.sinkIds ?? []).map((id) => ({
      id: `support::unknown::${id}`,
      source: id,
      target: WARNING_ID,
      domain: "unknown" as const,
    })),
  ];

  return { nodes, edges: causalEdges, supportEdges };
}

/**
 * Anchors on the node boundary along whichever axis dominates travel, so a
 * mostly-vertical MFG -> warning -> TEL flow gets a natural vertical S-curve
 * and any same-level lateral edge still gets a sane horizontal one.
 */
function edgeGeometry(source: GraphNode, target: GraphNode): EdgeGeometry {
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const vertical = Math.abs(dy) >= Math.abs(dx);
  const sourceHalf = source.kind === "warning" ? WARNING_NODE_HEIGHT / 2 : NODE_HEIGHT / 2;
  const targetHalf = target.kind === "warning" ? WARNING_NODE_HEIGHT / 2 : NODE_HEIGHT / 2;
  const sourceHalfW = source.kind === "warning" ? WARNING_NODE_WIDTH / 2 : NODE_WIDTH / 2;
  const targetHalfW = target.kind === "warning" ? WARNING_NODE_WIDTH / 2 : NODE_WIDTH / 2;

  const sourceAnchor = vertical
    ? { x: source.x, y: source.y + (dy >= 0 ? sourceHalf : -sourceHalf) }
    : { x: source.x + (dx >= 0 ? sourceHalfW : -sourceHalfW), y: source.y };
  const targetAnchor = vertical
    ? { x: target.x, y: target.y + (dy >= 0 ? -targetHalf : targetHalf) }
    : { x: target.x + (dx >= 0 ? -targetHalfW : targetHalfW), y: target.y };

  const along = { x: targetAnchor.x - sourceAnchor.x, y: targetAnchor.y - sourceAnchor.y };
  const length = Math.max(1, Math.hypot(along.x, along.y));
  const curve = clamp(length * 0.38, 30, 140);

  if (vertical) {
    const sign = along.y === 0 ? 1 : Math.sign(along.y);
    return {
      source: sourceAnchor,
      control1: { x: sourceAnchor.x, y: sourceAnchor.y + sign * curve },
      control2: { x: targetAnchor.x, y: targetAnchor.y - sign * curve },
      target: targetAnchor,
    };
  }
  const sign = along.x === 0 ? 1 : Math.sign(along.x);
  return {
    source: sourceAnchor,
    control1: { x: sourceAnchor.x + sign * curve, y: sourceAnchor.y },
    control2: { x: targetAnchor.x - sign * curve, y: targetAnchor.y },
    target: targetAnchor,
  };
}

function edgePath(geometry: EdgeGeometry) {
  return `M ${geometry.source.x} ${geometry.source.y} C ${geometry.control1.x} ${geometry.control1.y}, ${geometry.control2.x} ${geometry.control2.y}, ${geometry.target.x} ${geometry.target.y}`;
}

function cubicPoint(geometry: EdgeGeometry, t: number): GraphPoint {
  const inverse = 1 - t;
  return {
    x:
      inverse ** 3 * geometry.source.x +
      3 * inverse ** 2 * t * geometry.control1.x +
      3 * inverse * t ** 2 * geometry.control2.x +
      t ** 3 * geometry.target.x,
    y:
      inverse ** 3 * geometry.source.y +
      3 * inverse ** 2 * t * geometry.control1.y +
      3 * inverse * t ** 2 * geometry.control2.y +
      t ** 3 * geometry.target.y,
  };
}

function cubicTangent(geometry: EdgeGeometry, t: number): GraphPoint {
  const inverse = 1 - t;
  return {
    x:
      3 * inverse ** 2 * (geometry.control1.x - geometry.source.x) +
      6 * inverse * t * (geometry.control2.x - geometry.control1.x) +
      3 * t ** 2 * (geometry.target.x - geometry.control2.x),
    y:
      3 * inverse ** 2 * (geometry.control1.y - geometry.source.y) +
      6 * inverse * t * (geometry.control2.y - geometry.control1.y) +
      3 * t ** 2 * (geometry.target.y - geometry.control2.y),
  };
}

function edgeLabelPosition(geometry: EdgeGeometry, t: number, offset: number) {
  const point = cubicPoint(geometry, t);
  const tangent = cubicTangent(geometry, t);
  const length = Math.max(1, Math.hypot(tangent.x, tangent.y));
  let normal = { x: -tangent.y / length, y: tangent.x / length };
  if (normal.y > 0) normal = { x: -normal.x, y: -normal.y };
  return {
    x: point.x + normal.x * offset,
    y: point.y + normal.y * offset,
  };
}

function labelBounds(position: GraphPoint, text: string) {
  const width = Math.max(56, text.length * 6.2);
  return {
    left: position.x - width / 2,
    right: position.x + width / 2,
    top: position.y - 8,
    bottom: position.y + 8,
  };
}

function boundsOverlap(
  left: ReturnType<typeof labelBounds>,
  right: ReturnType<typeof labelBounds>,
  padding = 7,
) {
  return !(
    left.right + padding < right.left ||
    right.right + padding < left.left ||
    left.bottom + padding < right.top ||
    right.bottom + padding < left.top
  );
}

function layoutEdgeLabels(edges: LabeledEdge[], nodes: GraphNode[]) {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const occupied = nodes.map((node) => {
    const halfW = node.kind === "warning" ? WARNING_NODE_WIDTH / 2 : NODE_WIDTH / 2;
    const halfH = node.kind === "warning" ? WARNING_NODE_HEIGHT / 2 : NODE_HEIGHT / 2;
    return {
      left: node.x - halfW - 12,
      right: node.x + halfW + 12,
      top: node.y - halfH - 12,
      bottom: node.y + halfH + 12,
    };
  });
  const positions = new Map<string, EdgeLabelLayout>();
  const tCandidates = [0.5, 0.42, 0.58, 0.46, 0.54, 0.4, 0.6];
  const offsetCandidates = [14, 19, 25, 32, 40];

  [...edges]
    .sort((left, right) => left.id.localeCompare(right.id))
    .forEach((edge) => {
      const source = nodeById.get(edge.source);
      const target = nodeById.get(edge.target);
      if (!source || !target) return;
      const geometry = edgeGeometry(source, target);
      const text = edge.text;
      let selectedPosition: GraphPoint | null = null;
      let selectedBounds: ReturnType<typeof labelBounds> | null = null;

      for (const t of tCandidates) {
        for (const offset of offsetCandidates) {
          const position = edgeLabelPosition(geometry, t, offset);
          const bounds = labelBounds(position, text);
          const overlaps = occupied.some((candidate) => boundsOverlap(bounds, candidate));
          if (!overlaps) {
            selectedPosition = position;
            selectedBounds = bounds;
            break;
          }
        }
        if (selectedPosition) break;
      }

      if (!selectedPosition || !selectedBounds) {
        selectedPosition = edgeLabelPosition(geometry, 0.5, 40);
        selectedBounds = labelBounds(selectedPosition, text);
      }
      occupied.push(selectedBounds);
      positions.set(edge.id, { ...selectedPosition, text });
    });

  return positions;
}

function fitViewport(nodes: GraphNode[], edges: { source: string; target: string }[] = []) {
  if (nodes.length === 0) return { x: 0, y: 0, zoom: 1 };
  const points: GraphPoint[] = nodes.flatMap((node) => {
    const halfW = node.kind === "warning" ? WARNING_NODE_WIDTH / 2 : NODE_WIDTH / 2;
    const halfH = node.kind === "warning" ? WARNING_NODE_HEIGHT / 2 : NODE_HEIGHT / 2;
    return [
      { x: node.x - halfW, y: node.y - halfH },
      { x: node.x + halfW, y: node.y + halfH },
    ];
  });
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  edges.forEach((edge) => {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    if (!source || !target) return;
    const geometry = edgeGeometry(source, target);
    [0, 0.25, 0.5, 0.75, 1].forEach((t) => points.push(cubicPoint(geometry, t)));
  });
  const minX = Math.min(...points.map((point) => point.x)) - 36;
  const maxX = Math.max(...points.map((point) => point.x)) + 36;
  const minY = Math.min(...points.map((point) => point.y)) - 36;
  const maxY = Math.max(...points.map((point) => point.y)) + 36;
  const padding = 70;
  const zoom = clamp(
    Math.min(
      (GRAPH_WIDTH - padding * 2) / Math.max(1, maxX - minX),
      (GRAPH_HEIGHT - padding * 2) / Math.max(1, maxY - minY),
      1.35,
    ),
    MIN_ZOOM,
    MAX_ZOOM,
  );
  return {
    x: GRAPH_WIDTH / 2 - ((minX + maxX) / 2) * zoom,
    y: GRAPH_HEIGHT / 2 - ((minY + maxY) / 2) * zoom,
    zoom,
  };
}

function edgeTooltip(edge: GraphEdge) {
  const path = edge.path;
  const domain = domainLabel(path);
  const domainSpecific =
    path.causal_domain === "telematics"
      ? `Recurring vehicles: ${path.recurring_vehicles ?? "—"}\nEligible vehicles: ${path.eligible_vehicles ?? "—"}\nSupporting vehicles: ${(path.supporting_vehicle_ids ?? []).join(", ") || "—"}`
      : `Recurring machines: ${path.recurring_machines}\nEligible machines: ${path.eligible_machines}\nOverlap machines: ${path.overlap_machines.join(", ") || "—"}`;
  return `${edge.source} → ${edge.target}\nDomain: ${domain}\nSign: ${path.consensus_sign || "—"}\nObserved lag: ${formatObservedLag(path)}\nMean |score|: ${formatScore(path.mean_abs_score)}\nMedian |score|: ${formatScore(path.median_abs_score)}\nBest p-value: ${formatQValue(path.best_p_value)}\nBest q-value: ${formatQValue(path.best_q_value)}\nMin/max p-value: ${formatQValue(path.min_p_value)} / ${formatQValue(path.max_p_value)}\nMin/max q-value: ${formatQValue(path.min_q_value)} / ${formatQValue(path.max_q_value)}\nRecurrence: ${formatPercent(path.recurrence_fraction)}\nSign agreement: ${formatPercent(path.sign_agreement)}\nScope: ${path.scope || "—"}\nProvenance: ${path.provenance || "—"}\nCausal run: ${formatRunId(path.causal_run_id)}\n${domainSpecific}`;
}

export function WarrantyQualityCausalGraph({
  warning,
  manufacturingRunId,
  telematicsRunId,
  simulationAsOf,
  generatedAt,
}: CausalGraphProps) {
  const autoGraph = useMemo(() => buildGraph(warning.causal_paths), [warning.causal_paths]);
  const [nodes, setNodes] = useState<GraphNode[]>(autoGraph.nodes);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [viewport, setViewport] = useState(() =>
    fitViewport(autoGraph.nodes, [...autoGraph.edges, ...autoGraph.supportEdges]),
  );
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<{
    kind: "pan" | "node";
    pointerId: number;
    nodeId?: string;
    clientX: number;
    clientY: number;
    startX: number;
    startY: number;
    moved: boolean;
  } | null>(null);

  const suppressClickRef = useRef(false);
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const handleWheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      const rect = svg.getBoundingClientRect();
      const anchorX = (event.clientX - rect.left) * (GRAPH_WIDTH / Math.max(1, rect.width));
      const anchorY = (event.clientY - rect.top) * (GRAPH_HEIGHT / Math.max(1, rect.height));
      const factor = event.deltaY < 0 ? 1.1 : 0.9;
      setViewport((current) => {
        const nextZoom = clamp(current.zoom * factor, MIN_ZOOM, MAX_ZOOM);
        const ratio = nextZoom / current.zoom;
        return {
          zoom: nextZoom,
          x: anchorX - (anchorX - current.x) * ratio,
          y: anchorY - (anchorY - current.y) * ratio,
        };
      });
    };
    svg.addEventListener("wheel", handleWheel, { passive: false });
    return () => svg.removeEventListener("wheel", handleWheel);
  }, []);

  // Defensive reconciliation for a rebuilt autoGraph within a mounted
  // component (the parent forces a full remount via `key` on every
  // meaningful identity change, so in practice this only ever intersects
  // identical id sets — but it guarantees no stale position, selected node,
  // or selected edge can ever survive a topology that no longer contains it).
  useEffect(() => {
    setNodes((current) => {
      const positions = new Map(current.map((node) => [node.id, node]));
      return autoGraph.nodes.map((node) => positions.get(node.id) ?? node);
    });
    setSelectedNodeId((current) =>
      current && autoGraph.nodes.some((node) => node.kind === "metric" && node.id === current)
        ? current
        : null,
    );
    setSelectedEdgeId((current) =>
      current && autoGraph.edges.some((edge) => edge.id === current) ? current : null,
    );
  }, [autoGraph]);

  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const labeledEdges = useMemo<LabeledEdge[]>(
    () => [
      ...autoGraph.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        text: formatEdgeAnnotation(edge.path),
      })),
      ...autoGraph.supportEdges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        text: "supports warning",
      })),
    ],
    [autoGraph.edges, autoGraph.supportEdges],
  );
  const edgeLabels = useMemo(() => layoutEdgeLabels(labeledEdges, nodes), [labeledEdges, nodes]);
  const degree = useMemo(() => {
    const incoming = new Map<string, number>();
    const outgoing = new Map<string, number>();
    nodes.forEach((node) => {
      incoming.set(node.id, 0);
      outgoing.set(node.id, 0);
    });
    autoGraph.edges.forEach((edge) => {
      incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1);
      outgoing.set(edge.source, (outgoing.get(edge.source) ?? 0) + 1);
    });
    return { incoming, outgoing };
  }, [autoGraph.edges, nodes]);

  const selection = useMemo(() => {
    const activeNodeIds = new Set<string>();
    const activeEdgeIds = new Set<string>();
    const activeSupportIds = new Set<string>();
    if (!selectedNodeId) return { activeNodeIds, activeEdgeIds, activeSupportIds };
    activeNodeIds.add(selectedNodeId);
    autoGraph.edges.forEach((edge) => {
      if (edge.source !== selectedNodeId && edge.target !== selectedNodeId) return;
      activeEdgeIds.add(edge.id);
      activeNodeIds.add(edge.source);
      activeNodeIds.add(edge.target);
    });
    autoGraph.supportEdges.forEach((edge) => {
      if (edge.source === selectedNodeId) activeSupportIds.add(edge.id);
    });
    return { activeNodeIds, activeEdgeIds, activeSupportIds };
  }, [autoGraph.edges, autoGraph.supportEdges, selectedNodeId]);

  function graphUnits(clientDeltaX: number, clientDeltaY: number) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return { x: clientDeltaX, y: clientDeltaY };
    return {
      x: clientDeltaX * (GRAPH_WIDTH / Math.max(1, rect.width)),
      y: clientDeltaY * (GRAPH_HEIGHT / Math.max(1, rect.height)),
    };
  }

  function zoomAround(anchor: { x: number; y: number }, factor: number) {
    setViewport((current) => {
      const nextZoom = clamp(current.zoom * factor, MIN_ZOOM, MAX_ZOOM);
      const ratio = nextZoom / current.zoom;
      return {
        zoom: nextZoom,
        x: anchor.x - (anchor.x - current.x) * ratio,
        y: anchor.y - (anchor.y - current.y) * ratio,
      };
    });
  }

  function handleCanvasPointerDown(event: React.PointerEvent<SVGSVGElement>) {
    if (event.button !== 0) return;
    setSelectedNodeId(null);
    suppressClickRef.current = false;
    setSelectedEdgeId(null);
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      kind: "pan",
      pointerId: event.pointerId,
      clientX: event.clientX,
      moved: false,
      clientY: event.clientY,
      startX: viewport.x,
      startY: viewport.y,
    };
  }

  function handleNodePointerDown(event: React.PointerEvent<SVGGElement>, node: GraphNode) {
    if (event.button !== 0) return;
    event.stopPropagation();
    suppressClickRef.current = false;
    svgRef.current?.setPointerCapture(event.pointerId);
    dragRef.current = {
      kind: "node",
      pointerId: event.pointerId,
      moved: false,
      nodeId: node.id,
      clientX: event.clientX,
      clientY: event.clientY,
      startX: node.x,
      startY: node.y,
    };
  }

  function handlePointerMove(event: React.PointerEvent<SVGSVGElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const delta = graphUnits(event.clientX - drag.clientX, event.clientY - drag.clientY);
    if (Math.hypot(event.clientX - drag.clientX, event.clientY - drag.clientY) > 5) {
      drag.moved = true;
    }
    if (drag.kind === "pan") {
      setViewport((current) => ({
        ...current,
        x: drag.startX + delta.x,
        y: drag.startY + delta.y,
      }));
    } else {
      setNodes((current) =>
        current.map((node) =>
          node.id === drag.nodeId
            ? {
                ...node,
                x: drag.startX + delta.x / viewport.zoom,
                y: drag.startY + delta.y / viewport.zoom,
              }
            : node,
        ),
      );
    }
  }

  function handlePointerUp(event: React.PointerEvent<SVGSVGElement>) {
    if (dragRef.current?.pointerId === event.pointerId) {
      suppressClickRef.current = dragRef.current.moved;
      dragRef.current = null;
    }
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
  }

  function handleEdgeSelect(edge: GraphEdge) {
    if (selectedNodeId && edge.source !== selectedNodeId && edge.target !== selectedNodeId)
      setSelectedNodeId(null);
    setSelectedEdgeId(edge.id);
  }

  function resetLayout() {
    setNodes(autoGraph.nodes);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setViewport(fitViewport(autoGraph.nodes, [...autoGraph.edges, ...autoGraph.supportEdges]));
  }

  const manufacturingPaths = autoGraph.edges.filter(
    (edge) => edge.path.causal_domain === "manufacturing",
  ).length;
  const telematicsPaths = autoGraph.edges.filter(
    (edge) => edge.path.causal_domain === "telematics",
  ).length;
  const metricCount = autoGraph.nodes.filter((node) => node.kind === "metric").length;

  if (autoGraph.nodes.length === 0) {
    return (
      <Panel
        title="Warning Investigation Graph"
        subtitle="Manufacturing and telematics PCMCI candidates, with provenance and support kept distinct."
      >
        <div className="flex min-h-[360px] items-center justify-center rounded-xl border border-dashed border-white/10 bg-white/[0.02]">
          <div className="max-w-md text-center">
            <GitBranch className="mx-auto h-6 w-6 text-muted-foreground" />
            <div className="mt-3 text-sm font-medium">No lineage-aligned causal candidates</div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              This warning has field evidence, but no persisted stable PCMCI candidate overlaps the
              exact affected machine lineage.
            </div>
          </div>
        </div>
      </Panel>
    );
  }

  return (
    <Panel
      title="Warning Investigation Graph"
      subtitle="One canvas per selected warning. Manufacturing and telematics candidates remain two independent PCMCI models — only their evidence, not their metrics, is tied together."
    >
      <div className="mb-4 grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-8">
        <div className="rounded-lg border border-white/10 bg-white/[0.025] p-2">
          <div className="text-[9px] uppercase tracking-widest text-muted-foreground">
            Simulation time
          </div>
          <div className="mt-1 text-[11px] font-semibold">{formatIstDateTime(simulationAsOf)}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.025] p-2">
          <div className="text-[9px] uppercase tracking-widest text-muted-foreground">
            Generated
          </div>
          <div className="mt-1 text-[11px] font-semibold">{formatIstDateTime(generatedAt)}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.025] p-2">
          <div className="text-[9px] uppercase tracking-widest text-muted-foreground">
            Manufacturing run
          </div>
          <div className="mt-1 font-mono text-[11px] font-semibold">
            {formatRunId(manufacturingRunId)}
          </div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.025] p-2">
          <div className="text-[9px] uppercase tracking-widest text-muted-foreground">
            Telematics run
          </div>
          <div className="mt-1 font-mono text-[11px] font-semibold">
            {formatRunId(telematicsRunId)}
          </div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.025] p-2">
          <div className="text-[9px] uppercase tracking-widest text-muted-foreground">
            Manufacturing paths
          </div>
          <div className="mt-1 text-[11px] font-semibold">{manufacturingPaths}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.025] p-2">
          <div className="text-[9px] uppercase tracking-widest text-muted-foreground">
            Telematics paths
          </div>
          <div className="mt-1 text-[11px] font-semibold">{telematicsPaths}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.025] p-2">
          <div className="text-[9px] uppercase tracking-widest text-muted-foreground">
            Candidate paths
          </div>
          <div className="mt-1 text-[11px] font-semibold">{autoGraph.edges.length}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.025] p-2">
          <div className="text-[9px] uppercase tracking-widest text-muted-foreground">Metrics</div>
          <div className="mt-1 text-[11px] font-semibold">{metricCount}</div>
        </div>
      </div>

      <div className="relative h-[560px] overflow-hidden overscroll-contain rounded-xl border border-white/10 bg-[#090a0d] shadow-inner shadow-black/40">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`}
          className="h-full w-full touch-none select-none"
          role="img"
          aria-label={`Interactive warning investigation graph for ${humanize(warning.issue_category)}`}
          onPointerDown={handleCanvasPointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          <defs>
            <marker
              id="warranty-quality-causal-arrow-positive"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="oklch(0.72 0.22 27)" />
            </marker>
            <marker
              id="warranty-quality-causal-arrow-negative"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="oklch(0.75 0.14 235)" />
            </marker>
            <marker
              id="warranty-quality-causal-arrow-telematics"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="oklch(0.78 0.16 190)" />
            </marker>
            <marker
              id="warranty-quality-support-arrow"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="oklch(0.7 0 0)" />
            </marker>
            <filter
              id="warranty-quality-causal-selected-glow"
              x="-30%"
              y="-50%"
              width="160%"
              height="200%"
            >
              <feGaussianBlur stdDeviation="5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <rect width={GRAPH_WIDTH} height={GRAPH_HEIGHT} fill="transparent" />
          <g transform={`translate(${viewport.x} ${viewport.y}) scale(${viewport.zoom})`}>
            {/* Support edges: dashed, neutral — evidence association with the
                selected warning, never a PCMCI-discovered causal edge. */}
            {autoGraph.supportEdges.map((edge) => {
              const source = nodeById.get(edge.source);
              const target = nodeById.get(edge.target);
              if (!source || !target) return null;
              const geometry = edgeGeometry(source, target);
              const label = edgeLabels.get(edge.id);
              const active = selection.activeSupportIds.has(edge.id);
              const dimmed =
                Boolean(selectedNodeId && !active) || Boolean(!selectedNodeId && selectedEdgeId);
              return (
                <g key={edge.id} pointerEvents="none">
                  <path
                    d={edgePath(geometry)}
                    fill="none"
                    stroke={domainColor(edge.domain)}
                    strokeWidth={active ? 2 : 1.3}
                    strokeOpacity={dimmed ? 0.08 : active ? 0.7 : 0.4}
                    strokeDasharray="5 5"
                    markerEnd="url(#warranty-quality-support-arrow)"
                    vectorEffect="non-scaling-stroke"
                  />
                  {label ? (
                    <text
                      x={label.x}
                      y={label.y}
                      textAnchor="middle"
                      fontSize="9"
                      fontStyle="italic"
                      fontWeight="500"
                      fill="oklch(0.72 0 0)"
                      opacity={dimmed ? 0.12 : 0.85}
                      paintOrder="stroke"
                      stroke="#090a0d"
                      strokeOpacity="0.95"
                      strokeWidth="4"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      {label.text}
                    </text>
                  ) : null}
                  <title>
                    {`${edge.source} supports warning\nDomain: ${domainChip(edge.domain)}\nNot a PCMCI-discovered causal edge — an evidence association with the selected warning.`}
                  </title>
                </g>
              );
            })}

            {autoGraph.edges.map((edge) => {
              const source = nodeById.get(edge.source);
              const target = nodeById.get(edge.target);
              if (!source || !target) return null;
              const domain = domainLabel(edge.path);
              const negative = edge.path.consensus_sign.trim().startsWith("-");
              const edgeSelected = selectedEdgeId === edge.id;
              const connected = !selectedNodeId || selection.activeEdgeIds.has(edge.id);
              const dimmed =
                Boolean(selectedNodeId && !connected) ||
                Boolean(!selectedNodeId && selectedEdgeId && !edgeSelected);
              const stroke =
                domain === "TELEMATICS"
                  ? "oklch(0.78 0.16 190)"
                  : negative
                    ? "oklch(0.75 0.14 235)"
                    : "oklch(0.72 0.22 27)";
              const marker =
                domain === "TELEMATICS"
                  ? "url(#warranty-quality-causal-arrow-telematics)"
                  : negative
                    ? "url(#warranty-quality-causal-arrow-negative)"
                    : "url(#warranty-quality-causal-arrow-positive)";
              const geometry = edgeGeometry(source, target);
              const label = edgeLabels.get(edge.id);
              if (!label) return null;
              return (
                <g
                  key={edge.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`${edge.source} to ${edge.target} causal edge`}
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={(event) => {
                    event.stopPropagation();
                    handleEdgeSelect(edge);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      handleEdgeSelect(edge);
                    }
                  }}
                >
                  <path
                    d={edgePath(geometry)}
                    fill="none"
                    stroke="transparent"
                    strokeWidth="16"
                    vectorEffect="non-scaling-stroke"
                    className="cursor-pointer"
                  />
                  <path
                    d={edgePath(geometry)}
                    fill="none"
                    stroke={stroke}
                    strokeWidth={edgeSelected ? 3.4 : selectedNodeId && connected ? 2.5 : 1.7}
                    strokeOpacity={dimmed ? 0.08 : edgeSelected || selectedNodeId ? 0.95 : 0.72}
                    markerEnd={dimmed ? undefined : marker}
                    vectorEffect="non-scaling-stroke"
                    pointerEvents="none"
                    className="transition-[stroke-opacity,stroke-width] duration-200"
                  />
                  <text
                    x={label.x}
                    y={label.y}
                    textAnchor="middle"
                    fontSize="10"
                    fontWeight="700"
                    fill={stroke}
                    opacity={dimmed ? 0.12 : 1}
                    paintOrder="stroke"
                    stroke="#090a0d"
                    strokeOpacity="0.95"
                    strokeWidth="4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    pointerEvents="none"
                  >
                    {label.text}
                  </text>
                  <title>{edgeTooltip(edge)}</title>
                </g>
              );
            })}

            {nodes.map((node) => {
              if (node.kind === "warning") {
                return (
                  <g
                    key={node.id}
                    transform={`translate(${node.x} ${node.y})`}
                    className="cursor-grab active:cursor-grabbing"
                    onPointerDown={(event) => handleNodePointerDown(event, node)}
                    onClick={(event) => event.stopPropagation()}
                  >
                    <title>{`${humanize(warning.issue_category)}\nPriority: ${warning.priority}\nThis node is an evidence anchor, not a metric — dashed edges into it are evidence associations, not causal edges.`}</title>
                    <rect
                      x={-WARNING_NODE_WIDTH / 2 - 4}
                      y={-WARNING_NODE_HEIGHT / 2 - 4}
                      width={WARNING_NODE_WIDTH + 8}
                      height={WARNING_NODE_HEIGHT + 8}
                      rx={14}
                      fill="oklch(0.65 0.19 55 / 0.14)"
                      filter="url(#warranty-quality-causal-selected-glow)"
                    />
                    <rect
                      x={-WARNING_NODE_WIDTH / 2}
                      y={-WARNING_NODE_HEIGHT / 2}
                      width={WARNING_NODE_WIDTH}
                      height={WARNING_NODE_HEIGHT}
                      rx={12}
                      fill="oklch(0.24 0.05 55 / 0.97)"
                      stroke="oklch(0.72 0.19 55 / 0.9)"
                      strokeWidth={1.6}
                      vectorEffect="non-scaling-stroke"
                    />
                    <text
                      x={0}
                      y={-10}
                      textAnchor="middle"
                      fontSize="8.5"
                      fontWeight="700"
                      letterSpacing="0.14em"
                      fill="oklch(0.85 0.15 55)"
                    >
                      SELECTED WARNING
                    </text>
                    <text
                      x={0}
                      y={7}
                      textAnchor="middle"
                      fontSize="11.5"
                      fontWeight="700"
                      fill="white"
                    >
                      {humanize(warning.issue_category)}
                    </text>
                    <text
                      x={0}
                      y={22}
                      textAnchor="middle"
                      fontSize="9"
                      fontWeight="600"
                      fill="oklch(0.85 0.15 55 / 0.85)"
                    >
                      {warning.priority}
                    </text>
                  </g>
                );
              }

              const lines = metricLines(node.id);
              const selected = selectedNodeId === node.id;
              const connected = !selectedNodeId || selection.activeNodeIds.has(node.id);
              const chip = domainChip(node.domain);
              const chipColor = domainColor(node.domain);
              return (
                <g
                  key={node.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`${node.id} causal metric (${chip})`}
                  transform={`translate(${node.x} ${node.y})`}
                  className="cursor-grab outline-none active:cursor-grabbing"
                  opacity={selectedNodeId && !connected ? 0.24 : 1}
                  onPointerDown={(event) => handleNodePointerDown(event, node)}
                  onClick={(event) => {
                    event.stopPropagation();
                    if (suppressClickRef.current) {
                      suppressClickRef.current = false;
                      return;
                    }
                    setSelectedNodeId((current) => (current === node.id ? null : node.id));
                    setSelectedEdgeId(null);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedNodeId((current) => (current === node.id ? null : node.id));
                      setSelectedEdgeId(null);
                    }
                  }}
                >
                  <title>{`${node.id}\nDomain: ${chip}\nIncoming causal paths: ${degree.incoming.get(node.id) ?? 0}\nOutgoing causal paths: ${degree.outgoing.get(node.id) ?? 0}\nDrag to reposition · Click to inspect direct relationships`}</title>
                  {selected ? (
                    <rect
                      x={-NODE_WIDTH / 2 - 5}
                      y={-NODE_HEIGHT / 2 - 5}
                      width={NODE_WIDTH + 10}
                      height={NODE_HEIGHT + 10}
                      rx={12}
                      fill="oklch(0.62 0.23 27 / 0.16)"
                      filter="url(#warranty-quality-causal-selected-glow)"
                    />
                  ) : null}
                  <rect
                    x={-NODE_WIDTH / 2}
                    y={-NODE_HEIGHT / 2}
                    width={NODE_WIDTH}
                    height={NODE_HEIGHT}
                    rx={9}
                    fill={selected ? "oklch(0.34 0.12 27 / 0.96)" : "oklch(0.18 0.01 260 / 0.96)"}
                    stroke={
                      selected
                        ? "oklch(0.72 0.22 27 / 0.95)"
                        : connected && selectedNodeId
                          ? "oklch(1 0 0 / 0.26)"
                          : "oklch(1 0 0 / 0.16)"
                    }
                    strokeWidth={selected ? 1.6 : 1}
                    vectorEffect="non-scaling-stroke"
                  />
                  <circle cx={-NODE_WIDTH / 2} cy={0} r={2.5} fill="oklch(0.78 0 0 / 0.6)" />
                  <circle cx={NODE_WIDTH / 2} cy={0} r={2.5} fill="oklch(0.78 0 0 / 0.6)" />
                  {/* Compact domain indicator: a metric's origin is shown on
                      the node itself rather than by placing it inside a
                      large domain-colored region. */}
                  <rect
                    x={-NODE_WIDTH / 2 + 4}
                    y={-NODE_HEIGHT / 2 + 4}
                    width={22}
                    height={11}
                    rx={3}
                    fill={chipColor}
                    opacity={0.9}
                  />
                  <text
                    x={-NODE_WIDTH / 2 + 15}
                    y={-NODE_HEIGHT / 2 + 12.5}
                    textAnchor="middle"
                    fontSize="7"
                    fontWeight="700"
                    fill="#090a0d"
                  >
                    {chip}
                  </text>
                  {lines.map((line, index) => (
                    <text
                      key={`${node.id}-${line}-${index}`}
                      x={0}
                      y={lines.length === 1 ? 3 : -4 + index * 13}
                      textAnchor="middle"
                      fontSize="9.5"
                      fill="white"
                      fontWeight="500"
                      pointerEvents="none"
                    >
                      {line}
                    </text>
                  ))}
                </g>
              );
            })}
          </g>
        </svg>

        <div className="absolute bottom-3 left-3 flex items-center overflow-hidden rounded-lg border border-white/10 bg-black/70 shadow-xl backdrop-blur">
          <button
            type="button"
            className="grid h-9 w-9 place-items-center border-r border-white/10 text-muted-foreground hover:bg-white/10 hover:text-white"
            onClick={() => zoomAround({ x: GRAPH_WIDTH / 2, y: GRAPH_HEIGHT / 2 }, 1.15)}
            aria-label="Zoom in"
            title="Zoom in"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className="grid h-9 w-9 place-items-center border-r border-white/10 text-muted-foreground hover:bg-white/10 hover:text-white"
            onClick={() => zoomAround({ x: GRAPH_WIDTH / 2, y: GRAPH_HEIGHT / 2 }, 0.87)}
            aria-label="Zoom out"
            title="Zoom out"
          >
            <Minus className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className="grid h-9 w-9 place-items-center border-r border-white/10 text-muted-foreground hover:bg-white/10 hover:text-white"
            onClick={() =>
              setViewport(fitViewport(nodes, [...autoGraph.edges, ...autoGraph.supportEdges]))
            }
            aria-label="Fit graph to view"
            title="Fit view"
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className="grid h-9 w-9 place-items-center text-muted-foreground hover:bg-white/10 hover:text-white"
            onClick={resetLayout}
            aria-label="Reset graph layout"
            title="Reset layout"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="pointer-events-none absolute right-3 top-3 rounded-lg border border-white/10 bg-black/55 px-2.5 py-1.5 text-[9px] text-muted-foreground">
          {Math.round(viewport.zoom * 100)}% · drag canvas · drag nodes
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-[10px] text-muted-foreground">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-orange-300" />
          MFG · manufacturing / production-process causal relationship
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-cyan-300" />
          TEL · vehicle telematics / post-delivery causal relationship
        </div>
        <div>+ positive</div>
        <div>- negative</div>
        <div>Arrow: source → target</div>
        <div>Lag: observed minutes</div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-3 border-t-2 border-dashed border-white/40" />
          Dashed = supports warning (evidence association, not a PCMCI-discovered causal edge)
        </div>
      </div>

      <WarrantyQualityNodeInspector
        warning={warning}
        edges={autoGraph.edges}
        selectedNodeId={selectedNodeId}
        selectedEdgeId={selectedEdgeId}
        manufacturingRunId={manufacturingRunId}
        telematicsRunId={telematicsRunId}
        onSelectEdge={setSelectedEdgeId}
        onClearSelection={() => {
          setSelectedNodeId(null);
          setSelectedEdgeId(null);
        }}
      />
    </Panel>
  );
}
