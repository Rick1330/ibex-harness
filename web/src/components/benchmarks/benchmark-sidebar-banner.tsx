import { Gauge } from "lucide-react";

export function BenchmarkSidebarBanner() {
  return (
    <div className="sidebar-banner benchmark-sidebar-banner flex flex-col gap-2 border-b border-border px-1 pb-3">
      <p className="flex items-center gap-2 px-1 text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
        <Gauge className="size-3.5 shrink-0" aria-hidden strokeWidth={1.5} />
        Benchmarks
      </p>
    </div>
  );
}
