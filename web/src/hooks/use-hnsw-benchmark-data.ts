"use client";

import useSWR, { type KeyedMutator } from "swr";

import { benchmarkDataErrorMessage } from "@/hooks/benchmark-data-error";
import { HNSW_BENCHMARK_DATA_URL } from "@/lib/benchmarks/constants";
import {
  hnswBenchmarkDataSchema,
  type HnswBenchmarkDataParsed,
  type HnswBenchmarkRun,
} from "@/lib/benchmarks/hnsw-schema";
import {
  BENCHMARK_JSON_SWR_OPTIONS,
  loadBenchmarkJson,
} from "@/lib/benchmarks/parse-json-response";

const LOAD_ERROR = "Failed to load HNSW benchmark data";

function fetchHnswBenchmarkData(): Promise<HnswBenchmarkDataParsed> {
  return loadBenchmarkJson(
    () =>
      fetch(HNSW_BENCHMARK_DATA_URL, {
        signal: AbortSignal.timeout(10_000),
      }),
    hnswBenchmarkDataSchema,
  );
}

export function useHnswBenchmarkData(): {
  data: HnswBenchmarkDataParsed | undefined;
  runs: HnswBenchmarkRun[];
  latest: HnswBenchmarkRun | null;
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
  refresh: KeyedMutator<HnswBenchmarkDataParsed>;
} {
  const { data, error, isLoading, mutate } = useSWR(
    HNSW_BENCHMARK_DATA_URL,
    fetchHnswBenchmarkData,
    BENCHMARK_JSON_SWR_OPTIONS,
  );

  const runs = data?.runs ?? [];
  return {
    data,
    runs,
    latest: runs[0] ?? null,
    isLoading,
    isError: Boolean(error),
    errorMessage: benchmarkDataErrorMessage(error, LOAD_ERROR),
    refresh: mutate,
  };
}
