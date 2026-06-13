import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  Info,
  Lightbulb,
  OctagonAlert,
} from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

const CALLOUT_VARIANTS = {
  note: {
    icon: Info,
    border: "border-l-info",
    iconClass: "text-info",
  },
  tip: {
    icon: Lightbulb,
    border: "border-l-success",
    iconClass: "text-success",
  },
  warning: {
    icon: AlertTriangle,
    border: "border-l-warning",
    iconClass: "text-warning",
  },
  danger: {
    icon: OctagonAlert,
    border: "border-l-danger",
    iconClass: "text-danger",
  },
} as const;

export type CalloutType = keyof typeof CALLOUT_VARIANTS;

type CalloutProps = {
  type?: CalloutType;
  title?: string;
  children: ReactNode;
};

export function Callout({
  type = "note",
  title,
  children,
}: CalloutProps) {
  const variant = CALLOUT_VARIANTS[type];
  const Icon = variant.icon;

  return (
    <aside
      className={cn(
        "my-6 flex gap-3 rounded-md border border-border bg-panel p-4 text-sm",
        "border-l-[2px]",
        variant.border,
      )}
    >
      <Icon
        className={cn("size-4 shrink-0", variant.iconClass)}
        strokeWidth={1.5}
      />
      <div className="min-w-0 flex-1">
        {title ? (
          <p className="mb-1 font-medium text-text-primary">{title}</p>
        ) : null}
        <div className="text-text-secondary [&_p]:m-0">{children}</div>
      </div>
    </aside>
  );
}
