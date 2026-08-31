import Link from "next/link";

/** Static note: ranking-quality and write-pipeline gates run in CI only (m3.E.3). */
export function MemoryCiGatesCallout() {
  return (
    <div className="rounded-md border border-dashed border-border bg-muted/30 p-4 text-sm text-muted-foreground">
      <p className="font-medium text-foreground">Memory CI regression gates</p>
      <p className="mt-2">
        Ranking-quality (gold-set precision/recall/MRR) and write-pipeline (p95 create latency)
        benchmarks run on every Memory Benchmarks workflow but are not published here yet.
        Results appear in the GitHub Actions job summary and workflow artifacts.
      </p>
      <p className="mt-2">
        <Link
          href="/roadmap/phase-3-memory-engine/milestones/3.e.3-retrieval-quality-benchmark"
          className="underline underline-offset-2 hover:text-foreground"
        >
          Milestone 3.E.3
        </Link>{" "}
        tracks sign-off; published history and benchmark-bot integration follow the same
        suite contract as proxy and HNSW when needed.
      </p>
    </div>
  );
}
