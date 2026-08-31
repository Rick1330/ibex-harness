import type { Metadata } from "next";

import { BenchmarkWritePipelinePanel } from "@/components/benchmarks/benchmark-write-pipeline-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Write-pipeline benchmarks",
  description: "Memory create-path latency (p50/p95/p99) for the IBEX write pipeline.",
};

export default function BenchmarksWritePipelinePage() {
  return (
    <BenchmarkPageShell
      title="Write pipeline"
      subtitle="Create-path latency from the Memory Benchmarks CI suite (p95 SLA ≤ 200 ms)."
    >
      <BenchmarkWritePipelinePanel />
    </BenchmarkPageShell>
  );
}
