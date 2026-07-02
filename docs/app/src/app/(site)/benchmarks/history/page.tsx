import type { Metadata } from "next";

import { BenchmarkHistoryPanel } from "@/components/benchmarks/benchmark-history-panel";

export const metadata: Metadata = {
  title: "Benchmarks — History",
  description: "Historical benchmark runs and regression status.",
};

export default function BenchmarksHistoryPage() {
  return <BenchmarkHistoryPanel />;
}
