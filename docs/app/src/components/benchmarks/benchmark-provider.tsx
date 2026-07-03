"use client";

import type { ReactNode } from "react";
import { SWRConfig } from "swr";

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
}>;

export function BenchmarkProvider({ children }: BenchmarkProviderProps) {
  return (
    <SWRConfig
      value={{
        fetcher: fetchBenchmarkData,
        revalidateOnFocus: false,
        revalidateOnReconnect: false,
        dedupingInterval: 60_000,
      }}
    >
      {children}
    </SWRConfig>
  );
}
