import { STAGE_LABELS, type StageKey } from "@/lib/benchmarks/chart-colors";
import { GO_MICROBENCH_SYNTHETIC_STAGE_MODEL, SLA_TARGETS } from "@/lib/benchmarks/constants";
import { formatLatencyMs } from "@/lib/benchmarks/format";
import { stagePercentileRows, type StagePercentileRow } from "@/lib/benchmarks/stage-metrics";
import type { StageLatency } from "@/lib/benchmarks/types";

type StageDetailsTableProps = Readonly<{
  stages: StageLatency;
  stageModel?: string | null;
}>;

const SLA_KEY: Partial<Record<StageKey, number>> = {
  auth_lru_p99_ms: SLA_TARGETS.auth_lru_hit_p99_ms,
  auth_grpc_p99_ms: SLA_TARGETS.auth_grpc_fallback_p99_ms,
  rate_limit_p99_ms: SLA_TARGETS.rate_limit_p99_ms,
  directive_resolve_p99_ms: SLA_TARGETS.directive_resolve_p99_ms,
  prompt_inject_p99_ms: SLA_TARGETS.prompt_inject_p99_ms,
  total_overhead_p99_ms: SLA_TARGETS.total_overhead_p99_ms,
};

function isSyntheticStageModel(stageModel: string | null | undefined): boolean {
  return stageModel == null || stageModel === GO_MICROBENCH_SYNTHETIC_STAGE_MODEL;
}

function formatStageBudget(
  isSynthetic: boolean,
  p99: number | undefined,
  target: number | undefined,
): string {
  if (isSynthetic) {
    return "—";
  }
  if (p99 === undefined) {
    return "—";
  }
  if (!target || target <= 0) {
    return "—";
  }
  return `${Math.round((p99 / target) * 100)}%`;
}

function SyntheticStageCaption() {
  return (
    <p className="text-sm text-muted-foreground">
      Synthetic stage percentiles derived from Go microbenchmarks (ns/op), not live proxy traces.
      Use k6 p99 for end-to-end SLA. Values below 0.01 ms are shown in µs/ns.
    </p>
  );
}

type StageDetailsRowProps = Readonly<{
  row: StagePercentileRow;
  isSynthetic: boolean;
}>;

function StageDetailsRow({ row, isSynthetic }: StageDetailsRowProps) {
  const target = SLA_KEY[`${row.base}_p99_ms` as StageKey];
  const budget = formatStageBudget(isSynthetic, row.p99, target);

  return (
    <tr className="history-row border-b border-border last:border-0">
      <td className="px-4 py-2">{row.label}</td>
      <td className="px-4 py-2 font-mono tabular-nums">
        {row.p50 === undefined ? "—" : formatLatencyMs(row.p50)}
      </td>
      <td className="px-4 py-2 font-mono tabular-nums">
        {row.p95 === undefined ? "—" : formatLatencyMs(row.p95)}
      </td>
      <td className="px-4 py-2 font-mono tabular-nums">
        {row.p99 === undefined ? "—" : formatLatencyMs(row.p99)}
      </td>
      <td className="px-4 py-2 font-mono tabular-nums">
        {row.p999 === undefined ? "—" : formatLatencyMs(row.p999)}
      </td>
      {isSynthetic ? null : (
        <td className="px-4 py-2 font-mono tabular-nums">{budget}</td>
      )}
    </tr>
  );
}

export function StageDetailsTable({ stages, stageModel }: StageDetailsTableProps) {
  const rows = stagePercentileRows(stages, STAGE_LABELS);
  const isSynthetic = isSyntheticStageModel(stageModel);

  return (
    <div className="space-y-2">
      {isSynthetic ? <SyntheticStageCaption /> : null}
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border bg-muted/40">
            <tr>
              <th className="px-4 py-2 font-medium text-muted-foreground">Stage</th>
              <th className="px-4 py-2 font-medium text-muted-foreground">p50</th>
              <th className="px-4 py-2 font-medium text-muted-foreground">p95</th>
              <th className="px-4 py-2 font-medium text-muted-foreground">p99</th>
              <th className="px-4 py-2 font-medium text-muted-foreground">p99.9</th>
              {isSynthetic ? null : (
                <th className="px-4 py-2 font-medium text-muted-foreground">Budget</th>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <StageDetailsRow key={row.base} row={row} isSynthetic={isSynthetic} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
