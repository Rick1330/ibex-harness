import type {
  DriftActionStage,
  DriftActionTaken,
  DriftAlertStatus,
  DriftSeverity,
  FeatureClass,
  StatisticalTest,
} from "@/lib/drift/types"

export const FEATURE_LABEL: Record<FeatureClass, string> = {
  token_quantile_sketch: "Token quantile sketch",
  tool_distribution_smoothed: "Tool distribution",
  response_cluster_centroids: "Response clusters",
  error_successes: "Error successes",
  error_trials: "Error trials",
}

export const TEST_LABEL: Record<StatisticalTest, string> = {
  ks_two_sample: "KS two-sample",
  jensen_shannon: "Jensen–Shannon divergence",
  chi_squared_cluster: "χ² cluster membership",
  beta_binomial_ci: "Beta–Binomial CI overlap",
}

export const STAGE_LABEL: Record<DriftActionStage, string> = {
  shadow: "Shadow",
  notify: "Notify-only",
  auto_suspend: "Auto-suspend",
}

export function severityTone(
  s: DriftSeverity,
): "ok" | "error" | "warn" | "muted" | "info" {
  if (s === "high") return "error"
  if (s === "medium") return "warn"
  return "info"
}

export function statusTone(
  s: DriftAlertStatus,
): "ok" | "error" | "warn" | "muted" | "info" {
  if (s === "resolved") return "ok"
  if (s === "false_positive") return "muted"
  if (s === "open") return "error"
  return "warn"
}

export function actionTakenLabel(a: DriftActionTaken): string {
  if (a === "logged") return "logged"
  if (a === "notified") return "notified"
  return "suspended"
}

export function relativeAge(
  iso: string,
  now = Date.UTC(2026, 1, 11, 16, 0, 0),
) {
  const ms = now - new Date(iso).getTime()
  const h = Math.floor(ms / 3_600_000)
  if (h < 1) return "<1h"
  if (h < 48) return `${h}h`
  return `${Math.floor(h / 24)}d`
}
