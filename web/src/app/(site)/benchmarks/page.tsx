import type { Metadata } from "next";

import { BenchmarkOverviewPanel } from "@/components/benchmarks/lazy-panels";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Benchmarks",
  description:
    "IBEX Harness proxy overhead, k6 load tests, memory HNSW search, and CI regression gates for ranking quality and write latency.",
};

export default function BenchmarksOverviewPage() {
  return (
    <BenchmarkPageShell
      title="Benchmarks"
      subtitle="Performance metrics for the IBEX Harness proxy critical path and memory HNSW search. Ranking-quality and write-pipeline gates run in CI; published charts update when benchmark data PRs merge."
    >
      <BenchmarkOverviewPanel />
    </BenchmarkPageShell>
  );
}
