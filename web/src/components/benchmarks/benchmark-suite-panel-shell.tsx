"use client";

import type { ReactNode } from "react";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";

type BenchmarkSuitePanelShellProps = Readonly<{
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
  loadErrorLabel: string;
  onRetry: () => void;
  isEmpty?: boolean;
  skeletonClassName?: string;
  children: ReactNode;
}>;

export function BenchmarkSuitePanelShell({
  isLoading,
  isError,
  errorMessage,
  loadErrorLabel,
  onRetry,
  isEmpty = false,
  skeletonClassName = "h-[240px]",
  children,
}: BenchmarkSuitePanelShellProps) {
  if (isLoading) {
    return <ChartSkeleton className={skeletonClassName} />;
  }

  if (isError) {
    return (
      <BenchmarkErrorState
        message={errorMessage ?? loadErrorLabel}
        onRetry={onRetry}
      />
    );
  }

  if (isEmpty) {
    return <BenchmarkEmptyState />;
  }

  return <>{children}</>;
}

type BenchmarkHistoryColumn<T> = Readonly<{
  header: string;
  cell: (row: T) => ReactNode;
  className?: string;
}>;

type BenchmarkHistoryTableProps<T> = Readonly<{
  rows: readonly T[];
  rowKey: (row: T) => string | number;
  columns: readonly BenchmarkHistoryColumn<T>[];
}>;

export function BenchmarkHistoryTable<T>({
  rows,
  rowKey,
  columns,
}: BenchmarkHistoryTableProps<T>) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[40rem] text-left">
        <thead>
          <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
            {columns.map((column) => (
              <th key={column.header} className="py-2 font-medium">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-b border-border/60">
              {columns.map((column) => (
                <td
                  key={column.header}
                  className={column.className ?? "py-2 font-mono text-sm tabular-nums"}
                >
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
