import type { Metadata } from "next";

import { BenchmarkMemoryRunDetailPanel } from "@/components/benchmarks/benchmark-memory-run-detail-panel";
import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";
import { loadPublishedHnswBenchmarkData } from "@/lib/benchmarks/hnsw-published-data";

export const dynamic = "force-static";

type PageProps = Readonly<{
  params: Promise<{ sha: string }>;
}>;

export async function generateStaticParams() {
  const loaded = loadPublishedHnswBenchmarkData();
  if (!loaded.ok) return [];
  return loaded.data.runs.map((run) => ({ sha: run.short_sha }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { sha } = await params;
  return {
    title: `Memory HNSW run ${sha}`,
    description: `HNSW benchmark detail for ${sha}.`,
  };
}

export default async function BenchmarksMemoryRunDetailPage({ params }: PageProps) {
  const { sha } = await params;
  return (
    <BenchmarkPageShell
      title={`Memory run ${sha}`}
      subtitle="Per-size cells and methodology for one published HNSW run."
    >
      <BenchmarkMemoryRunDetailPanel sha={sha} />
    </BenchmarkPageShell>
  );
}
