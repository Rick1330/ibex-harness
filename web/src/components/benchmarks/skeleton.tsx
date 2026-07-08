import { cn } from "@/lib/cn";

type SkeletonProps = Readonly<{
  className?: string;
}>;

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={cn("animate-pulse rounded-sm bg-muted", className)}
      aria-hidden="true"
    />
  );
}

export function ChartSkeleton({ className }: SkeletonProps) {
  return <Skeleton className={cn("h-[200px] w-full rounded-md", className)} />;
}
