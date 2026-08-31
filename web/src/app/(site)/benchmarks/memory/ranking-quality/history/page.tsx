import type { Metadata } from "next";

import { BenchmarkRankingQualityHistoryPanel } from "@/components/benchmarks/benchmark-ranking-quality-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Ranking-quality history",
  description: "Published ranking-quality benchmark run history.",
};

export default function BenchmarksRankingQualityHistoryPage() {
  return (
    <BenchmarkPageShell
      title="Ranking-quality history"
      subtitle="Published gold-set ranking runs (newest first)."
    >
      <BenchmarkRankingQualityHistoryPanel />
    </BenchmarkPageShell>
  );
}
