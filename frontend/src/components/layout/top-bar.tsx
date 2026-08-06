import { Search, Sparkles, PlayCircle, ChevronDown } from "lucide-react";
import { useApp } from "@/lib/app-context";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function TopBar() {
  const { setCopilotOpen, executiveMode, setExecutiveMode, scenario, setScenario, startDemo } =
    useApp();

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-white/5 bg-background/70 px-4 backdrop-blur-xl lg:pl-6">
      <div className="relative flex-1 max-w-xl">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          placeholder="Search use cases, dealers, customers, agents…"
          className="h-10 w-full rounded-full border border-white/10 bg-white/[0.03] pl-10 pr-4 text-sm outline-none transition-all focus:border-primary/50 focus:bg-white/[0.06]"
        />
      </div>

      <div className="hidden items-center gap-2 md:flex">
        <span className="text-[11px] uppercase tracking-widest text-muted-foreground">
          Scenario
        </span>
        <Select value={scenario} onValueChange={setScenario}>
          <SelectTrigger className="h-9 w-[180px] rounded-full border-white/10 bg-white/[0.03] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="Baseline FY26">Baseline FY26</SelectItem>
            <SelectItem value="Aggressive Growth">Aggressive Growth</SelectItem>
            <SelectItem value="Cost Optimization">Cost Optimization</SelectItem>
            <SelectItem value="ESG-First">ESG-First</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="hidden items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 md:flex">
        <span className="text-[11px] uppercase tracking-widest text-muted-foreground">
          Executive
        </span>
        <Switch checked={executiveMode} onCheckedChange={setExecutiveMode} />
      </div>

      <Button
        variant="outline"
        size="sm"
        onClick={startDemo}
        className="hidden gap-2 rounded-full border-white/10 bg-white/[0.03] md:inline-flex"
      >
        <PlayCircle className="h-4 w-4" /> Start Demo Story
      </Button>

      <Button
        onClick={() => setCopilotOpen(true)}
        size="sm"
        className="gap-2 rounded-full mahindra-gradient text-white shadow-lg shadow-red-900/30 hover:opacity-90"
      >
        <Sparkles className="h-4 w-4" /> Ask AI Copilot
      </Button>
    </header>
  );
}
