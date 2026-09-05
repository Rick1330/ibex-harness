import { AlertTriangle, CheckCircle2, HelpCircle, XCircle, type LucideIcon } from "lucide-react";

import type { RunStatus } from "@/lib/benchmarks/types";

export type RunStatusVisualConfig = Readonly<{
  icon: LucideIcon;
  label: string;
  container: string;
  accent: string;
  dot: string;
}>;

export function runStatusVisualConfig(status: RunStatus): RunStatusVisualConfig {
  switch (status) {
    case "pass":
      return {
        icon: CheckCircle2,
        label: "PASSING",
        container: "border-border bg-card",
        accent: "text-success",
        dot: "bg-success",
      };
    case "regression":
      return {
        icon: AlertTriangle,
        label: "REGRESSION",
        container: "border-warning/30 bg-warning/5",
        accent: "text-warning",
        dot: "bg-warning",
      };
    case "fail":
      return {
        icon: XCircle,
        label: "FAILING",
        container: "border-danger/30 bg-danger/5",
        accent: "text-danger",
        dot: "bg-danger",
      };
    default:
      return {
        icon: HelpCircle,
        label: "UNKNOWN",
        container: "border-border bg-card",
        accent: "text-muted-foreground",
        dot: "bg-muted-foreground",
      };
  }
}

