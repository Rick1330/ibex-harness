"use client";

import type { KeyedMutator } from "swr";

import { useJsonBenchmarkData } from "@/hooks/use-json-benchmark-data";
import {
  RANKING_QUALITY_BENCHMARK_DATA_URL,
  WRITE_PIPELINE_BENCHMARK_DATA_URL,
} from "@/lib/benchmarks/constants";
import {
  rankingQualityBenchmarkDataSchema,
  type RankingQualityBenchmarkDataParsed,
  type RankingQualityBenchmarkRun,
} from "@/lib/benchmarks/ranking-quality-schema";
import {
  writePipelineBenchmarkDataSchema,
  type WritePipelineBenchmarkDataParsed,
  type WritePipelineBenchmarkRun,
} from "@/lib/benchmarks/write-pipeline-schema";

const RANKING_LOAD_ERROR = "Failed to load ranking-quality benchmark data";
const WRITE_LOAD_ERROR = "Failed to load write-pipeline benchmark data";

export function useRankingQualityBenchmarkData(): {
  data: RankingQualityBenchmarkDataParsed | undefined;
  runs: RankingQualityBenchmarkRun[];
  latest: RankingQualityBenchmarkRun | null;
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
  refresh: KeyedMutator<RankingQualityBenchmarkDataParsed>;
} {
  return useJsonBenchmarkData(
    RANKING_QUALITY_BENCHMARK_DATA_URL,
    rankingQualityBenchmarkDataSchema,
    RANKING_LOAD_ERROR,
  );
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
  return useJsonBenchmarkData(
    WRITE_PIPELINE_BENCHMARK_DATA_URL,
    writePipelineBenchmarkDataSchema,
    WRITE_LOAD_ERROR,
  );
}
