import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Panel, SectionTitle, StatPill } from "@/components/ui/panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import {
  useAskAnswer,
  useCredits,
  useDmrvPrompts,
  useElvEstimate,
  useMatchCreditBuyer,
  useRepriceCredit,
  useRvsfMetrics,
} from "@/hooks/use-api";
import { askDmrv } from "@/lib/api/endpoints";
import { toast } from "sonner";

export const Route = createFileRoute("/circularity")({
  head: () => ({ meta: [{ title: "Circular Economy Intelligence · Mahindra AI Command Center" }] }),
  component: Circularity,
});

function Circularity() {
  return (
    <div className="space-y-6">
      <SectionTitle
        title="Circular Economy Intelligence Platform"
        subtitle="AI for ELV valuation, RVSF operations, credit pricing, dMRV readiness and ESG monetization."
      />

      <Tabs defaultValue="elv">
        <TabsList className="flex-wrap justify-start bg-white/[0.03] border border-white/10">
          <TabsTrigger value="elv">ELV Assessment</TabsTrigger>
          <TabsTrigger value="rvsf">RVSF Operations</TabsTrigger>
          <TabsTrigger value="mkt">Credit Marketplace</TabsTrigger>
          <TabsTrigger value="dmrv">dMRV Copilot</TabsTrigger>
        </TabsList>
        <TabsContent value="elv" className="mt-6">
          <ELV />
        </TabsContent>
        <TabsContent value="rvsf" className="mt-6">
          <RVSF />
        </TabsContent>
        <TabsContent value="mkt" className="mt-6">
          <Marketplace />
        </TabsContent>
        <TabsContent value="dmrv" className="mt-6">
          <DMRV />
        </TabsContent>
      </Tabs>

      <div className="glass-strong rounded-2xl p-4 text-xs">
        <span className="font-semibold text-primary">AI Differentiator: </span>
        Turns scrappage and recycling data into priced, trusted and tradable sustainability value.
      </div>
    </div>
  );
}

function ELV() {
  const [type, setType] = useState("SUV");
  const [age, setAge] = useState([12]);
  const [cond, setCond] = useState([60]);
  const [docs, setDocs] = useState([80]);
  const estimate = useElvEstimate({
    vehicleType: type,
    age: age[0],
    condition: cond[0],
    docs: docs[0],
  });
  const price =
    estimate?.price ?? Math.round(80000 - age[0] * 3800 + cond[0] * 350 + docs[0] * 120);
  const rec = estimate?.recoverable ?? Math.round(price * 0.7);
  const risks =
    estimate?.risks ?? (docs[0] < 60 ? ["Incomplete RC", "Missing insurance papers"] : ["OK"]);
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Panel title="Inputs">
        <div className="space-y-3">
          <Field label="Vehicle type">
            <Select value={type} onValueChange={setType}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {["Hatch", "Sedan", "SUV", "Pickup", "Tractor"].map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label={`Age: ${age[0]} years`}>
            <Slider min={1} max={25} value={age} onValueChange={setAge} />
          </Field>
          <Field label={`Condition score: ${cond[0]}`}>
            <Slider min={0} max={100} value={cond} onValueChange={setCond} />
          </Field>
          <Field label={`Documents complete: ${docs[0]}%`}>
            <Slider min={0} max={100} value={docs} onValueChange={setDocs} />
          </Field>
        </div>
      </Panel>
      <Panel title="Recommended Valuation">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <Metric
            label="Suggested ELV price"
            value={`₹${price.toLocaleString("en-IN")}`}
            tone="success"
          />
          <Metric label="Recoverable value" value={`₹${rec.toLocaleString("en-IN")}`} tone="info" />
        </div>
        <div className="mt-3 rounded-lg border border-white/10 bg-white/[0.03] p-3 text-xs">
          <div className="text-muted-foreground uppercase tracking-widest text-[10px]">
            Risk flags / missing
          </div>
          <ul className="mt-1 space-y-1">
            {risks.map((r) => (
              <li key={r}>• {r}</li>
            ))}
          </ul>
        </div>
      </Panel>
    </div>
  );
}

const RVSF_FALLBACK = [
  { label: "Job-card delay prediction", value: "2.4 hrs", tone: "warning" },
  { label: "Throughput", value: "141 vehicles / day", tone: "success" },
  { label: "Bottleneck", value: "De-pollution bay", tone: "danger" },
  { label: "dMRV completeness", value: "78%", tone: "warning" },
  { label: "Compliance risk", value: "Low", tone: "success" },
];

function RVSF() {
  const rows = useRvsfMetrics() ?? RVSF_FALLBACK;
  return (
    <Panel title="RVSF Operations Intelligence">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
        {rows.map((m) => (
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
  );
}

function Marketplace() {
  const credits = useCredits();
  const reprice = useRepriceCredit();
  const matchBuyer = useMatchCreditBuyer();
  return (
    <Panel title="Credit Marketplace">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-[10px] uppercase tracking-widest text-muted-foreground">
            <tr className="border-b border-white/10">
              <th className="pb-2 text-left">Credit ID</th>
              <th className="pb-2">Type</th>
              <th className="pb-2">Price</th>
              <th className="pb-2">Buyer match</th>
              <th className="pb-2">Closure prob.</th>
              <th className="pb-2">Traceability</th>
              <th className="pb-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {credits.map((c) => (
              <tr key={c.id} className="border-b border-white/5 last:border-0">
                <td className="py-3">{c.id}</td>
                <td className="text-center">
                  <StatPill tone="info">{c.type}</StatPill>
                </td>
                <td className="text-center">{c.price}</td>
                <td className="text-center">{c.match}</td>
                <td className="text-center">{c.closure}%</td>
                <td className="text-center">{c.trace}</td>
                <td className="text-right">
                  <div className="inline-flex gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-white/10 h-7 text-xs"
                      onClick={() => {
                        reprice(c.id);
                        toast.success(`Repriced ${c.id}`);
                      }}
                    >
                      Reprice
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-white/10 h-7 text-xs"
                      onClick={() => {
                        matchBuyer(c.id);
                        toast.success(`Buyer matched for ${c.id}`);
                      }}
                    >
                      Match Buyer
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-white/10 h-7 text-xs"
                      onClick={() => toast("ESG report generated")}
                    >
                      ESG Report
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-white/10 h-7 text-xs"
                      onClick={() => toast("Traceability opened")}
                    >
                      Trace
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

const DMRV_FALLBACK = [
  {
    q: "Estimate carbon credits for this batch.",
    a: "Estimated 214 tCO2e from batch RVSF-Nagpur-Q3, of which 182 are verification-ready.",
  },
  {
    q: "Which fields are incomplete?",
    a: "Missing: origin geo-tag, weight tickets for 12 vehicles, technician attestation for 4 units.",
  },
  {
    q: "Is this verification-ready?",
    a: "78% ready — after adding origin geo-tags, verification confidence rises to 92%.",
  },
  {
    q: "Generate audit summary.",
    a: "Audit summary generated. 5 batches, 214 tCO2e, 91% traceable, 3 pending human reviews.",
  },
];

function DMRV() {
  const [ans, setAns] = useState<string | null>(null);
  const apiPrompts = useDmrvPrompts();
  const ask = useAskAnswer(askDmrv);
  const prompts =
    apiPrompts?.map((q) => ({ q, a: DMRV_FALLBACK.find((p) => p.q === q)?.a ?? "" })) ??
    DMRV_FALLBACK;
  return (
    <Panel title="dMRV Copilot">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {prompts.map((p) => (
          <Button
            key={p.q}
            variant="outline"
            onClick={() => ask(p.q, p.a, setAns)}
            className="justify-start border-white/10 text-left text-xs whitespace-normal h-auto py-2"
          >
            {p.q}
          </Button>
        ))}
      </div>
      {ans && (
        <div className="mt-4 rounded-lg border border-primary/30 bg-primary/10 p-3 text-sm">
          {ans}
        </div>
      )}
    </Panel>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-widest text-muted-foreground mb-1">
        {label}
      </div>
      {children}
    </div>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "success" | "info";
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
      <div className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</div>
      <div
        className={`mt-1 text-lg font-semibold ${tone === "success" ? "text-emerald-300" : "text-sky-300"}`}
      >
        {value}
      </div>
    </div>
  );
}
