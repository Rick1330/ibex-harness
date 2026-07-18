"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";

const OPTS = [
  { v: "system", icon: Monitor, label: "System" },
  { v: "light", icon: Sun, label: "Light" },
  { v: "dark", icon: Moon, label: "Dark" },
] as const;

type ThemeToggleProps = Readonly<{
  className?: string;
}>;

/** Three-state segmented theme control (DESIGN_GUIDE.md §9). */
export function ThemeToggle({ className }: ThemeToggleProps) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const current = mounted ? (theme ?? "system") : "system";

  if (!mounted) {
    return (
      <div
        aria-hidden
        className={cn(
          "inline-flex h-8 w-[5.5rem] animate-pulse rounded-sm border border-border bg-surface",
          className,
        )}
      />
    );
  }

  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      data-theme-toggle=""
      className={cn(
        "inline-flex items-center rounded-sm border border-border bg-surface p-0.5",
        className,
      )}
    >
      {OPTS.map(({ v, icon: Icon, label }) => {
        const active = current === v;
        return (
          <button
            key={v}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            onClick={() => setTheme(v)}
            className={cn(
              "grid size-7 place-items-center rounded-sm transition-colors",
              active
                ? "bg-background text-foreground shadow-[var(--shadow-1)]"
                : "text-foreground-subtle hover:text-foreground",
            )}
          >
            <Icon className="size-3.5" strokeWidth={1.75} />
          </button>
        );
      })}
    </div>
  );
}
