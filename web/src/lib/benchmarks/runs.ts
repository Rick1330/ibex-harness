import type { BenchmarkRun } from "@/lib/benchmarks/types";

export function findRunBySha(runs: BenchmarkRun[], sha: string): BenchmarkRun | null {
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
