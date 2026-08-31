import type { ReactNode } from "react";

import { BenchmarkWorkflowRunLink } from "@/components/benchmarks/benchmark-workflow-run-link";
import { isSafeBenchmarkRunUrl } from "@/lib/benchmarks/run-url";

type BenchmarkSuiteMetaLineProps = Readonly<{
  runUrl?: string;
  children: ReactNode;
}>;

export function BenchmarkSuiteMetaLine({ runUrl, children }: BenchmarkSuiteMetaLineProps) {
  return (
    <p className="text-sm text-muted-foreground">
      {children}
      {runUrl && isSafeBenchmarkRunUrl(runUrl) ? (
        <>
          {" · "}
          <BenchmarkWorkflowRunLink runUrl={runUrl} />
        </>
      ) : null}
    </p>
  );
}
