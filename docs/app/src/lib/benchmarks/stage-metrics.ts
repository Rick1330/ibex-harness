import type { StageLatency } from "@/lib/benchmarks/types";

export const STAGE_BASE_KEYS = [
  "auth_lru",
  "auth_grpc",
  "rate_limit",
  "directive_resolve",
  "prompt_inject",
  "total_overhead",
] as const;

export type StageBaseKey = (typeof STAGE_BASE_KEYS)[number];

export interface StagePercentileRow {
  base: StageBaseKey;
  label: string;
  p50?: number;
  p95?: number;
  p99?: number;
  p999?: number;
}

function readOptional(stages: StageLatency, key: string): number | undefined {
  const value = stages[key as keyof StageLatency];
  return typeof value === "number" ? value : undefined;
}

export function stagePercentileRows(
  stages: StageLatency,
  labels: Record<string, string>,
): StagePercentileRow[] {
  return STAGE_BASE_KEYS.map((base) => ({
    base,
    label: labels[`${base}_p99_ms`] ?? base,
    p50: readOptional(stages, `${base}_p50_ms`),
    p95: readOptional(stages, `${base}_p95_ms`),
    p99: readOptional(stages, `${base}_p99_ms`),
    p999: readOptional(stages, `${base}_p999_ms`),
  }));
}
