import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Panel, SectionTitle, StatPill } from "@/components/ui/panel";
import {
  useApproveDecision,
  useEscalateDecision,
  useRejectDecision,
  useTrustDecisionCompliance,
  useTrustDecisionEvents,
  useTrustDecisionExplanation,
  useTrustDecisionLineage,
  useTrustDecisionOutcome,
  useTrustDecisions,
} from "@/hooks/use-api";
import type { ReviewerRole, TrustDecision } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Eye, FileSearch, Check, X, AlertOctagon, Loader2, History, Target } from "lucide-react";

export const Route = createFileRoute("/trust")({
  head: () => ({ meta: [{ title: "Compliance Trust Ledger · Mahindra AI Command Center" }] }),
  component: Trust,
});

const REVIEWER_ROLES: ReviewerRole[] = [
  "Business Owner",
  "Domain Expert",
  "Risk Reviewer",
  "Compliance Reviewer",
  "Quality Reviewer",
];

/** Simulation Center runs are a live, actionable governance entry (see
 * app/services/trust.py) — canonical rows are immutable Synthetic Data
 * Factory history and never get action buttons that can't work. */
function isSimulationDecision(id: string): boolean {
  return id.startsWith("SIM_");
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function complianceTone(result: string): "success" | "warning" | "danger" | "default" {
  if (result === "PASS") return "success";
  if (result === "REVIEW_REQUIRED") return "warning";
  if (result === "FAIL") return "danger";
  return "default"; // NOT_APPLICABLE
}

/** Tracks scroll metrics for a horizontally-scrollable container so a custom
 * drag bar (see `HorizontalDragBar`) can render in place of the native
 * scrollbar. `watch` lets callers force a re-measure when content that
 * changes `scrollWidth` (e.g. a table's row count) changes without the
 * container's own box size changing. */
function useHorizontalDragScroll(watch?: unknown) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [metrics, setMetrics] = useState({ scrollLeft: 0, scrollWidth: 0, clientWidth: 0 });

  const updateMetrics = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setMetrics({ scrollLeft: el.scrollLeft, scrollWidth: el.scrollWidth, clientWidth: el.clientWidth });
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    updateMetrics();
    el.addEventListener("scroll", updateMetrics, { passive: true });
    const observer = new ResizeObserver(updateMetrics);
    observer.observe(el);
    return () => {
      el.removeEventListener("scroll", updateMetrics);
      observer.disconnect();
    };
  }, [updateMetrics, watch]);

  return { scrollRef, metrics };
}

/** Visible, draggable horizontal scrollbar ("wheel") for a wide table —
 * used instead of the browser's native scrollbar, which is hidden on the
 * scroll container this drives. */
function HorizontalDragBar({
  scrollRef,
  metrics,
}: {
  scrollRef: React.RefObject<HTMLDivElement | null>;
  metrics: { scrollLeft: number; scrollWidth: number; clientWidth: number };
}) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const dragState = useRef<{ startX: number; startScrollLeft: number } | null>(null);

  if (metrics.scrollWidth <= metrics.clientWidth + 1) return null;

  const thumbWidthPct = Math.max((metrics.clientWidth / metrics.scrollWidth) * 100, 8);
  const maxScrollLeft = metrics.scrollWidth - metrics.clientWidth;
  const thumbLeftPct = maxScrollLeft > 0 ? (metrics.scrollLeft / maxScrollLeft) * (100 - thumbWidthPct) : 0;

  const onThumbPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.stopPropagation();
    const el = scrollRef.current;
    if (!el) return;
    dragState.current = { startX: e.clientX, startScrollLeft: el.scrollLeft };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onThumbPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = scrollRef.current;
    const track = trackRef.current;
    if (!el || !track || !dragState.current) return;
    const deltaX = e.clientX - dragState.current.startX;
    const deltaScroll = (deltaX / track.clientWidth) * metrics.scrollWidth;
    el.scrollLeft = dragState.current.startScrollLeft + deltaScroll;
  };

  const onThumbPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    dragState.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
  };

  const onTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = scrollRef.current;
    const track = trackRef.current;
    if (!el || !track) return;
    const rect = track.getBoundingClientRect();
    const clickRatio = (e.clientX - rect.left) / rect.width;
    el.scrollLeft = clickRatio * metrics.scrollWidth - metrics.clientWidth / 2;
  };

  return (
    <div
      ref={trackRef}
      onClick={onTrackClick}
      className="relative mt-2 h-2.5 w-full cursor-pointer rounded-full bg-white/5"
      title="Drag to scroll"
    >
      <div
        onPointerDown={onThumbPointerDown}
        onPointerMove={onThumbPointerMove}
        onPointerUp={onThumbPointerUp}
        onClick={(e) => e.stopPropagation()}
        style={{ width: `${thumbWidthPct}%`, left: `${thumbLeftPct}%` }}
        className="absolute top-0 h-2.5 cursor-grab touch-none rounded-full bg-primary/60 transition-colors hover:bg-primary/80 active:cursor-grabbing active:bg-primary"
      />
    </div>
  );
}

function Trust() {
  const decisions = useTrustDecisions();
  const { scrollRef: decisionsScrollRef, metrics: decisionsScrollMetrics } = useHorizontalDragScroll(
    decisions.length,
  );
  const approveDecision = useApproveDecision();
  const rejectDecision = useRejectDecision();
  const escalateDecision = useEscalateDecision();
  const [lineage, setLineage] = useState<TrustDecision | null>(null);
  const [explanationTarget, setExplanationTarget] = useState<TrustDecision | null>(null);
  const [historyTarget, setHistoryTarget] = useState<TrustDecision | null>(null);
  const [outcomeTarget, setOutcomeTarget] = useState<TrustDecision | null>(null);
  const [escalateTarget, setEscalateTarget] = useState<TrustDecision | null>(null);
  const [reviewerRole, setReviewerRole] = useState<ReviewerRole>("Risk Reviewer");
  const [escalateReason, setEscalateReason] = useState("");
  const [rejectTarget, setRejectTarget] = useState<TrustDecision | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rowStatus, setRowStatus] = useState<Record<string, string>>({});
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null);
  const [complianceDetail, setComplianceDetail] = useState<{
    title: string;
    tone: "success" | "warning" | "danger" | "default";
    status: string;
    reason: string;
  } | null>(null);
  const lineageSteps = useTrustDecisionLineage(lineage?.id, !!lineage);
  const explanation = useTrustDecisionExplanation(explanationTarget?.id, !!explanationTarget);
  const events = useTrustDecisionEvents(historyTarget?.id, !!historyTarget);
  const outcome = useTrustDecisionOutcome(outcomeTarget?.id, !!outcomeTarget);
  const selectedDecision = decisions.find((d) => d.id === selectedDecisionId) ?? null;
  const compliance = useTrustDecisionCompliance(selectedDecisionId ?? undefined, !!selectedDecisionId);

  const handleApprove = (t: TrustDecision) => {
    approveDecision.mutate(t.id, {
      onSuccess: (updated) => {
        setRowStatus((s) => ({ ...s, [t.id]: updated.approval }));
        toast.success(`${t.id} approved`);
      },
      onError: (error) => toast.error(errorMessage(error, `${t.id} could not be approved`)),
    });
  };

  const handleRejectSubmit = () => {
    if (!rejectTarget) return;
    const target = rejectTarget;
    const reason = rejectReason;
    rejectDecision.mutate(
      { code: target.id, reason },
      {
        onSuccess: (updated) => {
          setRowStatus((s) => ({ ...s, [target.id]: updated.approval }));
          toast.error(`${target.id} rejected${reason ? ` — ${reason}` : ""}`);
          setRejectTarget(null);
          setRejectReason("");
        },
        onError: (error) => toast.error(errorMessage(error, `${target.id} could not be rejected`)),
      },
    );
  };

  const handleEscalateSubmit = () => {
    if (!escalateTarget) return;
    const target = escalateTarget;
    escalateDecision.mutate(
      { code: target.id, reviewerRole, reason: escalateReason },
      {
        onSuccess: (updated) => {
          setRowStatus((s) => ({ ...s, [target.id]: updated.approval }));
          toast(`${target.id} escalated to ${reviewerRole}`);
          setEscalateTarget(null);
          setEscalateReason("");
        },
        onError: (error) => toast.error(errorMessage(error, `${target.id} could not be escalated`)),
      },
    );
  };

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Compliance Trust Ledger"
        subtitle="Every AI recommendation has data lineage, explanation, confidence, approval and outcome tracking."
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_320px]">
        <Panel title="Recent AI Decisions" className="min-w-0">
          <div
            ref={decisionsScrollRef}
            className="overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          >
            <table className="w-full min-w-[1180px] text-sm">
              <thead className="text-[10px] uppercase tracking-widest text-muted-foreground">
                <tr className="border-b border-white/10">
                  <th className="whitespace-nowrap px-3 py-2 text-left first:pl-0">Decision ID</th>
                  <th className="whitespace-nowrap px-3 py-2 text-left">Use Case</th>
                  <th className="px-3 py-2 text-left">Recommendation</th>
                  <th className="whitespace-nowrap px-3 py-2 text-left">Conf.</th>
                  <th className="whitespace-nowrap px-3 py-2 text-left">Approval</th>
                  <th className="whitespace-nowrap px-3 py-2 text-left">Risk</th>
                  <th className="whitespace-nowrap px-3 py-2 text-left">Audit</th>
                  <th className="whitespace-nowrap px-3 py-2 text-right last:pr-0">Actions</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((t) => (
                  <tr
                    key={t.id}
                    onClick={() => setSelectedDecisionId(t.id)}
                    className={`cursor-pointer border-b border-white/5 last:border-0 hover:bg-white/[0.03] ${
                      selectedDecisionId === t.id ? "bg-primary/10" : ""
                    }`}
                  >
                    <td className="whitespace-nowrap px-3 py-3 pl-0 font-mono text-xs">{t.id}</td>
                    <td className="whitespace-nowrap px-3 py-3 text-xs">{t.use}</td>
                    <td className="max-w-[280px] px-3 py-3 text-xs">{t.rec}</td>
                    <td className="whitespace-nowrap px-3 py-3">{t.conf}%</td>
                    <td className="whitespace-nowrap px-3 py-3">
                      <StatPill
                        tone={
                          rowStatus[t.id] === "Approved" || t.approval === "Approved"
                            ? "success"
                            : rowStatus[t.id] === "Rejected"
                              ? "danger"
                              : "warning"
                        }
                      >
                        {rowStatus[t.id] || t.approval}
                      </StatPill>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3">
                      <StatPill
                        tone={
                          t.risk === "Low" ? "success" : t.risk === "Medium" ? "warning" : "danger"
                        }
                      >
                        {t.risk}
                      </StatPill>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3">
                      <StatPill tone={t.audit === "Complete" ? "success" : "info"}>
                        {t.audit}
                      </StatPill>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 pr-0 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="inline-flex gap-1">
                        <button
                          title="View Lineage"
                          onClick={() => setLineage(t)}
                          className="rounded-md border border-white/10 p-1.5 hover:border-primary/40 hover:bg-primary/10"
                        >
                          <FileSearch className="h-3.5 w-3.5" />
                        </button>
                        <button
                          title="View Explanation"
                          onClick={() => setExplanationTarget(t)}
                          className="rounded-md border border-white/10 p-1.5 hover:border-primary/40 hover:bg-primary/10"
                        >
                          <Eye className="h-3.5 w-3.5" />
                        </button>
                        <button
                          title="View History"
                          onClick={() => setHistoryTarget(t)}
                          className="rounded-md border border-white/10 p-1.5 hover:border-primary/40 hover:bg-primary/10"
                        >
                          <History className="h-3.5 w-3.5" />
                        </button>
                        {!isSimulationDecision(t.id) && (
                          <button
                            title="View Outcome"
                            onClick={() => setOutcomeTarget(t)}
                            className="rounded-md border border-white/10 p-1.5 hover:border-primary/40 hover:bg-primary/10"
                          >
                            <Target className="h-3.5 w-3.5" />
                          </button>
                        )}
                        {isSimulationDecision(t.id) && (
                          <>
                            <button
                              title="Approve"
                              disabled={approveDecision.isPending}
                              onClick={() => handleApprove(t)}
                              className="rounded-md border border-white/10 p-1.5 hover:border-emerald-500/40 hover:bg-emerald-500/10 disabled:opacity-40"
                            >
                              <Check className="h-3.5 w-3.5" />
                            </button>
                            <button
                              title="Reject"
                              disabled={rejectDecision.isPending}
                              onClick={() => {
                                setRejectTarget(t);
                                setRejectReason("");
                              }}
                              className="rounded-md border border-white/10 p-1.5 hover:border-red-500/40 hover:bg-red-500/10 disabled:opacity-40"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                            <button
                              title="Escalate"
                              onClick={() => {
                                setEscalateTarget(t);
                                setReviewerRole("Risk Reviewer");
                                setEscalateReason("");
                              }}
                              className="rounded-md border border-white/10 p-1.5 hover:border-amber-500/40 hover:bg-amber-500/10"
                            >
                              <AlertOctagon className="h-3.5 w-3.5" />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <HorizontalDragBar scrollRef={decisionsScrollRef} metrics={decisionsScrollMetrics} />
        </Panel>

        <Panel title="Compliance Rules" className="sticky top-20 max-h-[calc(100vh-6rem)] self-start overflow-y-auto">
          {!selectedDecision && (
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-muted-foreground">
              Select a decision to see its real compliance checks.
            </div>
          )}
          {selectedDecision && compliance.isLoading && (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Evaluating compliance…
            </div>
          )}
          {selectedDecision && compliance.isError && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
              Compliance evaluation unavailable. Check backend logs.
            </div>
          )}
          {selectedDecision && compliance.data && (
            <div className="space-y-2 text-sm">
              <div className="mb-1 font-mono text-[11px] text-muted-foreground">{selectedDecision.id}</div>
              <div
                role="button"
                tabIndex={0}
                onClick={() =>
                  setComplianceDetail({
                    title: "Execution eligible",
                    tone: selectedDecision.execution_eligible ? "success" : "danger",
                    status: selectedDecision.execution_eligible ? "Yes" : "Blocked",
                    reason: selectedDecision.execution_eligible_reason,
                  })
                }
                className="cursor-pointer rounded-lg border border-white/10 bg-white/[0.03] p-3 hover:border-primary/40 hover:bg-white/[0.05]"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold">Execution eligible</span>
                  <StatPill tone={selectedDecision.execution_eligible ? "success" : "danger"}>
                    {selectedDecision.execution_eligible ? "Yes" : "Blocked"}
                  </StatPill>
                </div>
              </div>
              {compliance.data.map((rule) => (
                <div
                  key={rule.rule_code}
                  role="button"
                  tabIndex={0}
                  onClick={() =>
                    setComplianceDetail({
                      title: rule.rule_name,
                      tone: complianceTone(rule.result),
                      status: rule.result.replace("_", " "),
                      reason: rule.reason,
                    })
                  }
                  className="cursor-pointer rounded-lg border border-white/10 bg-white/[0.03] p-3 hover:border-primary/40 hover:bg-white/[0.05]"
                >
                  <div className="flex items-center justify-between">
                    <span>{rule.rule_name}</span>
                    <StatPill tone={complianceTone(rule.result)}>{rule.result.replace("_", " ")}</StatPill>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <div className="glass-strong rounded-2xl p-4 text-xs">
        <span className="font-semibold text-primary">Business Impact: </span>
        Safer AI adoption, faster audits, lower regulatory risk, higher trust.
      </div>

      <Dialog open={!!lineage} onOpenChange={(o) => !o && setLineage(null)}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Lineage · {lineage?.id}</DialogTitle>
          </DialogHeader>
          {lineageSteps.isLoading && (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading lineage…
            </div>
          )}
          {lineageSteps.isError && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
              Lineage unavailable. Check backend logs.
            </div>
          )}
          {lineageSteps.data && (
            <ol className="space-y-2 text-sm">
              {lineageSteps.data.map((step) => (
                <li key={step.step} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                  <b>
                    {step.step}. {step.title}
                  </b>
                  {typeof step.detail === "string" ? (
                    step.detail && <div className="mt-1 text-muted-foreground">{step.detail}</div>
                  ) : (
                    step.detail &&
                    Object.keys(step.detail).length > 0 && (
                      <div className="mt-1 space-y-0.5 text-muted-foreground">
                        {Object.entries(step.detail).map(([key, value]) => (
                          <div key={key}>
                            {key}: {String(value)}
                          </div>
                        ))}
                      </div>
                    )
                  )}
                </li>
              ))}
            </ol>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!explanationTarget} onOpenChange={(o) => !o && setExplanationTarget(null)}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Explanation · {explanationTarget?.id}</DialogTitle>
          </DialogHeader>
          {explanation.isLoading && (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading explanation…
            </div>
          )}
          {explanation.isError && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
              Explanation unavailable. Check backend logs.
            </div>
          )}
          {explanation.data && (
            <div className="space-y-3 text-sm">
              <div className="rounded-lg border border-primary/30 bg-primary/10 p-3 text-xs">
                <span className="font-semibold text-primary">Recommendation: </span>
                {explanation.data.recommendation}
              </div>
              <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <div className="flex items-center justify-between">
                  <span className="font-semibold">Confidence</span>
                  <StatPill tone="info">{explanation.data.confidence}%</StatPill>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">{explanation.data.confidence_reason}</div>
              </div>
              {explanation.data.drivers.length > 0 && (
                <div>
                  <div className="mb-1 text-[11px] uppercase tracking-widest text-muted-foreground">Top drivers</div>
                  <div className="space-y-2">
                    {explanation.data.drivers.map((driver) => (
                      <div key={driver.name} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                        <div className="flex items-center justify-between">
                          <span>{driver.name}</span>
                          <StatPill tone={driver.direction === "positive" ? "success" : "danger"}>
                            {driver.direction === "positive" ? "+" : "−"}
                            {Math.abs(driver.contribution)}
                          </StatPill>
                        </div>
                        <div className="mt-1 text-xs text-muted-foreground">{driver.detail}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {explanation.data.supporting_evidence.length > 0 && (
                <div>
                  <div className="mb-1 text-[11px] uppercase tracking-widest text-muted-foreground">
                    Supporting evidence
                  </div>
                  <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs">
                    {explanation.data.supporting_evidence.map((item) => (
                      <div key={item.label} className="flex justify-between gap-3 py-0.5">
                        <span className="text-muted-foreground">{item.label}</span>
                        <span className="text-right">{item.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!complianceDetail} onOpenChange={(o) => !o && setComplianceDetail(null)}>
        <DialogContent className="max-w-md border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">{complianceDetail?.title}</DialogTitle>
          </DialogHeader>
          {complianceDetail && (
            <div className="space-y-3 text-sm">
              <StatPill tone={complianceDetail.tone}>{complianceDetail.status}</StatPill>
              <p className="text-muted-foreground">{complianceDetail.reason}</p>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!historyTarget} onOpenChange={(o) => !o && setHistoryTarget(null)}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">History · {historyTarget?.id}</DialogTitle>
          </DialogHeader>
          {events.isLoading && (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading history…
            </div>
          )}
          {events.isError && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
              History unavailable. Check backend logs.
            </div>
          )}
          {events.data && (
            <ol className="space-y-2 text-sm">
              {events.data.map((event, index) => (
                <li key={`${event.event_type}-${event.event_at}`} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                  <div className="flex items-center justify-between">
                    <b>
                      {index + 1}. {event.event_type.replace(/_/g, " ")}
                    </b>
                    <span className="text-[11px] text-muted-foreground">{new Date(event.event_at).toLocaleString()}</span>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {event.summary} — by {event.actor}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!outcomeTarget} onOpenChange={(o) => !o && setOutcomeTarget(null)}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Outcome · {outcomeTarget?.id}</DialogTitle>
          </DialogHeader>
          {outcome.isLoading && (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading outcome…
            </div>
          )}
          {outcome.isError && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
              Outcome unavailable. Check backend logs.
            </div>
          )}
          {outcome.data && (
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <span className="font-semibold">Status</span>
                <StatPill tone={outcome.data.outcome_status === "OBSERVED" ? "success" : "warning"}>
                  {outcome.data.outcome_status === "OBSERVED" ? "Observed" : "Outcome pending"}
                </StatPill>
              </div>

              {outcome.data.expected_impact && Object.keys(outcome.data.expected_impact).length > 0 && (
                <div>
                  <div className="mb-1 text-[11px] uppercase tracking-widest text-muted-foreground">
                    Expected impact
                  </div>
                  <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs">
                    {Object.entries(outcome.data.expected_impact).map(([key, value]) => (
                      <div key={key} className="flex justify-between gap-3 py-0.5">
                        <span className="text-muted-foreground">{key.replace(/_/g, " ")}</span>
                        <span className="text-right">{String(value)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {outcome.data.outcome_status === "OBSERVED" ? (
                <div>
                  <div className="mb-1 text-[11px] uppercase tracking-widest text-muted-foreground">
                    Observed outcome
                  </div>
                  <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs">
                    <div className="flex justify-between gap-3 py-0.5">
                      <span className="text-muted-foreground">Result</span>
                      <span className="text-right">{outcome.data.observed_outcome_value}</span>
                    </div>
                    <div className="flex justify-between gap-3 py-0.5">
                      <span className="text-muted-foreground">Observed at</span>
                      <span className="text-right">
                        {outcome.data.observed_at ? new Date(outcome.data.observed_at).toLocaleString() : "—"}
                      </span>
                    </div>
                    <div className="flex justify-between gap-3 py-0.5">
                      <span className="text-muted-foreground">Business outcome observed</span>
                      <span className="text-right">{outcome.data.business_outcome_observed ? "Yes" : "No"}</span>
                    </div>
                    {outcome.data.business_outcome_note && (
                      <div className="mt-1 text-muted-foreground">{outcome.data.business_outcome_note}</div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-muted-foreground">
                  No observed outcome has been recorded for this decision yet.
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!rejectTarget} onOpenChange={(o) => !o && setRejectTarget(null)}>
        <DialogContent className="max-w-md border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Reject · {rejectTarget?.id}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <div className="space-y-1">
              <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Reason</div>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                rows={3}
                placeholder="Why is this recommendation being rejected?"
                className="w-full rounded-lg border border-white/10 bg-white/[0.03] p-2 text-sm outline-none focus:border-red-500/40"
              />
            </div>
            <Button
              onClick={handleRejectSubmit}
              disabled={rejectDecision.isPending}
              variant="outline"
              className="gap-1 border-red-500/40 text-red-300 hover:bg-red-500/10"
            >
              {rejectDecision.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              {rejectDecision.isPending ? "Rejecting…" : "Reject"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!escalateTarget} onOpenChange={(o) => !o && setEscalateTarget(null)}>
        <DialogContent className="max-w-md border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Escalate · {escalateTarget?.id}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <div className="space-y-1">
              <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Reviewer role</div>
              <Select value={reviewerRole} onValueChange={(v) => setReviewerRole(v as ReviewerRole)}>
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
              <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Reason</div>
              <textarea
                value={escalateReason}
                onChange={(e) => setEscalateReason(e.target.value)}
                rows={3}
                placeholder="Why does this need human review?"
                className="w-full rounded-lg border border-white/10 bg-white/[0.03] p-2 text-sm outline-none focus:border-primary/40"
              />
            </div>
            <Button
              onClick={handleEscalateSubmit}
              disabled={escalateDecision.isPending}
              className="gap-1 mahindra-gradient text-white"
            >
              {escalateDecision.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              {escalateDecision.isPending ? "Escalating…" : "Escalate"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
