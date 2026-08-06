import { useApp } from "@/lib/app-context";
import { X, ChevronLeft, ChevronRight } from "lucide-react";

const STEPS = [
  {
    title: "Welcome",
    body: "Welcome to the Mahindra AI Command Center — a closed-loop AI operating layer across the group.",
  },
  {
    title: "Executive Overview",
    body: "Start here to see group-level AI impact, top recommendations and confidence.",
  },
  {
    title: "Simulation Center",
    body: "Open Simulation Center and test a Pune exchange-bonus scenario for XUV700.",
  },
  {
    title: "Dealer Revenue Optimizer",
    body: "Move to Dealer Revenue Optimizer and prioritize hot leads with next-best-action.",
  },
  {
    title: "Financial Services",
    body: "Open Financial Services AI Command Center and inspect a rural customer's financial twin.",
  },
  {
    title: "Circular Economy",
    body: "Open Circular Economy Intelligence and reprice a batch of carbon credits.",
  },
  {
    title: "Compliance Trust Ledger",
    body: "View the Compliance Trust Ledger to demonstrate AI governance and lineage.",
  },
  {
    title: "AI Factory Agents",
    body: "End with the AI Factory Agent Registry to show reusable, orchestrated AI IP.",
  },
];

export function DemoOverlay() {
  const { demoStep, nextDemo, prevDemo, exitDemo } = useApp();
  if (demoStep === null) return null;
  const step = STEPS[Math.min(demoStep, STEPS.length - 1)];
  const isLast = demoStep >= STEPS.length - 1;

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/50 p-6 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-2xl border border-white/10 bg-background/95 p-6 shadow-2xl">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
              Demo Story · Step {demoStep + 1} / {STEPS.length}
            </div>
            <h3 className="mt-1 text-lg font-semibold text-gradient-mahindra">{step.title}</h3>
          </div>
          <button
            onClick={exitDemo}
            className="rounded-lg p-2 text-muted-foreground hover:bg-white/5"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-3 text-sm text-foreground/80">{step.body}</p>
        <div className="mt-4 h-1 w-full rounded-full bg-white/5">
          <div
            className="h-full rounded-full mahindra-gradient transition-all"
            style={{ width: `${((demoStep + 1) / STEPS.length) * 100}%` }}
          />
        </div>
        <div className="mt-4 flex items-center justify-between">
          <button
            onClick={prevDemo}
            disabled={demoStep === 0}
            className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-foreground/80 hover:bg-white/5 disabled:opacity-40"
          >
            <ChevronLeft className="h-3.5 w-3.5" /> Back
          </button>
          <div className="flex gap-2">
            <button
              onClick={exitDemo}
              className="rounded-lg px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
            >
              Exit
            </button>
            <button
              onClick={isLast ? exitDemo : nextDemo}
              className="inline-flex items-center gap-1 rounded-lg mahindra-gradient px-4 py-1.5 text-xs font-semibold text-white shadow-lg shadow-red-900/30"
            >
              {isLast ? "Finish" : "Next"} <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
