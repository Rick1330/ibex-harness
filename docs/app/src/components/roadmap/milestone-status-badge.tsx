import { cn } from "@/lib/cn";
import type { MilestoneStatus } from "@/lib/roadmap-types";

const labels: Record<MilestoneStatus, string> = {
  completed: "Completed",
  "in-progress": "In Progress",
  planned: "Planned",
};

const styles: Record<MilestoneStatus, string> = {
  completed: "border-border bg-foreground/5 text-foreground",
  "in-progress": "border-border bg-muted/30 text-muted-foreground",
  planned: "border-border bg-muted/20 text-muted-foreground",
};

type MilestoneStatusBadgeProps = {
  status: MilestoneStatus;
  className?: string;
};

export function MilestoneStatusBadge({
  status,
  className,
}: MilestoneStatusBadgeProps) {
  return (
    <span
      className={cn(
        "shrink-0 rounded px-2 py-0.5 text-xs font-semibold border",
        styles[status],
        className,
      )}
    >
      {labels[status]}
    </span>
  );
}
