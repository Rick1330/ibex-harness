"use client";

import useSWR, { type KeyedMutator } from "swr";

import { RANKING_QUALITY_BENCHMARK_DATA_URL } from "@/lib/benchmarks/constants";
import {
  rankingQualityBenchmarkDataSchema,
  type RankingQualityBenchmarkDataParsed,
  type RankingQualityBenchmarkRun,
} from "@/lib/benchmarks/ranking-quality-schema";

const LOAD_ERROR = "Failed to load ranking-quality benchmark data";

function rankingQualityErrorMessage(error: unknown): string | null {
  if (!error) return null;
  return error instanceof Error ? error.message : LOAD_ERROR;
}

async function fetchRankingQualityData(
  url: string,
): Promise<RankingQualityBenchmarkDataParsed> {
  const response = await fetch(url, { signal: AbortSignal.timeout(10_000) });
  if (!response.ok) {
    throw new Error(`Failed to load ranking-quality benchmark data (${response.status})`);
  }
  const json: unknown = await response.json();
  return rankingQualityBenchmarkDataSchema.parse(json);
}

export function useRankingQualityBenchmarkData(): {
  data: RankingQualityBenchmarkDataParsed | undefined;
  runs: RankingQualityBenchmarkRun[];
  latest: RankingQualityBenchmarkRun | null;
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
  refresh: KeyedMutator<RankingQualityBenchmarkDataParsed>;
} {
  const { data, error, isLoading, mutate } = useSWR(
    RANKING_QUALITY_BENCHMARK_DATA_URL,
    fetchRankingQualityData,
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
    errorMessage: rankingQualityErrorMessage(error),
    refresh: mutate,
  };
}
