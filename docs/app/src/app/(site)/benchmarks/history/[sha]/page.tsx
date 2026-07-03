import fs from "node:fs";
import path from "node:path";

import type { Metadata } from "next";

import { BenchmarkPageShell } from "@/components/benchmarks/benchmark-page-shell";
import { BenchmarkRunDetailPanel } from "@/components/benchmarks/lazy-panels";

type RunDetailPageProps = Readonly<{
  params: Promise<{ sha: string }>;
}>;

export async function generateStaticParams() {
  const dataPath = path.join(process.cwd(), "public/benchmarks/benchmark-data.json");
  if (!fs.existsSync(dataPath)) {
    return [];
  }

  const raw = fs.readFileSync(dataPath, "utf8");
  const data = JSON.parse(raw) as { runs?: { short_sha: string }[] };
  const runs = data.runs ?? [];

  return runs.map((run) => ({ sha: run.short_sha }));
}

export async function generateMetadata(props: RunDetailPageProps): Promise<Metadata> {
  const { sha } = await props.params;
  return {
    title: `Benchmarks — Run ${sha}`,
    description: `Benchmark run detail for commit ${sha}.`,
  };
}

export default async function BenchmarkRunDetailPage(props: RunDetailPageProps) {
  const { sha } = await props.params;
  return (
    <BenchmarkPageShell
      title={`Run ${sha}`}
      subtitle="Full benchmark output for this commit."
    >
      <BenchmarkRunDetailPanel sha={sha} />
    </BenchmarkPageShell>
  );
}
