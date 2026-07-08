type HistoryTablePaginationProps = Readonly<{
  pageCount: number;
  totalCount: number;
  currentPage: number;
  totalPages: number;
  onPrev: () => void;
  onNext: () => void;
}>;

export function HistoryTablePagination({
  pageCount,
  totalCount,
  currentPage,
  totalPages,
  onPrev,
  onNext,
}: HistoryTablePaginationProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
      <p>
        Showing {pageCount} of {totalCount} runs
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={currentPage <= 1}
          onClick={onPrev}
          className="rounded-md border border-border px-2 py-1 disabled:opacity-40"
        >
          Prev
        </button>
        <span className="font-mono">
          Page {currentPage} of {totalPages}
        </span>
        <button
          type="button"
          disabled={currentPage >= totalPages}
          onClick={onNext}
          className="rounded-md border border-border px-2 py-1 disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  );
}
