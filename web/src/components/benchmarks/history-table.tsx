"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ExportCsvButton } from "@/components/benchmarks/export-csv-button";
import { HistoryCompareBanner } from "@/components/benchmarks/history-compare-banner";
import { HistoryTableFilters } from "@/components/benchmarks/history-table-filters";
import { HistoryTableHead } from "@/components/benchmarks/history-table-head";
import { HistoryTablePagination } from "@/components/benchmarks/history-table-pagination";
import { HistoryTableRow } from "@/components/benchmarks/history-table-row";
import { KeyboardHelpDialog } from "@/components/benchmarks/keyboard-help-dialog";
import { useBenchmarkKeyboard } from "@/hooks/use-benchmark-keyboard";
import { useCompareSelection } from "@/hooks/use-compare-selection";
import {
  compareHistoryRuns,
  defaultSortDirForKey,
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
  const pageRuns = useMemo(
    () => sorted.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
    [sorted, currentPage],
  );

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
        <HistoryCompareBanner
          selected={compare.selected}
          compareQuery={compare.compareQuery() ?? ""}
          onClear={compare.clear}
        />
      ) : null}

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="min-w-full text-left text-sm">
          <HistoryTableHead sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
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
