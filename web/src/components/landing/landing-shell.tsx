import type { ReactNode } from "react";

type LandingShellProps = Readonly<{
  children: ReactNode;
  className?: string;
  compact?: boolean;
  surface?: "card" | "primary";
}>;

const surfaceClasses: Record<NonNullable<LandingShellProps["surface"]>, string> = {
  card: "bg-card text-foreground",
  primary:
    "border-primary-foreground/30 bg-primary-foreground/5 text-primary-foreground",
};

/** Monospace command block with ascii-frame depth (landing-guide shell pattern). */
export function LandingShell({
  children,
  className = "",
  compact = false,
  surface = "card",
}: LandingShellProps) {
  return (
    <div
      className={`ascii-frame overflow-x-auto ${surfaceClasses[surface]} ${className}`.trim()}
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
