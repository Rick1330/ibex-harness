import type { BenchmarkRun } from "@/lib/benchmarks/types";

export function proxyOverheadBenchmark(run: BenchmarkRun) {
  return run.go_benchmarks.BenchmarkProxyOverhead ?? null;
}
