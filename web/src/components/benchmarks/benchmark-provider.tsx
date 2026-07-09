"use client";

import type { ReactNode } from "react";
import { SWRConfig } from "swr";

import { BENCHMARK_DATA_URL } from "@/lib/benchmarks/constants";
import { parseBenchmarkData } from "@/lib/benchmarks/schema";
import type { BenchmarkData } from "@/lib/benchmarks/types";

async function fetchBenchmarkData(url: string): Promise<BenchmarkData> {
  const response = await fetch(url, { signal: AbortSignal.timeout(10_000) });
  if (!response.ok) {
    throw new Error(`Failed to load benchmark data (${response.status})`);
  }
  const json: unknown = await response.json();
  return parseBenchmarkData(json);
}

type BenchmarkProviderProps = Readonly<{
  children: ReactNode;
  fallbackData?: BenchmarkData;
}>;

export function BenchmarkProvider({ children, fallbackData }: BenchmarkProviderProps) {
  return (
    <SWRConfig
      value={{
        fetcher: fetchBenchmarkData,
        fallback: fallbackData ? { [BENCHMARK_DATA_URL]: fallbackData } : undefined,
        revalidateOnFocus: false,
        revalidateOnReconnect: false,
        dedupingInterval: 60_000,
      }}
    >
      {children}
    </SWRConfig>
  );
}
