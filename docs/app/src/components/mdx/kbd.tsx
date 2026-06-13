import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type KbdProps = {
  children: ReactNode;
  className?: string;
};

export function Kbd({ children, className }: KbdProps) {
  return (
    <kbd
      className={cn(
        "inline-flex min-h-5 items-center rounded-[4px] border border-border",
        "bg-panel-raised px-1.5 font-mono text-[0.85em] text-text-primary",
        className,
      )}
    >
      {children}
    </kbd>
  );
}
