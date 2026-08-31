"use client";

import type { KeyedMutator } from "swr";

import { RANKING_QUALITY_BENCHMARK_DATA_URL } from "@/lib/benchmarks/constants";
import {
  rankingQualityBenchmarkDataSchema,
  type RankingQualityBenchmarkDataParsed,
  type RankingQualityBenchmarkRun,
} from "@/lib/benchmarks/ranking-quality-schema";
import { useJsonBenchmarkData } from "@/hooks/use-json-benchmark-data";

const LOAD_ERROR = "Failed to load ranking-quality benchmark data";

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
    LOAD_ERROR,
  );
}
