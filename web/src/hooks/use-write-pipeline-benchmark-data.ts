"use client";

import useSWR, { type KeyedMutator } from "swr";

import { WRITE_PIPELINE_BENCHMARK_DATA_URL } from "@/lib/benchmarks/constants";
import {
  writePipelineBenchmarkDataSchema,
  type WritePipelineBenchmarkDataParsed,
  type WritePipelineBenchmarkRun,
} from "@/lib/benchmarks/write-pipeline-schema";

const LOAD_ERROR = "Failed to load write-pipeline benchmark data";

async function fetchWritePipelineData(
  url: string,
): Promise<WritePipelineBenchmarkDataParsed> {
  const response = await fetch(url, { signal: AbortSignal.timeout(10_000) });
  if (!response.ok) {
    throw new Error(`Failed to load write-pipeline benchmark data (${response.status})`);
  }
  const json: unknown = await response.json();
  return writePipelineBenchmarkDataSchema.parse(json);
}

export function useWritePipelineBenchmarkData(): {
  data: WritePipelineBenchmarkDataParsed | undefined;
  runs: WritePipelineBenchmarkRun[];
  latest: WritePipelineBenchmarkRun | null;
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
  refresh: KeyedMutator<WritePipelineBenchmarkDataParsed>;
} {
  const { data, error, isLoading, mutate } = useSWR(
    WRITE_PIPELINE_BENCHMARK_DATA_URL,
    fetchWritePipelineData,
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
    errorMessage: error instanceof Error ? error.message : error ? LOAD_ERROR : null,
    refresh: mutate,
  };
}
