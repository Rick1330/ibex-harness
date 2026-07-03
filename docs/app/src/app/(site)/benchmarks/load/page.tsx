import type { Metadata } from "next";

import { BenchmarkLoadPanel } from "@/components/benchmarks/lazy-panels";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const metadata: Metadata = {
  title: "Benchmarks — Load test",
  description: "k6 load test results and latency distribution.",
};

export default function BenchmarksLoadPage() {
  return (
    <BenchmarkPageShell
      title="Load test results"
      subtitle="k6 load profile against the mock provider (no real OpenAI calls)."
    >
      <BenchmarkLoadPanel />
    </BenchmarkPageShell>
  );
}
