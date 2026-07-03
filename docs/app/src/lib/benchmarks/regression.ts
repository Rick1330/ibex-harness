import { REGRESSION_THRESHOLD_PCT } from "./constants";

export function pctChange(
  baseline: number | null,
  current: number,
  higherIsBetter = false,
): number | null {
  if (baseline === null) {
    return null;
  }
  if (!Number.isFinite(baseline)) {
    return null;
  }
  if (baseline === 0) {
    return null;
  }
  const raw = ((current - baseline) / baseline) * 100;
  return higherIsBetter ? -raw : raw;
}

function exceedsThreshold(deltaPct: number | null, threshold: number): boolean {
  if (deltaPct === null || !Number.isFinite(deltaPct)) {
    return false;
  }
  return deltaPct > threshold;
}

export function isRegression(deltaPct: number | null, threshold = REGRESSION_THRESHOLD_PCT): boolean {
  return exceedsThreshold(deltaPct, threshold);
}

export function deltaForRun(
  metricKey: string,
  deltas: Record<string, number | null> | undefined,
): number | null {
  if (!deltas) {
    return null;
  }
  const value = deltas[metricKey];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
