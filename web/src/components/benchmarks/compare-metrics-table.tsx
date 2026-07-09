import { cn } from "@/lib/cn";
import type { CompareMetricRow } from "@/lib/benchmarks/compare-metrics";

export type { CompareMetricRow };

function isNeutralDelta(delta: number | null): boolean {
  if (delta === null) {
    return true;
  }
  if (!Number.isFinite(delta)) {
    return true;
  }
  return Math.abs(delta) < 0.05;
}

function deltaClass(delta: number | null, higherIsBetter = false): string {
  if (isNeutralDelta(delta)) {
    return "text-muted-foreground";
  }
  const value = delta as number;
  const improved = higherIsBetter ? value > 0 : value < 0;
  return improved ? "text-success" : "text-danger";
}

type CompareMetricsTableProps = Readonly<{
  baseSha: string;
  headSha: string;
  rows: CompareMetricRow[];
}>;

export function CompareMetricsTable({ baseSha, headSha, rows }: CompareMetricsTableProps) {
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-border bg-muted/40">
          <tr>
            <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
              Metric
            </th>
            <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
              {baseSha}
            </th>
            <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
              {headSha}
            </th>
            <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
              Delta
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="history-row border-b border-border/70 last:border-0">
              <td className="px-4 py-3">{row.label}</td>
              <td className="px-4 py-3 font-mono tabular-nums">{row.base}</td>
              <td className="px-4 py-3 font-mono tabular-nums">{row.head}</td>
              <td
                className={cn(
                  "px-4 py-3 font-mono tabular-nums",
                  deltaClass(row.deltaValue, row.higherIsBetter),
                )}
              >
                {row.delta}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
