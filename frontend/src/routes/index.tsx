import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  useKpis,
  useRecommendations,
  useUpdateRecommendation,
  type RecommendationView,
} from "@/hooks/use-api";
import type { Kpi } from "@/lib/api/types";
import { Panel, SectionTitle, Sparkline, StatPill } from "@/components/ui/panel";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ArrowUpRight, Eye, PlayCircle, Check, UserCog, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { Link } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Executive Overview · Mahindra AI Command Center" },
      {
        name: "description",
        content:
          "Group-wide AI cockpit — predicted uplift, leakage prevented, recommendations, causal explanations.",
      },
    ],
  }),
  component: Overview,
});

function Overview() {
  const kpiCards = useKpis();
  const recommendations = useRecommendations();
  const updateRecommendation = useUpdateRecommendation();
  const [explain, setExplain] = useState<null | Kpi>(null);
  const [status, setStatus] = useState<Record<string, string>>({});
  const [simRec, setSimRec] = useState<null | RecommendationView>(null);

  const sample = [8, 12, 10, 15, 14, 18, 22, 19, 24, 28, 26, 32];

  return (
    <div className="space-y-8">
      <SectionTitle
        title="Mahindra AI Command Center"
        subtitle="A reusable AI intelligence layer across Auto, Finance, Logistics, Circular Economy, Renewables, Real Estate and Hospitality."
        right={
          <StatPill tone="success">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 pulse-red" /> Live · 42 agents
          </StatPill>
        }
      />

      {/* KPI grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {kpiCards.map((k) => (
          <div
            key={k.id}
            className="group glass rounded-2xl p-5 transition-all hover:border-primary/30 hover:bg-white/[0.05]"
          >
            <div className="flex items-start justify-between">
              <div className="text-[11px] uppercase tracking-widest text-muted-foreground">
                {k.label}
              </div>
              <StatPill tone="info">Conf {k.confidence}%</StatPill>
            </div>
            <div className="mt-3 flex items-end justify-between">
              <div>
                <div className="text-3xl font-bold text-gradient-mahindra">{k.value}</div>
                <div className="mt-1 flex items-center gap-1 text-xs text-emerald-400">
                  <TrendingUp className="h-3 w-3" /> {k.trend}
                </div>
              </div>
              <Sparkline values={sample.map((v) => v + Math.random() * 5)} />
            </div>
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setExplain(k)}
                className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs hover:border-primary/40 hover:bg-primary/10"
              >
                <Eye className="h-3 w-3" /> Explain
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Differentiator banner */}
      <div className="glass-strong flex flex-wrap items-center justify-between gap-4 rounded-2xl p-5">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-primary">
            AI Differentiator
          </div>
          <div className="mt-1 text-sm font-semibold">
            Closed-loop AI: Observe → Predict → Explain → Simulate → Recommend → Approve → Act →
            Learn
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {[
            "Observe",
            "Predict",
            "Explain",
            "Simulate",
            "Recommend",
            "Approve",
            "Act",
            "Learn",
          ].map((s, i) => (
            <span
              key={s}
              className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[11px] uppercase tracking-widest text-foreground/80"
              style={{ animationDelay: `${i * 80}ms` }}
            >
              {s}
            </span>
          ))}
        </div>
      </div>

      {/* Top Recommendations */}
      <Panel
        title="Top AI Recommendations Today"
        subtitle="Approve, simulate or route to human review — every action logged in the Trust Ledger."
      >
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {recommendations.map((r) => {
            const s = status[r.id];
            return (
              <div
                key={r.id}
                className="group rounded-xl border border-white/10 bg-white/[0.03] p-4 transition-all hover:border-primary/30 hover:bg-white/[0.05]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="text-sm font-medium leading-snug">{r.title}</div>
                  <StatPill
                    tone={
                      r.risk === "High" ? "danger" : r.risk === "Medium" ? "warning" : "success"
                    }
                  >
                    {r.risk} risk
                  </StatPill>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
                  <span className="rounded-md bg-primary/15 px-2 py-1 text-primary">
                    {r.impact}
                  </span>
                  <span className="rounded-md bg-white/5 px-2 py-1">
                    Confidence {r.confidence}%
                  </span>
                  {s && (
                    <span className="rounded-md bg-emerald-500/15 px-2 py-1 text-emerald-300">
                      {s}
                    </span>
                  )}
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setSimRec(r)}
                    className="gap-1 border-white/10"
                  >
                    <PlayCircle className="h-3.5 w-3.5" /> Simulate
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => {
                      updateRecommendation(r.id, "Approved");
                      setStatus((s) => ({ ...s, [r.id]: "Approved" }));
                      toast.success("Recommendation approved · logged to Trust Ledger");
                    }}
                    className="gap-1 mahindra-gradient text-white"
                  >
                    <Check className="h-3.5 w-3.5" /> Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      updateRecommendation(r.id, "Under Review");
                      setStatus((s) => ({ ...s, [r.id]: "Under Review" }));
                      toast("Sent to human review");
                    }}
                    className="gap-1 border-white/10"
                  >
                    <UserCog className="h-3.5 w-3.5" /> Human Review
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </Panel>

      {/* Quick links */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          { to: "/simulation", label: "Open Simulation Center" },
          { to: "/dealer", label: "Dealer Optimizer" },
          { to: "/collections", label: "Collections AI Swarm" },
          { to: "/trust", label: "Trust Ledger" },
        ].map((l) => (
          <Link
            key={l.to}
            to={l.to}
            className="glass group flex items-center justify-between rounded-xl p-4 text-sm hover:border-primary/30 hover:bg-white/[0.06]"
          >
            <span>{l.label}</span>
            <ArrowUpRight className="h-4 w-4 text-muted-foreground group-hover:text-primary" />
          </Link>
        ))}
      </div>

      {/* Explain modal */}
      <Dialog open={!!explain} onOpenChange={(o) => !o && setExplain(null)}>
        <DialogContent className="max-w-lg border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">
              AI Explanation — {explain?.label}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="rounded-lg bg-primary/10 p-3 text-sm">
              <span className="font-semibold text-primary">{explain?.value}</span> · Model
              confidence {explain?.confidence}%
            </div>
            <div className="text-xs uppercase tracking-widest text-muted-foreground">
              Causal drivers
            </div>
            <ul className="space-y-2">
              {explain?.drivers.map((d) => (
                <li
                  key={d}
                  className="flex items-start gap-2 rounded-lg border border-white/10 bg-white/[0.03] p-3 text-sm"
                >
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                  {d}
                </li>
              ))}
            </ul>
          </div>
        </DialogContent>
      </Dialog>

      {/* Simulate modal */}
      <Dialog open={!!simRec} onOpenChange={(o) => !o && setSimRec(null)}>
        <DialogContent className="max-w-lg border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Simulation — Prefilled</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Scenario: <span className="text-foreground">{simRec?.title}</span>
          </p>
          <div className="mt-3 space-y-2 text-sm">
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
              Predicted uplift:{" "}
              <span className="text-emerald-300 font-semibold">{simRec?.impact}</span>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
              Confidence: {simRec?.confidence}% · Risk: {simRec?.risk}
            </div>
            <div className="rounded-lg border border-primary/30 bg-primary/10 p-3 text-xs">
              Open the full{" "}
              <Link to="/simulation" className="underline">
                Simulation Center
              </Link>{" "}
              for interactive controls.
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
