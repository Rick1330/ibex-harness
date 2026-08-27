"use client";

import Link from "next/link";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { KpiCard } from "@/components/benchmarks/kpi-card";
import { SlaGauge } from "@/components/benchmarks/sla-gauge";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { HNSW_SLA_TARGETS } from "@/lib/benchmarks/constants";
import {
  corpusSizeLabel,
  formatRecallPct,
  largestCorpusResult,
} from "@/lib/benchmarks/hnsw-runs";
import type { HnswBenchmarkRun, HnswSizeResult } from "@/lib/benchmarks/hnsw-schema";
import { useHnswBenchmarkData } from "@/hooks/use-hnsw-benchmark-data";

function ResultRow({ result }: { readonly result: HnswSizeResult }) {
  return (
    <tr className="border-b border-border/60">
      <td className="py-2 font-mono text-sm">{corpusSizeLabel(result.corpus_size)}</td>
      <td className="py-2 font-mono text-sm tabular-nums">{result.query_count}</td>
      <td className="py-2 font-mono text-sm tabular-nums">
        {formatRecallPct(result.recall_at_10)}
      </td>
      <td className="py-2 font-mono text-sm tabular-nums">{result.latency_ms_p50.toFixed(2)}</td>
      <td className="py-2 font-mono text-sm tabular-nums">{result.latency_ms_p95.toFixed(2)}</td>
      <td className="py-2 font-mono text-sm tabular-nums">{result.latency_ms_p99.toFixed(2)}</td>
      <td className="py-2 font-mono text-sm tabular-nums">{result.ef_search}</td>
    </tr>
  );
}

function SlaSection({
  worstRecall,
  at1m,
}: {
  readonly worstRecall: number;
  readonly at1m: HnswSizeResult | undefined;
}) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold tracking-tight">Track B / Track E SLAs</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <SlaGauge
          label="Worst recall@10 (target ≥ 98%)"
          value={1 - worstRecall}
          target={1 - HNSW_SLA_TARGETS.recall_at_10}
          formatValue={(value) => formatRecallPct(1 - value)}
        />
        {at1m ? (
          <>
            <SlaGauge
              label="1M search p95"
              value={at1m.latency_ms_p95}
              target={HNSW_SLA_TARGETS.p95_ms_1m}
            />
            <SlaGauge
              label="1M search p99"
              value={at1m.latency_ms_p99}
              target={HNSW_SLA_TARGETS.p99_ms_1m}
            />
          </>
        ) : null}
      </div>
    </section>
  );
}

function ResultsTable({ latest }: { readonly latest: HnswBenchmarkRun }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold tracking-tight">Per-size results</h2>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[40rem] text-left">
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
              <th className="py-2 font-medium">Corpus</th>
              <th className="py-2 font-medium">Queries</th>
              <th className="py-2 font-medium">Recall@10</th>
              <th className="py-2 font-medium">p50 ms</th>
              <th className="py-2 font-medium">p95 ms</th>
              <th className="py-2 font-medium">p99 ms</th>
              <th className="py-2 font-medium">ef</th>
            </tr>
          </thead>
          <tbody>
            {latest.results.map((result) => (
              <ResultRow
                key={`${result.corpus_size}-${result.ef_search}-${result.min_similarity ?? 0}`}
                result={result}
              />
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-sm text-muted-foreground">
        {String(latest.methodology.recall ?? "Planted near-neighbor recall@10")} ·{" "}
        {String(latest.methodology.index ?? "pgvector HNSW")}
        {latest.run_url ? (
          <>
            {" "}
            ·{" "}
            <a className="underline underline-offset-2" href={latest.run_url}>
              run details
            </a>
          </>
        ) : null}
      </p>
    </section>
  );
}

export function BenchmarkMemoryPanel() {
  const { latest, runs, isLoading, isError, errorMessage, refresh } = useHnswBenchmarkData();

  if (isLoading) {
    return <ChartSkeleton className="h-[240px]" />;
  }

  if (isError) {
    return (
      <BenchmarkErrorState
        message={errorMessage ?? "Failed to load HNSW data"}
        onRetry={() => {
          void refresh();
        }}
      />
    );
  }

  if (!latest) {
    return <BenchmarkEmptyState />;
  }

  const at1m = latest.results.find((r) => r.corpus_size >= 1_000_000);
  const worstRecall = Math.min(...latest.results.map((r) => r.recall_at_10));
  const status = latest.status ?? "unknown";

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="rounded-md border border-border px-2 py-1 font-mono uppercase">
          {status}
        </span>
        <Link
          href="/benchmarks/memory/history"
          className="text-muted-foreground underline-offset-2 hover:underline"
        >
          History
        </Link>
        <Link
          href="/benchmarks/memory/compare"
          className="text-muted-foreground underline-offset-2 hover:underline"
        >
          Compare
        </Link>
        <Link
          href="/benchmarks/memory/latency"
          className="text-muted-foreground underline-offset-2 hover:underline"
        >
          Latency trends
        </Link>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Latest short SHA" value={latest.short_sha} hint={latest.branch} />
        <KpiCard
          label="Mean recall@10"
          value={formatRecallPct(latest.mean_recall_at_10)}
          hint={`${latest.results.length} corpus sizes`}
          higherIsBetter
        />
        <KpiCard
          label="Sizes measured"
          value={latest.results.map((r) => corpusSizeLabel(r.corpus_size)).join(" · ")}
        />
        <KpiCard label="Run #" value={String(latest.run_number)} hint={latest.timestamp} />
      </div>

      <SlaSection worstRecall={worstRecall} at1m={at1m} />
      <ResultsTable latest={latest} />

      {runs.length > 1 ? (
        <p className="text-sm text-muted-foreground">
          {runs.length} published runs — see{" "}
          <Link href="/benchmarks/memory/history" className="underline underline-offset-2">
            History
          </Link>{" "}
          for the full table.
        </p>
      ) : null}
    </div>
  );
}

export function MemorySuiteSummaryCard() {
  const { latest, isLoading, isError } = useHnswBenchmarkData();

  if (isLoading) {
    return <ChartSkeleton className="h-[120px]" />;
  }

  if (isError || !latest) {
    return (
      <div className="rounded-md border border-border p-4 text-sm text-muted-foreground">
        <p className="font-medium text-foreground">Memory HNSW</p>
        <p className="mt-1">No published HNSW runs yet.</p>
        <Link href="/benchmarks/memory" className="mt-2 inline-block underline underline-offset-2">
          Open Memory suite
        </Link>
      </div>
    );
  }

  const largest = largestCorpusResult(latest);

  return (
    <div className="rounded-md border border-border p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Memory HNSW
        </h2>
        <Link
          href="/benchmarks/memory"
          className="text-sm text-muted-foreground underline-offset-2 hover:underline"
        >
          Open suite
        </Link>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <KpiCard
          label="Mean recall@10"
          value={formatRecallPct(latest.mean_recall_at_10)}
          higherIsBetter
        />
        <KpiCard
          label={largest ? `${corpusSizeLabel(largest.corpus_size)} p95` : "Largest p95"}
          value={largest ? `${largest.latency_ms_p95.toFixed(1)} ms` : "—"}
        />
        <KpiCard label="Latest" value={latest.short_sha} hint={latest.branch} />
      </div>
    </div>
  );
}
