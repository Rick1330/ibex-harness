import { STAGE_LABELS, type StageKey } from "@/lib/benchmarks/chart-colors";
import { formatMs } from "@/lib/benchmarks/format";
import { SLA_TARGETS } from "@/lib/benchmarks/constants";
import { stagePercentileRows } from "@/lib/benchmarks/stage-metrics";
import type { StageLatency } from "@/lib/benchmarks/types";

type StageDetailsTableProps = Readonly<{
  stages: StageLatency;
}>;

const SLA_KEY: Partial<Record<StageKey, number>> = {
  auth_lru_p99_ms: SLA_TARGETS.auth_lru_hit_p99_ms,
  auth_grpc_p99_ms: SLA_TARGETS.auth_grpc_fallback_p99_ms,
  rate_limit_p99_ms: SLA_TARGETS.rate_limit_p99_ms,
  directive_resolve_p99_ms: SLA_TARGETS.directive_resolve_p99_ms,
  prompt_inject_p99_ms: SLA_TARGETS.prompt_inject_p99_ms,
  total_overhead_p99_ms: SLA_TARGETS.total_overhead_p99_ms,
};

export function StageDetailsTable({ stages }: StageDetailsTableProps) {
  const rows = stagePercentileRows(stages, STAGE_LABELS);

  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-border bg-muted/40">
          <tr>
            <th className="px-4 py-2 font-medium text-muted-foreground">Stage</th>
            <th className="px-4 py-2 font-medium text-muted-foreground">p50</th>
            <th className="px-4 py-2 font-medium text-muted-foreground">p95</th>
            <th className="px-4 py-2 font-medium text-muted-foreground">p99</th>
            <th className="px-4 py-2 font-medium text-muted-foreground">p99.9</th>
            <th className="px-4 py-2 font-medium text-muted-foreground">Budget</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const target = SLA_KEY[`${row.base}_p99_ms` as StageKey];
            const budget =
              row.p99 !== undefined && target && target > 0
                ? `${Math.round((row.p99 / target) * 100)}%`
                : "—";

            return (
              <tr key={row.base} className="history-row border-b border-border last:border-0">
                <td className="px-4 py-2">{row.label}</td>
                <td className="px-4 py-2 font-mono tabular-nums">
                  {row.p50 === undefined ? "—" : formatMs(row.p50)}
                </td>
                <td className="px-4 py-2 font-mono tabular-nums">
                  {row.p95 === undefined ? "—" : formatMs(row.p95)}
                </td>
                <td className="px-4 py-2 font-mono tabular-nums">
                  {row.p99 === undefined ? "—" : formatMs(row.p99)}
                </td>
                <td className="px-4 py-2 font-mono tabular-nums">
                  {row.p999 === undefined ? "—" : formatMs(row.p999)}
                </td>
                <td className="px-4 py-2 font-mono tabular-nums">{budget}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
