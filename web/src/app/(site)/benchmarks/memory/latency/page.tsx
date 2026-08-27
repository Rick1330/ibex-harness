import type { Metadata } from "next";

import { BenchmarkMemoryLatencyPanel } from "@/components/benchmarks/benchmark-memory-latency-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Memory HNSW latency",
  description: "HNSW recall and search latency trends by corpus size.",
};

export default function BenchmarksMemoryLatencyPage() {
  return (
    <BenchmarkPageShell
      title="Memory latency"
      subtitle="Recall@10 and search p95/p99 trends by corpus size from published HNSW runs."
    >
      <BenchmarkMemoryLatencyPanel />
    </BenchmarkPageShell>
  );
}
