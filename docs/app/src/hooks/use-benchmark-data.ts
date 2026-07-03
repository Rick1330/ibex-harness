"use client";

import useSWR from "swr";

import { BENCHMARK_DATA_URL } from "@/lib/benchmarks/constants";
import type { BenchmarkData, BenchmarkRun } from "@/lib/benchmarks/types";

export function useBenchmarkData() {
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
    refresh: mutate,
  };
}
