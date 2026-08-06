import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useSolutionBuckets, useSolutionTags } from "@/hooks/use-api";
import { Panel, SectionTitle, StatPill } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { Plus, PlayCircle, FileText } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/lib/app-context";
import { PoCRoadmapPanel } from "@/components/poc-roadmap";
import { ExecutiveSummaryModal } from "@/components/executive-summary";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/catalogue")({
  head: () => ({ meta: [{ title: "AI Solution Catalogue · Mahindra AI Command Center" }] }),
  component: Catalogue,
});

function Catalogue() {
  const { addPoc } = useApp();
  const solutionBuckets = useSolutionBuckets();
  const solutionTags = useSolutionTags();
  const [filter, setFilter] = useState<string | null>(null);
  const [summaryFor, setSummaryFor] = useState<string | null>(null);

  const buckets = useMemo(() => {
    if (!filter) return solutionBuckets;
    return solutionBuckets
      .map((b) => ({
        ...b,
        items: b.items.filter(() => b.tag === filter || filter === b.tag),
      }))
      .filter((b) => b.items.length);
  }, [filter, solutionBuckets]);

  return (
    <div className="space-y-8">
      <SectionTitle
        title="AI Solution Catalogue"
        subtitle="Reusable AI IP grouped by business bucket. Not a chatbot — a closed-loop AI operating layer."
      />

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setFilter(null)}
          className={cn(
            "rounded-full px-3 py-1.5 text-xs border transition-all",
            !filter
              ? "mahindra-gradient text-white border-transparent"
              : "border-white/10 bg-white/[0.03] hover:border-primary/40",
          )}
        >
          All
        </button>
        {solutionTags.map((t) => (
          <button
            key={t}
            onClick={() => setFilter(t === filter ? null : t)}
            className={cn(
              "rounded-full px-3 py-1.5 text-xs border transition-all",
              filter === t
                ? "mahindra-gradient text-white border-transparent"
                : "border-white/10 bg-white/[0.03] hover:border-primary/40",
            )}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          {buckets.map((bucket) => (
            <Panel
              key={bucket.name}
              title={bucket.name}
              actions={<StatPill>{bucket.tag}</StatPill>}
            >
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {bucket.items.map((it) => (
                  <div
                    key={it.name}
                    className="group rounded-xl border border-white/10 bg-white/[0.03] p-4 transition-all hover:border-primary/30 hover:bg-white/[0.05]"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="text-sm font-semibold">{it.name}</div>
                    </div>
                    <div className="mt-3 space-y-2 text-xs">
                      <div>
                        <span className="text-muted-foreground">Problem: </span>
                        {it.problem}
                      </div>
                      <div>
                        <span className="text-muted-foreground">Solution: </span>
                        {it.solution}
                      </div>
                      <div>
                        <span className="text-muted-foreground">Differentiator: </span>
                        <span className="text-primary/90">{it.diff}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Impact: </span>
                        <span className="text-emerald-300">{it.impact}</span>
                      </div>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setSummaryFor(it.name)}
                        className="gap-1 border-white/10"
                      >
                        <FileText className="h-3.5 w-3.5" /> View Demo
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => {
                          addPoc({ name: it.name, bucket: bucket.tag });
                          toast.success(`Added ${it.name} to PoC Roadmap`);
                        }}
                        className="gap-1 mahindra-gradient text-white"
                      >
                        <Plus className="h-3.5 w-3.5" /> Add to PoC
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          ))}
        </div>

        <div className="space-y-6">
          <PoCRoadmapPanel />
          <Panel title="Positioning">
            <div className="space-y-2 text-xs text-foreground/80">
              {[
                "Not a chatbot. A closed-loop AI operating layer.",
                "Predict. Explain. Simulate. Act. Learn.",
                "From AI pilots to reusable enterprise AI IP.",
                "Causal intelligence, not just dashboards.",
                "Every AI decision has a trust trail.",
              ].map((t) => (
                <div key={t} className="rounded-lg border border-white/10 bg-white/[0.03] p-2.5">
                  {t}
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>

      <ExecutiveSummaryModal
        open={!!summaryFor}
        onOpenChange={(o) => !o && setSummaryFor(null)}
        useCase={summaryFor || ""}
      />
    </div>
  );
}
