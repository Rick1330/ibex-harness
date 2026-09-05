import type { Metadata } from "next";

import { BenchmarkExtractionQualityComparePanel } from "@/components/benchmarks/benchmark-extraction-quality-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Extraction quality compare",
  description: "Side-by-side extraction-quality metric comparison between published runs.",
};

export default function ExtractionQualityComparePage() {
  return (
    <BenchmarkPageShell
      title="Extraction quality · Compare"
      subtitle="Diff precision/recall and assignment accuracy between two published gold-set runs."
    >
      <BenchmarkExtractionQualityComparePanel />
    </BenchmarkPageShell>
  );
}
