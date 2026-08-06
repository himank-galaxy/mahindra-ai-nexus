import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Panel, SectionTitle, StatPill } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useXrExperiences } from "@/hooks/use-api";
import { PlayCircle, Sparkles } from "lucide-react";

export const Route = createFileRoute("/xr")({
  head: () => ({ meta: [{ title: "AR/VR Experience Intelligence · Mahindra AI Command Center" }] }),
  component: XR,
});

const CARDS = [
  {
    id: "showroom",
    title: "AI Virtual Showroom",
    use: "Immersive vehicle exploration",
    feat: "Generative sales assistant + config",
    impact: "+18% online-to-visit conversion",
  },
  {
    id: "config",
    title: "3D Vehicle Configurator",
    use: "Personalized configurations",
    feat: "Real-time AI recommendations",
    impact: "+12% variant upsell",
  },
  {
    id: "repair",
    title: "AR Technician Repair Guide",
    use: "Step-by-step service",
    feat: "Component-aware AR overlays",
    impact: "-24% repair time",
  },
  {
    id: "training",
    title: "VR Dealer Sales Training",
    use: "Immersive skill building",
    feat: "AI feedback on pitch & objections",
    impact: "+22% training ROI",
  },
];

function XR() {
  const cards = useXrExperiences() ?? CARDS;
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="space-y-6">
      <SectionTitle
        title="AR/VR/XR Experience Intelligence"
        subtitle="AI-generated immersive journeys personalized to customer, dealer or technician context."
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {cards.map((c) => (
          <div key={c.id} className="glass rounded-2xl p-4 hover:border-primary/30">
            <div
              className="grid h-24 w-full place-items-center rounded-lg mahindra-gradient/20 border border-primary/20"
              style={{
                background:
                  "radial-gradient(circle at 30% 30%, oklch(0.58 0.22 27 / 0.35), transparent 60%), radial-gradient(circle at 70% 70%, oklch(0.65 0.18 250 / 0.25), transparent 60%)",
              }}
            >
              <Sparkles className="h-10 w-10 text-primary/70" />
            </div>
            <div className="mt-3 text-sm font-semibold">{c.title}</div>
            <div className="mt-1 space-y-1 text-xs text-muted-foreground">
              <div>{c.use}</div>
              <div className="text-primary/80">{c.feat}</div>
              <div className="text-emerald-300">{c.impact}</div>
            </div>
            <Button
              size="sm"
              onClick={() => setOpen(c.id)}
              className="mt-3 w-full mahindra-gradient text-white gap-1"
            >
              <PlayCircle className="h-3.5 w-3.5" /> Launch Demo
            </Button>
          </div>
        ))}
      </div>

      <div className="glass-strong rounded-2xl p-4 text-xs">
        <span className="font-semibold text-primary">AI Differentiator: </span>
        AI-generated immersive journeys personalized to customer, dealer or technician context.
      </div>

      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent className="max-w-2xl border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">
              {cards.find((c) => c.id === open)?.title}
            </DialogTitle>
          </DialogHeader>
          {open === "showroom" && <Showroom />}
          {open === "config" && <Config />}
          {open === "repair" && <Repair />}
          {open === "training" && <Training />}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Showroom() {
  const [model, setModel] = useState("XUV700");
  const [color, setColor] = useState("Napoli Black");
  return (
    <div className="space-y-3 text-sm">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="text-xs text-muted-foreground mb-1">Vehicle</div>
          <div className="flex flex-wrap gap-1">
            {["XUV700", "Scorpio-N", "Thar", "XUV 3XO"].map((m) => (
              <button
                key={m}
                onClick={() => setModel(m)}
                className={`rounded-md border px-2 py-1 text-xs ${model === m ? "border-primary bg-primary/20" : "border-white/10 bg-white/[0.03]"}`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-1">Color</div>
          <div className="flex flex-wrap gap-1">
            {["Napoli Black", "Everest White", "Red Rage", "Deep Forest"].map((c) => (
              <button
                key={c}
                onClick={() => setColor(c)}
                className={`rounded-md border px-2 py-1 text-xs ${color === c ? "border-primary bg-primary/20" : "border-white/10 bg-white/[0.03]"}`}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div
        className="grid h-40 w-full place-items-center rounded-lg border border-primary/20 mahindra-gradient/10"
        style={{
          background: "radial-gradient(circle, oklch(0.58 0.22 27 / 0.2), transparent 70%)",
        }}
      >
        <div className="text-center">
          <div className="text-lg font-semibold">{model}</div>
          <div className="text-xs text-muted-foreground">{color} · 360° preview</div>
        </div>
      </div>
      <div className="rounded-lg border border-primary/30 bg-primary/10 p-3 text-xs">
        <span className="font-semibold text-primary">AI Assistant: </span>Based on your family size
        and city, the {model} adaptive cruise pack + 3rd-row comfort would suit you best.
      </div>
    </div>
  );
}

function Config() {
  return (
    <div className="space-y-2 text-sm">
      {[
        "Base variant",
        "Adaptive cruise pack",
        "Sunroof + ambient lighting",
        "Panoramic display upgrade",
        "Advanced safety pack",
      ].map((f, i) => (
        <div
          key={f}
          className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.03] p-3"
        >
          <span>{f}</span>
          <StatPill tone={i < 3 ? "success" : "info"}>
            {i < 3 ? "Recommended" : "Optional"}
          </StatPill>
        </div>
      ))}
    </div>
  );
}

function Repair() {
  return (
    <ol className="space-y-2 text-sm">
      {[
        "Scan component",
        "Identify issue",
        "Overlay repair instruction",
        "Confirm completion",
        "Capture feedback",
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
  );
}

function Training() {
  return (
    <div className="grid grid-cols-2 gap-3 text-sm">
      <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
        <div className="text-xs text-muted-foreground">Trainee score</div>
        <div className="text-lg font-semibold text-emerald-300">84 / 100</div>
      </div>
      <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
        <div className="text-xs text-muted-foreground">Objection handling</div>
        <div className="text-lg font-semibold text-sky-300">B+</div>
      </div>
      <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
        <div className="text-xs text-muted-foreground">Pitch quality</div>
        <div className="text-lg font-semibold">A-</div>
      </div>
      <div className="rounded-lg border border-primary/30 bg-primary/10 p-3">
        <div className="text-xs text-primary">Improvement</div>
        <div className="text-sm">Practice finance-assisted objections</div>
      </div>
    </div>
  );
}
