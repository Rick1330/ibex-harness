"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";

type ThemeToggleProps = Readonly<{
  className?: string;
}>;

export function ThemeToggle({ className }: ThemeToggleProps) {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div
        aria-hidden
        className={cn(
          "size-8 animate-pulse rounded-[4px] border border-border bg-panel",
          className,
        )}
      />
    );
  }

  const isDark = resolvedTheme === "dark";

  return (
    <button
      type="button"
      aria-label="Toggle theme"
      data-theme-toggle=""
      className={cn(
        "inline-flex size-8 items-center justify-center rounded-[4px] border border-border",
        "text-text-secondary transition-colors hover:bg-panel-raised hover:text-text-primary",
        className,
      )}
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {isDark ? (
        <Sun className="size-4" strokeWidth={2} />
      ) : (
        <Moon className="size-4" strokeWidth={2} />
      )}
    </button>
  );
}
