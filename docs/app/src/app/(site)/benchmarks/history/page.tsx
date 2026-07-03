import type { Metadata } from "next";

import { BenchmarkHistoryPanel } from "@/components/benchmarks/lazy-panels";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const metadata: Metadata = {
  title: "Benchmarks — History",
  description: "Historical benchmark runs and regression status.",
};

export default function BenchmarksHistoryPage() {
  return (
    <BenchmarkPageShell title="Run history" subtitle="All benchmark runs on main.">
      <BenchmarkHistoryPanel />
    </BenchmarkPageShell>
  );
}
