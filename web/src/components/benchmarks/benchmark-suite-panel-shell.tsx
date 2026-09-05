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
  emptyTitle?: string;
  emptyMessage?: string;
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
  emptyTitle,
  emptyMessage,
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
    return <BenchmarkEmptyState title={emptyTitle} message={emptyMessage} />;
  }

  return <>{children}</>;
}
