"use client";

import useSWR, { type KeyedMutator } from "swr";
import type { ZodType } from "zod";

import { benchmarkDataErrorMessage } from "@/hooks/benchmark-data-error";
import {
  HNSW_BENCHMARK_DATA_URL,
  RANKING_QUALITY_BENCHMARK_DATA_URL,
  WRITE_PIPELINE_BENCHMARK_DATA_URL,
} from "@/lib/benchmarks/constants";

const BENCHMARK_DATA_URLS = [
  HNSW_BENCHMARK_DATA_URL,
  RANKING_QUALITY_BENCHMARK_DATA_URL,
  WRITE_PIPELINE_BENCHMARK_DATA_URL,
] as const;

export type BenchmarkJsonDataUrl = (typeof BENCHMARK_DATA_URLS)[number];

async function fetchWithTimeout(url: BenchmarkJsonDataUrl): Promise<Response> {
  switch (url) {
    case HNSW_BENCHMARK_DATA_URL:
      return fetch(HNSW_BENCHMARK_DATA_URL, { signal: AbortSignal.timeout(10_000) });
    case RANKING_QUALITY_BENCHMARK_DATA_URL:
      return fetch(RANKING_QUALITY_BENCHMARK_DATA_URL, {
        signal: AbortSignal.timeout(10_000),
      });
    case WRITE_PIPELINE_BENCHMARK_DATA_URL:
      return fetch(WRITE_PIPELINE_BENCHMARK_DATA_URL, {
        signal: AbortSignal.timeout(10_000),
      });
    default: {
      const _exhaustive: never = url;
      throw new Error(`Unsupported benchmark data URL: ${String(_exhaustive)}`);
    }
  }
}

async function fetchParsedJson<T>(
  url: BenchmarkJsonDataUrl,
  schema: ZodType<T>,
): Promise<T> {
  const response = await fetchWithTimeout(url);
  if (!response.ok) {
    throw new Error(`Failed to load benchmark data (${response.status})`);
  }
  const json: unknown = await response.json();
  return schema.parse(json);
}

export function useJsonBenchmarkData<TData extends { runs: unknown[] }>(
  url: BenchmarkJsonDataUrl,
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
    () => fetchParsedJson(url, schema),
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
