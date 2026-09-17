import { createFileRoute } from "@tanstack/react-router";
import { Database, Rows3, TableProperties, Clock3, Radio, RotateCcw } from "lucide-react";
import { cloneElement, useState, type ReactElement, type ReactNode } from "react";

import { DatasetTable } from "@/components/data/dataset-table";
import { ModuleDatasetPicker } from "@/components/data/module-dataset-picker";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Panel, SectionTitle, StatPill } from "@/components/ui/panel";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useDataCatalog, useDataRows, useDataStatus } from "@/hooks/use-data";
import type { DataDataset, DataModule } from "@/lib/api/types";
import { formatIstDateTime } from "@/lib/formatters";

export const Route = createFileRoute("/data")({
  head: () => ({ meta: [{ title: "Data · Mahindra AI Command Center" }] }),
  component: DataPage,
});

const DEFAULT_MODULE_ID = "warranty-quality";
const DEFAULT_DATASET_ID = "manufacturing_timeseries";
const PAGE_SIZES = [25, 50, 100, 200];

function statusTone(status: string): "default" | "success" | "warning" | "danger" | "info" {
  if (status === "LIVE") return "success";
  if (status === "STALE" || status === "PAUSED") return "warning";
  if (status === "ERROR" || status === "NOT_READY") return "danger";
  return "default";
}

function findDataset(
  modules: DataModule[],
  datasetId: string | undefined,
): DataDataset | undefined {
  return modules.flatMap((module) => module.datasets).find((dataset) => dataset.id === datasetId);
}

function DataPage() {
  const catalogQuery = useDataCatalog();
  const modules = catalogQuery.data?.modules ?? [];
  const [moduleId, setModuleId] = useState(DEFAULT_MODULE_ID);
  const [datasetId, setDatasetId] = useState<string | undefined>(DEFAULT_DATASET_ID);
  const [pageSize, setPageSize] = useState(50);
  const [page, setPage] = useState(1);
  const [cursor, setCursor] = useState<string | undefined>();
  const [before, setBefore] = useState<string | undefined>();

  const selectedModule = modules.find((module) => module.id === moduleId);
  const selectedDataset = findDataset(modules, datasetId);
  const statusQuery = useDataStatus(datasetId);
  const refreshKey = page === 1 ? statusQuery.data?.data_version : undefined;
  const rowsQuery = useDataRows(datasetId, pageSize, cursor, before, refreshKey);
  const responseMetadata = rowsQuery.data?.metadata;
  const liveStatus = statusQuery.data?.live_status ?? responseMetadata?.live_status ?? "CONNECTING";
  const totalRows = responseMetadata?.total_rows ?? statusQuery.data?.total_rows ?? 0;
  const columnCount = responseMetadata?.column_count ?? selectedDataset?.columns.length ?? 0;
  const latestTimestamp = responseMetadata?.latest_timestamp ?? statusQuery.data?.latest_timestamp;
  const hasNewerRows =
    page > 1 &&
    Boolean(
      statusQuery.data?.data_version &&
      statusQuery.data.data_version !== responseMetadata?.data_version,
    );

  const resetPaging = () => {
    setPage(1);
    setCursor(undefined);
    setBefore(undefined);
  };

  const selectModule = (nextModuleId: string) => {
    const nextModule = modules.find((module) => module.id === nextModuleId);
    setModuleId(nextModuleId);
    setDatasetId(nextModule?.datasets[0]?.id);
    resetPaging();
  };

  const selectDataset = (dataset: DataDataset) => {
    setDatasetId(dataset.id);
    resetPaging();
  };

  const goNext = () => {
    const nextCursor = rowsQuery.data?.pagination.next_cursor;
    if (!nextCursor) return;
    setCursor(nextCursor);
    setBefore(undefined);
    setPage((current) => current + 1);
  };

  const goPrevious = () => {
    const previousCursor = rowsQuery.data?.pagination.previous_cursor;
    if (!previousCursor || page <= 1) return;
    setBefore(previousCursor);
    setCursor(undefined);
    setPage((current) => Math.max(1, current - 1));
  };

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Data"
        subtitle="Explore the datasets behind every Mahindra AI Nexus screen and operational module."
        right={
          <StatPill tone={statusTone(liveStatus)}>
            <span className="h-1.5 w-1.5 rounded-full bg-current" /> {liveStatus}
          </StatPill>
        }
      />

      {catalogQuery.isError && (
        <Alert variant="destructive">
          <AlertTitle>Dataset catalog unavailable</AlertTitle>
          <AlertDescription>
            {catalogQuery.error instanceof Error
              ? catalogQuery.error.message
              : "The backend catalog could not be loaded."}
          </AlertDescription>
        </Alert>
      )}

      <ModuleDatasetPicker
        modules={modules}
        selectedModuleId={moduleId}
        selectedDatasetId={datasetId}
        onModuleChange={selectModule}
        onDatasetSelect={selectDataset}
      />

      {selectedDataset && (
        <>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <MetadataCard
              icon={<Rows3 />}
              label="Total rows"
              value={totalRows.toLocaleString("en-IN")}
            />
            <MetadataCard icon={<TableProperties />} label="Columns" value={String(columnCount)} />
            <MetadataCard
              icon={<Clock3 />}
              label="Latest timestamp"
              value={latestTimestamp ? formatIstDateTime(latestTimestamp) : "—"}
            />
            <MetadataCard
              icon={<Radio />}
              label="Source / status"
              value={responseMetadata?.source ?? "PostgreSQL runtime"}
              detail={liveStatus}
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Database className="h-4 w-4 text-primary" />
              <span>
                {selectedModule?.label} / {selectedDataset.display_name}
              </span>
              {page === 1 && selectedDataset.refresh_mode === "LIVE" && (
                <span className="text-emerald-300">· latest records auto-refresh</span>
              )}
              {page > 1 && <span>· older page held in place</span>}
            </div>
            <div className="flex items-center gap-2">
              <label htmlFor="data-page-size" className="text-xs text-muted-foreground">
                Rows per page
              </label>
              <Select
                value={String(pageSize)}
                onValueChange={(value) => {
                  setPageSize(Number(value));
                  resetPaging();
                }}
              >
                <SelectTrigger id="data-page-size" className="h-8 w-24 bg-white/[0.03] text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PAGE_SIZES.map((size) => (
                    <SelectItem key={size} value={String(size)}>
                      {size}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {hasNewerRows && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-primary/30 bg-primary/10 px-4 py-3 text-xs text-primary">
              <span>New records are available in {selectedDataset.display_name}.</span>
              <Button size="sm" variant="outline" onClick={resetPaging}>
                <RotateCcw /> View latest
              </Button>
            </div>
          )}

          {rowsQuery.isError && (
            <Alert variant="destructive">
              <AlertTitle>Dataset rows unavailable</AlertTitle>
              <AlertDescription>
                {rowsQuery.error instanceof Error
                  ? rowsQuery.error.message
                  : "The selected dataset could not be loaded."}
              </AlertDescription>
            </Alert>
          )}

          <DatasetTable
            dataset={selectedDataset}
            data={rowsQuery.data}
            metadata={responseMetadata}
            page={page}
            isLoading={rowsQuery.isLoading}
            isFetching={rowsQuery.isFetching}
            onRefresh={() => void rowsQuery.refetch()}
            onNext={goNext}
            onPrevious={goPrevious}
          />
        </>
      )}
    </div>
  );
}

function MetadataCard({
  icon,
  label,
  value,
  detail,
}: {
  icon: ReactElement<{ className?: string }>;
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="glass rounded-xl p-4">
      <div className="flex items-center gap-2 text-muted-foreground">
        {cloneElement(icon, { className: "h-4 w-4 text-primary" })}
        <span className="text-[10px] uppercase tracking-widest">{label}</span>
      </div>
      <div className="mt-2 truncate text-sm font-semibold" title={value}>
        {value}
      </div>
      {detail && (
        <div className="mt-1 text-[10px] uppercase tracking-widest text-emerald-300">{detail}</div>
      )}
    </div>
  );
}
