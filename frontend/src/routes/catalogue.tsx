import {
  createFileRoute,
  useNavigate,
} from "@tanstack/react-router";
import { useMemo, useState } from "react";
import {
  FileText,
  Plus,
} from "lucide-react";
import { toast } from "sonner";

import { ExecutiveSummaryModal } from "@/components/executive-summary";
import { PoCRoadmapPanel } from "@/components/poc-roadmap";
import { Button } from "@/components/ui/button";
import {
  Panel,
  SectionTitle,
  StatPill,
} from "@/components/ui/panel";
import {
  useSolutionBuckets,
  useSolutionTags,
} from "@/hooks/use-api";
import { useApp } from "@/lib/app-context";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/catalogue")({
  head: () => ({
    meta: [
      {
        title:
          "AI Solution Catalogue · Mahindra AI Command Center",
      },
    ],
  }),
  component: Catalogue,
});

const WARRANTY_QUALITY_SOLUTION =
  "Warranty & Quality Early-Warning Graph";

function Catalogue() {
  const navigate = useNavigate();
  const { addPoc } = useApp();

  const solutionBuckets = useSolutionBuckets();
  const solutionTags = useSolutionTags();

  const [filter, setFilter] =
    useState<string | null>(null);

  const [summaryFor, setSummaryFor] =
    useState<string | null>(null);

  const buckets = useMemo(() => {
    if (!filter) {
      return solutionBuckets;
    }

    return solutionBuckets
      .map((bucket) => ({
        ...bucket,
        items: bucket.items.filter(
          () =>
            bucket.tag === filter ||
            filter === bucket.tag,
        ),
      }))
      .filter(
        (bucket) => bucket.items.length,
      );
  }, [
    filter,
    solutionBuckets,
  ]);

  const handleViewDemo = (
    solutionName: string,
  ) => {
    if (
      solutionName ===
      WARRANTY_QUALITY_SOLUTION
    ) {
      void navigate({
        to: "/warranty-quality",
      });

      return;
    }

    setSummaryFor(solutionName);
  };

  return (
    <div className="space-y-8">
      <SectionTitle
        title="AI Solution Catalogue"
        subtitle="Reusable AI IP grouped by business bucket. Not a chatbot — a closed-loop AI operating layer."
      />

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setFilter(null)}
          className={cn(
            "rounded-full border px-3 py-1.5 text-xs transition-all",
            !filter
              ? "mahindra-gradient border-transparent text-white"
              : "border-white/10 bg-white/[0.03] hover:border-primary/40",
          )}
        >
          All
        </button>

        {solutionTags.map((tag) => (
          <button
            type="button"
            key={tag}
            onClick={() =>
              setFilter(
                tag === filter
                  ? null
                  : tag,
              )
            }
            className={cn(
              "rounded-full border px-3 py-1.5 text-xs transition-all",
              filter === tag
                ? "mahindra-gradient border-transparent text-white"
                : "border-white/10 bg-white/[0.03] hover:border-primary/40",
            )}
          >
            {tag}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          {buckets.map((bucket) => (
            <Panel
              key={bucket.name}
              title={bucket.name}
              actions={
                <StatPill>
                  {bucket.tag}
                </StatPill>
              }
            >
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {bucket.items.map(
                  (item) => (
                    <div
                      key={item.name}
                      className="group rounded-xl border border-white/10 bg-white/[0.03] p-4 transition-all hover:border-primary/30 hover:bg-white/[0.05]"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="text-sm font-semibold">
                          {item.name}
                        </div>
                      </div>

                      <div className="mt-3 space-y-2 text-xs">
                        <div>
                          <span className="text-muted-foreground">
                            Problem:{" "}
                          </span>
                          {item.problem}
                        </div>

                        <div>
                          <span className="text-muted-foreground">
                            Solution:{" "}
                          </span>
                          {item.solution}
                        </div>

                        <div>
                          <span className="text-muted-foreground">
                            Differentiator:{" "}
                          </span>
                          <span className="text-primary/90">
                            {item.diff}
                          </span>
                        </div>

                        <div>
                          <span className="text-muted-foreground">
                            Impact:{" "}
                          </span>
                          <span className="text-emerald-300">
                            {item.impact}
                          </span>
                        </div>
                      </div>

                      <div className="mt-4 flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            handleViewDemo(
                              item.name,
                            )
                          }
                          className="gap-1 border-white/10"
                        >
                          <FileText className="h-3.5 w-3.5" />
                          View Demo
                        </Button>

                        <Button
                          size="sm"
                          onClick={() => {
                            addPoc({
                              name: item.name,
                              bucket:
                                bucket.tag,
                            });

                            toast.success(
                              `Added ${item.name} to PoC Roadmap`,
                            );
                          }}
                          className="mahindra-gradient gap-1 text-white"
                        >
                          <Plus className="h-3.5 w-3.5" />
                          Add to PoC
                        </Button>
                      </div>
                    </div>
                  ),
                )}
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
              ].map((text) => (
                <div
                  key={text}
                  className="rounded-lg border border-white/10 bg-white/[0.03] p-2.5"
                >
                  {text}
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>

      <ExecutiveSummaryModal
        open={!!summaryFor}
        onOpenChange={(open) =>
          !open &&
          setSummaryFor(null)
        }
        useCase={summaryFor || ""}
      />
    </div>
  );
}
