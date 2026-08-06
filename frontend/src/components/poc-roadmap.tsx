import { useApp } from "@/lib/app-context";
import { Panel } from "@/components/ui/panel";
import { useRoadmapPlan } from "@/hooks/use-api";
import { Trash2, Rocket } from "lucide-react";
import { toast } from "sonner";
import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const FALLBACK_PHASES = [
  {
    p: "Phase 0",
    t: "Discovery",
    w: "1-2 weeks",
    d: "Align sponsors, data readiness, success metrics.",
  },
  {
    p: "Phase 1",
    t: "Prototype",
    w: "3-4 weeks",
    d: "Working prototype on real data slice, human-approved.",
  },
  {
    p: "Phase 2",
    t: "PoC",
    w: "6-8 weeks",
    d: "End-to-end closed loop with trust ledger + HITL.",
  },
  {
    p: "Phase 3",
    t: "Production Pilot",
    w: "8-12 weeks",
    d: "Scale to one BU / region, measure impact.",
  },
];

const FALLBACK_TOP_POCS = [
  "AI Simulation Center",
  "Dealer Revenue Optimizer",
  "Financial Services AI Command Center",
];

export function PoCRoadmapPanel() {
  const { poc, removePoc } = useApp();
  const plan = useRoadmapPlan();
  const phases = plan?.phases ?? FALLBACK_PHASES;
  const topPocs = plan?.topPocs ?? FALLBACK_TOP_POCS;
  const optional = plan?.optional ?? "Circular Economy Intelligence Platform";
  const [open, setOpen] = useState(false);

  const priorities = ["High", "High", "Medium", "Medium", "Low"];
  const complexity = ["Medium", "Low", "Medium", "High", "Medium"];

  return (
    <Panel
      title="PoC Roadmap"
      subtitle="Shortlist and generate an executive rollout plan."
      actions={
        <button
          onClick={() => {
            if (poc.length === 0) {
              toast.error("Add solutions from the catalogue first");
              return;
            }
            setOpen(true);
          }}
          className="inline-flex items-center gap-1.5 rounded-full mahindra-gradient px-3 py-1.5 text-xs font-semibold text-white shadow-lg shadow-red-900/30 hover:opacity-90"
        >
          <Rocket className="h-3.5 w-3.5" /> Generate PoC Roadmap
        </button>
      }
    >
      {poc.length === 0 ? (
        <div className="rounded-lg border border-dashed border-white/10 p-6 text-center text-xs text-muted-foreground">
          No solutions added yet. Click <span className="text-foreground">Add to PoC Roadmap</span>{" "}
          on any solution card.
        </div>
      ) : (
        <div className="space-y-2">
          {poc.map((p, i) => (
            <div
              key={p.name}
              className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.03] p-3"
            >
              <div>
                <div className="text-sm font-medium">{p.name}</div>
                <div className="mt-0.5 text-[10px] uppercase tracking-widest text-muted-foreground">
                  {p.bucket} · Priority {priorities[i % 5]} · Complexity {complexity[i % 5]}
                </div>
              </div>
              <button
                onClick={() => {
                  removePoc(p.name);
                  toast("Removed from PoC roadmap");
                }}
                className="rounded-md p-2 text-muted-foreground hover:bg-white/5 hover:text-destructive"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Recommended PoC Roadmap</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {phases.map((ph) => (
              <div
                key={ph.p}
                className="flex items-center gap-4 rounded-lg border border-white/10 bg-white/[0.03] p-3"
              >
                <div className="w-20 text-xs uppercase tracking-widest text-primary">{ph.p}</div>
                <div className="flex-1">
                  <div className="text-sm font-semibold">{ph.t}</div>
                  <div className="text-xs text-muted-foreground">{ph.d}</div>
                </div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  {ph.w}
                </div>
              </div>
            ))}
            <div className="mt-4 rounded-lg border border-primary/30 bg-primary/10 p-3">
              <div className="text-xs font-semibold text-primary uppercase tracking-widest">
                Top 3 recommended PoCs
              </div>
              <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">
                {topPocs.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ol>
              <div className="mt-2 text-xs text-muted-foreground">Optional: {optional}</div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </Panel>
  );
}
