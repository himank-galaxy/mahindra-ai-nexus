import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Panel, SectionTitle, StatPill } from "@/components/ui/panel";
import { useAgents, useWorkflowRun, type AiAgentView } from "@/hooks/use-api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Play, Bot } from "lucide-react";

export const Route = createFileRoute("/agents")({
  head: () => ({ meta: [{ title: "AI Factory Agent Registry · Mahindra AI Command Center" }] }),
  component: AgentsPage,
});

const FLOW = [
  "Data Agent",
  "Prediction Agent",
  "Causal Agent",
  "Simulation Agent",
  "Compliance Agent",
  "Human Review",
  "Action Agent",
  "Learning Agent",
];
const STAGE_MSG: Record<string, string> = {
  "Data Agent": "Fetching data",
  "Prediction Agent": "Forecasting outcome",
  "Causal Agent": "Explaining drivers",
  "Simulation Agent": "Testing scenarios",
  "Compliance Agent": "Checking rules",
  "Human Review": "Awaiting approval",
  "Action Agent": "Ready to execute",
  "Learning Agent": "Feedback captured",
};

function AgentsPage() {
  const agents = useAgents();
  const workflowRun = useWorkflowRun();
  const [inspect, setInspect] = useState<AiAgentView | null>(null);
  const [flowStep, setFlowStep] = useState<number>(-1);
  const [running, setRunning] = useState(false);
  const [liveMsg, setLiveMsg] = useState<Record<string, string>>({});

  async function run() {
    setRunning(true);
    setFlowStep(0);
    const result = await workflowRun();
    if (result) {
      setLiveMsg(Object.fromEntries(result.stages.map((s) => [s.stage, s.message])));
    }
    const interval = result?.intervalMs ?? 700;
    let i = 0;
    const tick = () => {
      i++;
      if (i >= FLOW.length) {
        setRunning(false);
        return;
      }
      setFlowStep(i);
      setTimeout(tick, interval);
    };
    setTimeout(tick, interval);
  }

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Mahindra AI Factory Agent Registry"
        subtitle="Multi-agent AI orchestration with memory, guardrails, human approval and learning loops."
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
        {agents.map((a) => (
          <div key={a.name} className="glass rounded-2xl p-4 hover:border-primary/30">
            <div className="flex items-center justify-between">
              <div className="grid h-9 w-9 place-items-center rounded-lg mahindra-gradient">
                <Bot className="h-4 w-4 text-white" />
              </div>
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
            <div className="mt-3 text-sm font-semibold">{a.name}</div>
            <div className="mt-1 text-xs text-muted-foreground">{a.role}</div>
            <div className="mt-2 rounded-md bg-white/[0.03] p-2 text-[11px] text-foreground/70">
              {a.last}
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {a.uses.map((u) => (
                <StatPill key={u}>{u}</StatPill>
              ))}
            </div>
            <Button
              size="sm"
              variant="outline"
              className="mt-3 w-full border-white/10"
              onClick={() => setInspect(a)}
            >
              Inspect Agent
            </Button>
          </div>
        ))}
      </div>

      <Panel
        title="Agent Collaboration Flow"
        actions={
          <Button onClick={run} disabled={running} className="mahindra-gradient text-white gap-1">
            <Play className="h-3.5 w-3.5" /> Run Agent Workflow
          </Button>
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          {FLOW.map((step, i) => (
            <div key={step} className="flex items-center gap-2">
              <div
                className={`rounded-xl border p-3 min-w-[130px] text-center transition-all ${flowStep >= i ? "border-primary bg-primary/20 shadow-lg shadow-red-900/20" : "border-white/10 bg-white/[0.03]"}`}
              >
                <div className="text-xs font-semibold">{step}</div>
                <div
                  className={`mt-1 text-[10px] ${flowStep >= i ? "text-emerald-300" : "text-muted-foreground"}`}
                >
                  {flowStep >= i ? (liveMsg[step] ?? STAGE_MSG[step]) : "Idle"}
                </div>
              </div>
              {i < FLOW.length - 1 && (
                <span
                  className={`text-lg ${flowStep > i ? "text-primary" : "text-muted-foreground"}`}
                >
                  →
                </span>
              )}
            </div>
          ))}
        </div>
      </Panel>

      <div className="glass-strong rounded-2xl p-4 text-xs">
        <span className="font-semibold text-primary">AI Differentiator: </span>
        Multi-agent AI orchestration with memory, guardrails, human approval and learning loops —
        reusable across Mahindra businesses.
      </div>

      <Dialog open={!!inspect} onOpenChange={(o) => !o && setInspect(null)}>
        <DialogContent className="max-w-lg border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">{inspect?.name}</DialogTitle>
          </DialogHeader>
          {inspect && (
            <div className="space-y-2 text-sm">
              <Item k="Agent objective" v={inspect.role} />
              <Item k="Inputs" v="Structured signals + policy + human feedback" />
              <Item k="Outputs" v="Recommendation + explanation + confidence" />
              <Item k="Guardrails" v="Consent · Fairness · Regulation · Business policy" />
              <Item k="Recent decisions" v={inspect.last} />
              <Item k="Human feedback received" v="Approve 78% · Modify 15% · Reject 7%" />
              <Item k="Learning updates" v="Weekly fine-tuning on outcomes" />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
function Item({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
      <div className="text-[10px] uppercase tracking-widest text-muted-foreground">{k}</div>
      <div className="mt-1">{v}</div>
    </div>
  );
}
