"use client";

import { Download } from "lucide-react";

import type { BenchmarkRun } from "@/lib/benchmarks/types";
import { exportRunsCsv } from "@/lib/benchmarks/export";
import type { TimeRange } from "@/lib/benchmarks/plot";

type ExportCsvButtonProps = Readonly<{
  runs: BenchmarkRun[];
  range?: TimeRange;
  label?: string;
}>;

export function ExportCsvButton({
  runs,
  range = "all",
  label = "Export CSV",
}: ExportCsvButtonProps) {
  return (
    <button
      type="button"
      onClick={() => exportRunsCsv(runs, range)}
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 font-mono text-xs text-muted-foreground transition-colors hover:text-foreground"
    >
      <Download className="h-3.5 w-3.5" aria-hidden />
      {label}
    </button>
  );
}
