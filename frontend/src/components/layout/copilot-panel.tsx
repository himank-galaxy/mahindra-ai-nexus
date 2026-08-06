import { X, Sparkles, Send, Bot, User as UserIcon } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { useApp } from "@/lib/app-context";
import { useSuggestedPrompts } from "@/hooks/use-api";
import { chatCopilot } from "@/lib/api/endpoints";
import type { CopilotResult } from "@/lib/api/types";
import { MiniBar } from "@/components/ui/panel";
import { cn } from "@/lib/utils";

export function CopilotPanel() {
  const { copilotOpen, setCopilotOpen, copilotMessages, pushCopilot } = useApp();
  const prompts = useSuggestedPrompts();
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [lastResult, setLastResult] = useState<CopilotResult | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [copilotMessages, typing]);

  function send(text?: string) {
    const q = (text ?? input).trim();
    if (!q) return;
    pushCopilot({ role: "user", content: q, ts: Date.now() });
    setInput("");
    setTyping(true);
    chatCopilot(q)
      .then((r) => {
        pushCopilot({ role: "ai", content: r.answer, ts: Date.now() });
        setLastResult(r);
      })
      .catch(() => {
        pushCopilot({
          role: "ai",
          content:
            "The copilot service is unreachable right now. Please check the backend and try again.",
          ts: Date.now(),
        });
        setLastResult(null);
      })
      .finally(() => setTyping(false));
  }

  return (
    <>
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity",
          copilotOpen ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={() => setCopilotOpen(false)}
      />
      <aside
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-white/10 bg-background/95 backdrop-blur-xl shadow-2xl transition-transform",
          copilotOpen ? "translate-x-0" : "translate-x-full",
        )}
      >
        <div className="flex h-16 items-center justify-between border-b border-white/5 px-5">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-lg mahindra-gradient">
              <Sparkles className="h-4 w-4 text-white" />
            </div>
            <div>
              <div className="text-sm font-semibold">AI Copilot</div>
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                Closed-loop reasoning
              </div>
            </div>
          </div>
          <button
            onClick={() => setCopilotOpen(false)}
            className="rounded-lg p-2 text-muted-foreground hover:bg-white/5 hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-5">
          {copilotMessages.length === 0 && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Ask about Auto, Finance, Logistics, Circularity, Compliance or Simulation. Try:
              </p>
              <div className="flex flex-wrap gap-2">
                {prompts.slice(0, 4).map((p) => (
                  <button
                    key={p}
                    onClick={() => send(p)}
                    className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-foreground/90 hover:border-primary/40 hover:bg-primary/10"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}

          {copilotMessages.map((m, i) => (
            <div
              key={i}
              className={cn("flex gap-3", m.role === "user" ? "justify-end" : "justify-start")}
            >
              {m.role === "ai" && (
                <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg mahindra-gradient">
                  <Bot className="h-4 w-4 text-white" />
                </div>
              )}
              <div
                className={cn(
                  "max-w-[80%] rounded-2xl px-4 py-2 text-sm",
                  m.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-white/[0.05] text-foreground",
                )}
              >
                {m.content}
              </div>
              {m.role === "user" && (
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

          {lastResult && !typing && (
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3 space-y-3">
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                Analysis · Confidence {lastResult.confidence}%
              </div>
              <div className="text-xs text-foreground/80">{lastResult.explanation}</div>
              {lastResult.chart && <MiniBar data={lastResult.chart} />}
              <div className="rounded-lg bg-black/40 p-2 font-mono text-[10px] text-emerald-300/90 whitespace-pre-wrap">
                {lastResult.sql}
              </div>
              <div className="rounded-lg border border-primary/30 bg-primary/10 p-2 text-xs">
                <span className="font-semibold text-primary">Recommended action: </span>
                {lastResult.action}
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-white/5 p-3">
          <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="Ask the copilot…"
              className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
            <button
              onClick={() => send()}
              className="grid h-8 w-8 place-items-center rounded-lg mahindra-gradient text-white hover:opacity-90"
            >
              <Send className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
