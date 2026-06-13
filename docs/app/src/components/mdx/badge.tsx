import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

const BADGE_VARIANTS = {
  default: "border-border text-text-secondary",
  beta: "border-warning/40 text-warning",
  new: "border-success/40 text-success",
  deprecated: "border-danger/40 text-danger",
} as const;

export type BadgeVariant = keyof typeof BADGE_VARIANTS;

type BadgeProps = {
  variant?: BadgeVariant;
  children: ReactNode;
};

export function Badge({ variant = "default", children }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-[4px] border bg-panel px-1.5",
        "text-[11px] font-medium uppercase tracking-wide",
        BADGE_VARIANTS[variant],
      )}
    >
      {children}
    </span>
  );
}
