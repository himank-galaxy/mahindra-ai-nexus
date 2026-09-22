import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Panel, SectionTitle, StatPill } from "@/components/ui/panel";
import {
  useApproveCase,
  useCaseTrustLedger,
  useCollectionsAgents,
  useCollectionsCases,
  useCollectionsMetrics,
  useModifyCase,
  useReviewCase,
  type CollectionsCaseView,
} from "@/hooks/use-api";
import type { CollectionsCategory, CollectionsChannel, CollectionsOffer, ReviewerRole } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Check, UserCog, FileSearch, Pencil, Loader2 } from "lucide-react";

export const Route = createFileRoute("/collections")({
  head: () => ({ meta: [{ title: "Collections AI Swarm · Mahindra AI Command Center" }] }),
  component: Collections,
});

const REVIEWER_ROLES: ReviewerRole[] = [
  "Business Owner",
  "Domain Expert",
  "Risk Reviewer",
  "Compliance Reviewer",
  "Quality Reviewer",
];

// Real recorded categories (see app/repositories/collections_simulation.py)
// — the exact same categories the recovery model was trained on, never a
// UI-invented grouping.
const CHANNEL_OPTIONS: { value: CollectionsChannel; label: string }[] = [
  { value: "SMS", label: "SMS" },
  { value: "WHATSAPP", label: "WhatsApp" },
  { value: "EMAIL", label: "Email" },
  { value: "CALL", label: "Call" },
  { value: "FIELD_VISIT", label: "Field Visit" },
];
const OFFER_OPTIONS: { value: CollectionsOffer; label: string }[] = [
  { value: "NONE", label: "None" },
  { value: "PAYMENT_REMINDER", label: "Payment Reminder" },
  { value: "PARTIAL_PAYMENT_PLAN", label: "Partial Payment Plan" },
  { value: "REPAYMENT_PLAN_DISCUSSION", label: "Repayment Plan Discussion" },
];

// Real methodology behind each KPI tile — see app/services/collections.py
// CollectionsService.list_metrics(). All are live SQL aggregates over the
// real collection_cases/collection_interactions/payment_history tables,
// computed fresh on every load — never hardcoded or historical snapshots.
const KPI_EXPLANATIONS: Record<string, string> = {
  "Open collection cases":
    "Live count of collection cases with status OPEN — COUNT(*) FILTER (case_status = 'OPEN') over the real collection_cases table. Recalculated on every page load.",
  "Current arrears":
    "Sum of the real current_arrears_inr column across every collection case right now — SUM(current_arrears_inr). This is the total overdue amount outstanding across all cases combined.",
  "90+ DPD cases":
    "Count of cases where current_dpd >= 90 — a standard severe-delinquency threshold, computed live from the real current_dpd column (not a fixed or cached value).",
  "Payment after contact":
    "Of every real customer-contact interaction ever recorded, the percentage that was followed by a payment: COUNT(payment_after_contact = true) / COUNT(all interactions) × 100. This is all-time, not a rolling window.",
  "Promise kept":
    "Of every time a customer promised to pay (promise_to_pay = true), the percentage where a payment actually followed: COUNT(payment_after_promise = true) / COUNT(promise_to_pay = true) × 100.",
  "Scheduled payment realization":
    "Total actual payments received divided by total scheduled payments due, across the full payment_history table — SUM(actual_payment_amount_inr) / SUM(scheduled_payment_amount_inr) × 100, capped at 100%.",
  "Resolved cases":
    "Total cases minus open cases — every collection case that has already reached a resolved status, whatever the total case count is right now.",
};

// Real methodology behind each Agent Swarm tile — see
// CollectionsService.list_agents(). These are channel-usage tallies over
// real historical contact interactions, not separate running AI agents —
// no model or process is "active" per tile; the number is a live COUNT.
function channelExplanation(name: string): string {
  const channel = name.replace(/ workflow$/i, "");
  return (
    `"${name}" is a live count of real customer-contact interactions recorded via ${channel} — ` +
    `GROUP BY channel, COUNT(*) over the collection_interactions table. It reflects historical contact ` +
    `volume for this channel, not a separate AI agent or a currently-running process. The channel a model ` +
    `actually recommends per case (the "Best channel" column below) is a different, forward-looking ` +
    `prediction — this tile is descriptive history, not a recommendation.`
  );
}

function complianceTone(flag: string): "success" | "warning" | "danger" | "default" {
  if (flag === "Passed") return "success";
  if (flag === "Review Required") return "warning";
  if (flag === "Failed") return "danger";
  return "default";
}

// Backend-derived, explainable priority (see
// app/services/collections_priority.py) — click opens `priority_reason`.
function priorityTone(priority: string): "success" | "warning" | "danger" | "info" {
  if (priority === "Critical") return "danger";
  if (priority === "High") return "warning";
  if (priority === "Medium") return "info";
  return "success"; // Low
}

function statusTone(status: string): "success" | "warning" | "danger" | "default" | "info" {
  if (status === "Approved") return "success";
  if (status === "Escalated") return "warning";
  if (status === "Rejected") return "danger";
  if (status === "Resolved") return "default";
  return "info"; // Pending
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

// The 4 mutually-exclusive filter buckets (see
// CollectionsService._categorize) — "Actionable" is the default view.
const CATEGORY_TABS: { value: CollectionsCategory; label: string }[] = [
  { value: "actionable", label: "Actionable" },
  { value: "review_required", label: "Review Required" },
  { value: "approved", label: "Approved" },
  { value: "resolved", label: "Resolved" },
];

/** A case is only actionable from this screen while it's still live and
 * undecided-or-escalated — an immutable canonical (Synthetic Data
 * Factory) decision (whether historically Approved or Rejected), or a
 * case already approved/resolved, can't be re-decided here (see
 * app/services/collections.py). Checking `governance_track` in addition
 * to `category` matters specifically for a canonical Rejected case,
 * which is bucketed under "Review Required" but is still immutable. */
function isActionable(c: CollectionsCaseView): boolean {
  return c.governance_track === "live" && (c.category === "actionable" || c.category === "review_required");
}

function Collections() {
  const metrics = useCollectionsMetrics();
  const agents = useCollectionsAgents();
  const cases = useCollectionsCases();
  const [activeCategory, setActiveCategory] = useState<CollectionsCategory>("actionable");
  const categoryCounts = useMemo(() => {
    const counts: Record<CollectionsCategory, number> = {
      actionable: 0,
      review_required: 0,
      approved: 0,
      resolved: 0,
    };
    for (const c of cases) counts[c.category] += 1;
    return counts;
  }, [cases]);
  const filteredCases = useMemo(() => cases.filter((c) => c.category === activeCategory), [cases, activeCategory]);
  const approveCase = useApproveCase();
  const modifyCase = useModifyCase();
  const reviewCase = useReviewCase();

  const [infoDetail, setInfoDetail] = useState<{ title: string; detail: string } | null>(null);
  const [ledgerTarget, setLedgerTarget] = useState<CollectionsCaseView | null>(null);
  const [modifyTarget, setModifyTarget] = useState<CollectionsCaseView | null>(null);
  const [modifyChannel, setModifyChannel] = useState<CollectionsChannel>("SMS");
  const [modifyOffer, setModifyOffer] = useState<CollectionsOffer>("NONE");
  const [modifyReason, setModifyReason] = useState("");
  const [reviewTarget, setReviewTarget] = useState<CollectionsCaseView | null>(null);
  const [reviewerRole, setReviewerRole] = useState<ReviewerRole>("Risk Reviewer");
  const [reviewReason, setReviewReason] = useState("");

  const ledger = useCaseTrustLedger(ledgerTarget?.id);

  const handleApprove = (c: CollectionsCaseView) => {
    if (!c.id) return;
    approveCase.mutate(c.id, {
      onSuccess: () => toast.success(`${c.customer} · Approved`),
      onError: (error) => toast.error(errorMessage(error, `${c.customer} could not be approved`)),
    });
  };

  const handleModifySubmit = () => {
    const target = modifyTarget;
    const caseId = target?.id;
    if (!target || !caseId) return;
    modifyCase.mutate(
      { caseId, channel: modifyChannel, offer: modifyOffer, reason: modifyReason },
      {
        onSuccess: () => {
          toast.success(`${target.customer} · action updated`);
          setModifyTarget(null);
          setModifyReason("");
        },
        onError: (error) => toast.error(errorMessage(error, `${target.customer}'s action could not be updated`)),
      },
    );
  };

  const handleReviewSubmit = () => {
    const target = reviewTarget;
    const caseId = target?.id;
    if (!target || !caseId) return;
    reviewCase.mutate(
      { caseId, reviewerRole, reason: reviewReason },
      {
        onSuccess: () => {
          toast(`${target.customer} sent to human review`);
          setReviewTarget(null);
          setReviewReason("");
        },
        onError: (error) => toast.error(errorMessage(error, `${target.customer} could not be sent to review`)),
      },
    );
  };

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Collections & Recovery AI Swarm"
        subtitle="Multi-agent collections system that predicts, recommends, checks compliance and learns from repayment outcomes."
      />

      {metrics.length === 0 ? (
        <div className="glass rounded-xl p-4 text-xs text-muted-foreground">Loading collections metrics…</div>
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {metrics.map((m) => (
            <div
              key={m.label}
              role="button"
              tabIndex={0}
              onClick={() =>
                setInfoDetail({
                  title: m.label,
                  detail: KPI_EXPLANATIONS[m.label] ?? "Live aggregate computed from real collections data.",
                })
              }
              className="glass cursor-pointer rounded-xl p-3 transition-colors hover:border-primary/40 hover:bg-white/[0.05]"
            >
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground">{m.label}</div>
              <div className="mt-1 text-lg font-semibold text-gradient-mahindra">{m.value}</div>
            </div>
          ))}
        </div>
      )}

      <Panel title="Agent Swarm">
        {agents.length === 0 ? (
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-muted-foreground">
            Loading channel activity…
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            {agents.map((a) => (
              <div
                key={a.name}
                role="button"
                tabIndex={0}
                onClick={() => setInfoDetail({ title: a.name, detail: channelExplanation(a.name) })}
                className="cursor-pointer rounded-lg border border-white/10 bg-white/[0.03] p-3 transition-colors hover:border-primary/40 hover:bg-white/[0.05]"
              >
                <div className="text-xs font-semibold">{a.name}</div>
                <div className="mt-2">
                  <StatPill tone="info">{a.status}</StatPill>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Customer Prioritization">
        <div className="mb-4 flex flex-wrap gap-2">
          {CATEGORY_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setActiveCategory(tab.value)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                activeCategory === tab.value
                  ? "border-primary/50 bg-primary/15 text-foreground"
                  : "border-white/10 bg-white/[0.03] text-muted-foreground hover:border-white/20 hover:text-foreground"
              }`}
            >
              {tab.label} <span className="opacity-70">{categoryCounts[tab.value]}</span>
            </button>
          ))}
        </div>

        {filteredCases.length === 0 ? (
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-muted-foreground">
            No {CATEGORY_TABS.find((t) => t.value === activeCategory)?.label.toLowerCase()} cases right now.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[10px] uppercase tracking-widest text-muted-foreground">
                <tr className="border-b border-white/10">
                  <th className="pb-2 text-left">Priority</th>
                  <th className="pb-2 text-left">Customer</th>
                  <th className="pb-2 text-left">DPD</th>
                  <th className="pb-2 text-left">Outstanding</th>
                  <th className="pb-2 text-left">Risk</th>
                  <th className="pb-2 text-left">Recovery</th>
                  <th className="pb-2 text-left">Best Action</th>
                  <th className="pb-2 text-left">Compliance</th>
                  <th className="pb-2 text-left">Status</th>
                  <th className="pb-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredCases.map((c) => (
                  <tr key={c.id ?? c.case_id} className="border-b border-white/5 last:border-0 hover:bg-white/[0.03]">
                    <td className="py-3">
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={() => setInfoDetail({ title: `Priority · ${c.customer}`, detail: c.priority_reason })}
                        className="inline-block cursor-pointer"
                      >
                        <StatPill tone={priorityTone(c.priority)}>{c.priority}</StatPill>
                      </div>
                    </td>
                    <td>{c.customer}</td>
                    <td>{c.dpd}</td>
                    <td>{c.out}</td>
                    <td>
                      <StatPill tone={c.roll > 70 ? "danger" : c.roll > 50 ? "warning" : "success"}>{c.roll}%</StatPill>
                    </td>
                    <td>{c.prob}%</td>
                    <td className="text-xs">{c.best_action}</td>
                    <td>
                      <StatPill tone={complianceTone(c.flag)}>{c.flag}</StatPill>
                    </td>
                    <td>
                      <StatPill tone={statusTone(c.status ?? "Pending")}>{c.status ?? "Pending"}</StatPill>
                    </td>
                    <td className="text-right">
                      <div className="inline-flex gap-1">
                        {isActionable(c) && (
                          <>
                            <button
                              title="Approve"
                              disabled={approveCase.isPending}
                              onClick={() => handleApprove(c)}
                              className="rounded-md border border-white/10 p-1.5 hover:border-emerald-500/40 hover:bg-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-30"
                            >
                              <Check className="h-3.5 w-3.5" />
                            </button>
                            <button
                              title="Modify"
                              onClick={() => {
                                setModifyTarget(c);
                                setModifyChannel("SMS");
                                setModifyOffer("NONE");
                                setModifyReason("");
                              }}
                              className="rounded-md border border-white/10 p-1.5 hover:border-primary/40 hover:bg-primary/10"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              title="Human review"
                              onClick={() => {
                                setReviewTarget(c);
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
                          onClick={() => setLedgerTarget(c)}
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
      </Panel>

      <div className="glass-strong rounded-2xl p-4 text-xs">
        <span className="font-semibold text-primary">Business Impact: </span>
        Lower NPAs, higher recovery, better customer treatment and improved field productivity.
      </div>

      <Dialog open={!!infoDetail} onOpenChange={(o) => !o && setInfoDetail(null)}>
        <DialogContent className="max-w-md border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">{infoDetail?.title}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">{infoDetail?.detail}</p>
        </DialogContent>
      </Dialog>

      <Dialog open={!!ledgerTarget} onOpenChange={(o) => !o && setLedgerTarget(null)}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Trust Ledger · {ledgerTarget?.customer}</DialogTitle>
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
                <StatPill tone={complianceTone(ledger.data.audit_status)}>{ledger.data.audit_status}</StatPill>
              </div>

              <div
                role="button"
                tabIndex={0}
                onClick={() =>
                  setInfoDetail({ title: `Priority · ${ledgerTarget?.customer}`, detail: ledger.data.priority_reason })
                }
                className="flex cursor-pointer items-center justify-between rounded-lg border border-white/10 bg-white/[0.03] p-3 hover:border-primary/40"
              >
                <span className="font-semibold">Priority</span>
                <StatPill tone={priorityTone(ledger.data.priority)}>{ledger.data.priority}</StatPill>
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
                  <span className="text-right">{new Date(ledger.data.scored_at).toLocaleString()}</span>
                </div>
              </div>

              {ledger.data.recommended_channel && (
                <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs">
                  <div className="flex justify-between gap-3 py-0.5">
                    <span className="text-muted-foreground">AI-recommended channel</span>
                    <span className="text-right">{ledger.data.recommended_channel}</span>
                  </div>
                  <div className="flex justify-between gap-3 py-0.5">
                    <span className="text-muted-foreground">AI-recommended action</span>
                    <span className="text-right">{ledger.data.recommended_offer}</span>
                  </div>
                  {ledger.data.modified_channel && (
                    <>
                      <div className="flex justify-between gap-3 py-0.5">
                        <span className="text-muted-foreground">Human-modified channel</span>
                        <span className="text-right">{ledger.data.modified_channel}</span>
                      </div>
                      <div className="flex justify-between gap-3 py-0.5">
                        <span className="text-muted-foreground">Human-modified action</span>
                        <span className="text-right">{ledger.data.modified_offer}</span>
                      </div>
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
                        <StatPill tone={complianceTone(check.result === "PASS" ? "Passed" : check.result)}>
                          {check.result.replace("_", " ")}
                        </StatPill>
                      </div>
                      <div className="mt-1 text-muted-foreground">{check.reason}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div className="mb-1 text-[11px] uppercase tracking-widest text-muted-foreground">Outcome</div>
                {ledger.data.outcome.outcome_status === "OBSERVED" ? (
                  <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs">
                    <div className="flex justify-between gap-3 py-0.5">
                      <span className="text-muted-foreground">Result</span>
                      <span className="text-right">{ledger.data.outcome.observed_outcome_value}</span>
                    </div>
                    {ledger.data.outcome.business_outcome_note && (
                      <div className="mt-1 text-muted-foreground">{ledger.data.outcome.business_outcome_note}</div>
                    )}
                  </div>
                ) : (
                  <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-muted-foreground">
                    No observed outcome has been recorded for this case yet.
                  </div>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!modifyTarget} onOpenChange={(o) => !o && setModifyTarget(null)}>
        <DialogContent className="max-w-md border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Modify Action · {modifyTarget?.customer}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <div className="space-y-1">
              <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Channel</div>
              <Select value={modifyChannel} onValueChange={(v) => setModifyChannel(v as CollectionsChannel)}>
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CHANNEL_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Offer</div>
              <Select value={modifyOffer} onValueChange={(v) => setModifyOffer(v as CollectionsOffer)}>
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {OFFER_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Reason</div>
              <textarea
                value={modifyReason}
                onChange={(e) => setModifyReason(e.target.value)}
                rows={3}
                placeholder="Why override the AI-recommended channel/offer?"
                className="w-full rounded-lg border border-white/10 bg-white/[0.03] p-2 text-sm outline-none focus:border-primary/40"
              />
            </div>
            <Button onClick={handleModifySubmit} disabled={modifyCase.isPending} className="gap-1 mahindra-gradient text-white">
              {modifyCase.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              {modifyCase.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!reviewTarget} onOpenChange={(o) => !o && setReviewTarget(null)}>
        <DialogContent className="max-w-md border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Human Review · {reviewTarget?.customer}</DialogTitle>
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
                value={reviewReason}
                onChange={(e) => setReviewReason(e.target.value)}
                rows={3}
                placeholder="Why does this case need human review?"
                className="w-full rounded-lg border border-white/10 bg-white/[0.03] p-2 text-sm outline-none focus:border-primary/40"
              />
            </div>
            <Button onClick={handleReviewSubmit} disabled={reviewCase.isPending} className="gap-1 mahindra-gradient text-white">
              {reviewCase.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              {reviewCase.isPending ? "Sending…" : "Send to Human Review"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
