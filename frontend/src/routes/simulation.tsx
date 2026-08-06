import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
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
import { Play, Zap, FileText, Check } from "lucide-react";
import {
  useAutoSalesSim,
  useCausalDrivers,
  useCollectionsSim,
  useCreditPricingSim,
  useDealerAllocationSim,
  useLogisticsDelaySim,
  useSimulationMeta,
} from "@/hooks/use-api";
import type { AutoSalesSimIn, CollectionsSimIn, LogisticsDelaySimIn } from "@/lib/api/types";
import { ExecutiveSummaryModal } from "@/components/executive-summary";

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

const FALLBACK_DRIVERS = [
  "Historical elasticity (finance approval, exchange bonus)",
  "Regional propensity model output",
  "Dealer capacity + waiting-list dynamics",
  "Competitor promo signal",
  "Weather / calendar events",
];

function useSimShell(name: string, domain: string) {
  const [explainOpen, setExplainOpen] = useState(false);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [approved, setApproved] = useState(false);
  const drivers = useCausalDrivers(domain, explainOpen);
  return {
    Actions: (
      <div className="mt-6 flex flex-wrap gap-2">
        <Button
          onClick={() => toast.success("Simulation refreshed")}
          className="gap-1 mahindra-gradient text-white"
        >
          <Play className="h-3.5 w-3.5" /> Run Simulation
        </Button>
        <Button
          variant="outline"
          onClick={() => setExplainOpen(true)}
          className="gap-1 border-white/10"
        >
          <Zap className="h-3.5 w-3.5" /> Explain Drivers
        </Button>
        <Button
          variant="outline"
          onClick={() => setSummaryOpen(true)}
          className="gap-1 border-white/10"
        >
          <FileText className="h-3.5 w-3.5" /> Generate Executive Summary
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            setApproved(true);
            toast.success("Recommendation approved · Trust Ledger updated");
          }}
          className="gap-1 border-white/10"
        >
          <Check className="h-3.5 w-3.5" /> {approved ? "Approved" : "Approve Recommendation"}
        </Button>
      </div>
    ),
    Modals: (
      <>
        <Dialog open={explainOpen} onOpenChange={setExplainOpen}>
          <DialogContent className="max-w-lg border-white/10 bg-background/95">
            <DialogHeader>
              <DialogTitle className="text-gradient-mahindra">Causal drivers · {name}</DialogTitle>
            </DialogHeader>
            <div className="space-y-2 text-sm">
              {(drivers?.drivers ?? FALLBACK_DRIVERS).map((d) => (
                <div key={d} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                  {d}
                </div>
              ))}
            </div>
          </DialogContent>
        </Dialog>
        <ExecutiveSummaryModal open={summaryOpen} onOpenChange={setSummaryOpen} useCase={name} />
      </>
    ),
  };
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
  const shell = useSimShell("Auto Sales Simulation", "auto-sales");

  const localOut = useMemo(() => {
    const regionBoost = region === "West" ? 1.15 : region === "North" ? 1.08 : 1.0;
    const intensityMul = intensity === "High" ? 1.25 : intensity === "Medium" ? 1.1 : 1.0;
    const uplift = Math.round(
      (discount[0] * 1.4 + bonus[0] / 6000 + campaign[0] * 3) * regionBoost * intensityMul,
    );
    const margin = Math.round(-(discount[0] * 1.1) - campaign[0] * 0.3);
    const cancel = Math.max(0, Math.round(10 - intensityMul * 4 - bonus[0] / 20000));
    const rev = Math.round(uplift * 3.2 + margin * 1.8);
    const conf = Math.min(97, 72 + Math.round(intensityMul * 8 + regionBoost * 6));
    return { uplift, margin, cancel, rev, conf };
  }, [region, model, discount, bonus, campaign, intensity]);

  const apiOut = useAutoSalesSim({
    region,
    model,
    discount: discount[0],
    bonus: bonus[0],
    campaign: campaign[0],
    intensity: intensity as AutoSalesSimIn["intensity"],
  });
  const out = apiOut ?? localOut;

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
        {shell.Actions}
      </Panel>

      <Panel
        title="Predicted Outputs"
        actions={<StatPill tone="info">Confidence {out.conf}%</StatPill>}
      >
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
          {apiOut?.recommendedAction ?? (
            <>
              Deploy exchange bonus ₹{bonus[0].toLocaleString("en-IN")} in {region} for {model} with{" "}
              {intensity.toLowerCase()} follow-up.
            </>
          )}
        </div>
      </Panel>
      {shell.Modals}
    </div>
  );
}

function DealerAlloc() {
  const [units, setUnits] = useState([120]);
  const [demand, setDemand] = useState([70]);
  const [capacity, setCapacity] = useState([80]);
  const [wait, setWait] = useState([14]);
  const shell = useSimShell("Dealer Allocation Simulation", "dealer-allocation");
  const localOut = {
    delay: Math.max(1, wait[0] - Math.round((demand[0] + capacity[0]) / 20)),
    rev: Math.round(units[0] * (demand[0] / 100) * 18),
    csat: Math.min(95, 70 + Math.round(capacity[0] / 5)),
  };
  const apiOut = useDealerAllocationSim({
    units: units[0],
    demand: demand[0],
    capacity: capacity[0],
    wait: wait[0],
  });
  const out = apiOut ?? localOut;
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
        {shell.Actions}
      </Panel>
      <Panel title="Recommended Allocation">
        <div className="grid grid-cols-2 gap-3">
          <Metric label="Delay reduction" value={`-${out.delay}d`} tone="success" />
          <Metric label="Revenue impact" value={`₹${out.rev} L`} tone="success" />
          <Metric label="CSAT" value={`${out.csat}`} tone="info" />
          <Metric
            label="Suggested split"
            value={apiOut?.suggestedSplit ?? "West 45% · North 30% · South 25%"}
            tone="default"
          />
        </div>
      </Panel>
      {shell.Modals}
    </div>
  );
}

function CollectionsSim() {
  const [risk, setRisk] = useState("Medium");
  const [channel, setChannel] = useState("Digital");
  const [offer, setOffer] = useState("Restructure");
  const [field, setField] = useState([40]);
  const shell = useSimShell("Finance Collections Simulation", "collections");
  const prob = { Low: 82, Medium: 68, High: 42 }[risk] || 60;
  const localOut = {
    prob,
    cost: channel === "Field" ? 1200 + field[0] * 8 : channel === "Voice" ? 320 : 90,
    friction: channel === "Field" ? 62 : channel === "Voice" ? 34 : 12,
    net: Math.round(prob * (offer === "Settlement" ? 0.7 : 1.0) * 42),
  };
  const apiOut = useCollectionsSim({
    risk: risk as CollectionsSimIn["risk"],
    channel: channel as CollectionsSimIn["channel"],
    offer: offer as CollectionsSimIn["offer"],
    field: field[0],
  });
  const out = apiOut ?? localOut;
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
                {["Digital", "Voice", "Field"].map((c) => (
                  <SelectItem key={c} value={c}>
                    {c}
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
                {["Restructure", "Waiver", "Settlement", "None"].map((o) => (
                  <SelectItem key={o} value={o}>
                    {o}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
          <Row label={`Field visit intensity: ${field[0]}%`}>
            <Slider min={0} max={100} value={field} onValueChange={setField} />
          </Row>
        </div>
        {shell.Actions}
      </Panel>
      <Panel title="Predicted Recovery">
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
      </Panel>
      {shell.Modals}
    </div>
  );
}

function LogisticsSim() {
  const [route, setRoute] = useState("Mumbai → Pune");
  const [warehouse, setWarehouse] = useState([60]);
  const [vehicle, setVehicle] = useState([70]);
  const [weather, setWeather] = useState([20]);
  const [sla, setSla] = useState("High");
  const shell = useSimShell("Logistics Delay Simulation", "logistics-delay");
  const localOut = {
    delay: Math.min(95, warehouse[0] * 0.3 + weather[0] * 0.4 + (100 - vehicle[0]) * 0.2),
    breach: sla === "High" ? 42 + weather[0] / 3 : 18 + weather[0] / 4,
    reroute: "Via Panvel bypass",
    cost: Math.round(warehouse[0] * 320 + weather[0] * 480),
  };
  const apiOut = useLogisticsDelaySim({
    route,
    warehouse: warehouse[0],
    vehicle: vehicle[0],
    weather: weather[0],
    sla: sla as LogisticsDelaySimIn["sla"],
  });
  const out = apiOut ?? localOut;
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Panel title="Inputs">
        <div className="space-y-4">
          <Row label="Route">
            <Select value={route} onValueChange={setRoute}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[
                  "Mumbai → Pune",
                  "Chennai → Bengaluru",
                  "Delhi → Jaipur",
                  "Mundra Port → NCR",
                  "Kolkata → Guwahati",
                ].map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
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
          <Row label="SLA priority">
            <Select value={sla} onValueChange={setSla}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {["Low", "Medium", "High"].map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
        </div>
        {shell.Actions}
      </Panel>
      <Panel title="Predicted Impact">
        <div className="grid grid-cols-2 gap-3">
          <Metric
            label="Delay probability"
            value={`${Math.round(out.delay)}%`}
            tone={out.delay > 50 ? "danger" : "warning"}
          />
          <Metric
            label="SLA breach risk"
            value={`${Math.round(out.breach)}%`}
            tone={out.breach > 40 ? "danger" : "success"}
          />
          <Metric label="Recommended reroute" value={out.reroute} tone="info" />
          <Metric
            label="Cost impact"
            value={`₹${out.cost.toLocaleString("en-IN")}`}
            tone="warning"
          />
        </div>
      </Panel>
      {shell.Modals}
    </div>
  );
}

function CreditPricing() {
  const [type, setType] = useState("Carbon");
  const [supply, setSupply] = useState([50]);
  const [demand, setDemand] = useState([60]);
  const [trace, setTrace] = useState([70]);
  const [verif, setVerif] = useState([65]);
  const shell = useSimShell("Circularity Credit Pricing Simulation", "credit-pricing");
  const price = Math.round(800 + demand[0] * 15 + trace[0] * 6 - supply[0] * 5);
  const closure = Math.min(95, 30 + demand[0] * 0.4 + trace[0] * 0.3 - supply[0] * 0.15);
  const match = Math.min(98, 40 + demand[0] * 0.5 + verif[0] * 0.2);
  const apiOut = useCreditPricingSim({
    type,
    supply: supply[0],
    demand: demand[0],
    trace: trace[0],
    verif: verif[0],
  });
  const complianceRisk =
    apiOut?.complianceRisk ?? (verif[0] < 40 ? "High" : verif[0] < 70 ? "Medium" : "Low");
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
                {["CD", "EPR", "SDG", "Carbon"].map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
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
        {shell.Actions}
      </Panel>
      <Panel title="Recommended Pricing">
        <div className="grid grid-cols-2 gap-3">
          <Metric
            label="Price band"
            value={
              apiOut
                ? `₹${apiOut.priceBandLow} – ₹${apiOut.priceBandHigh}`
                : `₹${price - 60} – ₹${price + 60}`
            }
            tone="success"
          />
          <Metric
            label="Trade closure prob."
            value={`${Math.round(apiOut?.closure ?? closure)}%`}
            tone="info"
          />
          <Metric
            label="Buyer match"
            value={`${Math.round(apiOut?.match ?? match)}%`}
            tone="success"
          />
          <Metric
            label="Compliance risk"
            value={complianceRisk}
            tone={
              complianceRisk === "High"
                ? "danger"
                : complianceRisk === "Medium"
                  ? "warning"
                  : "success"
            }
          />
        </div>
      </Panel>
      {shell.Modals}
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
