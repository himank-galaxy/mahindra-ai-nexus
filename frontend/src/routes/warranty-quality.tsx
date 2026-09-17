import { createFileRoute } from "@tanstack/react-router";
import {
  AlertTriangle,
  Clock,
  Database,
  Factory,
  MapPin,
  Package,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";

import { Panel, SectionTitle, StatPill } from "@/components/ui/panel";
import { WarrantyQualityCausalGraph } from "@/components/warranty-quality-causal-graph";
import { useWarrantyQualityCausalStatus, useWarrantyQualityEarlyWarnings } from "@/hooks/use-api";
import { formatIstDateTime } from "@/lib/formatters";
import type {
  WarrantyQualityCausalStatus,
  WarrantyQualityPriority,
  WarrantyQualityWarning,
} from "@/lib/api/types";

export const Route = createFileRoute("/warranty-quality")({
  head: () => ({
    meta: [
      {
        title: "Warranty & Quality Early-Warning Graph · Mahindra AI Command Center",
      },
    ],
  }),
  component: WarrantyQualityEarlyWarningPage,
});

function priorityTone(
  priority: WarrantyQualityPriority,
): "danger" | "warning" | "info" | "default" {
  if (priority === "CRITICAL") return "danger";
  if (priority === "HIGH") return "warning";
  if (priority === "MEDIUM") return "info";
  return "default";
}

function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatInr(value: number) {
  if (value >= 10_000_000) {
    return `₹${(value / 10_000_000).toFixed(2)} Cr`;
  }

  if (value >= 100_000) {
    return `₹${(value / 100_000).toFixed(2)} L`;
  }

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number, digits = 0) {
  return `${(value * 100).toFixed(digits)}%`;
}

function formatScore(value: number) {
  return value.toFixed(3);
}

function formatQValue(value: number) {
  if (value === 0) return "0";
  if (value < 0.001) return value.toExponential(2);
  return value.toFixed(4);
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{label}</div>

      <div className="mt-2 text-xl font-semibold tracking-tight">{value}</div>

      {detail && <div className="mt-1 text-[11px] text-muted-foreground">{detail}</div>}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-6">
      <SectionTitle
        title="Warranty & Quality Early-Warning Graph"
        subtitle="Connecting field issues to exact manufacturing lineage and statistically discovered stable causal candidates."
      />

      <Panel>
        <div className="flex min-h-[360px] items-center justify-center">
          <div className="text-center">
            <div className="mx-auto h-9 w-9 animate-spin rounded-full border-2 border-white/10 border-t-primary" />

            <div className="mt-4 text-sm font-medium">Loading early-warning evidence</div>

            <div className="mt-1 text-xs text-muted-foreground">
              Reading the latest persisted manufacturing causal run.
            </div>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function ErrorState({ error, status }: { error: unknown; status?: WarrantyQualityCausalStatus }) {
  const message = error instanceof Error ? error.message : "The early-warning API request failed.";

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Warranty & Quality Early-Warning Graph"
        subtitle="Connecting field issues to exact manufacturing lineage and statistically discovered stable causal candidates."
      />

      <CausalStatusPanel status={status} />

      <Panel>
        <div className="flex min-h-[320px] items-center justify-center">
          <div className="max-w-lg text-center">
            <div className="mx-auto grid h-11 w-11 place-items-center rounded-full border border-red-500/30 bg-red-500/10">
              <AlertTriangle className="h-5 w-5 text-red-300" />
            </div>

            <div className="mt-4 text-sm font-semibold">Early-warning data could not be loaded</div>

            <div className="mt-2 text-xs leading-5 text-muted-foreground">{message}</div>

            <div className="mt-3 text-[11px] text-muted-foreground">
              No fallback business data is displayed when the runtime API is unavailable.
            </div>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function EmptyState({ runId, status }: { runId: string; status?: WarrantyQualityCausalStatus }) {
  return (
    <div className="space-y-6">
      <SectionTitle
        title="Warranty & Quality Early-Warning Graph"
        subtitle="Connecting field issues to exact manufacturing lineage and statistically discovered stable causal candidates."
        right={<StatPill tone="info">Run {runId.slice(0, 8)}</StatPill>}
      />

      <CausalStatusPanel status={status} />

      <Panel>
        <div className="flex min-h-[320px] items-center justify-center">
          <div className="max-w-lg text-center">
            <div className="mx-auto grid h-11 w-11 place-items-center rounded-full border border-white/10 bg-white/[0.03]">
              <ShieldCheck className="h-5 w-5 text-muted-foreground" />
            </div>

            <div className="mt-4 text-sm font-semibold">No early warnings generated</div>

            <div className="mt-2 text-xs leading-5 text-muted-foreground">
              The persisted causal run was loaded successfully, but the API returned no warranty or
              quality warnings for this evaluation.
            </div>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function WarningList({
  warnings,
  active,
  onSelect,
}: {
  warnings: WarrantyQualityWarning[];
  active: WarrantyQualityWarning;
  onSelect: (issueCategory: string) => void;
}) {
  return (
    <Panel
      title="Priority Warnings"
      subtitle="Issue categories ranked by the runtime early-warning service."
      className="xl:sticky xl:top-6 xl:self-start"
    >
      <div className="max-h-[690px] space-y-2 overflow-y-auto pr-1">
        {warnings.map((warning) => {
          const selected = warning.issue_category === active.issue_category;

          return (
            <button
              key={warning.issue_category}
              type="button"
              onClick={() => onSelect(warning.issue_category)}
              className={[
                "w-full rounded-xl border p-3 text-left transition-all",

                selected
                  ? "border-primary/50 bg-primary/10 shadow-inner shadow-primary/10"
                  : "border-white/10 bg-white/[0.025] hover:border-white/20 hover:bg-white/[0.05]",
              ].join(" ")}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-xs font-semibold">
                    {humanize(warning.issue_category)}
                  </div>

                  <div className="mt-1 text-[10px] text-muted-foreground">
                    {warning.complaints} complaints · {warning.warranty_claims} claims
                  </div>
                </div>

                <StatPill tone={priorityTone(warning.priority)}>{warning.priority}</StatPill>
              </div>

              <div className="mt-3 grid grid-cols-2 gap-2 text-[10px]">
                <div>
                  <div className="text-muted-foreground">Evidence index</div>

                  <div className="mt-0.5 font-semibold">{warning.evidence_score}</div>
                </div>

                <div>
                  <div className="text-muted-foreground">Exact lineage</div>

                  <div className="mt-0.5 font-semibold">
                    {formatPercent(warning.exact_window_lineage_coverage)}
                  </div>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

function WarningEvidence({ warning }: { warning: WarrantyQualityWarning }) {
  return (
    <Panel
      title="Selected Warning Evidence"
      subtitle="Observed field evidence and exact manufacturing lineage for the selected issue category."
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-lg font-semibold">{humanize(warning.issue_category)}</div>

          <div className="mt-2 flex flex-wrap gap-2">
            <StatPill tone={priorityTone(warning.priority)}>{warning.priority}</StatPill>

            <StatPill tone="info">{humanize(warning.lineage_evidence_grade)}</StatPill>
          </div>
        </div>

        <div className="text-right">
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
            Empirical evidence index
          </div>

          <div className="mt-1 text-2xl font-semibold">{warning.evidence_score}</div>

          <div className="text-[10px] text-muted-foreground">Not probability or confidence</div>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard
          label="Complaints"
          value={String(warning.complaints)}
          detail={`${warning.service_events} service events`}
        />

        <MetricCard
          label="Repairs"
          value={String(warning.repairs)}
          detail={`${warning.warranty_candidates} warranty candidates`}
        />

        <MetricCard
          label="Warranty Claims"
          value={String(warning.warranty_claims)}
          detail={`${warning.affected_vehicles} affected vehicles`}
        />

        <MetricCard
          label="Approved Exposure"
          value={formatInr(warning.approved_exposure_inr)}
          detail={`Claim exposure ${formatInr(warning.claim_exposure_inr)}`}
        />
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <MetricCard label="Machines" value={String(warning.affected_machines)} />

        <MetricCard label="Batches" value={String(warning.affected_batches)} />

        <MetricCard label="Supplier Lots" value={String(warning.affected_supplier_lots)} />

        <MetricCard label="Models" value={String(warning.affected_models)} />

        <MetricCard label="Cities" value={String(warning.affected_cities)} />

        <MetricCard
          label="Exact Coverage"
          value={formatPercent(warning.exact_window_lineage_coverage)}
        />
      </div>
    </Panel>
  );
}

function ExactLineagePanel({ warning }: { warning: WarrantyQualityWarning }) {
  return (
    <Panel
      title="Exact Production Lineage"
      subtitle="Field issue → representative machine → production batch → supplier lot, aligned to the persisted causal-run window."
    >
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard label="Field Lineages" value={String(warning.field_lineages)} />

        <MetricCard label="Exact Window" value={String(warning.exact_window_lineages)} />

        <MetricCard label="Exact Machines" value={String(warning.exact_lineage_machines)} />

        <MetricCard label="Coverage" value={formatPercent(warning.exact_window_lineage_coverage)} />
      </div>

      {warning.exact_lineages.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-6 text-center text-xs text-muted-foreground">
          No exact production lineage records were returned for this warning.
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[650px] text-left text-xs">
              <thead>
                <tr className="border-b border-white/10 text-[10px] uppercase tracking-widest text-muted-foreground">
                  <th className="pb-3 pr-4 font-medium">Machine</th>

                  <th className="pb-3 pr-4 font-medium">Production Batch</th>

                  <th className="pb-3 font-medium">Supplier Lot</th>
                </tr>
              </thead>

              <tbody>
                {warning.exact_lineages.slice(0, 10).map((lineage, index) => (
                  <tr
                    key={`${lineage.machine_id}-${lineage.production_batch_id}-${lineage.supplier_lot_id}-${index}`}
                    className="border-b border-white/5 last:border-0"
                  >
                    <td className="py-3 pr-4 font-medium">{lineage.machine_id}</td>

                    <td className="py-3 pr-4 text-muted-foreground">
                      {lineage.production_batch_id}
                    </td>

                    <td className="py-3 text-muted-foreground">{lineage.supplier_lot_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {warning.exact_lineages.length > 10 && (
            <div className="mt-3 text-[10px] text-muted-foreground">
              Showing 10 of {warning.exact_lineages.length} exact lineage records.
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

function CausalSupportTable({ warning }: { warning: WarrantyQualityWarning }) {
  return (
    <Panel
      title="Lineage-Aligned Causal Candidate Support"
      subtitle="Persisted stable PCMCI candidates with machine overlap on exact affected production lineage."
    >
      {warning.causal_paths.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-6 text-center text-xs text-muted-foreground">
          No lineage-aligned stable causal candidates were returned for this warning.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] text-left text-xs">
            <thead>
              <tr className="border-b border-white/10 text-[10px] uppercase tracking-widest text-muted-foreground">
                <th className="pb-3 pr-4 font-medium">Evidence Type</th>

                <th className="pb-3 pr-4 font-medium">Candidate</th>

                <th className="pb-3 pr-4 font-medium">Sign</th>

                <th className="pb-3 pr-4 font-medium">Lag</th>

                <th className="pb-3 pr-4 font-medium">Mean |Score|</th>

                <th className="pb-3 pr-4 font-medium">Best q</th>

                <th className="pb-3 pr-4 font-medium">Recurrence</th>

                <th className="pb-3 pr-4 font-medium">Machine Support</th>

                <th className="pb-3 font-medium">Exact-Lineage Overlap</th>
              </tr>
            </thead>

            <tbody>
              {warning.causal_paths.map((path, index) => (
                <tr
                  key={`${path.source_metric}-${path.target_metric}-${path.observed_lags.join("-")}-${index}`}
                  className="border-b border-white/5 align-top last:border-0"
                >
                  <td className="py-3 pr-4">
                    <span
                      className={
                        path.causal_domain === "telematics"
                          ? "rounded-full border border-cyan-400/30 bg-cyan-400/10 px-2 py-1 text-[10px] font-medium text-cyan-200"
                          : "rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-1 text-[10px] font-medium text-amber-200"
                      }
                    >
                      {path.causal_domain === "telematics"
                        ? "Telematics causal"
                        : "Manufacturing causal"}
                    </span>

                    <div className="mt-1 text-[10px] text-muted-foreground">
                      {path.provenance ?? "manufacturing_causal_run"}
                    </div>
                  </td>

                  <td className="py-3 pr-4">
                    <div className="font-medium">{humanize(path.source_metric)}</div>

                    <div className="mt-0.5 text-[10px] text-muted-foreground">→</div>

                    <div className="mt-0.5 font-medium">{humanize(path.target_metric)}</div>

                    <div className="mt-1 text-[10px] text-muted-foreground">
                      Scope: {path.scope}
                    </div>
                  </td>

                  <td className="py-3 pr-4">{path.consensus_sign}</td>

                  <td className="py-3 pr-4">
                    {path.observed_lag_minutes?.length
                      ? path.observed_lag_minutes.join(", ") + " min"
                      : path.observed_lags.length
                        ? path.observed_lags.join(", ")
                        : "—"}
                  </td>

                  <td className="py-3 pr-4">{formatScore(path.mean_abs_score)}</td>

                  <td className="py-3 pr-4">{formatQValue(path.best_q_value)}</td>

                  <td className="py-3 pr-4">
                    <div>
                      {path.causal_domain === "telematics"
                        ? String(path.recurring_vehicles ?? 0) +
                          "/" +
                          String(path.eligible_vehicles ?? 0) +
                          " vehicles"
                        : String(path.recurring_machines) +
                          "/" +
                          String(path.eligible_machines) +
                          " machines"}
                    </div>

                    <div className="mt-0.5 text-[10px] text-muted-foreground">
                      {formatPercent(path.recurrence_fraction)}
                    </div>
                  </td>

                  <td className="py-3 pr-4">
                    {path.causal_domain === "telematics" ? (
                      <>
                        <div>{path.overlap_vehicle_count ?? 0} supported vehicles</div>

                        <div className="mt-0.5 text-[10px] text-muted-foreground">
                          {formatPercent(path.causal_edge_vehicle_fraction ?? 0)} of persisted edge
                          support
                        </div>
                      </>
                    ) : (
                      <>
                        <div>{path.overlap_count} overlapping machines</div>

                        <div className="mt-0.5 text-[10px] text-muted-foreground">
                          {formatPercent(path.causal_edge_machine_fraction)} of candidate machines
                        </div>
                      </>
                    )}
                  </td>

                  <td className="py-3">
                    {path.causal_domain === "telematics" ? (
                      <span className="text-muted-foreground">
                        Vehicle support above; lineage gate shown separately
                      </span>
                    ) : (
                      <>
                        <div>{path.exact_lineage_count} lineages</div>

                        <div className="mt-0.5 text-[10px] text-muted-foreground">
                          {formatPercent(path.exact_lineage_fraction)} lineage support
                        </div>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function HotspotPanels({ warning }: { warning: WarrantyQualityWarning }) {
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
      <Panel
        title="Supplier Hotspots"
        subtitle="Warranty exposure grouped by supplier and component."
      >
        {warning.supplier_hotspots.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 p-5 text-center text-xs text-muted-foreground">
            No supplier hotspot records returned.
          </div>
        ) : (
          <div className="space-y-2">
            {warning.supplier_hotspots.slice(0, 6).map((hotspot) => (
              <div
                key={`${hotspot.supplier_id}-${hotspot.component_category}`}
                className="rounded-xl border border-white/10 bg-white/[0.025] p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Package className="h-3.5 w-3.5 shrink-0 text-primary" />

                      <span className="truncate text-xs font-semibold">
                        {hotspot.supplier_name}
                      </span>
                    </div>

                    <div className="mt-1 text-[10px] text-muted-foreground">
                      {hotspot.component_category} · {hotspot.supplier_id}
                    </div>
                  </div>

                  <div className="text-right">
                    <div className="text-xs font-semibold">
                      {formatInr(hotspot.approved_exposure_inr)}
                    </div>

                    <div className="text-[10px] text-muted-foreground">approved exposure</div>
                  </div>
                </div>

                <div className="mt-3 flex gap-4 text-[10px] text-muted-foreground">
                  <span>{hotspot.claims} claims</span>

                  <span>{hotspot.supplier_lots} lots</span>

                  <span>{hotspot.batches} batches</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel
        title="Market Hotspots"
        subtitle="Warranty exposure grouped by model, variant and geography."
      >
        {warning.market_hotspots.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 p-5 text-center text-xs text-muted-foreground">
            No market hotspot records returned.
          </div>
        ) : (
          <div className="space-y-2">
            {warning.market_hotspots.slice(0, 6).map((hotspot, index) => (
              <div
                key={`${hotspot.vehicle_model_name}-${hotspot.variant}-${hotspot.city_name}-${index}`}
                className="rounded-xl border border-white/10 bg-white/[0.025] p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <MapPin className="h-3.5 w-3.5 shrink-0 text-primary" />

                      <span className="truncate text-xs font-semibold">
                        {hotspot.city_name}, {hotspot.region_name}
                      </span>
                    </div>

                    <div className="mt-1 text-[10px] text-muted-foreground">
                      {hotspot.vehicle_model_name} · {hotspot.variant}
                    </div>
                  </div>

                  <div className="text-right">
                    <div className="text-xs font-semibold">
                      {formatInr(hotspot.approved_exposure_inr)}
                    </div>

                    <div className="text-[10px] text-muted-foreground">approved exposure</div>
                  </div>
                </div>

                <div className="mt-3 flex gap-4 text-[10px] text-muted-foreground">
                  <span>{hotspot.claims} claims</span>

                  <span>{hotspot.batches} batches</span>

                  <span>{hotspot.supplier_lots} lots</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

function CalibrationPanel({
  complaintsP50,
  complaintsP75,
  complaintsP90,
  claimsP50,
  claimsP75,
  claimsP90,
  evidenceP50,
  evidenceP75,
  evidenceP90,
}: {
  complaintsP50: number;
  complaintsP75: number;
  complaintsP90: number;
  claimsP50: number;
  claimsP75: number;
  claimsP90: number;
  evidenceP50: number;
  evidenceP75: number;
  evidenceP90: number;
}) {
  return (
    <Panel
      title="Empirical Calibration Baseline"
      subtitle="Observed issue-category distribution used by warning prioritization. These values are calibration statistics, not model confidence."
    >
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-xl border border-white/10 bg-white/[0.025] p-4">
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
            Complaints
          </div>

          <div className="mt-3 grid grid-cols-3 gap-3">
            <MetricCard label="P50" value={complaintsP50.toFixed(1)} />

            <MetricCard label="P75" value={complaintsP75.toFixed(1)} />

            <MetricCard label="P90" value={complaintsP90.toFixed(1)} />
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.025] p-4">
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
            Warranty Claims
          </div>

          <div className="mt-3 grid grid-cols-3 gap-3">
            <MetricCard label="P50" value={claimsP50.toFixed(1)} />

            <MetricCard label="P75" value={claimsP75.toFixed(1)} />

            <MetricCard label="P90" value={claimsP90.toFixed(1)} />
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.025] p-4">
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
            Evidence Index
          </div>

          <div className="mt-3 grid grid-cols-3 gap-3">
            <MetricCard label="P50" value={evidenceP50.toFixed(1)} />

            <MetricCard label="P75" value={evidenceP75.toFixed(1)} />

            <MetricCard label="P90" value={evidenceP90.toFixed(1)} />
          </div>
        </div>
      </div>
    </Panel>
  );
}

function statusTone(status: string): "success" | "warning" | "danger" | "info" | "default" {
  if (status === "READY" || status === "REUSED" || status === "AVAILABLE" || status === "RUNNING")
    return "success";
  if (status === "NOT_READY" || status === "PAUSED") return "warning";
  if (status === "ERROR") return "danger";
  return "info";
}

function CausalStatusPanel({ status }: { status?: WarrantyQualityCausalStatus }) {
  if (!status) {
    return (
      <Panel
        title="Causal replay status"
        subtitle="Waiting for the persistent replay clock and scheduler status."
      >
        <div className="text-xs text-muted-foreground">
          Status is read-only; the browser does not start causal analysis.
        </div>
      </Panel>
    );
  }

  const deltaLabel = (domain: "manufacturing" | "telematics") => {
    const delta = status[domain].graph_delta;
    if (delta.new_edges === 0 && delta.removed_edges === 0) return "No structural change";
    return `+${delta.new_edges} new / -${delta.removed_edges} removed`;
  };

  const ingestionByDomain = new Map(status.ingestion.map((item) => [item.domain, item]));
  const lifecycleSummary = Object.entries(status.warning.lifecycle_counts ?? {})
    .map(([state, count]) => `${count} ${state.toLowerCase()}`)
    .join(" · ");
  const ingestorProblem = status.ingestion.find((item) => item.last_error);
  const pendingDomains = (["manufacturing", "telematics"] as const).filter(
    (domain) => status[domain].pending_refresh,
  );

  return (
    <Panel
      title="Live pipeline status"
      subtitle="Simulation time, data freshness and model freshness are deliberately separate readings."
    >
      <div className="rounded-xl border border-white/10 bg-white/[0.025] p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
            Simulation clock
          </span>
          <StatPill tone={statusTone(status.simulation.status)}>
            {status.simulation.status}
          </StatPill>
        </div>
        <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className="text-sm font-semibold">
            {formatIstDateTime(status.simulation.simulation_as_of)}
          </span>
          <span className="text-[11px] text-muted-foreground">
            {status.simulation.replay_speed} simulated min / real min · tick{" "}
            {status.simulation.tick_count}
          </span>
          <span className="text-[10px] text-muted-foreground">
            Last tick {formatIstDateTime(status.simulation.last_tick_at)}
          </span>
        </div>
      </div>

      <SectionLabel>Data freshness · physically ingested rows</SectionLabel>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {(["manufacturing", "telematics"] as const).map((domain) => {
          const ingestion = ingestionByDomain.get(domain);
          return (
            <div key={domain} className="rounded-xl border border-white/10 bg-white/[0.025] p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  {domain}
                </span>
                <StatPill tone={statusTone(ingestion?.status ?? "NOT_READY")}>
                  {ingestion?.status ?? "NOT_READY"}
                </StatPill>
              </div>
              <div className="mt-2 text-sm font-semibold">
                {formatIstDateTime(ingestion?.runtime_max_timestamp)}
              </div>
              <div className="mt-1 text-[11px] text-muted-foreground">
                Latest physically inserted timestamp
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted-foreground">
                <span>{(ingestion?.last_ingested_rows ?? 0).toLocaleString()} rows this tick</span>
                <span>
                  {(ingestion?.runtime_row_count ?? 0).toLocaleString()} rows in runtime table
                </span>
                <span>
                  {(ingestion?.rows_ingested_total ?? 0).toLocaleString()} ingested since cutover
                </span>
              </div>
              <div className="mt-1 text-[10px] text-muted-foreground">
                Replay cursor {formatIstDateTime(ingestion?.replay_cursor)} · source ends{" "}
                {formatIstDateTime(ingestion?.source_available_to)}
              </div>
              {ingestion?.status === "SOURCE_EXHAUSTED" ? (
                <div className="mt-1 text-[10px] text-amber-200/80">
                  This domain&apos;s immutable source is fully replayed; no further rows are due.
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      <SectionLabel>Model freshness · persisted causal runs</SectionLabel>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {(["manufacturing", "telematics"] as const).map((domain) => {
          const run = status[domain];
          return (
            <div key={domain} className="rounded-xl border border-white/10 bg-white/[0.025] p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  {domain} causal model
                </span>
                <StatPill tone={statusTone(run.status)}>{run.status}</StatPill>
              </div>
              <div className="mt-2 font-mono text-sm font-semibold">
                {run.run_id ? run.run_id.slice(0, 8) : "Not ready"}
              </div>
              <div className="mt-1 text-[11px] text-muted-foreground">
                {run.stable_edge_count ?? "—"} stable edges · {deltaLabel(domain)}
              </div>
              <div className="mt-1 text-[10px] text-muted-foreground">
                Source window {formatIstDateTime(run.source_from)} → {formatIstDateTime(run.source_to)}
              </div>
              <div className="mt-1 text-[10px] text-muted-foreground">
                Computed {run.model_freshness ? formatIstDateTime(run.model_freshness) : "not computed"}
                {run.last_runtime_seconds != null
                  ? ` · ${run.last_runtime_seconds.toFixed(1)}s`
                  : ""}
              </div>
              {run.last_error ? (
                <div className="mt-1 text-[10px] text-amber-200/80">
                  Last refresh error — previous completed run is still being served.
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      <SectionLabel>Warning freshness · scheduler and ingestor</SectionLabel>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-white/10 bg-white/[0.025] p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
              Warning evaluation
            </span>
            <StatPill tone={statusTone(status.warning.status)}>{status.warning.status}</StatPill>
          </div>
          <div className="mt-2 text-sm font-semibold">
            {status.warning.warning_count} current warnings
          </div>
          <div className="mt-1 text-[11px] text-muted-foreground">
            {lifecycleSummary || "no lifecycle transitions recorded"}
          </div>
          <div className="mt-1 text-[10px] text-muted-foreground">
            Evaluated {formatIstDateTime(status.warning.last_evaluated_at)} · version{" "}
            <span className="font-mono">
              {status.warning.evaluation_signature
                ? status.warning.evaluation_signature.slice(0, 12)
                : "—"}
            </span>
          </div>
          <div className="mt-1 text-[10px] text-muted-foreground">
            Field evidence version{" "}
            <span className="font-mono">
              {status.warning.field_evidence_signature
                ? status.warning.field_evidence_signature.slice(0, 12)
                : "—"}
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.025] p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
              Scheduler / ingestor
            </span>
            <StatPill tone={statusTone(status.scheduler.status)}>
              {status.scheduler.status}
            </StatPill>
          </div>
          <div className="mt-2 text-sm font-semibold">
            {pendingDomains.length
              ? `Coalesced refresh pending: ${pendingDomains.join(", ")}`
              : "No pending refresh"}
          </div>
          <div className="mt-1 text-[11px] text-muted-foreground">
            Last causal refresh{" "}
            {status.scheduler.last_refresh_at
              ? formatIstDateTime(status.scheduler.last_refresh_at)
              : "not run"}
          </div>
          <div className="mt-1 text-[10px] text-muted-foreground">
            {ingestorProblem
              ? `Last ingestion error (${ingestorProblem.domain}): ${ingestorProblem.last_error}`
              : "No ingestion error"}
          </div>
        </div>
      </div>
    </Panel>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 mt-4 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
      {children}
    </div>
  );
}

function WarrantyQualityEarlyWarningPage() {
  const statusQuery = useWarrantyQualityCausalStatus();
  const status = statusQuery.data;

  // The warning-evaluation run id/signature is the primary snapshot
  // identity; the manufacturing and telematics causal run ids and the field
  // evidence signature are folded in too so a change in any one of them
  // (not just a new evaluation row) is enough to pull a fresh snapshot. This
  // string IS the early-warnings query key, so a version the client has not
  // seen triggers its own fetch — no manual invalidateQueries bookkeeping.
  const evaluationVersion = status
    ? [
        status.warning.evaluation_run_id ?? status.warning.evaluation_signature ?? "no-eval",
        status.warning.field_evidence_signature ?? "no-evidence",
        status.manufacturing.run_id ?? "no-mfg",
        status.telematics.run_id ?? "no-tel",
      ].join(":")
    : undefined;

  const query = useWarrantyQualityEarlyWarnings(evaluationVersion);

  const [selectedIssueCategory, setSelectedIssueCategory] = useState<string | null>(null);

  if (query.isPending) {
    return (
      <div className="space-y-6">
        <SectionTitle
          title="Warranty & Quality Early-Warning Graph"
          subtitle="Trace field issues to exact production lineage and inspect persisted causal candidates."
        />
        <CausalStatusPanel status={statusQuery.data} />
        <LoadingState />
      </div>
    );
  }

  if (query.isError) {
    return <ErrorState error={query.error} status={statusQuery.data} />;
  }

  const data = query.data;

  if (!data || data.warnings.length === 0) {
    return <EmptyState runId={data?.causal_run_id ?? "unknown"} status={statusQuery.data} />;
  }

  const selectedWarning =
    data.warnings.find((warning) => warning.issue_category === selectedIssueCategory) ??
    data.warnings[0];

  // Forces a full remount of the causal graph whenever the selected warning,
  // OR the evidence backing it, changes — so no node position, drag state,
  // selected node/edge, or inspector selection from a previous warning (or a
  // previous run of the SAME warning) can ever leak into the next render.
  const graphKey = [
    selectedWarning.issue_category,
    data.manufacturing_causal_run_id ?? data.causal_run_id ?? "no-mfg",
    data.telematics_causal_run_id ?? "no-tel",
    evaluationVersion ?? "no-version",
  ].join("::");

  const criticalCount = data.warnings.filter((warning) => warning.priority === "CRITICAL").length;

  const highCount = data.warnings.filter((warning) => warning.priority === "HIGH").length;

  const totalApprovedExposure = data.warnings.reduce(
    (sum, warning) => sum + warning.approved_exposure_inr,

    0,
  );

  const totalCausalPaths = data.warnings.reduce(
    (sum, warning) => sum + warning.causal_paths.length,

    0,
  );

  const exactIssueCoverage =
    data.issue_categories_evaluated > 0
      ? data.issue_categories_with_exact_lineage / data.issue_categories_evaluated
      : 0;

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Warranty & Quality Early-Warning Graph"
        subtitle="Trace field issues to exact production lineage and inspect persisted manufacturing and telematics causal candidates with explicit evidence provenance."
        right={
          <div className="flex flex-wrap gap-2">
            <StatPill tone="info">Manufacturing {data.causal_run_id.slice(0, 8)}</StatPill>

            {data.telematics_causal_run_id ? (
              <StatPill tone="info">
                Telematics {data.telematics_causal_run_id.slice(0, 8)}
              </StatPill>
            ) : null}

            <StatPill>{data.warnings_generated} warnings</StatPill>
          </div>
        }
      />

      <CausalStatusPanel status={statusQuery.data} />

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-6">
        <MetricCard
          label="Warnings"
          value={String(data.warnings_generated)}
          detail={`${data.issue_categories_evaluated} issue categories evaluated`}
        />

        <MetricCard
          label="Critical"
          value={String(criticalCount)}
          detail={`${highCount} high-priority warnings`}
        />

        <MetricCard
          label="Exact-Lineage Issues"
          value={String(data.issue_categories_with_exact_lineage)}
          detail={`${formatPercent(exactIssueCoverage)} of evaluated categories`}
        />

        <MetricCard
          label="Candidate Paths"
          value={String(totalCausalPaths)}
          detail="Across generated warnings"
        />

        <MetricCard
          label="Approved Exposure"
          value={formatInr(totalApprovedExposure)}
          detail="Across warning records"
        />

        <MetricCard
          label="Calibration Issues"
          value={String(data.calibration.issue_categories)}
          detail="Empirical prioritization baseline"
        />
      </div>

      <Panel>
        <div className="grid grid-cols-1 gap-4 text-xs md:grid-cols-3">
          <div className="flex items-start gap-3">
            <Database className="mt-0.5 h-4 w-4 shrink-0 text-primary" />

            <div>
              <div className="font-semibold">Causal run lineage</div>

              <div className="mt-1 break-all text-[10px] leading-5 text-muted-foreground">
                {data.causal_signature}
              </div>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <Clock className="mt-0.5 h-4 w-4 shrink-0 text-primary" />

            <div>
              <div className="font-semibold">Observation window</div>

              <div className="mt-1 text-[10px] leading-5 text-muted-foreground">
                {formatIstDateTime(data.source_from)}
                <br />
                to {formatIstDateTime(data.source_to)}
              </div>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <Factory className="mt-0.5 h-4 w-4 shrink-0 text-primary" />

            <div>
              <div className="font-semibold">Evidence interpretation</div>

              <div className="mt-1 text-[10px] leading-5 text-muted-foreground">
                Exact lineage confirms traceability and window alignment. PCMCI edges are stable
                statistical causal candidates, not proof that a metric caused a field issue.
              </div>
            </div>
          </div>
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_310px]">
        <div className="space-y-6">
          <WarrantyQualityCausalGraph
            key={graphKey}
            warning={selectedWarning}
            manufacturingRunId={data.manufacturing_causal_run_id ?? data.causal_run_id}
            telematicsRunId={data.telematics_causal_run_id}
            simulationAsOf={statusQuery.data?.simulation.simulation_as_of}
            generatedAt={data.generated_at}
          />

          <WarningEvidence warning={selectedWarning} />
        </div>

        <WarningList
          warnings={data.warnings}
          active={selectedWarning}
          onSelect={setSelectedIssueCategory}
        />
      </div>

      <ExactLineagePanel warning={selectedWarning} />

      <CausalSupportTable warning={selectedWarning} />

      <HotspotPanels warning={selectedWarning} />

      <CalibrationPanel
        complaintsP50={data.calibration.complaints_p50}
        complaintsP75={data.calibration.complaints_p75}
        complaintsP90={data.calibration.complaints_p90}
        claimsP50={data.calibration.claims_p50}
        claimsP75={data.calibration.claims_p75}
        claimsP90={data.calibration.claims_p90}
        evidenceP50={data.calibration.evidence_score_p50}
        evidenceP75={data.calibration.evidence_score_p75}
        evidenceP90={data.calibration.evidence_score_p90}
      />

      <div className="glass-strong rounded-2xl p-4 text-xs leading-5">
        <span className="font-semibold text-primary">Evidence semantics: </span>
        The screen presents lineage-aligned causal candidate support. Exact manufacturing lineage
        establishes traceability to affected production, while PCMCI identifies statistically
        discovered stable causal candidates on machines from that lineage. Evidence score, q-value,
        recurrence and machine support must not be interpreted as causal probability or proof of
        root cause.
      </div>
    </div>
  );
}
