import type { Metadata } from "next";

import { BenchmarkLatencyPanel } from "@/components/benchmarks/lazy-panels";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";

export const metadata: Metadata = {
  title: "Benchmarks — Latency",
  description: "Proxy overhead latency trends over time.",
};

export default function BenchmarksLatencyPage() {
  return (
    <BenchmarkPageShell
      title="Latency trends"
      subtitle="Proxy overhead percentiles over time."
    >
      <BenchmarkLatencyPanel />
    </BenchmarkPageShell>
  );
}
