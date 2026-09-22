import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Panel, SectionTitle, StatPill } from "@/components/ui/panel";
import {
  useApproveShipment,
  useAutoHeal,
  useLogisticsRoutes,
  useModifyShipment,
  usePredictDelay,
  useReroute,
  useReviewShipment,
  useRouteShipments,
  useRouteSlaReport,
  useShipmentLedger,
  useWarehouseSignals,
} from "@/hooks/use-api";
import type {
  LogisticsAction,
  LogisticsRoute,
  LogisticsShipment,
  ReviewerRole,
} from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Wand2,
  ShieldAlert,
  Route as RouteIcon,
  FileText,
  Check,
  UserCog,
  FileSearch,
  Pencil,
  Loader2,
  PackageSearch,
} from "lucide-react";

export const Route = createFileRoute("/logistics")({
  head: () => ({ meta: [{ title: "Logistics AI Control Tower · Mahindra AI Command Center" }] }),
  component: Logistics,
});

const REVIEWER_ROLES: ReviewerRole[] = [
  "Business Owner",
  "Domain Expert",
  "Risk Reviewer",
  "Compliance Reviewer",
  "Quality Reviewer",
];

const STATUS_TABS: { value: "all" | "Pending" | "Escalated" | "Approved"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "Pending", label: "Pending" },
  { value: "Escalated", label: "Escalated" },
  { value: "Approved", label: "Approved" },
];

function priorityTone(priority: string): "success" | "warning" | "danger" | "info" {
  if (priority === "Critical") return "danger";
  if (priority === "High") return "warning";
  if (priority === "Medium") return "info";
  return "success"; // Low
}

function statusTone(status: string): "success" | "warning" | "danger" | "default" | "info" {
  if (status === "Approved") return "success";
  if (status === "Escalated") return "warning";
  return "info"; // Pending
}

function complianceTone(flag: string): "success" | "warning" | "danger" | "default" {
  if (flag === "Passed") return "success";
  if (flag === "Review Required") return "warning";
  if (flag === "Failed") return "danger";
  return "default";
}

function signalTone(tone: string): "success" | "warning" | "danger" {
  if (tone === "danger") return "danger";
  if (tone === "warning") return "warning";
  return "success";
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

/** A shipment is only actionable from this screen while it's still live
 * and undecided — an immutable canonical (Synthetic Data Factory)
 * decision, or a shipment already approved, can't be re-decided here
 * (see app/services/operational_logistics.py). */
function isActionable(s: LogisticsShipment): boolean {
  return s.governance_track === "live" && s.decision_status !== "Approved";
}

function Logistics() {
  const routes = useLogisticsRoutes();
  const signals = useWarehouseSignals();
  const predictDelay = usePredictDelay();
  const reroute = useReroute();
  const autoHeal = useAutoHeal();

  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_TABS)[number]["value"]>("all");
  const [search, setSearch] = useState("");
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { Pending: 0, Escalated: 0, Approved: 0 };
    for (const r of routes) counts[r.status] = (counts[r.status] ?? 0) + 1;
    return counts;
  }, [routes]);
  const filteredRoutes = useMemo(
    () =>
      routes.filter(
        (r) =>
          (statusFilter === "all" || r.status === statusFilter) &&
          r.name.toLowerCase().includes(search.trim().toLowerCase()),
      ),
    [routes, statusFilter, search],
  );

  const [infoDetail, setInfoDetail] = useState<{ title: string; detail: string } | null>(null);
  const [healResult, setHealResult] = useState<{
    route: LogisticsRoute;
    steps: string[];
    approved: number;
    already: number;
  } | null>(null);
  const [slaTarget, setSlaTarget] = useState<LogisticsRoute | null>(null);
  const [shipmentsTarget, setShipmentsTarget] = useState<LogisticsRoute | null>(null);
  const [ledgerTarget, setLedgerTarget] = useState<LogisticsShipment | null>(null);
  const [modifyTarget, setModifyTarget] = useState<LogisticsShipment | null>(null);
  const [modifyAction, setModifyAction] = useState<LogisticsAction>("MAINTAIN");
  const [modifyRouteId, setModifyRouteId] = useState<string>("");
  const [modifyReason, setModifyReason] = useState("");
  const [reviewTarget, setReviewTarget] = useState<LogisticsShipment | null>(null);
  const [reviewerRole, setReviewerRole] = useState<ReviewerRole>("Risk Reviewer");
  const [reviewReason, setReviewReason] = useState("");

  const slaReport = useRouteSlaReport(slaTarget?.id, !!slaTarget);
  const shipments = useRouteShipments(shipmentsTarget?.id, !!shipmentsTarget);
  const ledger = useShipmentLedger(ledgerTarget?.shipment_id);
  const approveShipment = useApproveShipment();
  const modifyShipment = useModifyShipment();
  const reviewShipment = useReviewShipment();

  const handlePredictDelay = (r: LogisticsRoute) => {
    predictDelay.mutate(r.id, {
      onSuccess: (updated) =>
        toast.success(
          `${r.name} · SLA risk ${updated.slaRisk}%, delay prob. ${updated.delayProb}%`,
        ),
      onError: (error) => toast.error(errorMessage(error, `${r.name} could not be re-scored`)),
    });
  };

  const handleReroute = (r: LogisticsRoute) => {
    reroute.mutate(r.id, {
      onSuccess: (updated) => toast.success(`${r.name} · ${updated.action}`),
      onError: (error) => toast.error(errorMessage(error, `${r.name} reroute preview failed`)),
    });
  };

  const handleAutoHeal = (r: LogisticsRoute) => {
    autoHeal.mutate(r.id, {
      onSuccess: (result) =>
        setHealResult({
          route: result.route,
          steps: result.steps,
          approved: result.approved_shipments,
          already: result.already_decided_shipments,
        }),
      onError: (error) => toast.error(errorMessage(error, `${r.name} auto-heal failed`)),
    });
  };

  const handleApprove = (s: LogisticsShipment) => {
    approveShipment.mutate(s.shipment_id, {
      onSuccess: () => toast.success(`${s.shipment_id} · Approved`),
      onError: (error) =>
        toast.error(errorMessage(error, `${s.shipment_id} could not be approved`)),
    });
  };

  const handleModifySubmit = () => {
    const target = modifyTarget;
    if (!target) return;
    if (modifyAction === "REROUTE" && !modifyRouteId) {
      toast.error("Pick a target route for the reroute override.");
      return;
    }
    modifyShipment.mutate(
      {
        shipmentId: target.shipment_id,
        action: modifyAction,
        routeId: modifyAction === "REROUTE" ? modifyRouteId : null,
        reason: modifyReason,
      },
      {
        onSuccess: () => {
          toast.success(`${target.shipment_id} · action updated`);
          setModifyTarget(null);
          setModifyReason("");
        },
        onError: (error) =>
          toast.error(errorMessage(error, `${target.shipment_id}'s action could not be updated`)),
      },
    );
  };

  const handleReviewSubmit = () => {
    const target = reviewTarget;
    if (!target) return;
    reviewShipment.mutate(
      { shipmentId: target.shipment_id, reviewerRole, reason: reviewReason },
      {
        onSuccess: () => {
          toast(`${target.shipment_id} sent to human review`);
          setReviewTarget(null);
          setReviewReason("");
        },
        onError: (error) =>
          toast.error(errorMessage(error, `${target.shipment_id} could not be sent to review`)),
      },
    );
  };

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Logistics AI Control Tower"
        subtitle="Predictive + causal logistics monitoring with auto-heal workflows."
      />

      <Panel title={`Freight Routes (${routes.length})`}>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setStatusFilter(tab.value)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                statusFilter === tab.value
                  ? "border-primary/50 bg-primary/15 text-foreground"
                  : "border-white/10 bg-white/[0.03] text-muted-foreground hover:border-white/20 hover:text-foreground"
              }`}
            >
              {tab.label}
              {tab.value !== "all" ? (
                <span className="opacity-70"> {statusCounts[tab.value] ?? 0}</span>
              ) : null}
            </button>
          ))}
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search route name…"
            className="ml-auto w-48 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs outline-none focus:border-primary/40"
          />
        </div>

        {routes.length === 0 ? (
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-muted-foreground">
            Loading routes…
          </div>
        ) : filteredRoutes.length === 0 ? (
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-muted-foreground">
            No routes match this filter.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {filteredRoutes.map((r) => (
              <div key={r.id} className="glass rounded-2xl p-4 hover:border-primary/30">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                      Route
                    </div>
                    <div className="text-sm font-semibold">{r.name}</div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() =>
                        setInfoDetail({ title: `Priority · ${r.name}`, detail: r.priority_reason })
                      }
                      className="cursor-pointer"
                    >
                      <StatPill tone={priorityTone(r.priority)}>{r.priority}</StatPill>
                    </div>
                    <StatPill tone={statusTone(r.status)}>{r.status}</StatPill>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                  <div className="rounded-md bg-white/5 p-2">
                    <div className="text-muted-foreground">SLA risk</div>
                    <div className="font-semibold">{r.slaRisk}%</div>
                  </div>
                  <div className="rounded-md bg-white/5 p-2">
                    <div className="text-muted-foreground">Delay prob.</div>
                    <div className="font-semibold">{r.delayProb}%</div>
                  </div>
                  <div className="rounded-md bg-white/5 p-2">
                    <div className="text-muted-foreground">Cost</div>
                    <div className="font-semibold">{r.cost}</div>
                  </div>
                </div>
                <div className="mt-2 rounded-md bg-white/5 p-2 text-xs">
                  <div className="text-muted-foreground">Recommendation</div>
                  <div className="font-semibold truncate">{r.action}</div>
                </div>
                <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>{r.active_shipments} active shipments</span>
                  <span>{r.at_risk_shipments} at risk</span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={predictDelay.isPending}
                    onClick={() => handlePredictDelay(r)}
                    className="gap-1 border-white/10"
                  >
                    <ShieldAlert className="h-3.5 w-3.5" /> Predict Delay
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={reroute.isPending}
                    onClick={() => handleReroute(r)}
                    className="gap-1 border-white/10"
                  >
                    <RouteIcon className="h-3.5 w-3.5" /> Recommend Reroute
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setShipmentsTarget(r)}
                    className="gap-1 border-white/10"
                  >
                    <PackageSearch className="h-3.5 w-3.5" /> Shipments
                  </Button>
                  <Button
                    size="sm"
                    disabled={autoHeal.isPending}
                    onClick={() => handleAutoHeal(r)}
                    className="gap-1 mahindra-gradient text-white"
                  >
                    {autoHeal.isPending ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Wand2 className="h-3.5 w-3.5" />
                    )}
                    Auto-Heal
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setSlaTarget(r)}
                    className="gap-1 border-white/10"
                  >
                    <FileText className="h-3.5 w-3.5" /> SLA Report
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Warehouse Signals">
        {signals.length === 0 ? (
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-muted-foreground">
            Loading warehouse signals…
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            {signals.map((m, i) => (
              <div
                key={`${m.label}-${i}`}
                role="button"
                tabIndex={0}
                onClick={() =>
                  setInfoDetail({
                    title: m.label,
                    detail: `${m.threshold}${
                      m.affected_routes.length ? ` — affects: ${m.affected_routes.join(", ")}` : ""
                    }`,
                  })
                }
                className="cursor-pointer rounded-lg border border-white/10 bg-white/[0.03] p-3 transition-colors hover:border-primary/40 hover:bg-white/[0.05]"
              >
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  {m.label}
                </div>
                <div className="mt-1 flex items-center justify-between">
                  <span className="text-sm font-semibold">{m.value}</span>
                  <StatPill tone={signalTone(m.tone)}>
                    {m.tone === "success" ? "OK" : m.tone === "warning" ? "Watch" : "Alert"}
                  </StatPill>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <div className="glass-strong rounded-2xl p-4 text-xs">
        <span className="font-semibold text-primary">AI Differentiator: </span>
        Predictive + causal logistics monitoring with auto-heal workflows and approval-gated
        execution.
      </div>

      {/* Info / priority / signal explanation dialog */}
      <Dialog open={!!infoDetail} onOpenChange={(o) => !o && setInfoDetail(null)}>
        <DialogContent className="max-w-md border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">{infoDetail?.title}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">{infoDetail?.detail}</p>
        </DialogContent>
      </Dialog>

      {/* Auto-heal result dialog */}
      <Dialog open={!!healResult} onOpenChange={(o) => !o && setHealResult(null)}>
        <DialogContent className="max-w-lg border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">
              Auto-Heal Result · {healResult?.route.name}
            </DialogTitle>
          </DialogHeader>
          <div className="mb-3 flex gap-4 text-xs">
            <StatPill tone="success">{healResult?.approved ?? 0} newly approved</StatPill>
            <StatPill tone="default">{healResult?.already ?? 0} already decided</StatPill>
          </div>
          <ol className="space-y-2 text-sm">
            {(healResult?.steps ?? []).map((s, i) => (
              <li
                key={s}
                className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.03] p-3"
              >
                <span className="grid h-6 w-6 place-items-center rounded-full mahindra-gradient text-xs font-bold text-white">
                  {i + 1}
                </span>
                {s}
              </li>
            ))}
          </ol>
        </DialogContent>
      </Dialog>

      {/* SLA report dialog */}
      <Dialog open={!!slaTarget} onOpenChange={(o) => !o && setSlaTarget(null)}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">
              SLA Report · {slaTarget?.name}
            </DialogTitle>
          </DialogHeader>
          {slaReport.isLoading && (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Building report…
            </div>
          )}
          {slaReport.data && (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div className="rounded-md bg-white/5 p-2">
                  <div className="text-muted-foreground">Active</div>
                  <div className="font-semibold">{slaReport.data.active_shipments}</div>
                </div>
                <div className="rounded-md bg-white/5 p-2">
                  <div className="text-muted-foreground">On time</div>
                  <div className="font-semibold">{slaReport.data.on_time_shipments}</div>
                </div>
                <div className="rounded-md bg-white/5 p-2">
                  <div className="text-muted-foreground">At risk</div>
                  <div className="font-semibold">{slaReport.data.at_risk_shipments}</div>
                </div>
              </div>
              <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs">
                <div className="flex justify-between gap-3 py-0.5">
                  <span className="text-muted-foreground">Expected breaches</span>
                  <span>{slaReport.data.expected_breaches}</span>
                </div>
                <div className="flex justify-between gap-3 py-0.5">
                  <span className="text-muted-foreground">Average delay</span>
                  <span>{slaReport.data.average_delay_minutes} min</span>
                </div>
                <div className="flex justify-between gap-3 py-0.5">
                  <span className="text-muted-foreground">Cost exposure</span>
                  <span>₹{slaReport.data.cost_exposure_inr.toLocaleString("en-IN")}</span>
                </div>
              </div>
              <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs">
                <div className="text-muted-foreground">Recommended action</div>
                <div className="font-semibold">{slaReport.data.recommended_action}</div>
              </div>
              <div>
                <div className="mb-1 text-[11px] uppercase tracking-widest text-muted-foreground">
                  Breach drivers
                </div>
                <div className="space-y-1.5">
                  {slaReport.data.drivers.map((d) => (
                    <div
                      key={d.name}
                      className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <span>{d.name}</span>
                        <StatPill tone={d.direction === "positive" ? "danger" : "success"}>
                          {d.contribution}
                        </StatPill>
                      </div>
                      <div className="mt-1 text-muted-foreground">{d.detail}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Shipment drill-down dialog */}
      <Dialog open={!!shipmentsTarget} onOpenChange={(o) => !o && setShipmentsTarget(null)}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">
              Shipments · {shipmentsTarget?.name}
            </DialogTitle>
          </DialogHeader>
          {shipments.isLoading && (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading shipments…
            </div>
          )}
          {shipments.data && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  <tr className="border-b border-white/10">
                    <th className="pb-2 text-left">Shipment</th>
                    <th className="pb-2 text-left">Priority</th>
                    <th className="pb-2 text-left">Delay</th>
                    <th className="pb-2 text-left">Breach</th>
                    <th className="pb-2 text-left">Recommended</th>
                    <th className="pb-2 text-left">Status</th>
                    <th className="pb-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {shipments.data.map((s) => (
                    <tr
                      key={s.shipment_id}
                      className="border-b border-white/5 last:border-0 hover:bg-white/[0.03]"
                    >
                      <td className="py-2 text-xs">{s.shipment_id}</td>
                      <td className="text-xs">{s.priority}</td>
                      <td>
                        <StatPill
                          tone={
                            s.delay_probability > 60
                              ? "danger"
                              : s.delay_probability > 30
                                ? "warning"
                                : "success"
                          }
                        >
                          {s.delay_probability}%
                        </StatPill>
                      </td>
                      <td>
                        <StatPill
                          tone={
                            s.breach_probability > 40
                              ? "danger"
                              : s.breach_probability > 20
                                ? "warning"
                                : "success"
                          }
                        >
                          {s.breach_probability}%
                        </StatPill>
                      </td>
                      <td className="text-xs">
                        {s.recommended_action}
                        {s.recommended_route_label ? ` → ${s.recommended_route_label}` : ""}
                      </td>
                      <td>
                        <StatPill tone={statusTone(s.decision_status)}>
                          {s.decision_status}
                        </StatPill>
                      </td>
                      <td className="text-right">
                        <div className="inline-flex gap-1">
                          {isActionable(s) && (
                            <>
                              <button
                                title="Approve"
                                disabled={approveShipment.isPending}
                                onClick={() => handleApprove(s)}
                                className="rounded-md border border-white/10 p-1.5 hover:border-emerald-500/40 hover:bg-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-30"
                              >
                                <Check className="h-3.5 w-3.5" />
                              </button>
                              <button
                                title="Modify"
                                onClick={() => {
                                  setModifyTarget(s);
                                  setModifyAction("MAINTAIN");
                                  setModifyRouteId("");
                                  setModifyReason("");
                                }}
                                className="rounded-md border border-white/10 p-1.5 hover:border-primary/40 hover:bg-primary/10"
                              >
                                <Pencil className="h-3.5 w-3.5" />
                              </button>
                              <button
                                title="Human review"
                                onClick={() => {
                                  setReviewTarget(s);
                                  setReviewerRole("Risk Reviewer");
                                  setReviewReason("");
                                }}
                                className="rounded-md border border-white/10 p-1.5 hover:border-white/40 hover:bg-white/10"
                              >
                                <UserCog className="h-3.5 w-3.5" />
                              </button>
                            </>
                          )}
                          <button
                            title="Trust ledger"
                            onClick={() => setLedgerTarget(s)}
                            className="rounded-md border border-white/10 p-1.5 hover:border-primary/40 hover:bg-primary/10"
                          >
                            <FileSearch className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Shipment trust ledger dialog */}
      <Dialog open={!!ledgerTarget} onOpenChange={(o) => !o && setLedgerTarget(null)}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">
              Trust Ledger · {ledgerTarget?.shipment_id}
            </DialogTitle>
          </DialogHeader>
          {ledger.isLoading && (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading governance state…
            </div>
          )}
          {ledger.isError && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
              Trust ledger unavailable. Check backend logs.
            </div>
          )}
          {ledger.data && (
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <span className="font-semibold">
                  {ledger.data.track === "canonical"
                    ? "Canonical decision"
                    : ledger.data.track === "live"
                      ? "Live decision"
                      : "Not yet decided"}
                </span>
                <StatPill tone={ledger.data.approval === "Approved" ? "success" : "warning"}>
                  {ledger.data.approval}
                </StatPill>
              </div>

              <div className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <span className="font-semibold">Audit status</span>
                <StatPill tone={complianceTone(ledger.data.audit_status)}>
                  {ledger.data.audit_status}
                </StatPill>
              </div>

              <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs">
                <div className="mb-1 text-[11px] uppercase tracking-widest text-muted-foreground">
                  Model &amp; scoring metadata
                </div>
                <div className="flex justify-between gap-3 py-0.5">
                  <span className="text-muted-foreground">Model</span>
                  <span className="text-right">{ledger.data.model_version}</span>
                </div>
                <div className="flex justify-between gap-3 py-0.5">
                  <span className="text-muted-foreground">Scored at</span>
                  <span className="text-right">
                    {new Date(ledger.data.scored_at).toLocaleString()}
                  </span>
                </div>
              </div>

              {ledger.data.recommended_action && (
                <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs">
                  <div className="flex justify-between gap-3 py-0.5">
                    <span className="text-muted-foreground">AI-recommended action</span>
                    <span className="text-right">{ledger.data.recommended_action}</span>
                  </div>
                  {ledger.data.recommended_route_id && (
                    <div className="flex justify-between gap-3 py-0.5">
                      <span className="text-muted-foreground">AI-recommended route</span>
                      <span className="text-right">{ledger.data.recommended_route_id}</span>
                    </div>
                  )}
                  {ledger.data.modified_action && (
                    <>
                      <div className="flex justify-between gap-3 py-0.5">
                        <span className="text-muted-foreground">Human-modified action</span>
                        <span className="text-right">{ledger.data.modified_action}</span>
                      </div>
                      {ledger.data.modified_route_id && (
                        <div className="flex justify-between gap-3 py-0.5">
                          <span className="text-muted-foreground">Human-modified route</span>
                          <span className="text-right">{ledger.data.modified_route_id}</span>
                        </div>
                      )}
                      {ledger.data.modification_reason && (
                        <div className="mt-1 text-muted-foreground">
                          Reason: {ledger.data.modification_reason}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              <div>
                <div className="mb-1 text-[11px] uppercase tracking-widest text-muted-foreground">
                  Compliance checks
                </div>
                <div className="space-y-1.5">
                  {ledger.data.compliance.map((check) => (
                    <div
                      key={check.rule_code}
                      className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <span>{check.rule_name}</span>
                        <StatPill
                          tone={complianceTone(check.result === "PASS" ? "Passed" : check.result)}
                        >
                          {check.result.replace("_", " ")}
                        </StatPill>
                      </div>
                      <div className="mt-1 text-muted-foreground">{check.reason}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div className="mb-1 text-[11px] uppercase tracking-widest text-muted-foreground">
                  Outcome
                </div>
                {ledger.data.outcome.outcome_status === "OBSERVED" ? (
                  <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs">
                    <div className="flex justify-between gap-3 py-0.5">
                      <span className="text-muted-foreground">Result</span>
                      <span className="text-right">
                        {ledger.data.outcome.observed_outcome_value}
                      </span>
                    </div>
                    {ledger.data.outcome.business_outcome_note && (
                      <div className="mt-1 text-muted-foreground">
                        {ledger.data.outcome.business_outcome_note}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-muted-foreground">
                    No observed outcome has been recorded for this shipment yet.
                  </div>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Modify action dialog */}
      <Dialog open={!!modifyTarget} onOpenChange={(o) => !o && setModifyTarget(null)}>
        <DialogContent className="max-w-md border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">
              Modify Action · {modifyTarget?.shipment_id}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <div className="space-y-1">
              <div className="text-[11px] uppercase tracking-widest text-muted-foreground">
                Action
              </div>
              <Select
                value={modifyAction}
                onValueChange={(v) => setModifyAction(v as LogisticsAction)}
              >
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="MAINTAIN">Maintain current route</SelectItem>
                  <SelectItem value="REROUTE">Reroute</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {modifyAction === "REROUTE" && (
              <div className="space-y-1">
                <div className="text-[11px] uppercase tracking-widest text-muted-foreground">
                  Target route
                </div>
                <Select value={modifyRouteId} onValueChange={setModifyRouteId}>
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder="Select a route" />
                  </SelectTrigger>
                  <SelectContent>
                    {routes
                      .filter((r) => r.route_id !== shipmentsTarget?.route_id)
                      .map((r) => (
                        <SelectItem key={r.route_id} value={r.route_id}>
                          {r.name}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-1">
              <div className="text-[11px] uppercase tracking-widest text-muted-foreground">
                Reason
              </div>
              <textarea
                value={modifyReason}
                onChange={(e) => setModifyReason(e.target.value)}
                rows={3}
                placeholder="Why override the AI-recommended action?"
                className="w-full rounded-lg border border-white/10 bg-white/[0.03] p-2 text-sm outline-none focus:border-primary/40"
              />
            </div>
            <Button
              onClick={handleModifySubmit}
              disabled={modifyShipment.isPending}
              className="gap-1 mahindra-gradient text-white"
            >
              {modifyShipment.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              {modifyShipment.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Human review dialog */}
      <Dialog open={!!reviewTarget} onOpenChange={(o) => !o && setReviewTarget(null)}>
        <DialogContent className="max-w-md border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">
              Human Review · {reviewTarget?.shipment_id}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <div className="space-y-1">
              <div className="text-[11px] uppercase tracking-widest text-muted-foreground">
                Reviewer role
              </div>
              <Select
                value={reviewerRole}
                onValueChange={(v) => setReviewerRole(v as ReviewerRole)}
              >
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {REVIEWER_ROLES.map((role) => (
                    <SelectItem key={role} value={role}>
                      {role}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <div className="text-[11px] uppercase tracking-widest text-muted-foreground">
                Reason
              </div>
              <textarea
                value={reviewReason}
                onChange={(e) => setReviewReason(e.target.value)}
                rows={3}
                placeholder="Why does this shipment need human review?"
                className="w-full rounded-lg border border-white/10 bg-white/[0.03] p-2 text-sm outline-none focus:border-primary/40"
              />
            </div>
            <Button
              onClick={handleReviewSubmit}
              disabled={reviewShipment.isPending}
              className="gap-1 mahindra-gradient text-white"
            >
              {reviewShipment.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              {reviewShipment.isPending ? "Sending…" : "Send to Human Review"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
