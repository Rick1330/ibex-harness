"use client";

import { useBenchmarkData } from "@/hooks/use-benchmark-data";

const WORKFLOW_URL =
  "https://github.com/Rick1330/ibex-harness/actions/workflows/benchmark.yml";

type BenchmarkErrorStateProps = Readonly<{
  message: string;
}>;

export function BenchmarkErrorState({ message }: BenchmarkErrorStateProps) {
  const { refresh } = useBenchmarkData();

  const handleRetry = () => {
    refresh();
  };

  return (
    <div className="rounded-md border border-danger/30 bg-danger/5 p-4">
      <p className="text-sm text-danger">{message}</p>
      <div className="mt-3 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={handleRetry}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm hover:bg-muted"
        >
          Retry
        </button>
        <a
          href={WORKFLOW_URL}
          target="_blank"
          rel="noreferrer"
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm hover:bg-muted"
        >
          View workflow
        </a>
      </div>
    </div>
  );
}
