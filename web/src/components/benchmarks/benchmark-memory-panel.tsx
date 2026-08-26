"use client";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { KpiCard } from "@/components/benchmarks/kpi-card";
import { SlaGauge } from "@/components/benchmarks/sla-gauge";
import { loadPublishedHnswBenchmarkData } from "@/lib/benchmarks/hnsw-published-data";
import type { HnswSizeResult } from "@/lib/benchmarks/hnsw-schema";

const RECALL_SLA = 0.98;
const P99_SLA_MS_1M = 100;
const P95_SLA_MS_1M = 30;

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function sizeLabel(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(0)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

function ResultRow({ result }: { readonly result: HnswSizeResult }) {
  return (
    <tr className="border-b border-border/60">
      <td className="py-2 font-mono text-sm">{sizeLabel(result.corpus_size)}</td>
      <td className="py-2 font-mono text-sm tabular-nums">{result.query_count}</td>
      <td className="py-2 font-mono text-sm tabular-nums">{formatPct(result.recall_at_10)}</td>
      <td className="py-2 font-mono text-sm tabular-nums">{result.latency_ms_p50.toFixed(2)}</td>
      <td className="py-2 font-mono text-sm tabular-nums">{result.latency_ms_p95.toFixed(2)}</td>
      <td className="py-2 font-mono text-sm tabular-nums">{result.latency_ms_p99.toFixed(2)}</td>
      <td className="py-2 font-mono text-sm tabular-nums">{result.ef_search}</td>
    </tr>
  );
}

export function BenchmarkMemoryPanel() {
  const data = loadPublishedHnswBenchmarkData();
  const latest = data.runs[0];

  if (!latest) {
    return <BenchmarkEmptyState />;
  }

  const at1m = latest.results.find((r) => r.corpus_size >= 1_000_000);
  const worstRecall = Math.min(...latest.results.map((r) => r.recall_at_10));

  return (
    <div className="space-y-8">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Latest short SHA" value={latest.short_sha} hint={latest.branch} />
        <KpiCard
          label="Mean recall@10"
          value={formatPct(latest.mean_recall_at_10)}
          hint={`${latest.results.length} corpus sizes`}
          higherIsBetter
        />
        <KpiCard
          label="Sizes measured"
          value={latest.results.map((r) => sizeLabel(r.corpus_size)).join(" · ")}
        />
        <KpiCard label="Run #" value={String(latest.run_number)} hint={latest.timestamp} />
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">Track B / Track E SLAs</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <SlaGauge
            label="Worst recall@10 (target ≥ 98%)"
            value={1 - worstRecall}
            target={1 - RECALL_SLA}
            formatValue={() => formatPct(worstRecall)}
          />
          {at1m ? (
            <>
              <SlaGauge label="1M search p95" value={at1m.latency_ms_p95} target={P95_SLA_MS_1M} />
              <SlaGauge label="1M search p99" value={at1m.latency_ms_p99} target={P99_SLA_MS_1M} />
            </>
          ) : null}
        </div>
      </section>

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
                <ResultRow key={result.corpus_size} result={result} />
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

      {data.runs.length > 1 ? (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold tracking-tight">History</h2>
          <ul className="space-y-2 text-sm">
            {data.runs.map((run) => (
              <li key={run.sha} className="flex flex-wrap gap-x-3 gap-y-1 font-mono">
                <span>{run.short_sha}</span>
                <span className="text-muted-foreground">{run.timestamp}</span>
                <span>mean recall {formatPct(run.mean_recall_at_10)}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
