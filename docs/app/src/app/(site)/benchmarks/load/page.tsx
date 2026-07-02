import type { Metadata } from "next";

import { BenchmarkLoadPanel } from "@/components/benchmarks/benchmark-load-panel";

export const metadata: Metadata = {
  title: "Benchmarks — Load",
  description: "k6 load test percentiles and throughput for the IBEX proxy.",
};

export default function BenchmarksLoadPage() {
  return <BenchmarkLoadPanel />;
}
