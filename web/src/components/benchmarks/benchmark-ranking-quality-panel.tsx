"use client";

import { KpiCard } from "@/components/benchmarks/kpi-card";
import {
  BenchmarkHistoryTable,
  BenchmarkSuitePanelShell,
} from "@/components/benchmarks/benchmark-suite-panel-shell";
import { useRankingQualityBenchmarkData } from "@/hooks/use-ranking-quality-benchmark-data";
import type { RankingQualityBenchmarkRun } from "@/lib/benchmarks/ranking-quality-schema";

const LOAD_ERROR = "Failed to load ranking-quality benchmark data";

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function OverviewKpis({ latest }: { readonly latest: RankingQualityBenchmarkRun }) {
  const m = latest.metrics;
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard label="Precision@5" value={formatPct(m.precision_at_5)} />
      <KpiCard label="Recall@10" value={formatPct(m.recall_at_10)} />
      <KpiCard label="MRR" value={formatPct(m.mrr)} />
      <KpiCard
        label="Queries"
        value={latest.query_count != null ? String(latest.query_count) : "—"}
      />
    </div>
  );
}

export function BenchmarkRankingQualityPanel() {
  const { latest, isLoading, isError, errorMessage, refresh } = useRankingQualityBenchmarkData();

  return (
    <BenchmarkSuitePanelShell
      isLoading={isLoading}
      isError={isError}
      errorMessage={errorMessage}
      loadErrorLabel={LOAD_ERROR}
      isEmpty={!latest}
      onRetry={() => {
        void refresh();
      }}
    >
      {latest ? (
        <div className="space-y-8">
          <p className="font-mono text-sm uppercase text-muted-foreground">
            Status: {latest.status ?? "unknown"} · run #{latest.run_number} · {latest.short_sha}
          </p>
          <OverviewKpis latest={latest} />
          <p className="text-sm text-muted-foreground">
            Gold set {latest.gold_set ?? "v1"}
            {latest.memory_count != null ? ` · ${latest.memory_count} memories` : ""}
            {latest.run_url ? (
              <>
                {" "}
                ·{" "}
                <a className="underline underline-offset-2" href={latest.run_url}>
                  workflow run
                </a>
              </>
            ) : null}
          </p>
        </div>
      ) : null}
    </BenchmarkSuitePanelShell>
  );
}

export function BenchmarkRankingQualityHistoryPanel() {
  const { runs, isLoading, isError, errorMessage, refresh } = useRankingQualityBenchmarkData();

  return (
    <BenchmarkSuitePanelShell
      isLoading={isLoading}
      isError={isError}
      errorMessage={errorMessage}
      loadErrorLabel={LOAD_ERROR}
      isEmpty={runs.length === 0}
      skeletonClassName="h-[200px]"
      onRetry={() => {
        void refresh();
      }}
    >
      <BenchmarkHistoryTable
        rows={runs}
        rowKey={(run) => run.run_number}
        columns={[
          { header: "Run #", cell: (run) => run.run_number },
          {
            header: "SHA",
            cell: (run) => run.short_sha,
            className: "py-2 font-mono text-sm",
          },
          {
            header: "Status",
            cell: (run) => (run.status ?? "unknown").toUpperCase(),
            className: "py-2 font-mono text-sm uppercase",
          },
          {
            header: "Precision@5",
            cell: (run) => formatPct(run.metrics.precision_at_5),
          },
          {
            header: "Recall@10",
            cell: (run) => formatPct(run.metrics.recall_at_10),
          },
          { header: "MRR", cell: (run) => formatPct(run.metrics.mrr) },
          {
            header: "When",
            cell: (run) => run.timestamp,
            className: "py-2 font-mono text-xs text-muted-foreground",
          },
        ]}
      />
    </BenchmarkSuitePanelShell>
  );
}
