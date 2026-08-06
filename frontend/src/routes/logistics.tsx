import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Panel, SectionTitle, StatPill } from "@/components/ui/panel";
import {
  useAutoHeal,
  useLogisticsRoutes,
  usePredictDelay,
  useReroute,
  useWarehouseSignals,
} from "@/hooks/use-api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Wand2, ShieldAlert, Route as RouteIcon, FileText } from "lucide-react";

export const Route = createFileRoute("/logistics")({
  head: () => ({ meta: [{ title: "Logistics AI Control Tower · Mahindra AI Command Center" }] }),
  component: Logistics,
});

const SIGNALS_FALLBACK = [
  { label: "Dock congestion", value: "62%", tone: "warning" },
  { label: "Picking delay", value: "9 min", tone: "warning" },
  { label: "Inventory imbalance", value: "-14%", tone: "danger" },
  { label: "Vehicle availability", value: "78%", tone: "success" },
  { label: "Load utilization", value: "84%", tone: "success" },
];

function Logistics() {
  const routes = useLogisticsRoutes();
  const signals = useWarehouseSignals() ?? SIGNALS_FALLBACK;
  const predictDelay = usePredictDelay();
  const reroute = useReroute();
  const autoHeal = useAutoHeal();
  const [heal, setHeal] = useState<string | null>(null);
  const [rerouted, setRerouted] = useState<Record<string, boolean>>({});
  const healRoute = routes.find((r) => r.name === heal);

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Logistics AI Control Tower"
        subtitle="Predictive + causal logistics monitoring with auto-heal workflows."
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {routes.map((r) => (
          <div key={r.name} className="glass rounded-2xl p-4 hover:border-primary/30">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  Route
                </div>
                <div className="text-sm font-semibold">{r.name}</div>
              </div>
              <StatPill tone={r.slaRisk > 45 ? "danger" : r.slaRisk > 25 ? "warning" : "success"}>
                SLA risk {r.slaRisk}%
              </StatPill>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
              <div className="rounded-md bg-white/5 p-2">
                <div className="text-muted-foreground">Delay prob.</div>
                <div className="font-semibold">{r.delayProb}%</div>
              </div>
              <div className="rounded-md bg-white/5 p-2">
                <div className="text-muted-foreground">Cost</div>
                <div className="font-semibold">{r.cost}</div>
              </div>
              <div className="rounded-md bg-white/5 p-2">
                <div className="text-muted-foreground">Rec.</div>
                <div className="font-semibold truncate">
                  {rerouted[r.name] || r.rerouted ? "Rerouted" : r.action}
                </div>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  if (r.id) predictDelay(r.id);
                  toast.success(`Delay prob updated to ${r.delayProb}%`);
                }}
                className="gap-1 border-white/10"
              >
                <ShieldAlert className="h-3.5 w-3.5" /> Predict Delay
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  if (r.id) reroute(r.id);
                  setRerouted((s) => ({ ...s, [r.name]: true }));
                  toast.success(`Reroute: ${r.action}`);
                }}
                className="gap-1 border-white/10"
              >
                <RouteIcon className="h-3.5 w-3.5" /> Recommend Reroute
              </Button>
              <Button
                size="sm"
                onClick={() => setHeal(r.name)}
                className="gap-1 mahindra-gradient text-white"
              >
                <Wand2 className="h-3.5 w-3.5" /> Auto-Heal
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => toast("SLA risk report generated")}
                className="gap-1 border-white/10"
              >
                <FileText className="h-3.5 w-3.5" /> SLA Report
              </Button>
            </div>
          </div>
        ))}
      </div>

      <Panel title="Warehouse Signals">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {signals.map((m) => (
            <div key={m.label} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                {m.label}
              </div>
              <div className="mt-1 flex items-center justify-between">
                <span className="text-sm font-semibold">{m.value}</span>
                <StatPill tone={m.tone as "success" | "warning" | "danger"}>
                  {m.tone === "success" ? "OK" : m.tone === "warning" ? "Watch" : "Alert"}
                </StatPill>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <div className="glass-strong rounded-2xl p-4 text-xs">
        <span className="font-semibold text-primary">AI Differentiator: </span>
        Predictive + causal logistics monitoring with auto-heal workflows and approval-gated
        execution.
      </div>

      <Dialog open={!!heal} onOpenChange={(o) => !o && setHeal(null)}>
        <DialogContent className="max-w-lg border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">
              Auto-Heal Workflow · {heal}
            </DialogTitle>
          </DialogHeader>
          <ol className="space-y-2 text-sm">
            {[
              "Notify transporter",
              "Reassign vehicle",
              "Update ETA",
              "Alert customer",
              "Monitor SLA",
            ].map((s, i) => (
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
          <Button
            onClick={() => {
              if (healRoute?.id) autoHeal(healRoute.id);
              toast.success("Auto-heal workflow approved & executing");
              setHeal(null);
            }}
            className="mahindra-gradient text-white"
          >
            Approve & Execute
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
