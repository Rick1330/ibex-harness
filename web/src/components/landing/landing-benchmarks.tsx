import Link from "next/link";

import { SectionShell } from "@/components/chrome/section-shell";
import { BENCHMARKS } from "@/lib/landing-content";

/** §04 · Benchmarks — mono tabular numbers (design §6). */
export function LandingBenchmarks() {
  return (
    <SectionShell
      id="benchmarks"
      section="§04"
      label="BENCHMARKS"
      docHref="/benchmarks"
      docLabel="See full methodology"
    >
      <div className="grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
        {BENCHMARKS.map((metric) => (
          <div key={metric.label} className="bg-background px-6 py-8 text-center">
            <div
              className="font-mono text-4xl font-medium tracking-tight"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {metric.value}
            </div>
            <div className="mt-2 font-mono text-xs uppercase tracking-[0.12em] text-foreground-muted">
              {metric.label}
            </div>
          </div>
        ))}
      </div>
      <p className="mt-6">
        <Link
          href="/benchmarks"
          className="font-mono text-xs text-foreground-muted transition-colors hover:text-accent"
        >
          See full methodology →
        </Link>
      </p>
    </SectionShell>
  );
}
