"use client";

import useSWR from "swr";

import { BENCHMARK_DATA_URL } from "@/lib/benchmarks/constants";
import { parseBenchmarkData } from "@/lib/benchmarks/schema";
import type { BenchmarkData, BenchmarkRun } from "@/lib/benchmarks/types";

async function fetchBenchmarkData(url: string): Promise<BenchmarkData> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to load benchmark data (${response.status})`);
  }
  const json: unknown = await response.json();
  return parseBenchmarkData(json);
}

export function useBenchmarkData() {
  const { data, error, isLoading, mutate } = useSWR(BENCHMARK_DATA_URL, fetchBenchmarkData, {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    dedupingInterval: 60_000,
  });

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
