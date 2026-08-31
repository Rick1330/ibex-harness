"use client";

import { KpiCard } from "@/components/benchmarks/kpi-card";
import { BenchmarkWorkflowRunLink } from "@/components/benchmarks/benchmark-workflow-run-link";
import {
  BenchmarkHistoryTable,
  BenchmarkSuitePanelShell,
} from "@/components/benchmarks/benchmark-suite-panel-shell";
import { useWritePipelineBenchmarkData } from "@/hooks/use-memory-suite-benchmark-data";
import { WRITE_PIPELINE_SLA_TARGETS } from "@/lib/benchmarks/constants";
import { isSafeBenchmarkRunUrl } from "@/lib/benchmarks/run-url";
import type { WritePipelineBenchmarkRun } from "@/lib/benchmarks/write-pipeline-schema";

const LOAD_ERROR = "Failed to load write-pipeline benchmark data";

function OverviewKpis({ latest }: { readonly latest: WritePipelineBenchmarkRun }) {
  const m = latest.metrics;
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <KpiCard label="p50" value={`${m.latency_ms_p50.toFixed(2)} ms`} />
      <KpiCard label="p95 (SLA ≤ 200 ms)" value={`${m.latency_ms_p95.toFixed(2)} ms`} />
      <KpiCard label="p99" value={`${m.latency_ms_p99.toFixed(2)} ms`} />
    </div>
  );
}

export function BenchmarkWritePipelinePanel() {
  const { latest, isLoading, isError, errorMessage, refresh } = useWritePipelineBenchmarkData();

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
            {latest.iterations != null ? `${latest.iterations} iterations` : "—"}
            {latest.metrics.latency_ms_p95 <= WRITE_PIPELINE_SLA_TARGETS.latency_ms_p95
              ? " · p95 within SLA"
              : " · p95 above SLA"}
            {isSafeBenchmarkRunUrl(latest.run_url) ? (
              <>
                {" · "}
                <BenchmarkWorkflowRunLink runUrl={latest.run_url} />
              </>
            ) : null}
          </p>
        </div>
      ) : null}
    </BenchmarkSuitePanelShell>
  );
}

export function BenchmarkWritePipelineHistoryPanel() {
  const { runs, isLoading, isError, errorMessage, refresh } = useWritePipelineBenchmarkData();

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
            header: "p50",
            cell: (run) => `${run.metrics.latency_ms_p50.toFixed(2)} ms`,
          },
          {
            header: "p95",
            cell: (run) => `${run.metrics.latency_ms_p95.toFixed(2)} ms`,
          },
          {
            header: "p99",
            cell: (run) => `${run.metrics.latency_ms_p99.toFixed(2)} ms`,
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
