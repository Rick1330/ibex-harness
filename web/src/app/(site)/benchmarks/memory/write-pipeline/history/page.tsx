import type { Metadata } from "next";

import { BenchmarkWritePipelineHistoryPanel } from "@/components/benchmarks/benchmark-write-pipeline-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Write-pipeline history",
  description: "Published write-pipeline benchmark run history.",
};

export default function BenchmarksWritePipelineHistoryPage() {
  return (
    <BenchmarkPageShell
      title="Write-pipeline history"
      subtitle="Published write-path latency runs (newest first)."
    >
      <BenchmarkWritePipelineHistoryPanel />
    </BenchmarkPageShell>
  );
}
