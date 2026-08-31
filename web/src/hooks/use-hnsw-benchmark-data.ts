"use client";

import type { KeyedMutator } from "swr";

import { useJsonBenchmarkData } from "@/hooks/use-json-benchmark-data";
import { HNSW_BENCHMARK_DATA_URL } from "@/lib/benchmarks/constants";
import {
  hnswBenchmarkDataSchema,
  type HnswBenchmarkDataParsed,
  type HnswBenchmarkRun,
} from "@/lib/benchmarks/hnsw-schema";

const LOAD_ERROR = "Failed to load HNSW benchmark data";

export function useHnswBenchmarkData(): {
  data: HnswBenchmarkDataParsed | undefined;
  runs: HnswBenchmarkRun[];
  latest: HnswBenchmarkRun | null;
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
  refresh: KeyedMutator<HnswBenchmarkDataParsed>;
} {
  return useJsonBenchmarkData(
    HNSW_BENCHMARK_DATA_URL,
    hnswBenchmarkDataSchema,
    LOAD_ERROR,
  );
}
