import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/cn";

type Status = "stable" | "beta" | "deprecated" | "new";

type StatusConfig = {
  icon: LucideIcon;
  label: string;
  className: string;
};

const STABLE_CONFIG: StatusConfig = {
  icon: CheckCircle2,
  label: "Stable",
  className: "border-success/40 text-success",
};

const BETA_CONFIG: StatusConfig = {
  icon: Clock,
  label: "Beta",
  className: "border-warning/40 text-warning",
};

const DEPRECATED_CONFIG: StatusConfig = {
  icon: AlertTriangle,
  label: "Deprecated",
  className: "border-danger/40 text-danger",
};

const NEW_CONFIG: StatusConfig = {
  icon: Sparkles,
  label: "New",
  className: "border-info/40 text-info",
};

function statusConfig(status: Status): StatusConfig {
  switch (status) {
    case "stable":
      return STABLE_CONFIG;
    case "beta":
      return BETA_CONFIG;
    case "deprecated":
      return DEPRECATED_CONFIG;
    case "new":
      return NEW_CONFIG;
  }
}

type StatusBadgeProps = Readonly<{
  status: Status;
}>;

export function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusConfig(status);
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
