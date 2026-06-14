import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/cn";

type Status = "stable" | "beta" | "deprecated" | "new";

const STATUS_CONFIG: Record<
  Status,
  { icon: LucideIcon; label: string; className: string }
> = {
  stable: {
    icon: CheckCircle2,
    label: "Stable",
    className: "border-success/40 text-success",
  },
  beta: {
    icon: Clock,
    label: "Beta",
    className: "border-warning/40 text-warning",
  },
  deprecated: {
    icon: AlertTriangle,
    label: "Deprecated",
    className: "border-danger/40 text-danger",
  },
  new: {
    icon: Sparkles,
    label: "New",
    className: "border-info/40 text-info",
  },
};

type StatusBadgeProps = {
  status: Status;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  const Icon = config.icon;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[4px] border bg-panel px-2 py-1",
        "align-middle text-xs font-medium",
        config.className,
      )}
    >
      <Icon className="size-3.5" strokeWidth={1.5} />
      {config.label}
    </span>
  );
}
