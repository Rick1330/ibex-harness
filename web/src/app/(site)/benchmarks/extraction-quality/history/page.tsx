import type { Metadata } from "next";

import { BenchmarkExtractionQualityHistoryPanel } from "@/components/benchmarks/benchmark-extraction-quality-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Extraction-quality history",
  description: "Published extraction-quality benchmark run history.",
};

export default function BenchmarksExtractionQualityHistoryPage() {
  return (
    <BenchmarkPageShell
      title="Extraction-quality history"
      subtitle="Published gold-set extraction runs (newest first)."
    >
      <BenchmarkExtractionQualityHistoryPanel />
    </BenchmarkPageShell>
  );
}
