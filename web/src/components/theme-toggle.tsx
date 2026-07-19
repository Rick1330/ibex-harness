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

type ThemeValue = (typeof OPTS)[number]["v"];

type ThemeToggleProps = Readonly<{
  className?: string;
}>;

function nextTheme(current: ThemeValue): ThemeValue {
  const index = OPTS.findIndex((opt) => opt.v === current);
  return OPTS[(index + 1) % OPTS.length]?.v ?? "system";
}

function ThemeToggleSkeleton({ className }: ThemeToggleProps) {
  return (
    <>
      <div
        aria-hidden
        className={cn(
          "size-8 animate-pulse rounded-full border border-border bg-surface md:hidden",
          className,
        )}
      />
      <div
        aria-hidden
        className={cn(
          "hidden h-8 w-[5.5rem] animate-pulse rounded-sm border border-border bg-surface md:inline-flex",
          className,
        )}
      />
    </>
  );
}

/** Mobile: one cycle button. Desktop: three-state segmented control. */
export function ThemeToggle({ className }: ThemeToggleProps) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return <ThemeToggleSkeleton className={className} />;
  }

  const current = (theme ?? "system") as ThemeValue;
  const currentOpt = OPTS.find((opt) => opt.v === current) ?? OPTS[0];
  const CurrentIcon = currentOpt.icon;

  return (
    <>
      <button
        type="button"
        data-theme-toggle="compact"
        aria-label={`Theme: ${currentOpt.label}. Click to switch.`}
        title={`Theme: ${currentOpt.label}`}
        onClick={() => setTheme(nextTheme(current))}
        className={cn(
          "inline-flex size-8 items-center justify-center rounded-full border border-border bg-surface",
          "text-foreground shadow-[var(--shadow-1)] transition-[transform,background-color,color]",
          "duration-[var(--dur-1)] hover:bg-background hover:text-foreground active:translate-y-px",
          "md:hidden",
          className,
        )}
      >
        <CurrentIcon className="size-3.5" strokeWidth={1.75} />
      </button>

      <div
        role="radiogroup"
        aria-label="Theme"
        data-theme-toggle="segmented"
        className={cn(
          "hidden items-center rounded-sm border border-border bg-surface p-0.5 md:inline-flex",
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
    </>
  );
}
