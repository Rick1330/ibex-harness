import { cn } from "@/lib/cn";

type RoadmapProgressProps = Readonly<{
  value: number;
  className?: string;
}>;

export function RoadmapProgress({ value, className }: RoadmapProgressProps) {
  return (
    <div className={cn("h-1.5 overflow-hidden rounded-full bg-muted", className)}>
      <div
        className="h-full rounded-full bg-foreground/70 transition-all duration-500"
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}
