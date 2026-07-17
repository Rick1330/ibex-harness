import type { ReactNode } from "react";

type LandingShellProps = Readonly<{
  children: ReactNode;
  className?: string;
  compact?: boolean;
}>;

/** Monospace command block for landing stack snippets. */
export function LandingShell({
  children,
  className = "",
  compact = false,
}: LandingShellProps) {
  return (
    <div
      className={`overflow-x-auto rounded-md border border-border bg-surface-1 ${className}`.trim()}
    >
      <pre
        className={`m-0 overflow-x-auto font-mono leading-relaxed ${
          compact ? "p-3 text-[11px]" : "p-4 text-[12px]"
        }`}
      >
        {children}
      </pre>
    </div>
  );
}
