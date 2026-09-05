"use client";

import { Gauge } from "lucide-react";
import { usePathname } from "next/navigation";

import { suiteForPathname } from "@/lib/benchmarks/suites";

export function BenchmarkSidebarBanner() {
  const pathname = usePathname();
  const normalized = (pathname || "/benchmarks").replace(/\/$/, "") || "/benchmarks";
  const suite = suiteForPathname(normalized);
  const subtitle =
    normalized === "/benchmarks" ? "Overview" : (suite?.label ?? "Benchmarks");

  return (
    <div className="sidebar-banner benchmark-sidebar-banner flex flex-col gap-2 border-b border-border px-1 pb-3">
      <p className="flex items-center gap-2 px-1 text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
        <Gauge className="size-3.5 shrink-0" aria-hidden strokeWidth={1.5} />
        Benchmarks
      </p>
      <p className="truncate px-1 text-xs text-muted-foreground">{subtitle}</p>
    </div>
  );
}
