import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Panel, SectionTitle, StatPill } from "@/components/ui/panel";
import {
  useApproveCase,
  useCaseLedger,
  useCollectionsAgents,
  useCollectionsCases,
  useCollectionsMetrics,
  useModifyCase,
  useReviewCase,
} from "@/hooks/use-api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Check, UserCog, FileSearch, Pencil } from "lucide-react";

export const Route = createFileRoute("/collections")({
  head: () => ({ meta: [{ title: "Collections AI Swarm · Mahindra AI Command Center" }] }),
  component: Collections,
});

const AGENTS = [
  { name: "Risk Prediction Agent", status: "Active" },
  { name: "Channel Optimization Agent", status: "Active" },
  { name: "Offer Recommendation Agent", status: "Recommended" },
  { name: "Field Route Agent", status: "Active" },
  { name: "Compliance Guardrail Agent", status: "Reviewing" },
  { name: "Human Review Agent", status: "Active" },
] as const;

const METRICS_FALLBACK = [
  { label: "Accounts at risk", value: "12,842" },
  { label: "Predicted roll-forward", value: "3,214" },
  { label: "Recovery opportunity", value: "₹42 Cr" },
  { label: "Field visit optimization", value: "-28% cost" },
  { label: "Compliance alerts", value: "6 flagged" },
];

function Collections() {
  const metrics = useCollectionsMetrics() ?? METRICS_FALLBACK;
  const agents = useCollectionsAgents() ?? AGENTS;
  const cases = useCollectionsCases();
  const approveCase = useApproveCase();
  const modifyCase = useModifyCase();
  const reviewCase = useReviewCase();
  const [row, setRow] = useState<Record<string, string>>({});
  const [ledger, setLedger] = useState<string | null>(null);
  const [modify, setModify] = useState<string | null>(null);
  const ledgerCase = cases.find((c) => c.customer === ledger);
  const ledgerEntries = useCaseLedger(ledgerCase?.id);
  const modifyTarget = cases.find((c) => c.customer === modify);

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Collections & Recovery AI Swarm"
        subtitle="Multi-agent collections system that predicts, recommends, checks compliance and learns from repayment outcomes."
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {metrics.map((m) => (
          <div key={m.label} className="glass rounded-xl p-3">
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
              {m.label}
            </div>
            <div className="mt-1 text-lg font-semibold text-gradient-mahindra">{m.value}</div>
          </div>
        ))}
      </div>

      <Panel title="Agent Swarm">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          {agents.map((a) => (
            <div key={a.name} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
              <div className="text-xs font-semibold">{a.name}</div>
              <div className="mt-2">
                <StatPill
                  tone={
                    a.status === "Active"
                      ? "success"
                      : a.status === "Recommended"
                        ? "info"
                        : "warning"
                  }
                >
                  {a.status}
                </StatPill>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Customer Prioritization">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-[10px] uppercase tracking-widest text-muted-foreground">
              <tr className="border-b border-white/10">
                <th className="pb-2 text-left">Customer</th>
                <th className="pb-2 text-left">DPD</th>
                <th className="pb-2 text-left">Outstanding</th>
                <th className="pb-2 text-left">Roll-fwd risk</th>
                <th className="pb-2 text-left">Best channel</th>
                <th className="pb-2 text-left">Action</th>
                <th className="pb-2 text-left">Prob.</th>
                <th className="pb-2 text-left">Compliance</th>
                <th className="pb-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr
                  key={c.customer}
                  className="border-b border-white/5 last:border-0 hover:bg-white/[0.03]"
                >
                  <td className="py-3">{c.customer}</td>
                  <td>{c.dpd}</td>
                  <td>{c.out}</td>
                  <td>
                    <StatPill tone={c.roll > 70 ? "danger" : c.roll > 50 ? "warning" : "success"}>
                      {c.roll}%
                    </StatPill>
                  </td>
                  <td className="text-xs">{c.channel}</td>
                  <td className="text-xs">{c.action}</td>
                  <td>{c.prob}%</td>
                  <td>
                    <StatPill
                      tone={
                        c.flag === "Escalate"
                          ? "danger"
                          : c.flag === "Review"
                            ? "warning"
                            : "success"
                      }
                    >
                      {c.flag}
                    </StatPill>
                  </td>
                  <td className="text-right">
                    <div className="inline-flex gap-1">
                      <button
                        title="Approve"
                        onClick={() => {
                          if (c.id) approveCase(c.id);
                          setRow((s) => ({ ...s, [c.customer]: "Approved" }));
                          toast.success(`${c.customer} · Approved`);
                        }}
                        className="rounded-md border border-white/10 p-1.5 hover:border-emerald-500/40 hover:bg-emerald-500/10"
                      >
                        <Check className="h-3.5 w-3.5" />
                      </button>
                      <button
                        title="Modify"
                        onClick={() => setModify(c.customer)}
                        className="rounded-md border border-white/10 p-1.5 hover:border-primary/40 hover:bg-primary/10"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        title="Human review"
                        onClick={() => {
                          if (c.id) reviewCase(c.id);
                          setRow((s) => ({ ...s, [c.customer]: "Human Review" }));
                          toast("Sent to human review");
                        }}
                        className="rounded-md border border-white/10 p-1.5 hover:border-white/40 hover:bg-white/10"
                      >
                        <UserCog className="h-3.5 w-3.5" />
                      </button>
                      <button
                        title="Trust ledger"
                        onClick={() => setLedger(c.customer)}
                        className="rounded-md border border-white/10 p-1.5 hover:border-primary/40 hover:bg-primary/10"
                      >
                        <FileSearch className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    {row[c.customer] && (
                      <div className="mt-1 text-[10px] text-muted-foreground">
                        {row[c.customer]}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="glass-strong rounded-2xl p-4 text-xs">
        <span className="font-semibold text-primary">Business Impact: </span>
        Lower NPAs, higher recovery, better customer treatment and improved field productivity.
      </div>

      <Dialog open={!!ledger} onOpenChange={(o) => !o && setLedger(null)}>
        <DialogContent className="max-w-lg border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Trust Ledger · {ledger}</DialogTitle>
          </DialogHeader>
          <ol className="space-y-2 text-sm">
            {(
              ledgerEntries ?? [
                "Data sources: DPD, income stability, past behavior",
                "Model output: restructuring recommended",
                "Key drivers: 3-month income variability + prior 30-DPD",
                "Compliance check: passed",
                "Human decision: approved",
                "Feedback: awaiting outcome",
              ]
            ).map((s) => (
              <li key={s} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                {s}
              </li>
            ))}
          </ol>
        </DialogContent>
      </Dialog>

      <Dialog open={!!modify} onOpenChange={(o) => !o && setModify(null)}>
        <DialogContent className="max-w-md border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Modify Action · {modify}</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 text-sm">
            {[
              "Digital-first outreach",
              "Voice + WhatsApp",
              "Field visit + settlement",
              "Escalate to legal",
            ].map((o) => (
              <button
                key={o}
                onClick={() => {
                  if (modifyTarget?.id) modifyCase(modifyTarget.id, o);
                  toast.success(`Action updated · ${o}`);
                  setModify(null);
                }}
                className="w-full rounded-lg border border-white/10 bg-white/[0.03] p-3 text-left hover:border-primary/40 hover:bg-primary/10"
              >
                {o}
              </button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
