"use client";

import Link from "next/link";

import { cn } from "@/lib/cn";
import { formatBytes, formatDeltaPct, formatMs, formatReqPerSec, formatTimestamp } from "@/lib/benchmarks/format";
import type { BenchmarkRun, RunStatus } from "@/lib/benchmarks/types";

type HistoryTableRowProps = Readonly<{
  run: BenchmarkRun;
  index: number;
  selectedIndex: number;
  isCompareSelected: boolean;
  onRowClick: (shortSha: string) => void;
  onToggleCompare: (shortSha: string) => void;
  statusClassName: (status: RunStatus) => string;
}>;

export function HistoryTableRow({
  run,
  index,
  selectedIndex,
  isCompareSelected,
  onRowClick,
  onToggleCompare,
  statusClassName,
}: HistoryTableRowProps) {
  return (
    <tr
      className="history-row cursor-pointer border-b border-border/70 last:border-0"
      data-selected={index === selectedIndex ? "true" : undefined}
      aria-selected={index === selectedIndex}
      onClick={() => { onRowClick(run.short_sha); }}
    >
      <td className="px-4 py-3" onClick={(event) => { event.stopPropagation(); }}>
        <input
          type="checkbox"
          checked={isCompareSelected}
          onChange={() => { onToggleCompare(run.short_sha); }}
          aria-label={`Compare ${run.short_sha}`}
        />
      </td>
      <td className="px-4 py-3 font-mono text-xs tabular-nums">{run.run_number || "—"}</td>
      <td className="px-4 py-3">
        <Link
          href={`/benchmarks/history/${run.short_sha}`}
          className="font-mono text-xs underline-offset-4 hover:underline"
        >
          {run.short_sha}
        </Link>
      </td>
      <td className="px-4 py-3">{run.branch}</td>
      <td className={cn("px-4 py-3 font-mono text-xs uppercase", statusClassName(run.status))}>
        {run.status}
      </td>
      <td className="px-4 py-3 font-mono tabular-nums">{formatMs(run.k6.p99_ms)}</td>
      <td className="px-4 py-3 font-mono tabular-nums">
        {run.go_benchmarks.BenchmarkProxyOverhead
          ? formatBytes(run.go_benchmarks.BenchmarkProxyOverhead.bytes_per_op)
          : "—"}
      </td>
      <td className="px-4 py-3 font-mono tabular-nums">{formatReqPerSec(run.k6.req_per_s)}</td>
      <td className="px-4 py-3 font-mono tabular-nums">
        {formatDeltaPct(run.regression_vs_baseline_pct)}
      </td>
      <td className="px-4 py-3 text-muted-foreground">
        {run.run_url ? (
          <a
            href={run.run_url}
            target="_blank"
            rel="noreferrer"
            className="underline-offset-4 hover:underline"
          >
            {formatTimestamp(run.timestamp)}
          </a>
        ) : (
          formatTimestamp(run.timestamp)
        )}
      </td>
      <td className="px-4 py-3" onClick={(event) => { event.stopPropagation(); }}>
        <Link
          href={`/benchmarks/compare?base=${run.baseline_sha ?? run.short_sha}&head=${run.short_sha}`}
          className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          Compare
        </Link>
      </td>
    </tr>
  );
}
