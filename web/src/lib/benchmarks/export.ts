import type { BenchmarkRun } from "@/lib/benchmarks/types";
import { formatMs, formatReqPerSec } from "@/lib/benchmarks/format";
import type { TimeRange } from "@/lib/benchmarks/plot";
import { filterRunsByRange } from "@/lib/benchmarks/plot";
import { proxyOverheadBenchmark } from "@/lib/benchmarks/run-benchmarks";

function needsCsvQuoting(value: string): boolean {
  return value.includes(",") || value.includes('"') || value.includes("\n");
}

function csvEscape(value: string): string {
  if (!needsCsvQuoting(value)) {
    return value;
  }
  return `"${value.replaceAll('"', '""')}"`;
}

function overheadBytes(run: BenchmarkRun): string {
  const bench = proxyOverheadBenchmark(run);
  return bench ? String(bench.bytes_per_op) : "";
}

export function exportRunsCsv(runs: BenchmarkRun[], range: TimeRange = "all"): void {
  const filtered = filterRunsByRange(runs, range);
  const header = [
    "run_number",
    "short_sha",
    "branch",
    "status",
    "timestamp",
    "p99_ms",
    "req_per_s",
    "error_rate",
    "bytes_per_op",
    "regression_vs_baseline_pct",
  ];

  const lines = filtered.map((run) =>
    [
      String(run.run_number),
      run.short_sha,
      run.branch,
      run.status,
      run.timestamp,
      formatMs(run.k6.p99_ms),
      formatReqPerSec(run.k6.req_per_s),
      String(run.k6.error_rate),
      overheadBytes(run),
      run.regression_vs_baseline_pct === null ? "" : String(run.regression_vs_baseline_pct),
    ]
      .map(csvEscape)
      .join(","),
  );

  const blob = new Blob([[header.join(","), ...lines].join("\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `ibex-benchmarks-${range}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
