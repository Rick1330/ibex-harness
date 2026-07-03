import type { Metadata } from "next";

import { BenchmarkComparePanel } from "@/components/benchmarks/lazy-panels";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const metadata: Metadata = {
  title: "Benchmarks — Compare",
  description: "Compare two benchmark runs side by side.",
};

export default function BenchmarksComparePage() {
  return (
    <BenchmarkPageShell
      title="Compare runs"
      subtitle="Side-by-side metric comparison between two benchmark commits."
    >
      <BenchmarkComparePanel />
    </BenchmarkPageShell>
  );
}
