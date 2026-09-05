"use client";

import { useMemo, useState, type ReactNode } from "react";

import { SuiteExportCsvButton } from "@/components/benchmarks/suite-export-csv-button";

const PAGE_SIZE = 20;

export type SuiteHistoryColumn<T> = Readonly<{
  header: string;
  cell: (row: T) => ReactNode;
  csv?: (row: T) => string | number;
  className?: string;
}>;

type SuiteHistoryTableProps<T> = Readonly<{
  rows: readonly T[];
  rowKey: (row: T) => string | number;
  columns: readonly SuiteHistoryColumn<T>[];
  getStatus: (row: T) => string;
  getBranch: (row: T) => string;
  csvFilename: string;
}>;

function uniqueSorted(values: Iterable<string>): string[] {
  return Array.from(new Set(values)).sort((a, b) => a.localeCompare(b));
}

function HistoryFilters({
  statuses,
  branches,
  statusFilter,
  branchFilter,
  onStatusChange,
  onBranchChange,
}: Readonly<{
  statuses: readonly string[];
  branches: readonly string[];
  statusFilter: string;
  branchFilter: string;
  onStatusChange: (value: string) => void;
  onBranchChange: (value: string) => void;
}>) {
  return (
    <div className="flex flex-wrap gap-3">
      <label className="space-y-1 text-sm">
        <span className="text-muted-foreground">Status</span>
        <select
          value={statusFilter}
          onChange={(event) => {
            onStatusChange(event.target.value);
          }}
          className="block w-40 rounded-md border border-border bg-background px-3 py-2 font-mono text-sm"
        >
          {statuses.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
      </label>
      <label className="space-y-1 text-sm">
        <span className="text-muted-foreground">Branch</span>
        <select
          value={branchFilter}
          onChange={(event) => {
            onBranchChange(event.target.value);
          }}
          className="block w-48 rounded-md border border-border bg-background px-3 py-2 font-mono text-sm"
        >
          {branches.map((branch) => (
            <option key={branch} value={branch}>
              {branch}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

function HistoryPagination({
  currentPage,
  totalPages,
  filteredCount,
  totalCount,
  onPrev,
  onNext,
}: Readonly<{
  currentPage: number;
  totalPages: number;
  filteredCount: number;
  totalCount: number;
  onPrev: () => void;
  onNext: () => void;
}>) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
      <p>
        {filteredCount} run{filteredCount === 1 ? "" : "s"}
        {filteredCount !== totalCount ? ` (filtered from ${totalCount})` : ""}
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={currentPage <= 1}
          onClick={onPrev}
          className="rounded-md border border-border px-3 py-1 disabled:opacity-50"
        >
          Prev
        </button>
        <span className="font-mono text-xs">
          {currentPage} / {totalPages}
        </span>
        <button
          type="button"
          disabled={currentPage >= totalPages}
          onClick={onNext}
          className="rounded-md border border-border px-3 py-1 disabled:opacity-50"
        >
          Next
        </button>
      </div>
    </div>
  );
}

export function SuiteHistoryTable<T>({
  rows,
  rowKey,
  columns,
  getStatus,
  getBranch,
  csvFilename,
}: SuiteHistoryTableProps<T>) {
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [branchFilter, setBranchFilter] = useState<string>("all");
  const [page, setPage] = useState(1);

  const statuses = useMemo(
    () => ["all", ...uniqueSorted(rows.map((row) => getStatus(row)))],
    [rows, getStatus],
  );
  const branches = useMemo(
    () => ["all", ...uniqueSorted(rows.map((row) => getBranch(row)))],
    [rows, getBranch],
  );

  const filtered = useMemo(() => {
    return rows.filter((row) => {
      if (statusFilter !== "all" && getStatus(row) !== statusFilter) {
        return false;
      }
      if (branchFilter !== "all" && getBranch(row) !== branchFilter) {
        return false;
      }
      return true;
    });
  }, [rows, statusFilter, branchFilter, getStatus, getBranch]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageRows = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const csvHeaders = columns.map((column) => column.header);
  const csvRows = filtered.map((row) =>
    columns.map((column) => {
      if (column.csv) {
        return column.csv(row);
      }
      const value = column.cell(row);
      return typeof value === "string" || typeof value === "number" ? value : "";
    }),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <HistoryFilters
          statuses={statuses}
          branches={branches}
          statusFilter={statusFilter}
          branchFilter={branchFilter}
          onStatusChange={(value) => {
            setStatusFilter(value);
            setPage(1);
          }}
          onBranchChange={(value) => {
            setBranchFilter(value);
            setPage(1);
          }}
        />
        <SuiteExportCsvButton
          filename={csvFilename}
          headers={csvHeaders}
          rows={csvRows}
        />
      </div>

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-border bg-muted/40">
            <tr>
              {columns.map((column) => (
                <th
                  key={column.header}
                  className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-muted-foreground"
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-8 text-center text-sm text-muted-foreground"
                >
                  No runs match the selected filters.
                </td>
              </tr>
            ) : (
              pageRows.map((row) => (
                <tr key={rowKey(row)} className="border-b border-border/70 last:border-0">
                  {columns.map((column) => (
                    <td
                      key={column.header}
                      className={column.className ?? "px-4 py-3 font-mono text-sm"}
                    >
                      {column.cell(row)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <HistoryPagination
        currentPage={currentPage}
        totalPages={totalPages}
        filteredCount={filtered.length}
        totalCount={rows.length}
        onPrev={() => {
          setPage((value) => Math.max(1, value - 1));
        }}
        onNext={() => {
          setPage((value) => Math.min(totalPages, value + 1));
        }}
      />
    </div>
  );
}
