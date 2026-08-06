import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { usePocMutations, usePocQuery } from "@/hooks/use-api";

type PoCItem = { name: string; bucket: string; addedAt: number };

type CopilotMsg = { role: "user" | "ai"; content: string; ts: number };

type Ctx = {
  poc: PoCItem[];
  addPoc: (item: Omit<PoCItem, "addedAt">) => void;
  removePoc: (name: string) => void;

  copilotOpen: boolean;
  setCopilotOpen: (v: boolean) => void;
  copilotMessages: CopilotMsg[];
  pushCopilot: (m: CopilotMsg) => void;
  clearCopilot: () => void;

  executiveMode: boolean;
  setExecutiveMode: (v: boolean) => void;

  scenario: string;
  setScenario: (v: string) => void;

  demoStep: number | null;
  startDemo: () => void;
  nextDemo: () => void;
  prevDemo: () => void;
  exitDemo: () => void;
};

const AppCtx = createContext<Ctx | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const apiPoc = usePocQuery().data;
  const pocMutations = usePocMutations();
  const poc = useMemo(() => apiPoc ?? [], [apiPoc]);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [copilotMessages, setCopilotMessages] = useState<CopilotMsg[]>([]);
  const [executiveMode, setExecutiveMode] = useState(false);
  const [scenario, setScenario] = useState("Baseline FY26");
  const [demoStep, setDemoStep] = useState<number | null>(null);

  const addPoc = useCallback(
    (item: Omit<PoCItem, "addedAt">) => {
      pocMutations.addPoc(item);
    },
    [pocMutations],
  );
  const removePoc = useCallback(
    (name: string) => {
      pocMutations.removePoc(name);
    },
    [pocMutations],
  );
  const pushCopilot = useCallback(
    (m: CopilotMsg) => setCopilotMessages((prev) => [...prev, m]),
    [],
  );
  const clearCopilot = useCallback(() => setCopilotMessages([]), []);

  const value = useMemo<Ctx>(
    () => ({
      poc,
      addPoc,
      removePoc,
      copilotOpen,
      setCopilotOpen,
      copilotMessages,
      pushCopilot,
      clearCopilot,
      executiveMode,
      setExecutiveMode,
      scenario,
      setScenario,
      demoStep,
      startDemo: () => setDemoStep(0),
      nextDemo: () => setDemoStep((s) => (s === null ? 0 : Math.min(s + 1, 7))),
      prevDemo: () => setDemoStep((s) => (s === null ? 0 : Math.max(s - 1, 0))),
      exitDemo: () => setDemoStep(null),
    }),
    [
      poc,
      copilotOpen,
      copilotMessages,
      executiveMode,
      scenario,
      demoStep,
      addPoc,
      removePoc,
      pushCopilot,
      clearCopilot,
    ],
  );

  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}

export function useApp() {
  const ctx = useContext(AppCtx);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
