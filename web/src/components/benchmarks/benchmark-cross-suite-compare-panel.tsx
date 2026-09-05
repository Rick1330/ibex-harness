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
import {
  buildCrossSuiteCompareRows,
  type SuiteLatestSnapshot,
} from "@/lib/benchmarks/cross-suite-compare";
import { formatMs, formatSuitePct } from "@/lib/benchmarks/format";
import { formatRecallPct } from "@/lib/benchmarks/hnsw-runs";

type SuiteHookSlice = Readonly<{
  isLoading: boolean;
  isError: boolean;
  errorMessage?: string | null;
  refresh: () => unknown;
}>;

function buildSnapshots(args: {
  proxy: ReturnType<typeof useBenchmarkData>;
  hnsw: ReturnType<typeof useHnswBenchmarkData>;
  ranking: ReturnType<typeof useRankingQualityBenchmarkData>;
  write: ReturnType<typeof useWritePipelineBenchmarkData>;
  extraction: ReturnType<typeof useExtractionQualityBenchmarkData>;
}): SuiteLatestSnapshot[] {
  const { proxy, hnsw, ranking, write, extraction } = args;
  return [
    {
      id: "proxy",
      label: "Proxy",
      shortSha: proxy.latest?.short_sha ?? null,
      status: proxy.latest?.status ?? null,
      timestamp: proxy.latest?.timestamp ?? null,
      metrics: proxy.latest
        ? [
            { label: "Proxy p99", value: formatMs(proxy.latest.k6.p99_ms) },
            {
              label: "Throughput",
              value: `${proxy.latest.k6.req_per_s.toFixed(0)} req/s`,
            },
            {
              label: "Total overhead p99",
              value: formatMs(proxy.latest.stages.total_overhead_p99_ms),
            },
          ]
        : [],
    },
    {
      id: "hnsw",
      label: "HNSW",
      shortSha: hnsw.latest?.short_sha ?? null,
      status: hnsw.latest?.status ?? null,
      timestamp: hnsw.latest?.timestamp ?? null,
      metrics: hnsw.latest
        ? [
            {
              label: "Mean recall@10",
              value: formatRecallPct(hnsw.latest.mean_recall_at_10),
            },
          ]
        : [],
    },
    {
      id: "rankingQuality",
      label: "Ranking",
      shortSha: ranking.latest?.short_sha ?? null,
      status: ranking.latest?.status ?? null,
      timestamp: ranking.latest?.timestamp ?? null,
      metrics: ranking.latest
        ? [
            {
              label: "Precision@5",
              value: formatSuitePct(ranking.latest.metrics.precision_at_5),
            },
            {
              label: "Recall@10",
              value: formatSuitePct(ranking.latest.metrics.recall_at_10),
            },
            { label: "MRR", value: formatSuitePct(ranking.latest.metrics.mrr) },
          ]
        : [],
    },
    {
      id: "writePipeline",
      label: "Write",
      shortSha: write.latest?.short_sha ?? null,
      status: write.latest?.status ?? null,
      timestamp: write.latest?.timestamp ?? null,
      metrics: write.latest
        ? [
            {
              label: "Write p95",
              value: formatMs(write.latest.metrics.latency_ms_p95),
            },
            {
              label: "Write p99",
              value: formatMs(write.latest.metrics.latency_ms_p99),
            },
          ]
        : [],
    },
    {
      id: "extractionQuality",
      label: "Extraction",
      shortSha: extraction.latest?.short_sha ?? null,
      status: extraction.latest?.status ?? null,
      timestamp: extraction.latest?.timestamp ?? null,
      metrics: extraction.latest
        ? [
            {
              label: "Precision macro",
              value: formatSuitePct(extraction.latest.metrics.precision_macro),
            },
            {
              label: "Recall macro",
              value: formatSuitePct(extraction.latest.metrics.recall_macro),
            },
          ]
        : [],
    },
  ];
}

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

function firstFailedHook(
  hooks: readonly SuiteHookSlice[],
): SuiteHookSlice | undefined {
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

  const snapshots = buildSnapshots({ proxy, hnsw, ranking, write, extraction });
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
