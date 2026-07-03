import {
  sortIndicator,
  type HistorySortDir,
  type HistorySortKey,
} from "@/lib/benchmarks/history-table-utils";

function ariaSortValue(
  active: boolean,
  sortDir: HistorySortDir,
): "ascending" | "descending" | "none" {
  if (!active) {
    return "none";
  }
  if (sortDir === "asc") {
    return "ascending";
  }
  return "descending";
}

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
  const ariaSort = ariaSortValue(active, sortDir);

  return (
    <th scope="col" aria-sort={ariaSort} className="px-4 py-3 font-medium text-muted-foreground">
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

type HistoryTableHeadProps = Readonly<{
  sortKey: HistorySortKey;
  sortDir: HistorySortDir;
  onSort: (key: HistorySortKey) => void;
}>;

export function HistoryTableHead({ sortKey, sortDir, onSort }: HistoryTableHeadProps) {
  return (
    <thead className="border-b border-border bg-muted/40">
      <tr>
        <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
          Cmp
        </th>
        <SortHeader label="Run #" column="run_number" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
        <SortHeader label="SHA" column="short_sha" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
        <SortHeader label="Branch" column="branch" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
        <SortHeader label="Status" column="status" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
        <SortHeader label="p99" column="p99" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
        <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
          Allocs
        </th>
        <SortHeader label="req/s" column="req_per_s" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
        <SortHeader label="Delta" column="delta" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
        <SortHeader label="When" column="timestamp" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
        <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
          Actions
        </th>
      </tr>
    </thead>
  );
}
