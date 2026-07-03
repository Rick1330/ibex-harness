"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ExportCsvButton } from "@/components/benchmarks/export-csv-button";
import { HistoryTableFilters } from "@/components/benchmarks/history-table-filters";
import { HistoryTablePagination } from "@/components/benchmarks/history-table-pagination";
import { KeyboardHelpDialog } from "@/components/benchmarks/keyboard-help-dialog";
import { useBenchmarkKeyboard } from "@/hooks/use-benchmark-keyboard";
import { useCompareSelection } from "@/hooks/use-compare-selection";
import { cn } from "@/lib/cn";
import { formatBytes, formatDeltaPct, formatMs, formatReqPerSec } from "@/lib/benchmarks/format";
import type { BenchmarkRun, RunStatus } from "@/lib/benchmarks/types";

const STATUS_FILTER_ID = "history-status-filter";

type SortKey = "run_number" | "short_sha" | "branch" | "status" | "p99" | "req_per_s" | "delta" | "timestamp";
type SortDir = "asc" | "desc";

type HistoryTableProps = Readonly<{
  runs: BenchmarkRun[];
}>;

const PAGE_SIZE = 20;

const STATUS_ORDER: Record<RunStatus, number> = {
  fail: 0,
  regression: 1,
  unknown: 2,
  pass: 3,
};

function sortValue(run: BenchmarkRun, key: SortKey): string | number {
  switch (key) {
    case "run_number":
      return run.run_number;
    case "short_sha":
      return run.short_sha;
    case "branch":
      return run.branch;
    case "status":
      return STATUS_ORDER[run.status];
    case "p99":
      return run.k6.p99_ms;
    case "req_per_s":
      return run.k6.req_per_s;
    case "delta":
      return run.regression_vs_baseline_pct ?? Number.NEGATIVE_INFINITY;
    case "timestamp":
      return new Date(run.timestamp).getTime();
    default:
      return 0;
  }
}

function compareRuns(a: BenchmarkRun, b: BenchmarkRun, key: SortKey, dir: SortDir): number {
  const left = sortValue(a, key);
  const right = sortValue(b, key);
  const cmp =
    typeof left === "string" && typeof right === "string"
      ? left.localeCompare(right)
      : Number(left) - Number(right);
  return dir === "asc" ? cmp : -cmp;
}

function statusClass(status: RunStatus): string {
  switch (status) {
    case "pass":
      return "text-success";
    case "regression":
      return "text-warning";
    case "fail":
      return "text-danger";
    default:
      return "text-muted-foreground";
  }
}

function sortIndicator(active: boolean, sortDir: SortDir): string {
  if (!active) {
    return "";
  }
  if (sortDir === "asc") {
    return " ↑";
  }
  return " ↓";
}

function SortHeader({
  label,
  column,
  sortKey,
  sortDir,
  onSort,
}: Readonly<{
  label: string;
  column: SortKey;
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (key: SortKey) => void;
}>) {
  const active = sortKey === column;
  const indicator = sortIndicator(active, sortDir);

  return (
    <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
      <button
        type="button"
        onClick={() => onSort(column)}
        className="inline-flex items-center gap-1 hover:text-foreground"
      >
        {label}
        <span className="font-mono text-xs" aria-hidden>
          {indicator}
        </span>
      </button>
    </th>
  );
}

export function HistoryTable({ runs }: HistoryTableProps) {
  const router = useRouter();
  const [sortKey, setSortKey] = useState<SortKey>("timestamp");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [statusFilter, setStatusFilter] = useState<RunStatus | "all">("all");
  const [branchFilter, setBranchFilter] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [helpOpen, setHelpOpen] = useState(false);
  const compare = useCompareSelection();

  const branches = useMemo(() => {
    const values = new Set(runs.map((run) => run.branch));
    return ["all", ...Array.from(values).sort((a, b) => a.localeCompare(b))];
  }, [runs]);

  const sorted = useMemo(() => {
    const filtered = runs.filter((run) => {
      if (statusFilter !== "all" && run.status !== statusFilter) {
        return false;
      }
      if (branchFilter !== "all" && run.branch !== branchFilter) {
        return false;
      }
      return true;
    });
    return [...filtered].sort((a, b) => compareRuns(a, b, sortKey, sortDir));
  }, [runs, sortKey, sortDir, statusFilter, branchFilter]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageRuns = sorted.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  useEffect(() => {
    setSelectedIndex(0);
  }, [currentPage, statusFilter, branchFilter, sortKey, sortDir]);

  useBenchmarkKeyboard({
    pageRuns,
    selectedIndex,
    setSelectedIndex,
    onToggleCompare: compare.toggle,
    onShowHelp: () => setHelpOpen((open) => !open),
    helpOpen,
    statusFilterId: STATUS_FILTER_ID,
  });

  function toggleSort(key: SortKey) {
    setPage(1);
    if (sortKey === key) {
      setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDir(key === "timestamp" ? "desc" : "asc");
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <HistoryTableFilters
          statusFilterId={STATUS_FILTER_ID}
          statusFilter={statusFilter}
          branchFilter={branchFilter}
          branches={branches}
          onStatusChange={(value) => {
            setPage(1);
            setStatusFilter(value);
          }}
          onBranchChange={(value) => {
            setPage(1);
            setBranchFilter(value);
          }}
        />
        <ExportCsvButton runs={sorted} />
      </div>

      {compare.canCompare ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-panel px-4 py-3 text-sm">
          <p className="font-mono text-xs text-muted-foreground">
            Compare selected: {compare.selected.join(" vs ")}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={compare.clear}
              className="rounded-md border border-border px-2 py-1 text-xs"
            >
              Clear
            </button>
            <Link
              href={`/benchmarks/compare?${compare.compareQuery()}`}
              className="rounded-md border border-border bg-background px-2 py-1 text-xs font-medium hover:bg-panel-raised"
            >
              Compare selected (2)
            </Link>
          </div>
        </div>
      ) : null}

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-border bg-muted/40">
            <tr>
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                Cmp
              </th>
              <SortHeader label="Run #" column="run_number" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              <SortHeader label="SHA" column="short_sha" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              <SortHeader label="Branch" column="branch" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              <SortHeader label="Status" column="status" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              <SortHeader label="p99" column="p99" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                Allocs
              </th>
              <SortHeader label="req/s" column="req_per_s" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              <SortHeader label="Delta" column="delta" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              <SortHeader label="When" column="timestamp" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {pageRuns.map((run, index) => (
              <tr
                key={run.sha}
                className="history-row cursor-pointer border-b border-border/70 last:border-0"
                data-selected={index === selectedIndex ? "true" : undefined}
                aria-selected={index === selectedIndex}
                onClick={() => router.push(`/benchmarks/history/${run.short_sha}`)}
              >
                <td className="px-4 py-3" onClick={(event) => event.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={compare.isSelected(run.short_sha)}
                    onChange={() => compare.toggle(run.short_sha)}
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
                <td className={cn("px-4 py-3 font-mono text-xs uppercase", statusClass(run.status))}>
                  {run.status}
                </td>
                <td className="px-4 py-3 font-mono tabular-nums">{formatMs(run.k6.p99_ms)}</td>
                <td className="px-4 py-3 font-mono tabular-nums">
                  {run.go_benchmarks.BenchmarkProxyOverhead
                    ? formatBytes(run.go_benchmarks.BenchmarkProxyOverhead.bytes_per_op)
                    : "—"}
                </td>
                <td className="px-4 py-3 font-mono tabular-nums">
                  {formatReqPerSec(run.k6.req_per_s)}
                </td>
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
                      {new Date(run.timestamp).toLocaleString()}
                    </a>
                  ) : (
                    new Date(run.timestamp).toLocaleString()
                  )}
                </td>
                <td className="px-4 py-3" onClick={(event) => event.stopPropagation()}>
                  <Link
                    href={`/benchmarks/compare?base=${run.baseline_sha ?? run.short_sha}&head=${run.short_sha}`}
                    className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                  >
                    Compare
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <HistoryTablePagination
        pageCount={pageRuns.length}
        totalCount={sorted.length}
        currentPage={currentPage}
        totalPages={totalPages}
        onPrev={() => setPage((value) => Math.max(1, value - 1))}
        onNext={() => setPage((value) => Math.min(totalPages, value + 1))}
      />
      <p className="text-xs text-muted-foreground">
        Click any row to open run detail. Press <kbd className="font-mono">?</kbd> for keyboard
        shortcuts.
      </p>
      <KeyboardHelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}
