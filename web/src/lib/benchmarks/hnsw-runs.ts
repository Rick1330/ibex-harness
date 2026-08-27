import type { HnswBenchmarkRun, HnswSizeResult } from "@/lib/benchmarks/hnsw-schema";
import type { TimeRange } from "@/lib/benchmarks/plot";

const RANGE_DAYS: Record<Exclude<TimeRange, "all">, number> = {
  "7d": 7,
  "14d": 14,
  "30d": 30,
  "90d": 90,
};

export function corpusSizeLabel(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(0)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

export function formatRecallPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function findHnswRunBySha(
  runs: readonly HnswBenchmarkRun[],
  sha: string,
): HnswBenchmarkRun | null {
  const normalized = sha.toLowerCase();
  return (
    runs.find(
      (run) =>
        run.short_sha.toLowerCase() === normalized ||
        run.sha.toLowerCase() === normalized ||
        run.sha.toLowerCase().startsWith(normalized),
    ) ?? null
  );
}

export function findHnswRunByNumber(
  runs: readonly HnswBenchmarkRun[],
  runNumber: number,
): HnswBenchmarkRun | null {
  if (!Number.isInteger(runNumber) || runNumber < 0) {
    return null;
  }
  return runs.find((run) => run.run_number === runNumber) ?? null;
}

export function filterHnswRunsByRange(
  runs: readonly HnswBenchmarkRun[],
  range: TimeRange,
): HnswBenchmarkRun[] {
  if (range === "all" || runs.length === 0) {
    return [...runs];
  }
  const cutoff = Date.now() - RANGE_DAYS[range] * 24 * 60 * 60 * 1000;
  return runs.filter((run) => new Date(run.timestamp).getTime() >= cutoff);
}

export function largestCorpusResult(run: HnswBenchmarkRun): HnswSizeResult | null {
  if (run.results.length === 0) return null;
  return run.results.reduce((best, cur) =>
    cur.corpus_size > best.corpus_size ? cur : best,
  );
}

export function resultAtCorpusSize(
  run: HnswBenchmarkRun,
  size: number,
): HnswSizeResult | undefined {
  return run.results.find((r) => r.corpus_size === size);
}

export function uniqueCorpusSizes(runs: readonly HnswBenchmarkRun[]): number[] {
  const sizes = new Set<number>();
  for (const run of runs) {
    for (const result of run.results) {
      sizes.add(result.corpus_size);
    }
  }
  return [...sizes].sort((a, b) => a - b);
}
