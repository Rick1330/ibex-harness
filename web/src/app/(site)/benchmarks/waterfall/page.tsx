import type { Metadata } from "next";

import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";
import { BenchmarkWaterfallPanel } from "@/components/benchmarks/lazy-panels";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Benchmarks — Waterfall",
  description: "Per-stage proxy overhead breakdown.",
};

export default function BenchmarksWaterfallPage() {
  return (
    <BenchmarkPageShell
      title="Stage breakdown"
      subtitle="Per-stage latency contribution to total proxy overhead."
    >
      <BenchmarkWaterfallPanel />
    </BenchmarkPageShell>
  );
}
