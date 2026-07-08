import type { BenchmarkRun } from "@/lib/benchmarks/types";

const COMPARE_SELECT_CLASS =
  "w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm focus:border-border-strong focus:outline-none focus:ring-2 focus:ring-border-strong/40";

type CompareRunSelectorsProps = Readonly<{
  runs: BenchmarkRun[];
  baseSha: string;
  headSha: string;
  onBaseChange: (sha: string) => void;
  onHeadChange: (sha: string) => void;
}>;

export function CompareRunSelectors({
  runs,
  baseSha,
  headSha,
  onBaseChange,
  onHeadChange,
}: CompareRunSelectorsProps) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <label className="space-y-1 text-sm">
        <span className="text-muted-foreground">Base</span>
        <select
          value={baseSha}
          onChange={(event) => { onBaseChange(event.target.value); }}
          className={COMPARE_SELECT_CLASS}
        >
          {runs.map((run) => (
            <option key={run.sha} value={run.short_sha}>
              {run.short_sha} · {run.branch}
            </option>
          ))}
        </select>
      </label>
      <label className="space-y-1 text-sm">
        <span className="text-muted-foreground">Head</span>
        <select
          value={headSha}
          onChange={(event) => { onHeadChange(event.target.value); }}
          className={COMPARE_SELECT_CLASS}
        >
          {runs.map((run) => (
            <option key={run.sha} value={run.short_sha}>
              {run.short_sha} · {run.branch}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
