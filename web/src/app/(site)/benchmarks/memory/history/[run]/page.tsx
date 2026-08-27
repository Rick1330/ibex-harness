import type { Metadata } from "next";

import { BenchmarkMemoryRunDetailPanel } from "@/components/benchmarks/benchmark-memory-run-detail-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";
import { loadPublishedHnswBenchmarkData } from "@/lib/benchmarks/hnsw-published-data";

export const dynamic = "force-static";

type PageProps = Readonly<{
  params: Promise<{ run: string }>;
}>;

export async function generateStaticParams() {
  const loaded = loadPublishedHnswBenchmarkData();
  if (!loaded.ok) return [];
  return loaded.data.runs.map((item) => ({ run: String(item.run_number) }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { run } = await params;
  return {
    title: `Memory HNSW run ${run}`,
    description: `HNSW benchmark detail for run ${run}.`,
  };
}

export default async function BenchmarksMemoryRunDetailPage({ params }: PageProps) {
  const { run } = await params;
  return (
    <BenchmarkPageShell
      title={`Memory run ${run}`}
      subtitle="Per-size cells and methodology for one published HNSW run."
    >
      <BenchmarkMemoryRunDetailPanel runNumber={run} />
    </BenchmarkPageShell>
  );
}
