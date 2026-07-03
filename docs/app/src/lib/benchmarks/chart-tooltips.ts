import type { TrendDatum } from "@/lib/benchmarks/plot";
import { formatDeltaPct, formatMs } from "@/lib/benchmarks/format";

export function formatTrendTipTitle(datum: TrendDatum, valueLabel = "Value"): string {
  const prPart = datum.prLabel ? ` · ${datum.prLabel}` : "";
  const when = datum.timestamp ?? datum.date.toISOString();

  const lines = [
    `${datum.shortSha}${prPart}`,
    new Date(when).toUTCString(),
    `${valueLabel}: ${formatMs(datum.value)}`,
    ...(typeof datum.deltaPct === "number"
      ? [`vs baseline: ${formatDeltaPct(datum.deltaPct)}`]
      : []),
    ...(typeof datum.budgetPct === "number" && Number.isFinite(datum.budgetPct)
      ? [`Budget: ${Math.round(datum.budgetPct)}% of target`]
      : []),
    ...(datum.runner ? [datum.runner] : []),
  ];

  return lines.join("\n");
}

export function formatThroughputTipTitle(datum: TrendDatum): string {
  return formatTrendTipTitle(
    { ...datum, value: datum.value },
    "Throughput",
  ).replace(
    `Throughput: ${formatMs(datum.value)}`,
    `Throughput: ${Math.round(datum.value).toLocaleString("en-US")} req/s`,
  );
}
