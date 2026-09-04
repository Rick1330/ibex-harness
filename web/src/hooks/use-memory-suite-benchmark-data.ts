"use client";

import useSWR, { type KeyedMutator } from "swr";

import { benchmarkDataErrorMessage } from "@/hooks/benchmark-data-error";
import {
  EXTRACTION_QUALITY_BENCHMARK_DATA_URL,
  RANKING_QUALITY_BENCHMARK_DATA_URL,
  WRITE_PIPELINE_BENCHMARK_DATA_URL,
} from "@/lib/benchmarks/constants";
import {
  BENCHMARK_JSON_SWR_OPTIONS,
  loadBenchmarkJson,
} from "@/lib/benchmarks/parse-json-response";
import {
  extractionQualityBenchmarkDataSchema,
  type ExtractionQualityBenchmarkDataParsed,
  type ExtractionQualityBenchmarkRun,
} from "@/lib/benchmarks/extraction-quality-schema";
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
const EXTRACTION_LOAD_ERROR = "Failed to load extraction-quality benchmark data";

function fetchRankingQualityBenchmarkData(): Promise<RankingQualityBenchmarkDataParsed> {
  return loadBenchmarkJson(
    () =>
      fetch(RANKING_QUALITY_BENCHMARK_DATA_URL, {
        signal: AbortSignal.timeout(10_000),
      }),
    rankingQualityBenchmarkDataSchema,
  );
}

function fetchWritePipelineBenchmarkData(): Promise<WritePipelineBenchmarkDataParsed> {
  return loadBenchmarkJson(
    () =>
      fetch(WRITE_PIPELINE_BENCHMARK_DATA_URL, {
        signal: AbortSignal.timeout(10_000),
      }),
    writePipelineBenchmarkDataSchema,
  );
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
    fetchRankingQualityBenchmarkData,
    BENCHMARK_JSON_SWR_OPTIONS,
  );
  const runs = data?.runs ?? [];
  return {
    data,
    runs,
    latest: runs[0] ?? null,
    isLoading,
    isError: Boolean(error),
    errorMessage: benchmarkDataErrorMessage(error, RANKING_LOAD_ERROR),
    refresh: mutate,
  };
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
    fetchWritePipelineBenchmarkData,
    BENCHMARK_JSON_SWR_OPTIONS,
  );
  const runs = data?.runs ?? [];
  return {
    data,
    runs,
    latest: runs[0] ?? null,
    isLoading,
    isError: Boolean(error),
    errorMessage: benchmarkDataErrorMessage(error, WRITE_LOAD_ERROR),
    refresh: mutate,
  };
}

function fetchExtractionQualityBenchmarkData(): Promise<ExtractionQualityBenchmarkDataParsed> {
  return loadBenchmarkJson(
    () =>
      fetch(EXTRACTION_QUALITY_BENCHMARK_DATA_URL, {
        signal: AbortSignal.timeout(10_000),
      }),
    extractionQualityBenchmarkDataSchema,
  );
}

export function useExtractionQualityBenchmarkData(): {
  data: ExtractionQualityBenchmarkDataParsed | undefined;
  runs: ExtractionQualityBenchmarkRun[];
  latest: ExtractionQualityBenchmarkRun | null;
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
  refresh: KeyedMutator<ExtractionQualityBenchmarkDataParsed>;
} {
  const { data, error, isLoading, mutate } = useSWR(
    EXTRACTION_QUALITY_BENCHMARK_DATA_URL,
    fetchExtractionQualityBenchmarkData,
    BENCHMARK_JSON_SWR_OPTIONS,
  );
  const runs = data?.runs ?? [];
  return {
    data,
    runs,
    latest: runs[0] ?? null,
    isLoading,
    isError: Boolean(error),
    errorMessage: benchmarkDataErrorMessage(error, EXTRACTION_LOAD_ERROR),
    refresh: mutate,
  };
}
