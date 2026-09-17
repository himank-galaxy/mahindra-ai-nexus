import { Database, Link2, Network, Table2 } from "lucide-react";

import { Panel, StatPill } from "@/components/ui/panel";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { DataDataset, DataModule } from "@/lib/api/types";

function relationshipTone(
  relationship: string,
): "default" | "success" | "warning" | "danger" | "info" {
  if (relationship === "DIRECT") return "success";
  if (relationship === "GOVERNANCE") return "warning";
  if (relationship === "LINEAGE") return "info";
  return "default";
}

export function ModuleDatasetPicker({
  modules,
  selectedModuleId,
  selectedDatasetId,
  onModuleChange,
  onDatasetSelect,
}: {
  modules: DataModule[];
  selectedModuleId: string;
  selectedDatasetId?: string;
  onModuleChange: (moduleId: string) => void;
  onDatasetSelect: (dataset: DataDataset) => void;
}) {
  const selectedModule = modules.find((module) => module.id === selectedModuleId);

  return (
    <Panel
      title="Data sources"
      subtitle="Select an application module, then open any associated dataset."
      actions={<Network className="h-4 w-4 text-primary" />}
    >
      <div className="space-y-5">
        <div className="max-w-xl space-y-2">
          <label
            className="text-[10px] uppercase tracking-widest text-muted-foreground"
            htmlFor="data-module"
          >
            Screen / Module
          </label>
          <Select value={selectedModuleId} onValueChange={onModuleChange}>
            <SelectTrigger id="data-module" className="bg-white/[0.03]">
              <SelectValue placeholder="Select a screen or module" />
            </SelectTrigger>
            <SelectContent>
              {modules.map((module) => (
                <SelectItem key={module.id} value={module.id}>
                  {module.label} ({module.datasets.length})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selectedModule && (
            <p className="text-xs text-muted-foreground">{selectedModule.description}</p>
          )}
        </div>

        <div>
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
              Datasets used by {selectedModule?.label ?? "this module"}
            </div>
            <StatPill tone="info">{selectedModule?.datasets.length ?? 0} datasets</StatPill>
          </div>

          {selectedModule?.datasets.length ? (
            <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
              {selectedModule.datasets.map((dataset) => {
                const link = dataset.links.find((item) => item.module_id === selectedModule.id);
                const active = selectedDatasetId === dataset.id;
                return (
                  <button
                    key={dataset.id}
                    type="button"
                    onClick={() => onDatasetSelect(dataset)}
                    className={`group rounded-xl border p-3 text-left transition-all ${
                      active
                        ? "border-primary/60 bg-primary/10 shadow-inner shadow-primary/10"
                        : "border-white/10 bg-white/[0.03] hover:border-primary/40 hover:bg-white/[0.05]"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 rounded-md bg-primary/10 p-2 text-primary">
                        {dataset.refresh_mode === "LIVE" ? (
                          <Network className="h-4 w-4" />
                        ) : (
                          <Table2 className="h-4 w-4" />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium">{dataset.display_name}</span>
                          {link && (
                            <StatPill tone={relationshipTone(link.relationship_type)}>
                              {link.relationship_type}
                            </StatPill>
                          )}
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
                          <span className="font-mono">{dataset.table_name}</span>
                          <span>·</span>
                          <span>{dataset.columns.length} columns</span>
                          {dataset.refresh_mode === "LIVE" && (
                            <>
                              <span>·</span>
                              <span className="text-emerald-300">live feed</span>
                            </>
                          )}
                        </div>
                        <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">
                          {dataset.description}
                        </p>
                        {selectedModule.id === "other-supporting" && dataset.links.length > 1 && (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {dataset.links
                              .filter((item) => item.module_id !== "other-supporting")
                              .map((item) => {
                                const related = modules.find(
                                  (module) => module.id === item.module_id,
                                );
                                return related ? (
                                  <span
                                    key={item.module_id}
                                    className="inline-flex items-center gap-1 rounded-md bg-white/5 px-2 py-1 text-[10px] text-muted-foreground"
                                  >
                                    <Link2 className="h-3 w-3" /> {related.label}
                                  </span>
                                ) : null;
                              })}
                          </div>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-6 text-center text-sm text-muted-foreground">
              <Database className="mx-auto mb-2 h-5 w-5 text-muted-foreground/60" />
              No database dataset is registered for this module.
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}
