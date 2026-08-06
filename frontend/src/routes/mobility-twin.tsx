import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Panel, SectionTitle, StatPill } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { useAskAnswer, useMobilityGraph, useMobilityKpis } from "@/hooks/use-api";
import { askMobilityTwin } from "@/lib/api/endpoints";

export const Route = createFileRoute("/mobility-twin")({
  head: () => ({ meta: [{ title: "Auto Mobility Twin · Mahindra AI Command Center" }] }),
  component: MobilityTwin,
});

const KPIS = [
  { l: "Lead → booking conversion", v: "17.4%", t: "+2.1 pts" },
  { l: "Test drive completion", v: "72%", t: "+4%" },
  { l: "Cancellation risk", v: "6.8%", t: "-1.2 pts" },
  { l: "Delivery delay", v: "9.4 d", t: "-3.1 d" },
  { l: "Warranty risk", v: "Low", t: "stable" },
  { l: "Finance approval rate", v: "78%", t: "+3%" },
  { l: "Dealer follow-up leakage", v: "12%", t: "-4%" },
];

type Node = {
  id: string;
  x: number;
  y: number;
  metric: string;
  trend: string;
  drivers: string[];
  action: string;
};

const NODES: Node[] = [
  {
    id: "Campaign Spend",
    x: 50,
    y: 60,
    metric: "₹4.2 Cr",
    trend: "+8%",
    drivers: ["Digital-heavy allocation", "Regional festive push"],
    action: "Reallocate 12% to programmatic",
  },
  {
    id: "Lead Quality",
    x: 180,
    y: 60,
    metric: "Score 72",
    trend: "+4",
    drivers: ["Better source mix", "Improved landing pages"],
    action: "Increase retargeting",
  },
  {
    id: "Dealer Follow-up",
    x: 320,
    y: 60,
    metric: "SLA 74%",
    trend: "+6%",
    drivers: ["NBA adoption", "WhatsApp templates"],
    action: "Escalate stale leads > 2h",
  },
  {
    id: "Test Drive",
    x: 460,
    y: 60,
    metric: "72% completion",
    trend: "+4%",
    drivers: ["AI scheduler", "SMS reminders"],
    action: "Add Sunday slots",
  },
  {
    id: "Booking",
    x: 600,
    y: 60,
    metric: "17.4%",
    trend: "+2.1",
    drivers: ["Exchange bonus", "Finance TAT"],
    action: "Bundle offers",
  },
  {
    id: "Finance Approval",
    x: 50,
    y: 180,
    metric: "78%",
    trend: "+3%",
    drivers: ["Alt-data model", "Faster KYC"],
    action: "Pre-approve rural",
  },
  {
    id: "Vehicle Allocation",
    x: 180,
    y: 180,
    metric: "89% utilization",
    trend: "+5%",
    drivers: ["Demand model", "Dealer capacity"],
    action: "Rebalance West",
  },
  {
    id: "Delivery Delay",
    x: 320,
    y: 180,
    metric: "9.4 d",
    trend: "-3.1d",
    drivers: ["Reduced waiting", "Better allocation"],
    action: "Monitor Q1",
  },
  {
    id: "Customer Satisfaction",
    x: 460,
    y: 180,
    metric: "NPS 62",
    trend: "+5",
    drivers: ["Delivery experience", "Service quality"],
    action: "Expand digital handover",
  },
  {
    id: "Service Experience",
    x: 600,
    y: 180,
    metric: "82% CSAT",
    trend: "+3%",
    drivers: ["Bay utilization", "AR technician guide"],
    action: "Roll out to 40 more dealers",
  },
  {
    id: "Warranty Claims",
    x: 180,
    y: 300,
    metric: "Batch B-2214 flagged",
    trend: "spike",
    drivers: ["Component supplier variance"],
    action: "Quarantine batch",
  },
  {
    id: "Repeat Purchase",
    x: 460,
    y: 300,
    metric: "24%",
    trend: "+2%",
    drivers: ["Loyalty program", "Cross-sell"],
    action: "Bundle insurance renewal",
  },
];

const EDGES: [string, string][] = [
  ["Campaign Spend", "Lead Quality"],
  ["Lead Quality", "Dealer Follow-up"],
  ["Dealer Follow-up", "Test Drive"],
  ["Test Drive", "Booking"],
  ["Finance Approval", "Booking"],
  ["Booking", "Vehicle Allocation"],
  ["Vehicle Allocation", "Delivery Delay"],
  ["Delivery Delay", "Customer Satisfaction"],
  ["Service Experience", "Customer Satisfaction"],
  ["Customer Satisfaction", "Repeat Purchase"],
  ["Warranty Claims", "Customer Satisfaction"],
  ["Service Experience", "Warranty Claims"],
];

const ASKS = [
  {
    q: "Why did bookings drop in Pune?",
    a: "Bookings dropped due to follow-up leakage at 2 Pune dealers (47%), competitor promo (28%), finance TAT (15%). Recommend: exchange bonus + follow-up SLA.",
  },
  {
    q: "What is causing delivery delay in West Zone?",
    a: "West Zone waiting is elevated by uneven allocation between Pune/Nashik vs Nagpur (63% of delay). Reallocate 120 units.",
  },
  {
    q: "Which factor has highest impact on cancellation?",
    a: "Finance approval TAT (>4 days) explains 41% of cancellations. Pre-approval for low-risk rural cuts it by 22%.",
  },
  {
    q: "How can we improve finance-assisted conversions?",
    a: "Pair thin-file credit twin with dealer NBA. Expected +6.4% conversion, -2.1% NPA risk.",
  },
];

function MobilityTwin() {
  const apiKpis = useMobilityKpis();
  const kpis = apiKpis?.map((k) => ({ l: k.label, v: k.value, t: k.trend })) ?? KPIS;
  const apiGraph = useMobilityGraph();
  const nodes: Node[] =
    apiGraph?.nodes.map((n) => ({
      id: n.label,
      x: n.x,
      y: n.y,
      metric: n.metric,
      trend: n.trend,
      drivers: n.drivers,
      action: n.action,
    })) ?? NODES;
  const edges = apiGraph?.edges ?? EDGES;
  const ask = useAskAnswer(askMobilityTwin);
  const [sel, setSel] = useState<Node | null>(null);
  const active = sel ?? nodes[4] ?? null;
  const [ans, setAns] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Auto Mobility Causal Decision Twin"
        subtitle="Connect demand, production, dealers, finance, service, warranty and customer experience into one causal intelligence layer."
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[280px_1fr_320px]">
        <Panel title="Business Health">
          <div className="space-y-2">
            {kpis.map((k) => (
              <div key={k.l} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  {k.l}
                </div>
                <div className="mt-1 flex items-center justify-between">
                  <span className="text-sm font-semibold">{k.v}</span>
                  <StatPill tone="success">{k.t}</StatPill>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          title="Causal Graph"
          subtitle="Click any node to inspect drivers, trend and downstream impact."
        >
          <div className="relative overflow-x-auto">
            <svg viewBox="0 0 700 380" className="w-full min-w-[700px]">
              <defs>
                <marker
                  id="arrow"
                  viewBox="0 0 10 10"
                  refX="8"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="oklch(0.72 0.22 27)" />
                </marker>
              </defs>
              {edges.map(([a, b]) => {
                const na = nodes.find((n) => n.id === a)!;
                const nb = nodes.find((n) => n.id === b)!;
                return (
                  <line
                    key={a + b}
                    x1={na.x + 55}
                    y1={na.y + 20}
                    x2={nb.x + 5}
                    y2={nb.y + 20}
                    stroke="oklch(1 0 0 / 0.25)"
                    strokeWidth="1.5"
                    markerEnd="url(#arrow)"
                  />
                );
              })}
              {nodes.map((n) => {
                const activeNode = active?.id === n.id;
                return (
                  <g key={n.id} onClick={() => setSel(n)} className="cursor-pointer">
                    <rect
                      x={n.x}
                      y={n.y}
                      width={120}
                      height={40}
                      rx={10}
                      fill={activeNode ? "oklch(0.58 0.22 27 / 0.35)" : "oklch(1 0 0 / 0.04)"}
                      stroke={activeNode ? "oklch(0.72 0.22 27)" : "oklch(1 0 0 / 0.15)"}
                      strokeWidth={activeNode ? 2 : 1}
                    />
                    <text
                      x={n.x + 60}
                      y={n.y + 24}
                      textAnchor="middle"
                      fontSize="10"
                      fill="white"
                      fontWeight={activeNode ? "600" : "400"}
                    >
                      {n.id}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
          {active && (
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  {active.id}
                </div>
                <div className="mt-1 text-lg font-semibold">{active.metric}</div>
                <div className="text-xs text-emerald-300">{active.trend}</div>
              </div>
              <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  Top drivers
                </div>
                <ul className="mt-1 space-y-1 text-xs">
                  {active.drivers.map((d) => (
                    <li key={d}>• {d}</li>
                  ))}
                </ul>
              </div>
              <div className="sm:col-span-2 rounded-lg border border-primary/30 bg-primary/10 p-3 text-xs">
                <span className="font-semibold text-primary">Recommended action: </span>
                {active.action}
              </div>
            </div>
          )}
        </Panel>

        <Panel title="Ask Causal Twin">
          <div className="space-y-2">
            {ASKS.map((a) => (
              <Button
                key={a.q}
                variant="outline"
                onClick={() => ask(a.q, a.a, setAns)}
                className="w-full justify-start border-white/10 text-left text-xs font-normal whitespace-normal h-auto py-2"
              >
                {a.q}
              </Button>
            ))}
          </div>
          {ans && (
            <div className="mt-4 rounded-lg border border-primary/30 bg-primary/10 p-3 text-xs">
              <div className="text-[10px] uppercase tracking-widest text-primary mb-1">
                AI Answer
              </div>
              {ans}
            </div>
          )}
        </Panel>
      </div>

      <div className="glass-strong rounded-2xl p-4 text-xs">
        <span className="font-semibold text-primary">AI Differentiator: </span>
        Causal AI explains <em>why</em> outcomes move, not only <em>what</em> moved — enabling
        boardroom-quality decisions.
      </div>
    </div>
  );
}
