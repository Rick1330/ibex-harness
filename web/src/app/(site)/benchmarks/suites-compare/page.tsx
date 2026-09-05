import type { Metadata } from "next";

import { BenchmarkCrossSuiteComparePanel } from "@/components/benchmarks/benchmark-cross-suite-compare-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Cross-suite compare",
  description:
    "Side-by-side latest runs across Proxy, HNSW, ranking, write-pipeline, and extraction suites.",
};

export default function BenchmarksSuitesComparePage() {
  return (
    <BenchmarkPageShell
      title="Cross-suite compare"
      subtitle="Latest published run from each suite. Metrics appear only where that suite publishes them — empty cells are honest gaps, not missing UI."
    >
      <BenchmarkCrossSuiteComparePanel />
    </BenchmarkPageShell>
  );
}
