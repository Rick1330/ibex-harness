import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Lightbulb,
  OctagonAlert,
  Sparkles,
  Zap,
} from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

const CALLOUT_VARIANTS = {
  note: {
    icon: Info,
    border: "border-l-info",
    iconClass: "text-info",
  },
  info: {
    icon: Info,
    border: "border-l-info",
    iconClass: "text-info",
  },
  tip: {
    icon: Lightbulb,
    border: "border-l-success",
    iconClass: "text-success",
  },
  success: {
    icon: CheckCircle2,
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
  new: {
    icon: Sparkles,
    border: "border-l-info",
    iconClass: "text-info",
  },
  experimental: {
    icon: Zap,
    border: "border-l-warning",
    iconClass: "text-warning",
  },
} as const;

export type CalloutType = keyof typeof CALLOUT_VARIANTS;

type CalloutProps = Readonly<{
  type?: CalloutType;
  title?: string;
  children: ReactNode;
}>;

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
        "ibex-callout my-8 flex gap-4 rounded-md border border-border bg-panel p-5",
        "border-s-[3px]",
        variant.border,
      )}
      data-type={type}
    >
      <Icon
        className={cn("mt-0.5 size-5 shrink-0", variant.iconClass)}
        strokeWidth={1.5}
      />
      <div className="min-w-0 flex-1">
        {title ? (
          <p className="mb-2 text-[0.9375rem] font-semibold text-text-primary">
            {title}
          </p>
        ) : null}
        <div className="text-[0.9375rem] leading-relaxed text-text-secondary [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0">
          {children}
        </div>
      </div>
    </aside>
  );
}
