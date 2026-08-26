import type { Metadata } from "next";

import { BenchmarkMemoryHistoryPanel } from "@/components/benchmarks/benchmark-memory-history-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Memory HNSW history",
  description: "Published Memory HNSW benchmark run history.",
};

export default function BenchmarksMemoryHistoryPage() {
  return (
    <BenchmarkPageShell
      title="Memory history"
      subtitle="Published HNSW recall/latency runs (newest first)."
    >
      <BenchmarkMemoryHistoryPanel />
    </BenchmarkPageShell>
  );
}
