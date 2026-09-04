import type { Metadata } from "next";

import { BenchmarkExtractionQualityPanel } from "@/components/benchmarks/benchmark-extraction-quality-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Extraction-quality benchmarks",
  description:
    "Gold-set extraction precision/recall, category-assignment accuracy, and temporal-field accuracy.",
};

export default function BenchmarksExtractionQualityPage() {
  return (
    <BenchmarkPageShell
      title="Extraction quality"
      subtitle="Gold-set extraction metrics from the Extraction Quality Eval CI suite (OpenAI CI-enforced; vLLM manual)."
    >
      <BenchmarkExtractionQualityPanel />
    </BenchmarkPageShell>
  );
}
