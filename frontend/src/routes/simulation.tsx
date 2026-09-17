import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Panel, SectionTitle, MiniBar, StatPill } from "@/components/ui/panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Play, Zap, FileText, Check, Loader2 } from "lucide-react";
import {
  useApproveSimulationRun,
  useGenerateSimulationRunSummary,
  useRunAutoSalesSim,
  useRunCollectionsSim,
  useRunCreditPricingSim,
  useRunDealerAllocationSim,
  useRunLogisticsDelaySim,
  useSimulationMeta,
  useSimulationRunDrivers,
} from "@/hooks/use-api";
import type {
  AutoSalesSimIn,
  CollectionsSimIn,
  CreditPricingSimIn,
  LogisticsDelaySimIn,
  SimulationCausalEdgeItem,
  SimulationDriverItem,
} from "@/lib/api/types";

// Reference options while the simulation metadata loads.
const REGIONS = ["West", "North", "South", "East"] as const;
const MODELS = ["XUV700", "Scorpio-N", "Thar", "Bolero", "XUV 3XO"] as const;

export const Route = createFileRoute("/simulation")({
  head: () => ({ meta: [{ title: "Simulation Center · Mahindra AI Command Center" }] }),
  component: Simulation,
});

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</div>
      {children}
    </div>
  );
}

/** Explain Drivers for Auto Sales: real predictive contribution (trained
 * model) kept visibly separate from causal evidence (PCMCI over the real
 * business panel) — never captioned as the same thing. */
function SimulationDriversDialog({
  open,
  onOpenChange,
  runId,
  title,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  runId: string | undefined;
  title: string;
}) {
  const { data, isPending, isError } = useSimulationRunDrivers(runId, open);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto border-white/10 bg-background/95">
        <DialogHeader>
          <DialogTitle className="text-gradient-mahindra">Explain Drivers · {title}</DialogTitle>
        </DialogHeader>
        {isPending && (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading evidence…
          </div>
        )}
        {isError && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
            Failed to load drivers. Check backend logs.
          </div>
        )}
        {data && (
          <div className="space-y-4 text-sm">
            <div>
              <div className="mb-2 text-[10px] uppercase tracking-widest text-primary">
                Predictive contribution (this simulation)
              </div>
              <div className="space-y-2">
                {data.predictive_drivers.map((driver: SimulationDriverItem) => (
                  <div key={driver.name} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{driver.name}</span>
                      <StatPill tone={driver.source === "trained_model" ? "info" : "warning"}>
                        {driver.source === "trained_model" ? "Trained model" : "Calibrated assumption"}
                      </StatPill>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">{driver.detail}</div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-2 text-[10px] uppercase tracking-widest text-primary">
                Causal evidence (historical, PCMCI)
              </div>
              {data.causal_evidence.length === 0 ? (
                <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-muted-foreground">
                  {data.causal_evidence_note}
                </div>
              ) : (
                <div className="space-y-2">
                  {data.causal_evidence.map((edge: SimulationCausalEdgeItem, index: number) => (
                    <div
                      key={`${edge.source}-${edge.target}-${index}`}
                      className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs"
                    >
                      <span className="font-medium">{edge.source}</span> → <span className="font-medium">{edge.target}</span>{" "}
                      (lag {edge.lag_days}d, p={edge.p_value.toFixed(3)})
                    </div>
                  ))}
                  <div className="text-[11px] text-muted-foreground">{data.causal_evidence_note}</div>
                </div>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Executive summary: built only from this run's own persisted evidence —
 * never a generic pitch template. */
function SimulationSummaryDialog({
  open,
  onOpenChange,
  runId,
  title,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  runId: string | undefined;
  title: string;
}) {
  const { data, isPending, isError } = useGenerateSimulationRunSummary(runId, open);
  const rows: [string, string | undefined][] = data
    ? [
        ["Scenario", data.scenario],
        ["Inputs", data.inputs_summary],
        ["Baseline", data.baseline],
        ["Predicted outcome", data.predicted_outcome],
        ["Major drivers", data.major_drivers.join(", ")],
        ["Trade-off", data.trade_off],
        ["Recommendation", data.recommendation],
        ["Confidence", data.confidence],
        ["Risk / dependency", data.risk],
      ]
    : [];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto border-white/10 bg-background/95">
        <DialogHeader>
          <DialogTitle className="text-gradient-mahindra">Executive Summary · {title}</DialogTitle>
        </DialogHeader>
        {isPending && (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Generating summary…
          </div>
        )}
        {isError && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
            Summary generation failed. Check backend logs.
          </div>
        )}
        {data && (
          <div className="space-y-3 text-sm">
            {rows.map(([k, v]) => (
              <div key={k} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <div className="text-[10px] uppercase tracking-widest text-primary">{k}</div>
                <div className="mt-1 text-foreground/90">{v}</div>
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function AutoSales() {
  const meta = useSimulationMeta();
  const regions = meta?.regions ?? REGIONS;
  const models = meta?.models ?? MODELS;
  const [region, setRegion] = useState<string>("West");
  const [model, setModel] = useState<string>("XUV700");
  const [discount, setDiscount] = useState([3]);
  const [bonus, setBonus] = useState([25000]);
  const [campaign, setCampaign] = useState([1.5]);
  const [intensity, setIntensity] = useState("Medium");

  const runSim = useRunAutoSalesSim();
  const approveSim = useApproveSimulationRun();
  const [approved, setApproved] = useState(false);
  const out = runSim.data;

  const handleRun = () => {
    setApproved(false);
    runSim.mutate({
      region,
      model,
      discount: discount[0],
      bonus: bonus[0],
      campaign: campaign[0],
      intensity: intensity as AutoSalesSimIn["intensity"],
    });
  };

  const handleApprove = () => {
    if (!out) return;
    approveSim.mutate(
      { runId: out.run_id },
      {
        onSuccess: () => {
          setApproved(true);
          toast.success("Recommendation approved · Trust Ledger updated");
        },
        onError: () => toast.error("Approval failed. Check backend logs."),
      },
    );
  };

  const [explainOpen, setExplainOpen] = useState(false);
  const [summaryOpen, setSummaryOpen] = useState(false);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Panel title="Inputs">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Row label="Region">
              <Select value={region} onValueChange={setRegion}>
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {regions.map((r) => (
                    <SelectItem key={r} value={r}>
                      {r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Row>
            <Row label="Model">
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {models.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Row>
          </div>
          <Row label={`Discount ${discount[0]}%`}>
            <Slider min={0} max={10} step={0.5} value={discount} onValueChange={setDiscount} />
          </Row>
          <Row label={`Exchange bonus ₹${bonus[0].toLocaleString("en-IN")}`}>
            <Slider min={0} max={75000} step={2500} value={bonus} onValueChange={setBonus} />
          </Row>
          <Row label={`Campaign spend ₹${campaign[0]} Cr`}>
            <Slider min={0} max={5} step={0.1} value={campaign} onValueChange={setCampaign} />
          </Row>
          <Row label="Dealer follow-up intensity">
            <Select value={intensity} onValueChange={setIntensity}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {["Low", "Medium", "High"].map((i) => (
                  <SelectItem key={i} value={i}>
                    {i}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
        </div>
        <div className="mt-6 flex flex-wrap gap-2">
          <Button
            onClick={handleRun}
            disabled={runSim.isPending}
            className="gap-1 mahindra-gradient text-white"
          >
            {runSim.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {runSim.isPending ? "Running…" : "Run Simulation"}
          </Button>
          <Button
            variant="outline"
            onClick={() => setExplainOpen(true)}
            disabled={!out}
            className="gap-1 border-white/10"
          >
            <Zap className="h-3.5 w-3.5" /> Explain Drivers
          </Button>
          <Button
            variant="outline"
            onClick={() => setSummaryOpen(true)}
            disabled={!out}
            className="gap-1 border-white/10"
          >
            <FileText className="h-3.5 w-3.5" /> Generate Executive Summary
          </Button>
          <Button
            variant="outline"
            onClick={handleApprove}
            disabled={!out || approved || approveSim.isPending}
            className="gap-1 border-white/10"
          >
            <Check className="h-3.5 w-3.5" />{" "}
            {approved ? "Approved" : approveSim.isPending ? "Approving…" : "Approve Recommendation"}
          </Button>
        </div>
      </Panel>

      <Panel
        title="Predicted Outputs"
        actions={out ? <StatPill tone="info">Confidence {out.conf}%</StatPill> : undefined}
      >
        {runSim.isPending && (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Running simulation…
          </div>
        )}
        {runSim.isError && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
            Simulation failed. Check backend logs.
          </div>
        )}
        {!runSim.isPending && !runSim.isError && !out && (
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-muted-foreground">
            Run a simulation to see predicted impact.
          </div>
        )}
        {out && !runSim.isPending && !runSim.isError && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Metric label="Booking uplift" value={`+${out.uplift}%`} tone="success" />
              <Metric
                label="Margin impact"
                value={`${out.margin}%`}
                tone={out.margin < -3 ? "danger" : "warning"}
              />
              <Metric
                label="Cancellation risk"
                value={`${out.cancel}%`}
                tone={out.cancel > 6 ? "warning" : "success"}
              />
              <Metric label="Net revenue impact" value={`₹${out.rev} Cr`} tone="success" />
            </div>
            <div className="mt-4">
              <MiniBar
                data={[
                  { label: "Bookings", value: 50 + out.uplift * 2 },
                  { label: "Margin", value: 50 + out.margin * 2 },
                  { label: "Cancel", value: 50 - out.cancel * 3 },
                ]}
              />
            </div>
            <div className="mt-4 rounded-lg border border-primary/30 bg-primary/10 p-3 text-xs">
              <span className="font-semibold text-primary">Recommended action: </span>
              {out.recommendedAction}
            </div>
          </>
        )}
      </Panel>
      <SimulationDriversDialog
        open={explainOpen}
        onOpenChange={setExplainOpen}
        runId={out?.run_id}
        title="Auto Sales Simulation"
      />
      <SimulationSummaryDialog
        open={summaryOpen}
        onOpenChange={setSummaryOpen}
        runId={out?.run_id}
        title="Auto Sales Simulation"
      />
    </div>
  );
}

function DealerAlloc() {
  const [units, setUnits] = useState([120]);
  const [demand, setDemand] = useState([70]);
  const [capacity, setCapacity] = useState([80]);
  const [wait, setWait] = useState([14]);

  const runSim = useRunDealerAllocationSim();
  const approveSim = useApproveSimulationRun();
  const [approved, setApproved] = useState(false);
  const [explainOpen, setExplainOpen] = useState(false);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const out = runSim.data;

  const handleRun = () => {
    setApproved(false);
    runSim.mutate({ units: units[0], demand: demand[0], capacity: capacity[0], wait: wait[0] });
  };

  const handleApprove = () => {
    if (!out) return;
    approveSim.mutate(
      { runId: out.run_id },
      {
        onSuccess: () => {
          setApproved(true);
          toast.success("Recommendation approved · Trust Ledger updated");
        },
        onError: () => toast.error("Approval failed. Check backend logs."),
      },
    );
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Panel title="Inputs">
        <div className="space-y-4">
          <Row label={`Units available: ${units[0]}`}>
            <Slider min={20} max={400} step={10} value={units} onValueChange={setUnits} />
          </Row>
          <Row label={`Region demand intensity: ${demand[0]}%`}>
            <Slider min={20} max={100} value={demand} onValueChange={setDemand} />
          </Row>
          <Row label={`Dealer capacity: ${capacity[0]}%`}>
            <Slider min={30} max={100} value={capacity} onValueChange={setCapacity} />
          </Row>
          <Row label={`Waiting period target: ${wait[0]} days`}>
            <Slider min={5} max={45} value={wait} onValueChange={setWait} />
          </Row>
        </div>
        <div className="mt-6 flex flex-wrap gap-2">
          <Button onClick={handleRun} disabled={runSim.isPending} className="gap-1 mahindra-gradient text-white">
            {runSim.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {runSim.isPending ? "Running…" : "Run Simulation"}
          </Button>
          <Button variant="outline" onClick={() => setExplainOpen(true)} disabled={!out} className="gap-1 border-white/10">
            <Zap className="h-3.5 w-3.5" /> Explain Drivers
          </Button>
          <Button variant="outline" onClick={() => setSummaryOpen(true)} disabled={!out} className="gap-1 border-white/10">
            <FileText className="h-3.5 w-3.5" /> Generate Executive Summary
          </Button>
          <Button
            variant="outline"
            onClick={handleApprove}
            disabled={!out || approved || approveSim.isPending}
            className="gap-1 border-white/10"
          >
            <Check className="h-3.5 w-3.5" />{" "}
            {approved ? "Approved" : approveSim.isPending ? "Approving…" : "Approve Recommendation"}
          </Button>
        </div>
      </Panel>
      <Panel title="Recommended Allocation" actions={out ? <StatPill tone="info">Confidence {out.conf}%</StatPill> : undefined}>
        {runSim.isPending && (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Running simulation…
          </div>
        )}
        {runSim.isError && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
            Simulation failed. Check backend logs.
          </div>
        )}
        {!runSim.isPending && !runSim.isError && !out && (
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-muted-foreground">
            Run a simulation to see the recommended allocation.
          </div>
        )}
        {out && !runSim.isPending && !runSim.isError && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Metric label="Delay reduction" value={`-${out.delay}d`} tone="success" />
              <Metric label="Revenue impact" value={`₹${out.rev} L`} tone="success" />
              <Metric label="CSAT" value={`${out.csat}`} tone="info" />
              <Metric label="Suggested split" value={out.suggestedSplit} tone="default" />
            </div>
            <div className="mt-4 rounded-lg border border-primary/30 bg-primary/10 p-3 text-xs">
              <span className="font-semibold text-primary">Recommended action: </span>
              {out.recommendedAction}
            </div>
          </>
        )}
      </Panel>
      <SimulationDriversDialog
        open={explainOpen}
        onOpenChange={setExplainOpen}
        runId={out?.run_id}
        title="Dealer Allocation Simulation"
      />
      <SimulationSummaryDialog
        open={summaryOpen}
        onOpenChange={setSummaryOpen}
        runId={out?.run_id}
        title="Dealer Allocation Simulation"
      />
    </div>
  );
}

// Real recorded categories (see app/repositories/collections_simulation.py)
// — no UI-to-real translation, so every choice trains on genuine
// historical outcomes.
const COLLECTIONS_CHANNEL_OPTIONS = [
  { value: "SMS", label: "SMS" },
  { value: "WHATSAPP", label: "WhatsApp" },
  { value: "EMAIL", label: "Email" },
  { value: "CALL", label: "Call" },
  { value: "FIELD_VISIT", label: "Field Visit" },
] as const;
const COLLECTIONS_OFFER_OPTIONS = [
  { value: "NONE", label: "None" },
  { value: "PAYMENT_REMINDER", label: "Payment Reminder" },
  { value: "PARTIAL_PAYMENT_PLAN", label: "Partial Payment Plan" },
  { value: "REPAYMENT_PLAN_DISCUSSION", label: "Repayment Plan Discussion" },
] as const;

function CollectionsSim() {
  const [risk, setRisk] = useState("Medium");
  const [channel, setChannel] = useState("WHATSAPP");
  const [offer, setOffer] = useState("REPAYMENT_PLAN_DISCUSSION");
  const [field, setField] = useState([40]);

  const runSim = useRunCollectionsSim();
  const approveSim = useApproveSimulationRun();
  const [approved, setApproved] = useState(false);
  const [explainOpen, setExplainOpen] = useState(false);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const out = runSim.data;

  const handleRun = () => {
    setApproved(false);
    runSim.mutate({
      risk: risk as CollectionsSimIn["risk"],
      channel: channel as CollectionsSimIn["channel"],
      offer: offer as CollectionsSimIn["offer"],
      field: field[0],
    });
  };

  const handleApprove = () => {
    if (!out) return;
    approveSim.mutate(
      { runId: out.run_id },
      {
        onSuccess: () => {
          setApproved(true);
          toast.success("Recommendation approved · Trust Ledger updated");
        },
        onError: () => toast.error("Approval failed. Check backend logs."),
      },
    );
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Panel title="Inputs">
        <div className="space-y-4">
          <Row label="Customer risk segment">
            <Select value={risk} onValueChange={setRisk}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {["Low", "Medium", "High"].map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
          <Row label="Contact channel">
            <Select value={channel} onValueChange={setChannel}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {COLLECTIONS_CHANNEL_OPTIONS.map((c) => (
                  <SelectItem key={c.value} value={c.value}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
          <Row label="Offer type">
            <Select value={offer} onValueChange={setOffer}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {COLLECTIONS_OFFER_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
          <Row label={`Field visit intensity: ${field[0]}%`}>
            <Slider min={0} max={100} value={field} onValueChange={setField} />
          </Row>
        </div>
        <div className="mt-6 flex flex-wrap gap-2">
          <Button onClick={handleRun} disabled={runSim.isPending} className="gap-1 mahindra-gradient text-white">
            {runSim.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {runSim.isPending ? "Running…" : "Run Simulation"}
          </Button>
          <Button variant="outline" onClick={() => setExplainOpen(true)} disabled={!out} className="gap-1 border-white/10">
            <Zap className="h-3.5 w-3.5" /> Explain Drivers
          </Button>
          <Button variant="outline" onClick={() => setSummaryOpen(true)} disabled={!out} className="gap-1 border-white/10">
            <FileText className="h-3.5 w-3.5" /> Generate Executive Summary
          </Button>
          <Button
            variant="outline"
            onClick={handleApprove}
            disabled={!out || approved || approveSim.isPending}
            className="gap-1 border-white/10"
          >
            <Check className="h-3.5 w-3.5" />{" "}
            {approved ? "Approved" : approveSim.isPending ? "Approving…" : "Approve Recommendation"}
          </Button>
        </div>
      </Panel>
      <Panel title="Predicted Recovery" actions={out ? <StatPill tone="info">Confidence {out.conf}%</StatPill> : undefined}>
        {runSim.isPending && (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Running simulation…
          </div>
        )}
        {runSim.isError && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
            Simulation failed. Check backend logs.
          </div>
        )}
        {!runSim.isPending && !runSim.isError && !out && (
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-muted-foreground">
            Run a simulation to see predicted recovery.
          </div>
        )}
        {out && !runSim.isPending && !runSim.isError && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Metric label="Recovery probability" value={`${out.prob}%`} tone="success" />
              <Metric label="Cost of recovery" value={`₹${out.cost}`} tone="warning" />
              <Metric
                label="Friction score"
                value={`${out.friction}`}
                tone={out.friction > 40 ? "danger" : "success"}
              />
              <Metric label="Net recovery value" value={`₹${out.net}K`} tone="success" />
            </div>
            <div className="mt-4 rounded-lg border border-primary/30 bg-primary/10 p-3 text-xs">
              <span className="font-semibold text-primary">Recommended action: </span>
              {out.recommendedAction}
            </div>
          </>
        )}
      </Panel>
      <SimulationDriversDialog
        open={explainOpen}
        onOpenChange={setExplainOpen}
        runId={out?.run_id}
        title="Finance Collections Simulation"
      />
      <SimulationSummaryDialog
        open={summaryOpen}
        onOpenChange={setSummaryOpen}
        runId={out?.run_id}
        title="Finance Collections Simulation"
      />
    </div>
  );
}

// Real recorded priority categories on `shipments.priority` (see
// app/repositories/logistics_delay_simulation.py) — no UI-to-real
// translation, unlike the retired invented "Low/Medium/High" SLA scale.
const LOGISTICS_PRIORITY_OPTIONS = [
  { value: "LOW", label: "Low" },
  { value: "NORMAL", label: "Normal" },
  { value: "HIGH", label: "High" },
  { value: "CRITICAL", label: "Critical" },
] as const;

function LogisticsSim() {
  const meta = useSimulationMeta();
  const routes = meta?.routes ?? [];
  const [route, setRoute] = useState("");
  const [warehouse, setWarehouse] = useState([60]);
  const [vehicle, setVehicle] = useState([70]);
  const [weather, setWeather] = useState([20]);
  const [sla, setSla] = useState("HIGH");

  // Routes are real ids fetched from the backend (no plausible default can
  // be guessed client-side) — select the first one once meta loads.
  useEffect(() => {
    if (!route && routes.length > 0) setRoute(routes[0].id);
  }, [route, routes]);

  const runSim = useRunLogisticsDelaySim();
  const approveSim = useApproveSimulationRun();
  const [approved, setApproved] = useState(false);
  const [explainOpen, setExplainOpen] = useState(false);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const out = runSim.data;

  const handleRun = () => {
    if (!route) return;
    setApproved(false);
    runSim.mutate({
      route,
      warehouse: warehouse[0],
      vehicle: vehicle[0],
      weather: weather[0],
      sla: sla as LogisticsDelaySimIn["sla"],
    });
  };

  const handleApprove = () => {
    if (!out) return;
    approveSim.mutate(
      { runId: out.run_id },
      {
        onSuccess: () => {
          setApproved(true);
          toast.success("Recommendation approved · Trust Ledger updated");
        },
        onError: () => toast.error("Approval failed. Check backend logs."),
      },
    );
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Panel title="Inputs">
        <div className="space-y-4">
          <Row label="Route">
            <Select value={route} onValueChange={setRoute}>
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Loading routes…" />
              </SelectTrigger>
              <SelectContent>
                {routes.map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    {r.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
          <Row label={`Warehouse load: ${warehouse[0]}%`}>
            <Slider min={0} max={100} value={warehouse} onValueChange={setWarehouse} />
          </Row>
          <Row label={`Vehicle availability: ${vehicle[0]}%`}>
            <Slider min={20} max={100} value={vehicle} onValueChange={setVehicle} />
          </Row>
          <Row label={`Weather disruption: ${weather[0]}%`}>
            <Slider min={0} max={100} value={weather} onValueChange={setWeather} />
          </Row>
          <Row label="Priority">
            <Select value={sla} onValueChange={setSla}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LOGISTICS_PRIORITY_OPTIONS.map((p) => (
                  <SelectItem key={p.value} value={p.value}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
        </div>
        <div className="mt-6 flex flex-wrap gap-2">
          <Button
            onClick={handleRun}
            disabled={runSim.isPending || !route}
            className="gap-1 mahindra-gradient text-white"
          >
            {runSim.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {runSim.isPending ? "Running…" : "Run Simulation"}
          </Button>
          <Button variant="outline" onClick={() => setExplainOpen(true)} disabled={!out} className="gap-1 border-white/10">
            <Zap className="h-3.5 w-3.5" /> Explain Drivers
          </Button>
          <Button variant="outline" onClick={() => setSummaryOpen(true)} disabled={!out} className="gap-1 border-white/10">
            <FileText className="h-3.5 w-3.5" /> Generate Executive Summary
          </Button>
          <Button
            variant="outline"
            onClick={handleApprove}
            disabled={!out || approved || approveSim.isPending}
            className="gap-1 border-white/10"
          >
            <Check className="h-3.5 w-3.5" />{" "}
            {approved ? "Approved" : approveSim.isPending ? "Approving…" : "Approve Recommendation"}
          </Button>
        </div>
      </Panel>
      <Panel title="Predicted Impact" actions={out ? <StatPill tone="info">Confidence {out.conf}%</StatPill> : undefined}>
        {runSim.isPending && (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Running simulation…
          </div>
        )}
        {runSim.isError && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
            Simulation failed. Check backend logs.
          </div>
        )}
        {!runSim.isPending && !runSim.isError && !out && (
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-muted-foreground">
            Run a simulation to see the predicted delay/breach impact.
          </div>
        )}
        {out && !runSim.isPending && !runSim.isError && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Metric label="Delay probability" value={`${out.delay}%`} tone={out.delay > 50 ? "danger" : "warning"} />
              <Metric label="SLA breach risk" value={`${out.breach}%`} tone={out.breach > 40 ? "danger" : "success"} />
              <Metric label="Recommended reroute" value={out.reroute} tone="info" />
              <Metric label="Cost impact" value={`₹${out.cost.toLocaleString("en-IN")}`} tone="warning" />
            </div>
            <div className="mt-4 rounded-lg border border-primary/30 bg-primary/10 p-3 text-xs">
              <span className="font-semibold text-primary">Recommended action: </span>
              {out.recommendedAction}
            </div>
          </>
        )}
      </Panel>
      <SimulationDriversDialog
        open={explainOpen}
        onOpenChange={setExplainOpen}
        runId={out?.run_id}
        title="Logistics Delay Simulation"
      />
      <SimulationSummaryDialog
        open={summaryOpen}
        onOpenChange={setSummaryOpen}
        runId={out?.run_id}
        title="Logistics Delay Simulation"
      />
    </div>
  );
}

// Real recorded categories on `credit_listings.credit_type` (see
// app/repositories/credit_pricing_simulation.py) — no UI-to-real
// translation, unlike the retired invented "Carbon/EPR/SDG/CD" scale.
const CREDIT_TYPE_OPTIONS = [
  { value: "MIXED_CIRCULARITY", label: "Mixed Circularity" },
  { value: "RECYCLING_AVOIDANCE", label: "Recycling Avoidance" },
  { value: "REUSE_AVOIDANCE", label: "Reuse Avoidance" },
] as const;

function CreditPricing() {
  const [type, setType] = useState("REUSE_AVOIDANCE");
  const [supply, setSupply] = useState([50]);
  const [demand, setDemand] = useState([60]);
  const [trace, setTrace] = useState([70]);
  const [verif, setVerif] = useState([65]);

  const runSim = useRunCreditPricingSim();
  const approveSim = useApproveSimulationRun();
  const [approved, setApproved] = useState(false);
  const [explainOpen, setExplainOpen] = useState(false);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const out = runSim.data;

  const handleRun = () => {
    setApproved(false);
    runSim.mutate({
      type: type as CreditPricingSimIn["type"],
      supply: supply[0],
      demand: demand[0],
      trace: trace[0],
      verif: verif[0],
    });
  };

  const handleApprove = () => {
    if (!out) return;
    approveSim.mutate(
      { runId: out.run_id },
      {
        onSuccess: () => {
          setApproved(true);
          toast.success("Recommendation approved · Trust Ledger updated");
        },
        onError: () => toast.error("Approval failed. Check backend logs."),
      },
    );
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Panel title="Inputs">
        <div className="space-y-4">
          <Row label="Credit type">
            <Select value={type} onValueChange={setType}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CREDIT_TYPE_OPTIONS.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
          <Row label={`Supply level: ${supply[0]}%`}>
            <Slider min={10} max={100} value={supply} onValueChange={setSupply} />
          </Row>
          <Row label={`Buyer demand: ${demand[0]}%`}>
            <Slider min={10} max={100} value={demand} onValueChange={setDemand} />
          </Row>
          <Row label={`Traceability score: ${trace[0]}%`}>
            <Slider min={10} max={100} value={trace} onValueChange={setTrace} />
          </Row>
          <Row label={`Verification readiness: ${verif[0]}%`}>
            <Slider min={10} max={100} value={verif} onValueChange={setVerif} />
          </Row>
        </div>
        <div className="mt-6 flex flex-wrap gap-2">
          <Button onClick={handleRun} disabled={runSim.isPending} className="gap-1 mahindra-gradient text-white">
            {runSim.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {runSim.isPending ? "Running…" : "Run Simulation"}
          </Button>
          <Button variant="outline" onClick={() => setExplainOpen(true)} disabled={!out} className="gap-1 border-white/10">
            <Zap className="h-3.5 w-3.5" /> Explain Drivers
          </Button>
          <Button variant="outline" onClick={() => setSummaryOpen(true)} disabled={!out} className="gap-1 border-white/10">
            <FileText className="h-3.5 w-3.5" /> Generate Executive Summary
          </Button>
          <Button
            variant="outline"
            onClick={handleApprove}
            disabled={!out || approved || approveSim.isPending}
            className="gap-1 border-white/10"
          >
            <Check className="h-3.5 w-3.5" />{" "}
            {approved ? "Approved" : approveSim.isPending ? "Approving…" : "Approve Recommendation"}
          </Button>
        </div>
      </Panel>
      <Panel title="Recommended Pricing" actions={out ? <StatPill tone="info">Confidence {out.conf}%</StatPill> : undefined}>
        {runSim.isPending && (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Running simulation…
          </div>
        )}
        {runSim.isError && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
            Simulation failed. Check backend logs.
          </div>
        )}
        {!runSim.isPending && !runSim.isError && !out && (
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs text-muted-foreground">
            Run a simulation to see the recommended pricing.
          </div>
        )}
        {out && !runSim.isPending && !runSim.isError && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Metric label="Price band" value={`₹${out.priceBandLow} – ₹${out.priceBandHigh}`} tone="success" />
              <Metric label="Trade closure prob." value={`${out.closure}%`} tone="info" />
              <Metric label="Buyer match" value={`${out.match}%`} tone="success" />
              <Metric
                label="Compliance risk"
                value={out.complianceRisk}
                tone={out.complianceRisk === "High" ? "danger" : out.complianceRisk === "Medium" ? "warning" : "success"}
              />
            </div>
            <div className="mt-4 rounded-lg border border-primary/30 bg-primary/10 p-3 text-xs">
              <span className="font-semibold text-primary">Recommended action: </span>
              {out.recommendedAction}
            </div>
          </>
        )}
      </Panel>
      <SimulationDriversDialog
        open={explainOpen}
        onOpenChange={setExplainOpen}
        runId={out?.run_id}
        title="Circularity Credit Pricing Simulation"
      />
      <SimulationSummaryDialog
        open={summaryOpen}
        onOpenChange={setSummaryOpen}
        runId={out?.run_id}
        title="Circularity Credit Pricing Simulation"
      />
    </div>
  );
}

function Metric({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "success" | "warning" | "danger" | "info";
}) {
  const map: Record<string, string> = {
    default: "text-foreground",
    success: "text-emerald-300",
    warning: "text-amber-300",
    danger: "text-red-300",
    info: "text-sky-300",
  };
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
      <div className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</div>
      <div className={`mt-1 text-lg font-semibold ${map[tone]}`}>{value}</div>
    </div>
  );
}

function Simulation() {
  return (
    <div className="space-y-6">
      <SectionTitle
        title="AI Simulation Center"
        subtitle="Test business decisions before spending money, moving inventory or changing operations."
      />

      <div className="glass-strong rounded-2xl p-4 text-xs">
        <span className="font-semibold text-primary">AI Differentiator: </span>
        Unlike standard dashboards, this simulation engine combines predictive modeling, causal
        graphs, optimization and human approval to guide decisions before execution.
      </div>

      <Tabs defaultValue="auto">
        <TabsList className="flex-wrap justify-start bg-white/[0.03] border border-white/10">
          <TabsTrigger value="auto">Auto Sales</TabsTrigger>
          <TabsTrigger value="dealer">Dealer Allocation</TabsTrigger>
          <TabsTrigger value="coll">Collections</TabsTrigger>
          <TabsTrigger value="log">Logistics Delay</TabsTrigger>
          <TabsTrigger value="credit">Credit Pricing</TabsTrigger>
        </TabsList>
        <TabsContent value="auto" className="mt-6">
          <AutoSales />
        </TabsContent>
        <TabsContent value="dealer" className="mt-6">
          <DealerAlloc />
        </TabsContent>
        <TabsContent value="coll" className="mt-6">
          <CollectionsSim />
        </TabsContent>
        <TabsContent value="log" className="mt-6">
          <LogisticsSim />
        </TabsContent>
        <TabsContent value="credit" className="mt-6">
          <CreditPricing />
        </TabsContent>
      </Tabs>
    </div>
  );
}
