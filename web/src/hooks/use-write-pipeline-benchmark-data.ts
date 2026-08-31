"use client";

import type { KeyedMutator } from "swr";

import { WRITE_PIPELINE_BENCHMARK_DATA_URL } from "@/lib/benchmarks/constants";
import {
  writePipelineBenchmarkDataSchema,
  type WritePipelineBenchmarkDataParsed,
  type WritePipelineBenchmarkRun,
} from "@/lib/benchmarks/write-pipeline-schema";
import { useJsonBenchmarkData } from "@/hooks/use-json-benchmark-data";

const LOAD_ERROR = "Failed to load write-pipeline benchmark data";

export function useWritePipelineBenchmarkData(): {
  data: WritePipelineBenchmarkDataParsed | undefined;
  runs: WritePipelineBenchmarkRun[];
  latest: WritePipelineBenchmarkRun | null;
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
  refresh: KeyedMutator<WritePipelineBenchmarkDataParsed>;
} {
  return useJsonBenchmarkData(
    WRITE_PIPELINE_BENCHMARK_DATA_URL,
    writePipelineBenchmarkDataSchema,
    LOAD_ERROR,
  );
}
