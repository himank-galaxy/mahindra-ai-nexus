import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Panel, SectionTitle, StatPill } from "@/components/ui/panel";
import {
  useConvertLead,
  useDealerLeads,
  useDealers,
  useLeadPitch,
  useMessageLead,
  useScheduleTestDrive,
} from "@/hooks/use-api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Copy, Sparkles, Phone, Calendar, Check, MessageCircle } from "lucide-react";

export const Route = createFileRoute("/dealer")({
  head: () => ({ meta: [{ title: "Dealer Revenue Optimizer · Mahindra AI Command Center" }] }),
  component: DealerOpt,
});

function DealerOpt() {
  const dealers = useDealers();
  const [selId, setSelId] = useState<string | null>(null);
  const activeId = selId ?? dealers[0]?.id ?? "";
  const dealer = useMemo(() => dealers.find((d) => d.id === activeId), [dealers, activeId]);
  const leads = useDealerLeads(dealer?.id);
  const messageLead = useMessageLead();
  const convertLead = useConvertLead();
  const scheduleTestDrive = useScheduleTestDrive();
  const [statuses, setStatuses] = useState<Record<string, string>>({});
  const [pitchFor, setPitchFor] = useState<string | null>(null);
  const [tdFor, setTdFor] = useState<string | null>(null);
  const pitchLead = leads.find((l) => l.name === pitchFor);
  const pitch = useLeadPitch(dealer?.id, pitchLead?.id, !!pitchFor);
  const tdLead = leads.find((l) => l.name === tdFor);

  // Dealer list is still loading from the API.
  if (!dealer) return null;

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Dealer Revenue & Customer Journey Optimizer"
        subtitle="Dealer-specific next-best-action engine that learns from real outcomes."
        right={
          <Select value={activeId} onValueChange={setSelId}>
            <SelectTrigger className="w-[240px] border-white/10 bg-white/[0.03]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {dealers.map((d) => (
                <SelectItem key={d.id} value={d.id}>
                  {d.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        {[
          ["Leads today", `${dealer.leads}`],
          ["Hot leads", `${dealer.hotLeads}`],
          ["Test drives pending", `${dealer.testDrivesPending}`],
          ["Booking probability", `${dealer.bookingProb}%`],
          ["Revenue at risk", dealer.revenueAtRisk],
          ["Follow-up leakage", dealer.leakage],
          ["Bay utilization", dealer.bayUtil],
        ].map(([l, v]) => (
          <div key={l} className="glass rounded-xl p-3">
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground">{l}</div>
            <div className="mt-1 text-lg font-semibold text-gradient-mahindra">{v}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_320px]">
        <Panel title="Lead Prioritization" subtitle="AI-scored next-best-action per lead.">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[10px] uppercase tracking-widest text-muted-foreground">
                <tr className="border-b border-white/10">
                  <th className="pb-2 text-left">Lead</th>
                  <th className="pb-2 text-left">Vehicle</th>
                  <th className="pb-2 text-left">Score</th>
                  <th className="pb-2 text-left">Prob.</th>
                  <th className="pb-2 text-left">Recommended action</th>
                  <th className="pb-2 text-left">Revenue</th>
                  <th className="pb-2 text-left">Status</th>
                  <th className="pb-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((l) => (
                  <tr
                    key={l.name}
                    className="border-b border-white/5 last:border-0 hover:bg-white/[0.03]"
                  >
                    <td className="py-3">{l.name}</td>
                    <td>{l.vehicle}</td>
                    <td>
                      <StatPill tone={l.score > 85 ? "success" : "info"}>{l.score}</StatPill>
                    </td>
                    <td>{l.prob}%</td>
                    <td className="text-xs text-foreground/80">{l.action}</td>
                    <td className="text-emerald-300">{l.revenue}</td>
                    <td>
                      <StatPill
                        tone={
                          statuses[l.name] === "Converted"
                            ? "success"
                            : statuses[l.name]
                              ? "info"
                              : "default"
                        }
                      >
                        {statuses[l.name] || l.status}
                      </StatPill>
                    </td>
                    <td className="text-right">
                      <div className="inline-flex gap-1">
                        <button
                          onClick={() => setPitchFor(l.name)}
                          className="rounded-md border border-white/10 p-1.5 hover:border-primary/40 hover:bg-primary/10"
                          title="Generate Pitch"
                        >
                          <Sparkles className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => {
                            if (l.id) messageLead(l.id);
                            setStatuses((s) => ({ ...s, [l.name]: "Message Sent" }));
                            toast.success("WhatsApp sent");
                          }}
                          className="rounded-md border border-white/10 p-1.5 hover:border-primary/40 hover:bg-primary/10"
                          title="Send WhatsApp"
                        >
                          <MessageCircle className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => setTdFor(l.name)}
                          className="rounded-md border border-white/10 p-1.5 hover:border-primary/40 hover:bg-primary/10"
                          title="Schedule Test Drive"
                        >
                          <Calendar className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => {
                            if (l.id) convertLead(l.id);
                            setStatuses((s) => ({ ...s, [l.name]: "Converted" }));
                            toast.success(`${l.name} · Converted`);
                          }}
                          className="rounded-md border border-white/10 p-1.5 hover:border-emerald-500/40 hover:bg-emerald-500/10"
                          title="Mark Converted"
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="AI Dealer Coach">
          <div className="space-y-3 text-sm">
            <div className="rounded-lg border border-primary/30 bg-primary/10 p-3">
              <div className="text-[10px] uppercase tracking-widest text-primary">
                Top action now
              </div>
              <div className="mt-1">
                Call <span className="font-semibold">Rakesh Patil</span> within 2h with ₹25K
                exchange bonus.
              </div>
              <div className="mt-1 text-xs text-emerald-300">
                +₹19.8L expected · 74% probability
              </div>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                Best offer
              </div>
              <div className="mt-1">XUV700 exchange bonus + finance pre-approval</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                Best time
              </div>
              <div className="mt-1">Weekdays 6–8 PM, Sat 11 AM–1 PM</div>
            </div>
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs">
              <span className="text-amber-300 font-semibold">Risk if ignored: </span>Potential ₹42L
              revenue leakage this week from top 5 stale hot leads.
            </div>
            <Button
              onClick={() => toast.success("Coach playbook delivered to dealer app")}
              className="w-full mahindra-gradient text-white gap-1"
            >
              <Phone className="h-4 w-4" /> Deliver Coach Playbook
            </Button>
          </div>
        </Panel>
      </div>

      <div className="glass-strong rounded-2xl p-4 text-xs">
        <span className="font-semibold text-primary">AI Differentiator: </span>
        Dealer-specific next-best-action engine that learns from real outcomes and updates in near
        real-time.
      </div>

      <Dialog open={!!pitchFor} onOpenChange={(o) => !o && setPitchFor(null)}>
        <DialogContent className="max-w-lg border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">
              Personalized Pitch · {pitchFor}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
              {pitch?.text ??
                `Hi ${pitchFor}, based on your interest and profile, the XUV700 with our current ₹25,000
              exchange bonus + 6.99% pre-approved finance would put your on-road cost within your
              target. I can hold a test drive slot at 6 PM tomorrow — would that work?`}
            </div>
            <Button
              onClick={() => {
                navigator.clipboard?.writeText(pitch?.text ?? `Personalized pitch for ${pitchFor}`);
                toast.success("Pitch copied");
              }}
              className="gap-1 mahindra-gradient text-white"
            >
              <Copy className="h-4 w-4" /> Copy Pitch
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!tdFor} onOpenChange={(o) => !o && setTdFor(null)}>
        <DialogContent className="max-w-md border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">
              Schedule Test Drive · {tdFor}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-3 gap-2 text-xs">
            {["Sat 11:00", "Sat 15:00", "Sat 18:00", "Sun 11:00", "Sun 15:00", "Sun 18:00"].map(
              (s) => (
                <button
                  key={s}
                  onClick={() => {
                    if (tdLead?.id) scheduleTestDrive(tdLead.id, s);
                    toast.success(`Test drive booked · ${s}`);
                    setTdFor(null);
                  }}
                  className="rounded-lg border border-white/10 bg-white/[0.03] p-2 hover:border-primary/40 hover:bg-primary/10"
                >
                  {s}
                </button>
              ),
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
