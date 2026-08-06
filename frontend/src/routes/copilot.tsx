import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { Panel, SectionTitle, MiniBar, StatPill } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Send, Sparkles, Bot, User as UserIcon, PlayCircle, Check, Download } from "lucide-react";
import { useSuggestedPrompts } from "@/hooks/use-api";
import { chatCopilot } from "@/lib/api/endpoints";
import type { CopilotResult } from "@/lib/api/types";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export const Route = createFileRoute("/copilot")({
  head: () => ({ meta: [{ title: "Analytics Copilot · Mahindra AI Command Center" }] }),
  component: Copilot,
});

type Turn = { role: "user"; text: string } | { role: "ai"; text: string; result: CopilotResult };

function Copilot() {
  const prompts = useSuggestedPrompts();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const nav = useNavigate();

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, typing]);

  function send(text?: string) {
    const q = (text ?? input).trim();
    if (!q) return;
    setTurns((prev) => [...prev, { role: "user", text: q }]);
    setInput("");
    setTyping(true);
    chatCopilot(q)
      .then((r) => {
        setTurns((prev) => [...prev, { role: "ai", text: r.answer, result: r }]);
      })
      .catch(() => {
        const r: CopilotResult = {
          answer: "The copilot service is unreachable right now. Please check the backend.",
          explanation: "The API did not respond. Retry once the backend is running.",
          sql: "-- copilot unavailable",
          python: "# copilot unavailable",
          action: "Check the FastAPI backend and retry.",
          confidence: 0,
        };
        setTurns((prev) => [...prev, { role: "ai", text: r.answer, result: r }]);
      })
      .finally(() => setTyping(false));
  }

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Dynamic Analytics Copilot"
        subtitle="Unlike fixed dashboards, this copilot dynamically generates analysis, explanations, simulations and action recommendations from business questions."
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_320px]">
        <Panel title="Conversation">
          <div className="max-h-[520px] min-h-[400px] space-y-4 overflow-y-auto pr-2">
            {turns.length === 0 && (
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-foreground/80">
                <div className="flex items-center gap-2 text-primary">
                  <Sparkles className="h-4 w-4" />
                  <span className="font-semibold">Ask anything about Mahindra businesses</span>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  Auto, Finance, Logistics, Circularity, Compliance and Simulation data are wired
                  up. Try a suggested prompt on the right.
                </p>
              </div>
            )}
            {turns.map((t, i) => (
              <div key={i} className={`flex gap-3 ${t.role === "user" ? "justify-end" : ""}`}>
                {t.role === "ai" && (
                  <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg mahindra-gradient">
                    <Bot className="h-4 w-4 text-white" />
                  </div>
                )}
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm ${t.role === "user" ? "bg-primary text-primary-foreground" : "bg-white/[0.05]"}`}
                >
                  {t.text}
                  {t.role === "ai" && (
                    <div className="mt-3 space-y-3">
                      <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                        Analysis · Confidence {t.result.confidence}%
                      </div>
                      <div className="text-xs text-foreground/80">{t.result.explanation}</div>
                      {t.result.chart && <MiniBar data={t.result.chart} />}
                      {t.result.table && (
                        <div className="overflow-x-auto rounded-lg border border-white/10">
                          <table className="w-full text-xs">
                            <thead className="bg-white/5">
                              <tr>
                                {t.result.table.headers.map((h) => (
                                  <th
                                    key={h}
                                    className="p-2 text-left font-medium text-muted-foreground"
                                  >
                                    {h}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {t.result.table.rows.map((r, ri) => (
                                <tr key={ri} className="border-t border-white/5">
                                  {r.map((c, ci) => (
                                    <td key={ci} className="p-2">
                                      {c}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                      <div className="rounded-lg bg-black/40 p-2 font-mono text-[10px] text-emerald-300/90 whitespace-pre-wrap">
                        {t.result.sql}
                      </div>
                      <div className="rounded-lg bg-black/40 p-2 font-mono text-[10px] text-sky-300/90 whitespace-pre-wrap">
                        {t.result.python}
                      </div>
                      <div className="rounded-lg border border-primary/30 bg-primary/10 p-2 text-xs">
                        <span className="font-semibold text-primary">Recommended action: </span>
                        {t.result.action}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="gap-1 border-white/10"
                          onClick={() => nav({ to: "/simulation" })}
                        >
                          <PlayCircle className="h-3.5 w-3.5" /> Simulate
                        </Button>
                        <Button
                          size="sm"
                          className="gap-1 mahindra-gradient text-white"
                          onClick={() => toast.success("Approved · logged to Trust Ledger")}
                        >
                          <Check className="h-3.5 w-3.5" /> Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="gap-1 border-white/10"
                          onClick={() =>
                            setSummary(
                              `${t.text}\n\n${t.result.explanation}\n\nAction: ${t.result.action}`,
                            )
                          }
                        >
                          <Download className="h-3.5 w-3.5" /> Export Summary
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
                {t.role === "user" && (
                  <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-white/10">
                    <UserIcon className="h-4 w-4" />
                  </div>
                )}
              </div>
            ))}
            {typing && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <div className="grid h-8 w-8 place-items-center rounded-lg mahindra-gradient">
                  <Bot className="h-4 w-4 text-white" />
                </div>
                <span className="inline-flex gap-1">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary" />
                  <span
                    className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary"
                    style={{ animationDelay: "120ms" }}
                  />
                  <span
                    className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary"
                    style={{ animationDelay: "240ms" }}
                  />
                </span>
              </div>
            )}
            <div ref={bottom} />
          </div>

          <div className="mt-4 flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="Ask about bookings, leakage, collections, SLA, credits, warranty…"
              className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
            <button
              onClick={() => send()}
              className="grid h-8 w-8 place-items-center rounded-lg mahindra-gradient text-white"
            >
              <Send className="h-3.5 w-3.5" />
            </button>
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel title="Suggested prompts">
            <div className="flex flex-col gap-2">
              {prompts.map((p) => (
                <button
                  key={p}
                  onClick={() => send(p)}
                  className="rounded-lg border border-white/10 bg-white/[0.03] p-2.5 text-left text-xs hover:border-primary/40 hover:bg-primary/10"
                >
                  {p}
                </button>
              ))}
            </div>
          </Panel>
          <Panel title="Capabilities">
            <div className="space-y-2 text-xs">
              {[
                "Natural language questions",
                "Auto SQL + Python generation",
                "Charts and tables",
                "Causal explanations",
                "Simulation & approve loop",
              ].map((c) => (
                <div key={c} className="flex items-center gap-2">
                  <StatPill tone="success">✓</StatPill>
                  {c}
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>

      <Dialog open={!!summary} onOpenChange={(o) => !o && setSummary(null)}>
        <DialogContent className="max-w-lg border-white/10 bg-background/95">
          <DialogHeader>
            <DialogTitle className="text-gradient-mahindra">Executive Summary</DialogTitle>
          </DialogHeader>
          <pre className="whitespace-pre-wrap rounded-lg border border-white/10 bg-white/[0.03] p-3 text-sm">
            {summary}
          </pre>
          <Button
            onClick={() => {
              navigator.clipboard?.writeText(summary || "");
              toast.success("Copied");
            }}
            className="mahindra-gradient text-white gap-1"
          >
            <Download className="h-4 w-4" /> Copy
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
