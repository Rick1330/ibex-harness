"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { cn } from "@/lib/cn";
import type { TimeRange } from "@/lib/benchmarks/plot";
import { parseTimeRange } from "@/lib/benchmarks/plot";

const RANGES: { value: TimeRange; label: string }[] = [
  { value: "7d", label: "7d" },
  { value: "14d", label: "14d" },
  { value: "30d", label: "30d" },
  { value: "90d", label: "90d" },
  { value: "all", label: "All" },
];

type TimeRangePickerProps = Readonly<{
  className?: string;
}>;

export function TimeRangePicker({ className }: TimeRangePickerProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const current = parseTimeRange(searchParams.get("range"));

  function setRange(range: TimeRange) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("range", range);
    router.replace(`${pathname}?${params.toString()}`);
  }

  return (
    <fieldset className={cn("flex flex-wrap gap-1 border-0 p-0", className)}>
      <legend className="sr-only">Time range</legend>
      {RANGES.map((range) => (
        <button
          key={range.value}
          type="button"
          onClick={() => { setRange(range.value); }}
          className={cn(
            "rounded-md border px-2.5 py-1 font-mono text-xs transition-colors",
            current === range.value
              ? "border-foreground bg-foreground text-background"
              : "border-border text-muted-foreground hover:text-foreground",
          )}
        >
          {range.label}
        </button>
      ))}
    </fieldset>
  );
}
