import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Panel, SectionTitle, StatPill } from "@/components/ui/panel";
import {
  useCustomerTwin,
  useFinanceProducts,
  useRmScript,
  useSimulateOffer,
  useSubmitTwinApproval,
  useTwinExplain,
} from "@/hooks/use-api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Slider } from "@/components/ui/slider";
import { ArrowRight, Sparkles, FileText, PlayCircle, Send, Copy } from "lucide-react";

export const Route = createFileRoute("/finance")({
  head: () => ({ meta: [{ title: "Financial Services · Mahindra AI Command Center" }] }),
  component: Finance,
});

function Finance() {
  const products = useFinanceProducts();
  const { twinId, twin } = useCustomerTwin();
  const [explain, setExplain] = useState(false);
  const [pitch, setPitch] = useState(false);
  const [sim, setSim] = useState(false);
  const [offer, setOffer] = useState([450000]);
  const [status, setStatus] = useState("Draft");
  const shownStatus = status === "Draft" ? (twin?.approval_status ?? status) : status;
  const submitApproval = useSubmitTwinApproval();
  const explainData = useTwinExplain(twinId, explain);
  const rmScript = useRmScript(twinId, pitch);
  const simOffer = useSimulateOffer(twinId, offer[0], sim);
  const nbaHeadline = twin?.nba.headline ?? "Offer ₹4.5L pre-approved SME working capital loan";
  const nbaOffer = nbaHeadline.replace(/^Offer\s+/i, "");
  const riskRows: [string, string][] = twin
    ? Object.entries(twin.risk_decomposition)
    : [
        ["Repayment history", "A"],
        ["Alt-data signal", "A-"],
        ["Agri-cycle", "B+"],
        ["Geography", "A"],
      ];
  const crossRows: [string, string][] = twin
    ? Object.entries(twin.cross_sell)
    : [
        ["SME loan", "87%"],
        ["Life insurance", "62%"],
        ["SIP", "41%"],
      ];

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Financial Services AI Command Center"
        subtitle="One intelligence layer across vehicle loans, SME loans, leasing, rural housing, insurance, mutual funds and fixed deposits."
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {products.map((p) => (
          <div key={p.name} className="glass rounded-xl p-4 hover:border-primary/30">
            <div className="text-sm font-semibold">{p.name}</div>
            <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
              <div>
                <div className="text-muted-foreground">Customers</div>
                <div className="font-semibold">{p.customers}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Risk</div>
                <div className="font-semibold">{p.risk}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Cross-sell</div>
                <div className="font-semibold">{p.cross}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Opp.</div>
                <div className="font-semibold">{p.opp}</div>
              </div>
            </div>
            <Button
              size="sm"
              variant="outline"
              className="mt-3 w-full border-white/10 gap-1"
              onClick={() => toast(`Opened ${p.name} workspace`)}
            >
              Open <ArrowRight className="h-3 w-3" />
            </Button>
          </div>
        ))}
      </div>

      <Panel
        title="Customer Financial Twin"
        subtitle="Unified view across products, with explainable risk and cross-sell intelligence."
      >
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ["Name", twin?.name ?? "Suresh Jadhav"],
                ["Location", twin?.location ?? "Sangli, Maharashtra"],
                ["Income stability", twin?.income_stability ?? "Medium-High"],
                ["Repayment", twin?.repayment ?? "Good"],
              ].map(([l, v]) => (
                <div key={l} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                  <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                    {l}
                  </div>
                  <div className="mt-1 text-sm font-semibold">{v}</div>
                </div>
              ))}
            </div>
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4">
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                Products held
              </div>
              <div className="mt-1 flex flex-wrap gap-2">
                {(twin?.products ?? ["Tractor Loan", "Motor Insurance", "Fixed Deposit"]).map(
                  (t) => (
                    <StatPill key={t} tone="info">
                      {t}
                    </StatPill>
                  ),
                )}
              </div>
            </div>
            <div className="rounded-lg border border-primary/30 bg-primary/10 p-4">
              <div className="text-[10px] uppercase tracking-widest text-primary">
                Next Best Action
              </div>
              <div className="mt-1 text-sm">
                Offer <span className="font-semibold">{nbaOffer}</span>
              </div>
              <div className="mt-1 text-xs text-emerald-300">
                Risk: {twin?.nba.risk ?? "Low"} · Expected margin:{" "}
                {twin?.nba.expected_margin ?? "₹42K"} · Confidence {twin?.nba.confidence ?? 87}%
              </div>
              <div className="mt-3">
                Status:{" "}
                <StatPill
                  tone={
                    shownStatus === "Approved"
                      ? "success"
                      : shownStatus === "Under Review"
                        ? "info"
                        : "default"
                  }
                >
                  {shownStatus}
                </StatPill>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => setExplain(true)}
                variant="outline"
                className="gap-1 border-white/10"
              >
                <Sparkles className="h-3.5 w-3.5" /> Explain Recommendation
              </Button>
              <Button
                onClick={() => setPitch(true)}
                variant="outline"
                className="gap-1 border-white/10"
              >
                <FileText className="h-3.5 w-3.5" /> Generate RM Script
              </Button>
              <Button
                onClick={() => setSim(true)}
                variant="outline"
                className="gap-1 border-white/10"
              >
                <PlayCircle className="h-3.5 w-3.5" /> Simulate Offer
              </Button>
              <Button
                onClick={() => {
                  if (twinId) submitApproval(twinId);
                  setStatus("Under Review");
                  toast.success("Sent for approval");
                }}
                className="gap-1 mahindra-gradient text-white"
              >
                <Send className="h-3.5 w-3.5" /> Send for Approval
              </Button>
            </div>
          </div>
          <div className="space-y-3">
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                Risk decomposition
              </div>
              <div className="mt-2 space-y-2 text-xs">
                {riskRows.map(([label, v]) => (
                  <Row key={label} label={label} v={v} />
                ))}
              </div>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                Cross-sell propensity
              </div>
              <div className="mt-2 space-y-2 text-xs">
                {crossRows.map(([label, v]) => (
                  <Row key={label} label={label} v={v} />
                ))}
              </div>
            </div>
          </div>
        </div>
      </Panel>

      <div className="glass-strong rounded-2xl p-4 text-xs">
        <span className="font-semibold text-primary">AI Differentiator: </span>
        One customer financial twin across products, with explainable risk and cross-sell
        intelligence.
      </div>

      <Dialog open={explain} onOpenChange={setExplain}>
        <DialogContent className="max-w-lg border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Why this recommendation</DialogTitle>
          </DialogHeader>
          <ul className="space-y-2 text-sm">
            {(
              explainData?.bullets ?? [
                "Repayment track record on tractor loan (36 EMIs paid on-time)",
                "Agri-cycle signal indicates stable cash-flow next 6 months",
                "Peer benchmarking in Sangli shows +18% growth in SME activity",
                "Insurance renewal + FD balance indicate low credit stress",
              ]
            ).map((d) => (
              <li key={d} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                • {d}
              </li>
            ))}
          </ul>
        </DialogContent>
      </Dialog>

      <Dialog open={pitch} onOpenChange={setPitch}>
        <DialogContent className="max-w-lg border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">RM Script</DialogTitle>
          </DialogHeader>
          <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-sm">
            {rmScript?.script ??
              `Namaste Suresh-ji, based on your excellent repayment record and current SME activity
            around Sangli, we've pre-approved a ₹4.5L working capital loan for you at 10.5% p.a.,
            disbursal within 24 hours. This can help you stock up ahead of the next season. Shall I
            share the digital application link?`}
          </div>
          <Button
            onClick={() => {
              navigator.clipboard?.writeText(rmScript?.script ?? "RM script copied");
              toast.success("Script copied");
            }}
            className="gap-1 mahindra-gradient text-white"
          >
            <Copy className="h-4 w-4" /> Copy Script
          </Button>
        </DialogContent>
      </Dialog>

      <Dialog open={sim} onOpenChange={setSim}>
        <DialogContent className="max-w-md border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Simulate Offer</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
              Loan amount: ₹{offer[0].toLocaleString("en-IN")}
            </div>
            <Slider
              min={100000}
              max={1000000}
              step={25000}
              value={offer}
              onValueChange={setOffer}
            />
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <div className="text-muted-foreground text-xs">EMI</div>
                <div className="font-semibold">
                  ₹
                  {(simOffer
                    ? simOffer.emi
                    : Math.round(offer[0] / 36 + offer[0] * 0.006)
                  ).toLocaleString("en-IN")}
                </div>
              </div>
              <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <div className="text-muted-foreground text-xs">Risk</div>
                <div className="font-semibold text-emerald-300">{simOffer?.risk ?? "Low"}</div>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Row({ label, v }: { label: string; v: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-semibold">{v}</span>
    </div>
  );
}
