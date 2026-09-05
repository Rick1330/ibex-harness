"use client";

import { Suspense, type ReactNode } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { BenchmarkSuitePanelShell } from "@/components/benchmarks/benchmark-suite-panel-shell";
import { CompareMetricsTable } from "@/components/benchmarks/compare-metrics-table";
import { CompareRunSelectors } from "@/components/benchmarks/compare-run-selectors";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import type { CompareMetricRow } from "@/components/benchmarks/compare-metrics-table";
import type { BenchmarkRunIdentity } from "@/lib/benchmarks/run-identity";

export type SuiteCompareRun = BenchmarkRunIdentity;

export function resolveComparePair<T extends SuiteCompareRun>(
  runs: readonly T[],
  baseSha: string,
  headSha: string,
): { base: T; head: T } | null {
  const base = baseSha
    ? runs.find((run) => run.short_sha === baseSha || run.sha === baseSha)
    : (runs[1] ?? runs[0]);
  const head = headSha
    ? runs.find((run) => run.short_sha === headSha || run.sha === headSha)
    : runs[0];
  if (!base || !head) {
    return null;
  }
  return { base, head };
}

type SuiteComparePanelProps<T extends SuiteCompareRun> = Readonly<{
  runs: readonly T[];
  isLoading: boolean;
  isError: boolean;
  errorMessage?: string | null;
  loadErrorLabel: string;
  comparePath: string;
  buildRows: (base: T, head: T) => readonly CompareMetricRow[];
  emptyTitle?: string;
  emptyMessage?: string;
  onRetry: () => void;
}>;

function SuiteCompareContent<T extends SuiteCompareRun>({
  runs,
  isLoading,
  isError,
  errorMessage,
  loadErrorLabel,
  comparePath,
  buildRows,
  emptyTitle,
  emptyMessage,
  onRetry,
}: SuiteComparePanelProps<T>) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const baseSha = searchParams.get("base") ?? "";
  const headSha = searchParams.get("head") ?? "";
  const pair = resolveComparePair(runs, baseSha, headSha);

  let body: ReactNode;
  if (runs.length < 2) {
    body = (
      <p className="text-sm text-muted-foreground">
        Need at least two published runs to compare.
      </p>
    );
  } else if (!pair) {
    body = <p className="text-sm text-muted-foreground">Select two runs to compare.</p>;
  } else {
    const replaceParam = (key: "base" | "head", value: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set(key, value);
      router.replace(`${comparePath}?${params.toString()}`);
    };
    body = (
      <div className="space-y-6">
        <CompareRunSelectors
          runs={runs}
          baseSha={pair.base.short_sha}
          headSha={pair.head.short_sha}
          onBaseChange={(value) => {
            replaceParam("base", value);
          }}
          onHeadChange={(value) => {
            replaceParam("head", value);
          }}
        />
        <CompareMetricsTable
          baseSha={pair.base.short_sha}
          headSha={pair.head.short_sha}
          rows={[...buildRows(pair.base, pair.head)]}
        />
      </div>
    );
  }

  return (
    <BenchmarkSuitePanelShell
      isLoading={isLoading}
      isError={isError}
      errorMessage={errorMessage ?? null}
      loadErrorLabel={loadErrorLabel}
      isEmpty={runs.length === 0}
      emptyTitle={emptyTitle}
      emptyMessage={emptyMessage}
      onRetry={onRetry}
    >
      {body}
    </BenchmarkSuitePanelShell>
  );
}

export function SuiteComparePanel<T extends SuiteCompareRun>(
  props: SuiteComparePanelProps<T>,
) {
  return (
    <Suspense fallback={<ChartSkeleton className="h-[200px]" />}>
      <SuiteCompareContent {...props} />
    </Suspense>
  );
}
