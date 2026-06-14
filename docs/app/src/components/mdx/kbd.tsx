import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type KbdProps = Readonly<{
  children: ReactNode;
  className?: string;
}>;

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

type KbdComboProps = Readonly<{
  keys: string[];
  className?: string;
}>;

export function KbdCombo({ keys, className }: KbdComboProps) {
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      {keys.map((key, index) => (
        <span className="inline-flex items-center gap-1" key={`${key}-${index}`}>
          <Kbd>{key}</Kbd>
          {index < keys.length - 1 ? (
            <span className="text-text-tertiary">+</span>
          ) : null}
        </span>
      ))}
    </span>
  );
}

