import type { Metadata } from "next";

import { BenchmarkMemoryComparePanel } from "@/components/benchmarks/benchmark-memory-compare-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Memory HNSW compare",
  description: "Compare two published Memory HNSW benchmark runs.",
};

export default function BenchmarksMemoryComparePage() {
  return (
    <BenchmarkPageShell
      title="Memory compare"
      subtitle="Diff mean recall and per-size latency between two published HNSW runs."
    >
      <BenchmarkMemoryComparePanel />
    </BenchmarkPageShell>
  );
}
