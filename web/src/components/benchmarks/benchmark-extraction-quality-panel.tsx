"use client";

import { KpiCard } from "@/components/benchmarks/kpi-card";
import { BenchmarkSuiteMetaLine } from "@/components/benchmarks/benchmark-suite-meta-line";
import {
  BenchmarkHistoryTable,
  BenchmarkSuitePanelShell,
} from "@/components/benchmarks/benchmark-suite-panel-shell";
import { useExtractionQualityBenchmarkData } from "@/hooks/use-memory-suite-benchmark-data";
import type { ExtractionQualityBenchmarkRun } from "@/lib/benchmarks/extraction-quality-schema";

const LOAD_ERROR = "Failed to load extraction-quality benchmark data";

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function OverviewKpis({ latest }: { readonly latest: ExtractionQualityBenchmarkRun }) {
  const m = latest.metrics;
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard label="Precision macro" value={formatPct(m.precision_macro)} />
      <KpiCard label="Recall macro" value={formatPct(m.recall_macro)} />
      <KpiCard
        label="Category assignment"
        value={formatPct(m.category_assignment_accuracy)}
      />
      <KpiCard label="Temporal fields" value={formatPct(m.temporal_field_accuracy)} />
    </div>
  );
}

export function BenchmarkExtractionQualityPanel() {
  const { latest, isLoading, isError, errorMessage, refresh } =
    useExtractionQualityBenchmarkData();

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
            Status: {latest.status ?? "unknown"} · enforcement:{" "}
            {latest.enforcement ?? "ci"} · run #{latest.run_number} · {latest.short_sha}
          </p>
          <OverviewKpis latest={latest} />
          <BenchmarkSuiteMetaLine runUrl={latest.run_url}>
            Gold set {latest.gold_set ?? "v1"}
            {latest.conversation_count != null
              ? ` · ${latest.conversation_count} conversations`
              : ""}
            {latest.provider ? ` · provider ${latest.provider}` : ""}
          </BenchmarkSuiteMetaLine>
        </div>
      ) : null}
    </BenchmarkSuitePanelShell>
  );
}

export function BenchmarkExtractionQualityHistoryPanel() {
  const { runs, isLoading, isError, errorMessage, refresh } =
    useExtractionQualityBenchmarkData();

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
            header: "Precision macro",
            cell: (run) => formatPct(run.metrics.precision_macro),
          },
          {
            header: "Recall macro",
            cell: (run) => formatPct(run.metrics.recall_macro),
          },
          {
            header: "Category",
            cell: (run) => formatPct(run.metrics.category_assignment_accuracy),
          },
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
