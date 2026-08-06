import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Panel, SectionTitle, StatPill } from "@/components/ui/panel";
import {
  useApproveDecision,
  useComplianceRules,
  useEscalateDecision,
  useRejectDecision,
  useTrustDecisions,
} from "@/hooks/use-api";
import type { TrustDecision } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Eye, FileSearch, Check, X, AlertOctagon } from "lucide-react";

export const Route = createFileRoute("/trust")({
  head: () => ({ meta: [{ title: "Compliance Trust Ledger · Mahindra AI Command Center" }] }),
  component: Trust,
});

const RULES_FALLBACK = [
  { label: "Consent check", status: "OK" },
  { label: "Bias / fairness check", status: "OK" },
  { label: "Regulatory rule check", status: "OK" },
  { label: "Business policy check", status: "1 pending" },
  { label: "Audit trail complete", status: "OK" },
];

function Trust() {
  const decisions = useTrustDecisions();
  const rules = useComplianceRules() ?? RULES_FALLBACK;
  const approveDecision = useApproveDecision();
  const rejectDecision = useRejectDecision();
  const escalateDecision = useEscalateDecision();
  const [lineage, setLineage] = useState<TrustDecision | null>(null);
  const [rowStatus, setRowStatus] = useState<Record<string, string>>({});

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Compliance Trust Ledger"
        subtitle="Every AI recommendation has data lineage, explanation, confidence, approval and outcome tracking."
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_320px]">
        <Panel title="Recent AI Decisions">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[10px] uppercase tracking-widest text-muted-foreground">
                <tr className="border-b border-white/10">
                  <th className="pb-2 text-left">Decision ID</th>
                  <th className="pb-2 text-left">Use Case</th>
                  <th className="pb-2 text-left">Recommendation</th>
                  <th className="pb-2 text-left">Conf.</th>
                  <th className="pb-2 text-left">Approval</th>
                  <th className="pb-2 text-left">Risk</th>
                  <th className="pb-2 text-left">Audit</th>
                  <th className="pb-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((t) => (
                  <tr
                    key={t.id}
                    className="border-b border-white/5 last:border-0 hover:bg-white/[0.03]"
                  >
                    <td className="py-3 font-mono text-xs">{t.id}</td>
                    <td className="text-xs">{t.use}</td>
                    <td className="text-xs">{t.rec}</td>
                    <td>{t.conf}%</td>
                    <td>
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
                    <td>
                      <StatPill
                        tone={
                          t.risk === "Low" ? "success" : t.risk === "Medium" ? "warning" : "danger"
                        }
                      >
                        {t.risk}
                      </StatPill>
                    </td>
                    <td>
                      <StatPill tone={t.audit === "Complete" ? "success" : "info"}>
                        {t.audit}
                      </StatPill>
                    </td>
                    <td className="text-right">
                      <div className="inline-flex gap-1">
                        <button
                          title="Lineage"
                          onClick={() => setLineage(t)}
                          className="rounded-md border border-white/10 p-1.5 hover:border-primary/40 hover:bg-primary/10"
                        >
                          <FileSearch className="h-3.5 w-3.5" />
                        </button>
                        <button
                          title="Explain"
                          onClick={() => toast(`${t.id}: model attributed decision to ${t.data}`)}
                          className="rounded-md border border-white/10 p-1.5 hover:border-primary/40 hover:bg-primary/10"
                        >
                          <Eye className="h-3.5 w-3.5" />
                        </button>
                        <button
                          title="Approve"
                          onClick={() => {
                            approveDecision(t.id);
                            setRowStatus((s) => ({ ...s, [t.id]: "Approved" }));
                            toast.success(`${t.id} approved`);
                          }}
                          className="rounded-md border border-white/10 p-1.5 hover:border-emerald-500/40 hover:bg-emerald-500/10"
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                        <button
                          title="Reject"
                          onClick={() => {
                            const r = prompt("Rejection reason?");
                            if (r !== null) {
                              rejectDecision(t.id, r || "no reason");
                              setRowStatus((s) => ({ ...s, [t.id]: "Rejected" }));
                              toast.error(`${t.id} rejected — ${r || "no reason"}`);
                            }
                          }}
                          className="rounded-md border border-white/10 p-1.5 hover:border-red-500/40 hover:bg-red-500/10"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                        <button
                          title="Escalate"
                          onClick={() => {
                            escalateDecision(t.id);
                            setRowStatus((s) => ({ ...s, [t.id]: "Escalated" }));
                            toast("Escalated to compliance officer");
                          }}
                          className="rounded-md border border-white/10 p-1.5 hover:border-amber-500/40 hover:bg-amber-500/10"
                        >
                          <AlertOctagon className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Compliance Rules">
          <div className="space-y-2 text-sm">
            {rules.map((rule) => (
              <div
                key={rule.label}
                className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.03] p-3"
              >
                <span>{rule.label}</span>
                <StatPill tone={rule.status === "OK" ? "success" : "warning"}>
                  {rule.status}
                </StatPill>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="glass-strong rounded-2xl p-4 text-xs">
        <span className="font-semibold text-primary">Business Impact: </span>
        Safer AI adoption, faster audits, lower regulatory risk, higher trust.
      </div>

      <Dialog open={!!lineage} onOpenChange={(o) => !o && setLineage(null)}>
        <DialogContent className="max-w-lg border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Lineage · {lineage?.id}</DialogTitle>
          </DialogHeader>
          {lineage && (
            <ol className="space-y-2 text-sm">
              <li className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <b>1. Data sources: </b>
                {lineage.data}
              </li>
              <li className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <b>2. Model output: </b>
                {lineage.rec} (confidence {lineage.conf}%)
              </li>
              <li className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <b>3. Key drivers: </b>Predictive + causal weighted signals
              </li>
              <li className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <b>4. Human decision: </b>
                {lineage.approval}
              </li>
              <li className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <b>5. Action taken: </b>Executed via Action Agent · SLA logged
              </li>
              <li className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <b>6. Feedback captured: </b>Outcome fed to Learning Agent
              </li>
            </ol>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
