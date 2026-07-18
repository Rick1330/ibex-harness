import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type LandingShellProps = Readonly<{
  children: ReactNode;
  className?: string;
  compact?: boolean;
}>;

/** Compact command block — same shell tokens as CodeShell (both themes). */
export function LandingShell({
  children,
  className = "",
  compact = false,
}: LandingShellProps) {
  return (
    <div className={cn("code-shell", className)}>
      <pre
        className={cn(
          "code-shell-body m-0",
          compact ? "min-h-0 p-3 text-[11px]" : "min-h-0 p-4 text-[12px]",
        )}
      >
        {children}
      </pre>
    </div>
  );
}
