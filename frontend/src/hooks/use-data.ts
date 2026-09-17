// TanStack Query hooks for the module-first Data explorer.

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiEnabled } from "@/lib/api/client";
import * as api from "@/lib/api/endpoints";
import type { DataCatalog, DataRows, DataStatus } from "@/lib/api/types";

export function useDataCatalog() {
  return useQuery<DataCatalog>({
    queryKey: ["data", "catalog"],
    queryFn: api.fetchDataCatalog,
    enabled: apiEnabled,
    staleTime: Infinity,
    retry: false,
  });
}

export function useDataStatus(datasetId: string | undefined) {
  return useQuery<DataStatus>({
    queryKey: ["data", "status", datasetId ?? ""],
    queryFn: () => api.fetchDataStatus(datasetId as string),
    enabled: apiEnabled && Boolean(datasetId),
    staleTime: 0,
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
    retry: false,
  });
}

export function useDataRows(
  datasetId: string | undefined,
  pageSize: number,
  cursor?: string,
  before?: string,
  refreshKey?: string,
) {
  return useQuery<DataRows>({
    queryKey: [
      "data",
      "rows",
      datasetId ?? "",
      pageSize,
      cursor ?? "",
      before ?? "",
      refreshKey ?? "",
    ],
    queryFn: () => api.fetchDataRows(datasetId as string, pageSize, cursor, before),
    enabled: apiEnabled && Boolean(datasetId),
    staleTime: 0,
    placeholderData: keepPreviousData,
    retry: false,
  });
}
