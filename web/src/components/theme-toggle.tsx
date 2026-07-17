"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";

const THEME_CYCLE = ["system", "light", "dark"] as const;

type ThemeCycle = (typeof THEME_CYCLE)[number];

type ThemeToggleProps = Readonly<{
  className?: string;
}>;

function nextTheme(current: ThemeCycle): ThemeCycle {
  const index = THEME_CYCLE.indexOf(current);
  return THEME_CYCLE[(index + 1) % THEME_CYCLE.length];
}

function themeLabel(theme: ThemeCycle, resolved: string | undefined): string {
  if (theme === "system") return "Theme: system";
  if (theme === "light") return "Theme: light";
  return "Theme: dark";
}

function resolveThemeIcon(
  active: ThemeCycle,
  resolvedTheme: string | undefined,
): typeof Monitor {
  if (active === "system") return Monitor;
  if (resolvedTheme === "dark") return Moon;
  return Sun;
}

export function ThemeToggle({ className }: ThemeToggleProps) {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div
        aria-hidden
        className={cn(
          "size-8 animate-pulse rounded-sm border border-border bg-surface-1",
          className,
        )}
      />
    );
  }

  const active = (theme ?? "system") as ThemeCycle;
  const Icon = resolveThemeIcon(active, resolvedTheme);

  return (
    <button
      type="button"
      aria-label={themeLabel(active, resolvedTheme)}
      data-theme-toggle=""
      className={cn(
        "inline-flex size-8 items-center justify-center rounded-sm border border-border",
        "text-foreground-muted transition-colors hover:bg-surface-1 hover:text-foreground",
        className,
      )}
      onClick={() => setTheme(nextTheme(active))}
    >
      <Icon className="size-4" strokeWidth={2} />
    </button>
  );
}
