"use client";

import useSWR, { type KeyedMutator } from "swr";

import { HNSW_BENCHMARK_DATA_URL } from "@/lib/benchmarks/constants";
import {
  hnswBenchmarkDataSchema,
  type HnswBenchmarkDataParsed,
  type HnswBenchmarkRun,
} from "@/lib/benchmarks/hnsw-schema";

const HNSW_LOAD_ERROR = "Failed to load HNSW benchmark data";

async function fetchHnswBenchmarkData(url: string): Promise<HnswBenchmarkDataParsed> {
  const response = await fetch(url, { signal: AbortSignal.timeout(10_000) });
  if (!response.ok) {
    throw new Error(`Failed to load HNSW benchmark data (${response.status})`);
  }
  const json: unknown = await response.json();
  return hnswBenchmarkDataSchema.parse(json);
}

function hnswErrorMessage(error: unknown): string | null {
  if (!error) return null;
  return error instanceof Error ? error.message : HNSW_LOAD_ERROR;
}

export function useHnswBenchmarkData(): {
  data: HnswBenchmarkDataParsed | undefined;
  runs: HnswBenchmarkRun[];
  latest: HnswBenchmarkRun | null;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  errorMessage: string | null;
  refresh: KeyedMutator<HnswBenchmarkDataParsed>;
} {
  const { data, error, isLoading, mutate } = useSWR<HnswBenchmarkDataParsed>(
    HNSW_BENCHMARK_DATA_URL,
    fetchHnswBenchmarkData,
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      dedupingInterval: 60_000,
    },
  );

  const runs = data?.runs ?? [];
  const latest: HnswBenchmarkRun | null = runs[0] ?? null;

  return {
    data,
    runs,
    latest,
    isLoading,
    isError: Boolean(error),
    error,
    errorMessage: hnswErrorMessage(error),
    refresh: mutate,
  };
}
