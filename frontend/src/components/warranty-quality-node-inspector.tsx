import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { StatPill } from "@/components/ui/panel";
import type { WarrantyQualityCausalPathSupport, WarrantyQualityWarning } from "@/lib/api/types";

type InspectorEdge = {
  id: string;
  source: string;
  target: string;
  path: WarrantyQualityCausalPathSupport;
};

type NodeInspectorProps = {
  warning: WarrantyQualityWarning;
  edges: InspectorEdge[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  manufacturingRunId?: string | null;
  telematicsRunId?: string | null;
  onSelectEdge: (edgeId: string) => void;
  onClearSelection: () => void;
};

function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function domainLabel(path: WarrantyQualityCausalPathSupport) {
  if (path.causal_domain === "manufacturing") return "MANUFACTURING";
  if (path.causal_domain === "telematics") return "TELEMATICS";
  return "UNKNOWN";
}

function domainDescription(domain: string) {
  if (domain === "MANUFACTURING") return "Production/process causal evidence";
  if (domain === "TELEMATICS") return "Post-delivery vehicle causal evidence";
  return "Domain not provided by the runtime API";
}

function formatNumber(value: number | null | undefined, digits = 3) {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "—"
    : value.toFixed(digits);
}

function formatProbability(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  return value < 0.001 ? value.toExponential(2) : value.toFixed(4);
}

function formatPercent(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "—"
    : `${(value * 100).toFixed(1)}%`;
}

function formatLag(path: WarrantyQualityCausalPathSupport) {
  const minutes = path.observed_lag_minutes?.filter((lag) => Number.isFinite(lag)) ?? [];
  if (minutes.length > 0) return `${minutes.join(" / ")} min`;
  const steps = path.observed_lags.filter((lag) => Number.isFinite(lag));
  return steps.length > 0 ? `${steps.join(" / ")} lag steps` : "—";
}

function formatList(values: string[]) {
  return values.length > 0 ? values.join(", ") : "—";
}

/** Render a count without ever leaking `undefined`/`null`/`NaN` to the user. */
function formatCount(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value) ? "—" : String(value);
}

/** Render a free-text runtime field, falling back to an em dash when absent. */
function formatText(value: string | null | undefined) {
  const trimmed = typeof value === "string" ? value.trim() : "";
  return trimmed.length > 0 ? trimmed : "—";
}

function unique(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value))));
}

function runId(value: string | null | undefined) {
  return value ? value.slice(0, 16) : "—";
}

function EvidenceRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-black/10 px-3 py-2">
      <div className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
      <div className="mt-1 break-words text-[11px] font-medium text-white/90">{value}</div>
    </div>
  );
}

function EdgeEvidenceCard({
  edge,
  expanded,
  selected,
  onSelect,
  onToggleExpanded,
}: {
  edge: InspectorEdge;
  expanded: boolean;
  selected: boolean;
  onSelect: () => void;
  onToggleExpanded: () => void;
}) {
  const path = edge.path;
  const domain = domainLabel(path);
  const positive = path.consensus_sign.trim().startsWith("+");

  return (
    <article
      id={`causal-edge-card-${edge.id}`}
      className={`border-b border-white/10 py-3 transition-colors last:border-b-0 ${
        selected ? "border-l-2 border-primary/70 bg-primary/5 pl-3" : ""
      }`}
    >
      <div className="flex items-start gap-3">
        <button
          type="button"
          className="min-w-0 flex-1 text-left"
          onClick={onSelect}
          aria-label={`Select causal edge ${edge.source} to ${edge.target}`}
        >
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-semibold">
            <span className="font-mono text-white">{edge.source}</span>
            <span className="text-primary">→</span>
            <span className="font-mono text-white">{edge.target}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="rounded-full border border-white/15 bg-white/[0.06] px-2 py-0.5 text-[9px] font-semibold tracking-wide text-white/90">
              {domain}
            </span>
            <span
              className={`rounded-full border px-2 py-0.5 text-[9px] font-semibold ${
                positive
                  ? "border-orange-300/30 bg-orange-300/10 text-orange-100"
                  : "border-sky-300/30 bg-sky-300/10 text-sky-100"
              }`}
            >
              {path.consensus_sign || "—"}
            </span>
            <span className="rounded-full border border-white/15 bg-white/[0.06] px-2 py-0.5 text-[9px] text-muted-foreground">
              {formatLag(path)}
            </span>
          </div>
        </button>
        <button
          type="button"
          className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-white/10 hover:text-white"
          onClick={onToggleExpanded}
          aria-expanded={expanded}
          aria-label={expanded ? "Collapse edge evidence" : "Expand edge evidence"}
        >
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>
      </div>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted-foreground">
        <span>{domainDescription(domain)}</span>
        <span>
          {positive ? "Positive" : "Negative"} ({path.consensus_sign || "—"})
        </span>
        <span>{formatLag(path)}</span>
        <span>Effect: {formatNumber(path.mean_abs_score)}</span>
      </div>

      {expanded && (
        <div className="mt-3 space-y-3 border-t border-white/10 pt-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <EvidenceRow label="Source metric" value={formatText(path.source_metric)} />
            <EvidenceRow label="Target metric" value={formatText(path.target_metric)} />
            <EvidenceRow label="Domain" value={domain} />
            <EvidenceRow label="Sign" value={formatText(path.consensus_sign)} />
            <EvidenceRow label="Observed lag" value={formatLag(path)} />
            <EvidenceRow label="Mean |score|" value={formatNumber(path.mean_abs_score)} />
            <EvidenceRow label="Median |score|" value={formatNumber(path.median_abs_score)} />
            <EvidenceRow label="Best p-value" value={formatProbability(path.best_p_value)} />
            <EvidenceRow label="Best q-value" value={formatProbability(path.best_q_value)} />
            <EvidenceRow label="Min p-value" value={formatProbability(path.min_p_value)} />
            <EvidenceRow label="Max p-value" value={formatProbability(path.max_p_value)} />
            <EvidenceRow label="Min q-value" value={formatProbability(path.min_q_value)} />
            <EvidenceRow label="Max q-value" value={formatProbability(path.max_q_value)} />
            <EvidenceRow
              label="Recurrence fraction"
              value={formatPercent(path.recurrence_fraction)}
            />
            <EvidenceRow label="Sign agreement" value={formatPercent(path.sign_agreement)} />
            <EvidenceRow label="Scope" value={formatText(path.scope)} />
            <EvidenceRow label="Provenance" value={formatText(path.provenance)} />
            <EvidenceRow label="Causal run ID" value={formatText(path.causal_run_id)} />
          </div>

          {domain === "MANUFACTURING" ? (
            <div>
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-primary">
                Manufacturing evidence
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <EvidenceRow
                  label="Recurring machines"
                  value={formatCount(path.recurring_machines)}
                />
                <EvidenceRow
                  label="Eligible machines"
                  value={formatCount(path.eligible_machines)}
                />
                <EvidenceRow label="Overlap machines" value={formatList(path.overlap_machines)} />
                <EvidenceRow label="Overlap count" value={formatCount(path.overlap_count)} />
                <EvidenceRow
                  label="Exact lineage count"
                  value={formatCount(path.exact_lineage_count)}
                />
                <EvidenceRow
                  label="Exact lineage fraction"
                  value={formatPercent(path.exact_lineage_fraction)}
                />
                <EvidenceRow
                  label="Issue lineage fraction"
                  value={formatPercent(path.issue_exact_lineage_machine_fraction)}
                />
                <EvidenceRow
                  label="Causal edge fraction"
                  value={formatPercent(path.causal_edge_machine_fraction)}
                />
              </div>
            </div>
          ) : domain === "TELEMATICS" ? (
            <div>
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-cyan-200">
                Telematics evidence
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <EvidenceRow
                  label="Recurring vehicles"
                  value={formatCount(path.recurring_vehicles)}
                />
                <EvidenceRow
                  label="Eligible vehicles"
                  value={formatCount(path.eligible_vehicles)}
                />
                <EvidenceRow
                  label="Supporting vehicles"
                  value={formatList(path.supporting_vehicle_ids ?? [])}
                />
                <EvidenceRow
                  label="Overlap vehicles"
                  value={formatList(path.overlap_vehicles ?? [])}
                />
                <EvidenceRow
                  label="Overlap count"
                  value={formatCount(path.overlap_vehicle_count)}
                />
                <EvidenceRow
                  label="Issue vehicle fraction"
                  value={formatPercent(path.issue_vehicle_fraction)}
                />
                <EvidenceRow
                  label="Causal edge fraction"
                  value={formatPercent(path.causal_edge_vehicle_fraction)}
                />
              </div>
            </div>
          ) : null}
        </div>
      )}
    </article>
  );
}

export function WarrantyQualityNodeInspector({
  warning,
  edges,
  selectedNodeId,
  selectedEdgeId,
  manufacturingRunId,
  telematicsRunId,
  onSelectEdge,
  onClearSelection,
}: NodeInspectorProps) {
  const [expandedEdgeIds, setExpandedEdgeIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!selectedEdgeId) return;
    setExpandedEdgeIds((current) => new Set(current).add(selectedEdgeId));
  }, [selectedEdgeId]);

  const selectedEdge = edges.find((edge) => edge.id === selectedEdgeId);

  const connectedEdges = useMemo(() => {
    if (!selectedNodeId) return [];
    return edges.filter((edge) => edge.source === selectedNodeId || edge.target === selectedNodeId);
  }, [edges, selectedNodeId]);

  if (!selectedNodeId && !selectedEdge) return null;

  const incomingEdges = connectedEdges.filter((edge) => edge.target === selectedNodeId);
  const outgoingEdges = connectedEdges.filter((edge) => edge.source === selectedNodeId);
  const metric = selectedNodeId ?? selectedEdge?.source ?? selectedEdge?.target ?? "";
  const connectedPaths = selectedNodeId
    ? connectedEdges.map((edge) => edge.path)
    : selectedEdge
      ? [selectedEdge.path]
      : [];
  const sourceMetrics = new Set(connectedPaths.map((path) => path.source_metric));
  const targetMetrics = new Set(connectedPaths.map((path) => path.target_metric));
  const appearsAsSource = sourceMetrics.has(metric);
  const appearsAsTarget = targetMetrics.has(metric);
  const role =
    appearsAsSource && appearsAsTarget
      ? "Source + Target"
      : appearsAsSource
        ? "Causal Source"
        : "Causal Target";
  const domains = Array.from(new Set(connectedPaths.map(domainLabel)));
  const connectedDomain =
    domains.includes("MANUFACTURING") && domains.includes("TELEMATICS")
      ? "Manufacturing + Telematics"
      : domains[0] === "MANUFACTURING"
        ? "Manufacturing"
        : domains[0] === "TELEMATICS"
          ? "Telematics"
          : "—";

  const manufacturingPaths = connectedPaths.filter(
    (path) => path.causal_domain === "manufacturing",
  );
  const telematicsPaths = connectedPaths.filter((path) => path.causal_domain === "telematics");
  const overlapMachines = unique(manufacturingPaths.flatMap((path) => path.overlap_machines));
  const affectedMachines = unique(warning.machine_ids);
  const exactLineageMachines = unique(warning.exact_lineages.map((lineage) => lineage.machine_id));
  const batches = unique(warning.exact_lineages.map((lineage) => lineage.production_batch_id));
  const supplierLots = unique(warning.exact_lineages.map((lineage) => lineage.supplier_lot_id));
  const supportingVehicles = unique(
    telematicsPaths.flatMap((path) => path.supporting_vehicle_ids ?? []),
  );
  const overlapVehicles = unique(telematicsPaths.flatMap((path) => path.overlap_vehicles ?? []));
  const manufacturingRuns = unique(manufacturingPaths.map((path) => path.causal_run_id));
  const telematicsRuns = unique(telematicsPaths.map((path) => path.causal_run_id));

  const toggleExpanded = (edgeId: string) => {
    setExpandedEdgeIds((current) => {
      const next = new Set(current);
      if (next.has(edgeId)) next.delete(edgeId);
      else next.add(edgeId);
      return next;
    });
  };

  const renderEdgeCards = (
    title: string,
    icon: "incoming" | "outgoing",
    cardEdges: InspectorEdge[],
  ) => (
    <div>
      <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-primary">
        {icon === "incoming" ? (
          <ArrowDown className="h-3.5 w-3.5" />
        ) : (
          <ArrowUp className="h-3.5 w-3.5" />
        )}
        {title}
      </div>
      <div className="space-y-2">
        {cardEdges.map((edge) => (
          <EdgeEvidenceCard
            key={edge.id}
            edge={edge}
            expanded={expandedEdgeIds.has(edge.id)}
            selected={selectedEdgeId === edge.id}
            onSelect={() => onSelectEdge(edge.id)}
            onToggleExpanded={() => toggleExpanded(edge.id)}
          />
        ))}
      </div>
    </div>
  );

  return (
    <section
      className="mt-4 rounded-2xl border border-primary/25 bg-primary/[0.035] p-4 shadow-inner shadow-primary/5"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-primary">
            {selectedNodeId ? "Node Inspector" : "Edge Inspector"}
          </div>
          <h3 className="mt-1 text-lg font-semibold">
            {selectedNodeId ? (
              <span className="font-mono">{metric}</span>
            ) : (
              `${selectedEdge?.source} → ${selectedEdge?.target}`
            )}
          </h3>
          <div className="mt-1 text-[11px] text-muted-foreground">
            {selectedNodeId
              ? "Direct incoming and outgoing causal evidence for the selected metric."
              : "Complete causal evidence for the selected runtime edge."}
          </div>
        </div>
        <button
          type="button"
          className="rounded-lg border border-white/10 p-2 text-muted-foreground hover:bg-white/10 hover:text-white"
          onClick={onClearSelection}
          aria-label="Clear graph selection"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {selectedNodeId ? (
        <>
          <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-5">
            <EvidenceRow label="Metric" value={metric} />
            <EvidenceRow label="Role" value={role} />
            <EvidenceRow label="Connected domains" value={connectedDomain} />
            <EvidenceRow label="Incoming edges" value={String(incomingEdges.length)} />
            <EvidenceRow label="Outgoing edges" value={String(outgoingEdges.length)} />
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-4">
            <EvidenceRow label="Total connected edges" value={String(connectedEdges.length)} />
            <EvidenceRow label="Manufacturing paths" value={String(manufacturingPaths.length)} />
            <EvidenceRow label="Telematics paths" value={String(telematicsPaths.length)} />
            <EvidenceRow label="Warning" value={humanize(warning.issue_category)} />
          </div>

          <div className="mt-5 space-y-5">
            {outgoingEdges.length > 0
              ? renderEdgeCards("Outgoing causal edges", "outgoing", outgoingEdges)
              : null}
            {incomingEdges.length > 0
              ? renderEdgeCards("Incoming causal edges", "incoming", incomingEdges)
              : null}
          </div>
        </>
      ) : selectedEdge ? (
        <div className="mt-4">
          <EdgeEvidenceCard
            edge={selectedEdge}
            expanded={expandedEdgeIds.has(selectedEdge.id)}
            selected
            onSelect={() => onSelectEdge(selectedEdge.id)}
            onToggleExpanded={() => toggleExpanded(selectedEdge.id)}
          />
        </div>
      ) : null}

      <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-white/10 bg-black/10 p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-primary">
            Lineage evidence
          </div>
          {manufacturingPaths.length > 0 ? (
            <div className="mt-3 grid grid-cols-2 gap-2">
              <EvidenceRow label="Overlap machines" value={formatList(overlapMachines)} />
              <EvidenceRow
                label="Affected machines"
                value={
                  affectedMachines.length > 0
                    ? formatList(affectedMachines)
                    : String(warning.affected_machines)
                }
              />
              <EvidenceRow
                label="Exact lineage machines"
                value={formatList(exactLineageMachines)}
              />
              <EvidenceRow label="Affected batches" value={formatList(batches)} />
              <EvidenceRow label="Affected supplier lots" value={formatList(supplierLots)} />
            </div>
          ) : null}
          {telematicsPaths.length > 0 ? (
            <div className="mt-3 grid grid-cols-2 gap-2">
              <EvidenceRow label="Supporting vehicle IDs" value={formatList(supportingVehicles)} />
              <EvidenceRow label="Overlap vehicles" value={formatList(overlapVehicles)} />
              <EvidenceRow label="Affected vehicles" value={String(warning.affected_vehicles)} />
            </div>
          ) : null}
          {manufacturingPaths.length === 0 && telematicsPaths.length === 0 ? (
            <div className="mt-2 text-xs text-muted-foreground">
              No domain-specific lineage evidence was returned for this selection.
            </div>
          ) : null}
        </div>

        <div className="rounded-xl border border-white/10 bg-black/10 p-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-primary">
            Warning context
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <EvidenceRow label="Issue category" value={humanize(warning.issue_category)} />
            <EvidenceRow label="Priority" value={warning.priority} />
            <EvidenceRow label="Affected vehicles" value={String(warning.affected_vehicles)} />
            <EvidenceRow label="Affected machines" value={String(warning.affected_machines)} />
            <EvidenceRow label="Affected batches" value={String(warning.affected_batches)} />
            <EvidenceRow
              label="Affected supplier lots"
              value={String(warning.affected_supplier_lots)}
            />
            <EvidenceRow label="Affected models" value={String(warning.affected_models)} />
            <EvidenceRow label="Affected cities" value={String(warning.affected_cities)} />
            <EvidenceRow label="Evidence score" value={String(warning.evidence_score)} />
            <EvidenceRow label="Lineage grade" value={humanize(warning.lineage_evidence_grade)} />
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-white/10 bg-black/10 p-3">
        <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-primary">
          Displayed causal runs
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
          <EvidenceRow
            label="Manufacturing run"
            value={runId(manufacturingRunId ?? manufacturingRuns[0])}
          />
          <EvidenceRow label="Telematics run" value={runId(telematicsRunId ?? telematicsRuns[0])} />
          <EvidenceRow
            label="Manufacturing provenance"
            value={manufacturingPaths[0]?.provenance || "—"}
          />
          <EvidenceRow
            label="Telematics provenance"
            value={telematicsPaths[0]?.provenance || "—"}
          />
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
        <StatPill>Selected warning: {humanize(warning.issue_category)}</StatPill>
        <span>Telematics paths selected: {warning.telematics_paths_selected ?? "—"}</span>
      </div>
    </section>
  );
}
