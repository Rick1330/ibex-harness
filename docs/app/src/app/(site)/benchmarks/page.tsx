import type { Metadata } from "next";

import { BenchmarkOverviewPanel } from "@/components/benchmarks/benchmark-overview-panel";

export const metadata: Metadata = {
  title: "Benchmarks",
  description: "IBEX Harness proxy overhead, k6 load test results, and regression status.",
};

export default function BenchmarksOverviewPage() {
  return <BenchmarkOverviewPanel />;
}
