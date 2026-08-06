import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useExecutiveSummary } from "@/hooks/use-api";
import type { ExecutiveSummary } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Copy } from "lucide-react";

/** Placeholder shown while the backend is generating the summary. */
const GENERATING: ExecutiveSummary = {
  problem: "Generating…",
  solution: "Generating…",
  diff: "Generating…",
  impact: "Generating…",
  data: "Generating…",
  scope: "Generating…",
  timeline: "Generating…",
  risks: "Generating…",
  next: "Generating…",
};

export function ExecutiveSummaryModal({
  open,
  onOpenChange,
  useCase,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  useCase: string;
}) {
  const s = useExecutiveSummary(useCase, open) ?? GENERATING;
  const text = `EXECUTIVE SUMMARY — ${useCase}
Business Problem: ${s.problem}
AI Solution: ${s.solution}
AI Differentiator: ${s.diff}
Business Impact: ${s.impact}
Data Required: ${s.data}
PoC Scope: ${s.scope}
Timeline: ${s.timeline}
Risks/Dependencies: ${s.risks}
Next Step: ${s.next}`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl border-white/10 bg-background/95">
        <DialogHeader>
          <DialogTitle className="text-gradient-mahindra">
            Executive Summary — {useCase}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          {[
            ["Business Problem", s.problem],
            ["AI Solution", s.solution],
            ["AI Differentiator", s.diff],
            ["Business Impact", s.impact],
            ["Data Required", s.data],
            ["Suggested PoC Scope", s.scope],
            ["Estimated Timeline", s.timeline],
            ["Risks / Dependencies", s.risks],
            ["Recommended Next Step", s.next],
          ].map(([k, v]) => (
            <div key={k} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
              <div className="text-[10px] uppercase tracking-widest text-primary">{k}</div>
              <div className="mt-1 text-foreground/90">{v}</div>
            </div>
          ))}
        </div>
        <div className="flex justify-end">
          <Button
            onClick={() => {
              navigator.clipboard?.writeText(text);
              toast.success("Summary copied to clipboard");
            }}
            className="gap-2 mahindra-gradient text-white"
          >
            <Copy className="h-4 w-4" /> Copy Summary
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
