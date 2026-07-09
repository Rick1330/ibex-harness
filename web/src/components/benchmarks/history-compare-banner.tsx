import Link from "next/link";

type HistoryCompareBannerProps = Readonly<{
  selected: string[];
  compareQuery: string;
  onClear: () => void;
}>;

export function HistoryCompareBanner({ selected, compareQuery, onClear }: HistoryCompareBannerProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-panel px-4 py-3 text-sm">
      <p className="font-mono text-xs text-muted-foreground">
        Compare selected: {selected.join(" vs ")}
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onClear}
          className="rounded-md border border-border px-2 py-1 text-xs"
        >
          Clear
        </button>
        <Link
          href={`/benchmarks/compare?${compareQuery}`}
          className="rounded-md border border-border bg-background px-2 py-1 text-xs font-medium hover:bg-panel-raised"
        >
          Compare selected ({selected.length})
        </Link>
      </div>
    </div>
  );
}
