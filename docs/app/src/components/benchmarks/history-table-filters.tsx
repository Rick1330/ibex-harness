import type { RunStatus } from "@/lib/benchmarks/types";

const FILTER_SELECT_CLASS =
  "rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground focus:border-border-strong focus:outline-none focus:ring-2 focus:ring-border-strong/40";

type HistoryTableFiltersProps = Readonly<{
  statusFilterId: string;
  statusFilter: RunStatus | "all";
  branchFilter: string;
  branches: string[];
  onStatusChange: (value: RunStatus | "all") => void;
  onBranchChange: (value: string) => void;
}>;

export function HistoryTableFilters({
  statusFilterId,
  statusFilter,
  branchFilter,
  branches,
  onStatusChange,
  onBranchChange,
}: HistoryTableFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <label htmlFor={statusFilterId} className="text-xs text-muted-foreground">
        <span className="mr-2">Status</span>
        <select
          id={statusFilterId}
          value={statusFilter}
          onChange={(event) => { onStatusChange(event.target.value as RunStatus | "all"); }}
          className={FILTER_SELECT_CLASS}
        >
          <option value="all">All</option>
          <option value="pass">Pass</option>
          <option value="regression">Regression</option>
          <option value="fail">Fail</option>
          <option value="unknown">Unknown</option>
        </select>
      </label>
      <label htmlFor="history-branch-filter" className="text-xs text-muted-foreground">
        <span className="mr-2">Branch</span>
        <select
          id="history-branch-filter"
          value={branchFilter}
          onChange={(event) => { onBranchChange(event.target.value); }}
          className={FILTER_SELECT_CLASS}
        >
          {branches.map((branch) => (
            <option key={branch} value={branch}>
              {branch === "all" ? "All" : branch}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
