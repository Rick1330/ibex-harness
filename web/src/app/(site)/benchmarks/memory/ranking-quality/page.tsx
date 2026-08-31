import type { Metadata } from "next";

import { BenchmarkRankingQualityPanel } from "@/components/benchmarks/benchmark-ranking-quality-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Ranking-quality benchmarks",
  description:
    "Gold-set retrieval ranking metrics (precision@5, recall@10, MRR) for the IBEX memory engine.",
};

export default function BenchmarksRankingQualityPage() {
  return (
    <BenchmarkPageShell
      title="Ranking quality"
      subtitle="Gold-set precision, recall, and MRR from the Memory Benchmarks CI suite."
    >
      <BenchmarkRankingQualityPanel />
    </BenchmarkPageShell>
  );
}
