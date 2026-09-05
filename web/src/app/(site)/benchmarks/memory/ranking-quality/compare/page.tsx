import type { Metadata } from "next";

import { BenchmarkRankingQualityComparePanel } from "@/components/benchmarks/benchmark-ranking-quality-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Ranking quality compare",
  description: "Side-by-side ranking-quality metric comparison between published runs.",
};

export default function RankingQualityComparePage() {
  return (
    <BenchmarkPageShell
      title="Ranking quality · Compare"
      subtitle="Diff precision@5, recall@10, and MRR between two published gold-set runs."
    >
      <BenchmarkRankingQualityComparePanel />
    </BenchmarkPageShell>
  );
}
