import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Panel, StatPill } from "@/components/ui/panel";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatIstDateTime } from "@/lib/formatters";
import type { DataDataset, DataMetadata, DataRows } from "@/lib/api/types";

function formatCell(value: unknown, column: string, timestampColumn?: string | null): string {
  if (value === null || value === undefined || value === "") return "—";
  if (column === timestampColumn || column.endsWith("_at") || column === "timestamp") {
    if (typeof value === "string") return formatIstDateTime(value);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number")
    return Number.isInteger(value)
      ? String(value)
      : value.toLocaleString("en-IN", { maximumFractionDigits: 4 });
  return String(value);
}

function statusTone(status: string): "default" | "success" | "warning" | "danger" | "info" {
  if (status === "LIVE") return "success";
  if (status === "STALE" || status === "PAUSED") return "warning";
  if (status === "ERROR" || status === "NOT_READY") return "danger";
  return "default";
}

export function DatasetTable({
  dataset,
  data,
  metadata,
  page,
  isLoading,
  isFetching,
  onRefresh,
  onNext,
  onPrevious,
}: {
  dataset?: DataDataset;
  data?: DataRows;
  metadata?: DataMetadata;
  page: number;
  isLoading: boolean;
  isFetching: boolean;
  onRefresh: () => void;
  onNext: () => void;
  onPrevious: () => void;
}) {
  const columns = data?.columns ?? dataset?.columns ?? [];
  const rows = data?.rows ?? [];
  const pagination = data?.pagination;
  const activeMetadata = metadata ?? data?.metadata;

  return (
    <Panel
      title={dataset ? dataset.display_name : "Dataset table"}
      subtitle={
        dataset
          ? `${dataset.table_name} · read-only PostgreSQL runtime view`
          : "Select a dataset to view its rows."
      }
      actions={
        dataset ? (
          <Button size="sm" variant="outline" onClick={onRefresh} disabled={isFetching}>
            <RefreshCw className={isFetching ? "animate-spin" : undefined} /> Refresh
          </Button>
        ) : undefined
      }
    >
      {!dataset ? (
        <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-10 text-center text-sm text-muted-foreground">
          Choose a dataset above to open its CSV-style table.
        </div>
      ) : isLoading && !data ? (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
            <div className="flex flex-wrap items-center gap-2">
              <StatPill tone={statusTone(activeMetadata?.live_status ?? dataset.refresh_mode)}>
                {activeMetadata?.live_status ?? dataset.refresh_mode}
              </StatPill>
              <span>{activeMetadata?.total_rows.toLocaleString("en-IN") ?? "—"} rows</span>
              <span>·</span>
              <span>{columns.length} columns</span>
              {activeMetadata?.latest_timestamp && (
                <>
                  <span>·</span>
                  <span>Latest {formatIstDateTime(activeMetadata.latest_timestamp)}</span>
                </>
              )}
            </div>
            {isFetching && <span className="text-primary">Updating latest records…</span>}
          </div>

          <div className="overflow-hidden rounded-xl border border-white/10">
            <div className="max-h-[620px] overflow-auto">
              <Table className="min-w-max text-xs">
                <TableHeader className="sticky top-0 z-10 bg-[#11131a]">
                  <TableRow>
                    {columns.map((column) => (
                      <TableHead
                        key={column.name}
                        className="whitespace-nowrap border-r border-white/5 px-3 py-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground"
                      >
                        {column.name}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.length ? (
                    rows.map((row, rowIndex) => (
                      <TableRow
                        key={`${rowIndex}-${String(row[dataset.timestamp_column ?? columns[0]?.name])}`}
                      >
                        {columns.map((column) => (
                          <TableCell
                            key={column.name}
                            className="whitespace-nowrap border-r border-white/5 px-3 py-2 font-mono text-[11px] text-foreground/85"
                          >
                            {formatCell(row[column.name], column.name, dataset.timestamp_column)}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell
                        colSpan={Math.max(columns.length, 1)}
                        className="h-28 text-center text-muted-foreground"
                      >
                        No rows available for this dataset.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">
              Page {page} · showing {rows.length.toLocaleString("en-IN")} records from the server
            </span>
            <Pagination className="mx-0 w-auto justify-end">
              <PaginationContent>
                <PaginationItem>
                  <PaginationPrevious
                    href="#"
                    aria-disabled={!pagination?.has_previous}
                    className={
                      !pagination?.has_previous ? "pointer-events-none opacity-40" : undefined
                    }
                    onClick={(event) => {
                      event.preventDefault();
                      if (pagination?.has_previous) onPrevious();
                    }}
                  />
                </PaginationItem>
                <PaginationItem>
                  <span className="inline-flex h-9 min-w-9 items-center justify-center rounded-md border border-primary/40 bg-primary/10 px-3 text-xs text-primary">
                    {page}
                  </span>
                </PaginationItem>
                <PaginationItem>
                  <PaginationNext
                    href="#"
                    aria-disabled={!pagination?.has_next}
                    className={!pagination?.has_next ? "pointer-events-none opacity-40" : undefined}
                    onClick={(event) => {
                      event.preventDefault();
                      if (pagination?.has_next) onNext();
                    }}
                  />
                </PaginationItem>
              </PaginationContent>
            </Pagination>
          </div>
        </>
      )}
    </Panel>
  );
}
