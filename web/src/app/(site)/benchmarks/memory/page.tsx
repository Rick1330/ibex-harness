import type { Metadata } from "next";

import { BenchmarkMemoryPanel } from "@/components/benchmarks/benchmark-memory-panel";
import { MemoryCiGatesCallout } from "@/components/benchmarks/memory-ci-gates-callout";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Memory HNSW benchmarks",
  description:
    "pgvector HNSW recall@10 and search latency at 10K / 100K (1M on CI schedule only) for the IBEX memory substrate.",
};

export default function BenchmarksMemoryPage() {
  return (
    <BenchmarkPageShell
      title="Memory HNSW"
      subtitle="Recall@10 and search latency for PgVectorStore against live pgvector HNSW (ef_search=40). Latency, history, and compare live under this suite."
    >
      <BenchmarkMemoryPanel />
      <div className="mt-8">
        <MemoryCiGatesCallout />
      </div>
    </BenchmarkPageShell>
  );
}
