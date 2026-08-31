import Link from "next/link";

import {
  RANKING_QUALITY_SUITE,
  WRITE_PIPELINE_SUITE,
} from "@/lib/benchmarks/suites";

/** Links to memory CI suites with published history on /benchmarks. */
export function MemoryCiGatesCallout() {
  return (
    <div className="rounded-md border border-dashed border-border bg-muted/30 p-4 text-sm text-muted-foreground">
      <p className="font-medium text-foreground">Memory CI regression gates</p>
      <p className="mt-2">
        Ranking-quality and write-pipeline suites run on every Memory Benchmarks workflow.
        Published history is available under{" "}
        <Link
          href={RANKING_QUALITY_SUITE.basePath}
          className="underline underline-offset-2 hover:text-foreground"
        >
          ranking quality
        </Link>{" "}
        and{" "}
        <Link
          href={WRITE_PIPELINE_SUITE.basePath}
          className="underline underline-offset-2 hover:text-foreground"
        >
          write pipeline
        </Link>
        .
      </p>
      <p className="mt-2">
        <Link
          href="/roadmap/phase-3-memory-engine/milestones/3.e.3-retrieval-quality-benchmark"
          className="underline underline-offset-2 hover:text-foreground"
        >
          Milestone 3.E.3
        </Link>{" "}
        tracks sign-off; artifacts and bot publish follow the same suite contract as proxy and
        HNSW.
      </p>
    </div>
  );
}
