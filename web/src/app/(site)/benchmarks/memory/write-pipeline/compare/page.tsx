import type { Metadata } from "next";

import { BenchmarkWritePipelineComparePanel } from "@/components/benchmarks/benchmark-write-pipeline-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Write pipeline compare",
  description: "Side-by-side write-pipeline latency comparison between published runs.",
};

export default function WritePipelineComparePage() {
  return (
    <BenchmarkPageShell
      title="Write pipeline · Compare"
      subtitle="Diff create-path p50/p95/p99 between two published runs."
    >
      <BenchmarkWritePipelineComparePanel />
    </BenchmarkPageShell>
  );
}
