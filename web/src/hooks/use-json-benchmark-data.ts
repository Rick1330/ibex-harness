"use client";

import useSWR, { type KeyedMutator } from "swr";
import type { ZodType } from "zod";

import { benchmarkDataErrorMessage } from "@/hooks/benchmark-data-error";
import { assertSafeBenchmarkDataUrl } from "@/lib/benchmarks/benchmark-data-url";

async function fetchParsedJson<T>(url: string, schema: ZodType<T>): Promise<T> {
  const safeUrl = assertSafeBenchmarkDataUrl(url);
  const response = await fetch(safeUrl, { signal: AbortSignal.timeout(10_000) });
  if (!response.ok) {
    throw new Error(`Failed to load benchmark data (${response.status})`);
  }
  const json: unknown = await response.json();
  return schema.parse(json);
}

export function useJsonBenchmarkData<TData extends { runs: unknown[] }>(
  url: string,
  schema: ZodType<TData>,
  loadErrorMessage: string,
): {
  data: TData | undefined;
  runs: TData["runs"];
  latest: TData["runs"][number] | null;
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
  refresh: KeyedMutator<TData>;
} {
  const { data, error, isLoading, mutate } = useSWR(
    url,
    (fetchUrl: string) => fetchParsedJson(fetchUrl, schema),
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      dedupingInterval: 60_000,
    },
  );

  const runs = data?.runs ?? [];
  return {
    data,
    runs,
    latest: runs[0] ?? null,
    isLoading,
    isError: Boolean(error),
    errorMessage: benchmarkDataErrorMessage(error, loadErrorMessage),
    refresh: mutate,
  };
}
