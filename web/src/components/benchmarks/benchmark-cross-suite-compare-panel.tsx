"use client";

import Link from "next/link";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";
import { useHnswBenchmarkData } from "@/hooks/use-hnsw-benchmark-data";
import {
  useExtractionQualityBenchmarkData,
  useRankingQualityBenchmarkData,
  useWritePipelineBenchmarkData,
} from "@/hooks/use-memory-suite-benchmark-data";
import { buildCrossSuiteCompareRows } from "@/lib/benchmarks/cross-suite-compare";
import {
  extractionSnapshot,
  hnswSnapshot,
  proxySnapshot,
  rankingSnapshot,
  writeSnapshot,
} from "@/lib/benchmarks/cross-suite-snapshots";
import type { SuiteLatestSnapshot } from "@/lib/benchmarks/cross-suite-compare";

type SuiteHookSlice = Readonly<{
  isLoading: boolean;
  isError: boolean;
  errorMessage?: string | null;
  refresh: () => unknown;
}>;

function CrossSuiteLinks() {
  return (
    <div className="flex flex-wrap gap-3 text-sm">
      <Link href="/benchmarks/compare" className="underline underline-offset-2">
        Proxy compare
      </Link>
      <Link href="/benchmarks/memory/compare" className="underline underline-offset-2">
        HNSW compare
      </Link>
      <Link
        href="/benchmarks/memory/ranking-quality/compare"
        className="underline underline-offset-2"
      >
        Ranking compare
      </Link>
      <Link
        href="/benchmarks/memory/write-pipeline/compare"
        className="underline underline-offset-2"
      >
        Write compare
      </Link>
      <Link
        href="/benchmarks/extraction-quality/compare"
        className="underline underline-offset-2"
      >
        Extraction compare
      </Link>
    </div>
  );
}

function CrossSuiteTable({
  snapshots,
}: Readonly<{ snapshots: readonly SuiteLatestSnapshot[] }>) {
  const rows = buildCrossSuiteCompareRows(snapshots);
  const columns = snapshots.map((snapshot) => ({
    id: snapshot.id,
    label: snapshot.label,
  }));

  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-max min-w-full text-left text-sm">
        <thead className="border-b border-border bg-muted/40">
          <tr>
            <th
              scope="col"
              className="sticky left-0 z-10 bg-muted/40 px-4 py-3 font-medium text-muted-foreground"
            >
              Metric
            </th>
            {columns.map((column) => (
              <th
                key={column.id}
                scope="col"
                className="px-4 py-3 font-medium text-muted-foreground"
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-b border-border/70 last:border-0">
              <th
                scope="row"
                className="sticky left-0 z-10 bg-background px-4 py-3 text-left font-medium"
              >
                {row.label}
              </th>
              {columns.map((column) => (
                <td
                  key={column.id}
                  className="px-4 py-3 font-mono text-xs tabular-nums text-muted-foreground sm:text-sm"
                >
                  {row.cells[column.id]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function firstFailedHook(hooks: readonly SuiteHookSlice[]): SuiteHookSlice | undefined {
  return hooks.find((hook) => hook.isError);
}

export function BenchmarkCrossSuiteComparePanel() {
  const proxy = useBenchmarkData();
  const hnsw = useHnswBenchmarkData();
  const ranking = useRankingQualityBenchmarkData();
  const write = useWritePipelineBenchmarkData();
  const extraction = useExtractionQualityBenchmarkData();
  const hooks: SuiteHookSlice[] = [proxy, hnsw, ranking, write, extraction];

  if (hooks.some((hook) => hook.isLoading)) {
    return <ChartSkeleton className="h-[240px]" />;
  }

  const failed = firstFailedHook(hooks);
  if (failed) {
    return (
      <BenchmarkErrorState
        message={failed.errorMessage ?? "Failed to load suite benchmark data"}
        onRetry={() => {
          for (const hook of hooks) {
            if (hook.isError) {
              void hook.refresh();
            }
          }
        }}
      />
    );
  }

  const snapshots = [
    proxySnapshot(proxy.latest),
    hnswSnapshot(hnsw.latest),
    rankingSnapshot(ranking.latest),
    writeSnapshot(write.latest),
    extractionSnapshot(extraction.latest),
  ];
  if (!snapshots.some((snapshot) => snapshot.shortSha != null)) {
    return (
      <BenchmarkEmptyState
        title="No suite runs to compare"
        message="Publish at least one suite’s benchmark JSON to populate this cross-suite view."
      />
    );
  }

  return (
    <div className="min-w-0 space-y-4">
      <p className="text-sm text-muted-foreground">
        Latest published run per suite. Shared identity rows first; suite-specific metrics
        show{" "}
        <span className="font-mono">—</span> where that suite has no matching field. Per-suite
        run pickers stay on each suite’s own Compare page.
      </p>
      <CrossSuiteLinks />
      <CrossSuiteTable snapshots={snapshots} />
    </div>
  );
}
