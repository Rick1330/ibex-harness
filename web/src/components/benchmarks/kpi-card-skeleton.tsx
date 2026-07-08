import { Skeleton } from "@/components/benchmarks/skeleton";

export function KpiCardSkeleton() {
  return (
    <output
      className="block space-y-3 rounded-md border border-border bg-card p-5"
      aria-live="polite"
      aria-label="Loading metric"
    >
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-8 w-20" />
      <Skeleton className="h-3 w-28" />
    </output>
  );
}

export function StatusBadgeSkeleton() {
  return (
    <output
      className="block space-y-2 rounded-md border border-border bg-card p-4"
      aria-live="polite"
      aria-label="Loading status"
    >
      <Skeleton className="h-4 w-40" />
      <Skeleton className="h-3 w-64" />
      <Skeleton className="h-3 w-56" />
    </output>
  );
}
