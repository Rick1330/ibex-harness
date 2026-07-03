"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ExportCsvButton } from "@/components/benchmarks/export-csv-button";
import { HistoryTableFilters } from "@/components/benchmarks/history-table-filters";
import { HistoryTablePagination } from "@/components/benchmarks/history-table-pagination";
import { HistoryTableRow } from "@/components/benchmarks/history-table-row";
import { KeyboardHelpDialog } from "@/components/benchmarks/keyboard-help-dialog";
import { useBenchmarkKeyboard } from "@/hooks/use-benchmark-keyboard";
import { useCompareSelection } from "@/hooks/use-compare-selection";
import {
  compareHistoryRuns,
  defaultSortDirForKey,
  sortIndicator,
  statusClassName,
  type HistorySortDir,
  type HistorySortKey,
} from "@/lib/benchmarks/history-table-utils";
import type { BenchmarkRun, RunStatus } from "@/lib/benchmarks/types";

const STATUS_FILTER_ID = "history-status-filter";
const PAGE_SIZE = 20;

type HistoryTableProps = Readonly<{
  runs: BenchmarkRun[];
}>;

function SortHeader({
  label,
  column,
  sortKey,
  sortDir,
  onSort,
}: Readonly<{
  label: string;
  column: HistorySortKey;
  sortKey: HistorySortKey;
  sortDir: HistorySortDir;
  onSort: (key: HistorySortKey) => void;
}>) {
  const active = sortKey === column;
  const indicator = sortIndicator(active, sortDir);

  return (
    <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
      <button
        type="button"
        onClick={() => { onSort(column); }}
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
  const [sortKey, setSortKey] = useState<HistorySortKey>("timestamp");
  const [sortDir, setSortDir] = useState<HistorySortDir>("desc");
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
    return [...filtered].sort((a, b) => compareHistoryRuns(a, b, sortKey, sortDir));
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
    onShowHelp: () => { setHelpOpen((open) => !open); },
    helpOpen,
    statusFilterId: STATUS_FILTER_ID,
  });

  function toggleSort(key: HistorySortKey) {
    setPage(1);
    if (sortKey === key) {
      setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDir(defaultSortDirForKey(key));
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
              <HistoryTableRow
                key={run.sha}
                run={run}
                index={index}
                selectedIndex={selectedIndex}
                isCompareSelected={compare.isSelected(run.short_sha)}
                onRowClick={(shortSha) => { router.push(`/benchmarks/history/${shortSha}`); }}
                onToggleCompare={compare.toggle}
                statusClassName={statusClassName}
              />
            ))}
          </tbody>
        </table>
      </div>

      <HistoryTablePagination
        pageCount={pageRuns.length}
        totalCount={sorted.length}
        currentPage={currentPage}
        totalPages={totalPages}
        onPrev={() => { setPage((value) => Math.max(1, value - 1)); }}
        onNext={() => { setPage((value) => Math.min(totalPages, value + 1)); }}
      />
      <p className="text-xs text-muted-foreground">
        Click any row to open run detail. Press <kbd className="font-mono">?</kbd> for keyboard
        shortcuts.
      </p>
      <KeyboardHelpDialog open={helpOpen} onClose={() => { setHelpOpen(false); }} />
    </div>
  );
}
