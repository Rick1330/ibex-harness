import type { Metadata } from "next";

import { BenchmarkOverviewPanel } from "@/components/benchmarks/lazy-panels";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Benchmarks",
  description: "IBEX Harness proxy overhead, k6 load test results, and regression status.",
};

export default function BenchmarksOverviewPage() {
  return (
    <BenchmarkPageShell
      title="Benchmarks"
      subtitle="Performance metrics for the IBEX Harness proxy critical path. Updated when benchmark PRs merge."
    >
      <BenchmarkOverviewPanel />
    </BenchmarkPageShell>
  );
}
