import type { Metadata } from "next";

import { BenchmarkMemoryPanel } from "@/components/benchmarks/benchmark-memory-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Memory HNSW benchmarks",
  description:
    "pgvector HNSW recall@10 and search latency at 10K / 100K / 1M for the IBEX memory substrate.",
};

export default function BenchmarksMemoryPage() {
  return (
    <BenchmarkPageShell
      title="Memory HNSW"
      subtitle="Recall@10 and search latency for PgVectorStore against live pgvector HNSW (ef_search=40). Separate from proxy overhead charts — same publish surface."
    >
      <BenchmarkMemoryPanel />
    </BenchmarkPageShell>
  );
}
