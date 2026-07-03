"use client";

import useSWR, { type KeyedMutator } from "swr";

import { BENCHMARK_DATA_URL } from "@/lib/benchmarks/constants";
import type { BenchmarkData, BenchmarkRun } from "@/lib/benchmarks/types";

const BENCHMARK_LOAD_ERROR = "Failed to load benchmark data";

function benchmarkErrorMessage(error: unknown): string | null {
  if (!error) {
    return null;
  }
  return error instanceof Error ? error.message : BENCHMARK_LOAD_ERROR;
}

export function useBenchmarkData(): {
  data: BenchmarkData | undefined;
  runs: BenchmarkRun[];
  latest: BenchmarkRun | null;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  errorMessage: string | null;
  refresh: KeyedMutator<BenchmarkData>;
} {
  const { data, error, isLoading, mutate } = useSWR<BenchmarkData>(BENCHMARK_DATA_URL);

  const runs = data?.runs ?? [];
  const latest: BenchmarkRun | null = runs[0] ?? null;

  return {
    data,
    runs,
    latest,
    isLoading,
    isError: Boolean(error),
    error,
    errorMessage: benchmarkErrorMessage(error),
    refresh: mutate,
  };
}
