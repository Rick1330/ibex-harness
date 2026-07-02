import type { ReactNode } from "react";

import { BenchmarkTabNav } from "@/components/benchmarks/benchmark-tab-nav";

export default function BenchmarksLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-[calc(100vh-var(--site-nav-height))] bg-background">
      <div className="container mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <header className="mb-6">
          <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Performance
          </p>
          <h1 className="text-3xl font-bold tracking-tight text-foreground md:text-4xl">
            Benchmarks
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Proxy overhead, load test, and regression data from CI. Updated on every successful
            main benchmark run.
          </p>
        </header>
        <BenchmarkTabNav />
        <main>{children}</main>
      </div>
    </div>
  );
}
