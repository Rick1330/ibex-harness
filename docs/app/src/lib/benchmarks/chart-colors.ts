export type StageKey =
  | "auth_lru_p99_ms"
  | "auth_grpc_p99_ms"
  | "rate_limit_p99_ms"
  | "directive_resolve_p99_ms"
  | "prompt_inject_p99_ms"
  | "total_overhead_p99_ms";

export const STAGE_LABELS: Record<StageKey, string> = {
  auth_lru_p99_ms: "Auth (LRU hit)",
  auth_grpc_p99_ms: "Auth (gRPC fallback)",
  rate_limit_p99_ms: "Rate limit",
  directive_resolve_p99_ms: "Directive resolve",
  prompt_inject_p99_ms: "Prompt injection",
  total_overhead_p99_ms: "Total overhead",
};

/** Distinct hues from the Matte Graphite token set — easy to tell apart in waterfall bars. */
const LIGHT_STAGE_COLORS: Record<StageKey, string> = {
  auth_lru_p99_ms: "hsl(142 71% 35%)",
  auth_grpc_p99_ms: "hsl(213 94% 68%)",
  rate_limit_p99_ms: "hsl(32 95% 44%)",
  directive_resolve_p99_ms: "hsl(280 65% 48%)",
  prompt_inject_p99_ms: "hsl(199 89% 58%)",
  total_overhead_p99_ms: "hsl(240 10% 4%)",
};

const DARK_STAGE_COLORS: Record<StageKey, string> = {
  auth_lru_p99_ms: "hsl(142 69% 58%)",
  auth_grpc_p99_ms: "hsl(213 94% 68%)",
  rate_limit_p99_ms: "hsl(38 92% 50%)",
  directive_resolve_p99_ms: "hsl(280 65% 60%)",
  prompt_inject_p99_ms: "hsl(199 89% 58%)",
  total_overhead_p99_ms: "hsl(0 0% 98%)",
};

export function stageColors(isDark: boolean): Record<StageKey, string> {
  return isDark ? DARK_STAGE_COLORS : LIGHT_STAGE_COLORS;
}

export function stageColor(key: StageKey, isDark: boolean): string {
  return stageColors(isDark)[key];
}

export function otherOverheadColor(isDark: boolean): string {
  return isDark ? "hsl(240 5% 65%)" : "hsl(240 5% 84%)";
}

/** Percentile / trend series — matches waterfall stage hues. */
export const CHART_SERIES_LIGHT = [
  "hsl(142 71% 35%)",
  "hsl(213 94% 68%)",
  "hsl(32 95% 44%)",
  "hsl(280 65% 48%)",
] as const;

export const CHART_SERIES_DARK = [
  "hsl(142 69% 58%)",
  "hsl(213 94% 68%)",
  "hsl(38 92% 50%)",
  "hsl(280 65% 60%)",
] as const;

export const CHART_SERIES_DUAL_LIGHT = [
  "hsl(213 94% 68%)",
  "hsl(199 89% 58%)",
] as const;

export const CHART_SERIES_DUAL_DARK = [
  "hsl(213 94% 68%)",
  "hsl(199 89% 58%)",
] as const;

export const CHART_PRIMARY_LINE_LIGHT = "hsl(213 94% 68%)";
export const CHART_PRIMARY_LINE_DARK = "hsl(213 94% 68%)";
